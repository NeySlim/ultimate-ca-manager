"""
Certificates EKU Routes
/api/v2/certificates/eku/* - Extended Key Usage endpoints
"""

from flask import request
from auth.unified import require_auth
from utils.response import success_response
from utils.eku_validation import EKU_NAMES
from . import bp


@bp.route('/api/v2/eku/known', methods=['GET'])
@require_auth(['read:certificates'])
def list_known_ekus():
    """Return the catalog of well-known Extended Key Usage OIDs.

    Used by the frontend to populate the EKU dropdown when issuing
    certificates or signing CSRs (RFC 5280 §4.2.1.12).
    """
    return success_response(data={
        'ekus': [
            {'oid': oid, 'name': name}
            for oid, name in EKU_NAMES.items()
        ]
    })
