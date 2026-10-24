"""Key store, zone index and audit sink of the DNS UPDATE listener.

Test names carry the invariant ID of the plan (K7, K8, K9, F1-F4, U3, N7,
N11, N12, N13): ``test_<ID>_<what>_pos`` and ``_neg``.
"""
import base64
import json
import logging
import uuid
from datetime import datetime

import dns.name
import pytest
from sqlalchemy import event

RAW_SECRET = bytes(range(1, 33))
B64_SECRET = base64.b64encode(RAW_SECRET).decode('ascii')


@pytest.fixture
def env(app):
    from models import db
    from models.acme_client_account import AcmeClientAccount
    from models.acme_dns_update import AcmeDnsUpdateKey
    from models.acme_models import AcmeEabCredential, AcmeDomain, DnsProvider

    with app.app_context():
        for model in (AcmeDnsUpdateKey, AcmeDomain):
            model.query.delete()
        db.session.commit()
        created = {'accounts': [], 'creds': [], 'acme_accounts': []}

        class Env:
            pass

        e = Env()
        e.db = db
        e.app = app

        def make_account(enabled=True):
            a = AcmeClientAccount(directory_url='https://u.example/dir', label='t',
                                  email='t@example.com', proxy_enabled=enabled)
            db.session.add(a)
            db.session.commit()
            created['accounts'].append(a.id)
            return a.id

        def make_key(account_id, name=None, status='active', algorithm='hmac-sha256',
                     eab_credential_id=None):
            k = AcmeDnsUpdateKey(acme_client_account_id=account_id,
                                 eab_credential_id=eab_credential_id,
                                 name=name or f'k{uuid.uuid4().hex[:8]}.example.',
                                 algorithm=algorithm, status=status)
            k.secret = B64_SECRET
            db.session.add(k)
            db.session.commit()
            return k

        def make_cred(status='used', used_by='acct-1'):
            c = AcmeEabCredential(kid=f'kid-{uuid.uuid4().hex[:8]}', status=status,
                                  used_by_account_id=used_by)
            c.hmac_key_b64 = B64_SECRET
            db.session.add(c)
            db.session.commit()
            created['creds'].append(c.id)
            return c.id

        def make_domain(name):
            p = DnsProvider.query.first()
            if p is None:
                p = DnsProvider(name='dnsupd-test-provider', provider_type='cloudflare')
                db.session.add(p)
                db.session.commit()
            db.session.add(AcmeDomain(domain=name, dns_provider_id=p.id))
            db.session.commit()

        class SqlCounter:
            def __init__(self):
                self.n = 0

            def __enter__(self):
                event.listen(db.engine, 'before_cursor_execute', self._hit)
                return self

            def __exit__(self, *a):
                event.remove(db.engine, 'before_cursor_execute', self._hit)

            def _hit(self, conn, cursor, statement, *args, **kw):
                self.last = statement
                self.n += 1

        e.make_account, e.make_key, e.make_cred = make_account, make_key, make_cred
        e.make_domain, e.SqlCounter = make_domain, SqlCounter
        yield e
        db.session.rollback()
        AcmeDnsUpdateKey.query.delete()
        AcmeDomain.query.delete()
        AcmeEabCredential.query.filter(AcmeEabCredential.id.in_(created['creds'])).delete(
            synchronize_session=False)
        AcmeClientAccount.query.filter(AcmeClientAccount.id.in_(created['accounts'])).delete(
            synchronize_session=False)
        db.session.commit()


def _n(text):
    return dns.name.from_text(text)


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


# ---------------------------------------------------------------- K7

def test_K7_valid_secret_gives_material_pos(env):
    from services.acme.dns_update.keys import KeyStore
    k = env.make_key(env.make_account())
    m = KeyStore().lookup(_n(k.name))
    assert m is not None and m.secret == RAW_SECRET and m.key_id == k.id


def test_K7_corrupt_secret_is_skipped_neg(env):
    from services.acme.dns_update.keys import KeyStore
    k = env.make_key(env.make_account())
    k._secret = 'gAAAAA-not-a-valid-fernet-token'
    env.db.session.commit()
    assert KeyStore().lookup(_n(k.name)) is None


def test_K7_non_base64_secret_is_skipped_neg(env):
    from services.acme.dns_update.keys import KeyStore
    k = env.make_key(env.make_account())
    k.secret = '!!!not base64!!!'
    env.db.session.commit()
    assert KeyStore().lookup(_n(k.name)) is None


