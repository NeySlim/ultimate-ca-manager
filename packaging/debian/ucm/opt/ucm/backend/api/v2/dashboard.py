"""
Dashboard & Stats Routes v2.0
/api/dashboard/* - Statistics and overview
/api/stats/* - Public stats (login page)
"""

from flask import Blueprint, request, g
from auth.unified import require_auth
from utils.response import success_response

bp = Blueprint('dashboard_v2', __name__)


@bp.route('/api/v2/stats/overview', methods=['GET'])
def get_public_stats():
    """Get public overview statistics (no auth required - for login page)"""
    try:
        from models import db
        from sqlalchemy import text
        
        # Query counts directly with SQL to avoid import issues
        total_cas = db.session.execute(text("SELECT COUNT(*) FROM certificate_authorities")).scalar() or 0
        total_certs = db.session.execute(text("SELECT COUNT(*) FROM certificates")).scalar() or 0
        
        # Try ACME accounts table
        try:
            acme_accounts = db.session.execute(text("SELECT COUNT(*) FROM acme_accounts")).scalar() or 0
        except:
            acme_accounts = 0
        
        # Active users
        try:
            active_users = db.session.execute(text("SELECT COUNT(*) FROM users WHERE is_active = 1")).scalar() or 0
        except:
            active_users = 1  # At least one user should exist
        
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
    from models import CA, Certificate
    from datetime import datetime, timedelta
    from models import db
    from sqlalchemy import text
    
    # Count CAs
    total_cas = CA.query.count()
    
    # Count certificates
    total_certs = Certificate.query.count()
    
    # Count expiring soon (next 30 days)
    expiry_threshold = datetime.utcnow() + timedelta(days=30)
    expiring_soon = Certificate.query.filter(
        Certificate.valid_to <= expiry_threshold,
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
    except:
        pass
    
    # Count ACME renewals (last 30 days)
    acme_renewals = 0
    try:
        thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).isoformat()
        acme_renewals = db.session.execute(
            text("SELECT COUNT(*) FROM acme_orders WHERE created_at >= :date"),
            {'date': thirty_days_ago}
        ).scalar() or 0
    except:
        pass
    
    return success_response(data={
        'total_cas': total_cas,
        'total_certificates': total_certs,
        'expiring_soon': expiring_soon,
        'revoked': revoked,
        'pending_csrs': pending_csrs,
        'acme_renewals': acme_renewals
    })


@bp.route('/api/v2/dashboard/recent-cas', methods=['GET'])
@require_auth(['read:cas'])
def get_recent_cas():
    """Get recently created CAs"""
    from models import CA
    
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
    """Get certificates expiring soon"""
    from models import Certificate
    from datetime import datetime, timedelta
    
    days = request.args.get('days', 30, type=int)
    
    expiry_threshold = datetime.utcnow() + timedelta(days=days)
    
    expiring = Certificate.query.filter(
        Certificate.valid_to <= expiry_threshold,
        Certificate.revoked == False
    ).order_by(Certificate.valid_to.asc()).limit(10).all()
    
    return success_response(data=[{
        'id': cert.id,
        'refid': cert.refid,
        'descr': cert.descr,
        'subject': cert.subject,
        'valid_to': cert.valid_to.isoformat() if cert.valid_to else None
    } for cert in expiring])


@bp.route('/api/v2/dashboard/activity', methods=['GET'])
@require_auth()
def get_activity_log():
    """Get recent activity"""
    from models import db
    from sqlalchemy import text
    
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
        import logging
        logging.error(f"Activity log error: {e}")
        return success_response(data={'activity': []})


@bp.route('/api/v2/dashboard/system-status', methods=['GET'])
def get_system_status():
    """Get system services status (no auth required - for login page)"""
    from models import db
    from sqlalchemy import text
    import os
    
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
    except:
        status['database'] = {'status': 'offline', 'message': 'Connection failed'}
    
    # Check ACME service - check config first, then accounts
    try:
        acme_enabled = db.session.execute(text("SELECT value FROM system_config WHERE key = 'acme.enabled'")).scalar()
        acme_count = db.session.execute(text("SELECT COUNT(*) FROM acme_accounts")).scalar() or 0
        
        if acme_enabled == 'true' or acme_enabled == '1':
            if acme_count > 0:
                status['acme'] = {'status': 'online', 'message': f'{acme_count} accounts'}
            else:
                status['acme'] = {'status': 'online', 'message': 'Enabled'}
        else:
            status['acme'] = {'status': 'offline', 'message': 'Disabled'}
    except:
        status['acme'] = {'status': 'offline', 'message': 'Not configured'}
    
    # SCEP is always available if UCM is running
    status['scep'] = {'status': 'online', 'message': 'Endpoint available'}
    
    # OCSP responder status
    status['ocsp'] = {'status': 'online', 'message': 'Responder active'}
    
    # CRL distribution status
    status['crl'] = {'status': 'online', 'message': 'Distribution active'}
    
    # Core is online if we can respond
    status['core'] = {'status': 'online', 'message': 'Operational'}
    
    return success_response(data=status)
