"""Overview aggregates: work queue, protocol health, compliance, issuance.

Each figure is a COUNT or GROUP BY run by the database, bounded in rows and in
statements whatever the table sizes. Nothing here loads ``crt`` or ``prv``:
key size and signature hash are the ``key_bits`` / ``sig_hash`` columns, set
whenever a certificate is stored (``models/certificate.py``).
"""
from datetime import datetime, timedelta

from sqlalchemy.orm import aliased
from sqlalchemy import (DateTime, String, and_, case, cast, false, func, literal, literal_column,
                        or_, select, true, type_coerce, union_all)

from models import CA, Certificate, SystemConfig
from models.acme_models import AcmeClientOrder, AcmeOrder
from models.audit_log import AuditLog
from models.certificate_template import CertificateTemplate
from models.crl import CRLMetadata
from models.key_recovery import KeyRecoveryRequest, STATUS_PENDING
from models.policy import ApprovalRequest
from models.scep import SCEPRequest
from services.ocsp_responder_renewal import renewed_by_responder_task
from utils.cert_status import EXPIRY_WINDOW_DAYS, holds_certificate, orphan_condition
from utils.datetime_utils import utc_isoformat, utc_now

QUEUE_KINDS = ('acme_order_failed', 'acme_client_renewal_failed', 'approval_pending',
               'scep_request_pending', 'key_recovery_pending', 'crl_due', 'crl_missing',
               'manual_renewal_due', 'client_renewal_overdue', 'auto_renewal_blocked',
               'renewal_declined', 'ca_expiring')
ACME_FAILURE_LOOKBACK_DAYS = 7
CRITICAL_WITHIN = timedelta(hours=24)
DEFAULT_CRL_VALIDITY_DAYS = 7
CA_EXPIRY_WARNING_DAYS = 365
CA_EXPIRY_CRITICAL_DAYS = 90
# Python's compliance grade calls a lifetime long from 399 whole days on
SERVER_LIFETIME_MAX_DAYS = 398
RSA_MIN_BITS = 3072
WEAK_SIG_HASHES = ('sha1', 'md5')
# Enrolment protocols whose client holds the key and renews on its own (not msca: UCM submits those to AD CS)
CLIENT_RENEWED_SOURCES = ('acme', 'letsencrypt', 'scep', 'est', 'wstep')
# Such a client still not renewed this close to expiry is overdue
CLIENT_RENEWAL_OVERDUE_DAYS = 7

_HREF = {
    'acme_order_failed': '/acme?tab=orders&order={id}',
    'acme_client_renewal_failed': '/acme?tab=client&order={id}',
    'approval_pending': '/approvals?request={id}',
    'scep_request_pending': '/scep-config?tab=requests&request={id}',
    'key_recovery_pending': '/key-recovery?request={id}',
    'crl_due': '/crl-ocsp?ca={id}',
    'crl_missing': '/crl-ocsp?ca={id}',
    'manual_renewal_due': '/certificates/{id}',
    'client_renewal_overdue': '/certificates/{id}',
    'auto_renewal_blocked': '/certificates/{id}',
    'renewal_declined': '/certificates/{id}',
    'ca_expiring': '/cas/{id}',
}


_CRITICAL, _WARNING = literal_column('0'), literal_column('1')


def _const(kind):
    """A kind name inlined as SQL text (from QUEUE_KINDS only): PostgreSQL types it as text."""
    if kind not in QUEUE_KINDS:
        raise ValueError(kind)
    return literal_column(f"'{kind}'", String)


def _not_archived(model=Certificate):
    return or_(model.archived.is_(False), model.archived.is_(None))


def _active_ca(now):
    """A CA that holds its certificate, is not revoked and has not expired."""
    return and_(CA.crt.isnot(None), CA.crt != '', or_(CA.revoked.is_(False), CA.revoked.is_(None)),
                or_(CA.valid_to.is_(None), CA.valid_to > now))


def _day(value) -> str:
    """DATE() comes back as a string on SQLite and as a date on PostgreSQL."""
    return value.isoformat() if hasattr(value, 'isoformat') else str(value)


