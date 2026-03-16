"""
CRL & OCSP Routes v2.0
"""

from flask import Blueprint, request, g
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db, CA, AuditLog
from models.crl import CRLMetadata
from services.crl_service import CRLService
from services.audit_service import AuditService
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('crl_v2', __name__)


@bp.route('/api/v2/crl', methods=['GET'])
@require_auth(['read:crl'])
def list_crls():
    """List CRLs - returns latest base (full) CRL per CA"""
    from sqlalchemy import func
    
    # Get the latest base CRL for each CA (exclude delta CRLs)
    subquery = db.session.query(
        CRLMetadata.ca_id,
        func.max(CRLMetadata.crl_number).label('max_crl_number')
    ).filter(
        CRLMetadata.is_delta == False
    ).group_by(CRLMetadata.ca_id).subquery()
    
    crls = CRLMetadata.query.join(
        subquery,
        db.and_(
            CRLMetadata.ca_id == subquery.c.ca_id,
            CRLMetadata.crl_number == subquery.c.max_crl_number
        )
    ).all()
    
    # Batch-load delta CRLs to avoid N+1
    ca_ids = [crl.ca_id for crl in crls]
    delta_subq = db.session.query(
        CRLMetadata.ca_id,
        func.max(CRLMetadata.crl_number).label('max_num')
    ).filter(
        CRLMetadata.ca_id.in_(ca_ids),
        CRLMetadata.is_delta == True
    ).group_by(CRLMetadata.ca_id).subquery()
    
    deltas = CRLMetadata.query.join(delta_subq, db.and_(
        CRLMetadata.ca_id == delta_subq.c.ca_id,
        CRLMetadata.crl_number == delta_subq.c.max_num
    )).all() if ca_ids else []
    delta_map = {d.ca_id: d for d in deltas}
    
    result = []
    for crl in crls:
        data = crl.to_dict()
        if crl.ca:
            data['caref'] = crl.ca.refid
        if crl.ca_id in delta_map:
            data['delta_crl'] = delta_map[crl.ca_id].to_dict()
        result.append(data)
    
    return success_response(data=result)


@bp.route('/api/v2/crl/<int:ca_id>', methods=['GET'])
@require_auth(['read:crl'])
def get_crl(ca_id):
    """Get CRL for CA"""
    ca = CA.query.get(ca_id)
    if not ca:
        return error_response('CA not found', 404)
        
    crl = CRLMetadata.query.filter_by(ca_id=ca_id, is_delta=False).order_by(CRLMetadata.crl_number.desc()).first()
    if not crl:
        return success_response(data=None)
    
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
        
        AuditService.log_action(
            action='crl_regenerate',
            resource_type='crl',
            resource_id=str(ca_id),
            resource_name=ca.descr,
            details=f'Regenerated CRL for CA: {ca.descr}',
            success=True
        )
        
        data = crl_metadata.to_dict() if crl_metadata else None
        if data:
            data['caref'] = ca.refid
        
        try:
            from websocket.emitters import on_crl_regenerated
            on_crl_regenerated(ca_id, ca.descr, data.get('next_update', '') if data else '', data.get('entries_count', 0) if data else 0)
        except Exception:
            pass
        
        return success_response(
            data=data,
            message='CRL regenerated successfully'
        )
    except Exception as e:
        logger.error(f'Failed to regenerate CRL: {e}')
        return error_response("Failed to regenerate CRL", 500)


@bp.route('/api/v2/crl/<int:ca_id>/auto-regen', methods=['POST'])
@require_auth(['write:crl'])
def toggle_auto_regen(ca_id):
    """Enable/disable automatic CRL regeneration for a CA"""
    ca = CA.query.get(ca_id)
    if not ca:
        return error_response('CA not found', 404)
    
    data = request.get_json() or {}
    enabled = data.get('enabled', not ca.cdp_enabled)  # Toggle if not specified
    
    try:
        ca.cdp_enabled = enabled
        
        # Auto-generate CDP URL if enabling and no URL set
        if enabled and not ca.cdp_url:
            from flask import request as flask_request
            base_url = flask_request.host_url.rstrip('/')
            ca.cdp_url = f"{base_url}/cdp/{ca.id}.crl"
        
        # Audit log
        username = getattr(g, 'user', {}).get('username', 'admin') if hasattr(g, 'user') else 'admin'
        audit = AuditLog(
            action='crl_auto_regen_toggle',
            resource_type='ca',
            resource_id=str(ca.id),
            resource_name=ca.descr,
            username=username,
            details=f"{'Enabled' if enabled else 'Disabled'} automatic CRL regeneration",
            ip_address=request.remote_addr,
            success=True
        )
        db.session.add(audit)
        db.session.commit()
        
        return success_response(
            data={'cdp_enabled': ca.cdp_enabled},
            message=f"Automatic CRL regeneration {'enabled' if enabled else 'disabled'}"
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f'Failed to update CRL auto-regen setting: {e}')
        return error_response("Failed to update CRL settings", 500)


