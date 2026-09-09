"""
Dashboard & Stats Routes v2.0
/api/dashboard/* - Statistics and overview
/api/stats/* - Public stats (login page)
"""

from flask import Blueprint, request, g
import logging
import os
from datetime import datetime, timedelta
from auth.unified import require_auth
from utils.response import success_response
from models import db, CA, Certificate
from utils.cert_status import (
    expired_condition, expiring_condition, issued_certificates,
    pending_requests, revoked_condition, valid_condition,
)
from models.ssh import SSHCertificateAuthority, SSHCertificate
from sqlalchemy import text
from utils.datetime_utils import utc_now, utc_isoformat, to_naive_utc

logger = logging.getLogger(__name__)

bp = Blueprint('dashboard_v2', __name__)

# A dedicated TSA signer within this many days of expiry shows as `warning` on
# the System Health widget. Matches the auto-renewal window used further down.
TSA_SIGNER_WARN_DAYS = 30


def _scep_ca_usable(ca):
    """Whether api/scep_protocol.get_scep_service would accept *ca*: it
    refuses a CA without private key or certificate, an offline CA, and an
    HSM-backed CA (SCEP needs RSA envelope decryption)."""
    return bool(ca.has_private_key and ca.crt and not ca.offline and not ca.revoked and not ca.uses_hsm)


def _scep_global_ca(value):
    """The CA scep_ca_id points at (numeric id or refid), or None."""
    if not value or value == '0':
        return None
    ca = None
    try:
        ca = db.session.get(CA, int(value))
    except (ValueError, TypeError):
        ca = None
    if ca is None:
        ca = CA.query.filter_by(refid=str(value)).first()
    return ca


def _status_rollback():
    """Reset the session after a failed status probe.

    On PostgreSQL a failed statement aborts the whole transaction; without a
    rollback every later probe in the same request fails with
    InFailedSqlTransaction and the remaining badges lie about their service.
    """
    try:
        db.session.rollback()
    except Exception:
        pass

# Client-safe messages for a dedicated TSA signer that /tsa cannot load, keyed
# by the coarse `reason` from describe_configured_signer(). The underlying
# detail (which can embed parse / key-loading exception text) is logged, never
# handed to the plain-auth dashboard caller.
_TSA_SIGNER_UNUSABLE_MSG = {
    'expired': 'Signer certificate has expired',
    'revoked': 'Signer certificate is revoked',
    'key_unavailable': 'Signer private key is unavailable',
    'invalid': 'Signer certificate is not usable',
}


@bp.route('/api/v2/stats/overview', methods=['GET'])
@require_auth()
def get_public_stats():
    """Get public overview statistics (no auth required - for login page)"""
    try:
        
        total_cas = db.session.execute(text("SELECT COUNT(*) FROM certificate_authorities")).scalar() or 0
        # Certificates, not signing requests: counting every row announced
        # the pending requests as certificates here too
        total_certs = issued_certificates().count()
        
        # Try ACME accounts table
        try:
            acme_accounts = db.session.execute(text("SELECT COUNT(*) FROM acme_accounts")).scalar() or 0
        except Exception:
            logger.debug("ACME accounts table not available")
            acme_accounts = 0
        
        # Active users
        try:
            active_users = db.session.execute(text("SELECT COUNT(*) FROM users WHERE is_active = true")).scalar() or 0
        except Exception:
            logger.debug("Users table query failed")
            active_users = 1
        
        return success_response(data={
            'total_cas': total_cas,
            'total_certs': total_certs,
            'acme_accounts': acme_accounts,
            'active_users': active_users
        })
    except Exception as e:
        # Fallback if DB not ready
        return success_response(data={
            'total_cas': 0,
            'total_certs': 0,
            'acme_accounts': 0,
            'active_users': 1
        })


