"""Which provider an account belongs to, and how an administrator moves it.

An account belongs to one provider and one stable identity (OIDC Core 1.0 §5.7:
only ``iss`` + ``sub`` identify the End-User). Link to SSO is the explicit,
audited way to attach any account to a provider; a sign-in never takes an
account by name or e-mail, and never creates a second account in silence when
one it may not open owns the presented e-mail.
"""
import uuid

import pytest

from models import db, User, AuditLog
from models.sso import SSOProvider

NOPASS = '!SSO_NO_PASSWORD!'
PREFIX = 'sb3'


def _cleanup():
    from api.v2.users.crud import _purge_user_dependencies
    rows = User.query.filter(User.username.like(f'{PREFIX}%')).all()
    for u in rows:
        _purge_user_dependencies(u.id)
    User.query.filter(User.username.like(f'{PREFIX}%')).delete(synchronize_session=False)
    db.session.commit()


@pytest.fixture
def providers(app):
    """Two OIDC providers for two IdPs, and a factory for more."""
    tag = uuid.uuid4().hex[:6]
    made = []

    def make(**fields):
        with app.app_context():
            base = dict(name=f'{PREFIX}-p-{uuid.uuid4().hex[:6]}', provider_type='oauth2',
                        enabled=False, oauth2_client_id='c', oauth2_client_secret='s',
                        auto_create_users=True, default_role='viewer')
            base.update(fields)
            row = SSOProvider(**base)
            db.session.add(row)
            db.session.commit()
            made.append(row.id)
            return row.id

    with app.app_context():
        _cleanup()
    a = make(name=f'{PREFIX}-a-{tag}', oauth2_issuer='https://a.example',
             oauth2_userinfo_url='https://a.example/userinfo')
    b = make(name=f'{PREFIX}-b-{tag}', oauth2_issuer='https://b.example',
             oauth2_userinfo_url='https://b.example/userinfo')
    make.a, make.b = a, b
    yield make
    with app.app_context():
        _cleanup()
        for pid in made:
            row = db.session.get(SSOProvider, pid)
            if row is not None:
                db.session.delete(row)
        db.session.commit()


def _name():
    return f'{PREFIX}{uuid.uuid4().hex[:8]}'


def _add(app, **kw):
    with app.app_context():
        kw.setdefault('email', f"{kw['username']}@corp.example")
        kw.setdefault('full_name', 'N')
        kw.setdefault('role', 'operator')
        kw.setdefault('active', True)
        u = User(**kw)
        db.session.add(u)
        db.session.commit()
        return u.id


def _login(app, pid, username, ext, email=None):
    from api.v2.sso.ldap_routes import _get_or_create_sso_user
    with app.test_request_context():
        p = db.session.get(SSOProvider, pid)
        user, err = _get_or_create_sso_user(p, username, email or f'{username}@corp.example', 'N', ext)
        return (user.username if user else None), err


def _last_audit(app, action, name):
    with app.app_context():
        row = (AuditLog.query.filter(AuditLog.action == action,
                                     AuditLog.details.contains(repr(name)))
               .order_by(AuditLog.id.desc()).first())
        return row.details if row else ''


def _count(app, **filters):
    with app.app_context():
        return User.query.filter_by(**filters).count()


# ── 1. Link to SSO works on every account ───────────────────────────────────

def _state(app, providers, state, name):
    """An account in ``state`` with respect to provider B; returns its id."""
    a = providers.a
    if state == 'local_password':
        return _add(app, username=name, auth_source='local', password_hash='hash-x')
    if state == 'unlinked_no_password':
        # What Unlink SSO leaves on an account that never had a password.
        return _add(app, username=name, auth_source='local', password_hash=NOPASS,
                    force_password_change=True)
    if state == 'other_provider':
        return _add(app, username=name, auth_source='oauth2', sso_provider_id=a,
                    sso_external_id='sub-at-a', password_hash=NOPASS)
    if state == 'orphan_unknown_idp':
        return _add(app, username=name, auth_source='oauth2', sso_provider_id=None,
                    sso_orphan_of=None, sso_external_id='sub-old', password_hash=NOPASS)
    if state == 'orphan_other_idp':
        return _add(app, username=name, auth_source='oauth2', sso_provider_id=None,
                    sso_orphan_of='oauth2:https://gone.example', sso_external_id='sub-old',
                    password_hash=NOPASS)
    if state == 'same_provider_other_identity':
        return _add(app, username=name, auth_source='oauth2', sso_provider_id=providers.b,
                    sso_external_id='sub-before', password_hash=NOPASS)
    raise AssertionError(state)


STATES = ['local_password', 'unlinked_no_password', 'other_provider', 'orphan_unknown_idp',
          'orphan_other_idp', 'same_provider_other_identity']


