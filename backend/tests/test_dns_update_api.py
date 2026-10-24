"""REST API of the DNS UPDATE TSIG keys, listener port and cache hooks.

Test names carry the invariant ID of the plan (K1, K3, K4, K5, N1, N2):
``test_<ID>_<what>_pos`` and ``_neg``.
"""
import base64
import json
import logging
import uuid

import dns.name
import pytest

from models import db, AcmeClientAccount, AcmeEabCredential, AcmeDomain, DnsProvider, SystemConfig
from models.acme_dns_update import AcmeDnsUpdateKey

PORT_KEY = 'acme.proxy.dns_update_port'
TLS_KEY = 'acme.client.tls_alpn_port'


@pytest.fixture(autouse=True)
def _fresh_port_warnings():
    """The port warnings are logged once per value: each test starts clean."""
    from services.acme.dns_update import status
    status._warned.clear()
    yield
    status._warned.clear()


@pytest.fixture
def env(app):
    from services.acme.dns_update.keys import key_store
    from services.acme.dns_update.zones import zone_index
    created = {'accounts': [], 'creds': []}
    with app.app_context():
        AcmeDnsUpdateKey.query.delete()
        AcmeDomain.query.delete()
        SystemConfig.query.filter(SystemConfig.key.in_([PORT_KEY, TLS_KEY])).delete(
            synchronize_session=False)
        db.session.commit()
        key_store.invalidate()
        zone_index.invalidate()

        class Env:
            pass

        e = Env()
        e.app = app

        def make_account(slug=None, enabled=True):
            a = AcmeClientAccount(directory_url='https://u.example/dir', label='t',
                                  email='t@example.com', proxy_enabled=enabled,
                                  proxy_slug=slug)
            db.session.add(a)
            db.session.commit()
            created['accounts'].append(a.id)
            return a.id

        def make_cred(status='active'):
            c = AcmeEabCredential(kid=f'kid-{uuid.uuid4().hex[:8]}', status=status)
            c.hmac_key_b64 = base64.b64encode(b'x' * 32).decode()
            db.session.add(c)
            db.session.commit()
            created['creds'].append(c.id)
            return c.id

        e.make_account, e.make_cred = make_account, make_cred
        yield e
        db.session.rollback()
        AcmeDnsUpdateKey.query.delete()
        AcmeDomain.query.delete()
        AcmeEabCredential.query.filter(AcmeEabCredential.id.in_(created['creds'])).delete(
            synchronize_session=False)
        AcmeClientAccount.query.filter(AcmeClientAccount.id.in_(created['accounts'])).delete(
            synchronize_session=False)
        SystemConfig.query.filter(SystemConfig.key.in_([PORT_KEY, TLS_KEY])).delete(
            synchronize_session=False)
        db.session.commit()
        key_store.invalidate()
        zone_index.invalidate()


def _url(account_id, key_id=None):
    base = f'/api/v2/acme/client/accounts/{account_id}/dns-update-keys'
    return base if key_id is None else f'{base}/{key_id}'


def _post(client, account_id, body=None):
    return client.post(_url(account_id), data=json.dumps(body or {}),
                       content_type='application/json')


def _data(resp):
    return resp.get_json()['data']


def _lookup(app, name):
    from services.acme.dns_update.keys import key_store
    with app.app_context():
        return key_store.lookup(dns.name.from_text(name))


# ------------------------------------------------------------------- K1

@pytest.mark.parametrize('algorithm,size', [
    ('hmac-sha256', 32), ('hmac-sha384', 48), ('hmac-sha512', 64)])
def test_K1_secret_length_follows_algorithm_pos(auth_client, env, algorithm, size):
    acct = env.make_account()
    r = _post(auth_client, acct, {'algorithm': algorithm})
    assert r.status_code == 201
    assert len(base64.b64decode(_data(r)['secret'], validate=True)) == size


def test_K1_secrets_are_not_reused_neg(auth_client, env):
    acct = env.make_account()
    secrets_seen = set()
    for _ in range(20):
        r = _post(auth_client, acct)
        assert r.status_code == 201
        secrets_seen.add(_data(r)['secret'])
    assert len(secrets_seen) == 20


# ------------------------------------------------------------------- K3

def test_K3_post_returns_secret_pos(auth_client, env):
    acct = env.make_account()
    r = _post(auth_client, acct)
    d = _data(r)
    assert r.status_code == 201
    assert d['secret'] and d['algorithm'] == 'hmac-sha256' and d['status'] == 'active'
    with env.app.app_context():
        assert db.session.get(AcmeDnsUpdateKey, d['id']).secret == d['secret']


def test_K3_list_never_returns_secret_neg(auth_client, env):
    acct = env.make_account()
    secret = _data(_post(auth_client, acct))['secret']
    r = auth_client.get(_url(acct))
    assert r.status_code == 200
    items = _data(r)
    assert len(items) == 1
    assert 'secret' not in items[0]
    assert secret not in r.get_data(as_text=True)