@bp.route('/api/v2/dashboard/stats', methods=['GET'])
@require_auth()
def get_dashboard_stats():
    """Get dashboard statistics"""
    
    # Count CAs
    total_cas = CA.query.count()
    
    # Rows holding a certificate. A row holding only a signing request is a
    # pending request, reported on its own below; counting it here made the
    # dashboard show it twice, once as a certificate and once as pending.
    now = utc_now()
    certs = issued_certificates()

    expired = certs.filter(expired_condition(now)).count()
    # A window over the valid ones, not a bucket of its own: a certificate
    # about to expire is still usable (see utils/cert_status)
    expiring_soon = certs.filter(expiring_condition(now)).count()
    revoked = certs.filter(revoked_condition()).count()
    total_certs = certs.count()
    
    # Requests still waiting for their certificate, read through the same
    # definition as the list that shows them (utils/cert_status): a hand
    # written copy of the rule drifted from it
    pending_csrs = 0
    try:
        pending_csrs = pending_requests().count()
    except Exception:
        logger.debug("Pending CSRs query failed")
    
    # Count ACME renewals (last 30 days)
    acme_renewals = 0
    try:
        thirty_days_ago = (utc_now() - timedelta(days=30)).isoformat()
        acme_renewals = db.session.execute(
            text("SELECT COUNT(*) FROM acme_orders WHERE created_at >= :date"),
            {'date': thirty_days_ago}
        ).scalar() or 0
    except Exception:
        logger.debug("Pending CSRs query failed")
    
    # A partition, like the certificates page: this figure feeds the status
    # pie chart next to expiring, expired and revoked, and each slice links
    # to the matching filter, so the four have to add up to the total and
    # never overlap. The Prometheus metrics answer the other way round, see
    # utils/cert_status.
    valid = certs.filter(valid_condition(now)).count()

    # SSH statistics
    ssh_cas = 0
    ssh_certs = 0
    ssh_user_certs = 0
    ssh_host_certs = 0
    try:
        ssh_cas = SSHCertificateAuthority.query.count()
        ssh_certs = SSHCertificate.query.count()
        ssh_user_certs = SSHCertificate.query.filter_by(cert_type='user').count()
        ssh_host_certs = SSHCertificate.query.filter_by(cert_type='host').count()
    except Exception:
        logger.debug("SSH stats query failed - tables may not exist")

    return success_response(data={
        'total_cas': total_cas,
        'total_certificates': total_certs,
        'valid': valid,
        'expiring_soon': expiring_soon,
        'expired': expired,
        'revoked': revoked,
        'pending_csrs': pending_csrs,
        'acme_renewals': acme_renewals,
        'ssh_cas': ssh_cas,
        'ssh_certificates': ssh_certs,
        'ssh_user_certs': ssh_user_certs,
        'ssh_host_certs': ssh_host_certs
    })


@bp.route('/api/v2/dashboard/recent-cas', methods=['GET'])
@require_auth(['read:cas'])
def get_recent_cas():
    """Get recently created CAs"""
    
    limit = request.args.get('limit', 5, type=int)
    
    recent = CA.query.order_by(CA.created_at.desc()).limit(limit).all()
    
    return success_response(data=[{
        'id': ca.id,
        'refid': ca.refid,
        'descr': ca.descr,
        'common_name': ca.common_name,
        'is_root': ca.is_root,
        'created_at': utc_isoformat(ca.created_at),
        'valid_to': utc_isoformat(ca.valid_to)
    } for ca in recent])


@bp.route('/api/v2/dashboard/expiring-certs', methods=['GET'])
@require_auth(['read:certificates'])
def get_expiring_certificates():
    """Get next certificates to expire (soonest first, not yet expired)"""
    
    limit = request.args.get('limit', 10, type=int)
    
    # Only certs that haven't expired yet, sorted by soonest expiration
    certs = Certificate.query.filter(
        Certificate.valid_to != None,
        Certificate.valid_to > utc_now(),
        Certificate.revoked == False
    ).order_by(Certificate.valid_to.asc()).limit(limit).all()

    # Flag the configured dedicated TSA signer so the widget can mark it as
    # infrastructure — its expiry means /tsa starts returning 503.
    tsa_signer_refid = db.session.execute(
        text("SELECT value FROM system_config WHERE key = 'tsa_signer_cert_refid'")
    ).scalar() or None

    return success_response(data=[{
        'id': cert.id,
        'refid': cert.refid,
        'descr': cert.descr,
        'common_name': cert.common_name,
        'subject': cert.subject,
        'valid_from': utc_isoformat(cert.valid_from),
        'valid_to': utc_isoformat(cert.valid_to),
        'is_tsa_signer': bool(tsa_signer_refid) and cert.refid == tsa_signer_refid,
    } for cert in certs])


