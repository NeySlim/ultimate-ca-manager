"""Overview routes: work queue, protocol health, compliance and issuance.

Parameter parsing and the response only; the figures come from
``services/dashboard_aggregates.py``.
"""
from flask import Blueprint, request

from api.v2.dashboard import DASHBOARD_MAX_ROWS
from auth.unified import require_auth
from models import db
from services import dashboard_aggregates
from utils.pagination import parse_request_limit
from utils.response import error_response, success_response

bp = Blueprint('dashboard_overview_v2', __name__)

HEALTH_MAX_DAYS = 30
ISSUANCE_MAX_DAYS = 90


def _days(maximum):
    """``?days=`` as an int in [1, maximum], or None when it is anything else."""
    raw = request.args.get('days', '7')
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return None
    return days if 1 <= days <= maximum else None


def _days_error(maximum):
    return error_response(f'days must be an integer between 1 and {maximum}', 400)


@bp.route('/api/v2/dashboard/queue', methods=['GET'])
@require_auth(['read:dashboard'])
def get_queue():
    limit = parse_request_limit(DASHBOARD_MAX_ROWS, DASHBOARD_MAX_ROWS)
    return success_response(data=dashboard_aggregates.work_queue(db.session, limit))


@bp.route('/api/v2/dashboard/health', methods=['GET'])
@require_auth(['read:dashboard'])
def get_health():
    days = _days(HEALTH_MAX_DAYS)
    if days is None:
        return _days_error(HEALTH_MAX_DAYS)
    return success_response(data=dashboard_aggregates.protocol_health(db.session, days))


@bp.route('/api/v2/dashboard/compliance', methods=['GET'])
@require_auth(['read:dashboard'])
def get_compliance():
    return success_response(data=dashboard_aggregates.compliance_summary(db.session))


@bp.route('/api/v2/dashboard/issuance', methods=['GET'])
@require_auth(['read:dashboard'])
def get_issuance():
    days = _days(ISSUANCE_MAX_DAYS)
    if days is None:
        return _days_error(ISSUANCE_MAX_DAYS)
    return success_response(data=dashboard_aggregates.issuance(db.session, days))
