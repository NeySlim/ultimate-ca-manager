"""The DEB ucm.env offers the rate-limit variables UCM reads.

It offered SESSION_TIMEOUT and RATE_LIMIT_PER_MINUTE/PER_HOUR, which nothing
applied, and none of the RATE_LIMIT_*_RPM/_BURST the limiter reads.
"""
import pytest

from security.rate_limiter import RateLimitConfig


@pytest.fixture
def offered(tmp_path):
    from tests.test_no_jwt_secret_generated import written_env
    return written_env('packaging/debian/postinst', tmp_path)


def test_dead_variables_are_not_offered(offered):
    assert not {'SESSION_TIMEOUT', 'RATE_LIMIT_PER_MINUTE', 'RATE_LIMIT_PER_HOUR'} & set(offered)
    assert not [name for name in offered if name.startswith('SCEP_')]


@pytest.mark.parametrize('name, path, field', [
    ('RATE_LIMIT_AUTH_RPM', '/api/v2/auth/login', 'rpm'),
    ('RATE_LIMIT_AUTH_BURST', '/api/v2/auth/login', 'burst'),
    ('RATE_LIMIT_HEAVY_RPM', '/api/v2/cas', 'rpm'),
    ('RATE_LIMIT_HEAVY_BURST', '/api/v2/cas', 'burst'),
])
def test_each_offered_limit_reaches_the_limiter(monkeypatch, offered, name, path, field):
    assert name in offered
    # The value shown is the default the limiter applies without it
    monkeypatch.setattr(RateLimitConfig, '_limits_loaded', False)
    monkeypatch.delenv(name, raising=False)
    RateLimitConfig._load_limits()
    assert RateLimitConfig._default_limits[path][field] == int(offered[name])
    monkeypatch.setattr(RateLimitConfig, '_limits_loaded', False)
    monkeypatch.setenv(name, '7')
    RateLimitConfig._load_limits()
    assert RateLimitConfig._default_limits[path][field] == 7
    monkeypatch.setattr(RateLimitConfig, '_limits_loaded', False)
    monkeypatch.delenv(name)
    RateLimitConfig._load_limits()
