"""Tests for trusted-proxy detection and its interplay with ProxyFix.

Regression coverage for the ProxyFix/trusted-proxy conflict: when
UCM_BEHIND_PROXY=1, Werkzeug's ProxyFix rewrites REMOTE_ADDR from the
(client-controlled) X-Forwarded-For header and preserves the real TCP peer
in environ['werkzeug.proxy_fix.orig']. Trust decisions must key on the
original peer — both so that a configured reverse proxy still passes the
check, and so that a direct attacker cannot impersonate a trusted proxy by
sending `X-Forwarded-For: 127.0.0.1`.
"""

from __future__ import annotations

import pytest
from werkzeug.middleware.proxy_fix import ProxyFix

from models import SystemConfig
from utils.trusted_proxy import (
    client_ip,
    immediate_peer_addr,
    is_request_from_trusted_proxy,
    reject_untrusted_proxy_headers,
)

NGINX_IP = '192.0.2.1'
CLIENT_IP = '10.0.0.1'
ATTACKER_IP = '203.0.113.9'


def _proxyfix_orig(peer):
    """Environ key Werkzeug's ProxyFix sets after rewriting REMOTE_ADDR."""
    return {'werkzeug.proxy_fix.orig': {'REMOTE_ADDR': peer}}


def _set_config(app, key, value):
    with app.app_context():
        from models import db
        row = SystemConfig.query.filter_by(key=key).first()
        if row:
            row.value = value
        else:
            db.session.add(SystemConfig(key=key, value=value))
        db.session.commit()


class TestImmediatePeerAddr:
    def test_without_proxyfix_returns_remote_addr(self, app):
        with app.test_request_context('/', environ_overrides={'REMOTE_ADDR': CLIENT_IP}):
            assert immediate_peer_addr() == CLIENT_IP

    def test_with_proxyfix_returns_original_peer(self, app):
        overrides = {'REMOTE_ADDR': CLIENT_IP, **_proxyfix_orig(NGINX_IP)}
        with app.test_request_context('/', environ_overrides=overrides):
            assert immediate_peer_addr() == NGINX_IP


class TestIsRequestFromTrustedProxy:
    def test_direct_trusted_peer(self, app, monkeypatch):
        monkeypatch.setenv('UCM_TRUSTED_PROXIES', NGINX_IP)
        with app.test_request_context('/', environ_overrides={'REMOTE_ADDR': NGINX_IP}):
            assert is_request_from_trusted_proxy() is True

    def test_trusted_proxy_still_trusted_when_proxyfix_rewrites_remote_addr(self, app, monkeypatch):
        """The reported bug: ProxyFix turned the peer into the client IP and
        every request from the configured proxy failed the trust check."""
        monkeypatch.setenv('UCM_TRUSTED_PROXIES', NGINX_IP)
        overrides = {'REMOTE_ADDR': CLIENT_IP, **_proxyfix_orig(NGINX_IP)}
        with app.test_request_context('/', environ_overrides=overrides):
            assert is_request_from_trusted_proxy() is True

    def test_spoofed_xff_cannot_impersonate_trusted_peer(self, app, monkeypatch):
        """Reverse direction: with ProxyFix active a direct attacker could
        send X-Forwarded-For: 127.0.0.1 and pass the default loopback trust,
        unlocking SSL_CLIENT_*/X-SSL-Client-* header handling."""
        monkeypatch.delenv('UCM_TRUSTED_PROXIES', raising=False)  # default: loopback
        overrides = {'REMOTE_ADDR': '127.0.0.1', **_proxyfix_orig(ATTACKER_IP)}
        with app.test_request_context('/', environ_overrides=overrides):
            assert is_request_from_trusted_proxy() is False

    def test_untrusted_peer_rejected(self, app, monkeypatch):
        monkeypatch.setenv('UCM_TRUSTED_PROXIES', NGINX_IP)
        with app.test_request_context('/', environ_overrides={'REMOTE_ADDR': ATTACKER_IP}):
            assert is_request_from_trusted_proxy() is False

    def test_wildcard_trusts_everyone(self, app, monkeypatch):
        monkeypatch.setenv('UCM_TRUSTED_PROXIES', '*')
        with app.test_request_context('/', environ_overrides={'REMOTE_ADDR': ATTACKER_IP}):
            assert is_request_from_trusted_proxy() is True


