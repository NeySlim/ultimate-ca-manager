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
    name = _name()
    uid = _state(app, providers, 'other_provider', name)
    assert auth_client.post(f'/api/v2/users/{uid}/unlink-sso').status_code == 200
    assert auth_client.post(f'/api/v2/users/{uid}/link-sso',
                            json={'provider_id': providers.b}).status_code == 200
    assert _login(app, providers.b, name, {'sub': 'sub-b'}) == (name, None)
    # Opened after the link, which closes the sessions it finds.
    r = _open_session(app, uid, name).get('/api/v2/certificates')
    assert r.status_code == 200, r.get_json()
    assert not (r.get_json() or {}).get('must_change_password'), r.get_json()


def _open_session(app, uid, name):
    """A client holding a session of the account, opened now."""
    from utils.datetime_utils import utc_now
    with app.app_context():
        u = db.session.get(User, uid)
        role, version = u.role, u.session_version or 0
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(user_id=uid, username=name, role=role, auth_method='sso', session_version=version,
                 login_time=utc_now().isoformat(), last_activity=utc_now().isoformat())
    return c


@pytest.mark.parametrize('state', ['local_password', 'other_provider', 'same_provider_other_identity'])
def test_link_that_changes_the_owner_closes_the_account_sessions(app, providers, auth_client, state):
    """Whoever held the former identity keeps no session once the account is moved or reset."""
    name = _name()
    uid = _state(app, providers, state, name)
    held = _open_session(app, uid, name)
    assert held.get('/api/v2/certificates').status_code == 200
    r = auth_client.post(f'/api/v2/users/{uid}/link-sso', json={'provider_id': providers.b})
    assert r.status_code == 200, r.get_json()
    assert held.get('/api/v2/certificates').status_code == 401
    assert auth_client.get('/api/v2/certificates').status_code == 200
    assert 'sessions closed' in _last_audit(app, 'user_link_sso', name)


def test_link_that_changes_nothing_keeps_the_account_sessions(app, providers, auth_client):
    name = _name()
    uid = _add(app, username=name, auth_source='oauth2', sso_provider_id=providers.b,
               sso_external_id=None, password_hash=NOPASS)
    held = _open_session(app, uid, name)
    r = auth_client.post(f'/api/v2/users/{uid}/link-sso', json={'provider_id': providers.b})
    assert r.status_code == 200
    assert 'sessions closed' not in _last_audit(app, 'user_link_sso', name)
    assert held.get('/api/v2/certificates').status_code == 200


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


def test_unverified_email_of_an_orphan_of_this_idp_names_the_real_cause(app, providers, auth_client):
    """The orphan is this provider's to adopt: only a verified e-mail matches it, linking does not."""
    name, idp_name = _name(), _name()
    uid = _add(app, username=name, email=f'{name}@corp.example', auth_source='oauth2',
               sso_provider_id=None, sso_orphan_of='oauth2:https://b.example',
               sso_external_id=None, password_hash=NOPASS)
    ext = {'sub': 'sub-o', 'email_verified': False}
    assert _login(app, providers.b, idp_name, ext, email=f'{name}@corp.example') == \
        (None, 'sso_email_conflict')
    details = _last_audit(app, 'login_failure', name)
    assert 'have the IdP verify' in details and 'Link to SSO' not in details, details
    # The text is true: linking it changes nothing, the refusal stands.
    assert auth_client.post(f'/api/v2/users/{uid}/link-sso',
                            json={'provider_id': providers.b}).status_code == 200
    assert _login(app, providers.b, idp_name, ext, email=f'{name}@corp.example') == \
        (None, 'sso_email_conflict')


def test_unverified_email_of_an_account_of_another_provider_says_link_moves_it(app, providers):
    with app.app_context():
        a_name = db.session.get(SSOProvider, providers.a).name
    name, idp_name = _name(), _name()
    _add(app, username=name, email=f'{name}@corp.example', auth_source='oauth2',
         sso_provider_id=providers.a, sso_external_id='sub-a', password_hash=NOPASS)
    assert _login(app, providers.b, idp_name, {'sub': 'sub-b', 'email_verified': False},
                  email=f'{name}@corp.example') == (None, 'sso_email_conflict')
    details = _last_audit(app, 'login_failure', name)
    assert repr(a_name) in details and 'Link to SSO moves it' in details, details
    assert 'have the IdP verify' not in details, details


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


