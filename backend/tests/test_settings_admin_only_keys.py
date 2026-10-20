"""General settings reserved to admin:settings.

write:settings alone may save a card that mixes reserved and ordinary keys:
the reserved ones are dropped before any validation. A body made only of
reserved keys is refused with 403.
"""
import json
import logging

import pytest

from models import db, SystemConfig

URL = '/api/v2/settings/general'

# One value per reserved key, each different from the defaults. Values that
# the route validates would fail with 400 or 404 if they were ever processed
# for an operator (admin_allowed_networks excludes the test client's address).
RESERVED_VALUES = {
    'enforce_2fa': True,
    'session_timeout': 999,
    'session_max_lifetime': 7200,
    'max_login_attempts': 7,
    'lockout_duration': 1200,
    'metrics_token': 'reserved-metrics-token-0123456789',
    'key_recovery_dual_control': False,
    'min_password_length': 20,
    'max_password_length': 64,
    'password_require_uppercase': False,
    'password_require_lowercase': False,
    'password_require_numbers': False,
    'password_require_special': False,
    'hsts_enabled': False,
    'hsts_include_subdomains': False,
    'hsts_max_age': 60,
    'base_url': 'https://reserved.example.com',
    'protocol_base_url': 'http://reserved.example.com:8080',
    'acme_public_vhost': 'acme.reserved.example.com',
    'acme_public_port': 8443,
    'acme_public_tls_cert_id': 999999,
    'auto_backup_enabled': True,
    'backup_frequency': 'weekly',
    'backup_retention_days': 1,
    'backup_password': 'Reserved-Backup-Pass-123!',
    'backup_kdf': 'pbkdf2',
    'clear_backup_password': True,
    'crl_auto_delete_expired_revoked': True,
    'ocsp_responder_auto_renew': False,
    'ocsp_responder_renew_days': 3,
    'crl_auto_purge_stale_serials': True,
    'audit_retention_days': 7,
    'admin_allowed_networks': '10.0.0.0/8',
}


def _patch(client, body, **kwargs):
    return client.patch(URL, data=json.dumps(body),
                        content_type='application/json', **kwargs)


def _rows():
    db.session.expire_all()
    return {row.key: row.value for row in SystemConfig.query.all()}


@pytest.fixture
def config_snapshot(app):
    """Restores every SystemConfig row the test changed."""
    with app.app_context():
        before = _rows()
    yield before
    with app.app_context():
        for row in SystemConfig.query.all():
            if row.key not in before:
                db.session.delete(row)
            elif row.value != before[row.key]:
                row.value = before[row.key]
        present = {row.key for row in SystemConfig.query.all()}
        for key, value in before.items():
            if key not in present:
                db.session.add(SystemConfig(key=key, value=value))
        db.session.commit()


@pytest.fixture(scope='module')
def operator_client(app, create_user):
    """Holds read:settings and write:settings, never admin:settings."""
    create_user(username='op_reserved_settings', role='operator')
    client = app.test_client()
    r = client.post('/api/v2/auth/login',
                    data=json.dumps({'username': 'op_reserved_settings',
                                     'password': 'TestPass123!'}),
                    content_type='application/json')
    assert r.status_code == 200, r.data
    return client


@pytest.fixture
def api_key(auth_client):
    """Mints admin-owned API keys with explicit scopes, revoked afterwards."""
    created = []

    def _mint(permissions):
        r = auth_client.post('/api/v2/account/apikeys',
                             data=json.dumps({'name': f'reserved-settings-{len(created)}',
                                              'permissions': permissions}),
                             content_type='application/json')
        assert r.status_code == 201, r.data
        data = r.get_json()['data']
        created.append(data['id'])
        return data['key']

    yield _mint
    for key_id in created:
        auth_client.delete(f'/api/v2/account/apikeys/{key_id}')


def test_the_reserved_set_is_the_contract():
    from api.v2.settings.general import _ADMIN_ONLY_SETTINGS
    assert set(_ADMIN_ONLY_SETTINGS) == set(RESERVED_VALUES)
    assert len(RESERVED_VALUES) == 33


@pytest.mark.parametrize('key', sorted(RESERVED_VALUES))
def test_an_operator_sending_only_a_reserved_key_is_refused(
        app, operator_client, config_snapshot, key):
    r = _patch(operator_client, {key: RESERVED_VALUES[key]})
    assert r.status_code == 403, (key, r.data)
    assert key in r.get_data(as_text=True)
    with app.app_context():
        assert _rows() == config_snapshot, f'{key} changed stored settings'


@pytest.mark.parametrize('key', sorted(RESERVED_VALUES))
def test_a_reserved_key_bundled_with_an_ordinary_one_is_dropped(
        app, operator_client, config_snapshot, key):
    name = f'site-{key}'
    r = _patch(operator_client, {'system_name': name, key: RESERVED_VALUES[key]})
    assert r.status_code == 200, (key, r.data)
    with app.app_context():
        after = _rows()
    assert after.pop('system_name') == name
    expected = dict(config_snapshot)
    expected.pop('system_name', None)
    assert after == expected, f'{key} was written by an operator'


