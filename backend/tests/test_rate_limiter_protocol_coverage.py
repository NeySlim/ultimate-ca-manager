"""Every protocol path has its own bucket, and none of them is the admin API's.

`utils/public_endpoints.PROTOCOL_PREFIXES` is the list of paths that belong to
a PKI client rather than to the interface. The rate limiter carried five of
them; the rest fell through to `_default`, which is one bucket per IP shared
with the whole admin API: a timestamping client and the operator's browser
spent the same quota, and the one that hit the ceiling was whichever went
second.
"""
import os

import pytest

from security.rate_limiter import RateLimitConfig, RateLimiter
from utils.public_endpoints import PROTOCOL_EXACT_PATHS, PROTOCOL_PREFIXES

SAMPLE_PATH = {
    '/cdp/': '/cdp/ca-refid.crl',
    '/ca/': '/ca/ca-refid.crt',
    '/ocsp/': '/ocsp/ca-refid',
    '/scep/': '/scep/profile?operation=GetCACert',
    '/.well-known/': '/.well-known/est/simpleenroll',
    '/tsa/': '/tsa/reply',
    '/ssh/setup/': '/ssh/setup/host',
    '/ssh/krl/': '/ssh/krl/ca-refid',
    '/ssh/enroll/': '/ssh/enroll/ca-refid',
    '/ssh/renew/': '/ssh/renew/host-refid',
    '/ADPolicyProvider_CEP_': '/ADPolicyProvider_CEP_UsernamePassword/service.svc',
    '/ADCertificateService_CES_': '/ADCertificateService_CES_UsernamePassword/service.svc',
}


@pytest.fixture()
def limiter():
    return RateLimiter()


@pytest.fixture()
def stock_limits(monkeypatch):
    """The limits as shipped, with every RATE_LIMIT_* override removed."""
    for name in [key for key in os.environ if key.startswith('RATE_LIMIT_')]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(RateLimitConfig, '_limits_loaded', False)
    monkeypatch.setattr(RateLimitConfig, '_default_limits', {})
    RateLimitConfig._load_limits()
    yield
    RateLimitConfig._limits_loaded = False
    RateLimitConfig._load_limits()


class TestNoProtocolPathFallsThrough:
    @pytest.mark.parametrize('prefix', PROTOCOL_PREFIXES)
    def test_a_prefix_has_its_own_bucket(self, limiter, prefix):
        path = SAMPLE_PATH[prefix]
        assert limiter._get_key('10.0.0.1', path) != '10.0.0.1:_default', prefix

    @pytest.mark.parametrize('path', sorted(PROTOCOL_EXACT_PATHS))
    def test_a_bare_path_has_its_own_bucket(self, limiter, path):
        assert limiter._get_key('10.0.0.1', path) != '10.0.0.1:_default', path

    def test_no_protocol_shares_the_admin_bucket(self, limiter):
        admin = limiter._get_key('10.0.0.1', '/api/v2/certificates')
        for path in list(SAMPLE_PATH.values()) + sorted(PROTOCOL_EXACT_PATHS):
            assert limiter._get_key('10.0.0.1', path) != admin, path


class TestABarePathIsNotAPrefix:
    def test_the_timestamping_settings_page_is_not_the_protocol(self, limiter):
        """`/tsa` is the protocol; `/tsa-config` is the page that configures it."""
        assert limiter._get_key('10.0.0.1', '/tsa-config') == '10.0.0.1:_default'
        assert RateLimitConfig.get_limit('/tsa-config') == \
            RateLimitConfig.get_default_limits()['_default']

    def test_the_protocol_path_itself_has_its_own_bucket(self, limiter):
        """Same rate as the admin API, a bucket of its own: that is the point.
        Sharing the rate is deliberate (classifying must not throttle), so the
        separation shows in the bucket, not in the number."""
        assert limiter._get_key('10.0.0.1', '/tsa') == '10.0.0.1:/tsa'
        assert RateLimitConfig.pattern_for('/tsa') == '/tsa'


class TestTheLimitsStayProtocolSized:
    NEWLY_CLASSIFIED = ['/tsa', '/ca/x.crt', '/ssh/setup/x', '/ssh/krl/x',
                        '/ADPolicyProvider_CEP_UsernamePassword/service.svc',
                        '/ADCertificateService_CES_UsernamePassword/service.svc']

    @pytest.mark.parametrize('path', NEWLY_CLASSIFIED)
    def test_classifying_a_path_never_throttles_it(self, path, stock_limits):
        """These fell in `_default` before: giving them a bucket must not
        take rate away from a machine client at the same time.

        Judged on the shipped defaults, never on this machine's env file: a
        deployment that lowers `RATE_LIMIT_STANDARD_RPM` below the protocol
        rate hid the regression locally while CI, which has no env file at
        all, failed on it.
        """
        assert RateLimitConfig.get_limit(path)['rpm'] >= \
            RateLimitConfig.get_default_limits()['_default']['rpm'], path


class TestTheLimitAndTheBucketAgree:
    """Resolving twice let a request be measured against one limit and
    counted in another."""

    PATHS = ['/tsa', '/tsa-config', '/tsa/reply', '/ocsp', '/ocsp/x',
             '/api/v2/certificates', '/acme/directory', '/nothing/special']

    @pytest.mark.parametrize('path', PATHS)
    def test_they_resolve_to_the_same_pattern(self, limiter, path):
        pattern = RateLimitConfig.pattern_for(path)
        assert limiter._get_key('10.0.0.1', path) == f'10.0.0.1:{pattern}'
        expected = (RateLimitConfig.get_default_limits().get(pattern)
                    or RateLimitConfig.get_default_limits()['_default'])
        assert RateLimitConfig.get_limit(path) == expected, path

    def test_a_custom_limit_moves_the_bucket_with_it(self, limiter):
        """An operator-set limit used to change the ceiling and leave the
        counting in `_default`, so it capped the whole admin API instead."""
        RateLimitConfig._load_limits()
        RateLimitConfig._custom_limits = {'/tsa': {'rpm': 5, 'burst': 2}}
        try:
            assert RateLimitConfig.get_limit('/tsa') == {'rpm': 5, 'burst': 2}
            assert limiter._get_key('10.0.0.1', '/tsa') == '10.0.0.1:/tsa'
            # And the admin page beside it keeps the admin limits.
            assert limiter._get_key('10.0.0.1', '/tsa-config') == '10.0.0.1:_default'
            assert RateLimitConfig.get_limit('/tsa-config') == \
                RateLimitConfig.get_default_limits()['_default']
        finally:
            RateLimitConfig._custom_limits = {}
