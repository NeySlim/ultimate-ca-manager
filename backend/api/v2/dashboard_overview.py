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
    """Items to act on, ``{kind, tier, id, label, due_at, href_hint}``, critical first then
    by ``due_at``, at most ``limit``; ``counts`` holds the full total per kind. A repeated
    ``kind`` restricts the items to those kinds (an unknown one is refused with 400).

    critical: ``acme_order_failed`` (last 7 days), ``acme_client_renewal_failed``,
    ``approval_pending`` expiring within 24 h, ``crl_due`` stale and ``crl_missing``,
    ``manual_renewal_due`` within 24 h, ``auto_renewal_blocked`` (the CA cannot sign),
    ``ca_expiring`` within 90 days. warning: other pending approvals, SCEP and key
    recovery requests, ``crl_due`` within min(24 h, half the CRL validity),
    ``manual_renewal_due`` within 30 days, ``client_renewal_overdue`` (protocol
    certificate without a stored key, 7 days out), ``renewal_declined``, ``ca_expiring``
    within a year. ``manual_renewal_due`` leaves out what auto-renewal, the enrolling
    client, UCM's ACME client or the OCSP responder task renews, and what a later
    identical certificate supersedes.
    """
    limit = parse_request_limit(DASHBOARD_MAX_ROWS, DASHBOARD_MAX_ROWS)
    kinds = request.args.getlist('kind') or None
    unknown = sorted(set(kinds or ()) - set(dashboard_aggregates.QUEUE_KINDS))
    if unknown:
        return error_response(f"unknown kind: {', '.join(unknown)}", 400)
    return success_response(data=dashboard_aggregates.work_queue(db.session, limit, kinds=kinds))


@bp.route('/api/v2/dashboard/health', methods=['GET'])
@require_auth(['read:dashboard'])
def get_health():
    """Per protocol, ``days`` (1-30) UTC days of ``{date, ok, failed}`` and the ``basis``
    measured: ACME audit entries, SCEP requests, EST issued certificates and failed
    audit entries; the scheduler reports its tasks by last status, without a series."""
    days = _days(HEALTH_MAX_DAYS)
    if days is None:
        return _days_error(HEALTH_MAX_DAYS)
    return success_response(data=dashboard_aggregates.protocol_health(db.session, days))


@bp.route('/api/v2/dashboard/compliance', methods=['GET'])
@require_auth(['read:dashboard'])
def get_compliance():
    """Counters over the live issued certificates (not revoked, archived or expired),
    read from columns. ``filter_hint`` is a certificate list query that reproduces the
    counter, given only when ``filter_available`` is true."""
    return success_response(data=dashboard_aggregates.compliance_summary(db.session))


@bp.route('/api/v2/dashboard/issuance', methods=['GET'])
@require_auth(['read:dashboard'])
def get_issuance():
    """Per CA and per UTC day over ``days`` (1-90): ``issued`` by ``created_at`` and
    ``renewed`` in place by ``renewed_at`` (the last renewal of each certificate, counted
    once however often it was renewed); ``by_source`` and ``total`` count issuances."""
    days = _days(ISSUANCE_MAX_DAYS)
    if days is None:
        return _days_error(ISSUANCE_MAX_DAYS)
    return success_response(data=dashboard_aggregates.issuance(db.session, days))
