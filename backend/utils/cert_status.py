"""Certificate status buckets, defined once.

Two views coexist, on purpose:

- The certificates page **partitions**: valid, expiring, expired, revoked,
  no overlap. Every card is a filter, so a count and the list behind it have
  to agree exactly (``api/v2/certificates/stats.py`` and ``cert_list.py``).
- The Prometheus metrics report the **lifecycle state**, valid, expired or
  revoked, and publish "expiring within N days" as a window over the valid
  ones: a certificate about to expire is still valid, which is what an
  operator watches for. The dashboard partitions like the certificates
  page, its status chart linking each slice to the matching filter.

What both share is the set they count: rows that actually hold a
certificate. A row holding only a signing request is a pending request,
reported on its own, and counting it as a certificate double-counts it
against the pending figure shown next to it.
"""
from datetime import timedelta

from sqlalchemy import and_, or_

from models import Certificate
from utils.datetime_utils import utc_now

EXPIRY_WINDOW_DAYS = 30


def holds_certificate(model=None):
    """Condition for "this row holds a certificate".

    Absent and empty both mean "none": a pending request is stored with no
    certificate, and some paths write the empty string for the same state
    (the CA table uses it as its sentinel). Testing only for absent left the
    empty ones counted as certificates in one view and as pending requests
    in the next.
    """
    model = model or Certificate
    return and_(model.crt.isnot(None), model.crt != '')


def awaits_certificate(model=None):
    """Complement of holds_certificate: no certificate yet."""
    model = model or Certificate
    return or_(model.crt.is_(None), model.crt == '')


def holds_request(model=None):
    """Condition for "this row holds a signing request".

    Same reading as holds_certificate: absent and empty both mean none. A
    row with an empty request was listed as a pending request while the
    dashboard, which already excluded it, counted something else.
    """
    model = model or Certificate
    return and_(model.csr.isnot(None), model.csr != '')


def pending_requests(query=None):
    """Rows holding a request and still waiting for their certificate.

    The exact complement of :func:`issued_certificates` among the rows that
    carry a request, so the two lists partition the records.
    """
    query = query if query is not None else Certificate.query
    return query.filter(holds_request(), awaits_certificate())


def signed_requests(query=None):
    """Rows whose request has received its certificate."""
    query = query if query is not None else Certificate.query
    return query.filter(holds_request(), holds_certificate())


def issued_certificates(query=None, include_archived: bool = True):
    """Rows that hold a certificate, excluding CSR-only records."""
    query = query if query is not None else Certificate.query
    query = query.filter(holds_certificate())
    if not include_archived:
        query = query.filter(Certificate.archived == False)  # noqa: E712
    return query


def revoked_condition():
    return Certificate.revoked == True  # noqa: E712


def expired_condition(now=None):
    """Past its expiry and not revoked; revoked wins over expired."""
    now = now or utc_now()
    return and_(
        Certificate.revoked == False,  # noqa: E712
        Certificate.valid_to.isnot(None),
        Certificate.valid_to <= now,
    )


def expiring_condition(now=None, days: int = EXPIRY_WINDOW_DAYS):
    """Inside the window and not yet expired."""
    now = now or utc_now()
    return and_(
        Certificate.revoked == False,  # noqa: E712
        Certificate.valid_to.isnot(None),
        Certificate.valid_to > now,
        Certificate.valid_to <= now + timedelta(days=days),
    )


def valid_condition(now=None, days: int = EXPIRY_WINDOW_DAYS, exclude_expiring: bool = True):
    """Usable today.

    With ``exclude_expiring`` the four buckets partition, as the certificates
    page needs; without it the answer is the lifecycle state, where a
    certificate inside the expiry window is still valid.

    A certificate with no expiry date reads as valid on its row, so it counts
    as valid here too rather than falling outside every bucket.
    """
    now = now or utc_now()
    floor = now + timedelta(days=days) if exclude_expiring else now
    return and_(
        Certificate.revoked == False,  # noqa: E712
        or_(Certificate.valid_to.is_(None), Certificate.valid_to > floor),
    )


def orphan_condition():
    """Issued by a CA this instance no longer holds.

    A missing link is not the same as no link: a certificate that never had
    one (imported, or issued by an external CA) is not an orphan.
    """
    from models import CA, db
    known_refs = db.session.query(CA.refid).filter(CA.refid.isnot(None))
    return and_(
        Certificate.caref.isnot(None),
        Certificate.caref.notin_(known_refs),
    )