class TestClientIp:
    def test_proxyfix_result_is_used_as_is(self, app, monkeypatch):
        """ProxyFix already resolved REMOTE_ADDR hop-aware; client_ip must not
        re-parse XFF (whose left-most entries are client-supplied)."""
        monkeypatch.setenv('UCM_TRUSTED_PROXIES', NGINX_IP)
        overrides = {'REMOTE_ADDR': CLIENT_IP, **_proxyfix_orig(NGINX_IP)}
        headers = {'X-Forwarded-For': f'1.1.1.1, {CLIENT_IP}'}
        with app.test_request_context('/', headers=headers, environ_overrides=overrides):
            assert client_ip() == CLIENT_IP

    def test_trusted_peer_without_proxyfix_uses_leftmost_xff(self, app, monkeypatch):
        monkeypatch.setenv('UCM_TRUSTED_PROXIES', NGINX_IP)
        headers = {'X-Forwarded-For': f'{CLIENT_IP}, 10.9.9.9'}
        with app.test_request_context('/', headers=headers, environ_overrides={'REMOTE_ADDR': NGINX_IP}):
            assert client_ip() == CLIENT_IP

    def test_untrusted_peer_xff_ignored(self, app, monkeypatch):
        monkeypatch.setenv('UCM_TRUSTED_PROXIES', NGINX_IP)
        headers = {'X-Forwarded-For': CLIENT_IP}
        with app.test_request_context('/', headers=headers, environ_overrides={'REMOTE_ADDR': ATTACKER_IP}):
            assert client_ip() == ATTACKER_IP

    def test_proxyfix_without_xff_still_honors_x_real_ip(self, app, monkeypatch):
        """ProxyFix ran but found no XFF to apply (REMOTE_ADDR untouched):
        the legacy X-Real-IP fallback for trusted peers must keep working."""
        monkeypatch.setenv('UCM_TRUSTED_PROXIES', NGINX_IP)
        overrides = {'REMOTE_ADDR': NGINX_IP, **_proxyfix_orig(NGINX_IP)}
        headers = {'X-Real-IP': CLIENT_IP}
        with app.test_request_context('/', headers=headers, environ_overrides=overrides):
            assert client_ip() == CLIENT_IP


class TestRejectUntrustedProxyHeaders:
    def test_trusted_peer_headers_accepted(self, app, monkeypatch):
        monkeypatch.setenv('UCM_TRUSTED_PROXIES', NGINX_IP)
        headers = {'X-SSL-Client-Verify': 'SUCCESS'}
        with app.test_request_context('/', headers=headers, environ_overrides={'REMOTE_ADDR': NGINX_IP}):
            assert reject_untrusted_proxy_headers('X-SSL-Client-Verify') is False

    def test_untrusted_peer_headers_rejected(self, app, monkeypatch):
        monkeypatch.setenv('UCM_TRUSTED_PROXIES', NGINX_IP)
        headers = {'X-SSL-Client-Verify': 'SUCCESS'}
        with app.test_request_context('/', headers=headers, environ_overrides={'REMOTE_ADDR': ATTACKER_IP}):
            assert reject_untrusted_proxy_headers('X-SSL-Client-Verify') is True