def test_K7_disallowed_algorithm_is_skipped_neg(env):
    from services.acme.dns_update.keys import KeyStore
    k = env.make_key(env.make_account(), algorithm='hmac-md5.sig-alg.reg.int')
    assert KeyStore().lookup(_n(k.name)) is None


# ---------------------------------------------------------------- K8

def _scope_for(env, cred_id):
    from services.acme.dns_update.keys import KeyStore
    k = env.make_key(env.make_account(), eab_credential_id=cred_id)
    store = KeyStore()
    assert store.lookup(_n(k.name)) is not None  # still valid for TSIG
    return k, store.scope(k.id)


def test_K8_used_credential_scope_allows_pos(env):
    k, scope = _scope_for(env, env.make_cred('used', 'acct-1'))
    assert scope.allows(k.acme_client_account_id, 'acct-1')


def test_K8_other_account_denied_neg(env):
    k, scope = _scope_for(env, env.make_cred('used', 'acct-1'))
    assert not scope.allows(k.acme_client_account_id, 'acct-2')
    assert not scope.allows(k.acme_client_account_id + 1, 'acct-1')


def test_K8_unused_credential_matches_nothing_neg(env):
    k, scope = _scope_for(env, env.make_cred('active', None))
    assert scope.eab_bound and scope.eab_account_id is None
    assert not scope.allows(k.acme_client_account_id, 'acct-1')


def test_K8_active_credential_with_account_matches_nothing_neg(env):
    k, scope = _scope_for(env, env.make_cred('active', 'acct-1'))
    assert not scope.allows(k.acme_client_account_id, 'acct-1')


def test_K8_used_credential_without_account_matches_nothing_neg(env):
    k, scope = _scope_for(env, env.make_cred('used', None))
    assert not scope.allows(k.acme_client_account_id, 'acct-1')
    assert not scope.allows(k.acme_client_account_id, None)


def test_K8_deleted_credential_matches_nothing_neg(env):
    from models.acme_models import AcmeEabCredential
    from sqlalchemy import text
    cred_id = env.make_cred('used', 'acct-1')
    k = env.make_key(env.make_account(), eab_credential_id=cred_id)
    env.db.session.execute(text('PRAGMA foreign_keys=OFF'))
    env.db.session.execute(text('DELETE FROM acme_eab_credentials WHERE id=:i'), {'i': cred_id})
    env.db.session.commit()
    from services.acme.dns_update.keys import KeyStore
    store = KeyStore()
    assert store.lookup(_n(k.name)) is not None
    scope = store.scope(k.id)
    assert not scope.allows(k.acme_client_account_id, 'acct-1')
    assert AcmeEabCredential.query.get(cred_id) is None


def test_K8_row_without_account_never_allowed_neg(env):
    k, scope = _scope_for(env, env.make_cred('used', 'acct-1'))
    assert not scope.allows(k.acme_client_account_id, None)
    assert not scope.allows(k.acme_client_account_id, '')
    assert not scope.allows(None, 'acct-1')


def test_K8_unbound_key_allows_any_client_account_of_proxy_account_pos(env):
    from services.acme.dns_update.keys import KeyScope
    s = KeyScope(5, False, None)
    assert s.allows(5, None) and s.allows(5, 'x')
    assert not s.allows(6, 'x')


# ---------------------------------------------------------------- K9

def test_K9_active_key_of_enabled_account_pos(env):
    from services.acme.dns_update.keys import KeyStore
    k = env.make_key(env.make_account(True))
    assert KeyStore().lookup(_n(k.name)) is not None


def test_K9_proxy_disabled_account_neg(env):
    from services.acme.dns_update.keys import KeyStore
    k = env.make_key(env.make_account(False))
    assert KeyStore().lookup(_n(k.name)) is None


def test_K9_deleted_account_row_neg(env):
    from services.acme.dns_update.keys import KeyStore
    from sqlalchemy import text
    acc = env.make_account(True)
    k = env.make_key(acc)
    env.db.session.execute(text('DELETE FROM acme_client_accounts WHERE id=:i'), {'i': acc})
    env.db.session.commit()
    assert KeyStore().lookup(_n(k.name)) is None


