"""The ceiling on what the backup archives may take is a setting an administrator can see and change."""
import json
import os
import time

import pytest

from models import AuditLog, SystemConfig, db

SCHEDULE = '/api/v2/settings/backup/schedule'
GENERAL = '/api/v2/settings/general'


def _set(key, value):
    row = SystemConfig.query.filter_by(key=key).first()
    if row:
        row.value = value
    else:
        db.session.add(SystemConfig(key=key, value=value))
    db.session.commit()


def _patch(client, url, body):
    return client.patch(url, data=json.dumps(body), content_type='application/json')


def _stored():
    row = SystemConfig.query.filter_by(key='backup_max_total_mb').first()
    return row.value if row else None


@pytest.fixture
def restore_ceiling(app):
    with app.app_context():
        before = _stored()
    yield
    with app.app_context():
        SystemConfig.query.filter_by(key='backup_max_total_mb').delete()
        if before is not None:
            db.session.add(SystemConfig(key='backup_max_total_mb', value=before))
        db.session.commit()


@pytest.mark.usefixtures('restore_ceiling')
class TestTheScheduleRouteCarriesTheCeiling:
    def test_it_is_accepted_stored_and_returned(self, app, auth_client):
        r = _patch(auth_client, SCHEDULE, {'max_total_mb': 512})
        assert r.status_code == 200, r.data
        assert r.get_json()['data']['max_total_mb'] == 512
        assert auth_client.get(SCHEDULE).get_json()['data']['max_total_mb'] == 512
        with app.app_context():
            assert _stored() == '512'

    def test_zero_means_no_ceiling(self, app, auth_client):
        assert _patch(auth_client, SCHEDULE, {'max_total_mb': 5}).status_code == 200
        r = _patch(auth_client, SCHEDULE, {'max_total_mb': 0})
        assert r.status_code == 200
        assert r.get_json()['data']['max_total_mb'] == 0

    @pytest.mark.parametrize('value', [-1, 1.5, 'abc', True, None, 10 ** 9, [3]])
    def test_a_value_that_is_not_a_sane_size_is_refused(self, app, auth_client, value):
        assert _patch(auth_client, SCHEDULE, {'max_total_mb': 7}).status_code == 200
        r = _patch(auth_client, SCHEDULE, {'max_total_mb': value})
        assert r.status_code == 400, r.data
        assert 'max_total_mb' in r.get_json()['message']
        with app.app_context():
            assert _stored() == '7'

    def test_only_an_administrator_may_change_it(self, app, viewer_client):
        with app.app_context():
            _set('backup_max_total_mb', '0')
        r = _patch(viewer_client, SCHEDULE, {'max_total_mb': 9})
        assert r.status_code == 403
        with app.app_context():
            assert _stored() == '0'

    def test_the_change_is_audited_with_its_value(self, app, auth_client):
        assert _patch(auth_client, SCHEDULE, {'max_total_mb': 321}).status_code == 200
        with app.app_context():
            entry = (AuditLog.query.filter_by(action='backup_schedule_updated')
                     .order_by(AuditLog.id.desc()).first())
            assert 'max_total_mb=321' in entry.details


@pytest.mark.usefixtures('restore_ceiling')
class TestGeneralSettingsShareTheContract:
    def test_the_general_route_validates_it_alike(self, app, auth_client):
        r = _patch(auth_client, GENERAL, {'backup_max_total_mb': -4})
        assert r.status_code == 400
        assert 'backup_max_total_mb' in r.get_json()['message']

    def test_the_general_route_stores_and_returns_it(self, app, auth_client):
        assert _patch(auth_client, GENERAL, {'backup_max_total_mb': 64}).status_code == 200
        assert auth_client.get(GENERAL).get_json()['data']['backup_max_total_mb'] == 64
        assert auth_client.get(SCHEDULE).get_json()['data']['max_total_mb'] == 64

    def test_an_operator_cannot_write_it_through_general(self, app, operator_client):
        with app.app_context():
            _set('backup_max_total_mb', '0')
        r = _patch(operator_client, GENERAL, {'backup_max_total_mb': 1})
        assert r.status_code == 403
        with app.app_context():
            assert _stored() == '0'


