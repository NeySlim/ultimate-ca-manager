"""An account opened by several providers, one row of user_sso_identities each.

A sign-in through provider P with stable identity S opens the account holding (P, S); no
sign-in attaches a provider to an existing account by a name or an e-mail another provider
sent: an administrator does (OIDC Core 1.0 §5.7). The database holds one account per (P, S)
and one row per (account, P) on both backends; a 2.254 database keeps every account's access.
"""
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError

from models import db, AuditLog, User, UserSSOIdentity
from models.sso import SSOProvider
from tests.sso_identity_support import identities, identity_for, legacy_user
from tests.upgrade_2254_support import BACKENDS, make_base

NOPASS = '!SSO_NO_PASSWORD!'
PREFIX = 'sid5'


def _name():
    return f'{PREFIX}{uuid.uuid4().hex[:8]}'


def _cleanup():
    from api.v2.users.crud import _purge_user_dependencies
    for (uid,) in User.query.filter(User.username.like(f'{PREFIX}%')).with_entities(User.id).all():
        _purge_user_dependencies(uid)
    User.query.filter(User.username.like(f'{PREFIX}%')).delete(synchronize_session=False)
    db.session.commit()


@pytest.fixture
def providers(app):
    """An OIDC and a SAML provider for two IdPs; ``providers(**fields)`` makes more."""
    made = []

    def make(**fields):
        with app.app_context():
            base = dict(name=f'{PREFIX}-{uuid.uuid4().hex[:6]}', provider_type='oauth2', enabled=False,
                        auto_create_users=True, default_role='viewer')
            base.update(fields)
            row = SSOProvider(**base)
            db.session.add(row)
            db.session.commit()
            made.append(row.id)
            return row.id

    with app.app_context():
        _cleanup()
    make.oidc = make(oauth2_issuer=f'https://oidc-{uuid.uuid4().hex[:6]}.example')
    make.saml = make(provider_type='saml', saml_entity_id=f'https://saml-{uuid.uuid4().hex[:6]}.example')
    yield make
    with app.app_context():
        assert _untrue_flags() == []
        _cleanup()
        UserSSOIdentity.query.filter(UserSSOIdentity.provider_id.in_(made)).delete(
            synchronize_session=False)
        SSOProvider.query.filter(SSOProvider.id.in_(made)).delete(synchronize_session=False)
        db.session.commit()


def _untrue_flags():
    """Accounts whose has_sso_identity says otherwise than their identity rows."""
    from sqlalchemy import exists, select
    users, rows = User.__table__, UserSSOIdentity.__table__
    held = exists().where(rows.c.user_id == users.c.id)
    return db.session.execute(select(users.c.username, users.c.has_sso_identity)
                              .where(users.c.has_sso_identity != held)).all()


@pytest.fixture(autouse=True)
def _the_local_flag_tells_the_truth(request):
    """After every scenario, the flag the local e-mail index reads agrees with the rows."""
    yield
    if 'app' in request.fixturenames:
        with request.getfixturevalue('app').app_context():
            assert _untrue_flags() == []


def _ext(provider_id, stable):
    with db.session.no_autoflush:
        kind = db.session.get(SSOProvider, provider_id).provider_type
    if kind == 'saml':
        return {'name_id': stable, 'name_id_format': 'urn:oasis:names:tc:SAML:2.0:nameid-format:persistent'}
    return {'sub': stable}


def _login(app, pid, username, stable, email=None, **more):
    from api.v2.sso.ldap_routes import _get_or_create_sso_user
    with app.test_request_context():
        p = db.session.get(SSOProvider, pid)
        user, err = _get_or_create_sso_user(p, username, email or f'{username}@corp.example', 'N',
                                            dict(_ext(pid, stable), **more))
        return (user.username if user else None), err


def _add(app, **kw):
    with app.app_context():
        kw.setdefault('email', f"{kw['username']}@corp.example")
        kw.setdefault('role', 'operator')
        kw.setdefault('active', True)
        user = legacy_user(**kw)
        db.session.add(user)
        db.session.commit()
        return user.id


def _rows(app, uid):
    with app.app_context():
        return identities(db.session.get(User, uid))


def _row_id(app, uid, pid):
    with app.app_context():
        return identity_for(db.session.get(User, uid), pid).id


def _attach(client, uid, pid, **body):
    return client.post(f'/api/v2/users/{uid}/sso-identities', json=dict(body, provider_id=pid))


def _detach(app, client, uid, pid):
    return client.delete(f'/api/v2/users/{uid}/sso-identities/{_row_id(app, uid, pid)}')


def _session(app, uid):
    """A client holding a session of the account, opened now."""
    from utils.datetime_utils import utc_now
    with app.app_context():
        u = db.session.get(User, uid)
        name, role, version = u.username, u.role, u.session_version or 0
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(user_id=uid, username=name, role=role, auth_method='sso', session_version=version,
                 login_time=utc_now().isoformat(), last_activity=utc_now().isoformat())
    return c


def _audit(app, action, name):
    with app.app_context():
        row = (AuditLog.query.filter(AuditLog.action == action, AuditLog.details.contains(repr(name)))
               .order_by(AuditLog.id.desc()).first())
        return row.details if row else ''


# ── Two providers, one account ──────────────────────────────────────────────

def test_two_attached_providers_each_open_the_account_by_their_own_identity(app, providers, auth_client):
    name = _name()
    uid = _add(app, username=name, auth_source='oauth2', sso_provider_id=providers.oidc,
               sso_external_id='sub-1', password_hash=NOPASS)
    # The second provider sends the same name: refused, the account is not its own yet
    assert _login(app, providers.saml, name, 'nameid-1') == (None, 'sso_username_conflict')
    assert 'attach provider' in _audit(app, 'login_failure', name)
    assert _rows(app, uid) == [(providers.oidc, 'sub-1', None)]
    assert _attach(auth_client, uid, providers.saml).status_code == 201
    assert _login(app, providers.saml, name, 'nameid-1') == (name, None)
    assert _login(app, providers.oidc, name, 'sub-1') == (name, None)
    assert _rows(app, uid) == [(providers.oidc, 'sub-1', None), (providers.saml, 'nameid-1', None)]
    # Each by its own identity, whatever name it sends afterwards
    assert _login(app, providers.saml, 'renamed-at-idp', 'nameid-1') == (name, None)
    assert _login(app, providers.oidc, name, 'nameid-1') == (None, 'sso_username_conflict')