@bp.route('/api/v2/dashboard/activity', methods=['GET'])
@require_auth()
def get_activity_log():
    """Get recent activity"""
    
    limit = request.args.get('limit', 20, type=int)
    
    # Human-readable action labels
    ACTION_LABELS = {
        'login_success': 'Logged in',
        'login_failed': 'Login failed',
        'logout': 'Logged out',
        'create': 'Created',
        'update': 'Updated',
        'delete': 'Deleted',
        'revoke': 'Revoked',
        'export': 'Exported',
        'import': 'Imported',
        'sign': 'Signed',
        'renew': 'Renewed',
    }
    
    try:
        results = db.session.execute(
            text("""
                SELECT action, resource_type, resource_id, username, timestamp, details
                FROM audit_logs 
                ORDER BY timestamp DESC 
                LIMIT :limit
            """),
            {'limit': limit}
        ).fetchall()
        
        activity = []
        for row in results:
            action = row.action or 'Unknown'
            resource = row.resource_type or ''
            
            # Use details if available, otherwise build message
            if row.details:
                message = row.details
            else:
                action_label = ACTION_LABELS.get(action, action.replace('_', ' ').title())
                if resource and resource != 'user':
                    message = f"{action_label} {resource}"
                else:
                    message = action_label
            
            # Handle timestamp
            ts = row.timestamp
            if ts and hasattr(ts, 'isoformat'):
                ts = utc_isoformat(ts)
            
            activity.append({
                'type': resource or 'system',
                'action': action,
                'message': message,
                'timestamp': ts,
                'user': row.username or 'System',
            })
        
        return success_response(data={'activity': activity})
    except Exception as e:
        logger.error(f"Activity log error: {e}")
        return success_response(data={'activity': []})


@bp.route('/api/v2/dashboard/certificate-trend', methods=['GET'])
@require_auth()
def get_certificate_trend():
    """Get certificate activity trend (issued/revoked/expired per day)"""
    
    days = request.args.get('days', 7, type=int)
    days = min(max(days, 1), 90)  # clamp 1-90
    
    try:
        today = utc_now().date()
        start_date = today - timedelta(days=days - 1)
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(today, datetime.max.time())
        
        # 3 grouped queries instead of 3×N
        issued_rows = db.session.execute(
            text("""
                SELECT DATE(created_at) as day, COUNT(*) as cnt
                FROM certificates
                WHERE created_at >= :start AND created_at <= :end
                GROUP BY DATE(created_at)
            """),
            {'start': start_dt, 'end': end_dt}
        ).fetchall()
        
        revoked_rows = db.session.execute(
            text("""
                SELECT DATE(revoked_at) as day, COUNT(*) as cnt
                FROM certificates
                WHERE revoked_at >= :start AND revoked_at <= :end
                GROUP BY DATE(revoked_at)
            """),
            {'start': start_dt, 'end': end_dt}
        ).fetchall()
        
        expired_rows = db.session.execute(
            text("""
                SELECT DATE(valid_to) as day, COUNT(*) as cnt
                FROM certificates
                WHERE valid_to >= :start AND valid_to <= :end
                  AND revoked IS NOT TRUE
                GROUP BY DATE(valid_to)
            """),
            {'start': start_dt, 'end': end_dt}
        ).fetchall()
        
        # Index by date string for O(1) lookup
        issued_map = {str(r[0]): r[1] for r in issued_rows}
        revoked_map = {str(r[0]): r[1] for r in revoked_rows}
        expired_map = {str(r[0]): r[1] for r in expired_rows}
        
        trend_data = []
        for i in range(days):
            day = start_date + timedelta(days=i)
            day_str = day.isoformat()
            label = day.strftime('%a') if days <= 7 else day.strftime('%d/%m')
            
            trend_data.append({
                'name': label,
                'date': day_str,
                'issued': issued_map.get(day_str, 0),
                'revoked': revoked_map.get(day_str, 0),
                'expired': expired_map.get(day_str, 0),
            })
        
        return success_response(data={'trend': trend_data})
    except Exception as e:
        logger.error(f"Certificate trend error: {e}")
        # Return empty but valid data
        return success_response(data={'trend': []})


