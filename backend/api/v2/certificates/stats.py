"""
Certificates Stats Routes
/api/v2/certificates/stats - Certificate statistics endpoints
/api/v2/certificates/compliance - Compliance statistics endpoints
"""

from datetime import timedelta
from flask import request
from auth.unified import require_auth
from sqlalchemy import or_
from models import Certificate, CA, db
from utils.cert_status import (
    expired_condition, expiring_condition, issued_certificates,
    orphan_condition, revoked_condition, valid_condition,
)
from services.compliance_service import calculate_compliance_score
from utils.response import success_response
from utils.datetime_utils import utc_now
from . import bp


@bp.route('/api/v2/certificates/stats', methods=['GET'])
@require_auth(['read:certificates'])
def get_certificate_stats():
    """Get certificate statistics"""

    now = utc_now()

    # The cards are filters, so they partition: see utils/cert_status
    base_query = issued_certificates()

    total = base_query.count()
    revoked = base_query.filter(revoked_condition()).count()
    expired = base_query.filter(expired_condition(now)).count()
    expiring = base_query.filter(expiring_condition(now)).count()
    valid = base_query.filter(valid_condition(now)).count()

    # Counted over the whole set, like every other card, instead of over the
    # page on screen (#345 review)
    orphan = base_query.filter(orphan_condition()).count()

    # Distinct issuance sources actually present, so the list "source" filter
    # can offer exactly the values that exist (NULL is surfaced as 'manual').
    source_rows = base_query.with_entities(Certificate.source).distinct().all()
    sources = sorted({(row[0] or 'manual') for row in source_rows})

    return success_response(data={
        'total': total,
        'valid': valid,
        'expiring': expiring,
        'expired': expired,
        'revoked': revoked,
        'orphan': orphan,
        'sources': sources
    })


@bp.route('/api/v2/certificates/compliance', methods=['GET'])
@require_auth(['read:certificates'])
def get_compliance_stats():
    """Get aggregate compliance statistics for all certificates"""

    total_count = issued_certificates().filter(Certificate.revoked == False).count()
    if not total_count:
        return success_response(data={
            'average_score': 0,
            'distribution': {'A+': 0, 'A': 0, 'B': 0, 'C': 0, 'D': 0, 'F': 0},
            'total': 0,
        })

    grades = {'A+': 0, 'A': 0, 'B': 0, 'C': 0, 'D': 0, 'F': 0}
    total_score = 0
    count = 0

    # Batch processing to avoid loading all certs into memory
    BATCH_SIZE = 200
    offset = 0
    while True:
        batch = issued_certificates().filter(
            Certificate.revoked == False
        ).limit(BATCH_SIZE).offset(offset).all()
        if not batch:
            break
        for cert in batch:
            d = cert.to_dict()
            result = calculate_compliance_score(d)
            total_score += result['score']
            grade = result['grade']
            if grade in grades:
                grades[grade] += 1
            count += 1
        offset += BATCH_SIZE
        db.session.expire_all()  # Release memory between batches

    return success_response(data={
        'average_score': round(total_score / count) if count else 0,
        'distribution': grades,
        'total': count,
    })
