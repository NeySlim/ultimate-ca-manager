"""Unit tests for security.rate_limiter LAN trust + standard tier defaults.

Issue: v2.154 rate limiter rejected legitimate UI traffic from LAN clients
(300 rpm / 50 burst on standard tier, and only `127.0.0.1,::1` whitelist).
v2.155 fix: RFC1918 / loopback / link-local auto-bypass when
RATE_LIMIT_TRUST_LAN is true (default), and bumped standard defaults.
"""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def fresh_rl(monkeypatch):
    """Reload security.rate_limiter with a clean class state and given env."""
    def _factory(env: dict | None = None):
        for k in (
            "RATE_LIMIT_TRUST_LAN",
            "RATE_LIMIT_WHITELIST",
            "RATE_LIMIT_STANDARD_RPM",
            "RATE_LIMIT_STANDARD_BURST",
            "RATE_LIMIT_ENABLED",
        ):
            monkeypatch.delenv(k, raising=False)
        for k, v in (env or {}).items():
            monkeypatch.setenv(k, v)
        import security.rate_limiter as mod
        importlib.reload(mod)
        # Reset class-level cached state
        mod.RateLimitConfig._limits_loaded = False
        mod.RateLimitConfig._enabled = None
        mod.RateLimitConfig._whitelist = set()
        mod.RateLimitConfig._custom_limits = {}
        return mod
    return _factory


class TestLanTrust:
    def test_rfc1918_bypassed_by_default(self, fresh_rl):
        mod = fresh_rl()
        for ip in ("192.168.1.42", "10.0.0.7", "172.16.5.5"):
            assert mod.RateLimitConfig.is_whitelisted(ip), f"{ip} should bypass"

    def test_loopback_bypassed(self, fresh_rl):
        mod = fresh_rl()
        assert mod.RateLimitConfig.is_whitelisted("127.0.0.1")
        assert mod.RateLimitConfig.is_whitelisted("::1")

    def test_link_local_bypassed(self, fresh_rl):
        mod = fresh_rl()
        assert mod.RateLimitConfig.is_whitelisted("169.254.1.1")

    def test_public_ip_not_bypassed(self, fresh_rl):
        mod = fresh_rl()
        assert not mod.RateLimitConfig.is_whitelisted("8.8.8.8")
        assert not mod.RateLimitConfig.is_whitelisted("1.1.1.1")

    def test_lan_trust_can_be_disabled(self, fresh_rl):
        mod = fresh_rl({"RATE_LIMIT_TRUST_LAN": "false"})
        # Loopback still in explicit whitelist (default RATE_LIMIT_WHITELIST)
        assert mod.RateLimitConfig.is_whitelisted("127.0.0.1")
        # But RFC1918 no longer auto-bypassed
        assert not mod.RateLimitConfig.is_whitelisted("192.168.1.42")
        assert not mod.RateLimitConfig.is_whitelisted("10.0.0.7")

    def test_malformed_ip_not_bypassed(self, fresh_rl):
        mod = fresh_rl()
        assert not mod.RateLimitConfig.is_whitelisted("not-an-ip")
        assert not mod.RateLimitConfig.is_whitelisted("")


class TestStandardDefaults:
    def test_standard_tier_defaults_bumped(self, fresh_rl):
        mod = fresh_rl()
        limits = mod.RateLimitConfig.get_default_limits()
        default = limits["_default"]
        # v2.155 bumped from 300/50 to 600/100
        assert default["rpm"] >= 600, f"standard rpm too low: {default}"
        assert default["burst"] >= 100, f"standard burst too low: {default}"

    def test_env_override_still_works(self, fresh_rl):
        mod = fresh_rl({
            "RATE_LIMIT_STANDARD_RPM": "1000",
            "RATE_LIMIT_STANDARD_BURST": "200",
        })
        limits = mod.RateLimitConfig.get_default_limits()
        assert limits["_default"]["rpm"] == 1000
        assert limits["_default"]["burst"] == 200


class TestCheckRateLimitWithLan:
    def test_lan_client_never_rate_limited(self, fresh_rl):
        mod = fresh_rl()
        limiter = mod.RateLimiter()
        # Hammer the limiter from a LAN IP — must never block
        for _ in range(2000):
            allowed, info = limiter.check_rate_limit("192.168.1.10", "/api/v2/certificates")
            assert allowed, info
        assert info.get("whitelisted") is True