@pytest.mark.parametrize('state', STATES)
def test_link_to_sso_attaches_any_account_and_the_next_sign_in_opens_it(
        app, providers, auth_client, state):
    name = _name()
    uid = _state(app, providers, state, name)
    # Before: provider B refuses the name, whatever the state.
    assert _login(app, providers.b, name, {'sub': 'sub-new'}) == (None, 'sso_username_conflict')
    r = auth_client.post(f'/api/v2/users/{uid}/link-sso', json={'provider_id': providers.b})
    assert r.status_code == 200, r.get_json()
    assert _login(app, providers.b, name, {'sub': 'sub-new'}) == (name, None)
    with app.app_context():
        u = db.session.get(User, uid)
        assert (u.auth_source, u.sso_provider_id, u.sso_external_id, u.sso_orphan_of) == \
            ('oauth2', providers.b, 'sub-new', None)
        if state == 'local_password':
            assert u.password_hash == 'hash-x'
        else:
            assert u.password_hash == NOPASS and u.force_password_change is False
    if state == 'other_provider':
        # Moved: its former provider no longer opens it.
        assert _login(app, providers.a, name, {'sub': 'sub-at-a'}) == (None, 'sso_username_conflict')


def test_relinked_account_without_password_is_not_asked_for_one(app, providers, auth_client):
    """Unlink SSO then Link to SSO: the SSO session is not confined to a password change."""
    from utils.datetime_utils import utc_now
    name = _name()
    uid = _state(app, providers, 'other_provider', name)
    assert auth_client.post(f'/api/v2/users/{uid}/unlink-sso').status_code == 200
    assert auth_client.post(f'/api/v2/users/{uid}/link-sso',
                            json={'provider_id': providers.b}).status_code == 200
    assert _login(app, providers.b, name, {'sub': 'sub-b'}) == (name, None)
    with app.app_context():
        role = db.session.get(User, uid).role
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(user_id=uid, username=name, role=role, auth_method='sso',
                 login_time=utc_now().isoformat(), last_activity=utc_now().isoformat())
    r = c.get('/api/v2/certificates')
    assert not (r.get_json() or {}).get('must_change_password'), (r.status_code, r.get_json())


def test_link_keeps_a_password_change_an_account_with_a_password_owes(app, providers, auth_client):
    name = _name()
    uid = _add(app, username=name, auth_source='local', password_hash='hash-y',
               force_password_change=True)
    assert auth_client.post(f'/api/v2/users/{uid}/link-sso',
                            json={'provider_id': providers.b}).status_code == 200
    with app.app_context():
        u = db.session.get(User, uid)
        assert u.password_hash == 'hash-y' and u.force_password_change is True


@pytest.mark.parametrize('state, origin', [
    ('local_password', 'was a local account'),
    ('other_provider', "was linked to provider '{a}', identity 'sub-at-a'"),
    ('orphan_unknown_idp', 'had no provider (its IdP is unknown), identity'),
    ('orphan_other_idp', "had no provider (orphan of 'oauth2:https://gone.example')"),
    ('same_provider_other_identity', "identity 'sub-before' reset"),
])
def test_link_audit_says_where_the_account_comes_from(app, providers, auth_client, state, origin):
    with app.app_context():
        a_name = db.session.get(SSOProvider, providers.a).name
    name = _name()
    uid = _state(app, providers, state, name)
    assert auth_client.post(f'/api/v2/users/{uid}/link-sso',
                            json={'provider_id': providers.b}).status_code == 200
    details = _last_audit(app, 'user_link_sso', name)
    assert origin.format(a=a_name) in details, details


def test_link_audit_bounds_the_former_identity(app, providers, auth_client):
    name = _name()
    long_id = 'x' * 500
    uid = _add(app, username=name, auth_source='oauth2', sso_provider_id=providers.a,
               sso_external_id=long_id, password_hash=NOPASS)
    assert auth_client.post(f'/api/v2/users/{uid}/link-sso',
                            json={'provider_id': providers.b}).status_code == 200
    details = _last_audit(app, 'user_link_sso', name)
    assert 'x' * 64 in details and 'x' * 65 not in details, details


def test_an_unlinked_account_without_password_is_still_not_taken_by_name(app, providers, auth_client):
    """Unlink makes the account local: no provider takes it back without Link to SSO."""
    name = _name()
    uid = _state(app, providers, 'other_provider', name)
    assert auth_client.post(f'/api/v2/users/{uid}/unlink-sso').status_code == 200
    for pid in (providers.a, providers.b):
        assert _login(app, pid, name, {'sub': 'sub-z'}) == (None, 'sso_username_conflict')


# ── 2. No silent second account ─────────────────────────────────────────────

