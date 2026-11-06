"""Two families of backup routes, one set of answers.

`/api/v2/settings/backup/*` and `/api/v2/system/backup/*` grew separately and
answered the same question two ways: one refused a traversal, an extension it
never writes, a name `secure_filename()` had to change and a symlink, the other
took whatever came out of `secure_filename()`. The schedule was worse — the
dedicated route bounded frequency and retention, General settings accepted any
string and any number, and reading the schedule back silently replaced what it
could not use.

Each test here takes one input and sends it down both paths. The point is not
that a given path refuses it: it is that the two paths agree, because the
decision is made in one place (`services/backup/storage.py` for archive names,
`services/backup/settings_contract.py` for schedule values).
"""
import json
import os

import pytest

from config.settings import Config
from models import db, SystemConfig
from services.backup import storage
from services.backup.settings_contract import (
    BackupSettingError,
    MAX_RETENTION_DAYS,
    validate_frequency,
    validate_retention_days,
)

from tests.fresh_app import fresh_app_fixtures

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()


# The two download routes, the two delete routes, the two settings routes.
DOWNLOAD_ROUTES = (
    '/api/v2/settings/backup/{name}/download',
    '/api/v2/system/backup/{name}/download',
)
DELETE_ROUTES = (
    '/api/v2/settings/backup/{name}',
    '/api/v2/system/backup/{name}',
)

ARCHIVE = 'ucm_backup_20260913_120000_000000_abcdef123456.ucmbkp'


def _set(key, value):
    row = SystemConfig.query.filter_by(key=key).first()
    if row:
        row.value = value
    else:
        db.session.add(SystemConfig(key=key, value=value))
    db.session.commit()


def _get(key):
    row = SystemConfig.query.filter_by(key=key).first()
    return row.value if row else None


@pytest.fixture
def backup_dir(app, tmp_path, monkeypatch):
    """A backup directory of this test's own, for both families of routes."""
    with app.app_context():
        monkeypatch.setattr(Config, 'BACKUP_DIR', tmp_path, raising=False)
        yield tmp_path


@pytest.fixture
def keep_schedule(app):
    """Restore the stored schedule: the suite shares one database."""
    keys = ('auto_backup_enabled', 'backup_frequency', 'backup_retention_days')
    with app.app_context():
        before = {key: _get(key) for key in keys}
    yield
    with app.app_context():
        for key, value in before.items():
            if value is None:
                SystemConfig.query.filter_by(key=key).delete()
            else:
                _set(key, value)
        db.session.commit()


def _patch(client, url, payload):
    return client.patch(url, data=json.dumps(payload),
                        content_type='application/json')


def _message(response) -> str:
    """The message a refusal carries, whatever shape the route answers in."""
    body = response.get_json(silent=True) or {}
    return str(body.get('message') or body.get('error') or '')


# ---------------------------------------------------------------------------
# Archive names
# ---------------------------------------------------------------------------