def test_K9_revoked_key_neg(env):
    from services.acme.dns_update.keys import KeyStore
    k = env.make_key(env.make_account(True), status='revoked')
    assert KeyStore().lookup(_n(k.name)) is None


def test_S13_lookup_is_case_insensitive_pos(env):
    from services.acme.dns_update.keys import KeyStore
    k = env.make_key(env.make_account(), name='key1.example.')
    assert KeyStore().lookup(_n('KEY1.Example.')).key_id == k.id


def test_S13_other_name_not_found_neg(env):
    from services.acme.dns_update.keys import KeyStore
    env.make_key(env.make_account(), name='key1.example.')
    assert KeyStore().lookup(_n('key2.example.')) is None


# ---------------------------------------------------------------- cache

def test_F1_warm_cache_runs_no_sql_pos(env):
    from services.acme.dns_update.keys import KeyStore
    from services.acme.dns_update.zones import ZoneIndex
    k = env.make_key(env.make_account(), name='warm.example.')
    env.make_domain('example.com')
    kid = k.id
    store, zi = KeyStore(), ZoneIndex()
    assert store.lookup(_n(k.name)) and zi.is_authoritative(_n('example.com.'))
    with env.SqlCounter() as c:
        for i in range(1000):
            store.lookup(_n('warm.example.'))
            store.lookup(_n(f'unknown{i}.example.'))
            zi.is_authoritative(_n('example.com.'))
            zi.is_authoritative(_n(f'x{i}.example.com.'))
        store.scope(kid)
    assert c.n == 0, c.last


def test_F1_cold_cache_runs_sql_neg(env):
    from services.acme.dns_update.keys import KeyStore
    env.make_key(env.make_account(), name='cold.example.')
    with env.SqlCounter() as c:
        KeyStore().lookup(_n('cold.example.'))
    assert c.n > 0


def test_F2_invalidate_reloads_pos(env):
    from services.acme.dns_update.keys import KeyStore
    store = KeyStore()
    assert store.lookup(_n('late.example.')) is None
    env.make_key(env.make_account(), name='late.example.')
    assert store.lookup(_n('late.example.')) is None  # still cached
    store.invalidate()
    assert store.lookup(_n('late.example.')) is not None


def test_F2_revocation_visible_after_invalidate_pos(env):
    from services.acme.dns_update import keys as keys_mod
    k = env.make_key(env.make_account(), name='rev.example.')
    store = keys_mod.KeyStore()
    assert store.lookup(_n(k.name)) is not None
    k.status = 'revoked'
    env.db.session.commit()
    assert store.lookup(_n(k.name)) is not None  # not yet
    store.invalidate()
    assert store.lookup(_n(k.name)) is None
    assert callable(keys_mod.invalidate_keys)


def test_F2_invalidate_keys_helper_resets_singleton_pos(env):
    from services.acme.dns_update.keys import key_store, invalidate_keys
    k = env.make_key(env.make_account(), name='single.example.')
    key_store.invalidate()
    assert key_store.lookup(_n(k.name)) is not None
    k.status = 'revoked'
    env.db.session.commit()
    invalidate_keys()
    assert key_store.lookup(_n(k.name)) is None
    key_store.invalidate()


def _restore_purge(name):
    # Only the registered purge: invalidate_after_restore() would also revoke
    # every session of the shared test database.
    from services.backup.restore.invalidate import CACHE_PURGES
    return dict(CACHE_PURGES).get(name)


def test_F2_restore_drops_the_listener_caches_pos(env):
    """A key or zone that a restore removed stops working at once (no 30 s wait)."""
    from models.acme_dns_update import AcmeDnsUpdateKey
    from models.acme_models import AcmeDomain
    from services.acme.dns_update.keys import key_store
    from services.acme.dns_update.zones import zone_index
    k = env.make_key(env.make_account(), name='restored-away.example.')
    env.make_domain('restored-away.example')
    key_store.invalidate()
    zone_index.invalidate()
    assert key_store.lookup(_n(k.name)) is not None
    assert zone_index.is_authoritative(_n('restored-away.example.'))
    # What the restore does to the rows: replaced, here simply gone.
    AcmeDnsUpdateKey.query.filter_by(name=k.name).delete()
    AcmeDomain.query.filter_by(domain='restored-away.example').delete()
    env.db.session.commit()
    _restore_purge('acme_dns_update')()
    assert key_store.lookup(_n(k.name)) is None
    assert not zone_index.is_authoritative(_n('restored-away.example.'))


