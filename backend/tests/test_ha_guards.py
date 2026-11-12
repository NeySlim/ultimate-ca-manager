"""Host-local operations answer 409 ha_mode when the node runs with UCM_HA=1."""
import pytest
from flask import Flask

from config.settings import Config
from utils.ha import reject_in_ha

ROUTES = [
    '/api/v2/database/switch',
    '/api/v2/database/migrate',
    '/api/v2/system/security/rotate-secrets',
    '/api/v2/system/updates/install',
    '/api/v2/system/restore',
    '/api/v2/system/backup/restore',
    '/api/v2/settings/backup/restore',
]
RESTORE_ROUTES = [r for r in ROUTES if 'restore' in r]


@pytest.mark.parametrize('path', ROUTES)
def test_route_refused_in_ha(auth_client, monkeypatch, path):
    monkeypatch.setattr(Config, 'HA_MODE', True)
    r = auth_client.post(path, json={})
    assert r.status_code == 409, r.data
    body = r.get_json()
    assert body['code'] == 'ha_mode'
    assert body['status'] == 409


@pytest.mark.parametrize('path', RESTORE_ROUTES)
def test_restore_route_keeps_its_usual_answer_without_ha(auth_client, monkeypatch, path):
    monkeypatch.setattr(Config, 'HA_MODE', False)
    r = auth_client.post(path, data={})
    assert r.status_code == 400, r.data


def test_decorator_passes_through_without_ha(monkeypatch):
    app = Flask(__name__)

    @app.route('/x')
    @reject_in_ha()
    def x():
        return 'ok'

    c = app.test_client()
    monkeypatch.setattr(Config, 'HA_MODE', False)
    assert c.get('/x').data == b'ok'
    monkeypatch.setattr(Config, 'HA_MODE', True)
    assert c.get('/x').status_code == 409


def test_scheduled_auto_update_skipped_in_ha(monkeypatch):
    import services.updates as updates
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.delenv('UCM_DOCKER', raising=False)

    def boom(*a, **k):
        raise AssertionError('auto-update must not proceed in HA mode')
    monkeypatch.setattr(updates, '_cfg_get', boom)
    monkeypatch.setattr(updates, 'install_update', boom)
    updates._auto_install({'latest_version': '99.0', 'download_url': 'http://x/p.deb'})


def test_service_restart_in_ha_is_a_rolling_restart_even_in_a_container(auth_client, monkeypatch):
    import services.cluster_commands as cc
    monkeypatch.setattr(cc, 'request_restart', lambda: (True, 'rolling'))
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.setattr('api.v2.system.service.is_docker', lambda: True)
    r = auth_client.post('/api/v2/system/service/restart', json={})
    assert r.status_code == 200, r.data
    assert r.get_json()['message'] == 'rolling'


def test_service_restart_keeps_its_usual_answer_without_ha(auth_client, monkeypatch):
    monkeypatch.setattr(Config, 'HA_MODE', False)
    monkeypatch.setattr('api.v2.system.service.is_docker', lambda: True)
    r = auth_client.post('/api/v2/system/service/restart', json={})
    assert r.status_code == 400, r.data


def _no_side_effects(monkeypatch, path):
    """Make the route refuse early without HA, so the test never mutates the host."""
    if path == '/api/v2/database/switch':
        monkeypatch.setattr('api.v2.database.is_docker', lambda: True)
    elif path == '/api/v2/system/updates/install':
        monkeypatch.setenv('UCM_DOCKER', '1')
    elif path.endswith('/enable-encryption'):
        monkeypatch.setattr('security.encryption.KeyEncryption.is_enabled',
                            property(lambda self: False), raising=False)
        monkeypatch.setattr('security.master_key_bootstrap.ephemeral_key_dir_refusal',
                            lambda: 'test')
    elif path.endswith('/https/unbind'):
        monkeypatch.setattr('services.https_binding.get_bound_refid', lambda: '')
    elif path.endswith('/disable-encryption'):
        monkeypatch.setattr('security.encryption.key_encryption_required', lambda: True)


USUAL = {
    '/api/v2/database/switch': (400, {}),
    '/api/v2/database/migrate': (400, {}),
    '/api/v2/system/security/enable-encryption': (409, {}),
    '/api/v2/system/security/disable-encryption': (409, {}),
    '/api/v2/system/security/encrypt-all-keys': (200, {}),
    '/api/v2/system/security/rotate-secrets': (400, {'new_secret': 'short'}),
    '/api/v2/system/updates/install': (400, {}),
    '/api/v2/system/https/unbind': (400, {}),
    # a string validity fails before any file is written
    '/api/v2/system/https/regenerate': (500, {'validity_days': 'x'}),
    '/api/v2/system/https/apply': (400, {}),
}


