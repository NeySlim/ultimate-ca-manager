"""GET /api/v2/system/instance (#403): what a fleet console reads of one instance.

Readable by a key holding read:instance and by nothing narrower; carries no secret; its
instance_id is the database's, the same across restarts and on every node of a cluster.
"""
import json
from datetime import timedelta

import pytest

from config.settings import Config
from models import db, CA, SystemConfig
from services.backup import installation
from tests.conftest import assert_success, get_json
from utils.datetime_utils import utc_now

ROUTE = '/api/v2/system/instance'
TOP_LEVEL = {'schema_version', 'instance_id', 'generated_at', 'version', 'update_channel', 'install',
             'mode', 'database', 'health', 'cas', 'update', 'backup', 'fips'}


def _key(auth_client, permissions, name='instance-state'):
    r = auth_client.post('/api/v2/account/apikeys', data=json.dumps(
        {'name': name, 'permissions': permissions}), content_type='application/json')
    return assert_success(r, 201)['key']


@pytest.fixture(scope='module')
def state_key(auth_client):
    return _key(auth_client, ['read:instance'])


def _read(app, key):
    return app.test_client().get(ROUTE, headers={'X-API-Key': key})


def test_a_key_scoped_to_read_instance_reads_the_state(app, state_key):
    data = assert_success(_read(app, state_key))
    assert set(data) == TOP_LEVEL
    assert data['schema_version'] == 1
    assert data['version'] == Config.APP_VERSION
    assert data['update_channel'] in ('stable', 'rc')
    assert data['health']['status'] in ('ok', 'degraded', 'safe_mode', 'maintenance')
    assert isinstance(data['fips']['active'], bool)


def test_a_key_without_the_scope_is_refused(app, auth_client):
    key = _key(auth_client, ['read:certificates', 'read:settings'], name='no-instance-scope')
    assert _read(app, key).status_code == 403


def test_no_credential_is_refused(app):
    assert app.test_client().get(ROUTE).status_code == 401


def test_a_viewer_session_is_refused(viewer_client):
    assert viewer_client.get(ROUTE).status_code == 403


def test_a_non_admin_cannot_mint_the_scope(viewer_client):
    r = viewer_client.post('/api/v2/account/apikeys', data=json.dumps(
        {'name': 'x', 'permissions': ['read:instance']}), content_type='application/json')
    assert r.status_code == 403


def test_the_scope_is_kept_from_custom_roles():
    from auth.permissions import CUSTOM_ROLE_GRANTABLE_PERMISSIONS, is_reserved_permission
    assert is_reserved_permission('read:instance')
    assert 'read:instance' not in CUSTOM_ROLE_GRANTABLE_PERMISSIONS


def test_the_database_is_named_never_located(app, state_key):
    data = assert_success(_read(app, state_key))
    assert set(data['database']) == {'engine', 'server_version'}
    with app.app_context():
        assert data['database']['engine'] == db.engine.dialect.name
    body = _read(app, state_key).get_data(as_text=True)
    url = app.config['SQLALCHEMY_DATABASE_URI']
    assert url not in body
    assert '://' not in json.dumps(data['database'])