def _window(days, now):
    start = datetime.combine(now.date() - timedelta(days=days - 1), datetime.min.time())
    return start, [(start.date() + timedelta(days=i)).isoformat() for i in range(days)]


def _renewal_config():
    from services.auto_renewal_service import AutoRenewalService
    return AutoRenewalService.get_renewal_config()


# ------------------------------------------------------------------ queue

def _within_half_validity(next_update, now, dialect):
    """``next_update`` comes before now + half the CA's CRL validity (7 days when unset or 0, as the CA reports it)."""
    days = func.coalesce(func.nullif(CA.crl_validity_days, 0), DEFAULT_CRL_VALIDITY_DAYS)
    if dialect == 'sqlite':
        return (func.julianday(next_update) - func.julianday(literal(now, DateTime))) * 2 < days
    return next_update < literal(now, DateTime) + func.make_interval(0, 0, 0, 0, days * 12)


def _queue_union(now, dialect):
    """One SELECT per kind, all shaped (kind, rank, id, label, due_at); rank 0 is critical."""
    soon = now + CRITICAL_WITHIN
    config = _renewal_config()  # read once: four kinds depend on it
    # type_coerce, not CAST: SQLite would turn CAST(... AS DATETIME) into a number
    text_label = lambda col: type_coerce(col, String)  # noqa: E731
    due = lambda col: type_coerce(col, DateTime)  # noqa: E731
    parts = []

    parts.append(select(
        _const('acme_order_failed').label('kind'), _CRITICAL.label('rank'),
        AcmeOrder.id.label('id'), text_label(AcmeOrder.identifiers).label('label'),
        due(AcmeOrder.created_at).label('due_at'),
    ).where(AcmeOrder.status == 'invalid',
            AcmeOrder.created_at >= now - timedelta(days=ACME_FAILURE_LOOKBACK_DAYS)))

    parts.append(select(
        _const('acme_client_renewal_failed').label('kind'), _CRITICAL.label('rank'),
        AcmeClientOrder.id.label('id'), text_label(AcmeClientOrder.domains).label('label'),
        due(func.coalesce(AcmeClientOrder.last_error_at, AcmeClientOrder.created_at)).label('due_at'),
    ).where(AcmeClientOrder.renewal_failures > 0))

    approval_due = func.coalesce(ApprovalRequest.expires_at, ApprovalRequest.created_at)
    parts.append(select(
        _const('approval_pending').label('kind'),
        case((and_(ApprovalRequest.expires_at.isnot(None), ApprovalRequest.expires_at < soon), _CRITICAL),
             else_=_WARNING).label('rank'),
        ApprovalRequest.id.label('id'), text_label(ApprovalRequest.request_type).label('label'),
        due(approval_due).label('due_at'),
    ).where(ApprovalRequest.status == 'pending'))

    parts.append(select(
        _const('scep_request_pending').label('kind'), _WARNING.label('rank'),
        SCEPRequest.id.label('id'), text_label(SCEPRequest.subject).label('label'),
        due(SCEPRequest.created_at).label('due_at'),
    ).where(SCEPRequest.status == 'pending'))

    parts.append(select(
        _const('key_recovery_pending').label('kind'), _WARNING.label('rank'),
        KeyRecoveryRequest.id.label('id'), text_label(KeyRecoveryRequest.cert_cn).label('label'),
        due(KeyRecoveryRequest.requested_at).label('due_at'),
    ).where(KeyRecoveryRequest.status == STATUS_PENDING))

    # nextUpdate of the newest full CRL by number, uploads included, as the CDP serves it
    full_crl = or_(CRLMetadata.is_delta.is_(False), CRLMetadata.is_delta.is_(None))
    newest = (select(CRLMetadata.ca_id.label('ca_id'), func.max(CRLMetadata.crl_number).label('number'))
              .where(full_crl).group_by(CRLMetadata.ca_id).subquery())
    latest = (select(CRLMetadata.ca_id.label('ca_id'), CRLMetadata.next_update.label('next_update'))
              .join(newest, and_(newest.c.ca_id == CRLMetadata.ca_id, newest.c.number == CRLMetadata.crl_number))
              .subquery())
    # Critical once stale or missing; a warning within min(24 h, half the CA's CRL validity)
    stale = or_(latest.c.next_update.is_(None), latest.c.next_update < now)
    parts.append(select(
        case((latest.c.next_update.is_(None), _const('crl_missing')),
             else_=_const('crl_due')).label('kind'),
        case((stale, _CRITICAL), else_=_WARNING).label('rank'),
        CA.id.label('id'), text_label(CA.descr).label('label'),
        due(func.coalesce(latest.c.next_update, literal(now, DateTime))).label('due_at'),
    ).select_from(CA).outerjoin(latest, latest.c.ca_id == CA.id)
     .where(_active_ca(now), CA.cdp_enabled.is_(True),
            or_(stale, and_(latest.c.next_update < soon,
                            _within_half_validity(latest.c.next_update, now, dialect)))))

    parts.append(select(
        _const('manual_renewal_due').label('kind'),
        case((Certificate.valid_to < soon, _CRITICAL), else_=_WARNING).label('rank'),
        Certificate.id.label('id'), text_label(func.coalesce(func.nullif(Certificate.subject_cn, ''), Certificate.descr)).label('label'),
        due(Certificate.valid_to).label('due_at'),
    ).where(*renewal_conditions('manual_renewal_due', now, config, dialect)))

    cert_label = text_label(func.coalesce(func.nullif(Certificate.subject_cn, ''), Certificate.descr))
    for kind, rank in (('client_renewal_overdue', _WARNING), ('auto_renewal_blocked', _CRITICAL),
                       ('renewal_declined', _WARNING)):
        conditions = renewal_conditions(kind, now, config, dialect)
        parts.append(select(
            _const(kind).label('kind'), rank.label('rank'), Certificate.id.label('id'),
            cert_label.label('label'), due(Certificate.valid_to).label('due_at'),
        ).where(*conditions))

    parts.append(select(
        _const('ca_expiring').label('kind'),
        case((CA.valid_to < now + timedelta(days=CA_EXPIRY_CRITICAL_DAYS), _CRITICAL), else_=_WARNING).label('rank'),
        CA.id.label('id'), text_label(CA.descr).label('label'), due(CA.valid_to).label('due_at'),
    ).where(_active_ca(now), CA.valid_to.isnot(None),
            CA.valid_to < now + timedelta(days=CA_EXPIRY_WARNING_DAYS)))

    return union_all(*parts).subquery('queue')