def test_the_email_of_an_account_of_the_first_provider_is_refused_to_the_second(app, providers):
    name, other = _name(), _name()
    _add(app, username=name, auth_source='oauth2', sso_provider_id=providers.oidc,
         sso_external_id='sub-2', password_hash=NOPASS)
    got = _login(app, providers.saml, other, 'nameid-2', email=f'{name}@corp.example')
    assert got == (None, 'sso_email_conflict')
    with app.app_context():
        assert User.query.filter_by(username=other).count() == 0
    assert 'attach this provider to it' in _audit(app, 'login_failure', name)


def test_the_role_follows_the_provider_of_the_last_sign_in(app, providers, auth_client):
    """Each provider synchronises the role by its own rules: no merge of the two."""
    for pid, role in ((providers.oidc, 'admin'), (providers.saml, 'auditor')):
        with app.app_context():
            p = db.session.get(SSOProvider, pid)
            p.role_mapping, p.sync_role_on_login = f'{{"grp": "{role}"}}', True
            db.session.commit()
    name = _name()
    uid = _add(app, username=name, auth_source='oauth2', sso_provider_id=providers.oidc,
               sso_external_id='sub-r', password_hash=NOPASS, role='viewer')
    assert _attach(auth_client, uid, providers.saml).status_code == 201

    def role():
        with app.app_context():
            return db.session.get(User, uid).role

    assert _login(app, providers.oidc, name, 'sub-r', groups=['grp']) == (name, None)
    assert role() == 'admin'
    assert _login(app, providers.saml, name, 'nameid-r', groups=['grp']) == (name, None)
    assert role() == 'auditor'
    assert _login(app, providers.oidc, name, 'sub-r', groups=['grp']) == (name, None)
    assert role() == 'admin'


def test_attaching_takes_back_the_orphan_the_same_idp_left_with_its_identity(app, providers, auth_client):
    """An explicit attachment never weakens a binding: no other sign-in may bind that row."""
    with app.app_context():
        key = db.session.get(SSOProvider, providers.oidc).idp_key()
    name = _name()
    uid = _add(app, username=name, auth_source='oauth2', sso_orphan_of=key, sso_external_id='old',
               password_hash=NOPASS)
    with app.app_context():
        orphan_id = identity_for(db.session.get(User, uid), None).id
    assert _attach(auth_client, uid, providers.oidc).status_code == 201
    assert _rows(app, uid) == [(providers.oidc, 'old', None)]
    assert _row_id(app, uid, providers.oidc) == orphan_id
    assert 'taking back its orphan of the same IdP' in _audit(app, 'user_sso_attach', name)
    # Only that identity opens it; the account's name sent with another one does not
    assert _login(app, providers.oidc, name, 'someone-else') == (None, 'sso_username_conflict')
    assert _login(app, providers.oidc, 'renamed', 'old') == (name, None)


def test_taking_back_an_orphan_whose_identity_opens_another_account_gets_409(app, providers, auth_client):
    with app.app_context():
        key = db.session.get(SSOProvider, providers.oidc).idp_key()
    name = _name()
    uid = _add(app, username=name, auth_source='oauth2', sso_orphan_of=key, sso_external_id='twice',
               password_hash=NOPASS)
    other = _add(app, username=_name(), auth_source='oauth2', sso_provider_id=providers.oidc,
                 sso_external_id='twice', password_hash=NOPASS)
    r = _attach(auth_client, uid, providers.oidc)
    assert r.status_code == 409, r.get_json()
    assert _rows(app, uid) == [(None, 'twice', key)]
    assert _rows(app, other) == [(providers.oidc, 'twice', None)]


def test_an_orphan_of_the_same_idp_beside_an_attachment_lets_the_name_bind_it(app, providers):
    """The account already has its own row for the provider: that row is bound, never a second."""
    with app.app_context():
        key = db.session.get(SSOProvider, providers.oidc).idp_key()
    name = _name()
    uid = _add(app, username=name, auth_source='oauth2', sso_provider_id=providers.oidc,
               password_hash=NOPASS)
    with app.app_context():
        db.session.add(UserSSOIdentity(user_id=uid, orphan_of=key, external_id='sub-o2'))
        db.session.commit()
    assert _login(app, providers.oidc, name, 'sub-o2') == (name, None)
    assert _rows(app, uid) == [(providers.oidc, 'sub-o2', None), (None, 'sub-o2', key)]


def test_a_second_attachment_to_the_same_provider_is_refused(app, providers, auth_client):
    name = _name()
    uid = _add(app, username=name, password_hash='hash')
    assert _attach(auth_client, uid, providers.oidc).status_code == 201
    r = _attach(auth_client, uid, providers.oidc)
    assert r.status_code == 409 and 'reset its identity' in r.get_json()['message']
    assert _rows(app, uid) == [(providers.oidc, None, None)]


def test_resetting_an_identity_lets_the_next_sign_in_bind_a_new_one(app, providers, auth_client):
    name = _name()
    uid = _add(app, username=name, auth_source='oauth2', sso_provider_id=providers.oidc,
               sso_external_id='sub-before', password_hash=NOPASS)
    held = _session(app, uid)
    assert _login(app, providers.oidc, name, 'sub-after') == (None, 'sso_username_conflict')
    r = auth_client.post(f'/api/v2/users/{uid}/sso-identities/{_row_id(app, uid, providers.oidc)}/reset')
    assert r.status_code == 200, r.get_json()
    assert held.get('/api/v2/certificates').status_code == 401
    assert _login(app, providers.oidc, name, 'sub-after') == (name, None)
    assert _rows(app, uid) == [(providers.oidc, 'sub-after', None)]
    assert "Reset identity 'sub-before'" in _audit(app, 'user_sso_reset', name)


# ── The database refuses two owners of one identity ─────────────────────────

