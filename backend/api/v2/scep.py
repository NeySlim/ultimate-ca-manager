"""
SCEP Management Routes v2.0
/api/scep/* - SCEP configuration and requests
"""

from flask import Blueprint, request, g
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db, SCEPRequest, SystemConfig, CA
from datetime import datetime, timezone
import secrets

bp = Blueprint('scep_v2', __name__)


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


@bp.route('/api/v2/scep/config', methods=['GET'])
@require_auth(['read:scep'])
def get_scep_config():
    """Get SCEP configuration from database"""
    return success_response(data={
        'enabled': get_config('scep_enabled', 'true') == 'true',
        'url': get_config('scep_url', '/scep/pkiclient.exe'),
        'ca_id': int(get_config('scep_ca_id', '0') or 0) or None,
        'ca_ident': get_config('scep_ca_ident', 'ucm-ca'),
        'auto_approve': get_config('scep_auto_approve', 'false') == 'true',
        'challenge_validity': int(get_config('scep_challenge_validity', '24'))
    })


@bp.route('/api/v2/scep/config', methods=['PATCH'])
@require_auth(['write:scep'])
def update_scep_config():
    """Update SCEP configuration in database"""
    data = request.json or {}
    
    if 'enabled' in data:
        set_config('scep_enabled', 'true' if data['enabled'] else 'false')
    if 'url' in data:
        set_config('scep_url', data['url'])
    if 'ca_id' in data:
        set_config('scep_ca_id', str(data['ca_id']) if data['ca_id'] else '')
    if 'ca_ident' in data:
        set_config('scep_ca_ident', data['ca_ident'])
    if 'auto_approve' in data:
        set_config('scep_auto_approve', 'true' if data['auto_approve'] else 'false')
    if 'challenge_validity' in data:
        set_config('scep_challenge_validity', str(data['challenge_validity']))
    
    db.session.commit()
    
    return success_response(message='SCEP configuration saved')


@bp.route('/api/v2/scep/requests', methods=['GET'])
@require_auth(['read:scep'])
def list_scep_requests():
    """List SCEP certificate requests"""
    status = request.args.get('status')
    query = SCEPRequest.query
    
    if status:
        query = query.filter_by(status=status)
        
    requests_list = query.order_by(SCEPRequest.created_at.desc()).limit(50).all()
    
    data = [req.to_dict() for req in requests_list]
    return success_response(data=data)


@bp.route('/api/v2/scep/<int:request_id>/approve', methods=['POST'])
@require_auth(['write:scep'])
def approve_scep_request(request_id):
    """Approve SCEP request"""
    scep_req = SCEPRequest.query.get(request_id)
    if not scep_req:
        return error_response('Request not found', 404)
        
    if scep_req.status != 'pending':
        return error_response(f'Request is already {scep_req.status}', 400)
    
    username = getattr(g, 'user', {}).get('username', 'admin') if hasattr(g, 'user') else 'admin'
    
    scep_req.status = 'approved'
    scep_req.approved_by = username
    scep_req.approved_at = datetime.now(timezone.utc)
    
    db.session.commit()
    
    return success_response(
        data=scep_req.to_dict(),
        message='SCEP request approved'
    )


@bp.route('/api/v2/scep/<int:request_id>/reject', methods=['POST'])
@require_auth(['write:scep'])
def reject_scep_request(request_id):
    """Reject SCEP request"""
    data = request.json
    reason = data.get('reason', 'Rejected by admin') if data else 'Rejected by admin'
    
    scep_req = SCEPRequest.query.get(request_id)
    if not scep_req:
        return error_response('Request not found', 404)
        
    if scep_req.status != 'pending':
        return error_response(f'Request is already {scep_req.status}', 400)
    
    username = getattr(g, 'user', {}).get('username', 'admin') if hasattr(g, 'user') else 'admin'
    
    scep_req.status = 'rejected'
    scep_req.rejection_reason = reason
    scep_req.approved_by = username
    scep_req.approved_at = datetime.now(timezone.utc)
    
    db.session.commit()
    
    return success_response(
        data=scep_req.to_dict(),
        message='SCEP request rejected'
    )


@bp.route('/api/v2/scep/stats', methods=['GET'])
@require_auth(['read:scep'])
def get_scep_stats():
    """Get SCEP statistics"""
    total = SCEPRequest.query.count()
    pending = SCEPRequest.query.filter_by(status='pending').count()
    approved = SCEPRequest.query.filter_by(status='approved').count()
    rejected = SCEPRequest.query.filter_by(status='rejected').count()
    
    return success_response(data={
        'total': total,
        'pending': pending,
        'approved': approved,
        'rejected': rejected
    })


@bp.route('/api/v2/scep/challenge/<int:ca_id>', methods=['GET'])
@require_auth(['read:scep'])
def get_challenge_password(ca_id):
    """Get challenge password for a CA"""
    ca = CA.query.get(ca_id)
    if not ca:
        return error_response('CA not found', 404)
    
    challenge = get_config(f'scep_challenge_{ca_id}')
    
    return success_response(data={
        'ca_id': ca_id,
        'challenge': challenge or 'Not configured'
    })


@bp.route('/api/v2/scep/challenge/<int:ca_id>/regenerate', methods=['POST'])
@require_auth(['write:scep'])
def regenerate_challenge_password(ca_id):
    """Regenerate challenge password for a CA"""
    ca = CA.query.get(ca_id)
    if not ca:
        return error_response('CA not found', 404)
    
    # Generate a secure random challenge password
    new_challenge = secrets.token_urlsafe(24)
    set_config(f'scep_challenge_{ca_id}', new_challenge)
    db.session.commit()
    
    return success_response(
        data={'challenge': new_challenge},
        message='Challenge password regenerated'
    )

