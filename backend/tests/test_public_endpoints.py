"""Tests for public endpoint URL helpers and Host-role enforcement."""

from __future__ import annotations

import pytest
from werkzeug.test import EnvironBuilder

from models import SystemConfig
from utils.public_endpoints import (
    build_effective_endpoints,
    check_host_access,
    get_admin_canonical_origin,
    get_admin_public_host,
    get_cors_origins,
    get_protocol_effective_url,
    is_split_acme_topology,
    parse_public_url,
    validate_admin_base_url,
    validate_acme_public_vhost_host,
    validate_protocol_base_url,
)

pytestmark = pytest.mark.usefixtures('clear_public_endpoint_settings')


@pytest.fixture
def clear_public_endpoint_settings(app):
    keys = ('base_url', 'protocol_base_url', 'acme_public_vhost', 'acme_public_port')
    with app.app_context():
        SystemConfig.query.filter(SystemConfig.key.in_(keys)).delete()
        from models import db
        db.session.commit()
    yield
    with app.app_context():
        SystemConfig.query.filter(SystemConfig.key.in_(keys)).delete()
        db.session.commit()


def _set_config(app, key, value):
    with app.app_context():
        from models import db
        row = SystemConfig.query.filter_by(key=key).first()
        if row:
            row.value = value
        else:
            db.session.add(SystemConfig(key=key, value=value))
        db.session.commit()


def _request(app, host='admin.ucm.example.com', path='/'):
    builder = EnvironBuilder(
        path=path,
        base_url=f'https://{host}/',
        headers={'Host': host},
    )
    with app.app_context():
        return builder.get_request()


class TestUrlValidation:
    def test_validate_admin_requires_https(self):
        url, err = validate_admin_base_url('http://admin.ucm.example.com')
        assert url is None
        assert 'https' in err

    def test_validate_admin_accepts_port(self):
        url, err = validate_admin_base_url('https://admin.ucm.example.com:8443')
        assert err is None
        assert url == 'https://admin.ucm.example.com:8443'

    def test_validate_admin_rejects_wildcard(self):
        url, err = validate_admin_base_url('https://*.ucm.example.com')
        assert url is None

    def test_validate_admin_rejects_path(self):
        url, err = validate_admin_base_url('https://admin.ucm.example.com/settings')
        assert url is None

    def test_validate_protocol_requires_http(self):
        url, err = validate_protocol_base_url('https://admin.ucm.example.com')
        assert url is None
        assert 'http' in err

    def test_validate_protocol_accepts_http(self):
        url, err = validate_protocol_base_url('http://admin.ucm.example.com:8080')
        assert err is None
        assert url == 'http://admin.ucm.example.com:8080'

    def test_empty_protocol_allowed(self):
        url, err = validate_protocol_base_url('')
        assert err is None
        assert url == ''

    def test_rejects_cloud_metadata_host(self):
        url, err = validate_admin_base_url('https://metadata.google.internal')
        assert url is None
        assert err

    def test_acme_vhost_rejects_metadata(self):
        assert validate_acme_public_vhost_host('metadata.google.internal') is not None

    def test_loopback_host_allowed_on_save(self):
        from utils.public_endpoints import validate_public_host_ssrf
        assert validate_public_host_ssrf('admin.ucm.example.com') is None