@pytest.mark.parametrize('orphan_of', ['oauth2:https://okta-gone.example', None])
@pytest.mark.parametrize('verified', [True, False])
def test_email_of_an_orphan_of_another_or_unknown_idp_is_refused_not_duplicated(
        app, providers, orphan_of, verified):
    """A provider deleted, another created, another name sent: no second account."""
    name, idp_name = _name(), _name()
    _add(app, username=name, email=f'{name}@corp.example', auth_source='oauth2',
         sso_provider_id=None, sso_orphan_of=orphan_of, sso_external_id='sub-old',
         password_hash=NOPASS)
    got = _login(app, providers.b, idp_name, {'sub': 'sub-new', 'email_verified': verified},
                 email=f'{name}@corp.example')
    assert got == (None, 'sso_email_conflict')
    assert _count(app, username=idp_name) == 0
    assert _count(app, email=f'{name}@corp.example') == 1
    details = _last_audit(app, 'login_failure', name)
    assert 'no provider' in details and 'Link to SSO attaches it' in details, details


def test_email_of_a_bound_orphan_of_this_idp_does_not_block_another_identity(app, providers):
    """Two identities of one IdP sharing an e-mail keep an account each, orphaned or not."""
    name, idp_name = _name(), _name()
    _add(app, username=name, email=f'{name}@corp.example', auth_source='oauth2',
         sso_provider_id=None, sso_orphan_of='oauth2:https://b.example', sso_external_id='sub-old',
         password_hash=NOPASS)
    assert _login(app, providers.b, idp_name, {'sub': 'sub-new'},
                  email=f'{name}@corp.example') == (idp_name, None)
    assert _count(app, email=f'{name}@corp.example') == 2


def test_email_of_an_unbound_orphan_of_this_idp_is_still_taken_back(app, providers):
    """The orphan check leaves this IdP's own orphans to the adoption that precedes it."""
    name, idp_name = _name(), _name()
    uid = _add(app, username=name, email=f'{name}@corp.example', auth_source='oauth2',
               sso_provider_id=None, sso_orphan_of='oauth2:https://b.example',
               sso_external_id=None, password_hash=NOPASS)
    assert _login(app, providers.b, idp_name, {'sub': 'sub-o'},
                  email=f'{name}@corp.example') == (name, None)
    with app.app_context():
        assert db.session.get(User, uid).sso_provider_id == providers.b


def test_another_person_sharing_the_email_signs_in_once_an_account_is_created_and_linked(
        app, providers, auth_client):
    """The remedy the refusal names for a shared mailbox: no setting, an explicit account."""
    name, idp_name = _name(), _name()
    _add(app, username=name, email=f'{name}@corp.example', auth_source='oauth2',
         sso_provider_id=providers.a, sso_external_id='sub-a', password_hash=NOPASS)
    assert _login(app, providers.b, idp_name, {'sub': 'sub-b'},
                  email=f'{name}@corp.example') == (None, 'sso_email_conflict')
    assert 'link it, removing its local password' in _last_audit(app, 'login_failure', name)
    r = auth_client.post('/api/v2/users', json={'username': idp_name, 'email': f'{name}@corp.example',
                                                 'password': 'Shared-Mailbox-9x!', 'role': 'viewer'})
    assert r.status_code in (200, 201), r.get_json()
    uid = r.get_json()['data']['id']
    assert auth_client.post(f'/api/v2/users/{uid}/link-sso',
                            json={'provider_id': providers.b}).status_code == 200
    assert _login(app, providers.b, idp_name, {'sub': 'sub-b'},
                  email=f'{name}@corp.example') == (idp_name, None)


def _other_provider_owns(app, providers, name):
    _add(app, username=name, email=f'{name}@corp.example', auth_source='oauth2',
         sso_provider_id=providers.a, sso_external_id='sub-a', password_hash=NOPASS)


def test_an_identity_the_mapping_refuses_learns_nothing_of_the_email_owner(app, providers):
    """The e-mail refusal falls only where an account was about to be created."""
    with app.app_context():
        db.session.get(SSOProvider, providers.b).role_mapping = '{"grp-x": "admin"}'
        db.session.get(SSOProvider, providers.b).default_role = None
        db.session.commit()
    name, idp_name = _name(), _name()
    _other_provider_owns(app, providers, name)
    got = _login(app, providers.b, idp_name, {'sub': 'sub-b', 'groups': ['y']},
                 email=f'{name}@corp.example')
    assert got == (None, 'sso_unmapped')
    assert _count(app, username=idp_name) == 0