def test_no_secret_reaches_the_answer(app, state_key, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://ucm:s3cr3t-db-password@db.example:5432/ucm')
    monkeypatch.setenv('UCM_ENCRYPTION_KEY', 'kek-material-never-shown')
    secret_key = app.config.get('SECRET_KEY')
    body = _read(app, state_key).get_data(as_text=True)
    for needle in ('s3cr3t-db-password', 'kek-material-never-shown', 'key_hash', 'ucm_ak_'):
        assert needle not in body
    if isinstance(secret_key, str) and secret_key:
        assert secret_key not in body


def test_the_instance_id_is_the_stored_one_and_stays(app, state_key):
    first = assert_success(_read(app, state_key))['instance_id']
    with app.app_context():
        assert first and first == installation.installation_id()
    assert assert_success(_read(app, state_key))['instance_id'] == first
    with app.app_context():
        # Read from the database each time: a restart, which clears every process cache, keeps it
        row = SystemConfig.query.filter_by(key=installation.CONFIG_KEY).first()
        row.value = 'a' * 32
        db.session.commit()
    try:
        assert assert_success(_read(app, state_key))['instance_id'] == 'a' * 32
    finally:
        with app.app_context():
            row = SystemConfig.query.filter_by(key=installation.CONFIG_KEY).first()
            row.value = first
            db.session.commit()


def test_every_node_of_a_cluster_answers_the_same_instance_id(app, state_key, monkeypatch):
    before = assert_success(_read(app, state_key))['instance_id']
    monkeypatch.setattr(Config, 'HA_MODE', True)
    for node in ('node-a', 'node-b'):
        monkeypatch.setattr(Config, 'NODE_ID', node)
        data = assert_success(_read(app, state_key))
        assert data['instance_id'] == before
        assert data['mode']['ha'] is True and data['mode']['node_id'] == node


def test_the_id_is_created_once_when_missing(app, state_key):
    with app.app_context():
        kept = SystemConfig.query.filter_by(key=installation.CONFIG_KEY).first()
        value = kept.value if kept else None
        if kept:
            db.session.delete(kept)
            db.session.commit()
    try:
        created = assert_success(_read(app, state_key))['instance_id']
        assert len(created) == 32
        assert assert_success(_read(app, state_key))['instance_id'] == created
    finally:
        if value:
            with app.app_context():
                row = SystemConfig.query.filter_by(key=installation.CONFIG_KEY).first()
                row.value = value
                db.session.commit()


def test_single_node_mode_names_no_cluster(app, state_key, monkeypatch):
    monkeypatch.setattr(Config, 'HA_MODE', False)
    mode = assert_success(_read(app, state_key))['mode']
    assert mode == {'ha': False, 'node_id': None, 'nodes': None}


def test_cas_counts_and_near_expirations(app, state_key):
    now = utc_now()
    with app.app_context():
        rows = [CA(refid=f'inst-state-{i}', descr=f'instance state {i}', crt='-----BEGIN CERTIFICATE-----x',
                   valid_to=now + delta, serial=0)
                for i, delta in enumerate((timedelta(days=30), timedelta(days=200), timedelta(days=-1)))]
        db.session.add_all(rows)
        db.session.commit()
        ids = [r.id for r in rows]
    try:
        cas = assert_success(_read(app, state_key))['cas']
        assert set(cas) == {'total', 'active', 'expired', 'expiring_90_days', 'expiring_365_days', 'next_expiry'}
        assert cas['total'] >= 3 and cas['expired'] >= 1
        assert cas['expiring_90_days'] >= 1 and cas['expiring_365_days'] >= cas['expiring_90_days'] + 1
        assert cas['next_expiry'] is not None
    finally:
        with app.app_context():
            CA.query.filter(CA.id.in_(ids)).delete(synchronize_session=False)
            db.session.commit()


def test_update_availability_comes_from_the_last_check_without_network(app, state_key, monkeypatch):
    import services.updates as updates
    monkeypatch.setattr(updates, 'check_for_updates',
                        lambda *a, **k: pytest.fail('the state route must not reach GitHub'))
    with app.app_context():
        for key in (updates._NOTIFIED_VERSION_KEY, updates._LAST_CHECK_TS_KEY):
            SystemConfig.query.filter_by(key=key).delete()
        db.session.commit()
    assert assert_success(_read(app, state_key))['update'] == {
        'available': None, 'latest_version': None, 'checked_at': None}
    with app.app_context():
        db.session.add(SystemConfig(key=updates._NOTIFIED_VERSION_KEY, value='999.0'))
        db.session.add(SystemConfig(key=updates._LAST_CHECK_TS_KEY, value='1700000000'))
        db.session.commit()
    try:
        update = assert_success(_read(app, state_key))['update']
        assert update['available'] is True and update['latest_version'] == '999.0'
        assert update['checked_at'].startswith('2023-11-14')
    finally:
        with app.app_context():
            for key in (updates._NOTIFIED_VERSION_KEY, updates._LAST_CHECK_TS_KEY):
                SystemConfig.query.filter_by(key=key).delete()
            db.session.commit()


def test_backup_reports_the_schedule_and_newest_archive(app, state_key):
    backup = assert_success(_read(app, state_key))['backup']
    assert set(backup) == {'scheduled', 'last_archive_at', 'last_outcome', 'last_outcome_at'}
    assert isinstance(backup['scheduled'], bool)


def test_the_answer_is_not_cached_by_intermediaries(app, state_key):
    r = _read(app, state_key)
    assert 'no-store' in (r.headers.get('Cache-Control') or '')
    assert get_json(r)['data']['generated_at']