class TestPreflightDiagnostics:
    def test_loopback_resolution_is_warn_not_fail(self, app):
        with app.app_context():
            from utils.public_endpoints import _classify_preflight_dns
            status, detail = _classify_preflight_dns('admin.ucm.example.com', ['127.0.1.1'], None)
            assert status == 'warn'
            assert 'loopback' in detail.lower()

    def test_public_nxdomain_is_fail(self, app):
        with app.app_context():
            from utils.public_endpoints import _classify_preflight_dns
            status, detail = _classify_preflight_dns(
                'admin.ucm.example.com', [], 'NXDOMAIN (public DNS)'
            )
            assert status == 'fail'
            assert 'NXDOMAIN' in detail

    def test_preflight_reports_local_and_public_dns(self, app, monkeypatch):
        with app.app_context():
            from utils.public_endpoints import run_preflight_checks

            monkeypatch.delenv('UCM_CORPORATE_DNS_SERVERS', raising=False)
            monkeypatch.setattr(
                'utils.public_endpoints._get_internal_dns_nameservers',
                lambda: [],
            )

            def fake_local(host):
                return ['127.0.1.1'], None

            def fake_public(host):
                return [], 'NXDOMAIN (public DNS)'

            monkeypatch.setattr(
                'utils.public_endpoints._resolve_host_ips', fake_local
            )
            monkeypatch.setattr(
                'utils.public_endpoints._resolve_host_ips_public', fake_public
            )
            _set_config(app, 'base_url', 'https://admin.ucm.example.com')

            result = run_preflight_checks()
            admin = next(c for c in result['checks'] if c['label'] == 'admin')
            assert admin['dns_local'] == 'warn'
            assert admin['dns_public'] == 'fail'
            assert admin['dns'] == 'warn'
            assert 'local:' in admin['detail']
            assert 'public:' in admin['detail']

    def test_preflight_internal_dns_ok(self, app, monkeypatch):
        with app.app_context():
            from utils.public_endpoints import run_preflight_checks

            monkeypatch.setenv('UCM_CORPORATE_DNS_SERVERS', '172.31.10.190')
            monkeypatch.setattr(
                'utils.public_endpoints._resolve_host_ips',
                lambda host: ([], 'Name or service not known'),
            )
            monkeypatch.setattr(
                'utils.public_endpoints._resolve_host_ips_internal',
                lambda host: (['172.31.10.8'], None),
            )
            monkeypatch.setattr(
                'utils.public_endpoints._resolve_host_ips_public',
                lambda host: ([], 'NXDOMAIN (public DNS)'),
            )
            _set_config(app, 'base_url', 'https://admin.ucm.example.com')

            result = run_preflight_checks()
            admin = next(c for c in result['checks'] if c['label'] == 'admin')
            assert result['internal_dns_configured'] is True
            assert result['corporate_dns_servers'] == ['172.31.10.190']
            assert admin['dns_local'] == 'fail'
            assert admin['dns_internal'] == 'warn'
            assert admin['dns_public'] == 'fail'
            assert admin['dns'] == 'warn'
            assert 'internal:' in admin['detail']

    def test_resolve_via_nameservers_ignores_aaaa_nxdomain(self, app):
        with app.app_context():
            from utils.public_endpoints import _resolve_host_ips_via_nameservers

            class FakeAnswer:
                def __init__(self, ip):
                    self._ip = ip

                def __str__(self):
                    return self._ip

            class FakeResolver:
                def __init__(self):
                    self.nameservers = []

                def resolve(self, host, rtype):
                    import dns.resolver

                    if rtype == 'A':
                        return [FakeAnswer('172.31.10.8')]
                    raise dns.resolver.NXDOMAIN()

            import dns.resolver as dns_resolver_mod

            def fake_resolver(**kwargs):
                return FakeResolver()

            import utils.public_endpoints as pe
            import dns.resolver
            orig = dns.resolver.Resolver
            dns.resolver.Resolver = fake_resolver
            try:
                ips, err = pe._resolve_host_ips_via_nameservers(
                    'admin.ucm.example.com',
                    ['172.31.10.190'],
                    nxdomain_detail='NXDOMAIN (internal DNS)',
                    empty_detail='no internal DNS records',
                )
            finally:
                dns.resolver.Resolver = orig
            assert ips == ['172.31.10.8']
            assert err is None

    def test_preflight_public_dns_ok_with_local_loopback(self, app, monkeypatch):
        with app.app_context():
            from utils.public_endpoints import run_preflight_checks

            monkeypatch.delenv('UCM_CORPORATE_DNS_SERVERS', raising=False)
            monkeypatch.setattr(
                'utils.public_endpoints._get_internal_dns_nameservers',
                lambda: [],
            )
            monkeypatch.setattr(
                'utils.public_endpoints._resolve_host_ips',
                lambda host: (['127.0.0.1'], None),
            )
            monkeypatch.setattr(
                'utils.public_endpoints._resolve_host_ips_public',
                lambda host: (['93.184.216.34'], None),
            )
            _set_config(app, 'base_url', 'https://admin.ucm.example.com')

            result = run_preflight_checks()
            admin = next(c for c in result['checks'] if c['label'] == 'admin')
            assert admin['dns_local'] == 'warn'
            assert admin['dns_public'] == 'ok'
            assert admin['dns'] == 'ok'

    def test_select_preflight_connect_ip_blocks_metadata(self, app):
        with app.app_context():
            from utils.public_endpoints import _select_preflight_connect_ip

            assert _select_preflight_connect_ip(['169.254.169.254']) is None
            assert _select_preflight_connect_ip(['127.0.0.1']) is None
            assert _select_preflight_connect_ip(['172.31.10.8']) == '172.31.10.8'

    def test_preflight_skips_probe_to_metadata_ip(self, app, monkeypatch):
        with app.app_context():
            from utils.public_endpoints import run_preflight_checks

            monkeypatch.setattr(
                'utils.public_endpoints._get_internal_dns_nameservers',
                lambda: [],
            )
            monkeypatch.setattr(
                'utils.public_endpoints._resolve_host_ips',
                lambda host: (['169.254.169.254'], None),
            )
            monkeypatch.setattr(
                'utils.public_endpoints._resolve_host_ips_public',
                lambda host: ([], 'NXDOMAIN (public DNS)'),
            )
            _set_config(app, 'base_url', 'https://admin.ucm.example.com')

            result = run_preflight_checks()
            admin = next(c for c in result['checks'] if c['label'] == 'admin')
            assert admin['dns_local'] == 'fail'
            assert admin['tls'] == 'skip'


