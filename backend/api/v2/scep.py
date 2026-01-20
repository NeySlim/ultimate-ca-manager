"""
SCEP Management Routes v2.0
/api/scep/* - SCEP configuration and requests
"""

from flask import Blueprint, request, g
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db, SCEPRequest
from datetime import datetime

bp = Blueprint('scep_v2', __name__)


@bp.route('/api/scep/config', methods=['GET'])
@require_auth(['read:scep'])
def get_scep_config():
    """Get SCEP configuration"""
    # In future this should come from SystemConfig
    return success_response(data={
        'enabled': True,
        'url': '/scep/pkiclient.exe',
        'ca_ident': 'ucm-ca'
    })


@bp.route('/api/scep/config', methods=['PATCH'])
@require_auth(['write:scep'])
def update_scep_config():
    """Update SCEP configuration"""
    data = request.json
    # Implement logic
    return success_response(
        data=data,
        message='SCEP config updated'
    )


@bp.route('/api/scep/requests', methods=['GET'])
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


@bp.route('/api/scep/<int:request_id>/approve', methods=['POST'])
@require_auth(['write:scep'])
def approve_scep_request(request_id):
    """Approve SCEP request"""
    scep_req = SCEPRequest.query.get(request_id)
    if not scep_req:
        return error_response('Request not found', 404)
        
    if scep_req.status != 'pending':
        return error_response(f'Request is already {scep_req.status}', 400)
        
    scep_req.status = 'approved'
    scep_req.approved_by = 'current_user' # TODO: get from g.user
    scep_req.approved_at = datetime.utcnow()
    
    # Trigger SCEP processing (would typically happen async or on next poll)
    # For now just marking as approved
    
    db.session.commit()
    
    return success_response(
        data=scep_req.to_dict(),
        message='SCEP request approved'
    )


@bp.route('/api/scep/<int:request_id>/reject', methods=['POST'])
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
        
    scep_req.status = 'rejected'
    scep_req.rejection_reason = reason
    scep_req.approved_by = 'current_user'
    scep_req.approved_at = datetime.utcnow()
    
    db.session.commit()
    
    return success_response(
        data=scep_req.to_dict(),
        message='SCEP request rejected'
    )


@bp.route('/api/scep/stats', methods=['GET'])
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

