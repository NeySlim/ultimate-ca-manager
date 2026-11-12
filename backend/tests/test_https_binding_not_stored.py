"""Outside HA, an HTTPS apply or regenerate whose binding is not stored restarts nothing.

The next start writes the pair the database names: restarting would serve the previous
certificate again over the one just written.
"""
import pytest


@pytest.fixture
def broken_binding(monkeypatch, tmp_path):
    import api.v2.system.https as route
    from config.settings import Config
    monkeypatch.setenv('HTTPS_CERT_PATH', str(tmp_path / 'https_cert.pem'))
    monkeypatch.setenv('HTTPS_KEY_PATH', str(tmp_path / 'https_key.pem'))
    monkeypatch.setattr(Config, 'HA_MODE', False)

    def fail(*a, **k):
        raise RuntimeError('commit failed')
    monkeypatch.setattr('services.https_binding.set_bound_refid', fail)
    restarts = []
    monkeypatch.setattr(route, 'restart_to_serve', lambda: restarts.append(1) or (True, ''))
    return restarts


def test_apply_without_a_stored_binding_does_not_restart(auth_client, create_cert, broken_binding):
    cert = create_cert(cn='https-unstored.example.test')
    r = auth_client.post('/api/v2/system/https/apply', json={'cert_id': cert['id']})
    assert r.status_code == 500, r.data
    assert broken_binding == []


def test_regenerate_without_a_stored_binding_does_not_restart(auth_client, broken_binding):
    r = auth_client.post('/api/v2/system/https/regenerate', json={'common_name': 'unstored.test'})
    assert r.status_code == 500, r.data
    assert broken_binding == []