def test_F2_without_the_restore_purge_the_key_cache_survives_neg(env):
    """The purge is what drops the key: without it the warm cache still answers."""
    from models.acme_dns_update import AcmeDnsUpdateKey
    from services.acme.dns_update.keys import key_store
    assert _restore_purge('acme_dns_update') is not None
    k = env.make_key(env.make_account(), name='survives.example.')
    key_store.invalidate()
    assert key_store.lookup(_n(k.name)) is not None
    AcmeDnsUpdateKey.query.filter_by(name=k.name).delete()
    env.db.session.commit()
    assert key_store.lookup(_n(k.name)) is not None  # stale until max age
    key_store.invalidate()


def test_F2_revocation_visible_after_max_age_pos(env):
    from services.acme.dns_update.keys import KeyStore
    clock = Clock()
    k = env.make_key(env.make_account(), name='aged.example.')
    store = KeyStore(max_age_s=30.0, clock=clock)
    assert store.lookup(_n(k.name)) is not None
    k.status = 'revoked'
    env.db.session.commit()
    clock.t += 29
    assert store.lookup(_n(k.name)) is not None
    clock.t += 2
    assert store.lookup(_n(k.name)) is None


def test_F3_db_error_keeps_previous_cache_pos(env, monkeypatch):
    from services.acme.dns_update.keys import KeyStore
    clock = Clock()
    k = env.make_key(env.make_account(), name='keep.example.')
    store = KeyStore(max_age_s=30.0, clock=clock)
    assert store.lookup(_n(k.name)) is not None

    def boom():
        raise RuntimeError('db down')
    monkeypatch.setattr(KeyStore, '_load', staticmethod(boom))
    clock.t += 100
    assert store.lookup(_n(k.name)) is not None


def test_F3_db_error_on_first_load_finds_nothing_neg(env, monkeypatch):
    from services.acme.dns_update.keys import KeyStore

    def boom():
        raise RuntimeError('db down')
    monkeypatch.setattr(KeyStore, '_load', staticmethod(boom))
    assert KeyStore().lookup(_n('any.example.')) is None


def test_F4_touch_sets_last_used_and_throttles_pos(env):
    from models.acme_dns_update import AcmeDnsUpdateKey
    from services.acme.dns_update.keys import KeyStore
    clock = Clock()
    k = env.make_key(env.make_account())
    store = KeyStore(clock=clock)
    when = datetime(2026, 1, 2, 3, 4, 5)
    store.touch(k.id, when)
    env.db.session.expire_all()
    assert AcmeDnsUpdateKey.query.get(k.id).last_used_at == when
    clock.t += 59
    with env.SqlCounter() as c:
        store.touch(k.id, datetime(2026, 1, 2, 3, 5, 5))
    assert c.n == 0
    clock.t += 2
    with env.SqlCounter() as c:
        store.touch(k.id, datetime(2026, 1, 2, 3, 6, 5))
    assert c.n > 0


def test_F4_touch_never_raises_neg(env, monkeypatch):
    from services.acme.dns_update.keys import KeyStore
    store = KeyStore()
    with monkeypatch.context() as m:
        m.setattr(env.db.session, 'commit',
                  lambda: (_ for _ in ()).throw(RuntimeError('x')))
        store.touch(1, datetime(2026, 1, 1))  # must not raise


# ---------------------------------------------------------------- U3

@pytest.fixture
def zone_env(env):
    from services.acme.dns_update.zones import ZoneIndex
    env.make_domain('example.com')
    env.make_domain('*.corp.example.net')
    return ZoneIndex()


@pytest.mark.parametrize('name', ['example.com.', 'corp.example.net.', 'example.net.',
                                  'EXAMPLE.com.'])
def test_U3_authoritative_pos(zone_env, name):
    assert zone_env.is_authoritative(_n(name))


@pytest.mark.parametrize('name', ['foo.example.com.', 'other.org.', 'net.', 'com.', '.',
                                  'a.corp.example.net.'])
def test_U3_not_authoritative_neg(zone_env, name):
    assert not zone_env.is_authoritative(_n(name))


def test_U3_zones_are_normalized_pos(zone_env):
    assert zone_env.zones() == frozenset({_n('example.com.'), _n('corp.example.net.')})


