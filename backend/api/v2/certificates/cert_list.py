"""Certificates list route"""
import logging
from datetime import timedelta
from flask import request
from sqlalchemy import or_, and_, case, func
from auth.unified import require_auth
from utils.response import success_response
from models import Certificate, CA, db
from services.compliance_service import calculate_compliance_score
from utils.datetime_utils import utc_now
from . import bp

logger = logging.getLogger(__name__)


@bp.route('/api/v2/certificates', methods=['GET'])
@require_auth(['read:certificates'])
def list_certificates():
    """List certificates"""

    page = max(1, request.args.get('page', 1, type=int))
    per_page = min(max(1, request.args.get('per_page', 20, type=int)), 100)
    status_list = request.args.getlist('status')  # supports multi-select: ?status=valid&status=expired
    ca_id_list = request.args.getlist('ca_id', type=int)  # supports multi-select: ?ca_id=1&ca_id=2
    search = request.args.get('search', '').strip()
    sort_by = request.args.get('sort_by', 'subject')  # Default sort by subject (common_name)
    sort_order = request.args.get('sort_order', 'asc')  # Default ascending (A-Z)

    # Whitelist of allowed sort columns
    # Use COALESCE for subject_cn to fallback to descr if CN not populated
    _cn_sort = func.coalesce(Certificate.subject_cn, Certificate.descr)
    ALLOWED_SORT_COLUMNS = {
        'subject': _cn_sort,
        'subject_cn': _cn_sort,
        'issuer': Certificate.issuer,
        'valid_to': Certificate.valid_to,
        'valid_from': Certificate.valid_from,
        'created_at': Certificate.created_at,
        'serial_number': Certificate.serial_number,
        'revoked': Certificate.revoked,
        'descr': Certificate.descr,
        'key_algo': Certificate.key_algo,
        'status': 'special',  # Handled separately with CASE
        'compliance_grade': 'special_compliance'  # Handled separately
    }

    query = Certificate.query.filter(Certificate.crt.isnot(None))

    # Apply CA filter (Certificate stores caref=CA.refid, not ca_id)
    if ca_id_list:
        ca_refs = []
        for cid in ca_id_list:
            ca = CA.query.get(cid)
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
            if status == 'revoked':
                status_conditions.append(Certificate.revoked == True)
            elif status == 'valid':
                status_conditions.append(
                    and_(Certificate.revoked == False, Certificate.valid_to > utc_now())
                )
            elif status == 'expired':
                status_conditions.append(Certificate.valid_to <= utc_now())
            elif status == 'expiring':
                expiry_threshold = utc_now() + timedelta(days=30)
                status_conditions.append(
                    and_(
                        Certificate.valid_to <= expiry_threshold,
                        Certificate.valid_to > utc_now(),
                        Certificate.revoked == False
                    )
                )
        if status_conditions:
            query = query.filter(or_(*status_conditions))

    # Apply search filter (escape LIKE wildcards)
    if search:
        safe_search = search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        query = query.filter(
            or_(
                Certificate.subject.ilike(f'%{safe_search}%', escape='\\'),
                Certificate.issuer.ilike(f'%{safe_search}%', escape='\\'),
                Certificate.descr.ilike(f'%{safe_search}%', escape='\\'),
                Certificate.serial_number.ilike(f'%{safe_search}%', escape='\\')
            )
        )

    # Apply sorting BEFORE pagination (use whitelist)
    sort_column = ALLOWED_SORT_COLUMNS.get(sort_by, Certificate.subject)

    if sort_by == 'status':
        # Special handling: sort by computed status (revoked > expired > expiring > valid)
        # Then alphabetically by subject within each group
        now = utc_now()
        expiry_threshold = now + timedelta(days=30)

        # Status priority: 1=revoked, 2=expired, 3=expiring, 4=valid
        status_order = case(
            (Certificate.revoked == True, 1),
            (Certificate.valid_to <= now, 2),
            (Certificate.valid_to <= expiry_threshold, 3),
            else_=4
        )

        if sort_order == 'desc':
            query = query.order_by(status_order.desc(), Certificate.subject.asc())
        else:
            query = query.order_by(status_order.asc(), Certificate.subject.asc())
    elif sort_by == 'compliance_grade':
        # Approximate compliance score in SQL for sorting:
        # Key strength: RSA 4096/EC = best, RSA 2048 = good, RSA 1024 = bad
        # Validity: revoked/expired = worst, expiring = medium, valid = best
        # This gives a rough sort order consistent with the computed score
        now = utc_now()
        expiry_threshold = now + timedelta(days=30)

        compliance_order = (
            # Key strength component (0-30)
            case(
                (Certificate.key_algo.ilike('%4096%'), 30),
                (Certificate.key_algo.ilike('%EC%'), 30),
                (Certificate.key_algo.ilike('%P-256%'), 30),
                (Certificate.key_algo.ilike('%P-384%'), 30),
                (Certificate.key_algo.ilike('%Ed25519%'), 30),
                (Certificate.key_algo.ilike('%2048%'), 20),
                (Certificate.key_algo.ilike('%1024%'), 5),
                else_=15
            ) +
            # Validity component (0-25)
            case(
                (Certificate.revoked == True, 0),
                (Certificate.valid_to <= now, 0),
                (Certificate.valid_to <= expiry_threshold, 15),
                else_=25
            )
        )

        if sort_order == 'desc':
            query = query.order_by(compliance_order.desc(), _cn_sort.asc())
        else:
            query = query.order_by(compliance_order.asc(), _cn_sort.asc())
    elif sort_column not in ('special', 'special_compliance'):
        if sort_order == 'desc':
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

    # Paginate
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    certs = []
    for cert in pagination.items:
        d = cert.to_dict()
        compliance = calculate_compliance_score(d)
        d['compliance_score'] = compliance['score']
        d['compliance_grade'] = compliance['grade']
        certs.append(d)

    return success_response(
        data=certs,
        meta={'total': pagination.total, 'page': page, 'per_page': per_page}
    )
