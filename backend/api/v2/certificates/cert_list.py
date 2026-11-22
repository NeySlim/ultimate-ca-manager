"""Certificates list route"""
import logging
from datetime import timedelta
from flask import request
from sqlalchemy import or_, and_, case, func
from sqlalchemy.orm import selectinload
from auth.unified import require_auth
from utils.response import success_response
from utils.serial_format import serial_search_forms
from utils.pagination import parse_request_pagination, parse_request_sort
from models import Certificate, CA, db
from models.windows_profile import profile_names_of
from utils.cert_status import (
    CERTIFICATE_STATUS_FILTERS, expired_condition, expiring_condition,
    issued_certificates, normalize_status_filters, orphan_condition,
    revoked_condition, unknown_status_message, valid_condition,
)
from utils.response import error_response
from services.compliance_service import calculate_compliance_score, key_algo_sort_levels, key_algo_sort_points
from utils.datetime_utils import utc_now
from services.dashboard_aggregates import certificate_list_conditions
from . import bp

logger = logging.getLogger(__name__)


def key_strength_order(column):
    """SQL key strength points (0-30) of a ``key_algo`` *column*, the scale of
    compliance_service._score_key_strength; another EC curve 15, the rest 10."""
    return case(*[(column.ilike(spelling), points) for spelling, points in key_algo_sort_points()],
                (column.ilike('EC %'), 15), else_=10)


def key_level_order(column):
    """SQL NIST category of a post-quantum ``key_algo`` *column*, 0 for a classical key."""
    return case(*[(column.ilike(spelling), level) for spelling, level in key_algo_sort_levels()], else_=0)


def _status_order(descending):
    """Revoked, expired, expiring, valid (reversed for desc), then subject and id ascending."""
    now = utc_now()
    rank = case(
        (Certificate.revoked == True, 1),  # noqa: E712
        (Certificate.valid_to <= now, 2),
        (Certificate.valid_to <= now + timedelta(days=30), 3),
        else_=4)
    return [rank.desc() if descending else rank.asc(), Certificate.subject.asc(), Certificate.id.asc()]


def _compliance_order(descending):
    """SQL approximation of the compliance score (key strength 0-30 plus validity 0-25),
    then the post-quantum level, then the name and id ascending."""
    now = utc_now()
    score = key_strength_order(Certificate.key_algo) + case(
        (Certificate.revoked == True, 0),  # noqa: E712
        (Certificate.valid_to <= now, 0),
        (Certificate.valid_to <= now + timedelta(days=30), 15),
        else_=25)
    level = key_level_order(Certificate.key_algo)
    name = func.coalesce(Certificate.subject_cn, Certificate.descr)
    if descending:
        return [score.desc(), level.desc(), name.asc(), Certificate.id.asc()]
    return [score.asc(), level.asc(), name.asc(), Certificate.id.asc()]


def _sort_columns():
    """The keys the list sorts on; a generated request may hold no subject_cn, hence the descr."""
    name = func.coalesce(Certificate.subject_cn, Certificate.descr)
    return {
        'subject': name,
        'subject_cn': name,
        'issuer': Certificate.issuer,
        'valid_to': Certificate.valid_to,
        'valid_from': Certificate.valid_from,
        'created_at': Certificate.created_at,
        'serial_number': Certificate.serial_number,
        'revoked': Certificate.revoked,
        'descr': Certificate.descr,
        'key_algo': Certificate.key_algo,
        # A legacy row without a source is a manual one, as the source filter reads it
        'source': func.coalesce(Certificate.source, 'manual'),
        'status': _status_order,
        'compliance_grade': _compliance_order,
    }