def test_U3_invalidate_reloads_pos(zone_env, env):
    assert not zone_env.is_authoritative(_n('new.org.'))
    env.make_domain('new.org')
    assert not zone_env.is_authoritative(_n('new.org.'))
    zone_env.invalidate()
    assert zone_env.is_authoritative(_n('new.org.'))


def test_U3_db_error_keeps_previous_pos(zone_env, monkeypatch):
    from services.acme.dns_update.zones import ZoneIndex
    clock = Clock()
    zi = ZoneIndex(clock=clock)
    assert zi.is_authoritative(_n('example.com.'))

    def boom():
        raise RuntimeError('db')
    monkeypatch.setattr(ZoneIndex, '_load', staticmethod(boom))
    clock.t += 100
    assert zi.is_authoritative(_n('example.com.'))


# ---------------------------------------------------------------- audit

@pytest.fixture
def audit_env(env):
    from models.audit_log import AuditLog
    env.AuditLog = AuditLog
    AuditLog.query.filter(AuditLog.resource_type == 'acme_dns_update').delete()
    env.db.session.commit()
    yield env


def _rows(env, action=None):
    env.db.session.expire_all()
    q = env.AuditLog.query.filter(env.AuditLog.resource_type == 'acme_dns_update')
    if action:
        q = q.filter(env.AuditLog.action == action)
    return q.all()


def _rec(sink, ip, reason='badkey', keyname=None, details=None, action='acme.dns_update.rejected'):
    return sink.audit_limited(action=action, reason=reason, peer_ip=ip, keyname=keyname,
                       success=False, details=details or {'reason': reason})


def test_N12_first_call_writes_row_pos(audit_env):
    from services.acme.dns_update.audit import AuditSink
    assert _rec(AuditSink(clock=Clock()), '192.0.2.1') is True
    assert len(_rows(audit_env)) == 1


def test_N12_flood_is_bounded_neg(audit_env):
    from services.acme.dns_update.audit import AuditSink
    clock = Clock()
    sink = AuditSink(clock=clock)
    written = sum(_rec(sink, f'10.{i // 250}.{i % 250}.{i % 7}') for i in range(1000))
    assert written == 20
    assert len(_rows(audit_env, 'acme.dns_update.rejected')) == 20
    assert len(_rows(audit_env, 'acme.dns_update.suppressed')) == 0
    clock.t += 61
    assert _rec(sink, '203.0.113.9') is True
    summary = _rows(audit_env, 'acme.dns_update.suppressed')
    assert len(summary) == 1
    d = json.loads(summary[0].details)
    assert d == {'reason': 'badkey', 'dropped': 980}
    assert len(_rows(audit_env)) == 22
    # a second window with no drops writes no second summary
    clock.t += 61
    _rec(sink, '203.0.113.10')
    assert len(_rows(audit_env, 'acme.dns_update.suppressed')) == 1


def test_N12_reasons_have_separate_limits_pos(audit_env):
    from services.acme.dns_update.audit import AuditSink
    sink = AuditSink(clock=Clock())
    for i in range(30):
        _rec(sink, f'10.0.0.{i}', reason='badkey')
    assert _rec(sink, '10.9.9.9', reason='badmac') is True


def test_N7_one_ip_one_row_neg(audit_env):
    from services.acme.dns_update.audit import AuditSink
    clock = Clock()
    sink = AuditSink(clock=clock)
    results = [_rec(sink, '192.0.2.7') for _ in range(100)]
    assert results.count(True) == 1
    assert len(_rows(audit_env)) == 1
    clock.t += 61
    assert _rec(sink, '192.0.2.7') is True


def test_N7_ip_table_is_bounded_neg(audit_env):
    from services.acme.dns_update.audit import AuditSink
    sink = AuditSink(max_ips=10, global_per_reason_per_minute=10**6, clock=Clock())
    for i in range(100):
        _rec(sink, f'10.0.0.{i}')
    assert len(sink._ip_hits) <= 10