def test_K3_list_unknown_account_neg(auth_client, env):
    assert auth_client.get(_url(99999999)).status_code == 404
    assert _post(auth_client, 99999999).status_code == 404


# ------------------------------------------------------------------- K4

@pytest.mark.parametrize('algorithm', ['hmac-sha256', 'HMAC-SHA384', 'hmac-sha512'])
def test_K4_allowed_algorithms_pos(auth_client, env, algorithm):
    r = _post(auth_client, env.make_account(), {'algorithm': algorithm})
    assert r.status_code == 201
    assert _data(r)['algorithm'] == algorithm.lower()


@pytest.mark.parametrize('algorithm', [
    'hmac-md5', 'hmac-md5.sig-alg.reg.int', 'hmac-sha1', 'hmac-sha224',
    'hmac-sha256-128', 'gss-tsig', '', 5])
def test_K4_other_algorithms_neg(auth_client, env, algorithm):
    acct = env.make_account()
    assert _post(auth_client, acct, {'algorithm': algorithm}).status_code == 400
    with env.app.app_context():
        assert AcmeDnsUpdateKey.query.count() == 0


# ------------------------------------------------------------------- K5

def test_K5_named_key_is_normalized_pos(auth_client, env):
    r = _post(auth_client, env.make_account(), {'name': 'My-Key.Example'})
    assert r.status_code == 201
    assert _data(r)['name'] == 'my-key.example.'


@pytest.mark.parametrize('name', ['a' * 64 + '.example.', 'a..b', '.'])
def test_K5_invalid_name_neg(auth_client, env, name):
    assert _post(auth_client, env.make_account(), {'name': name}).status_code == 400


def test_K5_duplicate_name_case_insensitive_neg(auth_client, env):
    acct = env.make_account()
    assert _post(auth_client, acct, {'name': 'key.example.'}).status_code == 201
    assert _post(auth_client, acct, {'name': 'Key.Example.'}).status_code == 409
    # Other account: the name is global.
    assert _post(auth_client, env.make_account(), {'name': 'KEY.example'}).status_code == 409


def test_K5_generated_name_uses_slug_pos(auth_client, env):
    r = _post(auth_client, env.make_account(slug='myproxy'))
    name = _data(r)['name']
    assert name.startswith('myproxy-') and name.endswith('.')
    assert len(name) == len('myproxy-') + 8 + 1


def test_K5_generated_name_without_slug_pos(auth_client, env):
    acct = env.make_account(slug=None)
    assert _data(_post(auth_client, acct))['name'].startswith(f'proxy{acct}-')


def test_K5_notes_too_long_neg(auth_client, env):
    acct = env.make_account()
    assert _post(auth_client, acct, {'notes': 'n' * 1000}).status_code == 201
    assert _post(auth_client, acct, {'notes': 'n' * 1001}).status_code == 400


# ------------------------------------------------------------------- EAB link

def test_eab_link_active_and_used_pos(auth_client, env):
    acct = env.make_account()
    for status in ('active', 'used'):
        cred = env.make_cred(status)
        r = _post(auth_client, acct, {'eab_credential_id': cred})
        assert r.status_code == 201
        assert _data(r)['eab_credential_id'] == cred


def test_eab_link_nonexistent_neg(auth_client, env):
    assert _post(auth_client, env.make_account(),
                 {'eab_credential_id': 99999999}).status_code == 400


def test_eab_link_revoked_neg(auth_client, env):
    cred = env.make_cred('revoked')
    assert _post(auth_client, env.make_account(),
                 {'eab_credential_id': cred}).status_code == 400


def test_eab_link_not_an_integer_neg(auth_client, env):
    assert _post(auth_client, env.make_account(),
                 {'eab_credential_id': 'abc'}).status_code == 400


# ------------------------------------------------------------------- permissions

def test_permissions_viewer_cannot_list_neg(viewer_client, auth_client, env):
    # Viewers have no read:acme (same as the EAB and ACME settings routes).
    acct = env.make_account()
    assert viewer_client.get(_url(acct)).status_code == 403
    assert auth_client.get(_url(acct)).status_code == 200


def test_permissions_viewer_cannot_write_neg(viewer_client, auth_client, env):
    acct = env.make_account()
    key_id = _data(_post(auth_client, acct))['id']
    assert _post(viewer_client, acct).status_code == 403
    assert viewer_client.delete(_url(acct, key_id)).status_code == 403
    with env.app.app_context():
        assert db.session.get(AcmeDnsUpdateKey, key_id).status == 'active'


# ------------------------------------------------------------------- DELETE