@pytest.mark.parametrize('path', list(USUAL))
def test_route_keeps_its_usual_answer_without_ha(auth_client, monkeypatch, path):
    monkeypatch.setattr(Config, 'HA_MODE', False)
    _no_side_effects(monkeypatch, path)
    code, body = USUAL[path]
    r = auth_client.post(path, json=body)
    assert r.status_code == code, r.data
    assert (r.get_json() or {}).get('code') != 'ha_mode'


def _stub_bound_renewal(monkeypatch):
    import types
    import services.https_binding as hb
    import utils.service_manager as sm
    import models
    from services.audit_service import AuditService
    calls = []
    cert = types.SimpleNamespace(id=1, crt='c', prv='k', descr='d')
    fake_q = types.SimpleNamespace(filter_by=lambda **k: types.SimpleNamespace(first=lambda: cert))
    monkeypatch.setattr(models, 'Certificate', types.SimpleNamespace(query=fake_q))
    monkeypatch.setattr(hb, 'get_bound_refid', lambda: 'r1')
    monkeypatch.setattr(hb, 'materialize_https_cert', lambda c: calls.append('materialize'))
    monkeypatch.setattr(sm, 'restart_service', lambda: calls.append('restart'))
    monkeypatch.setattr(AuditService, 'log_action', staticmethod(lambda **k: None))
    return hb, calls


def test_bound_cert_renewal_followed_in_ha_by_a_rolling_restart(app, monkeypatch):
    """Every node writes the renewed pair from the database as it restarts."""
    hb, calls = _stub_bound_renewal(monkeypatch)
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.setattr('config.settings.is_docker', lambda: True)
    with app.app_context():
        hb.on_certificate_renewed('certificate.renewed', {'certificate': {'refid': 'r1'}}, None, {})
        from models import SystemConfig, db
        SystemConfig.query.filter_by(key=hb.CHAIN_KEY).delete()
        db.session.commit()
    assert calls == ['materialize', 'restart']


def test_bound_cert_renewal_materialized_without_ha(monkeypatch):
    hb, calls = _stub_bound_renewal(monkeypatch)
    monkeypatch.setattr(Config, 'HA_MODE', False)
    hb.on_certificate_renewed('certificate.renewed', {'certificate': {'refid': 'r1'}}, None, {})
    assert 'materialize' in calls


def test_https_unbind_allowed_in_ha(auth_client, monkeypatch):
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.setattr('services.https_binding.get_bound_refid', lambda: '')
    r = auth_client.post('/api/v2/system/https/unbind', json={})
    assert r.status_code == 400, r.data
    assert (r.get_json() or {}).get('code') != 'ha_mode'


@pytest.fixture
def https_files(app, monkeypatch, tmp_path):
    """HTTPS files of the test's own; the binding, stored pair and commands are dropped after."""
    monkeypatch.setenv('HTTPS_CERT_PATH', str(tmp_path / 'https_cert.pem'))
    monkeypatch.setenv('HTTPS_KEY_PATH', str(tmp_path / 'https_key.pem'))
    monkeypatch.setattr(Config, 'HA_MODE', True)
    yield tmp_path
    from models import ClusterCommand, db
    from services import shared_files
    from services.https_binding import set_bound_refid
    with app.app_context():
        shared_files.drop_file(shared_files.HTTPS_GENERATED)
        set_bound_refid('')
        ClusterCommand.query.delete()
        db.session.commit()


def test_https_apply_in_ha_stores_what_every_node_serves(app, auth_client, https_files, create_cert):
    from models import ClusterCommand, SystemConfig
    from services.https_binding import CHAIN_KEY, get_bound_refid
    cert = create_cert(cn='ha-apply.example.test')
    r = auth_client.post('/api/v2/system/https/apply', json={'cert_id': cert['id']})
    assert r.status_code == 200, r.data
    with app.app_context():
        assert get_bound_refid() == cert['refid']
        chain = SystemConfig.query.filter_by(key=CHAIN_KEY).one().value
        assert chain == (https_files / 'https_cert.pem').read_text()
        assert [c.kind for c in ClusterCommand.query.all()] == ['restart']


def test_https_regenerate_in_ha_stores_the_pair_for_every_node(app, auth_client, https_files):
    import json
    from models import ClusterCommand
    from services import shared_files
    from services.https_binding import get_bound_refid
    r = auth_client.post('/api/v2/system/https/regenerate', json={'common_name': 'ucm-ha.test'})
    assert r.status_code == 200, r.data
    with app.app_context():
        pair = json.loads(shared_files.read_file(shared_files.HTTPS_GENERATED))
        assert pair == {'crt': (https_files / 'https_cert.pem').read_text(),
                        'key': (https_files / 'https_key.pem').read_text()}
        assert get_bound_refid() == ''
        assert [c.kind for c in ClusterCommand.query.all()] == ['restart']