def test_N13_row_has_peer_ip_and_username_pos(audit_env):
    from services.acme.dns_update.audit import AuditSink
    sink = AuditSink(clock=Clock())
    _rec(sink, '192.0.2.50', keyname='key1.example.')
    _rec(sink, '192.0.2.51', keyname=None)
    rows = {r.ip_address: r for r in _rows(audit_env)}
    assert rows['192.0.2.50'].username == 'dns-update:key1.example.'
    assert rows['192.0.2.50'].resource_name == 'key1.example.'
    assert rows['192.0.2.51'].username == 'dns-update:unauthenticated'
    assert rows['192.0.2.51'].resource_name == 'unauthenticated'
    assert rows['192.0.2.51'].success is False


def test_N13_reason_is_in_details_pos(audit_env):
    # The refusal reason is what an operator needs first (E2E finding).
    from services.acme.dns_update.audit import AuditSink
    sink = AuditSink(clock=Clock())
    _rec(sink, '192.0.2.70', keyname='key1.example.', reason='value_mismatch',
         details={'zone': 'example.com.'})
    d = json.loads(_rows(audit_env)[0].details)
    assert d['reason'] == 'value_mismatch' and d['zone'] == 'example.com.'


def test_N13_authenticated_row_has_no_rate_limit_reason_neg(audit_env):
    from services.acme.dns_update.audit import AuditSink
    sink = AuditSink(clock=Clock())
    sink.audit_authenticated(action='acme.dns_update.accepted', peer_ip='192.0.2.71',
                              keyname='key1.example.', success=True, details={'adds': 1})
    d = json.loads(_rows(audit_env)[0].details)
    assert 'reason' not in d and d['adds'] == 1


def test_N13_attacker_strings_are_sanitized_neg(audit_env):
    from services.acme.dns_update.audit import AuditSink
    evil = ('ab\r\n\x00\x7fé中' + 'x' * 400)
    sink = AuditSink(clock=Clock())
    _rec(sink, '192.0.2.60', keyname=evil, details={'qname': evil, 'n': 3, 'l': [evil]})
    row = _rows(audit_env)[0]
    expected = ('ab' + '??????' + 'x' * 400)[:255]
    assert row.resource_name == expected
    assert row.username == 'dns-update:' + expected
    d = json.loads(row.details)
    assert d['qname'] == expected and d['l'] == [expected] and d['n'] == 3


def test_N13_record_never_raises_neg(audit_env, monkeypatch):
    from services.acme.dns_update.audit import AuditSink
    from services.audit import AuditService
    monkeypatch.setattr(AuditService, 'log_action',
                        staticmethod(lambda **kw: (_ for _ in ()).throw(RuntimeError('x'))))
    assert _rec(AuditSink(clock=Clock()), '192.0.2.70') is not None


def test_N13_log_action_without_ip_keeps_old_behaviour_pos(audit_env, app):
    from services.audit import AuditService
    row = AuditService.log_action(action='dnsupd.test', resource_type='acme_dns_update',
                                  username='u')
    assert row.ip_address is None
    with app.test_request_context('/', environ_base={'REMOTE_ADDR': '198.51.100.4'}):
        row = AuditService.log_action(action='dnsupd.test', resource_type='acme_dns_update',
                                      username='u')
        assert row.ip_address == '198.51.100.4'
        row = AuditService.log_action(action='dnsupd.test', resource_type='acme_dns_update',
                                      username='u', ip_address='192.0.2.99')
        assert row.ip_address == '192.0.2.99'


# ---------------------------------------------------------------- N11

def test_N11_no_secret_in_logs_neg(audit_env, caplog):
    from services.acme.dns_update.keys import KeyStore
    from services.acme.dns_update.audit import AuditSink
    from services.acme.dns_update.zones import ZoneIndex
    caplog.set_level(logging.DEBUG)
    good = audit_env.make_key(audit_env.make_account())
    bad = audit_env.make_key(audit_env.make_account())
    bad._secret = 'gAAAAA-broken'
    audit_env.db.session.commit()
    store = KeyStore()
    store.lookup(_n(good.name))
    store.lookup(_n(bad.name))
    store.touch(good.id, datetime(2026, 1, 1))
    ZoneIndex().zones()
    _rec(AuditSink(clock=Clock()), '192.0.2.80', keyname=good.name)
    text = caplog.text
    assert 'skipped' in text  # the warning was logged, with the name only
    assert bad.name in text
    assert B64_SECRET not in text
    assert RAW_SECRET.hex() not in text
    assert repr(RAW_SECRET) not in text
    assert repr(store.lookup(_n(good.name))).find(B64_SECRET) == -1