def test_one_account_per_stable_identity_of_a_provider(app, providers):
    first, second = _name(), _name()
    _add(app, username=first, auth_source='oauth2', sso_provider_id=providers.oidc,
         sso_external_id='sub-dup', password_hash=NOPASS)
    with app.app_context():
        user = User(username=second, email=f'{second}@corp.example', role='viewer', password_hash=NOPASS)
        user.sso_identities.append(UserSSOIdentity(provider_id=providers.oidc, external_id='sub-dup'))
        db.session.add(user)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_one_attachment_per_provider_per_account(app, providers):
    name = _name()
    uid = _add(app, username=name, auth_source='oauth2', sso_provider_id=providers.oidc,
               password_hash=NOPASS)
    with app.app_context():
        db.session.add(UserSSOIdentity(user_id=uid, provider_id=providers.oidc, external_id='other'))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_rows_not_bound_yet_may_share_a_provider_across_accounts(app, providers):
    """NULL identities are distinct on both backends: several accounts wait for their first sign-in."""
    uids = [_add(app, username=_name(), auth_source='oauth2', sso_provider_id=providers.oidc,
                 password_hash=NOPASS) for _ in range(2)]
    assert [_rows(app, uid) for uid in uids] == [[(providers.oidc, None, None)]] * 2


# ── The database holds the e-mail of local accounts unique (#136) ─────────

def _insert_user(name, email, sso):
    db.session.execute(User.__table__.insert().values(
        username=name, email=email, password_hash='hash', role='viewer', has_sso_identity=sso))


def test_the_database_refuses_a_second_local_account_on_one_email(app, providers):
    first, second, third = _name(), _name(), _name()
    email = f'{first}@corp.example'
    with app.app_context():
        _insert_user(first, email, False)
        # An account a provider opens may share it
        _insert_user(second, email, True)
        db.session.commit()
        with pytest.raises(IntegrityError):
            _insert_user(third, email, False)
            db.session.flush()
        db.session.rollback()
        db.session.execute(User.__table__.delete().where(User.username.in_([first, second])))
        db.session.commit()


def test_two_creations_at_once_one_passes_the_other_gets_409(app, auth_client, monkeypatch):
    """Both pass the check before either commits: the index refuses the second."""
    import api.v2.users.crud as crud
    email = f'{_name()}@corp.example'
    body = dict(password='Race-Condition-42!', email=email, role='viewer')
    first = auth_client.post('/api/v2/users', json=dict(body, username=_name()))
    assert first.status_code == 201, first.get_json()
    monkeypatch.setattr(crud, 'local_email_holder', lambda *a, **k: None)
    name = _name()
    second = auth_client.post('/api/v2/users', json=dict(body, username=name))
    assert second.status_code == 409, second.get_json()
    with app.app_context():
        assert User.query.filter_by(username=name).count() == 0
    auth_client.delete(f"/api/v2/users/{first.get_json()['data']['id']}")


def test_an_import_beaten_to_an_email_by_another_creation_gets_409(app, auth_client, monkeypatch):
    """The import checked the e-mail before the other account committed: the index refuses it."""
    import io
    import api.v2.users.management as management
    email = f'{_name()}@corp.example'
    first = auth_client.post('/api/v2/users', json=dict(
        username=_name(), password='Race-Condition-42!', email=email, role='viewer'))
    assert first.status_code == 201, first.get_json()
    monkeypatch.setattr(management, 'local_email_holder', lambda *a, **k: None)
    name = _name()
    csv_text = f'username,email,full_name,role,password\n{name},{email},N,viewer,Race-Condition-42!\n'
    r = auth_client.post('/api/v2/users/import', data={'file': (io.BytesIO(csv_text.encode()), 'u.csv')},
                         content_type='multipart/form-data')
    assert r.status_code == 409, r.get_json()
    assert email in r.get_json()['message'], r.get_json()
    with app.app_context():
        assert User.query.filter_by(username=name).count() == 0
    auth_client.delete(f"/api/v2/users/{first.get_json()['data']['id']}")


def test_an_import_gives_an_sso_accounts_email_to_a_local_account(app, providers, auth_client):
    """E-mail is unique among local accounts only, as the creation of one account says."""
    import io
    sso, name = _name(), _name()
    email = f'{sso}@corp.example'
    _add(app, username=sso, email=email, auth_source='oauth2', sso_provider_id=providers.oidc,
         password_hash=NOPASS)
    csv_text = f'username,email,full_name,role,password\n{name},{email},N,viewer,Race-Condition-42!\n'
    r = auth_client.post('/api/v2/users/import', data={'file': (io.BytesIO(csv_text.encode()), 'u.csv')},
                         content_type='multipart/form-data')
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['data']['imported'] == 1, r.get_json()


def test_detaching_the_last_provider_at_once_with_a_new_local_account_gets_409(
        app, providers, auth_client, monkeypatch):
    import models.user as user_model
    local, name = _name(), _name()
    email = f'{local}@corp.example'
    _add(app, username=local, email=email, password_hash='hash')
    uid = _add(app, username=name, email=email, auth_source='oauth2',
               sso_provider_id=providers.oidc, password_hash=NOPASS)
    real, calls = user_model.local_email_holder, []

    def not_yet(*args, **kwargs):
        # The check runs before the local account commits; the answer to the refusal after
        calls.append(args)
        return None if len(calls) == 1 else real(*args, **kwargs)

    monkeypatch.setattr(user_model, 'local_email_holder', not_yet)
    r = _detach(app, auth_client, uid, providers.oidc)
    assert r.status_code == 409, r.get_json()
    assert _rows(app, uid) == [(providers.oidc, None, None)]


def test_the_flag_follows_every_change_of_the_rows(app, providers, auth_client):
    name = _name()
    uid = _add(app, username=name, password_hash='hash')

    def flag():
        with app.app_context():
            return db.session.execute(db.select(User.has_sso_identity).where(User.id == uid)).scalar()

    assert flag() is False
    assert _attach(auth_client, uid, providers.oidc).status_code == 201
    assert flag() is True
    assert _detach(app, auth_client, uid, providers.oidc).status_code == 200
    assert flag() is False
    # A row written outside the session, as another node would, goes through the same writer
    from tests.sso_identity_support import attach_from_another_node
    with app.app_context():
        attach_from_another_node(name, providers.saml)
    assert flag() is True


def test_an_sso_account_may_take_the_email_of_a_local_account_in_its_profile(app, providers):
    """Unique among local accounts only (#136): the profile and the index say the same."""
    local, name = _name(), _name()
    email = f'{local}@corp.example'
    _add(app, username=local, email=email, password_hash='hash')
    uid = _add(app, username=name, auth_source='oauth2', sso_provider_id=providers.oidc,
               sso_external_id='sub-p', password_hash=NOPASS)
    r = _session(app, uid).patch('/api/v2/account/profile', json={'email': email})
    assert r.status_code == 200, r.get_json()
    with app.app_context():
        assert db.session.get(User, uid).email == email


