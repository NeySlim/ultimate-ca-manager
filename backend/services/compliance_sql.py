"""The compliance score of ``compliance_service.calculate_compliance_score`` as one SQL
expression over stored columns (``key_algo``, ``key_bits``, ``sig_hash``, SANs, dates),
so an average and a grade distribution never parse a certificate.

Kept equal to the Python score by tests/test_dashboard_compliance_score.py; a signature
without a separate hash that is neither EdDSA nor post-quantum scores 25 here, 10 there.
"""
from datetime import timedelta

from sqlalchemy import and_, case, func, or_

from models import Certificate
from services.compliance_service import GRADE_THRESHOLDS, key_algo_sort_points

CA_CERT_TYPES = ('ca', 'root', 'intermediate')
SERVER_SHORT_DAYS = 398
SERVER_MODERATE_DAYS = 825


def _lifetime_over(dialect, days):
    """Whole days of lifetime, rounded down as timedelta.days, above *days*."""
    if dialect == 'sqlite':
        return func.julianday(Certificate.valid_to) - func.julianday(Certificate.valid_from) >= days + 1
    return Certificate.valid_to - Certificate.valid_from >= timedelta(days=days + 1)


def _ca_type():
    return func.lower(func.coalesce(Certificate.cert_type, '')).in_(CA_CERT_TYPES)


def key_points():
    """0-30: RSA by its modulus, a registered key by its spelling, another EC curve 15, the rest 10."""
    bits = func.coalesce(Certificate.key_bits, 0)
    rsa = case((bits >= 4096, 30), (bits >= 3072, 25), (bits >= 2048, 20), (bits >= 1024, 5), else_=0)
    named = [(Certificate.key_algo.ilike(spelling), points) for spelling, points in key_algo_sort_points()
             if not spelling.upper().startswith('RSA')]
    return case((Certificate.key_algo.ilike('RSA%'), rsa), *named,
                (Certificate.key_algo.ilike('EC %'), 15), else_=10)


def signature_points():
    """0-25 from the signature hash; no hash is EdDSA or a post-quantum scheme, which choose their own."""
    digest = func.lower(Certificate.sig_hash)
    return case((Certificate.sig_hash.is_(None), 25), (digest.like('sha512%'), 25), (digest == 'sha384', 25),
                (digest == 'sha256', 22), (digest.in_(('sha1', 'md5')), 0), else_=10)


def validity_points(now):
    """0-25: revoked or expired 0, at most 7 days left 5, at most 30 days 15; no expiry date is valid."""
    return case((Certificate.revoked.is_(True), 0), (Certificate.valid_to.is_(None), 25),
                (Certificate.valid_to <= now, 0), (Certificate.valid_to <= now + timedelta(days=7), 5),
                (Certificate.valid_to <= now + timedelta(days=30), 15), else_=25)


def _has_san():
    columns = (Certificate.san_dns, Certificate.san_ip, Certificate.san_email, Certificate.san_uri,
               Certificate.san_upn)
    return or_(*[and_(c.isnot(None), c != '', c != '[]') for c in columns])


def san_points():
    return case((_ca_type(), 10), (_has_san(), 10), else_=0)


def lifetime_points(dialect):
    """0-10: a CA is exempt; up to 398 days 10, up to 825 days 7, longer 3, a missing date 5."""
    return case((_ca_type(), 10),
                (or_(Certificate.valid_from.is_(None), Certificate.valid_to.is_(None)), 5),
                (_lifetime_over(dialect, SERVER_MODERATE_DAYS), 3),
                (_lifetime_over(dialect, SERVER_SHORT_DAYS), 7), else_=10)


def score_expression(dialect, now):
    """0-100, the sum of the five parts as calculate_compliance_score adds them."""
    return key_points() + signature_points() + validity_points(now) + san_points() + lifetime_points(dialect)


def grade_of(score):
    for threshold, grade in GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return GRADE_THRESHOLDS[-1][1]


def grade_counts(score_column):
    """One SUM per grade, best first, over a column holding the score."""
    bounds = [threshold for threshold, _ in GRADE_THRESHOLDS]
    sums = []
    for i, low in enumerate(bounds):
        high = bounds[i - 1] if i else None
        cond = score_column >= low if high is None else and_(score_column >= low, score_column < high)
        sums.append(func.coalesce(func.sum(case((cond, 1), else_=0)), 0))
    return [grade for _, grade in GRADE_THRESHOLDS], sums