@pytest.mark.parametrize('flag', [False, 'false'])
def test_unverified_email_of_an_admin_linked_account_is_refused_not_duplicated(
        app, providers, auth_client, flag):
    """(a) Linked by an administrator, other name, the IdP says the e-mail is unverified."""
    name, idp_name = _name(), _name()
    uid = _add(app, username=name, email=f'{name}@corp.example', auth_source='local',
               password_hash='hash')
    assert auth_client.post(f'/api/v2/users/{uid}/link-sso',
                            json={'provider_id': providers.b}).status_code == 200
    got = _login(app, providers.b, idp_name, {'sub': 'sub-u', 'email_verified': flag},
                 email=f'{name}@corp.example')
    assert got == (None, 'sso_email_conflict')
    assert _count(app, username=idp_name) == 0
    with app.app_context():
        assert db.session.get(User, uid).sso_external_id is None
    details = _last_audit(app, 'login_failure', name)
    assert 'unverified' in details and repr(idp_name) in details, details


def test_email_of_an_account_of_another_provider_is_refused_not_duplicated(app, providers):
    """(b) The e-mail belongs to an account of another provider; this one sends another name."""
    with app.app_context():
        a_name = db.session.get(SSOProvider, providers.a).name
    name, idp_name = _name(), _name()
    _add(app, username=name, email=f'{name}@corp.example', role='admin', auth_source='oauth2',
         sso_provider_id=providers.a, sso_external_id='sub-a', password_hash=NOPASS)
    got = _login(app, providers.b, idp_name, {'sub': 'sub-b'}, email=f'{name}@corp.example')
    assert got == (None, 'sso_email_conflict')
    assert _count(app, username=idp_name) == 0
    details = _last_audit(app, 'login_failure', name)
    assert repr(a_name) in details and 'Link to SSO' in details, details


def test_another_person_sharing_the_email_signs_in_once_an_account_is_created_and_linked(
        app, providers, auth_client):
    """The remedy the refusal names for a shared mailbox: no setting, an explicit account."""
    name, idp_name = _name(), _name()
    _add(app, username=name, email=f'{name}@corp.example', auth_source='oauth2',
         sso_provider_id=providers.a, sso_external_id='sub-a', password_hash=NOPASS)
    assert _login(app, providers.b, idp_name, {'sub': 'sub-b'},
                  email=f'{name}@corp.example') == (None, 'sso_email_conflict')
    r = auth_client.post('/api/v2/users', json={'username': idp_name, 'email': f'{name}@corp.example',
                                                 'password': 'Shared-Mailbox-9x!', 'role': 'viewer'})
    assert r.status_code in (200, 201), r.get_json()
    uid = r.get_json()['data']['id']
    assert auth_client.post(f'/api/v2/users/{uid}/link-sso',
                            json={'provider_id': providers.b}).status_code == 200
    assert _login(app, providers.b, idp_name, {'sub': 'sub-b'},
                  email=f'{name}@corp.example') == (idp_name, None)


def test_email_of_a_local_account_still_gives_a_distinct_sso_account(app, providers):
    """E-mail is unique among local accounts only (#136): an SSO account may share it."""
    name, idp_name = _name(), _name()
    _add(app, username=name, email=f'{name}@corp.example', auth_source='local', password_hash='hash')
    got = _login(app, providers.b, idp_name, {'sub': 'sub-l'}, email=f'{name}@corp.example')
    assert got == (idp_name, None)


def test_the_ldap_door_says_the_email_conflict_without_naming_the_account(app, providers, monkeypatch):
    from api.v2.sso import ldap_routes
    lid = providers(provider_type='ldap', enabled=True, ldap_server='ldap.example.test',
                    ldap_base_dn='dc=example')
    name, idp_name = _name(), _name()
    _add(app, username=name, email=f'{name}@corp.example', auth_source='oauth2',
         sso_provider_id=providers.a, sso_external_id='sub-a', password_hash=NOPASS)
    entry = {'dn': f'uid={idp_name},dc=example', 'uid': str(uuid.uuid4()),
             'email': f'{name}@corp.example'}
    monkeypatch.setattr(ldap_routes, '_ldap_authenticate_user',
                        lambda _p, username, _pw, before_bind=None: (dict(entry, username=username), None))
    r = app.test_client().post('/api/v2/sso/ldap/login',
                               json={'username': idp_name, 'password': 'pw', 'provider_id': lid})
    assert r.status_code == 403
    message = r.get_json()['message']
    assert message.startswith('Sign-in refused') and name not in message, message
    assert _count(app, username=idp_name) == 0


# ── 3. The refusal says the state of the account and what repairs it ───────