def _renewed_by_acme_client():
    """UCM's ACME client renews a certificate only through its issued order with renewal
    on, and only while the global switch, when set, reads 'true' (acme_renewal_service)."""
    switch_off = select(SystemConfig.id).where(
        SystemConfig.key == 'acme.client.renewal_enabled',
        or_(SystemConfig.value.is_(None), func.lower(SystemConfig.value) != 'true')).exists()
    order = select(AcmeClientOrder.id).where(
        AcmeClientOrder.certificate_id == Certificate.id, AcmeClientOrder.renewal_enabled.is_(True),
        AcmeClientOrder.status == 'issued').exists()
    return and_(Certificate.source == 'acme_client', order, ~switch_off)


def _no_key():
    return or_(Certificate.prv.is_(None), Certificate.prv == '')


def _superseded(now):
    """Same non-empty CN, full subject and SANs from the same CA, by a live
    certificate that itself lies beyond the expiry window."""
    newer = aliased(Certificate)
    exists = (select(newer.id).where(
        newer.subject_cn == Certificate.subject_cn, newer.caref == Certificate.caref,
        newer.subject.is_not_distinct_from(Certificate.subject),
        newer.san_dns.is_not_distinct_from(Certificate.san_dns),
        newer.san_ip.is_not_distinct_from(Certificate.san_ip),
        newer.id != Certificate.id, newer.valid_to > now + timedelta(days=EXPIRY_WINDOW_DAYS),
        holds_certificate(newer), newer.revoked.is_(False), _not_archived(newer)).exists())
    return and_(Certificate.subject_cn.isnot(None), Certificate.subject_cn != '', exists)


