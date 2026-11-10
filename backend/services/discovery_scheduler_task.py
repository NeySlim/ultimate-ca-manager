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
    def recover_stale_runs() -> int:
        """Mark scan runs orphaned by a process restart as failed.

        A scan run lives in a daemon thread; if the process dies mid-scan the
        row stays 'running' forever and would block future scheduled scans of
        its profile. Called once at startup, before the scheduler starts.
        """
        try:
            stale = ScanRun.query.filter_by(status='running').update(
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