def test_a_provider_without_auto_create_answers_as_before_on_a_taken_email(
        app, providers, monkeypatch):
    with app.app_context():
        db.session.get(SSOProvider, providers.b).auto_create_users = False
        db.session.commit()
    name, idp_name = _name(), _name()
    _other_provider_owns(app, providers, name)
    got = _login(app, providers.b, idp_name, {'sub': 'sub-b'}, email=f'{name}@corp.example')
    assert got == (None, 'auto_create_disabled')
    # The LDAP door keeps hiding the provisioning state behind its generic answer.
    from api.v2.sso import ldap_routes
    lid = providers(provider_type='ldap', enabled=True, ldap_server='ldap.example.test',
                    ldap_base_dn='dc=example', auto_create_users=False)
    entry = {'dn': f'uid={idp_name},dc=example', 'uid': str(uuid.uuid4()),
             'email': f'{name}@corp.example'}
    monkeypatch.setattr(ldap_routes, '_ldap_authenticate_user',
                        lambda _p, username, _pw, before_bind=None: (dict(entry, username=username), None))
    r = app.test_client().post('/api/v2/sso/ldap/login',
                               json={'username': idp_name, 'password': 'pw', 'provider_id': lid})
    assert (r.status_code, r.get_json()['message']) == (401, 'Invalid credentials')


def test_link_can_remove_the_local_password_the_account_was_created_with(app, providers, auth_client):
    """The shared-mailbox remedy leaves no administrator-chosen password outside the IdP."""
    from datetime import timedelta
    from utils.datetime_utils import utc_now
    name, idp_name, pw = _name(), _name(), 'Shared-Mailbox-9x!'
    r = auth_client.post('/api/v2/users', json={'username': idp_name, 'email': f'{name}@corp.example',
                                                 'password': pw, 'role': 'viewer'})
    assert r.status_code in (200, 201), r.get_json()
    uid = r.get_json()['data']['id']
    with app.app_context():
        u = db.session.get(User, uid)
        u.force_password_change = True
        u.password_reset_token, u.password_reset_expires = 'pending', utc_now() + timedelta(hours=1)
        db.session.commit()
    login = {'username': idp_name, 'password': pw}
    assert app.test_client().post('/api/v2/auth/login', json=login).status_code == 200
    r = auth_client.post(f'/api/v2/users/{uid}/link-sso',
                         json={'provider_id': providers.b, 'remove_password': True})
    assert r.status_code == 200, r.get_json()
    with app.app_context():
        u = db.session.get(User, uid)
        assert (u.password_hash, u.force_password_change, u.password_reset_token) == \
            (NOPASS, False, None)
    assert 'local password removed' in _last_audit(app, 'user_link_sso', idp_name)
    assert app.test_client().post('/api/v2/auth/login', json=login).status_code == 401
    assert _login(app, providers.b, idp_name, {'sub': 'sub-s'},
                  email=f'{name}@corp.example') == (idp_name, None)
    held = _open_session(app, uid, idp_name).get('/api/v2/certificates')
    assert held.status_code == 200 and not held.get_json().get('must_change_password')


@pytest.fixture
def mailbox(app, monkeypatch):
    from api.v2 import auth as auth_api
    from services.notification_service import NotificationService
    sent = []
    monkeypatch.setattr(auth_api, '_is_email_configured', lambda: True)
    monkeypatch.setattr(auth_api, 'get_admin_canonical_origin', lambda: 'https://pki.example.test')
    monkeypatch.setattr(NotificationService, 'send_email',
                        staticmethod(lambda **kw: sent.append(kw) or True))
    return sent


def _forgot(app, email):
    return app.test_client().post('/api/v2/auth/forgot-password', json={'email': email})


def test_the_password_reset_never_gives_a_password_to_an_sso_account(
        app, providers, auth_client, mailbox):
    """After Link to SSO removes the password, no password door opens the account."""
    name = _name()
    uid = _add(app, username=name, auth_source='local', password_hash='hash-r')
    assert auth_client.post(f'/api/v2/users/{uid}/link-sso', json={
        'provider_id': providers.b, 'remove_password': True}).status_code == 200
    r = _forgot(app, f'{name}@corp.example')
    assert r.status_code == 200 and 'If an account' in r.get_json()['message']
    assert mailbox == []
    with app.app_context():
        assert db.session.get(User, uid).password_reset_token is None


