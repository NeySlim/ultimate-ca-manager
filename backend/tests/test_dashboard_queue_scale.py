"""The certificate kinds of the work queue on a large table: the same rows as the
conditions they replace, no correlated subquery that walks a table for each
certificate, and a cost that grows linearly with the number of certificates."""
import json
import re
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import String, and_, cast, event, false, func, insert, literal, or_, select, text, true
from sqlalchemy.orm import aliased

from models import CA, Certificate, SystemConfig, db
from models.acme_models import AcmeClientOrder
from models.policy import ApprovalRequest
from services import dashboard_aggregates as da
from tests.dashboard_pem import self_signed
from utils.cert_status import EXPIRY_WINDOW_DAYS, holds_certificate
from utils.datetime_utils import utc_now

from cryptography.hazmat.primitives.asymmetric import ec

_PEM = self_signed(ec.generate_private_key(ec.SECP256R1()))
KINDS = da.RENEWAL_KINDS
SETTINGS = ('auto_renewal_enabled', 'auto_renewal_sources', 'auto_renewal_days',
            'acme.client.renewal_enabled', 'ocsp_responder_auto_renew')


# ------------------------------------------------- the conditions before PERF-01, kept as the reference

def _old_not_archived(model=Certificate):
    return or_(model.archived.is_(False), model.archived.is_(None))


def _old_no_key():
    return or_(Certificate.prv.is_(None), Certificate.prv == '')


def _old_renewed_by_acme_client():
    switch_off = select(SystemConfig.id).where(
        SystemConfig.key == 'acme.client.renewal_enabled',
        or_(SystemConfig.value.is_(None), func.lower(SystemConfig.value) != 'true')).exists()
    order = select(AcmeClientOrder.id).where(
        AcmeClientOrder.certificate_id == Certificate.id, AcmeClientOrder.renewal_enabled.is_(True),
        AcmeClientOrder.status == 'issued').exists()
    return and_(Certificate.source == 'acme_client', order, ~switch_off)


def _old_superseded(now):
    newer = aliased(Certificate)
    exists = (select(newer.id).where(
        newer.subject_cn == Certificate.subject_cn, newer.caref == Certificate.caref,
        newer.subject.is_not_distinct_from(Certificate.subject),
        newer.san_dns.is_not_distinct_from(Certificate.san_dns),
        newer.san_ip.is_not_distinct_from(Certificate.san_ip),
        newer.id != Certificate.id, newer.valid_to > now + timedelta(days=EXPIRY_WINDOW_DAYS),
        holds_certificate(newer), newer.revoked.is_(False), _old_not_archived(newer)).exists())
    return and_(Certificate.subject_cn.isnot(None), Certificate.subject_cn != '', exists)


def _old_client_renewed():
    return and_(Certificate.source.isnot(None), Certificate.source.in_(da.CLIENT_RENEWED_SOURCES), _old_no_key())


def _old_live_until(now, days):
    return [holds_certificate(), Certificate.revoked.is_(False), _old_not_archived(),
            Certificate.valid_to.isnot(None), Certificate.valid_to > now,
            Certificate.valid_to <= now + timedelta(days=days)]


def _old_responder():
    bound = select(SystemConfig.id).where(
        SystemConfig.key.like('ocsp_responder_cert_%'), SystemConfig.value == cast(Certificate.id, String)).exists()
    switched_off = select(SystemConfig.id).where(
        SystemConfig.key == 'ocsp_responder_auto_renew',
        or_(SystemConfig.value.is_(None), SystemConfig.value != 'true')).exists()
    return and_(bound, Certificate.prv.isnot(None), Certificate.prv != '', ~switched_off)


def _old_manual(now, config):
    skipped = [_old_no_key(), Certificate.source.is_(None),
               Certificate.source.notin_(config['renewal_sources'] or [''])]
    return [*_old_live_until(now, EXPIRY_WINDOW_DAYS), true() if not config['enabled'] else or_(*skipped),
            ~_old_renewed_by_acme_client(), ~_old_client_renewed(), ~_old_superseded(now),
            ~_old_renewal_declined(), ~_old_responder()]