def test_delete_revokes_then_deletes_pos(auth_client, env):
    acct = env.make_account()
    key_id = _data(_post(auth_client, acct))['id']
    r = auth_client.delete(_url(acct, key_id))
    assert r.status_code == 200
    assert _data(r)['status'] == 'revoked' and _data(r)['revoked_at']
    assert auth_client.delete(_url(acct, key_id)).status_code == 204
    with env.app.app_context():
        assert db.session.get(AcmeDnsUpdateKey, key_id) is None


def test_delete_other_account_key_neg(auth_client, env):
    acct, other = env.make_account(), env.make_account()
    key_id = _data(_post(auth_client, acct))['id']
    assert auth_client.delete(_url(other, key_id)).status_code == 404
    assert auth_client.delete(_url(acct, 99999999)).status_code == 404
    with env.app.app_context():
        assert db.session.get(AcmeDnsUpdateKey, key_id).status == 'active'


# ------------------------------------------------------------------- invalidation

def test_invalidation_post_makes_key_visible_pos(auth_client, env):
    acct = env.make_account()
    assert _lookup(env.app, 'late.example.') is None  # primes the cache
    assert _post(auth_client, acct, {'name': 'late.example.'}).status_code == 201
    assert _lookup(env.app, 'late.example.') is not None


def test_invalidation_revoke_hides_key_at_once_pos(auth_client, env):
    acct = env.make_account()
    d = _data(_post(auth_client, acct, {'name': 'gone.example.'}))
    assert _lookup(env.app, 'gone.example.') is not None
    assert auth_client.delete(_url(acct, d['id'])).status_code == 200
    assert _lookup(env.app, 'gone.example.') is None


def test_invalidation_without_delete_key_stays_neg(auth_client, env):
    acct = env.make_account()
    _post(auth_client, acct, {'name': 'stay.example.'})
    assert _lookup(env.app, 'stay.example.') is not None
    other = env.make_account()
    d = _data(_post(auth_client, other))
    auth_client.delete(_url(other, d['id']))
    assert _lookup(env.app, 'stay.example.') is not None


def test_invalidation_proxy_disabled_hides_key_pos(auth_client, env):
    acct = env.make_account(slug='pdis')
    _post(auth_client, acct, {'name': 'pd.example.'})
    assert _lookup(env.app, 'pd.example.') is not None
    r = auth_client.patch(f'/api/v2/acme/client/accounts/{acct}',
                          data=json.dumps({'proxy_enabled': False}),
                          content_type='application/json')
    assert r.status_code == 200
    assert _lookup(env.app, 'pd.example.') is None


def test_invalidation_account_delete_hides_key_pos(auth_client, env):
    acct = env.make_account()
    _post(auth_client, acct, {'name': 'ad.example.'})
    assert _lookup(env.app, 'ad.example.') is not None
    assert auth_client.delete(f'/api/v2/acme/client/accounts/{acct}').status_code == 200
    assert _lookup(env.app, 'ad.example.') is None


def test_invalidation_eab_delete_hides_key_pos(auth_client, env):
    acct = env.make_account()
    cred = env.make_cred('used')
    _post(auth_client, acct, {'name': 'eab.example.', 'eab_credential_id': cred})
    assert _lookup(env.app, 'eab.example.') is not None
    assert auth_client.delete(f'/api/v2/acme/eab-credentials/{cred}').status_code == 204
    assert _lookup(env.app, 'eab.example.') is None


def test_invalidation_acme_domain_api_pos(auth_client, env):
    from services.acme.dns_update.zones import zone_index
    with env.app.app_context():
        p = DnsProvider(name=f'dnsupd-{uuid.uuid4().hex[:6]}', provider_type='cloudflare')
        db.session.add(p)
        db.session.commit()
        pid = p.id
    zone = dns.name.from_text('zone-inv.example.com.')
    try:
        with env.app.app_context():
            assert not zone_index.is_authoritative(zone)
        r = auth_client.post('/api/v2/acme/domains',
                             data=json.dumps({'domain': 'zone-inv.example.com',
                                              'dns_provider_id': pid}),
                             content_type='application/json')
        assert r.status_code == 201
        dom_id = _data(r)['id']
        with env.app.app_context():
            assert zone_index.is_authoritative(zone)
        assert auth_client.delete(f'/api/v2/acme/domains/{dom_id}').status_code == 200
        with env.app.app_context():
            assert not zone_index.is_authoritative(zone)
    finally:
        with env.app.app_context():
            AcmeDomain.query.delete()
            DnsProvider.query.filter_by(id=pid).delete()
            db.session.commit()


# ------------------------------------------------------------------- N1

def test_N1_env_port_pos(app, env, monkeypatch):
    from services.acme.dns_update.status import get_dns_update_port
    monkeypatch.setenv('UCM_DNS_UPDATE_PORT', '8053')
    with app.app_context():
        assert get_dns_update_port() == 8053


def test_N1_env_invalid_is_zero_with_warning_neg(app, env, monkeypatch, caplog):
    from services.acme.dns_update.status import get_dns_update_port
    monkeypatch.setenv('UCM_DNS_UPDATE_PORT', 'abc')
    with app.app_context(), caplog.at_level(logging.WARNING):
        assert get_dns_update_port() == 0
    assert any('UCM_DNS_UPDATE_PORT' in r.getMessage() for r in caplog.records)


