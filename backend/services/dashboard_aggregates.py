"""Overview aggregates: work queue, protocol health, compliance, issuance.

Each figure is a COUNT or GROUP BY run by the database, bounded in rows and in
statements whatever the table sizes. Nothing here loads ``crt`` or ``prv``:
key size and signature hash are the ``key_bits`` / ``sig_hash`` columns, set
whenever a certificate is stored (``models/certificate.py``).
"""
from datetime import datetime, timedelta

from sqlalchemy import (DateTime, String, and_, case, func, literal, literal_column,
                        or_, select, true, type_coerce, union_all)

from models import CA, Certificate
from models.acme_models import AcmeClientOrder, AcmeOrder
from models.audit_log import AuditLog
from models.certificate_template import CertificateTemplate
from models.crl import CRLMetadata
from models.key_recovery import KeyRecoveryRequest, STATUS_PENDING
from models.policy import ApprovalRequest
from models.scep import SCEPRequest
from utils.cert_status import EXPIRY_WINDOW_DAYS, holds_certificate, orphan_condition
from utils.datetime_utils import utc_isoformat, utc_now

QUEUE_KINDS = ('acme_order_failed', 'acme_client_renewal_failed', 'approval_pending',
               'scep_request_pending', 'key_recovery_pending', 'crl_due', 'crl_missing',
               'manual_renewal_due', 'ca_expiring')
ACME_FAILURE_LOOKBACK_DAYS = 7
CRITICAL_WITHIN = timedelta(hours=24)
CA_EXPIRY_WARNING_DAYS = 365
CA_EXPIRY_CRITICAL_DAYS = 90
# Python's compliance grade calls a lifetime long from 399 whole days on
SERVER_LIFETIME_MAX_DAYS = 398
RSA_MIN_BITS = 3072
WEAK_SIG_HASHES = ('sha1', 'md5')

