"""Who may touch an archive, route by route and role by role.

An archive carries every private key and every secret of the installation.
The password protects the file; it does not decide who is allowed to obtain
it. Reading backups therefore moved from `read:settings` to `admin:system`,
but each route was checked on its own, which is how the two families grew
apart in the first place: an operator could still list the archives through
one path while the other refused, and could shorten retention through General
settings while the dedicated schedule route required an administrator.

This file is the grid itself. The routes are enumerated from `app.url_map`
rather than typed here, and a route of the two backup modules that is not in
the table fails the suite: the day someone adds one, its permission is a
decision to take, not an omission to discover afterwards.

Every cell is explicit: the statuses an authorised caller may receive, and a
flat 403 for a role that does not hold the right — never a 200, never a 500,
and never a 401 for a caller who is signed in. The last test checks what a
refusal says: an operator who is told "no" must not learn from it what the
archives are called, where they are kept or what they hold.
"""
import json
from dataclasses import dataclass
from typing import Callable, Dict, Tuple

import pytest

from config.settings import Config
from models import db, SystemConfig, User
from models.user import UserSession


# The two modules that own the backup and restore routes. A route defined
# anywhere else is not in this grid on purpose (the CA "restore" route puts an
# archived authority back, and has nothing to do with a backup file).
BACKUP_MODULES = ('api.v2.system.backup', 'api.v2.settings.backup')

# A name this service could have written, that is deliberately not on disk:
# every probe below must be answered on the permission, before the file is
# even looked for.
ABSENT_ARCHIVE = 'ucm_backup_20260101_000000_000000_absent.ucmbkp'

# One that *is* on disk, so a refusal has something to leak if it wants to.
CANARY_ARCHIVE = 'ucm_backup_20260101_000000_000000_canary.ucmbkp'
CANARY_BYTES = b'LEAK-CANARY-PAYLOAD'

# Refused before anything is created: the password rule is the same on both
# create routes, so this probe reaches the view and stops there.
WEAK_PASSWORD = {'password': 'short'}

GRANTED = 'granted'

ROLES = ('admin', 'operator', 'viewer')


def _post_json(client, url, payload):
    return client.post(url, data=json.dumps(payload),
                       content_type='application/json')


def _patch_json(client, url, payload):
    return client.patch(url, data=json.dumps(payload),
                        content_type='application/json')


@dataclass(frozen=True)
class Case:
    """One route, one method, and what each role must get from it."""

    rule: str                       # as Flask registered it
    method: str
    send: Callable                  # (client) -> response
    granted: Tuple[int, ...]        # statuses an authorised caller may get
    expected: Dict[str, object]     # role -> GRANTED or a status code

    @property
    def label(self) -> str:
        return f'{self.method} {self.rule}'


def _admin_only(send, granted):
    return dict(send=send, granted=granted,
                expected={'admin': GRANTED, 'operator': 403, 'viewer': 403})


def _settings_readers(send, granted):
    """read:settings: the administrator and the operator, never the viewer."""
    return dict(send=send, granted=granted,
                expected={'admin': GRANTED, 'operator': GRANTED, 'viewer': 403})


# ---------------------------------------------------------------------------
# The grid
# ---------------------------------------------------------------------------

