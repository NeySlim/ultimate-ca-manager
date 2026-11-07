"""Which account an SSO login opens, and whether it may open one at all.

OIDC Core 1.0 §5.7: only ``iss`` + ``sub`` identify the End-User; §5.1:
``preferred_username`` "MUST NOT" be relied upon as unique. With role mapping
rules, a user none of them matches is refused. The doors are the real OAuth2
callback and the LDAP login; SAML is in test_saml_strict_validation.
"""
import uuid

import pytest

from models import db, User
from models.sso import SSOProvider, SSOSession


def _cleanup(names):
    User.query.filter(User.username.in_(names)).delete(synchronize_session=False)
    db.session.commit()


@pytest.fixture
def oidc(app, monkeypatch):
    """The only enabled OAuth2 provider; the IdP answers with ``userinfo``."""
    from api.v2.sso import login_routes

    with app.app_context():
        others = [(p.id, p.enabled) for p in SSOProvider.query.filter_by(provider_type='oauth2').all()]
        for pid, _ in others:
            db.session.get(SSOProvider, pid).enabled = False
        row = SSOProvider(
            name=f'takeover-oidc-{uuid.uuid4().hex[:6]}', provider_type='oauth2', enabled=True,
            oauth2_client_id='ucm-client', oauth2_client_secret='secret',
            oauth2_auth_url='https://idp.example/authorize',
            oauth2_token_url='https://idp.example/token',
            oauth2_userinfo_url='https://idp.example/userinfo',
            oauth2_issuer='https://idp.example', id_token_verify=True,
            auto_create_users=True, default_role='viewer',
        )
        db.session.add(row)
        db.session.commit()
        pid = row.id

    answer = {}

    class Resp:
        ok = True
        text = ''

        def __init__(self, body):
            self._body = body

        def json(self):
            return self._body

    monkeypatch.setattr(login_routes, 'safe_request_post',
                        lambda *_a, **_k: Resp({'access_token': 'at', 'id_token': 'x.y.z'}))
    monkeypatch.setattr(login_routes, 'safe_request_get', lambda *_a, **_k: Resp(answer))
    monkeypatch.setattr(login_routes, 'verify_id_token',
                        lambda *_a, **_k: {'sub': answer.get('sub')})

    def configure(**fields):
        with app.app_context():
            row = db.session.get(SSOProvider, pid)
            for key, val in fields.items():
                setattr(row, key, val)
            db.session.commit()

    def login(userinfo):
        answer.clear()
        answer.update(userinfo)
        client = app.test_client()
        with client.session_transaction() as s:
            s['sso_state'] = 'st'
            s['sso_pkce_verifier'] = 'v'
            s['sso_nonce'] = 'n'
        r = client.get('/api/v2/sso/callback/oauth2?state=st&code=c')
        assert r.status_code == 302
        verify = client.get('/api/v2/auth/verify').get_json() or {}
        return r.headers['Location'], (verify.get('data') or {})

    login.provider_id = pid
    login.configure = configure
    yield login
    with app.app_context():
        SSOSession.query.filter_by(provider_id=pid).delete()
        User.query.filter_by(sso_provider_id=pid).delete()
        db.session.delete(db.session.get(SSOProvider, pid))
        for opid, enabled in others:
            db.session.get(SSOProvider, opid).enabled = enabled
        db.session.commit()


def test_oidc_email_local_part_does_not_open_the_local_admin(app, oidc):
    with app.app_context():
        _cleanup(['tkadmin'])
        db.session.add(User(username='tkadmin', email='tkadmin@corp.test', full_name='A',
                            role='admin', active=True, password_hash='hash', auth_source='local'))
        db.session.commit()
    try:
        location, verify = oidc({'sub': 'attacker-sub-1', 'email': 'tkadmin@attacker.example'})
        assert location.endswith('/login?error=sso_username_conflict')
        assert verify.get('authenticated') is not True
        with app.app_context():
            admin = User.query.filter_by(username='tkadmin').one()
            assert admin.sso_external_id is None and admin.auth_source == 'local'
            from models import AuditLog
            assert AuditLog.query.filter(
                AuditLog.action == 'login_failure',
                AuditLog.details.contains('tkadmin')).count() >= 1
    finally:
        with app.app_context():
            _cleanup(['tkadmin'])


