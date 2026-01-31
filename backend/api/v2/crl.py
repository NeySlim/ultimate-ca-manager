"""
CRL & OCSP Routes v2.0
"""

from flask import Blueprint, request, g
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db, CA, AuditLog
from models.crl import CRLMetadata
from services.crl_service import CRLService
import datetime

bp = Blueprint('crl_v2', __name__)


@bp.route('/api/v2/crl', methods=['GET'])
@require_auth(['read:crl'])
def list_crls():
    """List CRLs - returns latest CRL per CA"""
    # Get latest CRL for each CA using subquery
    from sqlalchemy import func
    
    # Get the latest CRL for each CA
    subquery = db.session.query(
        CRLMetadata.ca_id,
        func.max(CRLMetadata.crl_number).label('max_crl_number')
    ).group_by(CRLMetadata.ca_id).subquery()
    
    crls = CRLMetadata.query.join(
        subquery,
        db.and_(
            CRLMetadata.ca_id == subquery.c.ca_id,
            CRLMetadata.crl_number == subquery.c.max_crl_number
        )
    ).all()
    
    # Add caref to each CRL for frontend compatibility
    result = []
    for crl in crls:
        data = crl.to_dict()
        if crl.ca:
            data['caref'] = crl.ca.refid
        result.append(data)
    
    return success_response(data=result)


@bp.route('/api/v2/crl/<int:ca_id>', methods=['GET'])
@require_auth(['read:crl'])
def get_crl(ca_id):
    """Get CRL for CA"""
    ca = CA.query.get(ca_id)
    if not ca:
        return error_response('CA not found', 404)
        
    crl = CRLMetadata.query.filter_by(ca_id=ca_id).order_by(CRLMetadata.crl_number.desc()).first()
    if not crl:
        return error_response('CRL not found', 404)
    
    data = crl.to_dict(include_crl_data=True)
    data['caref'] = ca.refid
    return success_response(data=data)


@bp.route('/api/v2/crl/<int:ca_id>/regenerate', methods=['POST'])
@require_auth(['write:crl'])
def regenerate_crl(ca_id):
    """Force CRL regeneration"""
    ca = CA.query.get(ca_id)
    if not ca:
        return error_response('CA not found', 404)
    
    # Check if CA has private key
    if not ca.has_private_key:
        return error_response(f'CA "{ca.descr}" does not have a private key - cannot sign CRL', 400)
        
    try:
        crl_metadata = CRLService.generate_crl(ca.id, username=getattr(g, 'user', {}).get('username', 'admin') if hasattr(g, 'user') else 'admin')
        
        data = crl_metadata.to_dict() if crl_metadata else None
        if data:
            data['caref'] = ca.refid
        
        return success_response(
            data=data,
            message='CRL regenerated successfully'
        )
    except Exception as e:
        return error_response(f"Failed to regenerate CRL: {str(e)}", 500)


@bp.route('/api/v2/ocsp/status', methods=['GET'])
@require_auth(['read:certificates'])
def get_ocsp_status():
    """Get OCSP service status"""
    # Check if OCSP is enabled in SystemConfig (placeholder)
    return success_response(data={
        'enabled': True,
        'running': True
    })


@bp.route('/api/v2/ocsp/stats', methods=['GET'])
@require_auth(['read:certificates'])
def get_ocsp_stats():
    """Get OCSP statistics"""
    # In a real implementation this would query logs or stats table
    # For now we don't have OCSP stats tracking in DB
    return success_response(data={
        'total_requests': 0,
        'cache_hits': 0
    })
