"""Which providers open an account, and how an administrator attaches one.

An account is opened by the providers it is attached to, each with one stable
identity (OIDC Core 1.0 §5.7: only ``iss`` + ``sub`` identify the End-User).
Attaching a provider is the explicit, audited way to let it open any account;
a sign-in never takes an account by name or e-mail, and never creates a second
account in silence when one it may not open owns the presented e-mail. The
accounts are written as 2.254 held them and given the rows the upgrade gives.
"""
import uuid

import pytest

from models import db, User, AuditLog
from models.sso import SSOProvider
from tests.sso_identity_support import ext, identities, identity_for, legacy_user, prov, several_per_type

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
    # Two OIDC providers: what binds an account to its provider, not to its type
    with several_per_type(app):
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
        u = legacy_user(**kw)
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


def _link(app, client, uid, pid, **body):
    """What Link to SSO did in one call: attach ``pid``, or reset the identity of the
    attachment the account already has to it."""
    with app.app_context():
        row = identity_for(db.session.get(User, uid), pid)
        row_id = row.id if row is not None else None
    if row_id is None:
        return client.post(f'/api/v2/users/{uid}/sso-identities', json=dict(body, provider_id=pid))
    return client.post(f'/api/v2/users/{uid}/sso-identities/{row_id}/reset')


def _detach(app, client, uid, pid):
    with app.app_context():
        row_id = identity_for(db.session.get(User, uid), pid).id
    return client.delete(f'/api/v2/users/{uid}/sso-identities/{row_id}')


def _ok(r):
    assert r.status_code in (200, 201), r.get_json()
    return r


def _count(app, **filters):
    with app.app_context():
        return User.query.filter_by(**filters).count()


# ── 1. Link to SSO works on every account ───────────────────────────────────