def test_a_reset_token_issued_before_the_link_no_longer_sets_a_password(
        app, providers, auth_client, mailbox):
    name, pw = _name(), 'Reset-After-Link-9x!'
    # What Unlink SSO leaves: no password, a change owed; the reset is its way back.
    uid = _add(app, username=name, auth_source='local', password_hash=NOPASS,
               force_password_change=True)
    assert _forgot(app, f'{name}@corp.example').status_code == 200
    token = mailbox[0]['context']['reset_url'].split('token=')[1]
    assert auth_client.post(f'/api/v2/users/{uid}/link-sso',
                            json={'provider_id': providers.b}).status_code == 200
    r = app.test_client().post('/api/v2/auth/reset-password', json={'token': token, 'password': pw})
    assert (r.status_code, r.get_json()['message']) == (400, 'Invalid or expired reset token')
    with app.app_context():
        assert db.session.get(User, uid).password_hash == NOPASS
    assert app.test_client().post('/api/v2/auth/login',
                                  json={'username': name, 'password': pw}).status_code == 401


def test_the_reset_reaches_the_local_account_sharing_an_sso_account_email(
        app, providers, mailbox):
    name, other = _name(), _name()
    email = f'{name}@corp.example'
    _add(app, username=other, email=email, auth_source='oauth2', sso_provider_id=providers.b,
         sso_external_id='sub-x', password_hash=NOPASS)
    _add(app, username=name, email=email, auth_source='local', password_hash='hash-l')
    assert _forgot(app, email).status_code == 200
    assert [m['context']['username'] for m in mailbox] == [name]


def test_removing_the_password_closes_sessions_of_an_account_that_does_not_move(
        app, providers, auth_client):
    name = _name()
    uid = _add(app, username=name, auth_source='oauth2', sso_provider_id=providers.b,
               sso_external_id=None, password_hash='hash-z')
    held = _open_session(app, uid, name)
    r = auth_client.post(f'/api/v2/users/{uid}/link-sso',
                         json={'provider_id': providers.b, 'remove_password': True})
    assert r.status_code == 200
    assert held.get('/api/v2/certificates').status_code == 401


@pytest.mark.parametrize('value', ['yes', 1, None])
def test_remove_password_must_be_a_boolean(app, providers, auth_client, value):
    name = _name()
    uid = _add(app, username=name, auth_source='local', password_hash='hash-q')
    r = auth_client.post(f'/api/v2/users/{uid}/link-sso',
                         json={'provider_id': providers.b, 'remove_password': value})
    assert r.status_code == 400
    with app.app_context():
        u = db.session.get(User, uid)
        assert (u.password_hash, u.sso_provider_id) == ('hash-q', None)


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
    ('other_provider', ["is linked to provider '{a}'", 'Link to SSO moves it',
                        "after which '{a}' no longer opens it"]),
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

def test_oidc_orphan_is_taken_back_under_its_exact_idp_key_only(app, providers, auth_client):
    """OIDC Core 5.7: iss and sub together identify the user. An orphan recorded under a
    UserInfo URL is not the issuer's: Link to SSO attaches it, a sign-in does not."""
    name = _name()
    uid = _add(app, username=name, auth_source='oauth2', sso_orphan_of='oauth2:https://c.example/userinfo',
               sso_external_id='sub-c', password_hash=NOPASS)
    with_issuer = providers(oauth2_issuer='https://c.example', oauth2_userinfo_url='https://c.example/userinfo')
    assert _login(app, with_issuer, name, {'sub': 'sub-c'}) == (None, 'sso_username_conflict')
    assert auth_client.post(f'/api/v2/users/{uid}/link-sso', json={'provider_id': with_issuer}).status_code == 200
    assert _login(app, with_issuer, name, {'sub': 'sub-c'}) == (name, None)
    # Control: the provider recorded under that same key takes its orphan back by itself
    other = _name()
    _add(app, username=other, auth_source='oauth2', sso_orphan_of='oauth2:https://d.example/userinfo',
         sso_external_id='sub-d', password_hash=NOPASS)
    same_key = providers(oauth2_issuer=None, oauth2_userinfo_url='https://d.example/userinfo')
    assert _login(app, same_key, other, {'sub': 'sub-d'}) == (other, None)