def test_N1_db_port_pos(app, env, monkeypatch):
    from services.acme.dns_update.status import get_dns_update_port
    monkeypatch.delenv('UCM_DNS_UPDATE_PORT', raising=False)
    with app.app_context():
        db.session.add(SystemConfig(key=PORT_KEY, value='8053'))
        db.session.commit()
        assert get_dns_update_port() == 8053


def test_N1_nothing_or_bad_db_value_is_zero_neg(app, env, monkeypatch):
    from services.acme.dns_update.status import get_dns_update_port
    monkeypatch.delenv('UCM_DNS_UPDATE_PORT', raising=False)
    with app.app_context():
        assert get_dns_update_port() == 0
        db.session.add(SystemConfig(key=PORT_KEY, value='70000'))
        db.session.commit()
        assert get_dns_update_port() == 0


def test_N1_listening_flag_pos():
    from services.acme.dns_update import status
    status.set_listening(True)
    try:
        assert status.is_listening() is True
    finally:
        status.set_listening(False)
    assert status.is_listening() is False


# ------------------------------------------------------------------- N2

def _patch_settings(client, body):
    return client.patch('/api/v2/acme/client/settings', data=json.dumps(body),
                        content_type='application/json')


def test_N2_valid_ports_pos(auth_client, env, monkeypatch):
    monkeypatch.delenv('UCM_DNS_UPDATE_PORT', raising=False)
    r = _patch_settings(auth_client, {'dns_update_port': 8053})
    assert r.status_code == 200
    assert 'restart' in r.get_json()['message']
    g = _data(auth_client.get('/api/v2/acme/client/settings'))
    assert g['dns_update_port'] == 8053
    assert g['dns_update_port_env'] is None
    assert g['dns_update_listening'] is False
    assert _patch_settings(auth_client, {'dns_update_port': 0}).status_code == 200
    assert _data(auth_client.get('/api/v2/acme/client/settings'))['dns_update_port'] == 0


def test_N2_env_is_reported_pos(auth_client, env, monkeypatch):
    monkeypatch.setenv('UCM_DNS_UPDATE_PORT', '9053')
    g = _data(auth_client.get('/api/v2/acme/client/settings'))
    assert g['dns_update_port_env'] == '9053'


@pytest.mark.parametrize('port', [53, 1023, 70000, -1, 'abc', None, True])
def test_N2_bad_ports_neg(auth_client, env, port):
    assert _patch_settings(auth_client, {'dns_update_port': port}).status_code == 400
    with env.app.app_context():
        assert SystemConfig.query.filter_by(key=PORT_KEY).first() is None


def test_N2_conflict_with_https_port_neg(auth_client, env):
    from config.settings import Config
    assert _patch_settings(auth_client, {'dns_update_port': Config.HTTPS_PORT}).status_code == 400


def test_N2_conflict_with_http_protocol_port_neg(auth_client, env, monkeypatch):
    monkeypatch.setenv('HTTP_PROTOCOL_PORT', '8081')
    assert _patch_settings(auth_client, {'dns_update_port': 8081}).status_code == 400
    assert _patch_settings(auth_client, {'dns_update_port': 8082}).status_code == 200


def test_N2_viewer_cannot_patch_neg(viewer_client, env):
    assert _patch_settings(viewer_client, {'dns_update_port': 8053}).status_code == 403


def _set_cfg(key, value):
    cfg = SystemConfig.query.filter_by(key=key).first()
    if cfg:
        cfg.value = value
    else:
        db.session.add(SystemConfig(key=key, value=value))
    db.session.commit()


# ------------------------------------------------------------------- B3

@pytest.mark.parametrize('raw', ['', '  '])
def test_B3_blank_env_falls_back_to_db_pos(auth_client, app, env, monkeypatch, raw):
    from services.acme.dns_update.status import get_dns_update_port, get_dns_update_port_env
    monkeypatch.setenv('UCM_DNS_UPDATE_PORT', raw)
    with app.app_context():
        _set_cfg(PORT_KEY, '8053')
        assert get_dns_update_port_env() is None
        assert get_dns_update_port() == 8053
    g = _data(auth_client.get('/api/v2/acme/client/settings'))
    assert g['dns_update_port_env'] is None and g['dns_update_port'] == 8053


def test_B3_env_value_wins_over_db_neg(auth_client, app, env, monkeypatch):
    from services.acme.dns_update.status import get_dns_update_port
    monkeypatch.setenv('UCM_DNS_UPDATE_PORT', ' 8054 ')
    with app.app_context():
        _set_cfg(PORT_KEY, '8053')
        assert get_dns_update_port() == 8054
    g = _data(auth_client.get('/api/v2/acme/client/settings'))
    assert g['dns_update_port_env'] == '8054' and g['dns_update_port'] == 8053


