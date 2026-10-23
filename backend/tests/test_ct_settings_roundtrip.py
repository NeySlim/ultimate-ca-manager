"""The CT settings page saves back what GET gave it, built-in logs included."""
import pytest

from models import db, SystemConfig

KEYS = ('ct_enabled', 'ct_log_urls', 'ct_auto_submit', 'ct_embed_sct', 'ct_required')


@pytest.fixture
def no_ct_config(app):
    def wipe():
        with app.app_context():
            SystemConfig.query.filter(SystemConfig.key.in_(KEYS)).delete(synchronize_session=False)
            db.session.commit()
    wipe()
    yield
    wipe()


def _get(auth_client):
    r = auth_client.get('/api/v2/settings/ct')
    assert r.status_code == 200
    return r.get_json()['data']


def test_get_then_patch_the_same_body_saves(auth_client, no_ct_config):
    body = _get(auth_client)
    assert body['log_urls'] is None
    body['enabled'] = True
    r = auth_client.patch('/api/v2/settings/ct', json=body)
    assert r.status_code == 200, r.data
    after = _get(auth_client)
    assert after['enabled'] is True
    assert after['log_urls'] is None  # still the built-in logs


def test_null_returns_a_custom_list_to_the_built_in_logs(app, auth_client, no_ct_config):
    assert auth_client.patch('/api/v2/settings/ct',
                             json={'log_urls': ['https://ct.example.test/']}).status_code == 200
    assert _get(auth_client)['log_urls'] == ['https://ct.example.test/']
    assert auth_client.patch('/api/v2/settings/ct', json={'log_urls': None}).status_code == 200
    assert _get(auth_client)['log_urls'] is None


def test_other_types_are_refused(auth_client, no_ct_config):
    assert auth_client.patch('/api/v2/settings/ct', json={'log_urls': 'x'}).status_code == 400


@pytest.mark.parametrize('urls', [
    ['http://169.254.169.254/'],
    ['http://127.0.0.1:8080/'],
    ['ftp://ct.example.test/'],
    [42],
])
def test_a_log_url_the_submission_would_refuse_is_refused_at_save(app, auth_client, no_ct_config, urls):
    r = auth_client.patch('/api/v2/settings/ct', json={'enabled': True, 'log_urls': urls})
    assert r.status_code == 400, r.data
    body = _get(auth_client)
    assert body['log_urls'] is None and body['enabled'] is False, 'a refused body wrote part of itself'
