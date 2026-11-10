"""
Discovery Scheduler Task
Checks for scan profiles due for execution and triggers background scans.
Registered with SchedulerService — runs every 60 seconds.
"""
import logging
from datetime import timedelta

from models import db, ScanProfile, ScanRun
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


class DiscoverySchedulerTask:
    """Automatic discovery scan scheduler."""

    @staticmethod
    def register(scheduler, app) -> None:
        """Register the task; orphaned runs are recovered now on a single node, by the leader in HA."""
        from utils.ha import ha_enabled
        task = DiscoverySchedulerTask.execute
        if ha_enabled():
            import os
            from config.settings import Config
            node_id = Config.NODE_ID

            def recover_after_takeover():
                from services.scheduler_leader import fresh_node_ids
                return DiscoverySchedulerTask.recover_stale_runs(
                    keep_nodes=fresh_node_ids(scheduler.wake_interval))
            scheduler.on_leadership(recover_after_takeover)

            def recover_then_execute():
                # A node can go stale after takeover: its runs are orphans from then on
                from services.scheduler_leader import fresh_node_ids
                DiscoverySchedulerTask.recover_stale_runs(
                    live_nodes=fresh_node_ids(scheduler.wake_interval) | {node_id})
                DiscoverySchedulerTask.execute()
            task = recover_then_execute
            if os.environ.get('UCM_SCHEDULER_PROCESS') != '1':
                # The web process (gunicorn master included) starts before its workers:
                # no run of this node is alive yet; only the scheduler child skips this
                with app.app_context():
                    DiscoverySchedulerTask.recover_stale_runs(own_node=node_id)
        else:
            # Scan runs orphaned by a crash/restart stay 'running' forever and
            # would block future scheduled scans of their profile (#293)
            with app.app_context():
                DiscoverySchedulerTask.recover_stale_runs()
        scheduler.register_task(
            name="discovery_scan",
            func=task,
            interval=60,  # Check every minute for due profiles
            description="Run scheduled network discovery scans"
        )

    @staticmethod
    def recover_stale_runs(keep_nodes=None, live_nodes=None, own_node=None) -> int:
        """Mark scan runs orphaned by a process restart as failed.

        A scan run lives in a daemon thread; if the process dies mid-scan the
        row stays 'running' forever and would block future scheduled scans of
        its profile. With no argument every running scan is orphaned (one
        node, at startup). HA: ``keep_nodes`` (takeover) and ``live_nodes`` (every
        pass) keep the scans of those live nodes, scheduled ones only when started after
        the node's process started; ``own_node`` (node startup) fails only that node's scans.
        """
        try:
            from models import ClusterNode
            query = ScanRun.query.filter_by(status='running')
            # Only a node's scheduler process starts scheduled scans: they die with that process
            started_by_current = db.exists().where(db.and_(
                ClusterNode.node_id == ScanRun.node_id, ScanRun.started_at > ClusterNode.started_at))
            for nodes in (keep_nodes, live_nodes):
                if nodes is not None:
                    query = query.filter(db.or_(
                        db.and_(ScanRun.triggered_by == 'scheduled', ~started_by_current),
                        ScanRun.node_id.is_(None),
                        ScanRun.node_id.notin_(list(nodes) or [''])))
            if own_node is not None:
                query = query.filter(ScanRun.node_id == own_node)
            stale = query.update(
                {'status': 'failed', 'completed_at': utc_now()},
                synchronize_session=False,
            )
            db.session.commit()
            if stale:
                logger.warning(f"Marked {stale} orphaned discovery scan run(s) as failed")
            return stale
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to recover stale discovery scan runs: {e}", exc_info=True)
            return 0

    @staticmethod
    def _advance_next_scan(profile, now) -> bool:
        """Push next_scan_at one interval forward, BEFORE the scan runs.

        The scanner also recomputes it on completion, but a scan that crashes
        or outlives the interval must not leave next_scan_at in the past —
        that re-triggered the same giant scan on every restart (#293).
        Claimed only while still due and scheduled in the database: of two executors,
        only one moves it, and a schedule disabled meanwhile starts nothing.
        """
        seen = profile.next_scan_at
        name = profile.name
        due = (ScanProfile.next_scan_at.is_(None) if seen is None
               else ScanProfile.next_scan_at <= now)
        try:
            claimed = ScanProfile.query.filter(
                ScanProfile.id == profile.id, ScanProfile.schedule_enabled == True,  # noqa: E712
                due).update(
                {ScanProfile.next_scan_at:
                 now + timedelta(minutes=profile.schedule_interval_minutes or 1440)},
                synchronize_session=False)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to advance next_scan_at for profile '{name}': {e}",
                         exc_info=True)
            return False
        if claimed != 1:
            logger.info(f"Discovery profile '{name}' was claimed by another executor")
        return claimed == 1

    @staticmethod
    def execute() -> None:
        """Check all enabled profiles and trigger scans for those due."""
        try:
            now = utc_now()
            due_profiles = ScanProfile.query.filter(
                ScanProfile.schedule_enabled == True,
                ScanProfile.next_scan_at <= now,
            ).all()

            if not due_profiles:
                logger.debug("No discovery profiles due for scanning")
                return

            from services.discovery_service import DiscoveryService
            from flask import current_app
            service = DiscoveryService()

            triggered = 0
            for profile in due_profiles:
                try:
                    targets = profile.targets_list
                    ports = profile.ports_list
                    if not targets:
                        logger.warning(f"Discovery profile '{profile.name}' has no targets, skipping")
                        continue

                    if ScanRun.query.filter_by(scan_profile_id=profile.id,
                                               status='running').count():
                        logger.info(f"Discovery profile '{profile.name}' still has a scan "
                                    f"running, deferring to next interval")
                        DiscoverySchedulerTask._advance_next_scan(profile, now)
                        continue

                    if not DiscoverySchedulerTask._advance_next_scan(profile, now):
                        continue

                    logger.info(f"Starting scheduled scan for profile '{profile.name}' "
                                f"({len(targets)} targets, ports {ports})")

                    service.start_scan(
                        targets=targets,
                        ports=ports,
                        profile_id=profile.id,
                        triggered_by='scheduled',
                        triggered_by_user='scheduler',
                        app=current_app._get_current_object(),
                        timeout=profile.timeout,
                        max_workers=profile.max_workers,
                        resolve_dns=profile.resolve_dns,
                    )
                    triggered += 1

                except Exception as e:
                    logger.error(f"Error starting scheduled scan for profile "
                                 f"'{profile.name}': {e}", exc_info=True)

            if triggered:
                logger.info(f"Discovery scheduler: triggered {triggered} profile scan(s)")

        except Exception as e:
            logger.error(f"Error in discovery scheduler task: {e}", exc_info=True)
