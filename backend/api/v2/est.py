"""
EST Management Routes v2.0
/api/v2/est/* - EST configuration and statistics
"""

from flask import Blueprint, request, g
from auth.unified import require_auth
from utils.response import success_response, error_response
from utils.db_transaction import safe_commit
from models import db, SystemConfig, CA, AuditLog
from services.audit_service import AuditService
import json
import logging
import re

logger = logging.getLogger(__name__)

# Same safe charset the EST protocol layer accepts for a path label.
_EST_LABEL_RE = re.compile(r'^[A-Za-z0-9._-]{1,64}$')

bp = Blueprint('est_v2', __name__)


def get_config(key, default=None):
    """Get config value from database"""
    config = SystemConfig.query.filter_by(key=key).first()
    return config.value if config else default


def set_config(key, value):
    """Set config value in database"""
    config = SystemConfig.query.filter_by(key=key).first()
    if config:
        config.value = str(value) if value is not None else None
    else:
        config = SystemConfig(key=key, value=str(value) if value is not None else None)
        db.session.add(config)


@bp.route('/api/v2/est/config', methods=['GET'])
@require_auth(['read:est'])
def get_est_config():
    """Get EST configuration from database"""
    ca_refid = get_config('est_ca_refid', '')
    ca_id = None
    ca_name = None
    if ca_refid:
        ca = CA.query.filter_by(refid=ca_refid).first()
        if ca:
            ca_id = ca.id
            ca_name = ca.descr

    # RFC 7030 §3.2.2 CA labels: {label: ca_refid}. Enriched with the CA name
    # so the UI can show which authority each label serves.
    labels = {}
    try:
        raw_labels = json.loads(get_config('est_labels', '') or '{}')
        if isinstance(raw_labels, dict):
            for label, refid in raw_labels.items():
                ca_row = CA.query.filter_by(refid=refid).first()
                labels[label] = {
                    'ca_refid': refid,
                    'ca_name': ca_row.descr if ca_row else None,
                }
    except (TypeError, ValueError):
        logger.warning('Invalid est_labels configuration; reporting none')

    return success_response(data={
        'enabled': get_config('est_enabled', 'false') == 'true',
        'ca_refid': ca_refid,
        'ca_id': ca_id,
        'ca_name': ca_name,
        'username': get_config('est_username', ''),
        'password_set': bool(get_config('est_password', '')),
        'validity_days': int(get_config('est_validity_days', '365') or 365),
        'response_include_chain': get_config('est_response_include_chain', 'false') == 'true',
        'labels': labels,
    })


@bp.route('/api/v2/est/config', methods=['PATCH'])
@require_auth(['write:est'])
def update_est_config():
    """Update EST configuration in database"""
    data = request.json or {}

    if 'enabled' in data:
        set_config('est_enabled', 'true' if data['enabled'] else 'false')
    if 'ca_refid' in data:
        # Validate CA exists if a non-empty refid was provided
        if data['ca_refid']:
            if not CA.query.filter_by(refid=data['ca_refid']).first():
                return error_response('CA not found', 404)
        set_config('est_ca_refid', data['ca_refid'] or '')
    if 'ca_id' in data:
        # Look up refid from CA id
        if data['ca_id']:
            ca = db.session.get(CA, data['ca_id'])
            if not ca:
                return error_response('CA not found', 404)
            set_config('est_ca_refid', ca.refid)
        else:
            set_config('est_ca_refid', '')
    if 'username' in data:
        set_config('est_username', data['username'])
    if 'password' in data and data['password']:
        from werkzeug.security import generate_password_hash
        set_config('est_password', generate_password_hash(data['password']))
    if 'validity_days' in data:
        # Bound to PKI-internal cap (10 years).
        try:
            vd = int(data['validity_days'])
        except (TypeError, ValueError):
            return error_response('validity_days must be an integer', 400)
        if vd < 1 or vd > 3650:
            return error_response('validity_days must be between 1 and 3650', 400)
        set_config('est_validity_days', str(vd))
    if 'response_include_chain' in data:
        set_config('est_response_include_chain',
                   'true' if data['response_include_chain'] else 'false')

    if 'labels' in data:
        # RFC 7030 §3.2.2 CA labels. Accepts {label: ca_refid} or the enriched
        # {label: {ca_refid: ...}} shape the GET returns, so a client can round
        # -trip what it read. Every CA must exist: a label pointing at nothing
        # would 404 at enrollment time with no hint of the misconfiguration.
        labels_in = data['labels'] or {}
        if not isinstance(labels_in, dict):
            return error_response('labels must be an object', 400)
        if len(labels_in) > 50:
            return error_response('too many EST labels (max 50)', 400)

        cleaned = {}
        for label, value in labels_in.items():
            if not isinstance(label, str) or not _EST_LABEL_RE.match(label):
                return error_response(
                    f"Invalid EST label '{str(label)[:20]}': use letters, digits, "
                    "dot, dash or underscore (max 64 characters)", 400)
            refid = value.get('ca_refid') if isinstance(value, dict) else value
            if not isinstance(refid, str) or not refid:
                return error_response(f"Label '{label}' has no CA", 400)
            if not CA.query.filter_by(refid=refid).first():
                return error_response(f"Label '{label}': CA not found", 404)
            cleaned[label] = refid
        set_config('est_labels', json.dumps(cleaned))

    ok, _err = safe_commit(logger, "Failed to update EST configuration")
    if not ok:
        return _err

    AuditService.log_action(
        action='est_config_update',
        resource_type='est',
        resource_name='EST Configuration',
        details='Updated EST configuration',
        success=True
    )

    return success_response(message='EST configuration saved')


@bp.route('/api/v2/est/stats', methods=['GET'])
@require_auth(['read:est'])
def get_est_stats():
    """Get EST enrollment statistics from audit logs"""
    try:
        total = AuditLog.query.filter(
            AuditLog.action.like('est.%') | AuditLog.details.like('%EST enrollment%')
        ).count()
        successful = AuditLog.query.filter(
            (AuditLog.action.like('est.%') | AuditLog.details.like('%EST enrollment%')),
            AuditLog.success == True
        ).count()
        failed = AuditLog.query.filter(
            (AuditLog.action.like('est.%') | AuditLog.details.like('%EST enrollment%')),
            AuditLog.success == False
        ).count()

        # Also count certificate.issued with EST details
        est_issued = AuditLog.query.filter(
            AuditLog.action == 'certificate.issued',
            AuditLog.details.like('%EST%')
        ).count()

        return success_response(data={
            'total': total + est_issued,
            'successful': successful + est_issued,
            'failed': failed,
        })
    except Exception as e:
        logger.error(f"Failed to get EST stats: {e}")
        return success_response(data={
            'total': 0,
            'successful': 0,
            'failed': 0,
        })
