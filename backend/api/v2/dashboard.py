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
    from datetime import datetime
    
    limit = request.args.get('limit', 20, type=int)
    
    try:
        # Try to get audit logs if table exists
        results = db.session.execute(
            text("""
                SELECT action, entity_type, entity_id, user_id, created_at, details
                FROM audit_logs 
                ORDER BY created_at DESC 
                LIMIT :limit
            """),
            {'limit': limit}
        ).fetchall()
        
        activity = []
        for row in results:
            activity.append({
                'type': row.entity_type or 'system',
                'description': row.action or 'Unknown action',
                'timestamp': row.created_at.isoformat() if row.created_at else None,
                'user': f'User {row.user_id}' if row.user_id else 'System'
            })
        
        return success_response(data={'activity': activity})
    except:
        # If audit_logs table doesn't exist, return empty
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
    
    # Check ACME service (check if enabled in config or has active orders)
    try:
        acme_count = db.session.execute(text("SELECT COUNT(*) FROM acme_accounts")).scalar()
        if acme_count > 0:
            status['acme'] = {'status': 'online', 'message': f'{acme_count} accounts'}
        else:
            status['acme'] = {'status': 'idle', 'message': 'No accounts'}
    except:
        status['acme'] = {'status': 'disabled', 'message': 'Not configured'}
    
    # SCEP is always available if UCM is running
    status['scep'] = {'status': 'online', 'message': 'Endpoint available'}
    
    # Core is online if we can respond
    status['core'] = {'status': 'online', 'message': 'Operational'}
    
    return success_response(data=status)