class TestBothDownloadRoutesRefuseTheSameNames:
    """A name one route would not serve is a name neither serves."""

    @pytest.mark.parametrize('name, why', [
        ('..%2F..%2Fetc%2Fpasswd', 'traversal'),
        ('..', 'traversal'),
        ('%2Fetc%2Fpasswd', 'absolute path'),
        ('ucm backup.ucmbkp', 'secure_filename would rewrite the space'),
        ('ucm_backup_é.ucmbkp', 'secure_filename would drop the accent'),
        ('../ucm_backup_x.ucmbkp', 'secure_filename would drop the traversal'),
        ('ucm_backup_x.txt', 'extension this service never writes'),
        ('passwd', 'no extension at all'),
    ])
    def test_refused_identically(self, auth_client, backup_dir, name, why):
        statuses = []
        for route in DOWNLOAD_ROUTES:
            response = auth_client.get(route.format(name=name))
            statuses.append(response.status_code)
            assert response.status_code != 200, (
                f'{route} served {name!r} ({why})')
            assert response.status_code in (400, 403, 404), \
                f'{route} answered {response.status_code} for {name!r}'

        assert statuses[0] == statuses[1], (
            f'{name!r} ({why}) is refused with {statuses[0]} by Settings and '
            f'{statuses[1]} by System')

    def test_a_symlink_is_refused_by_both(self, auth_client, backup_dir,
                                          tmp_path):
        """An archive is a file this service wrote, never a link to one."""
        secret = tmp_path / 'outside.txt'
        secret.write_bytes(b'not an archive')
        link = backup_dir / 'ucm_backup_link.ucmbkp'
        os.symlink(secret, link)

        for route in DOWNLOAD_ROUTES:
            response = auth_client.get(route.format(name=link.name))
            assert response.status_code == 403, \
                f'{route} followed a symlink: {response.status_code}'
            assert b'not an archive' not in response.data

    def test_a_real_archive_is_served_by_both(self, auth_client, backup_dir):
        """The same valid name works on both, with the same bytes."""
        (backup_dir / ARCHIVE).write_bytes(b'UCMBKP-test-payload')

        for route in DOWNLOAD_ROUTES:
            response = auth_client.get(route.format(name=ARCHIVE))
            assert response.status_code == 200, \
                f'{route} refused a valid archive: {response.data}'
            assert response.data == b'UCMBKP-test-payload'

    def test_a_missing_archive_is_a_404_on_both(self, auth_client, backup_dir):
        for route in DOWNLOAD_ROUTES:
            response = auth_client.get(route.format(name=ARCHIVE))
            assert response.status_code == 404, route


class TestBothDeleteRoutesRefuseTheSameNames:
    """Deleting resolves the name exactly as downloading does.

    The two routes still answer differently once the name is accepted — the
    Settings one is idempotent (204 whether or not the file was there), the
    System one reports 404 — which is the response shape their callers have
    always had. What they no longer disagree on is which names get that far.
    """

    @pytest.mark.parametrize('name', [
        '..%2F..%2Fetc%2Fpasswd',
        'ucm backup.ucmbkp',
        'ucm_backup_x.txt',
        'passwd',
    ])
    def test_refused_identically(self, auth_client, backup_dir, name):
        statuses = [auth_client.delete(route.format(name=name)).status_code
                    for route in DELETE_ROUTES]
        # 4xx, without pinning which one: a name whose decoded path holds a
        # separator never reaches either view, and the SPA catch-all (GET only)
        # answers that DELETE with 405 on both families alike.
        for status in statuses:
            assert status >= 400, statuses
        assert statuses[0] == statuses[1], (
            f'{name!r} is refused with {statuses[0]} by Settings and '
            f'{statuses[1]} by System')

    def test_a_symlink_is_refused_by_both(self, auth_client, backup_dir,
                                          tmp_path):
        target = tmp_path / 'outside.txt'
        target.write_bytes(b'not an archive')

        for route in DELETE_ROUTES:
            link = backup_dir / 'ucm_backup_link.ucmbkp'
            os.symlink(target, link)
            try:
                response = auth_client.delete(route.format(name=link.name))
                assert response.status_code == 403, \
                    f'{route} accepted a symlink: {response.status_code}'
                assert target.is_file(), f'{route} deleted through a symlink'
            finally:
                link.unlink(missing_ok=True)

    def test_a_real_archive_is_deleted_by_both(self, auth_client, backup_dir):
        for route in DELETE_ROUTES:
            (backup_dir / ARCHIVE).write_bytes(b'x')
            response = auth_client.delete(route.format(name=ARCHIVE))
            assert response.status_code in (200, 204), \
                f'{route} refused to delete a valid archive: {response.data}'
            assert not (backup_dir / ARCHIVE).exists(), route


class TestArchiveResolutionIsOneImplementation:
    """The rule itself, where both families now read it."""

    @pytest.mark.parametrize('name', [
        '../../etc/passwd', '..', '/etc/passwd', 'ucm backup.ucmbkp',
        'ucm_backup_x.txt', 'passwd', '', None, 12,
    ])
    def test_refused(self, backup_dir, name):
        with pytest.raises((ValueError, PermissionError)):
            storage.resolve_archive(name)

    def test_accepts_the_names_it_writes(self, backup_dir):
        for name in (ARCHIVE, 'ucm_backup_old.json.enc'):
            resolved, filename = storage.resolve_archive(name)
            assert filename == name
            assert resolved.parent == backup_dir.resolve()