class TestMiddlewareRedirect:
    def test_spoofed_localhost_host_from_remote_ip_redirects(self, app, clear_public_endpoint_settings):
        _set_config(app, 'base_url', 'https://admin.ucm.example.com:8443')
        client = app.test_client()
        resp = client.get(
            '/',
            headers={'Host': 'localhost:8443'},
            environ_overrides={'REMOTE_ADDR': '203.0.113.1'},
        )
        assert resp.status_code == 302
        assert 'admin.ucm.example.com' in resp.headers.get('Location', '')

    def test_loopback_peer_with_localhost_host_allowed(self, app, clear_public_endpoint_settings):
        _set_config(app, 'base_url', 'https://admin.ucm.example.com:8443')
        client = app.test_client()
        resp = client.get(
            '/',
            headers={'Host': 'localhost:8443'},
            environ_overrides={'REMOTE_ADDR': '127.0.0.1'},
        )
        assert resp.status_code in (200, 302)  # 200 SPA or redirect if other middleware

    def test_untrusted_x_forwarded_host_blocked_when_proxyfix_enabled(self, app, clear_public_endpoint_settings):
        _set_config(app, 'base_url', 'https://admin.ucm.example.com:8443')
        _set_config(app, 'acme_public_vhost', 'acme.ucm.example.com')
        app.config['TRUSTED_PROXY_HOPS'] = 1
        client = app.test_client()
        resp = client.get(
            '/',
            headers={
                'Host': 'acme.ucm.example.com:8443',
                'X-Forwarded-Host': 'admin.ucm.example.com',
            },
            environ_overrides={'REMOTE_ADDR': '203.0.113.1'},
        )
        assert resp.status_code in (403, 404)
        assert resp.status_code != 200
        app.config['TRUSTED_PROXY_HOPS'] = 0

    def test_private_lan_x_forwarded_host_blocked_when_proxyfix_enabled(
        self, app, monkeypatch, clear_public_endpoint_settings,
    ):
        monkeypatch.delenv('UCM_TRUSTED_PROXIES', raising=False)
        _set_config(app, 'base_url', 'https://admin.ucm.example.com:8443')
        _set_config(app, 'acme_public_vhost', 'acme.ucm.example.com')
        app.config['TRUSTED_PROXY_HOPS'] = 1
        client = app.test_client()
        resp = client.get(
            '/',
            headers={
                'Host': 'acme.ucm.example.com:8443',
                'X-Forwarded-Host': 'admin.ucm.example.com',
            },
            environ_overrides={'REMOTE_ADDR': '172.31.10.50'},
        )
        assert resp.status_code == 403
        app.config['TRUSTED_PROXY_HOPS'] = 0


class TestDeploymentPorts:
    def test_admin_canonical_uses_https_port_env_when_url_omits_port(self, app, monkeypatch):
        monkeypatch.setenv('HTTPS_PORT', '8443')
        _set_config(app, 'base_url', 'https://admin.ucm.example.com')
        with app.app_context():
            assert get_admin_canonical_origin() == 'https://admin.ucm.example.com:8443'

    def test_protocol_effective_uses_http_protocol_port_env(self, app, monkeypatch):
        monkeypatch.setenv('HTTP_PROTOCOL_PORT', '8080')
        _set_config(app, 'protocol_base_url', 'http://pki.ucm.example.com')
        with app.app_context():
            assert get_protocol_effective_url() == 'http://pki.ucm.example.com:8080'

    def test_explicit_port_in_stored_url_is_preserved(self, app, monkeypatch):
        monkeypatch.setenv('HTTPS_PORT', '8443')
        _set_config(app, 'base_url', 'https://admin.ucm.example.com:9443')
        with app.app_context():
            assert get_admin_canonical_origin() == 'https://admin.ucm.example.com:9443'


