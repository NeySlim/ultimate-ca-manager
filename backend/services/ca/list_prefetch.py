"""What a CA listing needs per row, fetched once for the whole page.

Each CA row's `to_dict` and certificate count used to run their own queries, so
the cost of GET /api/v2/cas grew with the number of CAs. These helpers answer
the same questions with a fixed number of grouped queries.
"""
import re
from typing import Dict, Iterable, Optional

from models import db, CA, Certificate
from models.ca_cross_certificate import CACrossCertificate


def build(cas: Iterable[CA]) -> Dict[str, dict]:
    """Parent ids, certificate counts and cross-certificate facts of *cas*."""
    cas = list(cas)
    ids = [c.id for c in cas if c.id is not None]
    refids = [c.refid for c in cas if c.refid]
    carefs = {c.caref for c in cas if c.caref}

    parent_ids: Dict[str, Optional[int]] = {}
    for refid, pid in _in_chunks(
            lambda part: db.session.query(CA.refid, CA.id).filter(CA.refid.in_(part)).all(), carefs):
        parent_ids.setdefault(refid, pid)

    cert_counts: Dict[str, int] = {}
    for caref, total in _in_chunks(
            lambda part: db.session.query(Certificate.caref, db.func.count(Certificate.id))
            .filter(Certificate.caref.in_(part)).group_by(Certificate.caref).all(), refids):
        cert_counts[caref] = total

    cross_totals: Dict[int, int] = {}
    for ca_id, total in _in_chunks(
            lambda part: db.session.query(CACrossCertificate.ca_id, db.func.count(CACrossCertificate.id))
            .filter(CACrossCertificate.ca_id.in_(part)).group_by(CACrossCertificate.ca_id).all(), ids):
        cross_totals[ca_id] = total

    # served_for(): the first served row, by id, that is still servable
    cross_served = set()
    with_cross = [i for i, total in cross_totals.items() if total]
    for row in _in_chunks(
            lambda part: CACrossCertificate.query.filter(
                CACrossCertificate.ca_id.in_(part), CACrossCertificate.served.is_(True))
            .order_by(CACrossCertificate.id).all(), with_cross):
        if row.servable:
            cross_served.add(row.ca_id)

    return {'parent_ids': parent_ids, 'cert_counts': cert_counts,
            'cross_totals': cross_totals, 'cross_served': cross_served}


def issuer_counts() -> Dict[str, int]:
    """Number of certificates per stored issuer string, for the CN fallback."""
    return {issuer: total for issuer, total in db.session.query(
        Certificate.issuer, db.func.count(Certificate.id)).group_by(Certificate.issuer).all() if issuer}


def count_by_issuer_cn(counts: Dict[str, int], cn: str) -> int:
    """Certificates whose issuer holds `CN=<cn>` as a whole RDN, as the ILIKE patterns did.

    The patterns were `CN=cn,%`, `%,CN=cn,%` and `%,CN=cn`; `%` and `_` in the
    name kept their LIKE meaning, and the match ignores case.
    """
    body = ''.join('.*' if ch == '%' else '.' if ch == '_' else re.escape(ch) for ch in f'CN={cn}')
    pattern = re.compile(rf'{body},.*|.*,{body},.*|.*,{body}', re.IGNORECASE | re.DOTALL)
    return sum(total for issuer, total in counts.items() if pattern.fullmatch(issuer))


# Stays under the bound-parameter ceiling of every backend.
_CHUNK = 500


def _in_chunks(run, values):
    values = list(values)
    for start in range(0, len(values), _CHUNK):
        yield from run(values[start:start + _CHUNK])