def _client_renewed():
    """Protocol enrolment without a stored key: the client renews it itself."""
    return and_(Certificate.source.isnot(None), Certificate.source.in_(CLIENT_RENEWED_SOURCES), _no_key())


def _live_until(now, days):
    return [holds_certificate(), Certificate.revoked.is_(False), _not_archived(),
            Certificate.valid_to.isnot(None), Certificate.valid_to > now,
            Certificate.valid_to <= now + timedelta(days=days)]


def _manual_renewal_conditions(now, config):
    """Issued, live, inside the expiry window, left alone by auto-renewal (no stored key, a
    source it skips, or auto-renewal off). Excludes: a declined renewal, a delegated OCSP
    responder (its own task), client-renewed sources and UCM's ACME client, a superseded one."""
    skipped = [_no_key(), Certificate.source.is_(None), Certificate.source.notin_(config['renewal_sources'] or [''])]
    return [
        *_live_until(now, EXPIRY_WINDOW_DAYS),
        true() if not config['enabled'] else or_(*skipped),
        ~_renewed_by_acme_client(),
        ~_client_renewed(),
        ~_superseded(now),
        ~_renewal_declined(),
        ~renewed_by_responder_task(),
    ]


def _auto_renewed(config):
    """The certificates the auto-renewal pass picks up (stored key, a source it renews)."""
    if not config['enabled']:
        return false()
    return and_(~_no_key(), Certificate.source.isnot(None),
                Certificate.source.in_(config['renewal_sources'] or ['']))


def _issuer_cannot_sign(now):
    """Its CA, by refid, is offline, revoked, expired, awaiting its certificate or without
    a key (local or HSM): renewal refuses it (services/cert/renewal.py, _signing_ca)."""
    no_ca_key = and_(or_(CA.prv.is_(None), CA.prv == ''), CA.hsm_key_id.is_(None))
    return select(CA.id).where(
        CA.refid == Certificate.caref,
        or_(CA.offline.is_(True), CA.revoked.is_(True), CA.crt.is_(None), CA.crt == '', no_ca_key,
            CA.valid_to <= now)).exists()


def _renewal_declined(auto_only=False):
    """Any rejected renewal request naming the certificate in its current lifetime, whatever
    its trigger (not checked); ``auto_only`` keeps the scheduler's own requests."""
    named = literal('%"certificate_id": ', String) + cast(Certificate.id, String) + literal(',%', String)
    conditions = [
        ApprovalRequest.request_type == 'renewal', ApprovalRequest.status == 'rejected',
        ApprovalRequest.request_data.like(named),
        or_(Certificate.valid_from.is_(None), ApprovalRequest.created_at >= Certificate.valid_from)]
    if auto_only:
        conditions.append(ApprovalRequest.request_data.like('%"trigger": "auto"%'))
    return select(ApprovalRequest.id).where(*conditions).exists()


def _and_blocked(now, config, dialect):
    return and_(*_blocked_conditions(now, config, dialect))


def _past_last_third(now, dialect):
    """The scheduler never renews before the last third of the lifetime
    (AutoRenewalService._in_renewal_window); a certificate without valid_from is taken as due."""
    if dialect == 'sqlite':
        remaining = func.julianday(Certificate.valid_to) - func.julianday(literal(now, DateTime))
        lifetime = func.julianday(Certificate.valid_to) - func.julianday(Certificate.valid_from)
    else:
        remaining = Certificate.valid_to - literal(now, DateTime)
        lifetime = Certificate.valid_to - Certificate.valid_from
    return or_(Certificate.valid_from.is_(None), remaining * 3 <= lifetime)


