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


# ── A provider deleted then recreated keeps its users ───────────────────────

def _orphan(app, username, sub, through_api=None, issuer='https://idp.example/'):
    """An OIDC account bound to ``sub`` whose provider (``issuer``) is then deleted,
    through the API or, as before this release, by a bare row delete."""
    with app.app_context():
        _cleanup([username])
        old = SSOProvider(name=f'gone-{uuid.uuid4().hex[:6]}', provider_type='oauth2', enabled=False,
                          oauth2_issuer=issuer)
        db.session.add(old)
        db.session.commit()
        old_id = old.id
        db.session.add(User(username=username, email=f'{username}@corp.test', full_name='C',
                            role='admin', active=True, password_hash='!SSO_NO_PASSWORD!',
                            auth_source='oauth2', sso_provider_id=old_id, sso_external_id=sub))
        db.session.commit()
        if through_api is None:
            User.query.filter_by(username=username).update({User.sso_provider_id: None})
            db.session.delete(db.session.get(SSOProvider, old_id))
            db.session.commit()
    if through_api is not None:
        assert through_api.delete(f'/api/v2/sso/providers/{old_id}').status_code == 200
    return old_id


def test_deleting_a_provider_unlinks_its_users_and_keeps_its_idp(app, auth_client):
    _orphan(app, 'rvdel', 'del-sub', through_api=auth_client)
    try:
        with app.app_context():
            u = User.query.filter_by(username='rvdel').one()
            assert u.sso_provider_id is None
            assert u.sso_orphan_of == 'oauth2:https://idp.example'
    finally:
        with app.app_context():
            _cleanup(['rvdel'])


def test_a_provider_recreated_for_the_same_idp_opens_its_bound_users(app, auth_client, oidc):
    _orphan(app, 'rvcarol', 'carol-sub', through_api=auth_client)
    try:
        location, verify = oidc({'sub': 'carol-sub', 'preferred_username': 'rvcarol'})
        assert location.endswith('/login/sso-complete'), location
        assert verify['user']['username'] == 'rvcarol'
        with app.app_context():
            u = User.query.filter_by(username='rvcarol').one()
            assert u.sso_provider_id == oidc.provider_id and u.sso_external_id == 'carol-sub'
            assert u.sso_orphan_of is None
    finally:
        with app.app_context():
            _cleanup(['rvcarol'])


@pytest.mark.parametrize('issuer, through_api', [
    ('https://other-idp.example', True),   # OIDC Core §5.7: a sub means nothing without its iss
    ('https://idp.example', False),        # deleted before this release: the IdP is unknown
])
def test_an_orphan_is_not_opened_by_its_id_from_another_or_unknown_idp(
        app, auth_client, oidc, issuer, through_api):
    _orphan(app, 'rvorph', 'orph-sub', issuer=issuer, through_api=auth_client if through_api else None)
    try:
        location, verify = oidc({'sub': 'orph-sub', 'preferred_username': 'rvorph'})
        assert location.endswith('/login?error=sso_username_conflict'), location
        location, verify = oidc({'sub': 'orph-sub', 'preferred_username': 'rvorphx'})
        assert verify['user']['username'] == 'rvorphx'  # a new account, not the orphan
        with app.app_context():
            assert User.query.filter_by(username='rvorph').one().sso_provider_id is None
    finally:
        with app.app_context():
            _cleanup(['rvorph', 'rvorphx'])


