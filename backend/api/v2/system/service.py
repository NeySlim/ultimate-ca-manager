"""
System Service Operations (HSM, Chain Repair, Service Status)
"""

from . import bp
from flask import request
from auth.unified import require_auth
from utils.response import success_response, error_response
from services.audit_service import AuditService
from services.ski_aki_backfill import get_last_run_stats as get_backfill_stats
from services.scheduler_service import get_scheduler
from services.updates import get_current_version
from services import compliance_preflight, fips_preflight
import compliance_profiles
from models import db
from config.settings import is_docker
import os
import psutil
import fips_mode
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


@bp.route('/api/v2/system/hsm-status', methods=['GET'])
@require_auth(['read:settings'])
def get_hsm_status():
    """Get HSM availability status"""
    try:
        from utils.hsm_check import get_hsm_status as _get_status
        status = _get_status()
        return success_response(data=status)
    except Exception as e:
        logger.error(f"HSM status check failed: {e}")
        return error_response("HSM status check failed", 500)


# Friendly, admin-facing labels for the registered scheduler tasks. Falls back
# to the task's own description / a title-cased name when not listed here.
_TASK_LABELS = {
    'crl_auto_regen': 'CRL regeneration',
    'audit_log_cleanup': 'Audit log cleanup',
    'cert_expiry_alerts': 'Certificate expiry alerts',
    'acme_auto_renewal': 'ACME auto-renewal',
    'ski_aki_backfill': 'Certificate chain repair',
    'cert_auto_renewal': 'Certificate auto-renewal',
    'ocsp_cache_cleanup': 'OCSP cache cleanup',
    'update_check': 'Update check',
    'discovery_scan': 'Discovery scans',
    'scheduled_reports': 'Scheduled reports',
    'scheduled_backup': 'Scheduled backups',
    'session_cleanup': 'Session cleanup',
}


@bp.route('/api/v2/system/scheduler', methods=['GET'])
@require_auth(['read:settings'])
def get_scheduler_tasks():
    """List all registered scheduler tasks with their live status."""
    try:
        statuses = get_scheduler().get_all_tasks_status()
        tasks = []
        for name, st in statuses.items():
            st = dict(st)
            st['label'] = _TASK_LABELS.get(name, (st.get('description') or name.replace('_', ' ').title()))
            tasks.append(st)
        tasks.sort(key=lambda t: t['label'].lower())
        warnings = sum(1 for t in tasks if t.get('last_error'))
        return success_response(data={
            'tasks': tasks,
            'total': len(tasks),
            'warnings': warnings,
        })
    except Exception as e:
        logger.error(f"Failed to list scheduler tasks: {e}")
        return error_response("Failed to list scheduler tasks", 500)


@bp.route('/api/v2/system/scheduler/<task_name>/run', methods=['POST'])
@require_auth(['admin:system'])
def run_scheduler_task(task_name):
    """Trigger an immediate run of a registered scheduler task."""
    try:
        scheduler = get_scheduler()
        if task_name not in scheduler.get_all_tasks_status():
            return error_response("Task not found", 404)
        result = scheduler.run_task_now(task_name)
        if result is None:
            return error_response("Task not found", 404)
        AuditService.log_action(
            action='scheduler_task_run', resource_type='system',
            resource_name=task_name, details=f"Manually ran scheduler task: {task_name}",
            success=not bool(result.get('last_error')),
        )
        result['label'] = _TASK_LABELS.get(task_name, task_name.replace('_', ' ').title())
        return success_response(data=result, message=f"Task '{task_name}' executed")
    except Exception as e:
        logger.error(f"Failed to run scheduler task {task_name}: {e}")
        return error_response("Failed to run scheduler task", 500)


@bp.route('/api/v2/system/chain-repair', methods=['GET'])
@require_auth(['read:cas'])
def get_chain_repair_status():
    """Get chain repair task status and last run stats"""
    try:
        task_status = get_scheduler().get_task_status('ski_aki_backfill') or {}
        stats = get_backfill_stats()
        return success_response(data={
            'task': task_status,
            'stats': stats
        })
    except Exception as e:
        logger.error(f"Failed to get chain repair status: {e}")
        return error_response("Failed to get chain repair status", 500)