@pytest.fixture(scope='module')
def operator_client(app, create_user):
    create_user(username='op_backup_ceiling', role='operator')
    client = app.test_client()
    r = client.post('/api/v2/auth/login',
                    data=json.dumps({'username': 'op_backup_ceiling',
                                     'password': 'TestPass123!'}),
                    content_type='application/json')
    assert r.status_code == 200, r.data
    return client


def _archive(directory, name, size, age_days):
    path = directory / name
    path.write_bytes(b'x' * size)
    stamp = time.time() - age_days * 86400
    os.utime(path, (stamp, stamp))
    return path


@pytest.fixture
def disk(app, tmp_path, monkeypatch):
    from config.settings import Config
    monkeypatch.setattr(Config, 'BACKUP_DIR', tmp_path, raising=False)
    monkeypatch.setattr(Config, 'HA_MODE', False, raising=False)
    return tmp_path


@pytest.mark.usefixtures('restore_ceiling')
class TestWhatTheArchivesTake:
    def test_the_schedule_says_how_much_room_and_how_many(self, app, auth_client, disk):
        _archive(disk, 'ucm_backup_20260101_000000.ucmbkp', 1000, 3)
        _archive(disk, 'ucm_backup_20260102_000000.ucmbkp', 2500, 2)
        data = auth_client.get(SCHEDULE).get_json()['data']
        assert data['stored_bytes'] == 3500
        assert data['stored_count'] == 2
        assert data['over_ceiling'] is False

    def test_over_ceiling_is_said_when_the_total_exceeds_it(self, app, auth_client, disk):
        _archive(disk, 'ucm_backup_20260101_000000.ucmbkp', 2 * 1024 * 1024, 1)
        assert _patch(auth_client, SCHEDULE, {'max_total_mb': 1}).status_code == 200
        assert auth_client.get(SCHEDULE).get_json()['data']['over_ceiling'] is True


@pytest.mark.usefixtures('restore_ceiling')
class TestRemovalsForTheCeiling:
    def _removed_names(self, app):
        with app.app_context():
            rows = AuditLog.query.filter_by(action='backup_delete').all()
            return [r.details for r in rows]

    def test_each_archive_removed_for_the_ceiling_is_audited(self, app, disk):
        from services.backup import schedule
        mb = 1024 * 1024
        names = [f'ucm_backup_2026010{i}_000000.ucmbkp' for i in range(1, 5)]
        with app.app_context():
            _set('backup_retention_days', '3650')
            _set('backup_min_keep', '1')
            _set('backup_max_total_mb', '1')
            for i, name in enumerate(names):
                _archive(disk, name, mb // 2, 10 - i)
            removed = schedule.run_backup_retention()
        assert removed >= 1
        details = ' '.join(self._removed_names(app))
        gone = [n for n in names if not (disk / n).exists()]
        assert gone and (disk / names[-1]).exists()
        for name in gone:
            assert name in details

    def test_an_archive_alone_above_the_ceiling_is_kept_and_signalled(
            self, app, auth_client, disk, caplog):
        mb = 1024 * 1024
        only = _archive(disk, 'ucm_backup_20260101_000000.ucmbkp', 2 * mb, 1)
        with app.app_context():
            _set('backup_retention_days', '3650')
            _set('backup_max_total_mb', '1')
        with caplog.at_level('WARNING'):
            r = auth_client.post('/api/v2/system/backups/run-retention')
        assert r.status_code == 200, r.data
        assert only.exists()
        assert r.get_json()['data']['removed'] == 0
        assert 'ceiling' in r.get_json()['data']['warning']
        assert any('ceiling' in rec.getMessage() for rec in caplog.records)

    def test_no_warning_when_the_archives_fit(self, app, auth_client, disk):
        _archive(disk, 'ucm_backup_20260101_000000.ucmbkp', 1000, 1)
        with app.app_context():
            _set('backup_retention_days', '3650')
            _set('backup_max_total_mb', '1')
        r = auth_client.post('/api/v2/system/backups/run-retention')
        assert r.get_json()['data'].get('warning') is None
