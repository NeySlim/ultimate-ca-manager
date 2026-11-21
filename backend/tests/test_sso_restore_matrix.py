"""No restore leaves an account the archive held by SSO claimable by its name.

An account an archive describes as opened by a provider (an identity row in a 3.0 archive; in a
2.254 one a source other than local, or a provider, a stable identity or an orphaned IdP key)
comes back with an identity row, a change of password owed, or a password: otherwise any
configured provider would open it by its name. The matrix plays every archive state against
every state of the target; the differential holds step 167 and the restore of a 2.254 archive
to the same rows.
"""
import itertools
import os
import uuid
from contextlib import ExitStack, contextmanager

import pytest

from models import db, User, UserSSOIdentity
from models.sso import SSOProvider
from tests.fresh_app import fresh_app_fixtures
from tests.test_backup_cross_installation import Keys, _installation
from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own
from tests.upgrade_2254_support import BACKENDS, make_base
from utils.sso_identity_upgrade import identity_rows

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()

NOPASS = '!SSO_NO_PASSWORD!'
REAL = 'pbkdf2:sha256:real'
IDP_KEY = 'oauth2:https://gone.example'
_PG_URL = os.environ.get('UCM_TEST_PG_URL')
ENGINES = [
    'sqlite',
    pytest.param('postgresql', marks=[
        pytest.mark.postgres,
        pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')]),
]


def _cases():
    """(format, mode, auth_source, password, provider, identity, orphan_of, account).

    provider: 'same' (here under its name and number), 'moved' (here under its name, another
    number), 'absent' (named, not here), 'dangling' (a number without a reference), 'none'.
    identity: 'free', 'held' (another account here holds it), 'absent' (no stable identity).
    account: 'absent' from the target, 'own' (here with rows of its own), 'bare' (here, no row).
    Pruned: an orphaned IdP key with a provider (2.254 cleared the provider when it set the
    key), and an identity held here at a provider not here (no row here can hold it)."""
    for fmt, mode, source, password, provider, identity, orphan, account in itertools.product(
            ('3.0', '2.254'), ('merge', 'replace'), ('local', 'ldap', 'oauth2', 'saml'),
            ('nopass', 'real'), ('same', 'moved', 'absent', 'dangling', 'none'),
            ('free', 'held', 'absent'), (None, IDP_KEY), ('absent', 'own', 'bare')):
        if orphan is not None and provider != 'none':
            continue
        if identity == 'held' and provider not in ('same', 'moved'):
            continue
        yield pytest.param(fmt, mode, source, password, provider, identity, orphan, account,
                           id='-'.join(str(v) for v in (fmt, mode, source, password, provider,
                                                        identity, 'orphan' if orphan else 'idp',
                                                        account)))


CASES = list(_cases())


@pytest.fixture(scope='module', params=ENGINES)
def installation(request, app, tmp_path_factory):
    """One target installation per engine, shared by the cases: each names its own rows."""
    directory = tmp_path_factory.mktemp('sso-matrix')
    keys = Keys(directory, f'matrix-{request.param}')
    if request.param == 'sqlite':
        with _installation(app, f"sqlite:///{directory / 'target.db'}", keys), app.app_context():
            yield request.param
        return
    with _a_schema_of_our_own(f'sso_matrix_{uuid.uuid4().hex[:10]}') as url:
        with _installation(app, url, keys, is_postgresql=True), app.app_context():
            yield request.param
            db.session.rollback()


def _a_clean_target():
    """No provider and no account of an earlier case: one provider per type, and each case's
    restore decides what its own names resolve to."""
    from api.v2.users.crud import _purge_user_dependencies
    earlier = [uid for (uid,) in db.session.query(User.id).filter(User.username.like('mx-%'))]
    UserSSOIdentity.query.filter(UserSSOIdentity.user_id.in_(earlier)).delete(synchronize_session=False)
    for uid in earlier:
        _purge_user_dependencies(uid)
    User.query.filter(User.id.in_(earlier)).delete(synchronize_session=False)
    UserSSOIdentity.query.filter(UserSSOIdentity.provider_id.isnot(None)).update(
        {UserSSOIdentity.provider_id: None}, synchronize_session=False)
    SSOProvider.query.delete(synchronize_session=False)
    db.session.commit()


def _provider(name, kind='oauth2'):
    row = SSOProvider(name=name, provider_type=kind, oauth2_issuer=f'https://{name}.example',
                      enabled=True, auto_create_users=True, default_role='viewer')
    db.session.add(row)
    db.session.flush()
    return row


def _account(name, password_hash=NOPASS, rows=()):
    user = User(username=name, email=f'{name}@matrix.test', role='admin', active=True,
                password_hash=password_hash)
    db.session.add(user)
    db.session.flush()
    for provider_id, external_id, orphan_of in rows:
        row = UserSSOIdentity(user_id=user.id, provider_id=provider_id, orphan_of=orphan_of)
        row.bind(external_id)
        db.session.add(row)
    db.session.flush()
    return user


def _rows_of(user_id):
    return sorted(((r.provider_id, r.external_id, r.orphan_of) for r in
                   UserSSOIdentity.query.filter_by(user_id=user_id)), key=repr)


def claimable_by_name(user):
    """The gate itself: a provider the account was never attached to, sending its name and
    e-mail, opens it. Also the state that lets it: no row, no password, no change owed."""
    from flask import current_app
    from api.v2.sso.account_state import legacy_sso_account
    from api.v2.sso.ldap_routes import _get_or_create_sso_user
    name, email, uid = user.username, user.email, user.id
    # The cases use the OIDC and the LDAP slot: the stranger is the SAML provider
    stranger = _provider(f'stranger-{uuid.uuid4().hex[:8]}', 'saml')
    db.session.commit()
    with current_app.test_request_context():
        opened, _error = _get_or_create_sso_user(stranger, name, email, 'N', {'name_id': 'attacker'})
        opened_id = opened.id if opened is not None else None
        db.session.rollback()
    return legacy_sso_account(db.session.get(User, uid)), opened_id == uid


def _archive(fmt, t, source, password, provider, identity, orphan, here_id):
    """The archive's sections for the account, and whether it describes it as held by SSO."""
    name = f'mx-{t}'
    external_id = f'ext-{t}' if identity != 'absent' else None
    number = {'same': here_id, 'moved': (here_id or 0) + 5000, 'absent': 7000 + int(t[:3], 16),
              'dangling': 12000 + int(t[:3], 16), 'none': None}[provider]
    ref = {'name': f'src-{t}'} if provider in ('same', 'moved', 'absent') else None
    user = {'username': name, 'email': f'{name}@matrix.test', 'role': 'admin', 'active': True,
            'password_hash': NOPASS if password == 'nopass' else REAL,
            'force_password_change': False, 'custom_role_id': None, 'custom_role_id_ref': None}
    data = {'users': [user]}
    if provider in ('same', 'moved'):
        data['sso_providers'] = [{'name': f'src-{t}', 'provider_type': 'oauth2',
                                  'oauth2_issuer': f'https://src-{t}.example', 'enabled': True}]
    if fmt == '2.254':
        user.update(auth_source=source, sso_provider_id=number, sso_provider_id_ref=ref,
                    sso_external_id=external_id, sso_orphan_of=orphan)
        held = source != 'local' or any(v is not None for v in (number, external_id, orphan))
        return data, held
    # A 3.0 archive: the source was a 2.254 upgraded there, its provider present unless dangling
    placed = {number: number} if provider in ('same', 'moved', 'absent') else {}
    rows = identity_rows([(1, source, number, external_id, orphan, user['password_hash'], False)],
                         placed)
    data['user_sso_identities'] = [
        {'user_id': 900, 'user_id_ref': {'username': name}, 'provider_id': pid,
         'provider_id_ref': ref if pid is not None else None, 'orphan_of': orphan_of,
         'external_id': ext, 'created_by': None}
        for _uid, pid, orphan_of, ext in rows]
    return data, bool(rows)


def _restore(data, mode):
    from services.backup_service import BackupService
    return BackupService()._restore_payload(data, os.urandom(32), mode)


# About a minute on one process: left to the suites, as every slow test is
@pytest.mark.slow
@pytest.mark.parametrize('fmt, mode, source, password, provider, identity, orphan, account', CASES)
def test_no_restore_leaves_an_sso_account_claimable_by_name(installation, fmt, mode, source,
                                                           password, provider, identity, orphan,
                                                           account):
    from services.database_admin.verify import check_local_email_flags
    t = uuid.uuid4().hex[:10]
    _a_clean_target()
    here = _provider(f'src-{t}') if provider in ('same', 'moved') else None
    data, held = _archive(fmt, t, source, password, provider, identity, orphan,
                          here.id if here else None)
    own = []
    if account == 'own':
        elsewhere = _provider(f'own-{t}', 'ldap')
        own = [(elsewhere.id, f'own-{t}', None), (None, f'own-orphan-{t}', None)]
        _account(f'mx-{t}', rows=own)
    elif account == 'bare':
        _account(f'mx-{t}')
    holder = None
    if identity == 'held':
        holder = _account(f'mx-{t}-holder', rows=[(here.id, f'ext-{t}', None)]).id
    db.session.commit()

    _restore(data, mode)
    db.session.expire_all()

    user = User.query.filter_by(username=f'mx-{t}').one()
    rows = _rows_of(user.id)
    if held:
        assert rows or user.force_password_change or user.password_hash != NOPASS, rows
        assert claimable_by_name(user) == (False, False)
    if mode == 'merge':
        # A merge keeps what the target held: the account's rows, the holder's identity
        assert set(own) <= set(rows), (own, rows)
        if holder is not None:
            assert _rows_of(holder) == [(here.id, f'ext-{t}', None)]
    check_local_email_flags(db.engine)


# -- the differential: step 167 and the restore of a 2.254 archive ------------------------

def _states(dialect):
    """Every 2.254 account state, with stable identities two accounts share."""
    providers = (1, 99, None) if dialect == 'sqlite' else (1, None)
    for n, (source, password, force, provider, ext, orphan) in enumerate(itertools.product(
            ('local', 'ldap', 'oauth2', 'saml'), (NOPASS, REAL), (False, True), providers,
            ('own', 'shared', None), (None, IDP_KEY))):
        if orphan is not None and provider is not None:
            continue
        external_id = {'own': f'ext-{n}', 'shared': 'ext-shared', None: None}[ext]
        yield f'df-{n:03d}', source, password, force, provider, external_id, orphan


def _upgraded(dialect, tmp_path, monkeypatch):
    with contextmanager(make_base)(dialect, tmp_path, monkeypatch, 'ssodiff') as base:
        base.run("INSERT INTO pro_sso_providers (id, name, provider_type, id_token_verify, "
                 "sync_role_on_login, enforce_2fa) VALUES (1, 'p-one', 'oauth2', TRUE, FALSE, FALSE)")
        for i, (name, source, password, force, provider, ext, orphan) in enumerate(
                _states(dialect), start=1):
            base.run("INSERT INTO users (id, username, email, password_hash, role, auth_source, "
                     "sso_provider_id, sso_external_id, sso_orphan_of, force_password_change) "
                     "VALUES (:i, :n, :e, :pw, 'viewer', :s, :p, :x, :o, :f)",
                     {'i': i, 'n': name, 'e': f'{name}@x.test', 'pw': password, 's': source,
                      'p': provider, 'x': ext, 'o': orphan, 'f': force})
        assert base.upgrade()
        rows = base.run(
            "SELECT u.username, p.name, i.external_id, i.orphan_of FROM users u "
            "JOIN user_sso_identities i ON i.user_id = u.id "
            "LEFT JOIN pro_sso_providers p ON p.id = i.provider_id")
    return sorted(rows, key=repr)


def _restored(app, dialect, tmp_path, mode):
    users = [{'username': name, 'email': f'{name}@x.test', 'password_hash': password,
              'role': 'viewer', 'active': True, 'force_password_change': force,
              'auth_source': source, 'sso_provider_id': provider,
              'sso_provider_id_ref': {'name': 'p-one'} if provider == 1 else None,
              'sso_external_id': ext, 'sso_orphan_of': orphan}
             for name, source, password, force, provider, ext, orphan in _states(dialect)]
    keys = Keys(tmp_path, f'diff-{dialect}-{mode}')
    with ExitStack() as stack:
        if dialect == 'sqlite':
            stack.enter_context(_installation(app, f"sqlite:///{tmp_path / f'diff-{mode}.db'}", keys))
        else:
            url = stack.enter_context(_a_schema_of_our_own(f'sso_diff_{uuid.uuid4().hex[:10]}'))
            stack.enter_context(_installation(app, url, keys, is_postgresql=True))
        stack.enter_context(app.app_context())
        # The target numbers its provider otherwise than the source: the archive names it
        _provider('padding', 'saml')
        _provider('p-one')
        db.session.commit()
        _restore({'users': users, 'sso_providers': [
            {'name': 'p-one', 'provider_type': 'oauth2', 'enabled': True}]}, mode)
        rows = db.session.execute(db.select(
            User.username, SSOProvider.name, UserSSOIdentity.external_id,
            UserSSOIdentity.orphan_of).join(UserSSOIdentity, UserSSOIdentity.user_id == User.id)
            .outerjoin(SSOProvider, SSOProvider.id == UserSSOIdentity.provider_id)).all()
        db.session.rollback()
        return sorted((tuple(r) for r in rows), key=repr)


@pytest.mark.parametrize('mode', ['merge', 'replace'])
@pytest.mark.parametrize('dialect', BACKENDS)
def test_a_254_archive_restored_gets_the_rows_the_upgrade_gives(app, dialect, mode, tmp_path,
                                                                 monkeypatch):
    upgraded = _upgraded(dialect, tmp_path, monkeypatch)
    restored = _restored(app, dialect, tmp_path, mode)
    assert len(upgraded) > 100
    assert restored == upgraded