def test_B3_stored_port_invalid_is_zero_neg(app, env):
    from services.acme.dns_update.status import get_stored_dns_update_port
    with app.app_context():
        assert get_stored_dns_update_port() == 0
        _set_cfg(PORT_KEY, 'abc')
        assert get_stored_dns_update_port() == 0
        _set_cfg(PORT_KEY, '8053')
        assert get_stored_dns_update_port() == 8053


# ------------------------------------------------------------------- B4

def test_B4_dns_port_equal_to_stored_tls_alpn_port_neg(auth_client, app, env, monkeypatch):
    monkeypatch.delenv('UCM_DNS_UPDATE_PORT', raising=False)
    with app.app_context():
        _set_cfg(TLS_KEY, '8443')
    assert _patch_settings(auth_client, {'dns_update_port': 8443}).status_code == 400
    with app.app_context():
        assert SystemConfig.query.filter_by(key=PORT_KEY).first() is None


def test_B4_dns_port_different_from_tls_alpn_port_pos(auth_client, app, env, monkeypatch):
    monkeypatch.delenv('UCM_DNS_UPDATE_PORT', raising=False)
    with app.app_context():
        _set_cfg(TLS_KEY, '8443')
    assert _patch_settings(auth_client, {'dns_update_port': 8444}).status_code == 200


def test_B4_dns_port_equal_to_tls_alpn_port_in_same_body_neg(auth_client, env, monkeypatch):
    monkeypatch.delenv('UCM_DNS_UPDATE_PORT', raising=False)
    r = _patch_settings(auth_client, {'dns_update_port': 8443, 'tls_alpn_port': 8443})
    assert r.status_code == 400


def test_B4_tls_alpn_port_equal_to_stored_dns_port_neg(auth_client, app, env, monkeypatch):
    monkeypatch.delenv('UCM_DNS_UPDATE_PORT', raising=False)
    with app.app_context():
        _set_cfg(PORT_KEY, '8053')
    assert _patch_settings(auth_client, {'tls_alpn_port': 8053}).status_code == 400
    with app.app_context():
        assert SystemConfig.query.filter_by(key=TLS_KEY).first() is None


def test_B4_tls_alpn_port_different_from_dns_port_pos(auth_client, app, env, monkeypatch):
    monkeypatch.delenv('UCM_DNS_UPDATE_PORT', raising=False)
    with app.app_context():
        _set_cfg(PORT_KEY, '8053')
    assert _patch_settings(auth_client, {'tls_alpn_port': 8054}).status_code == 200


def test_B4_tls_alpn_port_with_disabled_dns_port_pos(auth_client, env, monkeypatch):
    monkeypatch.delenv('UCM_DNS_UPDATE_PORT', raising=False)
    assert _patch_settings(auth_client, {'tls_alpn_port': 8053, 'dns_update_port': 0}
                           ).status_code == 200


def test_B4_restart_required_only_on_change_pos(auth_client, env, monkeypatch):
    monkeypatch.delenv('UCM_DNS_UPDATE_PORT', raising=False)
    from services.acme.dns_update import status
    status.set_listening(True, 8053)
    try:
        first = _patch_settings(auth_client, {'dns_update_port': 9053})
        assert _data(first)['restart_required'] is True
        second = _patch_settings(auth_client, {'dns_update_port': 8053})
        assert second.status_code == 200
        assert _data(second)['restart_required'] is False
    finally:
        status.set_listening(False)


def test_B4_restart_not_required_when_env_is_set_neg(auth_client, app, env, monkeypatch):
    monkeypatch.setenv('UCM_DNS_UPDATE_PORT', '9053')
    r = _patch_settings(auth_client, {'dns_update_port': 8053})
    assert r.status_code == 200
    assert _data(r)['restart_required'] is False
    assert _data(r)['dns_update_port_env_override'] is True
    assert 'UCM_DNS_UPDATE_PORT' in r.get_json()['message']
    with app.app_context():
        assert SystemConfig.query.filter_by(key=PORT_KEY).first().value == '8053'


def test_B4_no_env_override_flag_without_env_neg(auth_client, env, monkeypatch):
    monkeypatch.delenv('UCM_DNS_UPDATE_PORT', raising=False)
    r = _patch_settings(auth_client, {'dns_update_port': 8053})
    assert 'dns_update_port_env_override' not in _data(r)


# ------------------------------------------------------------------- B5

def _audit_mark(app):
    """The newest audit row id now. Rows are never deleted: the log is a hash chain
    that later tests verify."""
    from models.audit_log import AuditLog
    with app.app_context():
        return db.session.query(db.func.max(AuditLog.id)).scalar() or 0