def _old_auto_renewed(config):
    if not config['enabled']:
        return false()
    return and_(~_old_no_key(), Certificate.source.isnot(None),
                Certificate.source.in_(config['renewal_sources'] or ['']))


def _old_issuer_cannot_sign(now):
    no_ca_key = and_(or_(CA.prv.is_(None), CA.prv == ''), CA.hsm_key_id.is_(None))
    return select(CA.id).where(
        CA.refid == Certificate.caref,
        or_(CA.offline.is_(True), CA.revoked.is_(True), CA.crt.is_(None), CA.crt == '', no_ca_key,
            CA.valid_to <= now)).exists()


def _old_renewal_declined(auto_only=False):
    named = literal('%"certificate_id": ', String) + cast(Certificate.id, String) + literal(',%', String)
    conditions = [
        ApprovalRequest.request_type == 'renewal', ApprovalRequest.status == 'rejected',
        ApprovalRequest.request_data.like(named),
        or_(Certificate.valid_from.is_(None), ApprovalRequest.created_at >= Certificate.valid_from)]
    if auto_only:
        conditions.append(ApprovalRequest.request_data.like('%"trigger": "auto"%'))
    return select(ApprovalRequest.id).where(*conditions).exists()


def _old_blocked(now, config, dialect):
    return [*_old_live_until(now, config['days_before_expiry']), da._past_last_third(now, dialect),
            _old_auto_renewed(config), _old_issuer_cannot_sign(now), ~_old_renewal_declined(auto_only=True)]


def _old_conditions(kind, now, config, dialect):
    if kind == 'manual_renewal_due':
        return _old_manual(now, config)
    if kind == 'client_renewal_overdue':
        return [*_old_live_until(now, da.CLIENT_RENEWAL_OVERDUE_DAYS), _old_client_renewed(),
                ~_old_superseded(now), ~_old_renewal_declined()]
    if kind == 'auto_renewal_blocked':
        return _old_blocked(now, config, dialect)
    return [*_old_live_until(now, EXPIRY_WINDOW_DAYS), _old_renewal_declined(), ~_old_superseded(now),
            ~and_(*_old_blocked(now, config, dialect))]


# ------------------------------------------------------------------------------------- fixtures

def _set(key, value):
    row = SystemConfig.query.filter_by(key=key).first()
    if value is None:
        if row is not None:
            db.session.delete(row)
    elif row is None:
        db.session.add(SystemConfig(key=key, value=value))
    else:
        row.value = value


class _Rows:
    """Rows created by a test, removed at the end whatever happened."""

    def __init__(self):
        self.ids = {Certificate: [], CA: [], SystemConfig: [], ApprovalRequest: [], AcmeClientOrder: []}

    def add(self, row):
        db.session.add(row)
        db.session.flush()
        self.ids[type(row)].append(row.id)
        return row

    def bulk(self, model, rows):
        if not rows:
            return []
        result = db.session.execute(insert(model).returning(model.id), rows)
        ids = [r[0] for r in result]
        self.ids[model].extend(ids)
        return ids

    def drop(self):
        db.session.rollback()
        for model in (AcmeClientOrder, ApprovalRequest, SystemConfig, Certificate, CA):
            ids = self.ids[model]
            for i in range(0, len(ids), 500):
                model.query.filter(model.id.in_(ids[i:i + 500])).delete(synchronize_session=False)
        db.session.commit()


@pytest.fixture
def rows(app):
    with app.app_context():
        saved = {k: getattr(SystemConfig.query.filter_by(key=k).first(), 'value', None) for k in SETTINGS}
        created = _Rows()
        yield created
        created.drop()
        for key, value in saved.items():
            _set(key, value)
        db.session.commit()


def _ca(rows, name, **kw):
    kw.setdefault('prv', 'k')
    kw.setdefault('valid_to', utc_now() + timedelta(days=3650))
    return rows.add(CA(refid=str(uuid.uuid4()), descr=name, crt='placeholder', **kw))