def _blocked_conditions(now, config, dialect):
    """Due for auto-renewal (inside days_before_expiry and the last third of its lifetime), which
    then fails on every pass because the CA cannot sign; only an automatic refusal parks it."""
    return [*_live_until(now, config['days_before_expiry']), _past_last_third(now, dialect),
            _auto_renewed(config), _issuer_cannot_sign(now), ~_renewal_declined(auto_only=True)]


def _declined_conditions(now, config, dialect):
    """Precedence auto_renewal_blocked > renewal_declined: a certificate is queued once."""
    return [*_live_until(now, EXPIRY_WINDOW_DAYS), _renewal_declined(), ~_superseded(now),
            ~_and_blocked(now, config, dialect)]


def _client_overdue_conditions(now):
    """A client-renewed certificate its client has not replaced a week before expiry."""
    return [*_live_until(now, CLIENT_RENEWAL_OVERDUE_DAYS), _client_renewed(), ~_superseded(now),
            ~_renewal_declined()]


def _short_label(kind, label):
    if label and kind in ('acme_order_failed', 'acme_client_renewal_failed'):
        import json
        try:
            values = json.loads(label)
            names = [v.get('value') if isinstance(v, dict) else v for v in values]
            label = ', '.join(str(n) for n in names if n)
        except (TypeError, ValueError, AttributeError):
            pass
    return (label or '')[:200]


def work_queue(session, limit, now=None, kinds=None):
    """Items to act on, critical first then by due date, and the total per kind.
    *kinds* restricts the items (not the counts) to those kinds."""
    now = now or utc_now()
    queue = _queue_union(now, session.get_bind().dialect.name)
    counts = {kind: 0 for kind in QUEUE_KINDS}
    for kind, n in session.execute(select(queue.c.kind, func.count()).group_by(queue.c.kind)):
        counts[kind] = n
    listing = select(queue)
    if kinds is not None:
        listing = listing.where(queue.c.kind.in_(list(kinds)))
    rows = session.execute(
        listing.order_by(queue.c.rank, queue.c.due_at, queue.c.kind, queue.c.id).limit(limit))
    items = [{
        'kind': r.kind, 'tier': 'critical' if r.rank == 0 else 'warning', 'id': r.id,
        'label': _short_label(r.kind, r.label), 'due_at': utc_isoformat(r.due_at),
        'href_hint': _HREF[r.kind].format(id=r.id),
    } for r in rows]
    return {'items': items, 'counts': counts, 'total': sum(counts.values()),
            'filter_hints': {kind: {'renewal': kind} for kind in RENEWAL_KINDS}}


# ----------------------------------------------------------------- health

def _series(dates, ok_rows, failed_rows):
    ok = {_day(d): n for d, n in ok_rows}
    failed = {_day(d): n for d, n in failed_rows}
    return [{'date': d, 'ok': ok.get(d, 0), 'failed': failed.get(d, 0)} for d in dates]


def _by_day(session, column, start, *where):
    day = func.date(column)
    return session.execute(select(day, func.count()).where(column >= start, *where).group_by(day)).all()


def _last(session, column, status_column, *where):
    row = session.execute(select(column, status_column).where(*where)
                          .order_by(column.desc()).limit(1)).first()
    return (row[0], row[1]) if row else (None, None)


def _audit_status(success):
    return None if success is None else ('ok' if success else 'failed')


def _acme_health(session, start, dates):
    acme = AuditLog.action.startswith('acme.', autoescape=True)
    day = func.date(AuditLog.timestamp)
    rows = session.execute(select(day, AuditLog.success, func.count())
                           .where(acme, AuditLog.timestamp >= start)
                           .group_by(day, AuditLog.success)).all()
    when, success = _last(session, AuditLog.timestamp, AuditLog.success, acme)
    return {
        'basis': 'audit',
        'periods': _series(dates, [(d, n) for d, s, n in rows if s is not False],
                           [(d, n) for d, s, n in rows if s is False]),
        'last_operation_at': utc_isoformat(when), 'last_status': _audit_status(success),
    }


