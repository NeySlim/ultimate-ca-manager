"""
OCSP Responder Routes
"""
from flask import Blueprint, request, Response, abort

ocsp_bp = Blueprint('ocsp', __name__)


@ocsp_bp.route('/ocsp', methods=['GET', 'POST'])
def ocsp_responder():
    """OCSP responder endpoint"""
    # Simple stub - full implementation would require ocsp_service
    # For now, return a basic response
    return Response(b'OCSP responder not fully configured', status=503)