class TestBothCreateRoutesWriteTheSameWay:
    """One naming scheme, one directory, one validation record."""

    def test_same_directory_and_naming(self, auth_client, backup_dir):
        password = 'ParityBackupPass!42'
        created = {}

        for label, url, payload in (
            ('settings', '/api/v2/settings/backup/create', {'password': password}),
            ('system', '/api/v2/system/backup/create', {'password': password}),
        ):
            response = auth_client.post(url, data=json.dumps(payload),
                                        content_type='application/json')
            assert response.status_code == 200, (label, response.data)
            data = response.get_json()['data']
            created[label] = data

            name = data['filename']
            assert (backup_dir / name).is_file(), \
                f'{label} wrote outside the configured directory'
            # Both are resolvable by the shared resolver, which is what the
            # download routes will ask: a name one family wrote and the other
            # would refuse to serve is the divergence this closes.
            storage.resolve_archive(name)
            assert name in storage.read_catalog(backup_dir), \
                f'{label} published an archive with no validation record'
            assert data['size_bytes'] == (backup_dir / name).stat().st_size

        assert created['settings']['filename'] != created['system']['filename']

    def test_no_absolute_path_is_returned(self, auth_client, backup_dir):
        """Where the instance keeps its archives is not the caller's business."""
        response = auth_client.post(
            '/api/v2/settings/backup/create',
            data=json.dumps({'password': 'ParityBackupPass!42'}),
            content_type='application/json')
        assert response.status_code == 200, response.data
        data = response.get_json()['data']
        assert 'path' not in data
        assert str(backup_dir) not in json.dumps(data)

    @pytest.mark.parametrize('password, rule', [
        ('short', 'at least'),
        ('aaaaaaaaaaaaaaaa', 'distinct'),
    ])
    def test_same_password_rule(self, auth_client, backup_dir, password, rule):
        for url in ('/api/v2/settings/backup/create',
                    '/api/v2/system/backup/create'):
            response = auth_client.post(url, data=json.dumps({'password': password}),
                                        content_type='application/json')
            assert response.status_code == 400, (url, response.data)
            assert rule in _message(response).lower(), (url, response.data)


# ---------------------------------------------------------------------------
# Schedule values
# ---------------------------------------------------------------------------

SCHEDULE_URL = '/api/v2/settings/backup/schedule'
GENERAL_URL = '/api/v2/settings/general'


class TestBothSettingsRoutesRefuseTheSameFrequencies:

    @pytest.mark.parametrize('frequency', [
        'hourly', 'DAILY', 'every-monday', '', None, 7,
    ])
    def test_refused_by_both(self, auth_client, keep_schedule, app, frequency):
        with app.app_context():
            _set('backup_frequency', 'daily')

        schedule = _patch(auth_client, SCHEDULE_URL, {'frequency': frequency})
        assert schedule.status_code == 400, schedule.data
        general = _patch(auth_client, GENERAL_URL, {'backup_frequency': frequency})
        assert general.status_code == 400, general.data

        # The refusal names the rule, not just "invalid": an administrator has
        # to be able to tell which cadences exist.
        for response in (schedule, general):
            message = _message(response)
            assert 'must be one of' in message, message
            for known in ('daily', 'weekly', 'monthly'):
                assert known in message, message

        with app.app_context():
            assert _get('backup_frequency') == 'daily', \
                'a refused frequency was stored anyway'

    def test_accepted_by_both(self, auth_client, keep_schedule, app):
        assert _patch(auth_client, SCHEDULE_URL,
                      {'frequency': 'weekly'}).status_code == 200
        with app.app_context():
            assert _get('backup_frequency') == 'weekly'

        assert _patch(auth_client, GENERAL_URL,
                      {'backup_frequency': 'monthly'}).status_code == 200
        with app.app_context():
            assert _get('backup_frequency') == 'monthly'


