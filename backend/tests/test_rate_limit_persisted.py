"""PUT /system/security/rate-limit is stored on a single node too, and read again at start."""
import json

import pytest

from models import SystemConfig, db
from security.rate_limiter import STORED_KEY, RateLimitConfig

URL = '/api/v2/system/security/rate-limit'


@pytest.fixture
def clean_limits(app):
    saved = (RateLimitConfig._limits_loaded, RateLimitConfig._enabled,
             dict(RateLimitConfig._custom_limits), set(RateLimitConfig._whitelist))
    yield
    (RateLimitConfig._limits_loaded, RateLimitConfig._enabled,
     RateLimitConfig._custom_limits, RateLimitConfig._whitelist) = saved
    with app.app_context():
        SystemConfig.query.filter_by(key=STORED_KEY).delete()
        db.session.commit()


def test_a_change_survives_a_restart_without_ha(app, auth_client, clean_limits):
    r = auth_client.put(URL, data=json.dumps({
        'custom_limits': {'/api/v2/persist-test': {'rpm': 9, 'burst': 3}},
        'whitelist_add': ['192.0.2.55'], 'enabled': False}), content_type='application/json')
    assert r.status_code == 200, r.data
    with app.app_context():
        stored = json.loads(SystemConfig.query.filter_by(key=STORED_KEY).one().value)
    assert stored['custom_limits']['/api/v2/persist-test'] == {'rpm': 9, 'burst': 3}

    # A restart: the class state is empty, the start reads what the API stored
    RateLimitConfig.compose(None)
    assert '/api/v2/persist-test' not in RateLimitConfig.get_config()['custom_limits']
    with app.app_context():
        RateLimitConfig.compose(RateLimitConfig.read_stored())
    config = RateLimitConfig.get_config()
    assert config['custom_limits']['/api/v2/persist-test'] == {'rpm': 9, 'burst': 3}
    assert '192.0.2.55' in config['whitelist']
    assert config['enabled'] is False


def test_the_answer_shows_the_new_state(auth_client, clean_limits):
    r = auth_client.put(URL, data=json.dumps({'whitelist_add': ['192.0.2.56']}),
                        content_type='application/json')
    assert r.status_code == 200, r.data
    assert '192.0.2.56' in r.get_json()['data']['whitelist']


@pytest.mark.parametrize('body, field', [
    ({'enabled': 'false', 'whitelist_add': ['10.9.8.7']}, 'enabled'),
    ({'enabled': 0}, 'enabled'),
    ({'whitelist_add': '10.9.8.7'}, 'whitelist_add'),
    ({'whitelist_add': ['not-an-address']}, 'whitelist_add'),
    ({'whitelist_remove': [7]}, 'whitelist_remove'),
    ({'custom_limits': {'/api/v2/x': {'rpm': 0}}}, 'custom_limits'),
    ({'custom_limits': {'/api/v2/x': {'rpm': True}}}, 'custom_limits'),
    ({'custom_limits': {'/api/v2/x': {'rpm': 5, 'burst': 0}}}, 'custom_limits'),
    ({'custom_limits': {'/api/v2/x': {}}}, 'custom_limits'),
    ({'custom_limits': ['/api/v2/x']}, 'custom_limits'),
])
def test_a_bad_value_is_a_400_naming_the_field_and_stores_nothing(app, auth_client, clean_limits, body, field):
    r = auth_client.put(URL, data=json.dumps(body), content_type='application/json')
    assert r.status_code == 400, r.data
    assert field in r.get_json()['message']
    with app.app_context():
        assert SystemConfig.query.filter_by(key=STORED_KEY).first() is None


def test_a_valid_address_is_stored_in_its_canonical_form(auth_client, clean_limits):
    r = auth_client.put(URL, data=json.dumps({'whitelist_add': ['2001:DB8:0:0:0:0:0:1']}),
                        content_type='application/json')
    assert r.status_code == 200, r.data
    assert '2001:db8::1' in r.get_json()['data']['whitelist']


def test_start_reads_the_stored_settings_again(app, auth_client, clean_limits, monkeypatch):
    import security.rate_limiter as rl
    monkeypatch.setattr(rl, 'init_rate_limiter', lambda _app=None: None)
    r = auth_client.put(URL, data=json.dumps({'whitelist_add': ['192.0.2.57']}),
                        content_type='application/json')
    assert r.status_code == 200, r.data
    rl.RateLimitConfig.compose(None)
    assert '192.0.2.57' not in rl.RateLimitConfig.get_config()['whitelist']
    rl.start_rate_limiting(app)
    assert '192.0.2.57' in rl.RateLimitConfig.get_config()['whitelist']
