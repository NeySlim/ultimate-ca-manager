"""Expirations per UTC day ahead: the overview's horizon and calendar.

The population is the certificate list's ``valid`` and ``expiring`` statuses together (issued,
not revoked, not yet expired, archived included), cut into whole UTC days from today: the
list filtered on ``status`` and one day's ``expires_from``/``expires_to`` gives that day's rows.
"""
from datetime import datetime, timedelta

from sqlalchemy import and_, bindparam, case, false, func, or_, select

from models import CA, Certificate, SystemConfig
from services.dashboard_aggregates import CLIENT_RENEWED_SOURCES, _active_ca, _day
from utils.cert_status import holds_certificate
from utils.datetime_utils import utc_isoformat, utc_now

# Renewed without an operator: the enrolling client, Windows autoenrolment, UCM's ACME client
AUTOMATIC_SOURCES = CLIENT_RENEWED_SOURCES + ('acme_client',)
# The list statuses whose union is the population above
POPULATION_STATUSES = ['valid', 'expiring']


def _signers(session):
    """The dedicated TSA signer's refid and the delegated OCSP responders' certificate ids."""
    from services.tsa_service import configured_signer_refid
    responders = set()
    for value in session.execute(select(SystemConfig.value).where(
            SystemConfig.key.startswith('ocsp_responder_cert_', autoescape=True))).scalars():
        try:
            responders.add(int(value))
        except (TypeError, ValueError):
            continue
    return configured_signer_refid() or None, sorted(responders)


def _signer_condition(tsa_refid, responder_ids):
    parts = []
    if tsa_refid:
        parts.append(Certificate.refid == tsa_refid)
    if responder_ids:
        parts.append(Certificate.id.in_(bindparam(None, responder_ids, expanding=True, literal_execute=True)))
    return or_(*parts) if parts else false()


def expirations(session, days, now=None):
    """Per UTC day from today, ``days`` days: total, manual and automatic expirations, signers
    (TSA, OCSP responder) and active CAs expiring that day; today counts from now on."""
    now = now or utc_now()
    start = datetime.combine(now.date(), datetime.min.time())
    end = start + timedelta(days=days)
    dates = [(start.date() + timedelta(days=i)).isoformat() for i in range(days)]
    day = func.date(Certificate.valid_to)
    automatic = and_(Certificate.source.isnot(None), Certificate.source.in_(AUTOMATIC_SOURCES))
    count_if = lambda cond: func.coalesce(func.sum(case((cond, 1), else_=0)), 0)  # noqa: E731
    rows = session.execute(
        select(day, func.count(), count_if(automatic), count_if(_signer_condition(*_signers(session))))
        .where(holds_certificate(), Certificate.revoked.is_(False), Certificate.valid_to.isnot(None),
               Certificate.valid_to > now, Certificate.valid_to < end)
        .group_by(day)).all()
    per_day = {_day(d): (int(n), int(auto), int(signers)) for d, n, auto, signers in rows}
    ca_day = func.date(CA.valid_to)
    cas = {_day(d): int(n) for d, n in session.execute(
        select(ca_day, func.count()).where(_active_ca(now), CA.valid_to.isnot(None), CA.valid_to < end)
        .group_by(ca_day)).all()}
    periods = []
    for d in dates:
        total, auto, signers = per_day.get(d, (0, 0, 0))
        periods.append({'date': d, 'total': total, 'manual': total - auto, 'automatic': auto,
                        'signers': signers, 'cas': cas.get(d, 0), 'infrastructure': bool(signers or cas.get(d))})
    total = sum(p['total'] for p in periods)
    automatic_total = sum(p['automatic'] for p in periods)
    return {
        'days': days, 'from': dates[0], 'to': dates[-1], 'after': utc_isoformat(now),
        'total': total, 'manual': total - automatic_total, 'automatic': automatic_total,
        'cas': sum(p['cas'] for p in periods), 'signers': sum(p['signers'] for p in periods),
        'automatic_sources': list(AUTOMATIC_SOURCES),
        'filter_hint': {'status': POPULATION_STATUSES, 'expires_to': end.date().isoformat()},
        'periods': periods,
    }