def test_oidc_preferred_username_does_not_open_another_sso_account(app, oidc):
    with app.app_context():
        _cleanup(['tkbob'])
        db.session.add(User(username='tkbob', email='bob@corp.test', full_name='Bob',
                            role='operator', active=True, password_hash='!SSO_NO_PASSWORD!',
                            auth_source='oauth2', sso_provider_id=oidc.provider_id,
                            sso_external_id='bob-sub'))
        db.session.commit()
    try:
        location, verify = oidc({'sub': 'mallory-sub', 'preferred_username': 'tkbob',
                                 'email': 'mallory@else.test'})
        assert location.endswith('/login?error=sso_username_conflict')
        assert verify.get('authenticated') is not True
        with app.app_context():
            assert User.query.filter_by(username='tkbob').one().sso_external_id == 'bob-sub'
        # Bob himself still signs in.
        location, verify = oidc({'sub': 'bob-sub', 'preferred_username': 'tkbob'})
        assert location.endswith('/login/sso-complete')
        assert verify.get('user', {}).get('username') == 'tkbob'
    finally:
        with app.app_context():
            _cleanup(['tkbob'])


def test_oidc_email_never_adopts_an_account_bound_to_another_sub(app, oidc):
    with app.app_context():
        _cleanup(['tkcarol', 'tkcarol2'])
        db.session.add(User(username='tkcarol', email='carol@corp.test', full_name='C',
                            role='admin', active=True, password_hash='!SSO_NO_PASSWORD!',
                            auth_source='oauth2', sso_provider_id=oidc.provider_id,
                            sso_external_id='carol-sub'))
        db.session.commit()
    try:
        location, _ = oidc({'sub': 'other-sub', 'preferred_username': 'tkcarol2',
                            'email': 'carol@corp.test'})
        assert location.endswith('/login/sso-complete')
        with app.app_context():
            assert User.query.filter_by(username='tkcarol').one().sso_external_id == 'carol-sub'
            assert User.query.filter_by(username='tkcarol2').one().sso_external_id == 'other-sub'
    finally:
        with app.app_context():
            _cleanup(['tkcarol', 'tkcarol2'])


def test_oidc_adopts_an_admin_linked_account_and_binds_its_sub(app, oidc):
    """The documented merge path: Link to SSO, then the first login binds the sub."""
    with app.app_context():
        _cleanup(['tkdave'])
        db.session.add(User(username='tkdave', email='dave@corp.test', full_name='D',
                            role='admin', active=True, password_hash='hash',
                            auth_source='oauth2', sso_provider_id=oidc.provider_id))
        db.session.commit()
    try:
        location, verify = oidc({'sub': 'dave-sub', 'preferred_username': 'tkdave'})
        assert location.endswith('/login/sso-complete')
        with app.app_context():
            assert User.query.filter_by(username='tkdave').one().sso_external_id == 'dave-sub'
    finally:
        with app.app_context():
            _cleanup(['tkdave'])


@pytest.fixture
def ldap(app, monkeypatch):
    from api.v2.sso import ldap_routes

    with app.app_context():
        others = [(p.id, p.enabled) for p in SSOProvider.query.filter_by(provider_type='ldap').all()]
        for pid, _ in others:
            db.session.get(SSOProvider, pid).enabled = False
        row = SSOProvider(name=f'takeover-ldap-{uuid.uuid4().hex[:6]}', provider_type='ldap',
                          enabled=True, ldap_server='ldap.example.test',
                          auto_create_users=True, default_role='viewer')
        db.session.add(row)
        db.session.commit()
        pid = row.id
    directory = {}
    monkeypatch.setattr(ldap_routes, '_ldap_authenticate_user',
                        lambda _p, username, _pw: (dict(directory, username=username), None))

    def login(username, **entry):
        directory.clear()
        directory.update(entry)
        client = app.test_client()
        return client.post('/api/v2/sso/ldap/login',
                           json={'username': username, 'password': 'pw', 'provider_id': pid})

    login.provider_id = pid
    yield login
    with app.app_context():
        SSOSession.query.filter_by(provider_id=pid).delete()
        User.query.filter_by(sso_provider_id=pid).delete()
        db.session.delete(db.session.get(SSOProvider, pid))
        for opid, enabled in others:
            db.session.get(SSOProvider, opid).enabled = enabled
        db.session.commit()


