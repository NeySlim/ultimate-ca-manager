"""RATE_LIMIT_ENABLED is read once: the route limits and the tiered limiter agree on every spelling."""
import json
import random

import pytest

from tests.fresh_app import fresh_app

_ON = ['true', '1', 'yes', 'on', 'TrUe', 'YES', None, '']
_OFF = ['false', '0', 'no', 'off', 'OFF']


def _public_addr():
    return f'8.{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}'


def _route_limited(client):
    """The sixth failed login from one address is refused by the 5/minute route limit."""
    addr = _public_addr()
    codes = [client.post('/api/v2/auth/login/password', environ_base={'REMOTE_ADDR': addr},
                         content_type='application/json',
                         data=json.dumps({'username': 'nobody-rle', 'password': 'wrong'})).status_code
             for _ in range(6)]
    assert codes[:5] == [401] * 5, codes
    return codes[5] == 429


def _tier_limited(client):
    """The auth tier gives `/api/v2/auth/register` a burst of 9: the tenth request is refused."""
    addr = _public_addr()
    responses = [client.post('/api/v2/auth/register', environ_base={'REMOTE_ADDR': addr})
                 for _ in range(10)]
    assert all(r.status_code != 429 for r in responses[:9])
    last = responses[9]
    return last.status_code == 429 and 'retry_after' in (last.get_json() or {})


@pytest.fixture
def app_with(monkeypatch):
    from app import limiter
    from security.rate_limiter import RateLimitConfig
    # Both are process state a server builds once: each app here starts from a new process's.
    saved = RateLimitConfig._enabled, limiter.initialized

    def build(value):
        if value is None:
            monkeypatch.delenv('RATE_LIMIT_ENABLED', raising=False)
        else:
            monkeypatch.setenv('RATE_LIMIT_ENABLED', value)
        RateLimitConfig._enabled, limiter.initialized = None, False
        return fresh_app()

    yield build
    RateLimitConfig._enabled, limiter.initialized = saved


@pytest.mark.parametrize('value', _ON + _OFF)
def test_both_limiters_follow_the_variable(app_with, value):
    with app_with(value) as application:
        client = application.test_client()
        route, tier = _route_limited(client), _tier_limited(client)
    expected = value not in _OFF
    assert (route, tier) == (expected, expected)