# ── Detaching ───────────────────────────────────────────────────────────────

def test_detaching_one_of_two_keeps_the_other_and_closes_the_sessions(app, providers, auth_client):
    name = _name()
    uid = _add(app, username=name, auth_source='oauth2', sso_provider_id=providers.oidc,
               sso_external_id='sub-k', password_hash=NOPASS)
    assert _attach(auth_client, uid, providers.saml).status_code == 201
    assert _login(app, providers.saml, name, 'nameid-k') == (name, None)
    held = _session(app, uid)
    assert held.get('/api/v2/certificates').status_code == 200
    r = _detach(app, auth_client, uid, providers.saml)
    assert r.status_code == 200, r.get_json()
    assert held.get('/api/v2/certificates').status_code == 401
    assert r.get_json()['meta']['other_sessions_closed'] in (1, None)
    with app.app_context():
        u = db.session.get(User, uid)
        assert u.force_password_change is not True and u.password_hash == NOPASS
    assert _rows(app, uid) == [(providers.oidc, 'sub-k', None)]
    assert _login(app, providers.oidc, name, 'sub-k') == (name, None)
    assert _login(app, providers.saml, name, 'nameid-k') == (None, 'sso_username_conflict')
    assert "Detached provider" in _audit(app, 'user_sso_detach', name)


def test_detaching_the_last_provider_of_an_account_without_password_asks_for_one(
        app, providers, auth_client):
    name = _name()
    uid = _add(app, username=name, auth_source='oauth2', sso_provider_id=providers.oidc,
               sso_external_id='sub-l', password_hash=NOPASS)
    held = _session(app, uid)
    r = _detach(app, auth_client, uid, providers.oidc)
    assert r.status_code == 200 and 'set a password' in r.get_json()['message']
    assert held.get('/api/v2/certificates').status_code == 401
    with app.app_context():
        u = db.session.get(User, uid)
        assert (u.is_local, u.force_password_change) == (True, True)
    assert 'that must set a password' in _audit(app, 'user_sso_detach', name)
    assert _login(app, providers.oidc, name, 'sub-l') == (None, 'sso_username_conflict')


def test_detaching_the_last_provider_keeps_a_password_the_account_has(app, providers, auth_client):
    name = _name()
    uid = _add(app, username=name, auth_source='oauth2', sso_provider_id=providers.oidc,
               password_hash='kept-hash')
    assert _detach(app, auth_client, uid, providers.oidc).status_code == 200
    with app.app_context():
        u = db.session.get(User, uid)
        assert (u.password_hash, u.force_password_change) == ('kept-hash', False)


def test_the_last_provider_does_not_go_while_a_local_account_holds_the_email(app, providers, auth_client):
    """E-mail is unique among local accounts (#136): detaching would make a second one."""
    local, name = _name(), _name()
    email = f'{local}@corp.example'
    _add(app, username=local, email=email, password_hash='hash')
    uid = _add(app, username=name, email=email, auth_source='oauth2',
               sso_provider_id=providers.oidc, password_hash=NOPASS)
    r = _detach(app, auth_client, uid, providers.oidc)
    assert r.status_code == 409 and 'e-mail' in r.get_json()['message']
    assert _rows(app, uid) == [(providers.oidc, None, None)]


def test_an_anonymous_caller_attaches_nothing(app, providers, client):
    name = _name()
    uid = _add(app, username=name, password_hash='hash')
    assert client.post(f'/api/v2/users/{uid}/sso-identities',
                       json={'provider_id': providers.oidc}).status_code == 401
    assert _rows(app, uid) == []


def test_write_users_outside_the_administrator_role_attaches_nothing(app, providers, auth_client):
    """write:users is reserved: a custom role or a group that stored it grants it to no one,
    so choosing who opens an account stays the administrator's."""
    from models.group import Group, GroupMember
    from models.rbac import CustomRole
    name, target = _name(), _name()
    uid = _add(app, username=target, password_hash='hash')
    with app.app_context():
        role = CustomRole(name=f'{name}-role', permissions=['write:users', 'read:users'])
        group = Group(name=f'{name}-group', permissions=['write:users'])
        db.session.add_all([role, group])
        db.session.flush()
        caller = User(username=name, email=f'{name}@corp.example', role='operator',
                      custom_role_id=role.id)
        caller.set_password('Operator-Pass-42!')
        db.session.add(caller)
        db.session.flush()
        db.session.add(GroupMember(group_id=group.id, user_id=caller.id))
        db.session.commit()
        caller_id, role_id, group_id = caller.id, role.id, group.id
    try:
        client = _session(app, caller_id)
        assert client.post(f'/api/v2/users/{uid}/sso-identities',
                           json={'provider_id': providers.oidc}).status_code == 403
        assert _rows(app, uid) == []
        assert _attach(auth_client, uid, providers.oidc).status_code == 201
        row = _row_id(app, uid, providers.oidc)
        assert client.post(f'/api/v2/users/{uid}/sso-identities/{row}/reset').status_code == 403
        assert client.delete(f'/api/v2/users/{uid}/sso-identities/{row}').status_code == 403
        assert _rows(app, uid) == [(providers.oidc, None, None)]
    finally:
        with app.app_context():
            GroupMember.query.filter_by(group_id=group_id).delete()
            db.session.delete(db.session.get(Group, group_id))
            db.session.delete(db.session.get(User, caller_id))
            db.session.delete(db.session.get(CustomRole, role_id))
            db.session.commit()


# ── A provider or an account deleted ────────────────────────────────────────

def test_deleting_a_provider_orphans_its_rows_only(app, providers, auth_client):
    with app.app_context():
        key = db.session.get(SSOProvider, providers.saml).idp_key()
    name = _name()
    uid = _add(app, username=name, auth_source='oauth2', sso_provider_id=providers.oidc,
               sso_external_id='sub-d', password_hash=NOPASS)
    assert _attach(auth_client, uid, providers.saml).status_code == 201
    assert _login(app, providers.saml, name, 'nameid-d') == (name, None)
    assert auth_client.delete(f'/api/v2/sso/providers/{providers.saml}').status_code == 200
    assert _rows(app, uid) == [(providers.oidc, 'sub-d', None), (None, 'nameid-d', key)]
    # Recreated for the exact same IdP: it takes its own back, by its identity
    again = providers(provider_type='saml', saml_entity_id=key.split(':', 1)[1])
    assert _login(app, again, 'another-name', 'nameid-d') == (name, None)
    assert _rows(app, uid) == [(providers.oidc, 'sub-d', None), (again, 'nameid-d', None)]