def test_operator_saves_the_name_but_not_the_session_timeout(
        app, operator_client, config_snapshot):
    before = config_snapshot.get('session_timeout')
    r = _patch(operator_client, {'system_name': 'x', 'session_timeout': 999})
    assert r.status_code == 200, r.data
    with app.app_context():
        rows = _rows()
    assert rows['system_name'] == 'x'
    assert rows.get('session_timeout') == before


def test_operator_session_timeout_alone_changes_nothing(
        app, operator_client, config_snapshot):
    r = _patch(operator_client, {'session_timeout': 999})
    assert r.status_code == 403
    assert 'session_timeout' in r.get_json()['message']
    with app.app_context():
        assert _rows() == config_snapshot


@pytest.mark.parametrize('body', [
    {'session_timeout': 'abc', 'timezone': 'Europe/Paris'},
    {'hsts_max_age': 'abc', 'timezone': 'Europe/Paris'},
    {'backup_retention_days': 'abc', 'timezone': 'Europe/Paris'},
    {'base_url': 'not a url', 'timezone': 'Europe/Paris'},
])
def test_dropped_keys_are_never_validated(app, operator_client, config_snapshot, body):
    reserved = next(k for k in body if k != 'timezone')
    r = _patch(operator_client, body)
    assert r.status_code == 200, r.data
    with app.app_context():
        rows = _rows()
    assert rows['timezone'] == 'Europe/Paris'
    assert rows.get(reserved) == config_snapshot.get(reserved)


def test_invalid_reserved_value_next_to_the_name_saves_the_name(
        app, operator_client, config_snapshot):
    r = _patch(operator_client, {'system_name': 'x', 'session_timeout': 'abc'})
    assert r.status_code == 200, r.data
    with app.app_context():
        rows = _rows()
    assert rows['system_name'] == 'x'
    assert rows.get('session_timeout') == config_snapshot.get('session_timeout')


@pytest.mark.parametrize('extra', [{'force': True}, {'no_such_setting': 1}])
def test_a_meta_or_unknown_key_is_enough_to_avoid_the_refusal(
        app, operator_client, config_snapshot, extra):
    r = _patch(operator_client, {'session_timeout': 999, **extra})
    assert r.status_code == 200, r.data
    with app.app_context():
        assert _rows() == config_snapshot


def test_operator_ordinary_keys_are_saved(app, operator_client, config_snapshot):
    r = _patch(operator_client, {'system_name': 'Operator PKI', 'timezone': 'Asia/Tokyo',
                                 'date_format': 'iso', 'show_time': False})
    assert r.status_code == 200, r.data
    with app.app_context():
        rows = _rows()
    assert rows['system_name'] == 'Operator PKI'
    assert rows['timezone'] == 'Asia/Tokyo'
    assert rows['date_format'] == 'iso'
    assert rows['show_time'] == 'false'


def test_dropped_keys_are_logged(operator_client, config_snapshot, caplog):
    with caplog.at_level(logging.INFO, logger='api.v2.settings.general'):
        r = _patch(operator_client, {'system_name': 'x', 'session_timeout': 999,
                                     'enforce_2fa': True})
    assert r.status_code == 200
    logged = ' '.join(rec.getMessage() for rec in caplog.records
                      if rec.levelno == logging.INFO)
    assert 'session_timeout' in logged and 'enforce_2fa' in logged


def test_an_administrator_writes_a_reserved_key(app, auth_client, config_snapshot):
    r = _patch(auth_client, {'session_timeout': 999})
    assert r.status_code == 200, r.data
    with app.app_context():
        assert _rows()['session_timeout'] == '999'


def test_an_administrator_writes_every_key_of_a_mixed_body(
        app, auth_client, config_snapshot):
    r = _patch(auth_client, {'system_name': 'Admin PKI', 'session_timeout': 1234,
                             'enforce_2fa': False})
    assert r.status_code == 200, r.data
    with app.app_context():
        rows = _rows()
    assert rows['system_name'] == 'Admin PKI'
    assert rows['session_timeout'] == '1234'
    assert rows['enforce_2fa'] == 'false'


def test_the_check_is_on_the_permission_not_the_role(
        app, operator_client, api_key, config_snapshot):
    """An admin-owned key without admin:settings is refused; a key holding it,
    though it is not '*', may write."""
    narrow = api_key(['read:settings', 'write:settings'])
    r = _patch(app.test_client(), {'session_timeout': 999},
               headers={'X-API-Key': narrow})
    assert r.status_code == 403, r.data

    granted = api_key(['read:settings', 'write:settings', 'admin:settings'])
    r = _patch(app.test_client(), {'session_timeout': 999},
               headers={'X-API-Key': granted})
    assert r.status_code == 200, r.data
    with app.app_context():
        assert _rows()['session_timeout'] == '999'


def test_an_operator_still_reads_the_reserved_values(app, operator_client, config_snapshot):
    with app.app_context():
        row = SystemConfig.query.filter_by(key='session_timeout').first()
        if row is None:
            db.session.add(SystemConfig(key='session_timeout', value='4321'))
        else:
            row.value = '4321'
        db.session.commit()
    r = operator_client.get(URL)
    assert r.status_code == 200
    data = r.get_json()['data']
    assert data['session_timeout'] == 4321
    assert data['backup_password'] == ''
    assert data['metrics_token'] == ''
