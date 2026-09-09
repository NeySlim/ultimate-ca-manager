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
from services.compliance_service import calculate_compliance_score
from utils.response import success_response
from utils.datetime_utils import utc_now
from . import bp


@bp.route('/api/v2/certificates/stats', methods=['GET'])
@require_auth(['read:certificates'])
def get_certificate_stats():
    """Get certificate statistics"""

    now = utc_now()
    expiry_threshold = now + timedelta(days=30)

    # Only count actual certificates (not pending CSRs)
    base_query = Certificate.query.filter(Certificate.crt.isnot(None))

    total = base_query.count()
    revoked = base_query.filter(Certificate.revoked == True).count()
    expired = base_query.filter(
        Certificate.valid_to <= now,
        Certificate.revoked == False
    ).count()
    expiring = base_query.filter(
        Certificate.valid_to <= expiry_threshold,
        Certificate.valid_to > now,
        Certificate.revoked == False
    ).count()
    # Same bucket as the list filter and the row status: not revoked, not
    # expiring, not expired. A certificate with no validity date counts as
    # valid, as its row does, instead of falling outside every bucket.
    valid = base_query.filter(
        Certificate.revoked == False,
        or_(
            Certificate.valid_to.is_(None),
            Certificate.valid_to > expiry_threshold,
        ),
    ).count()

    # Certificates whose issuing CA is gone: counted over the whole set, like
    # every other card, instead of over the page on screen (#345 review)
    known_refs = db.session.query(CA.refid).filter(CA.refid.isnot(None))
    orphan = base_query.filter(
        Certificate.caref.isnot(None),
        Certificate.caref.notin_(known_refs),
    ).count()

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

    total_count = Certificate.query.filter(Certificate.crt.isnot(None), Certificate.revoked == False).count()
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
        batch = Certificate.query.filter(Certificate.crt.isnot(None), Certificate.revoked == False).limit(BATCH_SIZE).offset(offset).all()
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
