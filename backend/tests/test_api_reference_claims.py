"""Claims in docs/API_REFERENCE.md checked against the application."""
import contextlib
import json
import random

from tests.fresh_app import fresh_app

_EST = '/.well-known/est/cacerts'
_XCEP = '/ADPolicyProvider_CEP_Kerberos/service.svc'


@contextlib.contextmanager
def _setting(app, key, value):
    from models import SystemConfig, db
    with app.app_context():
        row = SystemConfig.query.filter_by(key=key).first()
        before = row.value if row else None
        if row is None:
            row = SystemConfig(key=key)
            db.session.add(row)
        row.value = value
        db.session.commit()
    try:
        yield
    finally:
        with app.app_context():
            row = SystemConfig.query.filter_by(key=key).first()
            if before is None:
                db.session.delete(row)
            else:
                row.value = before
            db.session.commit()


def test_a_protocol_turned_off_answers_503(app):
    c = app.test_client()
    with _setting(app, 'est_enabled', 'false'), _setting(app, 'xcep_enabled', 'false'):
        # The switch's own refusal: an unconfigured EST or Kerberos binding also gives 503.
        for path, body in ((_EST, 'EST disabled'), (_XCEP, 'XCEP disabled')):
            r = c.get(path)
            assert (r.status_code, r.get_data(as_text=True)) == (503, body), path
    with _setting(app, 'est_enabled', 'true'), _setting(app, 'xcep_enabled', 'true'):
        assert c.get(_EST).get_data(as_text=True) != 'EST disabled'
        assert c.get(_XCEP).get_data(as_text=True) != 'XCEP disabled'


def test_rate_limit_enabled_false_lets_six_failed_logins_through(monkeypatch):
    from app import limiter
    from security.rate_limiter import RateLimitConfig
    saved = RateLimitConfig._enabled, limiter.initialized
    monkeypatch.setenv('RATE_LIMIT_ENABLED', 'false')
    # Process state a server builds once: the app starts from a new process's.
    RateLimitConfig._enabled, limiter.initialized = None, False
    try:
        with fresh_app() as application:
            c, addr = application.test_client(), _public_addr()
            codes = [c.post('/api/v2/auth/login/password', environ_base={'REMOTE_ADDR': addr},
                            content_type='application/json',
                            data=json.dumps({'username': 'nobody-off', 'password': 'wrong'})).status_code
                     for _ in range(6)]
    finally:
        RateLimitConfig._enabled, limiter.initialized = saved
    assert codes == [401] * 6


def test_mtls_list_routes_accept_api_keys(auth_client, app):
    r = auth_client.post('/api/v2/account/apikeys',
                         data=json.dumps({'password': 'changeme123', 'name': 'mtls-doc',
                                          'permissions': ['read:certificates']}),
                         content_type='application/json')
    key = r.get_json()['data']['key']
    c = app.test_client()
    for path in ('/api/v2/mtls/certificates', '/api/v2/mtls/available-certificates'):
        assert c.get(path, headers={'X-API-Key': key}).status_code == 200, path
        assert c.get(path, headers={'X-API-Key': key[:-4] + 'zzzz'}).status_code == 401, path


def _public_addr():
    return f'8.{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}'


_RATE_HEADERS = ('Retry-After', 'X-RateLimit-Limit', 'X-RateLimit-Remaining')


def test_a_tiered_limiter_429_carries_the_rate_headers(app):
    # The auth tier gives /api/v2/auth/register a burst of 9; no route limit applies there.
    c, addr = app.test_client(), _public_addr()
    last = [c.post('/api/v2/auth/register', environ_base={'REMOTE_ADDR': addr})
            for _ in range(10)][-1]
    assert last.status_code == 429 and 'retry_after' in last.get_json()
    for name in _RATE_HEADERS:
        assert last.headers.get(name), name
    assert last.headers['X-RateLimit-Remaining'] == '0'


def test_a_route_limit_429_carries_the_rate_headers_and_reset(app):
    c, addr = app.test_client(), _public_addr()
    last = [c.post('/api/v2/auth/login/password', environ_base={'REMOTE_ADDR': addr},
                   content_type='application/json',
                   data=json.dumps({'username': 'nobody-hdr', 'password': 'wrong'}))
            for _ in range(6)][-1]
    assert last.status_code == 429 and 'retry_after' not in last.get_json()
    for name in _RATE_HEADERS + ('X-RateLimit-Reset',):
        assert last.headers.get(name), name