@bp.route('/api/v2/dashboard/system-status', methods=['GET'])
@require_auth()
def get_system_status():
    """Get system services status (no auth required - for login page)"""
    
    status = {
        'database': {'status': 'online', 'message': 'Connected'},
        'acme': {'status': 'online', 'message': 'Running'},
        'scep': {'status': 'online', 'message': 'Running'},
        'core': {'status': 'online', 'message': 'Operational'}
    }
    
    # Check database
    try:
        db.session.execute(text('SELECT 1'))
        status['database'] = {'status': 'online', 'message': 'Connected'}
    except Exception:
        _status_rollback()
        logger.debug('Database status check failed')
        status['database'] = {'status': 'offline', 'message': 'Connection failed'}
    
    # Check ACME service - check config first, then accounts
    try:
        acme_enabled = db.session.execute(text("SELECT value FROM system_config WHERE key = 'acme.enabled'")).scalar()
        acme_count = db.session.execute(text("SELECT COUNT(*) FROM acme_accounts")).scalar() or 0
        
        # Default to enabled when no config key exists (matches acme.py settings logic)
        is_enabled = acme_enabled != 'false' and acme_enabled != '0'
        
        if is_enabled:
            if acme_count > 0:
                status['acme'] = {'status': 'online', 'message': f'{acme_count} accounts'}
            else:
                status['acme'] = {'status': 'online', 'message': 'Enabled'}
        else:
            status['acme'] = {'status': 'offline', 'message': 'Disabled'}
    except Exception:
        _status_rollback()
        logger.debug('ACME status check failed')
        status['acme'] = {'status': 'offline', 'message': 'Not configured'}
    
    # SCEP: the same rules as api/scep_protocol.get_scep_service (#328: the
    # tile used to be hardcoded online). The global toggle gates every
    # endpoint, profiles included, and only the literal 'true' (or no row at
    # all) enables it. A CA the endpoint would refuse (no key, no
    # certificate, offline, HSM-backed) does not count as serving, nor does
    # an enabled profile bound to such a CA.
    try:
        from models.scep import ScepProfile
        scep_enabled = db.session.execute(
            text("SELECT value FROM system_config WHERE key = 'scep_enabled'")
        ).scalar()
        if scep_enabled is not None and scep_enabled != 'true':
            status['scep'] = {'status': 'offline', 'message': 'Disabled'}
        else:
            scep_ca_id = db.session.execute(
                text("SELECT value FROM system_config WHERE key = 'scep_ca_id'")
            ).scalar()
            global_ca = _scep_global_ca(scep_ca_id)
            global_ok = global_ca is not None and _scep_ca_usable(global_ca)
            enabled_profiles = ScepProfile.query.filter_by(enabled=True).all()
            usable_profiles = 0
            for profile in enabled_profiles:
                profile_ca = CA.query.filter_by(refid=profile.ca_refid).first()
                if profile_ca is not None and _scep_ca_usable(profile_ca):
                    usable_profiles += 1
            if global_ok and usable_profiles:
                status['scep'] = {'status': 'online',
                                  'message': f'Configured, {usable_profiles} profile(s)'}
            elif global_ok:
                status['scep'] = {'status': 'online', 'message': 'Configured'}
            elif usable_profiles:
                status['scep'] = {'status': 'online', 'message': f'{usable_profiles} profile(s)'}
            elif global_ca is not None or enabled_profiles:
                status['scep'] = {'status': 'warning', 'message': 'Enabled, CA not usable'}
            else:
                status['scep'] = {'status': 'warning', 'message': 'Enabled, no CA assigned'}
    except Exception:
        _status_rollback()
        logger.debug('SCEP status check failed')
        status['scep'] = {'status': 'offline', 'message': 'Status unknown'}
    
    # EST status - check if configured
    try:
        est_enabled = db.session.execute(
            text("SELECT value FROM system_config WHERE key = 'est_enabled'")
        ).scalar()
        est_ca = db.session.execute(
            text("SELECT value FROM system_config WHERE key = 'est_ca_refid'")
        ).scalar()
        if est_enabled == 'true' and est_ca:
            status['est'] = {'status': 'online', 'message': 'Configured'}
        elif est_enabled == 'true':
            status['est'] = {'status': 'warning', 'message': 'Enabled, no CA assigned'}
        else:
            status['est'] = {'status': 'offline', 'message': 'Disabled'}
    except Exception:
        _status_rollback()
        logger.debug('EST status check failed')
        status['est'] = {'status': 'offline', 'message': 'Disabled'}
    
    # OCSP responder status - check if any CA has OCSP enabled
    try:
        ocsp_enabled_count = db.session.execute(
            text("SELECT COUNT(*) FROM certificate_authorities WHERE ocsp_enabled = true")
        ).scalar() or 0
        if ocsp_enabled_count > 0:
            status['ocsp'] = {'status': 'online', 'message': f'{ocsp_enabled_count} CA(s) with OCSP'}
        else:
            status['ocsp'] = {'status': 'offline', 'message': 'No CA has OCSP enabled'}
    except Exception:
        _status_rollback()
        logger.debug('OCSP status check failed')
        status['ocsp'] = {'status': 'offline', 'message': 'Status unknown'}
    
    # CRL distribution status - check if any CA has CDP enabled
    try:
        cdp_count = db.session.execute(
            text("SELECT COUNT(*) FROM certificate_authorities WHERE cdp_enabled = true")
        ).scalar() or 0
        if cdp_count > 0:
            status['crl'] = {'status': 'online', 'message': f'{cdp_count} CA(s) with CDP'}
        else:
            status['crl'] = {'status': 'online', 'message': 'Available on demand'}
    except Exception:
        _status_rollback()
        status['crl'] = {'status': 'online', 'message': 'Distribution active'}
    
    # Auto-renewal status
    try:
        renewal_enabled = db.session.execute(
            text("SELECT value FROM system_config WHERE key = 'auto_renewal_enabled'")
        ).scalar()
        if renewal_enabled == 'true':
            now_dt = utc_now()
            window_end = now_dt + timedelta(days=30)
            pending = db.session.execute(
                text("""SELECT COUNT(*) FROM certificates
                    WHERE revoked IS NOT TRUE AND valid_to IS NOT NULL
                    AND valid_to >= :now AND valid_to <= :end"""),
                {'now': now_dt, 'end': window_end}
            ).scalar() or 0
            msg = f'Scheduled ({pending} pending)' if pending > 0 else 'Scheduled'
            status['auto_renewal'] = {'status': 'online', 'message': msg}
        else:
            status['auto_renewal'] = {'status': 'offline', 'message': 'Disabled'}
    except Exception:
        _status_rollback()
        status['auto_renewal'] = {'status': 'offline', 'message': 'Disabled'}
    
    # SMTP / Email notifications status. The configuration lives in the
    # smtp_config row Settings > Email writes, not in system_config keys
    # (#329: the tile read keys nothing ever wrote, so a working SMTP setup
    # showed as "Not configured"). Same readiness rules as the sender:
    # enabled, with host, port and From address.
    try:
        from models.email_notification import SMTPConfig
        smtp = SMTPConfig.query.first()
        smtp_host = (smtp.smtp_host or '').strip() if smtp else ''
        if not smtp_host:
            status['smtp'] = {'status': 'offline', 'message': 'Not configured'}
        elif not smtp.enabled:
            status['smtp'] = {'status': 'warning', 'message': 'Configured but disabled'}
        elif not (smtp.smtp_port and (smtp.smtp_from or '').strip()):
            status['smtp'] = {'status': 'warning', 'message': 'Enabled, port or From address missing'}
        else:
            status['smtp'] = {'status': 'online', 'message': f'Host: {smtp_host}'}
    except Exception:
        _status_rollback()
        logger.debug('SMTP status check failed')
        status['smtp'] = {'status': 'offline', 'message': 'Status unknown'}
    
    # Webhooks status
    try:
        webhook_count = db.session.execute(
            text("SELECT COUNT(*) FROM webhook_endpoints WHERE enabled = true")
        ).scalar() or 0
        total_webhooks = db.session.execute(
            text("SELECT COUNT(*) FROM webhook_endpoints")
        ).scalar() or 0
        if webhook_count > 0:
            status['webhooks'] = {'status': 'online', 'message': f'{webhook_count} active endpoint(s)'}
        elif total_webhooks > 0:
            status['webhooks'] = {'status': 'warning', 'message': f'{total_webhooks} endpoint(s), none active'}
        else:
            status['webhooks'] = {'status': 'offline', 'message': 'No endpoints'}
    except Exception:
        _status_rollback()
        status['webhooks'] = {'status': 'offline', 'message': 'Not configured'}
    
    # TSA (RFC 3161). A configured dedicated signer is a single point of failure:
    # /tsa returns 503 the moment it expires, is revoked, or its key stops
    # decrypting, with no CA fallback. Surface its health before that happens.
    # The status rules mirror api/tsa_protocol.py: the grandfathered enable rule
    # (missing tsa_enabled row = enabled) and the CA-path gates both live in
    # tsa_service helpers so the widget and the endpoint cannot drift apart.
    try:
        from services.tsa_service import (
            describe_configured_signer, tsa_ca_certificate_path_ready,
            tsa_is_enabled,
        )
        if not tsa_is_enabled():
            status['tsa'] = {'status': 'offline', 'message': 'Disabled'}
        else:
            signer = describe_configured_signer()
            if not signer.get('configured'):
                if tsa_ca_certificate_path_ready():
                    status['tsa'] = {'status': 'online',
                                     'message': 'Signing with CA certificate'}
                else:
                    status['tsa'] = {'status': 'offline',
                                     'message': 'No signing certificate configured'}
            elif not signer.get('usable'):
                logger.warning('TSA dashboard: dedicated signer unusable: %s',
                               signer.get('error'))
                status['tsa'] = {
                    'status': 'offline',
                    'message': _TSA_SIGNER_UNUSABLE_MSG.get(
                        signer.get('reason'), 'Signer certificate is not usable'),
                }
            else:
                dt = to_naive_utc(
                    datetime.fromisoformat(signer['not_after'])
                ) if signer.get('not_after') else None
                days_left = (dt - utc_now()).days if dt else None
                if days_left is not None and days_left <= TSA_SIGNER_WARN_DAYS:
                    status['tsa'] = {
                        'status': 'warning',
                        'message': f'Signer expires in {max(days_left, 0)} day(s)',
                    }
                else:
                    status['tsa'] = {'status': 'online', 'message': 'Dedicated signer'}
    except Exception:
        _status_rollback()
        # A resolver bug is exactly when the dashboard must not claim health.
        logger.debug('TSA status check failed', exc_info=True)
        status['tsa'] = {'status': 'warning', 'message': 'Status unavailable'}

    # Core is online if we can respond
    status['core'] = {'status': 'online', 'message': 'Operational'}

    return success_response(data=status)