@bp.route('/api/v2/system/chain-repair/run', methods=['POST'])
@require_auth(['write:cas'])
def run_chain_repair():
    """Trigger immediate chain repair"""
    try:
        result = get_scheduler().run_task_now('ski_aki_backfill')
        if result is None:
            return error_response("Chain repair task not found", 404)
        return success_response(data={
            'task': result,
            'stats': get_backfill_stats()
        })
    except Exception as e:
        logger.error(f"Chain repair failed: {e}")
        return error_response("Chain repair failed", 500)


@bp.route('/api/v2/system/service/status', methods=['GET'])
@require_auth(['read:settings'])
def get_service_status():
    """Get UCM service status: version, uptime, PID, memory"""
    try:
        proc = psutil.Process(os.getpid())
        parent = proc.parent()
        # Use parent (gunicorn master) if available, else current worker
        main_proc = parent if parent and 'gunicorn' in (parent.name() or '') else proc

        create_time = datetime.fromtimestamp(main_proc.create_time(), tz=timezone.utc)
        uptime_seconds = int((datetime.now(timezone.utc) - create_time).total_seconds())

        # Memory in MB
        mem_info = main_proc.memory_info()
        memory_mb = round(mem_info.rss / 1024 / 1024, 1)

        # Check if running in Docker
        is_docker_env = os.path.exists('/.dockerenv') or os.path.exists('/run/.containerenv') or os.environ.get('UCM_DOCKER') == '1'

        return success_response(data={
            'version': get_current_version(),
            'pid': main_proc.pid,
            'uptime_seconds': uptime_seconds,
            'started_at': create_time.isoformat(),
            'memory_mb': memory_mb,
            'is_docker': is_docker_env,
            'python_version': f"{os.sys.version_info.major}.{os.sys.version_info.minor}.{os.sys.version_info.micro}",
            'crypto': fips_mode.status(),
        })
    except Exception as e:
        logger.error(f"Failed to get service status: {e}")
        return error_response("Failed to get service status", 500)


@bp.route('/api/v2/system/fips-preflight', methods=['GET'])
@require_auth(['admin:system'])
def get_fips_preflight():
    """What FIPS mode would refuse on this instance; reads only."""
    try:
        return success_response(data=fips_preflight.run())
    except Exception as e:
        logger.error(f"FIPS preflight failed: {e}")
        return error_response("FIPS preflight failed", 500)
    finally:
        db.session.rollback()


@bp.route('/api/v2/system/compliance-preflight', methods=['GET'])
@require_auth(['admin:system'])
def get_compliance_preflight():
    """What a compliance profile would refuse on this instance (or on one CA); reads only."""
    name, error = compliance_profiles.normalize(request.args.get('profile'))
    if error or name is None:
        return error_response(error or 'profile is required', 400)
    ca_id = request.args.get('ca', type=int)
    if request.args.get('ca') not in (None, '') and ca_id is None:
        return error_response('ca must be a CA id', 400)
    try:
        return success_response(data=compliance_preflight.run(name, ca_id))
    except LookupError:
        return error_response('CA not found', 404)
    except Exception as e:
        logger.error(f"Compliance preflight failed: {e}")
        return error_response("Compliance preflight failed", 500)
    finally:
        db.session.rollback()


@bp.route('/api/v2/system/service/restart', methods=['POST'])
@require_auth(['write:settings'])
def restart_service():
    """Restart the UCM service"""
    if is_docker():
        return error_response("Service restart is not available in Docker. Restart the container instead.", 400)

    try:
        AuditService.log_action(
            action='service_restart',
            resource_type='system',
            details='Manual service restart requested from settings',
            success=True
        )

        from utils.service_manager import restart_service as do_restart
        success, message = do_restart()

        if success:
            return success_response(message=message)
        else:
            return error_response(message, 500)
    except Exception as e:
        logger.error(f"Failed to restart service: {e}")
        return error_response("Failed to restart service", 500)