@bp.route('/api/v2/certificates', methods=['GET'])
@require_auth(['read:certificates'])
def list_certificates():
    """List certificates"""

    page, per_page = parse_request_pagination(default_per_page=20)
    # supports multi-select: ?status=valid&status=expired
    status_list, unknown_status = normalize_status_filters(
        request.args.getlist('status'), CERTIFICATE_STATUS_FILTERS)
    if unknown_status:
        return error_response(
            unknown_status_message(unknown_status, CERTIFICATE_STATUS_FILTERS),
            400)
    ca_id_list = request.args.getlist('ca_id', type=int)  # supports multi-select: ?ca_id=1&ca_id=2
    source_list = request.args.getlist('source')  # supports multi-select: ?source=msca&source=acme
    search = request.args.get('search', '').strip()
    template_modified = request.args.get('template_modified', '').lower() in ('1', 'true', 'yes')
    # Read before the query: an unknown key or direction is a 400 (InvalidSort)
    sort = parse_request_sort(_sort_columns(), ('subject', 'asc'), tiebreak=Certificate.id)

    # The same set the counters above the list are computed from
    query = issued_certificates()

    # Eager-load the linked template: to_dict() resolves template_name, and
    # without this the list page would run one extra query per templated cert.
    query = query.options(selectinload(Certificate.template))

    # Apply CA filter (Certificate stores caref=CA.refid, not ca_id)
    if ca_id_list:
        ca_refs = []
        for cid in ca_id_list:
            ca = db.session.get(CA, cid)
            if ca:
                ca_refs.append(ca.refid)
        if ca_refs:
            query = query.filter(Certificate.caref.in_(ca_refs))
        else:
            query = query.filter(Certificate.id < 0)  # No results for invalid CAs

    # Apply status filter (supports multi-select)
    if status_list:
        status_conditions = []
        for status in status_list:
            # The buckets partition, so a filter and the card above it
            # always agree: see utils/cert_status
            if status == 'revoked':
                status_conditions.append(revoked_condition())
            elif status == 'valid':
                status_conditions.append(valid_condition())
            elif status == 'expired':
                status_conditions.append(expired_condition())
            elif status == 'orphan':
                # Selected over the whole set rather than on the page just
                # received, which showed nothing whenever the orphans sat
                # further down (#345 review)
                status_conditions.append(orphan_condition())
            elif status == 'expiring':
                status_conditions.append(expiring_condition())
            elif status == 'archived':
                # Superseded by a protocol re-enrolment, kept for history
                status_conditions.append(Certificate.archived == True)  # noqa: E712
        if status_conditions:
            query = query.filter(or_(*status_conditions))

    # Filtered here, not on the page received, so pagination and total agree
    if request.args.get('has_private_key', '').lower() in ('1', 'true', 'yes'):
        query = query.filter(Certificate.prv.isnot(None), Certificate.prv != '')

    # Compliance and renewal filters share their SQL with the dashboard counters
    try:
        query = query.filter(*certificate_list_conditions(request.args, db.session.get_bind().dialect.name))
    except ValueError as exc:
        return error_response(str(exc), 400)

    # Certificates issued from a template but diverging from its defaults (#258)
    if template_modified:
        query = query.filter(Certificate.template_overrides.isnot(None))

    # Apply source filter (supports multi-select). Legacy rows may have NULL
    # source; treat those as 'manual' so the manual filter still finds them.
    if source_list:
        source_conditions = []
        non_manual = [s for s in source_list if s != 'manual']
        if non_manual:
            source_conditions.append(Certificate.source.in_(non_manual))
        if 'manual' in source_list:
            source_conditions.append(
                or_(Certificate.source == 'manual', Certificate.source.is_(None))
            )
        query = query.filter(or_(*source_conditions))

    # Apply search filter (escape LIKE wildcards)
    if search:
        safe_search = search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        query = query.filter(
            or_(
                Certificate.subject.ilike(f'%{safe_search}%', escape='\\'),
                Certificate.issuer.ilike(f'%{safe_search}%', escape='\\'),
                Certificate.descr.ilike(f'%{safe_search}%', escape='\\'),
                Certificate.serial_number.ilike(f'%{safe_search}%', escape='\\'),
                # A whole serial typed in hex or colon hex, as the UI shows it
                Certificate.serial_number.in_(serial_search_forms(search)),
            )
        )

    query = query.order_by(*sort.clauses)

    # Paginate
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    # The records of the page in one query: a revocation they make shows as OCSP answers it
    from services.cert.issued_lookup import persisted_revocations_of, show_effective_revocation
    recorded = persisted_revocations_of(pagination.items)
    profile_names = profile_names_of(pagination.items)
    certs = []
    for cert in pagination.items:
        d = show_effective_revocation(cert.to_dict(windows_profile_names=profile_names), cert, recorded.get(cert.id))
        compliance = calculate_compliance_score(d)
        d['compliance_score'] = compliance['score']
        d['compliance_grade'] = compliance['grade']
        certs.append(d)

    return success_response(
        data=certs,
        meta={'total': pagination.total, 'page': page, 'per_page': per_page}
    )