def _scep_health(session, start, dates):
    day = func.date(SCEPRequest.created_at)
    rows = session.execute(select(day, SCEPRequest.status, func.count())
                           .where(SCEPRequest.created_at >= start,
                                  SCEPRequest.status.in_(('approved', 'rejected')))
                           .group_by(day, SCEPRequest.status)).all()
    when, status = _last(session, SCEPRequest.created_at, SCEPRequest.status)
    return {
        'basis': 'requests',
        'periods': _series(dates, [(d, n) for d, s, n in rows if s == 'approved'],
                           [(d, n) for d, s, n in rows if s == 'rejected']),
        'last_operation_at': utc_isoformat(when),
        'last_status': {'approved': 'ok', 'rejected': 'failed'}.get(status, status),
    }


def _est_health(session, start, dates):
    """EST audits only its server-side key generation; enrolments are counted as issued rows."""
    issued = and_(Certificate.source == 'est', holds_certificate())
    failed = and_(AuditLog.action.startswith('est_', autoescape=True), AuditLog.success.is_(False))
    ok_rows = _by_day(session, Certificate.created_at, start, issued)
    failed_rows = _by_day(session, AuditLog.timestamp, start, failed)
    ok_at, _ = _last(session, Certificate.created_at, Certificate.id, issued)
    failed_at, _ = _last(session, AuditLog.timestamp, AuditLog.id, failed)
    last = max((t for t in (ok_at, failed_at) if t is not None), default=None)
    return {
        'basis': 'issued', 'failed_basis': 'audit',
        'periods': _series(dates, ok_rows, failed_rows),
        'last_operation_at': utc_isoformat(last),
        'last_status': None if last is None else ('ok' if last == ok_at else 'failed'),
    }


def _scheduler_health():
    from services.scheduler_service import get_scheduler
    statuses = get_scheduler().get_all_tasks_status()
    by_status = {}
    stale = False
    last_run, last_status = None, None
    for status in statuses.values():
        key = status.get('last_status') or 'never'
        by_status[key] = by_status.get(key, 0) + 1
        stale = stale or bool(status.get('stale'))
        run = status.get('last_run')
        if run and (last_run is None or run > last_run):
            last_run, last_status = run, status.get('last_status')
    return {'basis': 'scheduler', 'periods': None, 'tasks': len(statuses),
            'by_status': by_status, 'stale': stale,
            'last_operation_at': last_run, 'last_status': last_status}


def protocol_health(session, days, now=None):
    """Per protocol, ``days`` UTC calendar days of ok/failed counts, oldest first."""
    now = now or utc_now()
    start, dates = _window(days, now)
    return {
        'days': days, 'from': dates[0], 'to': dates[-1],
        'protocols': {
            'acme': _acme_health(session, start, dates),
            'scep': _scep_health(session, start, dates),
            'est': _est_health(session, start, dates),
            'scheduler': _scheduler_health(),
        },
    }


# ------------------------------------------------------------- compliance

def _lifetime_exceeds(dialect, days):
    if dialect == 'sqlite':
        return func.julianday(Certificate.valid_to) - func.julianday(Certificate.valid_from) >= days + 1
    return Certificate.valid_to - Certificate.valid_from >= timedelta(days=days + 1)


def live_conditions(now):
    """The set every compliance counter is taken over (and the list's ``live`` filter)."""
    return [holds_certificate(), Certificate.revoked.is_(False), _not_archived(),
            or_(Certificate.valid_to.is_(None), Certificate.valid_to > now)]


def weak_rsa_condition(bits=RSA_MIN_BITS):
    return and_(Certificate.key_algo.like('RSA%'), Certificate.key_bits < bits)


def weak_hash_condition(hashes=WEAK_SIG_HASHES):
    return Certificate.sig_hash.in_(list(hashes))


def server_condition():
    templates = select(CertificateTemplate.id).where(CertificateTemplate.template_type == 'web_server')
    return or_(Certificate.cert_type == 'server_cert', Certificate.template_id.in_(templates))