class TestBothSettingsRoutesRefuseTheSameRetentions:

    @pytest.mark.parametrize('retention', [
        0, -1, MAX_RETENTION_DAYS + 1, 99999,
    ])
    def test_out_of_bounds_refused_by_both(self, auth_client, keep_schedule,
                                           app, retention):
        with app.app_context():
            _set('backup_retention_days', '30')

        schedule = _patch(auth_client, SCHEDULE_URL,
                          {'retention_days': retention})
        general = _patch(auth_client, GENERAL_URL,
                         {'backup_retention_days': retention})

        for response in (schedule, general):
            assert response.status_code == 400, response.data
            message = _message(response)
            assert f'between 1 and {MAX_RETENTION_DAYS}' in message, message

        with app.app_context():
            assert _get('backup_retention_days') == '30', \
                'a refused retention was stored anyway'

    @pytest.mark.parametrize('retention', [
        None, '', 'forever', 7.5, True, [30],
    ])
    def test_non_integer_refused_by_both(self, auth_client, keep_schedule,
                                         app, retention):
        with app.app_context():
            _set('backup_retention_days', '30')

        schedule = _patch(auth_client, SCHEDULE_URL,
                          {'retention_days': retention})
        general = _patch(auth_client, GENERAL_URL,
                         {'backup_retention_days': retention})

        for response in (schedule, general):
            assert response.status_code == 400, (retention, response.data)
            assert 'whole number of days' in _message(response), response.data

        with app.app_context():
            assert _get('backup_retention_days') == '30'

    def test_accepted_by_both(self, auth_client, keep_schedule, app):
        assert _patch(auth_client, SCHEDULE_URL,
                      {'retention_days': 14}).status_code == 200
        with app.app_context():
            assert _get('backup_retention_days') == '14'

        assert _patch(auth_client, GENERAL_URL,
                      {'backup_retention_days': 21}).status_code == 200
        with app.app_context():
            assert _get('backup_retention_days') == '21'

    def test_a_valid_schedule_goes_through_both_at_once(
            self, auth_client, keep_schedule, app):
        assert _patch(auth_client, SCHEDULE_URL, {
            'enabled': False, 'frequency': 'weekly', 'retention_days': 45,
        }).status_code == 200
        assert _patch(auth_client, GENERAL_URL, {
            'auto_backup_enabled': False, 'backup_frequency': 'weekly',
            'backup_retention_days': 45,
        }).status_code == 200

        with app.app_context():
            assert _get('backup_frequency') == 'weekly'
            assert _get('backup_retention_days') == '45'


class TestTheScheduleContractIsOneImplementation:
    """The rule itself, where both routes now read it."""

    def test_frequencies_come_from_the_scheduler(self):
        from services.backup.schedule import _VALID_FREQUENCIES
        from services.backup.settings_contract import valid_frequencies

        assert valid_frequencies() == tuple(_VALID_FREQUENCIES), \
            'the contract would accept a cadence the scheduler cannot run'

    @pytest.mark.parametrize('value', ['hourly', '', None, 7, 'DAILY'])
    def test_frequency_refused(self, value):
        with pytest.raises(BackupSettingError):
            validate_frequency(value)

    @pytest.mark.parametrize('value', [0, -1, 3651, None, '', 'x', 7.5, True])
    def test_retention_refused(self, value):
        with pytest.raises(BackupSettingError):
            validate_retention_days(value)

    @pytest.mark.parametrize('value, expected', [
        (1, 1), (30, 30), ('30', 30), (' 30 ', 30), (30.0, 30),
        (MAX_RETENTION_DAYS, MAX_RETENTION_DAYS),
    ])
    def test_retention_accepted(self, value, expected):
        assert validate_retention_days(value) == expected

    def test_the_message_names_the_field_it_was_given(self):
        """Each route names its own field, one rule behind both."""
        with pytest.raises(BackupSettingError) as exc:
            validate_retention_days(0, 'retention_days')
        assert str(exc.value).startswith('retention_days')

        with pytest.raises(BackupSettingError) as exc:
            validate_retention_days(0)
        assert str(exc.value).startswith('backup_retention_days')