def test_deleting_an_account_removes_its_rows(app, providers, auth_client):
    name = _name()
    uid = _add(app, username=name, auth_source='oauth2', sso_provider_id=providers.oidc,
               sso_external_id='sub-x', password_hash=NOPASS)
    assert auth_client.delete(f'/api/v2/users/{uid}').status_code == 200
    with app.app_context():
        assert UserSSOIdentity.query.filter_by(user_id=uid).count() == 0
    # Its identity is free for the account the provider creates next
    assert _login(app, providers.oidc, _name(), 'sub-x')[1] is None


# ── Which accounts no self-service door gives a password ───────────────────

@pytest.mark.parametrize('fields, only', [
    ({'auth_source': 'oauth2', 'sso_external_id': 's'}, True),        # attached, bound
    ({'auth_source': 'oauth2'}, True),                                 # attached, not bound yet
    ({'auth_source': 'oauth2', 'sso_orphan_of': 'oauth2:https://gone.example'}, True),  # orphan
    ({'auth_source': 'oauth2', 'force_password_change': True}, True),  # attached, a change owed
    ({'auth_source': 'local', 'force_password_change': False}, True),  # older than auth_source
    ({'auth_source': 'local', 'force_password_change': True}, False),  # detached, owes a password
    ({'auth_source': 'oauth2', 'password_hash': 'kept'}, False),       # kept its password
    ({'auth_source': 'local', 'password_hash': 'local'}, False),       # local
], ids=['bound', 'pending', 'orphan', 'owing', 'legacy', 'detached', 'kept-password', 'local'])
def test_sso_only_reads_the_rows(app, providers, fields, only):
    from api.v2.sso.account_state import sso_only
    fields = dict({'password_hash': NOPASS}, **fields)
    if fields['auth_source'] != 'local' and 'sso_orphan_of' not in fields:
        fields['sso_provider_id'] = providers.oidc
    uid = _add(app, username=_name(), **fields)
    with app.app_context():
        assert sso_only(db.session.get(User, uid)) is only


def test_enforced_2fa_of_any_attached_provider_applies_outside_its_sign_in(app, providers, auth_client):
    from auth.twofa_enforcement import enforcement_active_for
    with app.app_context():
        db.session.get(SSOProvider, providers.saml).enforce_2fa = True
        db.session.commit()
    uid = _add(app, username=_name(), auth_source='oauth2', sso_provider_id=providers.oidc,
               password_hash=NOPASS)
    with app.app_context():
        assert enforcement_active_for(db.session.get(User, uid)) is False
    assert _attach(auth_client, uid, providers.saml).status_code == 201
    with app.app_context():
        user = db.session.get(User, uid)
        assert enforcement_active_for(user) is True
        assert enforcement_active_for(user, provider=db.session.get(SSOProvider, providers.oidc)) is False


# ── Backup and restore ──────────────────────────────────────────────────────

def _backup():
    from services.backup_service import BackupService
    return BackupService()


def test_a_restore_brings_the_rows_back_and_orphans_a_provider_it_cannot_place(app, providers, auth_client):
    from services.backup import manifest
    password = 'Correct-Horse-Battery-9'
    name = _name()
    uid = _add(app, username=name, auth_source='oauth2', sso_provider_id=providers.oidc,
               sso_external_id='sub-b', password_hash=NOPASS)
    assert _attach(auth_client, uid, providers.saml).status_code == 201
    assert _login(app, providers.saml, name, 'nameid-b') == (name, None)
    with app.app_context():
        include = {n: n in ('users', 'user_sso_identities') for n in manifest.SECTIONS}
        blob = _backup().create_backup(password, include=include)
        # The account goes, and so does one of its providers, which the archive does not carry
        db.session.delete(db.session.get(User, uid))
        UserSSOIdentity.query.filter_by(provider_id=providers.saml).delete()
        db.session.delete(db.session.get(SSOProvider, providers.saml))
        db.session.commit()
        _backup().restore_backup(blob, password, mode='merge')
        db.session.expire_all()
        restored = User.query.filter_by(username=name).one()
        assert identities(restored) == [(providers.oidc, 'sub-b', None), (None, 'nameid-b', None)]
        # A second restore of the same archive writes no second row
        _backup().restore_backup(blob, password, mode='merge')
        db.session.expire_all()
        assert len(User.query.filter_by(username=name).one().sso_identities) == 2


def test_a_replace_by_an_archive_that_matches_keeps_the_rows_and_warns_nothing(app, providers, auth_client):
    """A live row has no orphan_of, an orphan no provider: the rows are matched by account and
    provider, or account and IdP key, never judged incomplete, removed and made again."""
    from services.backup import manifest
    password = 'Correct-Horse-Battery-9'
    name = _name()
    uid = _add(app, username=name, auth_source='oauth2', sso_provider_id=providers.oidc,
               sso_external_id='sub-rp', password_hash=NOPASS)
    with app.app_context():
        db.session.add(UserSSOIdentity(user_id=uid, orphan_of='saml:https://gone.example',
                                       external_id='nameid-rp'))
        db.session.commit()
        before = [(row.id, row.provider_id, row.external_id, row.orphan_of)
                  for row in UserSSOIdentity.query.order_by(UserSSOIdentity.id)]
        include = {n: n in ('users', 'user_sso_identities') for n in manifest.SECTIONS}
        blob = _backup().create_backup(password, include=include)
        results = _backup().restore_backup(blob, password, mode='replace')
        db.session.expire_all()
        assert [w for w in results['warnings'] if 'user_sso_identities' in w] == []
        # SQLite may hand a recreated row its old id: the replacement says what it removed
        assert results['removed'].get('user_sso_identities', 0) == 0, results['removed']
        assert [(row.id, row.provider_id, row.external_id, row.orphan_of)
                for row in UserSSOIdentity.query.order_by(UserSSOIdentity.id)] == before