def _cert(rows, name, days, **kw):
    kw.setdefault('source', 'manual')
    kw.setdefault('subject_cn', name)
    kw.setdefault('valid_from', utc_now() - timedelta(days=300))
    kw.setdefault('crt', _PEM)
    return rows.add(Certificate(refid=str(uuid.uuid4()), descr=name, valid_to=utc_now() + timedelta(days=days), **kw))


def _reject(rows, data, created_days=0):
    body = data if isinstance(data, str) else json.dumps(data)
    return rows.add(ApprovalRequest(request_type='renewal', status='rejected', request_data=body,
                                    created_at=utc_now() - timedelta(days=created_days)))


def _varied(rows):
    """Every rule of the four kinds, on both sides of each boundary."""
    ok = _ca(rows, 'scale-ok')
    other = _ca(rows, 'scale-other')
    offline = _ca(rows, 'scale-offline', offline=True)
    keyless = _ca(rows, 'scale-keyless', prv=None)
    c = {}
    for ca, tag in ((ok, 'ok'), (offline, 'off'), (keyless, 'nokey')):
        for days in (0.5, 5, 10, 20, 45, 200):
            for source in ('manual', 'scep', 'acme', 'acme_client', None, 'import'):
                for prv in ('k', None):
                    name = f'scale-{tag}-{days}-{source}-{prv}'
                    c[name] = _cert(rows, name, days, caref=ca.refid, source=source, prv=prv)
    # supersession: same CN, subject and SANs by a live certificate beyond the window, in the same CA
    for case, kw in (('plain', {}), ('revoked', {'revoked': True}), ('archived', {'archived': True}),
                     ('other_san', {'san_dns': '["b.scale.test"]'}), ('other_ip', {'san_ip': '["192.0.2.9"]'}),
                     ('other_dn', {'subject': 'CN=x,O=B'}), ('other_ca', {'caref': other.refid}),
                     ('inside', {'_days': 25}), ('no_crt', {'crt': None}), ('blank', {'subject_cn': ''})):
        name = f'scale-sup-{case}'
        kw = dict(kw)
        days = kw.pop('_days', 300)
        base = {'caref': ok.refid, 'subject': 'CN=x,O=A', 'san_dns': '["a.scale.test"]'}
        cn = kw.pop('subject_cn', name)
        old_kw = dict(base, subject_cn=cn)
        c[name] = _cert(rows, name, 6, **old_kw)
        _cert(rows, name + '-new', days, **dict(base, subject_cn=cn, **kw))
        _cert(rows, name + '-client', 6, **dict(old_kw, source='acme', prv=None))
    for case, (subject, san) in {'null_subject': (None, None), 'null_san': ('CN=y', None)}.items():
        name = f'scale-sup-{case}'
        c[name] = _cert(rows, name, 6, caref=ok.refid, subject=subject, san_dns=san)
        _cert(rows, name + '-new', 300, caref=ok.refid, subject=subject, san_dns=san)
    # UCM's ACME client: an issued order with renewal on, or not
    for status, renew in (('issued', True), ('issued', False), ('pending', True)):
        cert = _cert(rows, f'scale-acme-{status}-{renew}', 10, caref=ok.refid, source='acme_client', prv='k')
        rows.add(AcmeClientOrder(domains='["scale.test"]', status=status, renewal_enabled=renew,
                                 certificate_id=cert.id))
    # delegated OCSP responders, bound by any key under the prefix (LIKE: '_' and case are loose)
    for key, prv in (('ocsp_responder_cert_{ca}', 'k'), ('ocsp_responder_cert_{ca}', None),
                     ('OCSP_RESPONDER_CERT_{ca}', 'k'), ('ocspXresponderXcertX{ca}', 'k'), ('ocsp_responder_{ca}', 'k')):
        cert = _cert(rows, f'scale-ocsp-{key}-{prv}', 10, caref=ok.refid, source='import', prv=prv)
        rows.add(SystemConfig(key=key.format(ca=uuid.uuid4().hex[:8]), value=str(cert.id)))
    rows.add(SystemConfig(key=f'ocsp_responder_cert_{uuid.uuid4().hex[:8]}', value=None))
    rows.add(SystemConfig(key=f'ocsp_responder_cert_{uuid.uuid4().hex[:8]}', value=' 1'))
    # rejected renewals: matched by LIKE '%"certificate_id": <id>,%' in the current lifetime
    for ca, tag in ((ok, 'ok'), (offline, 'off')):
        for case in ('auto', 'manual', 'last_key', 'upper', 'wildcard', 'prefix', 'before', 'spaced', 'none'):
            cert = _cert(rows, f'scale-decl-{tag}-{case}', 10, caref=ca.refid, prv='k')
            i = cert.id
            data = {
                'auto': {'certificate_id': i, 'trigger': 'auto'},
                'manual': {'certificate_id': i, 'trigger': 'manual'},
                'last_key': f'{{"trigger": "auto", "certificate_id": {i}}}',
                'upper': f'{{"CERTIFICATE_ID": {i}, "trigger": "auto"}}',
                'wildcard': f'{{"certificateXid": {i}, "trigger": "auto"}}',
                'prefix': f'{{"certificate_id": {i}0, "trigger": "auto"}}',
                'before': {'certificate_id': i, 'trigger': 'auto'},
                'spaced': f'{{"certificate_id":  {i}, "trigger": "auto"}}',
                'none': None,
            }[case]
            if data is not None:
                _reject(rows, data, created_days=400 if case == 'before' else 0)
        no_start = _cert(rows, f'scale-decl-{tag}-nostart', 10, caref=ca.refid, prv='k', valid_from=None)
        _reject(rows, {'certificate_id': no_start.id, 'trigger': 'auto'}, created_days=900)
    rows.add(ApprovalRequest(request_type='renewal', status='rejected', request_data=None))
    for status, rtype in (('pending', 'renewal'), ('rejected', 'certificate')):
        cert = _cert(rows, f'scale-decl-{status}-{rtype}', 10, caref=ok.refid, prv='k')
        rows.add(ApprovalRequest(request_type=rtype, status=status,
                                 request_data=json.dumps({'certificate_id': cert.id, 'trigger': 'auto'})))
    for name, kw in (('revoked', {'revoked': True}), ('archived', {'archived': True}), ('csr', {'crt': None}),
                     ('blank_crt', {'crt': ''}), ('expired', {'_days': -1}), ('no_end', {'_days': None})):
        kw = dict(kw)
        days = kw.pop('_days', 10)
        if days is None:
            row = _cert(rows, f'scale-misc-{name}', 10, caref=ok.refid, **kw)
            row.valid_to = None
        else:
            _cert(rows, f'scale-misc-{name}', days, caref=ok.refid, **kw)
    db.session.flush()
    return c