CASES = (
    # -- System: the archives themselves -----------------------------------
    Case(rule='/api/v2/system/backup', method='POST',
         **_admin_only(lambda c: _post_json(c, '/api/v2/system/backup', {}),
                       granted=(400,))),
    Case(rule='/api/v2/system/backup/create', method='POST',
         **_admin_only(lambda c: _post_json(c, '/api/v2/system/backup/create', {}),
                       granted=(400,))),
    Case(rule='/api/v2/system/backups', method='GET',
         **_admin_only(lambda c: c.get('/api/v2/system/backups'),
                       granted=(200,))),
    Case(rule='/api/v2/system/backup/list', method='GET',
         **_admin_only(lambda c: c.get('/api/v2/system/backup/list'),
                       granted=(200,))),
    Case(rule='/api/v2/system/backup/<filename>/download', method='GET',
         **_admin_only(
             lambda c: c.get(f'/api/v2/system/backup/{ABSENT_ARCHIVE}/download'),
             granted=(404,))),
    Case(rule='/api/v2/system/backup/<filename>', method='DELETE',
         **_admin_only(
             lambda c: c.delete(f'/api/v2/system/backup/{ABSENT_ARCHIVE}'),
             granted=(404,))),
    Case(rule='/api/v2/system/backups/bulk-delete', method='POST',
         **_admin_only(
             lambda c: _post_json(c, '/api/v2/system/backups/bulk-delete', {}),
             granted=(400,))),
    Case(rule='/api/v2/system/backups/run-retention', method='POST',
         **_admin_only(
             lambda c: c.post('/api/v2/system/backups/run-retention'),
             granted=(200,))),
    Case(rule='/api/v2/system/restore', method='POST',
         **_admin_only(lambda c: c.post('/api/v2/system/restore'),
                       granted=(400,))),
    Case(rule='/api/v2/system/backup/restore', method='POST',
         **_admin_only(lambda c: c.post('/api/v2/system/backup/restore'),
                       granted=(400,))),

    # -- Settings: the parallel family -------------------------------------
    Case(rule='/api/v2/settings/backup', method='GET',
         **_settings_readers(lambda c: c.get('/api/v2/settings/backup'),
                             granted=(200,))),
    Case(rule='/api/v2/settings/backup/create', method='POST',
         **_admin_only(
             lambda c: _post_json(c, '/api/v2/settings/backup/create',
                                  WEAK_PASSWORD),
             granted=(400,))),
    Case(rule='/api/v2/settings/backup/restore', method='POST',
         **_admin_only(lambda c: c.post('/api/v2/settings/backup/restore'),
                       granted=(400,))),
    Case(rule='/api/v2/settings/backup/<filename>/download', method='GET',
         **_admin_only(
             lambda c: c.get(f'/api/v2/settings/backup/{ABSENT_ARCHIVE}/download'),
             granted=(404,))),
    Case(rule='/api/v2/settings/backup/<filename>', method='DELETE',
         # This family has always been idempotent: a name that is already gone
         # answers 204. What matters here is who gets that far.
         **_admin_only(
             lambda c: c.delete(f'/api/v2/settings/backup/{ABSENT_ARCHIVE}'),
             granted=(204,))),
    Case(rule='/api/v2/settings/backup/schedule', method='GET',
         **_settings_readers(lambda c: c.get('/api/v2/settings/backup/schedule'),
                             granted=(200,))),
    Case(rule='/api/v2/settings/backup/schedule', method='PATCH',
         **_admin_only(
             lambda c: _patch_json(c, '/api/v2/settings/backup/schedule', {}),
             granted=(400,))),
    Case(rule='/api/v2/settings/backup/history', method='GET',
         **_admin_only(lambda c: c.get('/api/v2/settings/backup/history'),
                       granted=(200,))),
)

CASES_BY_LABEL = {case.label: case for case in CASES}