def test_a_merge_skips_an_identity_another_account_holds_here(app, providers, auth_client):
    """One identity opens one account: the archive's row is left out, named, the rest restored."""
    from services.backup import manifest
    password = 'Correct-Horse-Battery-9'
    name, holder = _name(), _name()
    uid = _add(app, username=name, auth_source='oauth2', sso_provider_id=providers.oidc,
               sso_external_id='sub-m', password_hash=NOPASS)
    assert _attach(auth_client, uid, providers.saml).status_code == 201
    with app.app_context():
        provider_name = db.session.get(SSOProvider, providers.oidc).name
        include = {n: n in ('users', 'user_sso_identities') for n in manifest.SECTIONS}
        blob = _backup().create_backup(password, include=include)
        db.session.delete(db.session.get(User, uid))
        db.session.commit()
    holder_id = _add(app, username=holder, auth_source='oauth2', sso_provider_id=providers.oidc,
                     sso_external_id='sub-m', password_hash=NOPASS)
    with app.app_context():
        results = _backup().restore_backup(blob, password, mode='merge')
        db.session.expire_all()
        restored = User.query.filter_by(username=name).one()
        # The skipped row stays as an orphan of an unknown IdP, which opens nothing
        assert set(identities(restored)) == {(providers.saml, None, None), (None, 'sub-m', None)}
        assert identities(db.session.get(User, holder_id)) == [(providers.oidc, 'sub-m', None)]
    skipped = [w for w in results['warnings'] if 'user_sso_identities' in w]
    assert len(skipped) == 1 and repr(holder) in skipped[0] and repr(provider_name) in skipped[0] \
        and repr(name) in skipped[0], results['warnings']


def test_an_archive_from_before_the_rows_skips_an_identity_another_account_holds(app, providers):
    with app.app_context():
        provider_name = db.session.get(SSOProvider, providers.oidc).name
    holder = _name()
    holder_id = _add(app, username=holder, auth_source='oauth2', sso_provider_id=providers.oidc,
                     sso_external_id='sub-t', password_hash=NOPASS)
    service, plan = _backup(), SimpleNamespace(warnings=[])
    with app.app_context():
        user = User(username=_name(), email='taken@corp.example', role='viewer', password_hash=NOPASS)
        db.session.add(user)
        service._legacy_sso_identities = [(user, {
            'auth_source': 'oauth2', 'sso_provider_id': 7, 'sso_provider_id_ref': {'name': provider_name},
            'sso_external_id': 'sub-t'})]
        results = {}
        service._restore_legacy_sso_identities(results, plan)
        db.session.commit()
        assert identities(user) == [(None, 'sub-t', None)]
        assert identities(db.session.get(User, holder_id)) == [(providers.oidc, 'sub-t', None)]
        assert len(plan.warnings) == 1 and repr(holder) in plan.warnings[0] \
            and repr(provider_name) in plan.warnings[0], plan.warnings


def _claimable_by_name(app, providers, uid, name):
    """Whether an identity of another provider opens the account by its name alone."""
    from api.v2.sso.account_state import legacy_sso_account
    other = providers()
    with app.app_context():
        legacy = legacy_sso_account(db.session.get(User, uid))
    return legacy, _login(app, other, name, 'attacker')


def test_a_merge_keeps_a_skipped_identity_as_an_orphan_so_the_name_opens_nothing(app, providers):
    """An account whose only row is skipped keeps it as an orphan of an unknown IdP: without a
    row and a password, any provider would open it by its name."""
    from services.backup import manifest
    password = 'Correct-Horse-Battery-9'
    name = _name()
    uid = _add(app, username=name, auth_source='oauth2', sso_provider_id=providers.oidc,
               sso_external_id='sub-skip', password_hash=NOPASS, role='admin')
    with app.app_context():
        include = {n: n in ('users', 'user_sso_identities') for n in manifest.SECTIONS}
        blob = _backup().create_backup(password, include=include)
        db.session.delete(db.session.get(User, uid))
        db.session.commit()
    _add(app, username=_name(), auth_source='oauth2', sso_provider_id=providers.oidc,
         sso_external_id='sub-skip', password_hash=NOPASS)
    with app.app_context():
        results = _backup().restore_backup(blob, password, mode='merge')
        db.session.expire_all()
        uid = User.query.filter_by(username=name).one().id
    assert _rows(app, uid) == [(None, 'sub-skip', None)]
    assert _claimable_by_name(app, providers, uid, name) == (False, (None, 'sso_username_conflict'))
    skipped = [w for w in results['warnings'] if 'user_sso_identities' in w]
    assert len(skipped) == 1 and 'orphan' in skipped[0], results['warnings']


def test_two_skipped_identities_of_one_account_stay_two_orphans(app, providers):
    """Orphans of an unknown IdP are told apart by their identity: neither overwrites the other."""
    from services.backup import manifest
    password = 'Correct-Horse-Battery-9'
    name = _name()
    uid = _add(app, username=name, auth_source='oauth2', sso_provider_id=providers.oidc,
               sso_external_id='sub-two', password_hash=NOPASS)
    with app.app_context():
        attach_row = UserSSOIdentity(user_id=uid, provider_id=providers.saml)
        attach_row.bind('nameid-two')
        db.session.add(attach_row)
        db.session.commit()
        include = {n: n in ('users', 'user_sso_identities') for n in manifest.SECTIONS}
        blob = _backup().create_backup(password, include=include)
        db.session.delete(db.session.get(User, uid))
        db.session.commit()
    _add(app, username=_name(), auth_source='oauth2', sso_provider_id=providers.oidc,
         sso_external_id='sub-two', password_hash=NOPASS)
    _add(app, username=_name(), auth_source='saml', sso_provider_id=providers.saml,
         sso_external_id='nameid-two', password_hash=NOPASS)
    with app.app_context():
        _backup().restore_backup(blob, password, mode='merge')
        db.session.expire_all()
        uid = User.query.filter_by(username=name).one().id
    assert sorted(_rows(app, uid)) == [(None, 'nameid-two', None), (None, 'sub-two', None)]


@pytest.mark.parametrize('mode', ['merge', 'replace'])
def test_an_account_holding_two_unknown_orphans_is_restored_as_it_is(app, providers, mode):
    from services.backup import manifest
    password = 'Correct-Horse-Battery-9'
    uid = _add(app, username=_name(), password_hash=NOPASS)
    with app.app_context():
        for external_id in ('orphan-a', 'orphan-b'):
            row = UserSSOIdentity(user_id=uid)
            row.bind(external_id)
            db.session.add(row)
        db.session.commit()
        before = sorted((r.id, r.external_id) for r in UserSSOIdentity.query.filter_by(user_id=uid))
        include = {n: n in ('users', 'user_sso_identities') for n in manifest.SECTIONS}
        blob = _backup().create_backup(password, include=include)
        results = _backup().restore_backup(blob, password, mode=mode)
        db.session.expire_all()
        assert [w for w in results['warnings'] if 'user_sso_identities' in w] == []
        assert results.get('removed', {}).get('user_sso_identities', 0) == 0
        assert sorted((r.id, r.external_id)
                      for r in UserSSOIdentity.query.filter_by(user_id=uid)) == before