class TestMtlsMiddlewareProxyGate:
    """middleware.mtls_middleware._extract_certificate must honor proxy cert
    headers from a trusted proxy even when ProxyFix rewrote REMOTE_ADDR, and
    ignore them when the real peer is untrusted."""

    def _extract(self, app, monkeypatch, environ_overrides):
        from middleware.mtls_middleware import _extract_certificate
        monkeypatch.setattr(
            'services.certificate_parser.CertificateParser.extract_from_nginx_headers',
            staticmethod(lambda headers: {'cn': 'sentinel'}),
        )
        headers = {'X-SSL-Client-Verify': 'SUCCESS'}
        with app.test_request_context('/', headers=headers, environ_overrides=environ_overrides):
            return _extract_certificate()

    def test_headers_honored_from_trusted_proxy_with_proxyfix(self, app, monkeypatch):
        monkeypatch.setenv('UCM_TRUSTED_PROXIES', NGINX_IP)
        overrides = {'REMOTE_ADDR': CLIENT_IP, **_proxyfix_orig(NGINX_IP)}
        assert self._extract(app, monkeypatch, overrides) == {'cn': 'sentinel'}

    def test_headers_ignored_for_spoofed_xff_peer(self, app, monkeypatch):
        monkeypatch.delenv('UCM_TRUSTED_PROXIES', raising=False)  # default: loopback
        overrides = {'REMOTE_ADDR': '127.0.0.1', **_proxyfix_orig(ATTACKER_IP)}
        assert self._extract(app, monkeypatch, overrides) is None


@pytest.fixture
def proxyfix_app(app, monkeypatch):
    """Session app temporarily wrapped in a real ProxyFix middleware, with
    the public-host middleware seeing TRUSTED_PROXY_HOPS=1 — reproducing the
    reported deployment (UCM_BEHIND_PROXY=1 behind nginx)."""
    monkeypatch.setenv('UCM_TRUSTED_PROXIES', NGINX_IP)
    _set_config(app, 'base_url', 'https://admin.ucm.example.com:8443')
    app.config['TRUSTED_PROXY_HOPS'] = 1
    original_wsgi = app.wsgi_app
    app.wsgi_app = ProxyFix(original_wsgi, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    try:
        yield app
    finally:
        app.wsgi_app = original_wsgi
        app.config['TRUSTED_PROXY_HOPS'] = 0
        with app.app_context():
            from models import db
            SystemConfig.query.filter_by(key='base_url').delete()
            db.session.commit()


class TestProxyFixMiddlewareIntegration:
    def test_trusted_nginx_forwarded_admin_request_not_blocked(self, proxyfix_app):
        """Reported symptom: UCM_BEHIND_PROXY=1 + UCM_TRUSTED_PROXIES made
        every nginx-proxied Web UI request fail with 403."""
        client = proxyfix_app.test_client()
        resp = client.get(
            '/',
            headers={
                'Host': 'admin.ucm.example.com:8443',
                'X-Forwarded-Host': 'admin.ucm.example.com',
                'X-Forwarded-For': CLIENT_IP,
            },
            environ_overrides={'REMOTE_ADDR': NGINX_IP},
        )
        assert resp.status_code != 403
        assert resp.status_code in (200, 302)

    def test_direct_client_spoofing_x_forwarded_host_blocked(self, proxyfix_app):
        """A direct (non-proxy) client sending X-Forwarded-Host is still a
        spoof attempt and must stay blocked."""
        client = proxyfix_app.test_client()
        resp = client.get(
            '/',
            headers={
                'Host': 'admin.ucm.example.com:8443',
                'X-Forwarded-Host': 'admin.ucm.example.com',
                'X-Forwarded-For': CLIENT_IP,
            },
            environ_overrides={'REMOTE_ADDR': ATTACKER_IP},
        )
        assert resp.status_code == 403

    def test_spoofed_xff_loopback_does_not_bypass_spoof_check(self, proxyfix_app, monkeypatch):
        """Pre-fix, X-Forwarded-For: 127.0.0.1 from a direct attacker passed
        the default loopback trust after ProxyFix rewrote REMOTE_ADDR."""
        monkeypatch.delenv('UCM_TRUSTED_PROXIES', raising=False)  # default: loopback
        client = proxyfix_app.test_client()
        resp = client.get(
            '/',
            headers={
                'Host': 'admin.ucm.example.com:8443',
                'X-Forwarded-Host': 'admin.ucm.example.com',
                'X-Forwarded-For': '127.0.0.1',
            },
            environ_overrides={'REMOTE_ADDR': ATTACKER_IP},
        )
        assert resp.status_code == 403