def test_ldap_directory_admin_does_not_open_the_local_admin(app, ldap):
    with app.app_context():
        _cleanup(['tkroot'])
        db.session.add(User(username='tkroot', email='root@corp.test', full_name='R',
                            role='admin', active=True, password_hash='hash', auth_source='local'))
        db.session.commit()
    try:
        r = ldap('tkroot', dn='uid=tkroot,dc=example', uid='uuid-root')
        assert r.status_code == 403
        assert 'local account' in r.get_json()['message']
        with app.app_context():
            assert User.query.filter_by(username='tkroot').one().sso_external_id is None
    finally:
        with app.app_context():
            _cleanup(['tkroot'])


def test_ldap_adopts_a_pre_stable_id_account_of_the_same_provider(app, ldap):
    """Accounts created before stable ids keep matching by name, once."""
    with app.app_context():
        _cleanup(['tkold'])
        db.session.add(User(username='tkold', email='old@corp.test', full_name='O',
                            role='operator', active=True, password_hash='!SSO_NO_PASSWORD!',
                            auth_source='ldap', sso_provider_id=ldap.provider_id))
        db.session.commit()
    try:
        r = ldap('tkold', dn='uid=tkold,dc=example', uid='uuid-old')
        assert r.status_code == 200, r.get_json()
        with app.app_context():
            assert User.query.filter_by(username='tkold').one().sso_external_id == 'uuid-old'
    finally:
        with app.app_context():
            _cleanup(['tkold'])


def test_bind_never_replaces_an_existing_external_id(app):
    from api.v2.sso.ldap_routes import _bind_external_id
    with app.app_context():
        _cleanup(['tkbound'])
        u = User(username='tkbound', email='b@corp.test', full_name='B', role='viewer',
                 active=True, password_hash='!SSO_NO_PASSWORD!', auth_source='oauth2',
                 sso_provider_id=1, sso_external_id='first')
        db.session.add(u)
        db.session.commit()
        provider = SSOProvider(id=1, provider_type='oauth2')
        try:
            assert _bind_external_id(u, provider, 'second') is False
            assert u.sso_external_id == 'first'
        finally:
            db.session.rollback()
            _cleanup(['tkbound'])


# ── Unmapped users (role mapping rules are an admission list) ───────────────

def _audited(app, needle):
    from models import AuditLog
    with app.app_context():
        return AuditLog.query.filter(AuditLog.action == 'login_failure',
                                     AuditLog.details.contains(needle)).count()


def test_oidc_user_no_rule_matches_is_refused(app, oidc):
    oidc.configure(role_mapping='{"pki-admins": "admin"}')
    try:
        location, verify = oidc({'sub': 'nomap-sub', 'preferred_username': 'tknomap',
                                 'groups': ['staff']})
        assert location.endswith('/login?error=sso_unmapped')
        assert verify.get('authenticated') is not True
        with app.app_context():
            assert User.query.filter_by(username='tknomap').count() == 0
        assert _audited(app, 'tknomap') >= 1
        location, _ = oidc({'sub': 'map-sub', 'preferred_username': 'tkmap',
                            'groups': ['pki-admins']})
        assert location.endswith('/login/sso-complete')
    finally:
        with app.app_context():
            _cleanup(['tknomap', 'tkmap'])


def test_existing_user_dropped_from_every_mapped_group_is_refused(app, oidc):
    oidc.configure(role_mapping='{"pki-users": "viewer"}')
    try:
        assert oidc({'sub': 'drop-sub', 'preferred_username': 'tkdrop',
                     'groups': ['pki-users']})[0].endswith('/login/sso-complete')
        location, verify = oidc({'sub': 'drop-sub', 'preferred_username': 'tkdrop', 'groups': []})
        assert location.endswith('/login?error=sso_unmapped')
        assert verify.get('authenticated') is not True
    finally:
        with app.app_context():
            _cleanup(['tkdrop'])


