"""
CDP Routes - CRL Distribution Points (Public Endpoints)
RFC 5280 compliant HTTP-based CRL distribution
These endpoints are PUBLIC and do not require authentication
"""
from flask import Blueprint, send_file, jsonify, abort, render_template
from io import BytesIO

from models import CA
from services.crl_service import CRLService

cdp_bp = Blueprint('cdp', __name__)


@cdp_bp.route('/<ca_refid>/crl.pem', methods=['GET'])
def get_crl_pem(ca_refid):
    """
    Public endpoint to download CRL in PEM format
    
    URL: /cdp/{ca_refid}/crl.pem
    
    This is referenced in certificates' CRL Distribution Points extension
    """
    try:
        # Get CA by refid
        ca = CA.query.filter_by(refid=ca_refid).first()
        if not ca:
            abort(404, description='CA not found')
        
        # Get latest CRL
        crl_pem = CRLService.get_crl_pem(ca_refid)
        if not crl_pem:
            abort(404, description='No CRL available for this CA')
        
        # Send PEM format
        return send_file(
            BytesIO(crl_pem.encode('utf-8')),
            mimetype='application/x-pem-file',
            as_attachment=False,  # Display in browser if possible
            download_name=f'{ca_refid}.pem'
        )
        
    except Exception as e:
        abort(500, description=str(e))


@cdp_bp.route('/<ca_refid>/crl.der', methods=['GET'])
def get_crl_der(ca_refid):
    """
    Public endpoint to download CRL in DER format
    
    URL: /cdp/{ca_refid}/crl.der
    """
    try:
        # Get CA by refid
        ca = CA.query.filter_by(refid=ca_refid).first()
        if not ca:
            abort(404, description='CA not found')
        
        # Get latest CRL
        crl_der = CRLService.get_crl_der(ca_refid)
        if not crl_der:
            abort(404, description='No CRL available for this CA')
        
        # Send DER format
        return send_file(
            BytesIO(crl_der),
            mimetype='application/pkix-crl',
            as_attachment=False,  # Display in browser if possible
            download_name=f'{ca_refid}.crl'
        )
        
    except Exception as e:
        abort(500, description=str(e))


@cdp_bp.route('/<ca_refid>/crl.crl', methods=['GET'])
def get_crl_crl(ca_refid):
    """
    Public endpoint to download CRL in DER format with .crl extension
    
    URL: /cdp/{ca_refid}/crl.crl
    
    This is an alias for crl.der - some systems prefer .crl extension
    """
    # Redirect to DER endpoint
    return get_crl_der(ca_refid)


@cdp_bp.route('/<ca_refid>/info', methods=['GET'])
def get_crl_info(ca_refid):
    """
    Public endpoint to get CRL information (HTML page)
    
    URL: /cdp/{ca_refid}/info
    
    Useful for debugging and monitoring
    """
    try:
        # Get CA by refid
        ca = CA.query.filter_by(refid=ca_refid).first()
        if not ca:
            abort(404, description='CA not found')
        
        # Get latest CRL
        latest_crl = CRLService.get_latest_crl_by_refid(ca_refid)
        
        if not latest_crl:
            crl_info = {
                'ca_refid': ca_refid,
                'ca_name': ca.descr,
                'ca_common_name': ca.common_name,
                'has_crl': False,
                'message': 'No CRL generated yet for this CA'
            }
        else:
            crl_info = {
                'ca_refid': ca_refid,
                'ca_name': ca.descr,
                'ca_common_name': ca.common_name,
                'has_crl': True,
                'crl_number': latest_crl.crl_number,
                'this_update': latest_crl.this_update.isoformat() if latest_crl.this_update else None,
                'next_update': latest_crl.next_update.isoformat() if latest_crl.next_update else None,
                'revoked_count': latest_crl.revoked_count,
                'is_stale': latest_crl.is_stale,
                'days_until_expiry': latest_crl.days_until_expiry,
                'download_urls': {
                    'pem': f'/cdp/{ca_refid}/crl.pem',
                    'der': f'/cdp/{ca_refid}/crl.der',
                    'crl': f'/cdp/{ca_refid}/crl.crl'
                }
            }
        
        return render_template('crl/info.html', crl_info=crl_info)
        
    except Exception as e:
        abort(500, description=str(e))