SCENARIOS = {
    'auto_off': {'auto_renewal_enabled': 'false', 'acme.client.renewal_enabled': None,
                 'ocsp_responder_auto_renew': None},
    'auto_manual': {'auto_renewal_enabled': 'true', 'auto_renewal_sources': '["manual"]', 'auto_renewal_days': '30',
                    'acme.client.renewal_enabled': 'false', 'ocsp_responder_auto_renew': 'false'},
    'auto_wide': {'auto_renewal_enabled': 'true', 'auto_renewal_sources': '["manual", "import", "acme_client"]',
                  'auto_renewal_days': '60', 'acme.client.renewal_enabled': 'TRUE',
                  'ocsp_responder_auto_renew': 'true'},
    'auto_none': {'auto_renewal_enabled': 'true', 'auto_renewal_sources': '[]', 'auto_renewal_days': '15'},
}


def _ids(conditions):
    return [r[0] for r in db.session.execute(
        select(Certificate.id).where(and_(*conditions)).order_by(Certificate.valid_to, Certificate.id))]


@pytest.mark.parametrize('scenario', sorted(SCENARIOS))
def test_the_four_kinds_list_the_rows_the_previous_conditions_listed(app, auth_client, rows, scenario):
    with app.app_context():
        for key, value in SCENARIOS[scenario].items():
            _set(key, value)
        db.session.commit()
        _varied(rows)
        db.session.commit()
        now = utc_now()
        dialect = db.engine.dialect.name
        config = da._renewal_config()
        queue = da.work_queue(db.session, 10_000, now=now, kinds=KINDS)
        listed = {}
        for item in queue['items']:
            listed.setdefault(item['kind'], []).append(item['id'])
        seen = 0
        for kind in KINDS:
            expected = _ids(_old_conditions(kind, now, config, dialect))
            seen += len(expected)
            filters = da.certificate_list_conditions(_Args(renewal=kind), dialect, now=now)
            assert _ids(filters) == expected, kind
            assert queue['counts'][kind] == len(expected), kind
            assert sorted(listed.get(kind, [])) == sorted(expected), kind
        assert seen > 20  # the data set reaches the kinds