def test_unbound_orphan_keyed_by_a_shared_userinfo_is_not_taken_by_name(app, providers):
    """One UserInfo endpoint serves every tenant (Entra ID): only iss + sub may match."""
    name = _name()
    userinfo = 'https://graph.microsoft.com/oidc/userinfo'
    _add(app, username=name, role='admin', auth_source='oauth2', sso_provider_id=None,
         sso_orphan_of=f'oauth2:{userinfo}', sso_external_id=None, password_hash=NOPASS)
    tenant_b = providers(oauth2_issuer='https://login.microsoftonline.com/tenant-b/v2.0',
                         oauth2_userinfo_url=userinfo)
    assert _login(app, tenant_b, name, {'sub': 'attacker-sub'}) == (None, 'sso_username_conflict')
    assert _login(app, tenant_b, _name(), {'sub': 'attacker-sub-2'},
                  email=f'{name}@corp.example')[0] != name


def _ldap_orphan(app, name, external_id, base='ou=people,dc=example,dc=com'):
    return _add(app, username=name, auth_source='ldap', sso_provider_id=None,
                sso_orphan_of=f'ldap:dc1.example.com|{base}', sso_external_id=external_id,
                password_hash=NOPASS)


@pytest.mark.parametrize('uid_attr', [None, 'entryUUID', 'objectGUID'])
def test_ldap_orphan_is_not_taken_back_through_another_host_even_with_a_unique_id(
        app, providers, uid_attr):
    name = _name()
    guid = uuid.uuid4()
    ext = guid.hex if uid_attr == 'objectGUID' else str(guid)
    _ldap_orphan(app, name, ext)
    pid = providers(provider_type='ldap', ldap_server='10.0.0.7', ldap_uid_attr=uid_attr,
                    ldap_base_dn='OU=People,DC=example,DC=com')
    assert _login(app, pid, name, {'uid': ext, 'dn': f'uid={name},ou=people,dc=example,dc=com'}) \
        == (None, 'sso_username_conflict')


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


@pytest.mark.parametrize('fields, sent', [
    ({'auth_source': 'oauth2', 'password_hash': NOPASS}, False),
    ({'auth_source': 'local', 'password_hash': NOPASS, 'force_password_change': False}, False),
    ({'auth_source': 'oauth2', 'password_hash': 'kept-hash'}, True),
    ({'auth_source': 'local', 'password_hash': NOPASS, 'force_password_change': True}, True),
    ({'auth_source': 'local', 'password_hash': 'local-hash'}, True),
], ids=['sso-no-password', 'sso-before-auth-source', 'sso-kept-password', 'unlinked', 'local'])
def test_the_reset_link_goes_to_every_account_but_one_its_provider_alone_opens(
        app, providers, mailbox, fields, sent):
    """No password is handed to an account that has none and signs in through its provider;
    one that holds a password, or was unlinked to set one, keeps the reset."""
    name = _name()
    if fields['auth_source'] != 'local':
        fields = dict(fields, sso_provider_id=providers.b)
    uid = _add(app, username=name, **fields)
    r = _forgot(app, f'{name}@corp.example')
    assert r.status_code == 200 and 'If an account' in r.get_json()['message']
    assert [m['context']['username'] for m in mailbox] == ([name] if sent else [])
    with app.app_context():
        assert bool(db.session.get(User, uid).password_reset_token) is sent


def test_the_reset_reaches_the_active_account_behind_an_inactive_one(app, providers, mailbox):
    gone, name = _name(), _name()
    email = f'{name}@corp.example'
    _add(app, username=gone, email=email, auth_source='oauth2', sso_provider_id=providers.b,
         password_hash='old-hash', active=False)
    _add(app, username=name, email=email, auth_source='local', password_hash='hash-l')
    assert _forgot(app, email).status_code == 200
    assert [m['context']['username'] for m in mailbox] == [name]


def test_an_administrator_cannot_remove_the_password_of_their_own_account(app, providers, auth_client):
    with app.app_context():
        me = User.query.filter_by(username='admin').one()
        uid, before = me.id, (me.password_hash, me.auth_source, me.sso_provider_id)
    try:
        r = auth_client.post(f'/api/v2/users/{uid}/link-sso',
                             json={'provider_id': providers.b, 'remove_password': True})
        assert r.status_code == 400 and 'your own account' in r.get_json()['message']
        with app.app_context():
            me = db.session.get(User, uid)
            assert (me.password_hash, me.auth_source, me.sso_provider_id) == before
    finally:  # the shared admin account stays usable whatever the answer was
        with app.app_context():
            me = db.session.get(User, uid)
            me.password_hash, me.auth_source, me.sso_provider_id = before
            me.sso_external_id = None
            db.session.commit()
