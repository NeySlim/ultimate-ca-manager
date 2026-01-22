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
        from database import db
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
    
    return success_response(data={
        'total_cas': total_cas,
        'total_certificates': total_certs,
        'expiring_soon': expiring_soon,
        'revoked': revoked
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
    limit = request.args.get('limit', 20, type=int)
    return success_response(data=[])