@pytest.mark.parametrize('merging', [True, False], ids=['merge', 'replace'])
def test_an_archive_from_before_the_rows_keeps_a_skipped_identity_as_an_orphan(app, providers, merging):
    with app.app_context():
        provider_name = db.session.get(SSOProvider, providers.oidc).name
    _add(app, username=_name(), auth_source='oauth2', sso_provider_id=providers.oidc,
         sso_external_id='sub-ts', password_hash=NOPASS)
    service, plan, name = _backup(), SimpleNamespace(warnings=[]), _name()
    with app.app_context():
        user = User(username=name, email=f'{name}@corp.example', role='admin', password_hash=NOPASS)
        db.session.add(user)
        service._merging = merging
        service._legacy_sso_identities = [(user, {
            'auth_source': 'oauth2', 'sso_provider_id': 7, 'sso_provider_id_ref': {'name': provider_name},
            'sso_external_id': 'sub-ts'})]
        service._restore_legacy_sso_identities({}, plan)
        db.session.commit()
        uid = user.id
    assert _rows(app, uid) == [(None, 'sub-ts', None)]
    assert _claimable_by_name(app, providers, uid, name) == (False, (None, 'sso_username_conflict'))
    assert len(plan.warnings) == 1 and 'orphan' in plan.warnings[0], plan.warnings


@pytest.mark.parametrize('ref', [None, {'name': 'not-here'}], ids=['no-ref', 'gone'])
@pytest.mark.parametrize('merging', [True, False], ids=['merge', 'replace'])
def test_a_pre_024_account_whose_provider_is_not_here_stays_an_orphan(app, providers, ref, merging):
    """The upgrade keeps such an account as an orphan of an unknown IdP: so does a restore."""
    service, name = _backup(), _name()
    with app.app_context():
        user = User(username=name, email=f'{name}@corp.example', role='admin', password_hash=NOPASS)
        db.session.add(user)
        service._merging = merging
        service._legacy_sso_identities = [(user, {
            'auth_source': 'local', 'sso_provider_id': 7, 'sso_provider_id_ref': ref,
            'sso_external_id': None})]
        service._restore_legacy_sso_identities({}, SimpleNamespace(warnings=[]))
        db.session.commit()
        uid = user.id
    assert _rows(app, uid) == [(None, None, None)]
    assert _claimable_by_name(app, providers, uid, name) == (False, (None, 'sso_username_conflict'))


def test_an_archive_from_before_the_rows_gets_the_rows_an_upgrade_gives(app, providers):
    """2.254 archives carry the provider on the account row."""
    with app.app_context():
        provider_name = db.session.get(SSOProvider, providers.oidc).name
    accounts = {
        'bound': ({'auth_source': 'oauth2', 'sso_provider_id': 7, 'sso_provider_id_ref': {'name': provider_name},
                   'sso_external_id': 'sub-a'}, NOPASS, [(providers.oidc, 'sub-a', None)]),
        'gone': ({'auth_source': 'oauth2', 'sso_provider_id': 8, 'sso_provider_id_ref': {'name': 'not-here'},
                  'sso_external_id': 'sub-g'}, NOPASS, [(None, 'sub-g', None)]),
        'orphan': ({'auth_source': 'saml', 'sso_orphan_of': 'saml:https://old.example'}, NOPASS,
                   [(None, None, 'saml:https://old.example')]),
        'local': ({'auth_source': 'local'}, 'hash', []),
    }
    service = _backup()
    with app.app_context():
        service._legacy_sso_identities = []
        made = {}
        for label, (row, password_hash, _rows_after) in accounts.items():
            user = User(username=_name(), email=f'{label}@corp.example', role='viewer',
                        password_hash=password_hash)
            db.session.add(user)
            service._legacy_sso_identities.append((user, row))
            made[label] = user
        results = {}
        service._restore_legacy_sso_identities(results, SimpleNamespace(warnings=[]))
        db.session.commit()
        for label, (_row, _hash, rows_after) in accounts.items():
            assert identities(made[label]) == rows_after, label
        assert results['user_sso_identities'] == 3


def test_a_replace_from_before_the_rows_leaves_no_stale_collection(app, providers):
    """The rows a replace deletes in SQL are gone from the account read in the same session."""
    with app.app_context():
        provider_name = db.session.get(SSOProvider, providers.oidc).name
    uid = _add(app, username=_name(), auth_source='oauth2', sso_provider_id=providers.oidc,
               sso_external_id='sub-old', password_hash=NOPASS)
    service = _backup()
    with app.app_context():
        user = db.session.get(User, uid)
        assert identities(user) == [(providers.oidc, 'sub-old', None)]
        service._merging = False
        service._legacy_sso_identities = [(user, {
            'auth_source': 'oauth2', 'sso_provider_id': 7, 'sso_provider_id_ref': {'name': provider_name},
            'sso_external_id': 'sub-new'})]
        service._restore_legacy_sso_identities({}, SimpleNamespace(warnings=[]))
        assert identities(user) == [(providers.oidc, 'sub-new', None)]
        db.session.commit()


# ── The upgrade from 2.254 ──────────────────────────────────────────────────