@bp.route('/api/v2/crl/<int:ca_id>/delta', methods=['GET'])
@require_auth(['read:crl'])
def get_delta_crl(ca_id):
    """Get latest delta CRL for a CA"""
    ca = CA.query.get(ca_id)
    if not ca:
        return error_response('CA not found', 404)
    
    delta = CRLService.get_latest_delta_crl(ca_id)
    if not delta:
        return success_response(data=None)
    
    data = delta.to_dict(include_crl_data=True)
    data['caref'] = ca.refid
    return success_response(data=data)


@bp.route('/api/v2/crl/<int:ca_id>/delta/regenerate', methods=['POST'])
@require_auth(['write:crl'])
def regenerate_delta_crl(ca_id):
    """Force delta CRL generation"""
    ca = CA.query.get(ca_id)
    if not ca:
        return error_response('CA not found', 404)
    if not ca.has_private_key:
        return error_response('CA does not have a private key', 400)
    if not ca.cdp_enabled:
        return error_response('CDP is not enabled for this CA', 400)
    if not ca.delta_crl_enabled:
        return error_response('Delta CRL is not enabled for this CA', 400)
    
    try:
        username = getattr(g, 'user', {}).get('username', 'admin') if hasattr(g, 'user') else 'admin'
        crl_metadata = CRLService.generate_delta_crl(ca.id, username=username)
        
        data = crl_metadata.to_dict() if crl_metadata else None
        if data:
            data['caref'] = ca.refid
        
        return success_response(data=data, message='Delta CRL generated successfully')
    except ValueError as e:
        logger.warning(f'Delta CRL generation rejected for CA {ca_id}: {e}')
        msg = str(e)
        if 'not found' in msg:
            return error_response('CA not found', 404)
        elif 'private key' in msg:
            return error_response('CA does not have a private key', 400)
        elif 'base CRL' in msg:
            return error_response('No base CRL exists — generate a full CRL first', 400)
        return error_response('Delta CRL generation failed', 400)
    except Exception as e:
        logger.error(f'Failed to generate delta CRL: {e}')
        return error_response("Failed to generate delta CRL", 500)


@bp.route('/api/v2/crl/<int:ca_id>/delta-config', methods=['POST'])
@require_auth(['write:crl'])
def configure_delta_crl(ca_id):
    """Configure delta CRL settings for a CA"""
    ca = CA.query.get(ca_id)
    if not ca:
        return error_response('CA not found', 404)
    
    data = request.get_json() or {}
    
    try:
        if 'enabled' in data:
            ca.delta_crl_enabled = bool(data['enabled'])
        if 'interval' in data:
            interval = int(data['interval'])
            if interval < 1 or interval > 168:  # 1h to 7 days
                return error_response('Interval must be between 1 and 168 hours', 400)
            ca.delta_crl_interval = interval
        
        username = getattr(g, 'user', {}).get('username', 'admin') if hasattr(g, 'user') else 'admin'
        AuditService.log_action(
            action='delta_crl_config',
            resource_type='ca',
            resource_id=str(ca.id),
            resource_name=ca.descr,
            details=f"Delta CRL config: enabled={ca.delta_crl_enabled}, interval={ca.delta_crl_interval}h",
            success=True
        )
        
        db.session.commit()
        
        return success_response(
            data={
                'delta_crl_enabled': ca.delta_crl_enabled,
                'delta_crl_interval': ca.delta_crl_interval
            },
            message='Delta CRL configuration updated'
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f'Failed to configure delta CRL: {e}')
        return error_response("Failed to update delta CRL settings", 500)


@bp.route('/api/v2/ocsp/status', methods=['GET'])
@require_auth(['read:certificates'])
def get_ocsp_status():
    """Get OCSP service status"""
    try:
        ocsp_cas = CA.query.filter_by(ocsp_enabled=True).count()
        enabled = ocsp_cas > 0
        return success_response(data={
            'enabled': enabled,
            'running': enabled,
            'ca_count': ocsp_cas
        })
    except Exception as e:
        logger.warning(f"OCSP status check failed: {e}")
        return success_response(data={
            'enabled': False,
            'running': False,
            'ca_count': 0
        })


@bp.route('/api/v2/ocsp/stats', methods=['GET'])
@require_auth(['read:certificates'])
def get_ocsp_stats():
    """Get OCSP statistics from cached responses"""
    from models.ocsp import OCSPResponse
    try:
        total = OCSPResponse.query.count()
        return success_response(data={
            'total_requests': total,
            'cache_hits': total,
        })
    except Exception as e:
        logger.error(f"OCSP stats query failed: {e}")
        return success_response(data={
            'total_requests': 0,
            'cache_hits': 0,
        })