def _state(app, providers, state, name):
    """An account in ``state`` with respect to provider B; returns its id."""
    a = providers.a
    if state == 'local_password':
        return _add(app, username=name, password_hash='hash-x')
    if state == 'unlinked_no_password':
        # What Unlink SSO leaves on an account that never had a password.
        return _add(app, username=name, password_hash=NOPASS,
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
    with app.app_context():
        before = [r for r in identities(db.session.get(User, uid)) if r[0] != providers.b]
    _ok(_link(app, auth_client, uid, providers.b))
    assert _login(app, providers.b, name, {'sub': 'sub-new'}) == (name, None)
    with app.app_context():
        u = db.session.get(User, uid)
        assert identity_for(u, providers.b).external_id == 'sub-new'
        # The rows it had for other providers stay as they were
        assert [r for r in identities(u) if r[0] != providers.b] == before
        if state == 'local_password':
            assert u.password_hash == 'hash-x'
        else:
            assert u.password_hash == NOPASS and u.force_password_change is False
    if state == 'other_provider':
        # Attached, not moved: its first provider still opens it by its own identity.
        assert _login(app, providers.a, name, {'sub': 'sub-at-a'}) == (name, None)


def test_relinked_account_without_password_is_not_asked_for_one(app, providers, auth_client):
    """Detach the last provider, then attach one: the SSO session is not confined to a
    password change."""
    name = _name()
    uid = _state(app, providers, 'other_provider', name)
    _ok(_detach(app, auth_client, uid, providers.a))
    _ok(_link(app, auth_client, uid, providers.b))
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
    r = _ok(_link(app, auth_client, uid, providers.b))
    assert held.get('/api/v2/certificates').status_code == 401
    assert auth_client.get('/api/v2/certificates').status_code == 200
    assert r.get_json()['meta']['other_sessions_closed'] in (1, None)
    action = 'user_sso_reset' if state == 'same_provider_other_identity' else 'user_sso_attach'
    assert 'other session' in _last_audit(app, action, name)


def test_link_that_changes_nothing_keeps_the_account_sessions(app, providers, auth_client):
    name = _name()
    uid = _add(app, username=name, auth_source='oauth2', sso_provider_id=providers.b,
               sso_external_id=None, password_hash=NOPASS)
    held = _open_session(app, uid, name)
    r = _link(app, auth_client, uid, providers.b)
    assert r.status_code == 200 and r.get_json()['meta']['other_sessions_closed'] == 0
    assert held.get('/api/v2/certificates').status_code == 200


def test_link_keeps_a_password_change_an_account_with_a_password_owes(app, providers, auth_client):
    name = _name()
    uid = _add(app, username=name, password_hash='hash-y',
               force_password_change=True)
    _ok(_link(app, auth_client, uid, providers.b))
    with app.app_context():
        u = db.session.get(User, uid)
        assert u.password_hash == 'hash-y' and u.force_password_change is True


@pytest.mark.parametrize('state, origin', [
    ('local_password', 'before: a local account'),
    ('other_provider', "before: provider '{a}', identity 'sub-at-a'"),
    ('orphan_unknown_idp', 'before: no provider (its IdP is unknown), identity'),
    ('orphan_other_idp', "before: no provider (orphan of 'oauth2:https://gone.example')"),
    ('same_provider_other_identity', "Reset identity 'sub-before'"),
])
def test_link_audit_says_where_the_account_comes_from(app, providers, auth_client, state, origin):
    with app.app_context():
        a_name = db.session.get(SSOProvider, providers.a).name
    name = _name()
    uid = _state(app, providers, state, name)
    _ok(_link(app, auth_client, uid, providers.b))
    action = 'user_sso_reset' if state == 'same_provider_other_identity' else 'user_sso_attach'
    details = _last_audit(app, action, name)
    assert origin.format(a=a_name) in details, details


def test_link_audit_bounds_the_former_identity(app, providers, auth_client):
    name = _name()
    long_id = 'x' * 255  # the widest identity the column holds
    uid = _add(app, username=name, auth_source='oauth2', sso_provider_id=providers.a,
               sso_external_id=long_id, password_hash=NOPASS)
    _ok(_link(app, auth_client, uid, providers.b))
    details = _last_audit(app, 'user_sso_attach', name)
    assert 'x' * 64 in details and 'x' * 65 not in details, details


def test_an_unlinked_account_without_password_is_still_not_taken_by_name(app, providers, auth_client):
    """Detaching its last provider makes the account local: no provider takes it back
    without being attached."""
    name = _name()
    uid = _state(app, providers, 'other_provider', name)
    _ok(_detach(app, auth_client, uid, providers.a))
    for pid in (providers.a, providers.b):
        assert _login(app, pid, name, {'sub': 'sub-z'}) == (None, 'sso_username_conflict')


# ── 2. No silent second account ─────────────────────────────────────────────

@pytest.mark.parametrize('flag', [False, 'false'])
def test_unverified_email_of_an_admin_linked_account_is_refused_not_duplicated(
        app, providers, auth_client, flag):
    """(a) Linked by an administrator, other name, the IdP says the e-mail is unverified."""
    name, idp_name = _name(), _name()
    uid = _add(app, username=name, email=f'{name}@corp.example',
               password_hash='hash')
    _ok(_link(app, auth_client, uid, providers.b))
    got = _login(app, providers.b, idp_name, {'sub': 'sub-u', 'email_verified': flag},
                 email=f'{name}@corp.example')
    assert got == (None, 'sso_email_conflict')
    assert _count(app, username=idp_name) == 0
    with app.app_context():
        assert ext(db.session.get(User, uid)) is None
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
    assert 'have the IdP verify' in details and 'attach provider' not in details, details
    # The text is true: attaching the provider changes nothing, the refusal stands.
    _ok(_link(app, auth_client, uid, providers.b))
    assert _login(app, providers.b, idp_name, ext, email=f'{name}@corp.example') == \
        (None, 'sso_email_conflict')


def test_unverified_email_of_an_account_of_another_provider_says_attach_this_one(app, providers):
    with app.app_context():
        a_name = db.session.get(SSOProvider, providers.a).name
    name, idp_name = _name(), _name()
    _add(app, username=name, email=f'{name}@corp.example', auth_source='oauth2',
         sso_provider_id=providers.a, sso_external_id='sub-a', password_hash=NOPASS)
    assert _login(app, providers.b, idp_name, {'sub': 'sub-b', 'email_verified': False},
                  email=f'{name}@corp.example') == (None, 'sso_email_conflict')
    details = _last_audit(app, 'login_failure', name)
    assert repr(a_name) in details and 'attach provider' in details, details
    assert 'keep opening it' in details and 'have the IdP verify' not in details, details


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
    assert repr(a_name) in details and 'attach provider' in details, details


def test_another_person_sharing_the_email_signs_in_once_an_account_is_created_and_attached(
        app, providers, auth_client):
    """The remedy the refusal names for a shared mailbox: no setting, an explicit account."""
    name, idp_name = _name(), _name()
    _add(app, username=name, email=f'{name}@corp.example', auth_source='oauth2',
         sso_provider_id=providers.a, sso_external_id='sub-a', password_hash=NOPASS)
    assert _login(app, providers.b, idp_name, {'sub': 'sub-b'},
                  email=f'{name}@corp.example') == (None, 'sso_email_conflict')
    assert 'attach this provider to it, removing its local password' in \
        _last_audit(app, 'login_failure', name)
    r = auth_client.post('/api/v2/users', json={'username': idp_name, 'email': f'{name}@corp.example',
                                                 'password': 'Shared-Mailbox-9x!', 'role': 'viewer'})
    assert r.status_code in (200, 201), r.get_json()
    uid = r.get_json()['data']['id']
    _ok(_link(app, auth_client, uid, providers.b))
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
    _ok(_link(app, auth_client, uid, providers.b, remove_password=True))
    with app.app_context():
        u = db.session.get(User, uid)
        assert (u.password_hash, u.force_password_change, u.password_reset_token) == \
            (NOPASS, False, None)
    assert 'local password removed' in _last_audit(app, 'user_sso_attach', idp_name)
    assert app.test_client().post('/api/v2/auth/login', json=login).status_code == 401
    assert _login(app, providers.b, idp_name, {'sub': 'sub-s'},
                  email=f'{name}@corp.example') == (idp_name, None)
    held = _open_session(app, uid, idp_name).get('/api/v2/certificates')
    assert held.status_code == 200 and not held.get_json().get('must_change_password')


def test_removing_the_password_with_an_attachment_closes_the_account_sessions(
        app, providers, auth_client):
    """The password goes only with an attachment now; both end what the account had opened."""
    name = _name()
    uid = _add(app, username=name, auth_source='oauth2', sso_provider_id=providers.a,
               sso_external_id=None, password_hash='hash-z')
    held = _open_session(app, uid, name)
    r = _link(app, auth_client, uid, providers.b, remove_password=True)
    assert r.status_code == 201 and r.get_json()['meta']['other_sessions_closed'] in (1, None)
    assert held.get('/api/v2/certificates').status_code == 401
    with app.app_context():
        assert db.session.get(User, uid).password_hash == NOPASS


@pytest.mark.parametrize('value', ['yes', 1, None])
def test_remove_password_must_be_a_boolean(app, providers, auth_client, value):
    name = _name()
    uid = _add(app, username=name, password_hash='hash-q')
    r = _link(app, auth_client, uid, providers.b, remove_password=value)
    assert r.status_code == 400
    with app.app_context():
        u = db.session.get(User, uid)
        assert (u.password_hash, identities(u)) == ('hash-q', [])


def test_email_of_a_local_account_still_gives_a_distinct_sso_account(app, providers):
    """E-mail is unique among local accounts only (#136): an SSO account may share it."""
    name, idp_name = _name(), _name()
    _add(app, username=name, email=f'{name}@corp.example', password_hash='hash')
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
    ('local_password', ['is a local account', "attach provider '{b}' to the account"]),
    ('other_provider', ["is attached to provider '{a}'", "attach provider '{b}' to the account",
                        "the providers it is attached to keep opening it"]),
    ('same_provider_other_identity', ["bound to another identity of '{b}' ('sub-before')",
                                      "reset the identity of its '{b}' attachment"]),
    ('orphan_unknown_idp', ['has no provider (its IdP is unknown)',
                            "attach provider '{b}' to the account"]),
    ('orphan_other_idp', ["has no provider (orphan of 'oauth2:https://gone.example')",
                          "attach provider '{b}' to the account"]),
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
    """OIDC Core §5.7: iss and sub together identify the user. An orphan recorded under a
    UserInfo URL is not the issuer's: attaching the provider lets it in, a sign-in does not."""
    name = _name()
    uid = _add(app, username=name, auth_source='oauth2', sso_orphan_of='oauth2:https://c.example/userinfo',
               sso_external_id='sub-c', password_hash=NOPASS)
    with_issuer = providers(oauth2_issuer='https://c.example', oauth2_userinfo_url='https://c.example/userinfo')
    assert _login(app, with_issuer, name, {'sub': 'sub-c'}) == (None, 'sso_username_conflict')
    _ok(_link(app, auth_client, uid, with_issuer))
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


@pytest.fixture
def reset_mail(monkeypatch):
    """Password reset available; the fixture lists who was sent a link."""
    import api.v2.auth as auth_api
    from services.notification_service import NotificationService
    sent = []
    monkeypatch.setattr(auth_api, '_is_email_configured', lambda: True)
    monkeypatch.setattr(auth_api, 'get_admin_canonical_origin', lambda: 'https://ucm.example.test')
    monkeypatch.setattr(NotificationService, 'send_email',
                        staticmethod(lambda **kw: sent.append(kw['context']['username'])))
    return sent


def _forgot(app, email):
    r = app.test_client().post('/api/v2/auth/forgot-password', json={'email': email})
    assert r.status_code == 200 and 'If an account' in r.get_json()['message']


@pytest.mark.parametrize('fields, sent', [
    ({'auth_source': 'oauth2', 'password_hash': NOPASS}, False),
    ({'auth_source': 'oauth2', 'password_hash': 'kept-hash'}, True),
    ({'auth_source': 'local', 'password_hash': NOPASS, 'force_password_change': True}, True),
    ({'auth_source': 'local', 'password_hash': 'local-hash'}, True),
], ids=['sso-no-password', 'sso-kept-password', 'unlinked-no-password', 'local'])
def test_forgot_password_sends_no_link_to_an_sso_account_without_password(
        app, providers, reset_mail, fields, sent):
    """An account the provider alone opens gets no password by e-mail; the answer is the same."""
    name = _name()
    if fields['auth_source'] != 'local':
        fields = dict(fields, sso_provider_id=providers.b)
    uid = _add(app, username=name, **fields)
    _forgot(app, f'{name}@corp.example')
    assert reset_mail == ([name] if sent else [])
    with app.app_context():
        assert bool(db.session.get(User, uid).password_reset_token) is sent


def test_forgot_password_reaches_the_local_account_that_shares_the_email(app, providers, reset_mail):
    sso_name, local_name, email = _name(), _name(), f'{_name()}@corp.example'
    _add(app, username=sso_name, email=email, auth_source='oauth2', sso_provider_id=providers.b,
         password_hash=NOPASS)
    _add(app, username=local_name, email=email, password_hash='local-hash')
    _forgot(app, email)
    assert reset_mail == [local_name]


def test_a_reset_token_sets_no_password_on_an_sso_account_without_one(app, providers):
    import hashlib
    from datetime import timedelta
    from utils.datetime_utils import utc_now
    name, token = _name(), 'token-of-an-sso-only-account'
    uid = _add(app, username=name, auth_source='oauth2', sso_provider_id=providers.b,
               password_hash=NOPASS, password_reset_token=hashlib.sha256(token.encode()).hexdigest(),
               password_reset_expires=utc_now() + timedelta(hours=1))
    r = app.test_client().post('/api/v2/auth/reset-password',
                               json={'token': token, 'password': 'Brand-New-Passw0rd!x'})
    assert r.status_code == 400 and r.get_json()['message'] == 'Invalid or expired reset token'
    with app.app_context():
        assert db.session.get(User, uid).password_hash == NOPASS


def test_removing_the_password_forgets_a_generated_initial_password(app, providers, auth_client):
    import json
    from auth.initial_admin import MARKER_KEY
    from models import SystemConfig
    name = _name()
    uid = _add(app, username=name, password_hash='generated-hash', role='admin')
    with app.app_context():
        before = SystemConfig.query.filter_by(key=MARKER_KEY).first()
        assert before is None, 'this test owns the marker'
        db.session.add(SystemConfig(key=MARKER_KEY, value=json.dumps({'user_id': uid})))
        db.session.commit()
    try:
        _ok(_link(app, auth_client, uid, providers.b, remove_password=True))
        with app.app_context():
            assert SystemConfig.query.filter_by(key=MARKER_KEY).first() is None
    finally:
        with app.app_context():
            SystemConfig.query.filter_by(key=MARKER_KEY).delete()
            db.session.commit()


def test_an_administrator_cannot_remove_the_password_of_their_own_account(app, providers, auth_client):
    with app.app_context():
        me = User.query.filter_by(username='admin').one()
        uid, before = me.id, (me.password_hash, identities(me))
    try:
        r = _link(app, auth_client, uid, providers.b, remove_password=True)
        assert r.status_code == 400 and 'your own account' in r.get_json()['message']
        with app.app_context():
            me = db.session.get(User, uid)
            assert (me.password_hash, identities(me)) == before
    finally:  # the shared admin account stays usable whatever the answer was
        with app.app_context():
            me = db.session.get(User, uid)
            me.password_hash = before[0]
            me.sso_identities.clear()
            db.session.commit()


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
    assert 'no provider' in details and 'attach provider' in details, details


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
        assert prov(db.session.get(User, uid)) == providers.b


def test_forgot_password_sends_no_link_to_an_sso_account_older_than_its_auth_source(
        app, providers, reset_mail):
    """Local by its column, without password and owing no change: its provider alone opens it."""
    name = _name()
    _add(app, username=name, password_hash=NOPASS, force_password_change=False)
    _forgot(app, f'{name}@corp.example')
    assert reset_mail == []


def test_forgot_password_reaches_the_active_account_behind_an_inactive_one(app, providers, reset_mail):
    gone, name = _name(), _name()
    email = f'{name}@corp.example'
    _add(app, username=gone, email=email, auth_source='oauth2', sso_provider_id=providers.b,
         password_hash='old-hash', active=False)
    _add(app, username=name, email=email, password_hash='hash-l')
    _forgot(app, email)
    assert reset_mail == [name]
