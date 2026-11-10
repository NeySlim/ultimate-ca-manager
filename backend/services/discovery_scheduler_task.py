"""
Discovery Scheduler Task
Checks for scan profiles due for execution and triggers background scans.
Registered with SchedulerService — runs every 60 seconds.
"""
import logging
from datetime import datetime, timezone, timedelta

from models import db, ScanProfile, ScanRun

logger = logging.getLogger(__name__)


class DiscoverySchedulerTask:
    """Automatic discovery scan scheduler."""

    @staticmethod
    def register(scheduler, app) -> None:
        """Register the task; orphaned runs are recovered now on a single node, by the leader in HA."""
        from utils.ha import ha_enabled
        if ha_enabled():
            def recover_after_takeover():
                from services.scheduler_leader import fresh_node_ids
                return DiscoverySchedulerTask.recover_stale_runs(
                    keep_nodes=fresh_node_ids(scheduler.wake_interval))
            scheduler.on_leadership(recover_after_takeover)
        else:
            # Scan runs orphaned by a crash/restart stay 'running' forever and
            # would block future scheduled scans of their profile (#293)
            with app.app_context():
                DiscoverySchedulerTask.recover_stale_runs()
        scheduler.register_task(
            name="discovery_scan",
            func=DiscoverySchedulerTask.execute,
            interval=60,  # Check every minute for due profiles
            description="Run scheduled network discovery scans"
        )

    @staticmethod
    def recover_stale_runs(keep_nodes=None) -> int:
        """Mark scan runs orphaned by a process restart as failed.

        A scan run lives in a daemon thread; if the process dies mid-scan the
        row stays 'running' forever and would block future scheduled scans of
        its profile. Without ``keep_nodes`` every running scan is orphaned (one
        node, at startup). With it (HA takeover), manual scans of those live
        nodes are kept; scheduled scans ran on the former leader and are not.
        """
        try:
            query = ScanRun.query.filter_by(status='running')
            if keep_nodes is not None:
                query = query.filter(db.or_(
                    ScanRun.triggered_by == 'scheduled', ScanRun.node_id.is_(None),
                    ScanRun.node_id.notin_(list(keep_nodes) or [''])))
            stale = query.update(
                {'status': 'failed', 'completed_at': datetime.now(timezone.utc)}
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
    def _advance_next_scan(profile, now) -> None:
        """Push next_scan_at one interval forward, BEFORE the scan runs.

        The scanner also recomputes it on completion, but a scan that crashes
        or outlives the interval must not leave next_scan_at in the past —
        that re-triggered the same giant scan on every restart (#293).
        """
        profile.next_scan_at = now + timedelta(minutes=profile.schedule_interval_minutes or 1440)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to advance next_scan_at for profile '{profile.name}': {e}",
                         exc_info=True)

    @staticmethod
    def execute() -> None:
        """Check all enabled profiles and trigger scans for those due."""
        try:
            now = datetime.now(timezone.utc)
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

                    DiscoverySchedulerTask._advance_next_scan(profile, now)

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