# (username, auth_source, provider, external_id, orphan_of, password_hash, force_password_change):
# every state 2.254 knew, and the rows the upgrade gives it
STATES_2254 = [
    ('bound', 'oauth2', 1, 'sub-1', None, NOPASS, False, [(1, 'sub-1', None)]),
    ('pending', 'saml', 2, None, None, 'kept', False, [(2, None, None)]),
    ('orphan', 'oauth2', None, 'sub-o', 'oauth2:https://gone.example', NOPASS, False,
     [(None, 'sub-o', 'oauth2:https://gone.example')]),
    ('orphan_unknown', 'ldap', None, 'uid-u', None, NOPASS, False, [(None, 'uid-u', None)]),
    ('dangling', 'oauth2', 99, 'sub-d', None, NOPASS, False, [(None, 'sub-d', None)]),
    ('shared_id', 'oauth2', 1, 'sub-1', None, NOPASS, False, [(None, 'sub-1', None)]),
    ('local', 'local', None, None, None, 'hash', False, []),
    ('local_stale_id', 'local', None, 'stale', None, 'hash', False, []),
    ('legacy', 'local', None, None, None, NOPASS, False, []),
    ('legacy_024', 'local', 1, None, None, NOPASS, False, [(1, None, None)]),
    ('legacy_orphan', 'local', None, None, 'oauth2:https://gone.example', NOPASS, False,
     [(None, None, 'oauth2:https://gone.example')]),
    ('detached', 'local', None, None, None, NOPASS, True, []),
    ('detached_with_provider', 'local', 2, None, None, NOPASS, True, []),
    # 2.254 opened none by its name: the identity it carries makes it an orphan, never claimable
    ('legacy_bound_alone', 'local', None, 'sub-l', None, NOPASS, False, [(None, 'sub-l', None)]),
]


# PostgreSQL enforced the foreign key in 2.254: no account names a provider that is gone
_ONLY_SQLITE = {'dangling'}


def test_the_step_follows_the_trust_store_step_in_the_upgrade():
    from migrations._from_2_254 import STEPS
    assert STEPS.index('167_user_sso_identities') == \
        STEPS.index('166_trust_store_certificates_only') + 1


@pytest.mark.parametrize('dialect', BACKENDS)
def test_the_full_upgrade_runs_the_trust_store_step_then_this_one(dialect, tmp_path, monkeypatch,
                                                                   capfd):
    for base in make_base(dialect, tmp_path, monkeypatch, 's167order'):
        capfd.readouterr()
        assert base.upgrade()
        journal = capfd.readouterr().out.splitlines()
        marks = [line.strip().split(':')[0] for line in journal if line.strip().startswith('step 16')]
        assert marks.index('step 166_trust_store_certificates_only') < \
            marks.index('step 167_user_sso_identities'), journal
        assert 'user_sso_identities' in base.tables()


@pytest.fixture(params=BACKENDS)
def upgraded_2254(request, tmp_path, monkeypatch):
    for base in make_base(request.param, tmp_path, monkeypatch, 's167'):
        base.run("INSERT INTO pro_sso_providers (id, name, provider_type, id_token_verify, "
                 "sync_role_on_login, enforce_2fa) VALUES (1, 'p-oidc', 'oauth2', TRUE, FALSE, FALSE), "
                 "(2, 'p-saml', 'saml', TRUE, FALSE, FALSE)")
        for i, (name, source, pid, ext, orphan, pw, force, _rows_after) in enumerate(STATES_2254, start=1):
            if name in _ONLY_SQLITE and request.param != 'sqlite':
                continue
            base.run("INSERT INTO users (id, username, email, password_hash, role, auth_source, "
                     "sso_provider_id, sso_external_id, sso_orphan_of, force_password_change) "
                     "VALUES (:i, :n, :e, :pw, 'viewer', :s, :p, :x, :o, :f)",
                     {'i': i, 'n': name, 'e': f'{name}@x.test', 'pw': pw, 's': source, 'p': pid,
                      'x': ext, 'o': orphan, 'f': force})
        assert base.upgrade()
        yield base


def test_each_2254_account_gets_the_rows_that_keep_its_access(upgraded_2254):
    rows = upgraded_2254.run(
        "SELECT u.username, i.provider_id, i.external_id, i.orphan_of FROM users u "
        "JOIN user_sso_identities i ON i.user_id = u.id ORDER BY u.id, i.id")
    got = {}
    for name, pid, ext, orphan in rows:
        got.setdefault(name, []).append((pid, ext, orphan))
    names = {name for (name,) in upgraded_2254.run("SELECT username FROM users")}
    states = [state for state in STATES_2254 if state[0] in names]
    assert len(states) >= len(STATES_2254) - len(_ONLY_SQLITE)
    assert {state[0]: got.get(state[0], []) for state in states} == \
        {state[0]: state[-1] for state in states}
    # The flag the local e-mail index reads says which accounts got rows
    flags = {name: bool(flag) for name, flag in
             upgraded_2254.run("SELECT username, has_sso_identity FROM users")}
    assert flags == {state[0]: bool(state[-1]) for state in states}
    columns = upgraded_2254.run("SELECT * FROM users WHERE id = 1")
    assert len(columns) == 1
    bound_at = upgraded_2254.run(
        "SELECT bound_at IS NOT NULL FROM user_sso_identities WHERE external_id = 'sub-o'")
    assert bound_at in ([(1,)], [(True,)])


def test_the_upgrade_step_runs_again_without_changing_anything(upgraded_2254):
    from migrations._from_2_254 import step
    def state():
        return (upgraded_2254.run("SELECT user_id, provider_id, external_id, orphan_of FROM "
                                  "user_sso_identities ORDER BY id"),
                upgraded_2254.run("SELECT id, has_sso_identity FROM users ORDER BY id"))
    before = state()
    with upgraded_2254.connection() as conn:
        step('167_user_sso_identities').upgrade(conn)
    assert state() == before


def test_the_upgraded_index_refuses_a_second_local_account_on_one_email(upgraded_2254):
    from sqlalchemy.exc import IntegrityError as Refused
    insert = ("INSERT INTO users (username, email, password_hash, role, has_sso_identity) "
              "VALUES (:n, :e, 'h', 'viewer', :s)")
    # 'bound' is opened by a provider: a local account may take its e-mail, and an SSO one 'local's
    upgraded_2254.run(insert, {'n': 'new-local', 'e': 'bound@x.test', 's': False})
    upgraded_2254.run(insert, {'n': 'new-sso', 'e': 'local@x.test', 's': True})
    with pytest.raises(Refused):
        upgraded_2254.run(insert, {'n': 'second-local', 'e': 'local@x.test', 's': False})


def test_the_upgraded_constraints_refuse_a_second_owner(upgraded_2254):
    from sqlalchemy.exc import IntegrityError as Refused
    with pytest.raises(Refused):
        upgraded_2254.run("INSERT INTO user_sso_identities (user_id, provider_id, external_id) "
                          "VALUES (7, 1, 'sub-1')")
    with pytest.raises(Refused):
        upgraded_2254.run("INSERT INTO user_sso_identities (user_id, provider_id) VALUES (1, 1)")
