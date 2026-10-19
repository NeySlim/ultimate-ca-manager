"""The DEB ucm.env offers the rate-limit variables UCM reads.

It offered SESSION_TIMEOUT and RATE_LIMIT_PER_MINUTE/PER_HOUR, which nothing
applied, and none of the RATE_LIMIT_*_RPM/_BURST the limiter reads.
"""
import pathlib
import re

import pytest

from security.rate_limiter import RateLimitConfig

POSTINST = pathlib.Path(__file__).resolve().parents[2] / 'packaging' / 'debian' / 'postinst'


def _offered():
    body = re.search(r"<<\s*'?ENVEOF'?\n(.*?)\nENVEOF", POSTINST.read_text(), re.S).group(1)
    return dict(re.findall(r'^#?\s*([A-Z][A-Z0-9_]+)=(\S*)', body, re.M))


def test_dead_variables_are_not_offered():
    assert not {'SESSION_TIMEOUT', 'RATE_LIMIT_PER_MINUTE', 'RATE_LIMIT_PER_HOUR'} & set(_offered())


@pytest.mark.parametrize('name, path, field', [
    ('RATE_LIMIT_AUTH_RPM', '/api/v2/auth/login', 'rpm'),
    ('RATE_LIMIT_AUTH_BURST', '/api/v2/auth/login', 'burst'),
    ('RATE_LIMIT_HEAVY_RPM', '/api/v2/cas', 'rpm'),
    ('RATE_LIMIT_HEAVY_BURST', '/api/v2/cas', 'burst'),
])
def test_each_offered_limit_reaches_the_limiter(monkeypatch, name, path, field):
    offered = _offered()
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
