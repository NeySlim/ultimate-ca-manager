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
from sqlalchemy import text
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

bp = Blueprint('dashboard_v2', __name__)


@bp.route('/api/v2/stats/overview', methods=['GET'])
def get_public_stats():
    """Get public overview statistics (no auth required - for login page)"""
    try:
        
        # Query counts directly with SQL to avoid import issues
        total_cas = db.session.execute(text("SELECT COUNT(*) FROM certificate_authorities")).scalar() or 0
        total_certs = db.session.execute(text("SELECT COUNT(*) FROM certificates")).scalar() or 0
        
        # Try ACME accounts table
        try:
            acme_accounts = db.session.execute(text("SELECT COUNT(*) FROM acme_accounts")).scalar() or 0
        except Exception:
            logger.debug("ACME accounts table not available")
            acme_accounts = 0
        
        # Active users
        try:
            active_users = db.session.execute(text("SELECT COUNT(*) FROM users WHERE is_active = 1")).scalar() or 0
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
    
    # Count certificates
    total_certs = Certificate.query.count()
    
    # Count expired (past valid_to, not revoked)
    now = utc_now()
    expired = Certificate.query.filter(
        Certificate.valid_to < now,
        Certificate.revoked == False
    ).count()
    
    # Count expiring soon (next 30 days, not yet expired)
    expiry_threshold = now + timedelta(days=30)
    expiring_soon = Certificate.query.filter(
        Certificate.valid_to <= expiry_threshold,
        Certificate.valid_to >= now,
        Certificate.revoked == False
    ).count()
    
    # Count revoked
    revoked = Certificate.query.filter_by(revoked=True).count()
    
    # Count pending CSRs (if CSR table exists)
    pending_csrs = 0
    try:
        pending_csrs = db.session.execute(
            text("SELECT COUNT(*) FROM certificate_requests WHERE status = 'pending'")
        ).scalar() or 0
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
    
    return success_response(data={
        'total_cas': total_cas,
        'total_certificates': total_certs,
        'expiring_soon': expiring_soon,
        'expired': expired,
        'revoked': revoked,
        'pending_csrs': pending_csrs,
        'acme_renewals': acme_renewals
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
        'created_at': ca.created_at.isoformat() if ca.created_at else None,
        'valid_to': ca.valid_to.isoformat() if ca.valid_to else None
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
    
    return success_response(data=[{
        'id': cert.id,
        'refid': cert.refid,
        'descr': cert.descr,
        'common_name': cert.common_name,
        'subject': cert.subject,
        'valid_from': cert.valid_from.isoformat() if cert.valid_from else None,
        'valid_to': cert.valid_to.isoformat() if cert.valid_to else None
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
                ts = ts.isoformat()
            
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
                  AND (revoked IS NULL OR revoked = 0)
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
        logger.debug('ACME status check failed')
        status['acme'] = {'status': 'offline', 'message': 'Not configured'}
    
    # SCEP is always available if UCM is running
    status['scep'] = {'status': 'online', 'message': 'Endpoint available'}
    
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
        logger.debug('EST status check failed')
        status['est'] = {'status': 'offline', 'message': 'Disabled'}
    
    # OCSP responder status - check if any CA has OCSP enabled
    try:
        ocsp_enabled_count = db.session.execute(
            text("SELECT COUNT(*) FROM certificate_authorities WHERE ocsp_enabled = 1")
        ).scalar() or 0
        if ocsp_enabled_count > 0:
            status['ocsp'] = {'status': 'online', 'message': f'{ocsp_enabled_count} CA(s) with OCSP'}
        else:
            status['ocsp'] = {'status': 'offline', 'message': 'No CA has OCSP enabled'}
    except Exception:
        logger.debug('OCSP status check failed')
        status['ocsp'] = {'status': 'offline', 'message': 'Status unknown'}
    
    # CRL distribution status - check if any CA has CDP enabled
    try:
        cdp_count = db.session.execute(
            text("SELECT COUNT(*) FROM certificate_authorities WHERE cdp_enabled = 1")
        ).scalar() or 0
        if cdp_count > 0:
            status['crl'] = {'status': 'online', 'message': f'{cdp_count} CA(s) with CDP'}
        else:
            status['crl'] = {'status': 'online', 'message': 'Available on demand'}
    except Exception:
        status['crl'] = {'status': 'online', 'message': 'Distribution active'}
    
    # Auto-renewal status
    try:
        renewal_enabled = db.session.execute(
            text("SELECT value FROM system_config WHERE key = 'auto_renewal_enabled'")
        ).scalar()
        if renewal_enabled == 'true':
            pending = db.session.execute(
                text("""SELECT COUNT(*) FROM certificates 
                    WHERE revoked = 0 AND valid_to IS NOT NULL 
                    AND valid_to BETWEEN datetime('now') AND datetime('now', '+30 days')""")
            ).scalar() or 0
            msg = f'Scheduled ({pending} pending)' if pending > 0 else 'Scheduled'
            status['auto_renewal'] = {'status': 'online', 'message': msg}
        else:
            status['auto_renewal'] = {'status': 'offline', 'message': 'Disabled'}
    except Exception:
        status['auto_renewal'] = {'status': 'offline', 'message': 'Disabled'}
    
    # SMTP / Email notifications status
    try:
        smtp_host = db.session.execute(
            text("SELECT value FROM system_config WHERE key = 'email_smtp_host'")
        ).scalar()
        smtp_enabled = db.session.execute(
            text("SELECT value FROM system_config WHERE key = 'email_enabled'")
        ).scalar()
        if smtp_enabled == 'true' and smtp_host:
            status['smtp'] = {'status': 'online', 'message': f'Host: {smtp_host}'}
        elif smtp_host:
            status['smtp'] = {'status': 'warning', 'message': 'Configured but disabled'}
        else:
            status['smtp'] = {'status': 'offline', 'message': 'Not configured'}
    except Exception:
        status['smtp'] = {'status': 'offline', 'message': 'Not configured'}
    
    # Webhooks status
    try:
        webhook_count = db.session.execute(
            text("SELECT COUNT(*) FROM webhook_endpoints WHERE active = 1")
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
        status['webhooks'] = {'status': 'offline', 'message': 'Not configured'}
    
    # Core is online if we can respond
    status['core'] = {'status': 'online', 'message': 'Operational'}
    
    return success_response(data=status)