def test_a_saml_orphan_is_not_opened_by_another_idp(app, auth_client):
    """A SAML NameID only means something for the IdP that issued it."""
    from api.v2.sso.ldap_routes import _get_or_create_sso_user
    email_fmt = 'urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress'
    with app.app_context():
        _cleanup(['rvorph2'])
        rows = [SSOProvider(name=f'saml-{n}-{uuid.uuid4().hex[:6]}', provider_type='saml',
                            enabled=False, saml_entity_id=f'https://{n}.example/idp',
                            default_role='viewer') for n in ('a', 'b')]
        db.session.add_all(rows)
        db.session.commit()
        a_id, b_id = rows[0].id, rows[1].id
        db.session.add(User(username='rvorph2', email='alice@corp.example', full_name='A', role='admin',
                            active=True, password_hash='!SSO_NO_PASSWORD!', auth_source='saml',
                            sso_provider_id=a_id, sso_external_id='alice@corp.example'))
        db.session.commit()
    assert auth_client.delete(f'/api/v2/sso/providers/{a_id}').status_code == 200
    try:
        with app.test_request_context():
            user, err = _get_or_create_sso_user(
                db.session.get(SSOProvider, b_id), 'rvorph2', 'alice@corp.example', 'A',
                {'name_id': 'alice@corp.example', 'name_id_format': email_fmt})
            assert user is None and err == 'sso_username_conflict'
            db.session.rollback()
            assert User.query.filter_by(username='rvorph2').one().sso_provider_id is None
    finally:
        with app.app_context():
            _cleanup(['rvorph2'])
            db.session.delete(db.session.get(SSOProvider, b_id))
            db.session.commit()


def test_an_orphan_of_another_type_is_not_opened_by_its_id(app, oidc):
    with app.app_context():
        _cleanup(['rvsaml'])
        db.session.add(User(username='rvsaml', email='s@corp.test', full_name='S', role='admin',
                            active=True, password_hash='!SSO_NO_PASSWORD!', auth_source='saml',
                            sso_provider_id=None, sso_external_id='shared-id'))
        db.session.commit()
    try:
        location, verify = oidc({'sub': 'shared-id', 'preferred_username': 'rvsamlx'})
        assert (verify.get('user') or {}).get('username') != 'rvsaml'
        with app.app_context():
            assert User.query.filter_by(username='rvsaml').one().sso_provider_id is None
    finally:
        with app.app_context():
            _cleanup(['rvsaml', 'rvsamlx'])


# ── An account from before migration 024 is never opened by email ──────────

def test_a_legacy_sso_account_is_not_opened_by_email(app, oidc):
    with app.app_context():
        _cleanup(['rvleg', 'rvother'])
        db.session.add(User(username='rvleg', email='leg@corp.test', full_name='L', role='operator',
                            active=True, password_hash='!SSO_NO_PASSWORD!', auth_source='local'))
        db.session.commit()
    try:
        location, verify = oidc({'sub': 'att-x', 'preferred_username': 'rvother',
                                 'email': 'leg@corp.test'})
        assert (verify.get('user') or {}).get('username') != 'rvleg'
        with app.app_context():
            leg = User.query.filter_by(username='rvleg').one()
            assert leg.sso_external_id is None and leg.auth_source == 'local'
    finally:
        with app.app_context():
            _cleanup(['rvleg', 'rvother'])


def test_ldap_without_rules_nor_default_role_says_so(app, ldap):
    with app.app_context():
        row = db.session.get(SSOProvider, ldap.provider_id)
        row.role_mapping, row.default_role = None, None
        db.session.commit()
    try:
        r = ldap('tkldapnorole', dn='uid=tkldapnorole,dc=example', uid='uuid-norole')
        assert r.status_code == 403
        assert 'default role' in r.get_json()['message']
    finally:
        with app.app_context():
            _cleanup(['tkldapnorole'])


def test_ldap_asks_a_totp_the_user_enrolled_without_enforcement(app, ldap):
    import pyotp
    with app.app_context():
        _cleanup(['tkvolotp'])
        assert db.session.get(SSOProvider, ldap.provider_id).enforce_2fa is not True
        db.session.add(User(username='tkvolotp', email='vol@corp.test', full_name='V', role='viewer',
                            active=True, password_hash='!SSO_NO_PASSWORD!', auth_source='ldap',
                            sso_provider_id=ldap.provider_id, sso_external_id='uuid-vol',
                            totp_secret=pyotp.random_base32(), totp_confirmed=True))
        db.session.commit()
    try:
        r = ldap('tkvolotp', dn='uid=tkvolotp,dc=example', uid='uuid-vol')
        assert r.status_code == 200
        assert r.get_json()['data'].get('requires_2fa') is True
    finally:
        with app.app_context():
            _cleanup(['tkvolotp'])