def long_server_condition(dialect, days=SERVER_LIFETIME_MAX_DAYS):
    return and_(server_condition(), lifetime_over_condition(dialect, days))


def lifetime_over_condition(dialect, days):
    return and_(Certificate.valid_from.isnot(None), Certificate.valid_to.isnot(None),
                _lifetime_exceeds(dialect, days))


def no_key_condition():
    return _no_key()


# Counter name -> list filter that reproduces it (the list ANDs ``live`` with the rest)
COMPLIANCE_LIST_FILTERS = {
    'rsa_below_3072': {'live': 'true', 'key_algo_prefix': 'RSA', 'key_bits_below': str(RSA_MIN_BITS)},
    'weak_signature_hash': {'live': 'true', 'sig_hash': list(WEAK_SIG_HASHES)},
    'server_lifetime_over_398_days': {'live': 'true', 'server': 'true',
                                      'lifetime_over_days': str(SERVER_LIFETIME_MAX_DAYS)},
    'incomplete_chain': {'live': 'true', 'incomplete_chain': 'true'},
    'no_private_key': {'live': 'true', 'no_key': 'true'},
}
RENEWAL_KINDS = ('manual_renewal_due', 'client_renewal_overdue', 'auto_renewal_blocked', 'renewal_declined')


def renewal_conditions(kind, now, config, dialect):
    """The rows of one certificate queue kind: the queue and the list's ``renewal`` filter."""
    if kind == 'manual_renewal_due':
        return _manual_renewal_conditions(now, config)
    if kind == 'client_renewal_overdue':
        return _client_overdue_conditions(now)
    if kind == 'auto_renewal_blocked':
        return _blocked_conditions(now, config, dialect)
    if kind == 'renewal_declined':
        return _declined_conditions(now, config, dialect)
    raise ValueError(kind)


_BOOL = ('1', 'true', 'yes')
# Bounds keep a number inside what both backends bind and timedelta holds: beyond them, 400 and not 500
MAX_KEY_BITS_FILTER = 1_000_000
MAX_LIFETIME_DAYS_FILTER = 100_000
LIST_FILTER_PARAMS = frozenset({'live', 'key_algo', 'key_algo_prefix', 'key_bits_below', 'sig_hash', 'server',
                                'lifetime_over_days', 'no_key', 'incomplete_chain', 'renewal'})


def certificate_list_conditions(args, dialect, now=None):
    """Conditions for the list filters in *args* (a werkzeug MultiDict); ValueError on a bad value."""
    now = now or utc_now()
    conditions = []

    def number(name, maximum):
        raw = args.get(name)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            raise ValueError(f'{name} must be a whole number') from None
        if not 0 <= value <= maximum:
            raise ValueError(f'{name} must be between 0 and {maximum}')
        return value

    def flag(name):
        raw = args.get(name)
        if raw is None:
            return False
        if raw.lower() not in _BOOL + ('0', 'false', 'no'):
            raise ValueError(f'{name} must be true or false')
        return raw.lower() in _BOOL

    if flag('live'):
        conditions += live_conditions(now)
    if flag('no_key'):
        conditions.append(no_key_condition())
    if flag('incomplete_chain'):
        conditions.append(orphan_condition())
    if flag('server'):
        conditions.append(server_condition())
    if 'key_algo' in args:
        conditions.append(Certificate.key_algo.in_(args.getlist('key_algo')))
    if 'key_algo_prefix' in args:
        prefix = args.get('key_algo_prefix')
        if not prefix.isalnum():
            raise ValueError('key_algo_prefix must be alphanumeric')
        conditions.append(Certificate.key_algo.like(f'{prefix}%'))
    if 'key_bits_below' in args:
        conditions.append(Certificate.key_bits < number('key_bits_below', MAX_KEY_BITS_FILTER))
    if 'sig_hash' in args:
        conditions.append(weak_hash_condition(args.getlist('sig_hash')))
    if 'lifetime_over_days' in args:
        conditions.append(lifetime_over_condition(dialect, number('lifetime_over_days', MAX_LIFETIME_DAYS_FILTER)))
    if 'renewal' in args:
        kinds = args.getlist('renewal')
        bad = [k for k in kinds if k not in RENEWAL_KINDS]
        if bad:
            raise ValueError(f"Unknown renewal kind: {', '.join(bad)}")
        config = _renewal_config()
        conditions.append(or_(*[and_(*renewal_conditions(k, now, config, dialect)) for k in kinds]))
    return conditions