def test_without_rules_users_get_the_default_role(app, oidc):
    oidc.configure(role_mapping=None, default_role='auditor')
    try:
        assert oidc({'sub': 'def-sub', 'preferred_username': 'tkdef'})[0].endswith('/login/sso-complete')
        with app.app_context():
            assert User.query.filter_by(username='tkdef').one().role == 'auditor'
    finally:
        with app.app_context():
            _cleanup(['tkdef'])


def test_an_empty_default_role_is_stored_and_admits_nobody(app, auth_client, oidc):
    r = auth_client.put(f'/api/v2/sso/providers/{oidc.provider_id}',
                        json={'default_role': '', 'role_mapping': {}})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['data']['default_role'] is None
    try:
        location, _ = oidc({'sub': 'none-sub', 'preferred_username': 'tknone'})
        assert location.endswith('/login?error=sso_unmapped')
        with app.app_context():
            assert User.query.filter_by(username='tknone').count() == 0
    finally:
        with app.app_context():
            _cleanup(['tknone'])


def test_an_unknown_default_role_is_refused_not_turned_into_viewer(auth_client, oidc):
    r = auth_client.put(f'/api/v2/sso/providers/{oidc.provider_id}', json={'default_role': 'root'})
    assert r.status_code == 400
    assert 'default_role' in r.get_json()['message']


def test_ldap_user_no_rule_matches_is_refused(app, ldap):
    with app.app_context():
        db.session.get(SSOProvider, ldap.provider_id).role_mapping = '{"pki-admins": "admin"}'
        db.session.commit()
    try:
        r = ldap('tkldapnomap', dn='uid=tkldapnomap,dc=example', uid='uuid-nomap', groups=['staff'])
        assert r.status_code == 403
        assert 'mapping' in r.get_json()['message']
        with app.app_context():
            assert User.query.filter_by(username='tkldapnomap').count() == 0
    finally:
        with app.app_context():
            _cleanup(['tkldapnomap'])


# ── Enforced 2FA on an LDAP provider asks the enrolled code ────────────────

def test_ldap_with_enforced_2fa_asks_the_enrolled_totp(app, ldap):
    import pyotp
    secret = pyotp.random_base32()
    with app.app_context():
        _cleanup(['tkotp'])
        db.session.get(SSOProvider, ldap.provider_id).enforce_2fa = True
        db.session.add(User(username='tkotp', email='otp@corp.test', full_name='O', role='viewer',
                            active=True, password_hash='!SSO_NO_PASSWORD!', auth_source='ldap',
                            sso_provider_id=ldap.provider_id, sso_external_id='uuid-otp',
                            totp_secret=secret, totp_confirmed=True))
        db.session.commit()
    try:
        client = app.test_client()
        ldap('tkotp', dn='uid=tkotp,dc=example', uid='uuid-otp')  # primes the directory answer
        r = client.post('/api/v2/sso/ldap/login',
                        json={'username': 'tkotp', 'password': 'pw', 'provider_id': ldap.provider_id})
        assert r.status_code == 200
        body = r.get_json()['data']
        assert body.get('requires_2fa') is True and 'totp' in body['methods']
        assert not (client.get('/api/v2/auth/verify').get_json().get('data') or {}).get('authenticated')
        r = client.post('/api/v2/auth/login/2fa', json={'code': pyotp.TOTP(secret).now()})
        assert r.status_code == 200, r.get_json()
        verify = client.get('/api/v2/auth/verify').get_json()['data']
        assert verify['authenticated'] is True and verify['user']['username'] == 'tkotp'
    finally:
        with app.app_context():
            _cleanup(['tkotp'])


def test_an_account_of_another_provider_is_not_opened(app, oidc, ldap):
    with app.app_context():
        _cleanup(['tkcross'])
        db.session.add(User(username='tkcross', email='cross@corp.test', full_name='X', role='admin',
                            active=True, password_hash='!SSO_NO_PASSWORD!', auth_source='oauth2',
                            sso_provider_id=oidc.provider_id))
        db.session.commit()
    try:
        r = ldap('tkcross', dn='uid=tkcross,dc=example', uid='uuid-cross')
        assert r.status_code == 403
        with app.app_context():
            u = User.query.filter_by(username='tkcross').one()
            assert u.sso_provider_id == oidc.provider_id and u.sso_external_id is None
    finally:
        with app.app_context():
            _cleanup(['tkcross'])