@pytest.mark.parametrize('state, says', [
    ('local_password', ['is a local account', 'Link to SSO attaches it']),
    ('other_provider', ["is linked to provider '{a}'", 'Link to SSO moves it']),
    ('same_provider_other_identity', ["bound to another identity of '{b}' ('sub-before')",
                                      'Link to SSO resets its identity']),
    ('orphan_unknown_idp', ['has no provider (its IdP is unknown)', 'Link to SSO attaches it']),
    ('orphan_other_idp', ["has no provider (orphan of 'oauth2:https://gone.example')",
                          'Link to SSO attaches it']),
])
def test_name_conflict_audit_and_log_name_the_state_and_the_remedy(
        app, providers, state, says, caplog):
    import logging
    with app.app_context():
        a_name = db.session.get(SSOProvider, providers.a).name
        b_name = db.session.get(SSOProvider, providers.b).name
    name = _name()
    _state(app, providers, state, name)
    caplog.set_level(logging.WARNING)
    assert _login(app, providers.b, name, {'sub': 'sub-new'}) == (None, 'sso_username_conflict')
    details = _last_audit(app, 'login_failure', name)
    for text in says:
        text = text.format(a=a_name, b=b_name)
        assert text in details, details
        assert text in caplog.text, caplog.text


def test_no_rule_and_no_default_role_is_its_own_code(app, providers):
    with app.app_context():
        p = db.session.get(SSOProvider, providers.b)
        p.role_mapping, p.default_role = None, None
        db.session.commit()
    assert _login(app, providers.b, _name(), {'sub': 'sub-n'}) == (None, 'sso_no_default_role')
    with app.app_context():
        db.session.get(SSOProvider, providers.b).role_mapping = '{"grp-x": "admin"}'
        db.session.commit()
    assert _login(app, providers.b, _name(), {'sub': 'sub-m', 'groups': ['y']}) == (None, 'sso_unmapped')


# ── 4. Same IdP ─────────────────────────────────────────────────────────────

def test_oidc_orphan_keyed_by_userinfo_is_taken_back_once_the_issuer_is_set(app, providers):
    """Deleted without an issuer (key = UserInfo URL), recreated with one."""
    name = _name()
    _add(app, username=name, auth_source='oauth2', sso_orphan_of='oauth2:https://c.example/userinfo',
         sso_external_id='sub-c', password_hash=NOPASS)
    other = providers(oauth2_issuer='https://c2.example', oauth2_userinfo_url='https://c2.example/userinfo')
    assert _login(app, other, name, {'sub': 'sub-c'}) == (None, 'sso_username_conflict')
    same = providers(oauth2_issuer='https://c.example', oauth2_userinfo_url='https://c.example/userinfo/')
    assert _login(app, same, name, {'sub': 'sub-c'}) == (name, None)


def _ldap_orphan(app, name, external_id, base='ou=people,dc=example,dc=com'):
    return _add(app, username=name, auth_source='ldap', sso_provider_id=None,
                sso_orphan_of=f'ldap:dc1.example.com|{base}', sso_external_id=external_id,
                password_hash=NOPASS)


@pytest.mark.parametrize('uid_attr', [None, 'entryUUID', 'objectGUID'])
def test_ldap_orphan_with_a_directory_unique_id_is_taken_back_through_another_host(
        app, providers, uid_attr):
    name = _name()
    guid = uuid.uuid4()
    ext = guid.hex if uid_attr == 'objectGUID' else str(guid)
    _ldap_orphan(app, name, ext)
    pid = providers(provider_type='ldap', ldap_server='10.0.0.7', ldap_uid_attr=uid_attr,
                    ldap_base_dn='OU=People,DC=example,DC=com')
    assert _login(app, pid, name, {'uid': ext, 'dn': f'uid={name},ou=people,dc=example,dc=com'}) \
        == (name, None)


@pytest.mark.parametrize('case', ['dn_fallback', 'other_base_dn', 'custom_uid_attr'])
def test_ldap_orphan_is_not_taken_back_through_another_host_without_a_unique_id(
        app, providers, case):
    name = _name()
    dn = f'uid={name},ou=people,dc=example,dc=com'
    ext = dn if case == 'dn_fallback' else str(uuid.uuid4())
    _ldap_orphan(app, name, ext)
    pid = providers(provider_type='ldap', ldap_server='dc2.example.com',
                    ldap_uid_attr='uid' if case == 'custom_uid_attr' else None,
                    ldap_base_dn='dc=other,dc=com' if case == 'other_base_dn'
                    else 'ou=people,dc=example,dc=com')
    data = {'dn': dn} if case == 'dn_fallback' else {'uid': ext, 'dn': dn}
    assert _login(app, pid, name, data) == (None, 'sso_username_conflict')
    # Control: the same host takes it back whatever its id.
    same = providers(provider_type='ldap', ldap_server='dc1.example.com',
                     ldap_uid_attr='uid' if case == 'custom_uid_attr' else None,
                     ldap_base_dn='dc=other,dc=com' if case == 'other_base_dn'
                     else 'ou=people,dc=example,dc=com')
    if case != 'other_base_dn':
        assert _login(app, same, name, data) == (name, None)