_HREF = {
    'acme_order_failed': '/acme?tab=orders&order={id}',
    'acme_client_renewal_failed': '/acme?tab=client&order={id}',
    'approval_pending': '/approvals?request={id}',
    'scep_request_pending': '/scep-config?tab=requests&request={id}',
    'key_recovery_pending': '/key-recovery?request={id}',
    'crl_due': '/crl-ocsp?ca={id}',
    'crl_missing': '/crl-ocsp?ca={id}',
    'manual_renewal_due': '/certificates/{id}',
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

def _queue_union(now):
    """One SELECT per kind, all shaped (kind, rank, id, label, due_at); rank 0 is critical."""
    soon = now + CRITICAL_WITHIN
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

    # nextUpdate of the newest full CRL signed here, per CA; deltas and uploads do not refresh it
    own_full = and_(or_(CRLMetadata.is_delta.is_(False), CRLMetadata.is_delta.is_(None)),
                    or_(CRLMetadata.is_external.is_(False), CRLMetadata.is_external.is_(None)))
    newest = (select(CRLMetadata.ca_id.label('ca_id'), func.max(CRLMetadata.crl_number).label('number'))
              .where(own_full).group_by(CRLMetadata.ca_id).subquery())
    latest = (select(CRLMetadata.ca_id.label('ca_id'), CRLMetadata.next_update.label('next_update'))
              .join(newest, and_(newest.c.ca_id == CRLMetadata.ca_id, newest.c.number == CRLMetadata.crl_number))
              .subquery())
    parts.append(select(
        case((latest.c.next_update.is_(None), _const('crl_missing')),
             else_=_const('crl_due')).label('kind'),
        _CRITICAL.label('rank'), CA.id.label('id'), text_label(CA.descr).label('label'),
        due(func.coalesce(latest.c.next_update, literal(now, DateTime))).label('due_at'),
    ).select_from(CA).outerjoin(latest, latest.c.ca_id == CA.id)
     .where(_active_ca(now), CA.cdp_enabled.is_(True),
            or_(latest.c.next_update.is_(None), latest.c.next_update < soon)))

    parts.append(select(
        _const('manual_renewal_due').label('kind'),
        case((Certificate.valid_to < soon, _CRITICAL), else_=_WARNING).label('rank'),
        Certificate.id.label('id'), text_label(func.coalesce(Certificate.subject_cn, Certificate.descr)).label('label'),
        due(Certificate.valid_to).label('due_at'),
    ).where(*_manual_renewal_conditions(now)))

    parts.append(select(
        _const('ca_expiring').label('kind'),
        case((CA.valid_to < now + timedelta(days=CA_EXPIRY_CRITICAL_DAYS), _CRITICAL), else_=_WARNING).label('rank'),
        CA.id.label('id'), text_label(CA.descr).label('label'), due(CA.valid_to).label('due_at'),
    ).where(_active_ca(now), CA.valid_to.isnot(None),
            CA.valid_to < now + timedelta(days=CA_EXPIRY_WARNING_DAYS)))

    return union_all(*parts).subquery('queue')


def _manual_renewal_conditions(now):
    """Issued, live, inside the expiry window, and left alone by auto-renewal:
    no stored key, a source it skips (NULL included), or auto-renewal off."""
    config = _renewal_config()
    skipped = [or_(Certificate.prv.is_(None), Certificate.prv == ''),
               Certificate.source.is_(None), Certificate.source.notin_(config['renewal_sources'] or [''])]
    return [
        holds_certificate(), Certificate.revoked.is_(False), _not_archived(),
        Certificate.valid_to.isnot(None), Certificate.valid_to > now,
        Certificate.valid_to <= now + timedelta(days=EXPIRY_WINDOW_DAYS),
        true() if not config['enabled'] else or_(*skipped),
    ]


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


def work_queue(session, limit, now=None):
    """Items to act on, critical first then by due date, and the total per kind."""
    now = now or utc_now()
    queue = _queue_union(now)
    counts = {kind: 0 for kind in QUEUE_KINDS}
    for kind, n in session.execute(select(queue.c.kind, func.count()).group_by(queue.c.kind)):
        counts[kind] = n
    rows = session.execute(
        select(queue).order_by(queue.c.rank, queue.c.due_at, queue.c.kind, queue.c.id).limit(limit))
    items = [{
        'kind': r.kind, 'tier': 'critical' if r.rank == 0 else 'warning', 'id': r.id,
        'label': _short_label(r.kind, r.label), 'due_at': utc_isoformat(r.due_at),
        'href_hint': _HREF[r.kind].format(id=r.id),
    } for r in rows]
    return {'items': items, 'counts': counts, 'total': sum(counts.values())}


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

def _lifetime_exceeds(session, days):
    if session.get_bind().dialect.name == 'sqlite':
        return func.julianday(Certificate.valid_to) - func.julianday(Certificate.valid_from) >= days + 1
    return Certificate.valid_to - Certificate.valid_from >= timedelta(days=days + 1)


def compliance_summary(session, now=None):
    """Counters over the live issued certificates, each with the list filter it stands for."""
    now = now or utc_now()
    live = [holds_certificate(), Certificate.revoked.is_(False), _not_archived(),
            or_(Certificate.valid_to.is_(None), Certificate.valid_to > now)]
    weak_rsa = and_(Certificate.key_algo.like('RSA%'), Certificate.key_bits < RSA_MIN_BITS)
    weak_hash = Certificate.sig_hash.in_(WEAK_SIG_HASHES)
    server = or_(Certificate.cert_type == 'server_cert', CertificateTemplate.template_type == 'web_server')
    long_server = and_(server, Certificate.valid_from.isnot(None), Certificate.valid_to.isnot(None),
                       _lifetime_exceeds(session, SERVER_LIFETIME_MAX_DAYS))
    no_key = or_(Certificate.prv.is_(None), Certificate.prv == '')
    total = lambda cond: func.coalesce(func.sum(case((cond, 1), else_=0)), 0)  # noqa: E731
    row = session.execute(
        select(func.count(), total(weak_rsa), total(weak_hash), total(long_server),
               total(orphan_condition()), total(no_key))
        .select_from(Certificate)
        .outerjoin(CertificateTemplate, CertificateTemplate.id == Certificate.template_id)
        .where(*live)).one()
    algos = session.execute(select(Certificate.key_algo, func.count()).where(*live)
                            .group_by(Certificate.key_algo).order_by(func.count().desc())).all()
    live_hint = {'status': ['valid', 'expiring']}
    counters = {
        'rsa_below_3072': (row[1], {**live_hint, 'key_family': 'RSA', 'key_bits_lt': RSA_MIN_BITS}),
        'weak_signature_hash': (row[2], {**live_hint, 'sig_hash': list(WEAK_SIG_HASHES)}),
        'server_lifetime_over_398_days': (
            row[3], {**live_hint, 'server': True, 'lifetime_gt_days': SERVER_LIFETIME_MAX_DAYS}),
        'incomplete_chain': (row[4], {'status': ['orphan']}),
        'no_private_key': (row[5], {**live_hint, 'has_private_key': False}),
    }
    return {
        'total': row[0],
        'by_key_algorithm': [{'key_algo': algo, 'count': n,
                              'filter_hint': {**live_hint, 'key_algo': algo}} for algo, n in algos],
        'counters': {name: {'count': int(n), 'filter_hint': hint} for name, (n, hint) in counters.items()},
    }


# --------------------------------------------------------------- issuance

def issuance(session, days, now=None):
    """Certificates issued per CA and per UTC day, plus the total per source."""
    now = now or utc_now()
    start, dates = _window(days, now)
    issued = [holds_certificate(), Certificate.created_at >= start]
    day = func.date(Certificate.created_at)
    rows = session.execute(
        select(Certificate.caref, CA.id, CA.descr, day, func.count())
        .select_from(Certificate).outerjoin(CA, CA.refid == Certificate.caref)
        .where(*issued).group_by(Certificate.caref, CA.id, CA.descr, day)).all()
    source = func.coalesce(Certificate.source, 'manual')
    by_source = {s: n for s, n in session.execute(
        select(source, func.count()).where(*issued).group_by(source))}
    per_ca = {}
    for caref, ca_id, name, d, n in rows:
        entry = per_ca.setdefault(caref, {'caref': caref, 'ca_id': ca_id, 'ca_name': name, 'counts': {}})
        entry['counts'][_day(d)] = n
    by_ca = []
    for entry in per_ca.values():
        counts = entry.pop('counts')
        entry['periods'] = [{'date': d, 'count': counts.get(d, 0)} for d in dates]
        entry['total'] = sum(counts.values())
        by_ca.append(entry)
    by_ca.sort(key=lambda e: (-e['total'], e['ca_name'] or ''))
    return {'days': days, 'from': dates[0], 'to': dates[-1], 'by_ca': by_ca,
            'by_source': by_source, 'total': sum(by_source.values())}