class _Args(dict):
    def getlist(self, key):
        return [self[key]] if key in self else []


# ------------------------------------------------------------------------- plans and growth

def _statements(app, call):
    """(statement, parameters) of every SELECT that call() runs."""
    seen = []
    with app.app_context():
        engine = db.engine

    def listener(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith('SELECT'):
            seen.append((statement, parameters))

    event.listen(engine, 'before_cursor_execute', listener)
    try:
        call()
    finally:
        event.remove(engine, 'before_cursor_execute', listener)
    return seen


def _sqlite_violations(statement, parameters):
    """A full SCAN under a correlated subquery, or a correlated lookup of certificates not keyed by CN."""
    raw = db.session.connection().connection.driver_connection
    plan = raw.execute('EXPLAIN QUERY PLAN ' + statement, parameters or ()).fetchall()
    parent = {row[0]: row[1] for row in plan}
    detail = {row[0]: row[3] for row in plan}

    def correlated(node):
        while node in parent:
            node = parent[node]
            if detail.get(node, '').startswith('CORRELATED'):
                return True
        return False

    bad = []
    for node, step in detail.items():
        if not correlated(node):
            continue
        if step.startswith('SCAN '):
            bad.append(step)
        elif step.startswith('SEARCH certificates') and 'subject_cn=?' not in step:
            bad.append(step)
    return bad


def _pg_violations(statement, parameters):
    """A Seq Scan run per outer row (a SubPlan that is not hashed), or such a lookup of certificates not keyed by CN."""
    raw = db.session.connection().connection.driver_connection
    with raw.cursor() as cur:
        cur.execute('SET LOCAL enable_seqscan = off')
        cur.execute('EXPLAIN (FORMAT JSON) ' + statement, parameters)
        plan = cur.fetchone()[0]
        if isinstance(plan, str):
            plan = json.loads(plan)
    bad = []
    # A hashed subplan runs once; PostgreSQL names it so only where the expression uses it
    dumped = json.dumps(plan)

    def walk(node, per_row):
        name = str(node.get('Subplan Name', ''))
        per_row = per_row or (node.get('Parent Relationship') == 'SubPlan'
                              and not re.search(rf'hashed {re.escape(name)}\b', dumped)
                              and not name.startswith('hashed'))
        kind = node.get('Node Type', '')
        if per_row and kind == 'Seq Scan':
            bad.append(f"Seq Scan on {node.get('Relation Name')}")
        if per_row and node.get('Relation Name') == 'certificates' and 'Scan' in kind:
            keys = str(node.get('Index Cond', '')) + str(node.get('Recheck Cond', ''))
            if 'subject_cn' not in keys:
                bad.append(f"{kind} on certificates by {keys or 'nothing'}")
        for child in node.get('Plans', []):
            walk(child, per_row)

    walk(plan[0]['Plan'], False)
    return bad


@pytest.mark.parametrize('scenario', ['auto_off', 'auto_wide'])
def test_no_correlated_subquery_walks_a_table_for_each_certificate(app, auth_client, rows, scenario):
    with app.app_context():
        for key, value in SCENARIOS[scenario].items():
            _set(key, value)
        db.session.commit()
        if db.engine.dialect.name == 'postgresql':
            # PostgreSQL plans from statistics: give it a CA of some size, as an installation has
            _grow(rows, _ca(rows, 'plan-ca'), uuid.uuid4().hex[:6], 0, 2000)
            for table in ('certificates', 'acme_client_orders', 'system_config', 'approval_requests'):
                db.session.execute(text(f'ANALYZE {table}'))
            db.session.commit()
    calls = {
        'queue': lambda: auth_client.get('/api/v2/dashboard/queue'),
        **{f'list:{k}': (lambda k=k: auth_client.get('/api/v2/certificates', query_string={'renewal': k}))
           for k in KINDS},
    }
    with app.app_context():
        check = _pg_violations if db.engine.dialect.name == 'postgresql' else _sqlite_violations
        found = {}
        for name, call in calls.items():
            for statement, parameters in _statements(app, call):
                if 'certificates' not in statement:
                    continue
                bad = check(statement, parameters)
                db.session.rollback()
                if bad:
                    found.setdefault(name, set()).update(bad)
    assert not found, found


def _grow(rows, ca, tag, start, count):
    """count due certificates and as many rows in each table a renewal kind looks into."""
    now = utc_now()
    due = [dict(refid=str(uuid.uuid4()), descr=f'grow-{tag}-{i}', subject_cn=f'grow-{tag}-{i}', caref=ca.refid,
                crt=_PEM, prv='k', source=('manual', 'acme_client')[i % 2], revoked=False, archived=False,
                valid_from=now - timedelta(days=300), valid_to=now + timedelta(days=5 + i % 20))
           for i in range(start, start + count)]
    later = [dict(d, refid=str(uuid.uuid4()), descr=d['descr'] + '-later', subject_cn=d['subject_cn'] + '-later',
                  valid_to=now + timedelta(days=200)) for d in due]
    rows.bulk(Certificate, due)
    later_ids = rows.bulk(Certificate, later)
    rows.bulk(AcmeClientOrder, [dict(domains='[]', status='issued', renewal_enabled=True, certificate_id=i,
                                     created_at=now) for i in later_ids])
    rows.bulk(SystemConfig, [dict(key=f'ocsp_responder_cert_{tag}_{i}', value=str(i)) for i in later_ids])
    rows.bulk(ApprovalRequest, [dict(request_type='renewal', status='rejected', created_at=now,
                                     request_data=json.dumps({'certificate_id': i, 'trigger': 'auto'}))
                                for i in later_ids])
    db.session.commit()


def _steps(app):
    """SQLite virtual machine instructions (in thousands) the work queue costs."""
    counter = [0]
    with app.app_context():
        raw = db.session.connection().connection.driver_connection
        raw.set_progress_handler(lambda: counter.__setitem__(0, counter[0] + 1) or 0, 1000)
        try:
            da.work_queue(db.session, 50)
        finally:
            raw.set_progress_handler(None, 1000)
            db.session.rollback()
    return counter[0]


def test_the_queue_cost_grows_linearly_with_the_certificates(app, rows):
    with app.app_context():
        if db.engine.dialect.name != 'sqlite':
            pytest.skip('instruction counts are a SQLite measure; the plan test covers PostgreSQL')
        for key, value in SCENARIOS['auto_off'].items():
            _set(key, value)
        db.session.commit()
        ca = _ca(rows, 'grow-ca')
        db.session.commit()
        tag = uuid.uuid4().hex[:6]
    k = 300
    base = _steps(app)
    with app.app_context():
        _grow(rows, db.session.merge(ca), tag, 0, k)
    once = _steps(app)
    with app.app_context():
        _grow(rows, db.session.merge(ca), tag, k, k)
    twice = _steps(app)
    first, second = once - base, twice - once
    # Linear: the second batch costs what the first did; a per-row walk of a table makes it about three times as much
    assert second < 1.5 * first, (base, once, twice)