def _key_audit(app, action, after):
    from models.audit_log import AuditLog
    with app.app_context():
        db.session.expire_all()
        return AuditLog.query.filter(
            AuditLog.id > after, AuditLog.action == action,
            AuditLog.resource_type == 'acme_dns_update_key').all()


def test_B5_soft_revoke_revokes_linked_key_and_audits_pos(auth_client, app, env):
    mark = _audit_mark(app)
    acct = env.make_account()
    cred = env.make_cred('active')
    kid = _data(_post(auth_client, acct, {'name': 'b5a.example.', 'eab_credential_id': cred}))['id']
    assert auth_client.delete(f'/api/v2/acme/eab-credentials/{cred}').status_code == 200
    with app.app_context():
        key = db.session.get(AcmeDnsUpdateKey, kid)
        assert key is not None and key.status == 'revoked' and key.revoked_at is not None
        kid_text = db.session.get(AcmeEabCredential, cred).kid
    rows = _key_audit(app, 'acme.dns_update.key.revoke', mark)
    assert len(rows) == 1
    assert rows[0].resource_id == str(kid) and rows[0].resource_name == 'b5a.example.'
    assert kid_text in rows[0].details
    assert _lookup(app, 'b5a.example.') is None


def test_B5_soft_revoke_leaves_other_credential_key_neg(auth_client, app, env):
    mark = _audit_mark(app)
    acct = env.make_account()
    cred, other = env.make_cred('active'), env.make_cred('active')
    _post(auth_client, acct, {'name': 'b5b.example.', 'eab_credential_id': cred})
    other_id = _data(_post(auth_client, acct, {'name': 'b5c.example.',
                                               'eab_credential_id': other}))['id']
    free_id = _data(_post(auth_client, acct, {'name': 'b5d.example.'}))['id']
    assert auth_client.delete(f'/api/v2/acme/eab-credentials/{cred}').status_code == 200
    with app.app_context():
        assert db.session.get(AcmeDnsUpdateKey, other_id).status == 'active'
        assert db.session.get(AcmeDnsUpdateKey, free_id).status == 'active'
    assert len(_key_audit(app, 'acme.dns_update.key.revoke', mark)) == 1


def test_B5_permanent_delete_removes_linked_key_and_audits_pos(auth_client, app, env):
    mark = _audit_mark(app)
    acct = env.make_account()
    cred = env.make_cred('used')
    kid = _data(_post(auth_client, acct, {'name': 'b5e.example.', 'eab_credential_id': cred}))['id']
    assert auth_client.delete(f'/api/v2/acme/eab-credentials/{cred}').status_code == 204
    with app.app_context():
        assert db.session.get(AcmeDnsUpdateKey, kid) is None
    rows = _key_audit(app, 'acme.dns_update.key.delete', mark)
    assert len(rows) == 1
    assert rows[0].resource_id == str(kid) and rows[0].resource_name == 'b5e.example.'
    assert 'kid-' in rows[0].details


def test_B5_permanent_delete_leaves_unlinked_keys_neg(auth_client, app, env):
    mark = _audit_mark(app)
    acct = env.make_account()
    cred = env.make_cred('used')
    free_id = _data(_post(auth_client, acct, {'name': 'b5f.example.'}))['id']
    assert auth_client.delete(f'/api/v2/acme/eab-credentials/{cred}').status_code == 204
    with app.app_context():
        assert db.session.get(AcmeDnsUpdateKey, free_id).status == 'active'
    assert _key_audit(app, 'acme.dns_update.key.delete', mark) == []


# ------------------------------------------------------------------- logs

def test_no_secret_in_logs_neg(auth_client, env, caplog):
    acct = env.make_account()
    with caplog.at_level(logging.DEBUG):
        r = _post(auth_client, acct)
    secret = _data(r)['secret']
    assert r.status_code == 201
    assert secret not in caplog.text
    with env.app.app_context():
        from models.audit_log import AuditLog
        rows = AuditLog.query.filter(AuditLog.action.like('acme.dns_update.key.%')).all()
        assert rows and all(secret not in (row.details or '') for row in rows)


# ------------------------------------------------------------------- D1 (API)

def test_D1_create_with_eab_sets_bound_pos(auth_client, env):
    acct = env.make_account()
    r = _post(auth_client, acct, {'eab_credential_id': env.make_cred('active')})
    assert r.status_code == 201 and _data(r)['eab_bound'] is True
    with env.app.app_context():
        assert AcmeDnsUpdateKey.query.get(_data(r)['id']).eab_bound is True


def test_D1_create_without_eab_is_not_bound_neg(auth_client, env):
    r = _post(auth_client, env.make_account())
    assert r.status_code == 201 and _data(r)['eab_bound'] is False


# ------------------------------------------------------------------- D4

