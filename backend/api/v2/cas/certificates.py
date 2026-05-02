"""
CAs Certificates Operations (list certificates for a CA)
"""

from . import bp
from flask import request

from auth.unified import require_auth
from utils.response import success_response, error_response
from utils.pagination import paginate
from services.ca_service import CAService
from models import Certificate, CA


@bp.route('/api/v2/cas/<int:ca_id>/certificates', methods=['GET'])
@require_auth(['read:certificates'])
def list_ca_certificates(ca_id):
    """List certificates for this CA"""
    ca = CAService.get_ca(ca_id)
    if not ca:
        return error_response('CA not found', 404)

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    # Filter by CA refid
    query = Certificate.query.filter_by(caref=ca.refid).order_by(Certificate.created_at.desc())

    result = paginate(query, page, per_page)

    # Convert items to dict
    return success_response(
        data=[cert.to_dict() for cert in result['items']],
        meta=result['meta']
    )