def _list_filter(hint):
    return {'filter_hint': hint, 'filter_available': hint is not None}


def compliance_summary(session, now=None):
    """Counters over the live issued certificates, each with the list filter it stands for."""
    now = now or utc_now()
    dialect = session.get_bind().dialect.name
    rules = {'rsa_below_3072': weak_rsa_condition(), 'weak_signature_hash': weak_hash_condition(),
             'server_lifetime_over_398_days': long_server_condition(dialect),
             'incomplete_chain': orphan_condition(), 'no_private_key': no_key_condition()}
    total = lambda cond: func.coalesce(func.sum(case((cond, 1), else_=0)), 0)  # noqa: E731
    row = session.execute(
        select(func.count(), *[total(c) for c in rules.values()])
        .select_from(Certificate).where(*live_conditions(now))).one()
    algos = session.execute(select(Certificate.key_algo, func.count()).where(*live_conditions(now))
                            .group_by(Certificate.key_algo).order_by(func.count().desc())).all()
    return {
        'total': row[0],
        'by_key_algorithm': [{'key_algo': algo, 'count': n, **_list_filter(
            {'live': 'true', 'key_algo': algo} if algo is not None else None)} for algo, n in algos],
        'counters': {name: {'count': int(n), **_list_filter(COMPLIANCE_LIST_FILTERS[name])}
                     for name, n in zip(rules, row[1:])},
    }


# --------------------------------------------------------------- issuance

def _per_ca_day(session, column, start):
    """``(caref, ca id, ca name, day, count)`` of the rows whose ``column`` falls in the window."""
    day = func.date(column)
    return session.execute(
        select(Certificate.caref, CA.id, CA.descr, day, func.count())
        .select_from(Certificate).outerjoin(CA, CA.refid == Certificate.caref)
        .where(holds_certificate(), column >= start)
        .group_by(Certificate.caref, CA.id, CA.descr, day)).all()


def issuance(session, days, now=None):
    """Per CA and per UTC day, certificates issued (``created_at``) and renewed in place
    (``renewed_at``: the last renewal of each certificate, so one renewed several times in
    the window counts once); the total per source counts issuances only."""
    now = now or utc_now()
    start, dates = _window(days, now)
    source = func.coalesce(Certificate.source, 'manual')
    by_source = {s: n for s, n in session.execute(
        select(source, func.count()).where(holds_certificate(), Certificate.created_at >= start)
        .group_by(source))}
    per_ca = {}
    for counter, column in (('issued', Certificate.created_at), ('renewed', Certificate.renewed_at)):
        for caref, ca_id, name, d, n in _per_ca_day(session, column, start):
            entry = per_ca.setdefault(caref, {'caref': caref, 'ca_id': ca_id, 'ca_name': name,
                                              'issued': {}, 'renewed': {}})
            entry[counter][_day(d)] = n
    by_ca = []
    for entry in per_ca.values():
        issued, renewed = entry.pop('issued'), entry.pop('renewed')
        entry['periods'] = [{'date': d, 'issued': issued.get(d, 0), 'renewed': renewed.get(d, 0)}
                            for d in dates]
        entry['issued'], entry['renewed'] = sum(issued.values()), sum(renewed.values())
        entry['total'] = entry['issued'] + entry['renewed']
        by_ca.append(entry)
    by_ca.sort(key=lambda e: (-e['total'], e['ca_name'] or ''))
    return {'days': days, 'from': dates[0], 'to': dates[-1], 'by_ca': by_ca,
            'by_source': by_source, 'total': sum(by_source.values()),
            'renewed': sum(e['renewed'] for e in by_ca)}