def test_D4a_restart_required_compares_with_running_port_pos(auth_client, env, monkeypatch):
    from services.acme.dns_update import status
    monkeypatch.delenv('UCM_DNS_UPDATE_PORT', raising=False)
    status.set_listening(True, 8053)
    try:
        assert status.listening_port() == 8053
        assert _data(_patch_settings(auth_client, {'dns_update_port': 9053}))[
            'restart_required'] is True
        assert _data(_patch_settings(auth_client, {'dns_update_port': 8053}))[
            'restart_required'] is False
    finally:
        status.set_listening(False)
    assert status.listening_port() == 0


def test_D4a_not_listening_compares_with_zero_neg(auth_client, env, monkeypatch):
    from services.acme.dns_update import status
    monkeypatch.delenv('UCM_DNS_UPDATE_PORT', raising=False)
    status.set_listening(False)
    assert _data(_patch_settings(auth_client, {'dns_update_port': 0}))[
        'restart_required'] is False
    assert _data(_patch_settings(auth_client, {'dns_update_port': 8053}))[
        'restart_required'] is True


def test_D4b_tls_alpn_conflicts_with_env_dns_port_pos(auth_client, env, monkeypatch):
    monkeypatch.setenv('UCM_DNS_UPDATE_PORT', '9443')
    r = _patch_settings(auth_client, {'tls_alpn_port': 9443, 'dns_update_port': 0})
    assert r.status_code == 400


def test_D4b_tls_alpn_without_env_ignores_disabled_port_neg(auth_client, env, monkeypatch):
    monkeypatch.delenv('UCM_DNS_UPDATE_PORT', raising=False)
    r = _patch_settings(auth_client, {'tls_alpn_port': 9443, 'dns_update_port': 0})
    assert r.status_code == 200


def test_D4c_env_out_of_range_is_zero_with_warning_pos(app, env, monkeypatch, caplog):
    from services.acme.dns_update.status import get_dns_update_port
    monkeypatch.setenv('UCM_DNS_UPDATE_PORT', '70000')
    with app.app_context(), caplog.at_level(logging.WARNING):
        assert get_dns_update_port() == 0
    assert any('UCM_DNS_UPDATE_PORT' in r.getMessage() for r in caplog.records)


def test_D4c_env_valid_port_no_warning_neg(app, env, monkeypatch, caplog):
    from services.acme.dns_update.status import get_dns_update_port
    monkeypatch.setenv('UCM_DNS_UPDATE_PORT', '8053')
    with app.app_context(), caplog.at_level(logging.WARNING):
        assert get_dns_update_port() == 8053
    assert not caplog.records


def test_D4c_env_privileged_port_kept_with_warning_pos(app, env, monkeypatch, caplog):
    from services.acme.dns_update.status import get_dns_update_port
    monkeypatch.setenv('UCM_DNS_UPDATE_PORT', '53')
    with app.app_context(), caplog.at_level(logging.WARNING):
        assert get_dns_update_port() == 53
    assert any('CAP_NET_BIND_SERVICE' in r.getMessage() for r in caplog.records)


def test_D4d_effective_port_follows_env_pos(auth_client, env, monkeypatch):
    monkeypatch.setenv('UCM_DNS_UPDATE_PORT', '8054')
    assert _data(auth_client.get('/api/v2/acme/client/settings'))[
        'dns_update_port_effective'] == 8054


def test_D4d_effective_port_invalid_env_is_zero_neg(auth_client, env, monkeypatch):
    monkeypatch.setenv('UCM_DNS_UPDATE_PORT', '70000')
    assert _data(auth_client.get('/api/v2/acme/client/settings'))[
        'dns_update_port_effective'] == 0


def test_D4d_effective_port_from_db_without_env_pos(auth_client, app, env, monkeypatch):
    monkeypatch.delenv('UCM_DNS_UPDATE_PORT', raising=False)
    with app.app_context():
        _set_cfg(PORT_KEY, '8053')
    assert _data(auth_client.get('/api/v2/acme/client/settings'))[
        'dns_update_port_effective'] == 8053


# ------------------------------------------------------------------- F3

def _warm_row(app, acct_id, tag):
    """A pending order and an expected value of the account, in the real cache."""
    from datetime import timedelta
    from models import AcmeClientOrder
    from models.acme_dns_update import AcmeProxyDnsChallenge
    from utils.datetime_utils import utc_now
    order = AcmeClientOrder(
        domains=json.dumps([f'{tag}.example.com']), environment='staging',
        challenge_type='dns-01', status='pending', is_proxy_order=True,
        order_url=f'https://u.example/o/{tag}', account_id=f'acct-{tag}',
        client_jwk_thumbprint=f'thumb-{tag}', acme_client_account_id=acct_id)
    db.session.add(order)
    db.session.commit()
    row = AcmeProxyDnsChallenge(
        order_id=order.id, client_jwk_thumbprint=f'thumb-{tag}',
        identifier=f'{tag}.example.com', record_name=f'_acme-challenge.{tag}.example.com.',
        txt_value=f'v-{tag}', zone_name='example.com.', acme_client_account_id=acct_id,
        account_id=f'acct-{tag}', expires_at=utc_now() + timedelta(hours=1))
    db.session.add(row)
    db.session.commit()
    return order.id, row.id


