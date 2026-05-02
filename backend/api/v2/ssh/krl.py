"""
SSH CA KRL (Key Revocation List) endpoint.
"""

import re

from flask import Response

from auth.unified import require_auth
from utils.response import error_response
from services.ssh_krl_service import SSHKRLService
from models.ssh import SSHCertificateAuthority

from .helpers import bp, logger


@bp.route('/api/v2/ssh/cas/<int:ca_id>/krl', methods=['GET'])
@require_auth(['read:ssh'])
def get_ssh_ca_krl(ca_id):
    """Download the KRL (Key Revocation List) for this CA."""
    try:
        krl_data = SSHKRLService.generate_krl(ca_id)
        ca = SSHCertificateAuthority.query.get(ca_id)
        ca_name = ca.descr if ca else 'unknown'

        return Response(
            krl_data,
            mimetype='application/octet-stream',
            headers={
                'Content-Disposition': f'attachment; filename="ssh_ca_{re.sub(r"[^a-zA-Z0-9_.-]", "_", ca_name)}_krl"'
            }
        )
    except ValueError as e:
        return error_response(str(e), 404)
    except RuntimeError as e:
        logger.error(f"Failed to generate KRL for CA {ca_id}: {e}")
        return error_response('Failed to generate KRL', 500)
    except Exception as e:
        logger.error(f"Failed to generate KRL: {e}")
        return error_response('Failed to generate KRL', 500)
