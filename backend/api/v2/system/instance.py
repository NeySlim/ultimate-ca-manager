"""Instance state for a fleet console (#403): schema in docs/API_REFERENCE.md."""
import logging

from . import bp
from auth.unified import require_auth
from services.instance_state import instance_state
from utils.response import success_response, error_response

logger = logging.getLogger(__name__)


@bp.route('/api/v2/system/instance', methods=['GET'])
@require_auth(['read:instance'])
def get_instance_state():
    """Version, mode, database engine, health, CAs, update, backup and FIPS of this instance."""
    try:
        response, status = success_response(data=instance_state())
    except Exception as exc:
        from models import db
        db.session.rollback()
        logger.error("Instance state failed: %s", type(exc).__name__)
        return error_response('Failed to read the instance state', 500)
    response.headers['Cache-Control'] = 'no-store'
    return response, status