def _cached_account_ids():
    from services.acme.dns_update import records
    snap = records.get_active_snapshot()
    return {r.acme_client_account_id for group in snap.by_name.values() for r in group}


def _drop_orders(order_ids):
    from models import AcmeClientOrder
    from models.acme_dns_update import AcmeProxyDnsChallenge
    AcmeProxyDnsChallenge.query.filter(AcmeProxyDnsChallenge.order_id.in_(order_ids)).delete(
        synchronize_session=False)
    AcmeClientOrder.query.filter(AcmeClientOrder.id.in_(order_ids)).delete(
        synchronize_session=False)
    db.session.commit()


def test_F3_account_delete_drops_its_rows_from_warm_cache_pos(auth_client, app, env):
    from services.acme.dns_update import records
    acct = env.make_account()
    with app.app_context():
        order_id, _row = _warm_row(app, acct, 'f3a')
        try:
            records.invalidate_cache()
            assert acct in _cached_account_ids()  # the cache is warm with the row
            assert auth_client.delete(f'/api/v2/acme/client/accounts/{acct}').status_code == 200
            assert acct not in _cached_account_ids()  # no wait for the 5 s age
        finally:
            _drop_orders([order_id])
            records.invalidate_cache()


def test_F3_deleting_another_account_leaves_the_row_neg(auth_client, app, env):
    from services.acme.dns_update import records
    acct, other = env.make_account(), env.make_account()
    with app.app_context():
        order_id, _row = _warm_row(app, acct, 'f3b')
        try:
            records.invalidate_cache()
            assert acct in _cached_account_ids()
            assert auth_client.delete(f'/api/v2/acme/client/accounts/{other}').status_code == 200
            assert acct in _cached_account_ids()
        finally:
            _drop_orders([order_id])
            records.invalidate_cache()


# ------------------------------------------------------------------- F4

def test_F4_same_invalid_env_warns_once_pos(app, env, monkeypatch, caplog):
    from services.acme.dns_update.status import get_dns_update_port
    monkeypatch.setenv('UCM_DNS_UPDATE_PORT', '70000')
    with app.app_context(), caplog.at_level(logging.WARNING):
        assert get_dns_update_port() == 0
        assert get_dns_update_port() == 0
    assert len([r for r in caplog.records if 'UCM_DNS_UPDATE_PORT' in r.getMessage()]) == 1


def test_F4_other_invalid_value_warns_again_neg(app, env, monkeypatch, caplog):
    from services.acme.dns_update.status import get_dns_update_port
    with app.app_context(), caplog.at_level(logging.WARNING):
        monkeypatch.setenv('UCM_DNS_UPDATE_PORT', '70000')
        get_dns_update_port()
        monkeypatch.setenv('UCM_DNS_UPDATE_PORT', 'abc')
        assert get_dns_update_port() == 0
        monkeypatch.setenv('UCM_DNS_UPDATE_PORT', '53')
        assert get_dns_update_port() == 53
        get_dns_update_port()
    messages = [r.getMessage() for r in caplog.records]
    assert len(messages) == 3
    assert any('abc' in m for m in messages) and any('CAP_NET_BIND_SERVICE' in m for m in messages)


# ------------------------------------------------------------------- F5

def test_F5_settings_get_reads_stored_port_once_pos(auth_client, app, env, monkeypatch):
    from sqlalchemy import event
    monkeypatch.delenv('UCM_DNS_UPDATE_PORT', raising=False)
    with app.app_context():
        _set_cfg(PORT_KEY, '8053')
    hits = []

    def _count(conn, cursor, statement, parameters, *_a):
        if 'system_config' in statement and PORT_KEY in repr(parameters):
            hits.append(statement)

    event.listen(db.engine, 'before_cursor_execute', _count)
    try:
        resp = auth_client.get('/api/v2/acme/client/settings')
    finally:
        event.remove(db.engine, 'before_cursor_execute', _count)
    assert resp.status_code == 200
    assert len(hits) == 1
    data = _data(resp)
    assert data['dns_update_port'] == 8053 and data['dns_update_port_effective'] == 8053


def test_F5_explicit_stored_value_is_used_without_db_read_neg(app, env, monkeypatch):
    from services.acme.dns_update.status import get_dns_update_port
    monkeypatch.delenv('UCM_DNS_UPDATE_PORT', raising=False)
    with app.app_context():
        _set_cfg(PORT_KEY, '8053')
        assert get_dns_update_port() == 8053
        assert get_dns_update_port(0) == 0  # the given value wins, no new read
        assert get_dns_update_port(9000) == 9000
    monkeypatch.setenv('UCM_DNS_UPDATE_PORT', '8054')
    with app.app_context():
        assert get_dns_update_port(9000) == 8054  # env still wins