# The backup settings General settings also writes. Each one is a way to have
# the daily task delete the archives, or to change the password they are
# encrypted with, so each one is admin-only there too.
BACKUP_SETTINGS = {
    'auto_backup_enabled': False,
    'backup_frequency': 'daily',
    'backup_retention_days': 30,
    'backup_password': 'Correct-Horse-Battery-9',
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _login(app, username, password):
    client = app.test_client()
    response = client.post('/api/v2/auth/login',
                           data=json.dumps({'username': username,
                                            'password': password}),
                           content_type='application/json')
    assert response.status_code == 200, response.data
    return client


@pytest.fixture(scope='module')
def matrix_users(app, create_user):
    """One operator and one viewer of this file's own, removed afterwards.

    The suite's database is shared by every file of a worker, so the accounts
    are taken back out at the end — sessions first, since a session row points
    at its user and a restore reads this database as a database.
    """
    created = [create_user(username='matrix_backup_operator', role='operator'),
               create_user(username='matrix_backup_viewer', role='viewer')]
    yield created

    with app.app_context():
        ids = [row.id for row in User.query.filter(
            User.username.in_(['matrix_backup_operator',
                               'matrix_backup_viewer'])).all()]
        if ids:
            UserSession.query.filter(UserSession.user_id.in_(ids)).delete(
                synchronize_session=False)
            User.query.filter(User.id.in_(ids)).delete(synchronize_session=False)
            db.session.commit()


@pytest.fixture(scope='module')
def clients(app, auth_client, matrix_users):
    """One signed-in client per role, plus the anonymous one."""
    return {
        'admin': auth_client,
        'operator': _login(app, 'matrix_backup_operator', 'TestPass123!'),
        'viewer': _login(app, 'matrix_backup_viewer', 'TestPass123!'),
    }


@pytest.fixture(autouse=True)
def backup_dir(app, tmp_path, monkeypatch):
    """An archive directory of this file's own, holding one real file.

    Every probe runs against it: the granted answers (listing, retention) must
    not depend on what the rest of the suite left in the shared sandbox, and
    the refusals have a real archive to name if they are going to name one.
    """
    monkeypatch.setattr(Config, 'BACKUP_DIR', tmp_path, raising=False)
    (tmp_path / CANARY_ARCHIVE).write_bytes(CANARY_BYTES)
    yield tmp_path


@pytest.fixture
def keep_backup_settings(app):
    """Put the four backup settings back: the database is shared."""
    with app.app_context():
        before = {key: (SystemConfig.query.filter_by(key=key).first() or
                        SystemConfig(key=key, value=None)).value
                  for key in BACKUP_SETTINGS}
    yield
    with app.app_context():
        for key, value in before.items():
            row = SystemConfig.query.filter_by(key=key).first()
            if value is None:
                if row:
                    db.session.delete(row)
            elif row:
                row.value = value
            else:
                db.session.add(SystemConfig(key=key, value=value))
        db.session.commit()


def _stored(key):
    row = SystemConfig.query.filter_by(key=key).first()
    return row.value if row else None


# ---------------------------------------------------------------------------
# The table is the whole list
# ---------------------------------------------------------------------------

def _registered_backup_routes(app):
    """Every (rule, method) the two backup modules registered.

    Read from the application rather than written down twice: a table that is
    maintained by hand is a table that stops describing the routes.
    """
    found = {}
    for rule in app.url_map.iter_rules():
        view = app.view_functions.get(rule.endpoint)
        if getattr(view, '__module__', '') not in BACKUP_MODULES:
            continue
        for method in rule.methods - {'HEAD', 'OPTIONS'}:
            found[f'{method} {rule.rule}'] = rule.endpoint
    return found


class TestEveryBackupRouteHasADecidedPermission:
    def test_the_two_modules_expose_routes_at_all(self, app):
        """A filter that matched nothing would make the next test vacuous."""
        assert len(_registered_backup_routes(app)) >= 15

    def test_no_backup_route_is_missing_from_the_matrix(self, app):
        """The point of this file: a new route without a decided permission
        fails here, rather than shipping with whatever it happened to get."""
        registered = set(_registered_backup_routes(app))
        missing = sorted(registered - set(CASES_BY_LABEL))
        assert not missing, (
            'these backup routes are not in the permission matrix; add them '
            f'with the status each role must get: {missing}')

    def test_the_matrix_holds_no_route_that_no_longer_exists(self, app):
        registered = set(_registered_backup_routes(app))
        stale = sorted(set(CASES_BY_LABEL) - registered)
        assert not stale, f'the matrix describes routes that are gone: {stale}'

    def test_every_cell_is_filled(self):
        for case in CASES:
            assert set(case.expected) == set(ROLES), case.label


# ---------------------------------------------------------------------------
# The grid itself
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('label', sorted(CASES_BY_LABEL))
@pytest.mark.parametrize('role', ROLES)
def test_route_by_role(clients, label, role):
    case = CASES_BY_LABEL[label]
    expected = case.expected[role]
    response = case.send(clients[role])

    if expected is GRANTED:
        assert response.status_code in case.granted, (
            f'{role} holds the right for {label} but got '
            f'{response.status_code}: {response.data[:300]}')
        return

    assert response.status_code == expected, (
        f'{role} must be refused {label} with {expected}, got '
        f'{response.status_code}: {response.data[:300]}')
    # The two answers that would defeat the point: served, or crashed.
    assert response.status_code not in (200, 500)


@pytest.mark.parametrize('label', sorted(CASES_BY_LABEL))
def test_no_session_is_refused_before_any_permission(client, label):
    """Without a session the answer is 401, on every route of the family."""
    case = CASES_BY_LABEL[label]
    response = case.send(client)
    assert response.status_code == 401, (
        f'{label} answered {response.status_code} to a caller with no session')


@pytest.mark.parametrize('label', sorted(CASES_BY_LABEL))
@pytest.mark.parametrize('role', ('operator', 'viewer'))
def test_a_refusal_discloses_nothing_about_the_archives(
        clients, backup_dir, label, role):
    """A refusal says no; it does not describe what was refused.

    Not the name of an archive, not the directory they are kept in, not a
    single byte of one: a caller who is not allowed to list the archives must
    not be able to learn what they are called from the error that tells them
    so.
    """
    case = CASES_BY_LABEL[label]
    if case.expected[role] is GRANTED:
        pytest.skip(f'{role} holds the right for {label}')

    response = case.send(clients[role])
    body = response.data.decode(errors='replace')

    assert 'ucm_backup' not in body, f'{label} named an archive: {body[:300]}'
    assert str(backup_dir) not in body, f'{label} disclosed the directory'
    assert CANARY_BYTES.decode() not in body, f'{label} returned archive bytes'
    assert '.ucmbkp' not in body, f'{label} disclosed an archive name'

    payload = response.get_json(silent=True) or {}
    message = str(payload.get('message') or payload.get('error') or '')
    assert message, f'{label} refused without saying anything'
    assert 'permission' in message.lower() or 'forbidden' in message.lower(), \
        f'{label} refused with a message that is not about permissions: {message}'


# ---------------------------------------------------------------------------
# The same decision, taken through General settings
# ---------------------------------------------------------------------------

class TestBackupSettingsAreAdminOnlyEverywhere:
    """The schedule route is admin-only; General settings writes the same rows.

    An operator holds `write:settings`, so without an explicit list these four
    keys would be his to change — and shortening retention to a day is enough
    to have the daily task delete every archive on the server.
    """

    def test_the_backup_settings_general_exposes_are_the_ones_decided_here(
            self, auth_client):
        """Enumerated from the API, so a new backup setting fails this test."""
        from api.v2.settings.general import _ADMIN_ONLY_SETTINGS

        response = auth_client.get('/api/v2/settings/general')
        assert response.status_code == 200, response.data
        # Status the screen reads but nobody writes: the flag that a password
        # is stored, since the password itself is never returned
        read_only = {'backup_password_set'}
        exposed = {key for key in response.get_json()['data']
                   if 'backup' in key} - read_only

        assert exposed == set(BACKUP_SETTINGS), (
            'General settings exposes backup settings this matrix does not '
            f'decide: {sorted(exposed ^ set(BACKUP_SETTINGS))}')
        for key in BACKUP_SETTINGS:
            assert key in _ADMIN_ONLY_SETTINGS, \
                f'{key} can be written with write:settings alone'
        # Clearing the password stops every scheduled backup just as surely
        assert 'clear_backup_password' in _ADMIN_ONLY_SETTINGS

    @pytest.mark.parametrize('key', sorted(BACKUP_SETTINGS))
    @pytest.mark.parametrize('role', ('operator', 'viewer'))
    def test_a_backup_setting_alone_is_refused(
            self, app, clients, keep_backup_settings, key, role):
        with app.app_context():
            before = _stored(key)

        response = _patch_json(clients[role], '/api/v2/settings/general',
                               {key: BACKUP_SETTINGS[key]})
        assert response.status_code == 403, (key, role, response.data)

        with app.app_context():
            assert _stored(key) == before, \
                f'{role} changed {key} through General settings'

    @pytest.mark.parametrize('key', sorted(BACKUP_SETTINGS))
    def test_an_administrator_may_write_it(self, app, auth_client,
                                           keep_backup_settings, key):
        response = _patch_json(auth_client, '/api/v2/settings/general',
                               {key: BACKUP_SETTINGS[key]})
        assert response.status_code == 200, (key, response.data)

    def test_bundling_it_with_an_allowed_key_does_not_smuggle_it_through(
            self, app, clients, auth_client, keep_backup_settings):
        """A payload that mixes allowed and admin-only keys saves the allowed
        ones and drops the rest, rather than refusing the whole card. That is
        deliberate — and it must not become a way in: the retention the
        operator sent has to be the one value that did not land.
        """
        with app.app_context():
            SystemConfig.query.filter_by(key='backup_retention_days').delete()
            db.session.add(SystemConfig(key='backup_retention_days', value='30'))
            db.session.commit()

        current = auth_client.get('/api/v2/settings/general')
        site_name = current.get_json()['data']['site_name']

        response = _patch_json(clients['operator'], '/api/v2/settings/general',
                               {'site_name': site_name,
                                'backup_retention_days': 1})
        assert response.status_code == 200, response.data

        with app.app_context():
            assert _stored('backup_retention_days') == '30', \
                'an operator shortened retention by bundling it with a site name'

    def test_the_scheduled_backup_password_is_never_read_back(
            self, app, auth_client, keep_backup_settings):
        """It encrypts every archive the unattended task writes. Whoever may
        set it may not get it back out through the settings it lives in."""
        assert _patch_json(
            auth_client, '/api/v2/settings/general',
            {'backup_password': BACKUP_SETTINGS['backup_password']},
        ).status_code == 200

        response = auth_client.get('/api/v2/settings/general')
        assert response.status_code == 200
        body = response.data.decode()
        assert response.get_json()['data']['backup_password'] == ''
        assert BACKUP_SETTINGS['backup_password'] not in body

        with app.app_context():
            stored = _stored('backup_password')
            assert stored and stored != BACKUP_SETTINGS['backup_password'], \
                'the scheduled-backup password is stored in clear'
