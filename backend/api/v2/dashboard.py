"""
Dashboard & Stats Routes v2.0
/api/dashboard/* - Statistics and overview
/api/stats/* - Public stats (login page)
"""

from flask import Blueprint, request, g
from auth.unified import require_auth
from utils.response import success_response

bp = Blueprint('dashboard_v2', __name__)


@bp.route('/api/stats/overview', methods=['GET'])
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


@bp.route('/api/dashboard/stats', methods=['GET'])
@require_auth()
def get_dashboard_stats():
    """Get dashboard statistics"""
    return success_response(data={
        'total_cas': 0,
        'total_certificates': 0,
        'expiring_soon': 0,
        'revoked': 0
    })


@bp.route('/api/dashboard/recent-cas', methods=['GET'])
@require_auth(['read:cas'])
def get_recent_cas():
    """Get recently created CAs"""
    limit = request.args.get('limit', 5, type=int)
    return success_response(data=[])


@bp.route('/api/dashboard/expiring-certs', methods=['GET'])
@require_auth(['read:certificates'])
def get_expiring_certificates():
    """Get certificates expiring soon"""
    days = request.args.get('days', 30, type=int)
    return success_response(data=[])


@bp.route('/api/dashboard/activity', methods=['GET'])
@require_auth()
def get_activity_log():
    """Get recent activity"""
    limit = request.args.get('limit', 20, type=int)
    return success_response(data=[])