class TestAdminHostResolution:
    def test_base_url_overrides_env(self, app, monkeypatch):
        monkeypatch.setenv('FQDN', 'legacy.ucm.example.com')
        _set_config(app, 'base_url', 'https://admin.ucm.example.com:8443')
        with app.app_context():
            assert get_admin_public_host() == 'admin.ucm.example.com'

    def test_cors_includes_admin_url(self, app, monkeypatch):
        monkeypatch.setenv('HTTPS_PORT', '8443')
        _set_config(app, 'base_url', 'https://admin.ucm.example.com:8443')
        with app.app_context():
            origins = get_cors_origins()
        assert 'https://admin.ucm.example.com:8443' in origins

    def test_cors_includes_deployment_port_when_base_url_omits_port(self, app, monkeypatch):
        monkeypatch.setenv('HTTPS_PORT', '8443')
        _set_config(app, 'base_url', 'https://admin.ucm.example.com')
        with app.app_context():
            origins = get_cors_origins()
        assert 'https://admin.ucm.example.com:8443' in origins


class TestSplitTopology:
    def test_split_detected(self, app):
        _set_config(app, 'base_url', 'https://admin.ucm.example.com:8443')
        _set_config(app, 'acme_public_vhost', 'acme.ucm.example.com')
        with app.app_context():
            assert is_split_acme_topology() is True

    def test_acme_host_blocks_admin_ui(self, app):
        _set_config(app, 'base_url', 'https://admin.ucm.example.com:8443')
        _set_config(app, 'acme_public_vhost', 'acme.ucm.example.com')
        with app.app_context():
            denied = check_host_access('/', 'acme.ucm.example.com')
        assert denied == (404, 'Admin interface is not available on the ACME public vhost')

    def test_acme_host_allows_directory(self, app):
        _set_config(app, 'base_url', 'https://admin.ucm.example.com:8443')
        _set_config(app, 'acme_public_vhost', 'acme.ucm.example.com')
        with app.app_context():
            assert check_host_access('/acme/directory', 'acme.ucm.example.com') is None

    def test_alias_admin_redirect_not_blocked(self, app):
        _set_config(app, 'base_url', 'https://admin.ucm.example.com:8443')
        with app.app_context():
            assert check_host_access('/', 'legacy.ucm.example.com') is None


class TestEffectiveEndpoints:
    def test_build_effective_split(self, app):
        _set_config(app, 'base_url', 'https://admin.ucm.example.com:8443')
        _set_config(app, 'acme_public_vhost', 'acme.ucm.example.com')
        _set_config(app, 'acme_public_port', '8443')
        with app.app_context():
            req = _request(app)
            data = build_effective_endpoints(req)
        assert data['admin']['host'] == 'admin.ucm.example.com'
        assert data['acme']['vhost'] == 'acme.ucm.example.com'
        assert data['acme']['directory_url'] == 'https://acme.ucm.example.com:8443/acme'
        assert data['acme']['split_topology'] is True


class TestPatchValidation:
    def test_patch_rejects_invalid_base_url(self, auth_client, clear_public_endpoint_settings):
        resp = auth_client.patch(
            '/api/v2/settings/general',
            json={'base_url': 'not-a-url'},
        )
        assert resp.status_code == 400

    def test_patch_accepts_valid_base_url(self, auth_client, clear_public_endpoint_settings):
        resp = auth_client.patch(
            '/api/v2/settings/general',
            json={'base_url': 'https://admin.ucm.example.com:8443'},
        )
        assert resp.status_code == 200

    def test_public_endpoints_get(self, auth_client, clear_public_endpoint_settings):
        auth_client.patch(
            '/api/v2/settings/general',
            json={
                'base_url': 'https://admin.ucm.example.com:8443',
                'acme_public_vhost': 'acme.ucm.example.com',
            },
        )
        resp = auth_client.get('/api/v2/settings/public-endpoints')
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['data']['admin']['host'] == 'admin.ucm.example.com'

    def test_patch_rejects_metadata_host(self, auth_client, clear_public_endpoint_settings):
        resp = auth_client.patch(
            '/api/v2/settings/general',
            json={'base_url': 'https://metadata.google.internal'},
        )
        assert resp.status_code == 400

    def test_preflight_requires_write_settings(self, auth_client, viewer_client, clear_public_endpoint_settings):
        auth_client.patch(
            '/api/v2/settings/general',
            json={'base_url': 'https://admin.ucm.example.com:8443'},
        )
        ok = auth_client.post('/api/v2/settings/public-endpoints/preflight', json={})
        assert ok.status_code == 200
        denied = viewer_client.post('/api/v2/settings/public-endpoints/preflight', json={})
        assert denied.status_code == 403
