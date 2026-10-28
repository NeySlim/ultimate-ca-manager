"""Findings and explicit repairs for CAs damaged before cross-certificates existed (#400)."""
import logging

from flask import g, request

from auth.unified import require_auth
from models import db
from services.ca import cross_repair
from services.ca.cross_certs import CrossCertError
from utils.response import error_response, success_response

from . import bp

logger = logging.getLogger(__name__)


def _username():
    return getattr(getattr(g, 'current_user', None), 'username', None) or 'system'


@bp.route('/api/v2/cas/cross-findings', methods=['GET'])
@require_auth(['read:cas'])
def cross_findings():
    return success_response(data={'findings': cross_repair.findings(), 'note': cross_repair.NOTE})


def _run(action, message, ca_id, *args):
    try:
        ca, row, warnings = action(ca_id, *args, _username())
    except CrossCertError as e:
        db.session.rollback()
        return error_response(e.message, e.status, details={'code': e.code})
    return success_response(data={**ca.to_dict(), 'cross_certificate': row.to_dict(), 'warnings': warnings},
                            message=f'{message}. {cross_repair.NOTE}')


@bp.route('/api/v2/cas/<int:ca_id>/convert-to-cross', methods=['POST'])
@require_auth(['write:cas'])
def convert_to_cross(ca_id):
    return _run(cross_repair.convert_to_cross, 'Duplicate converted into a cross-certificate', ca_id)


@bp.route('/api/v2/cas/<int:ca_id>/restore-primary', methods=['POST'])
@require_auth(['write:cas'])
def restore_primary(ca_id):
    """Body (JSON): ``{certificate: PEM}``, the self-signed certificate of this record's key."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error_response('JSON body must be an object', 400)
    return _run(cross_repair.restore_primary, 'Self-signed certificate restored', ca_id,
                data.get('certificate') or data.get('pem') or '')
