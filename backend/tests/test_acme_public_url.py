"""Tests for public ACME endpoint URLs (configured vhost) and JWS URL rules.

Reference topology (example.com — no production hostnames):

- Admin GUI base URL: ``admin.ucm.example.com``
- ACME public vhost: ``acme.ucm.example.com``

See ``docs/testing/ACME-PUBLIC-VHOST.md`` for the full test plan.
"""

from __future__ import annotations

import base64
import json

import pytest
from werkzeug.test import EnvironBuilder

from utils.acme_public_url import (
    get_acme_expected_urls,
    get_acme_public_host,
    get_acme_public_origin,
    is_valid_public_vhost,
)

pytestmark = pytest.mark.usefixtures('clear_acme_public_vhost_settings')


def _make_request(app, host='admin.ucm.example.com', scheme='https'):
    builder = EnvironBuilder(
        path='/',
        base_url=f'{scheme}://{host}/',
        headers={'Host': host},
    )
    with app.app_context():
        return builder.get_request()


class TestGetAcmePublicOrigin:
    def test_uses_configured_acme_vhost_and_non_default_port(self, app, set_acme_public_config):
        set_acme_public_config('acme.ucm.example.com', '8443')
        with app.app_context():
            origin = get_acme_public_origin(_make_request(app))
        assert origin == 'https://acme.ucm.example.com:8443'

    def test_omits_port_when_443(self, app, set_acme_public_config):
        set_acme_public_config('acme.ucm.example.com', '443')
        with app.app_context():
            origin = get_acme_public_origin(_make_request(app))
        assert origin == 'https://acme.ucm.example.com'

    def test_falls_back_to_request_host_when_vhost_unset(self, app, set_acme_public_config):
        set_acme_public_config('', '8443')
        with app.app_context():
            origin = get_acme_public_origin(
                _make_request(app, host='admin.ucm.example.com:8443')
            )
        assert origin == 'https://admin.ucm.example.com:8443'

    def test_admin_request_host_does_not_override_configured_acme_vhost(self, app, set_acme_public_config):
        """Directory URLs must advertise the ACME vhost, not the admin Host header."""
        set_acme_public_config('acme.ucm.example.com', '8443')
        with app.app_context():
            origin = get_acme_public_origin(
                _make_request(app, host='admin.ucm.example.com:8443')
            )
        assert origin == 'https://acme.ucm.example.com:8443'

    def test_public_host_strips_port(self, app, set_acme_public_config):
        set_acme_public_config('acme.ucm.example.com', '8443')
        with app.app_context():
            assert get_acme_public_host(_make_request(app)) == 'acme.ucm.example.com'

    def test_public_host_falls_back_to_request_host(self, app, set_acme_public_config):
        set_acme_public_config('', '443')
        with app.app_context():
            host = get_acme_public_host(
                _make_request(app, host='admin.ucm.example.com:8443')
            )
        assert host == 'admin.ucm.example.com'


class TestPublicVhostValidation:
    @pytest.mark.parametrize('host,expected', [
        ('acme.ucm.example.com', True),
        ('acme.example.com', True),
        ('acme.lan', True),
        ('..', False),
        ('a..b', False),
        ('.host', False),
        ('host-', False),
        ('a-.example.com', False),
        ('acme', False),          # single label — not a usable public FQDN
        ('*.example.com', False),
    ])
    def test_is_valid_public_vhost(self, host, expected):
        assert is_valid_public_vhost(host) is expected


class TestAcmeDirectoryPublicUrls:
    """Integration: configured vhost appears in ACME directory URLs."""

    def test_local_directory_uses_configured_public_origin(self, client, app, set_acme_public_config):
        set_acme_public_config('acme.ucm.example.com', '8443')
        r = client.get('/acme/directory')
        assert r.status_code == 200
        data = r.get_json()
        assert data['newOrder'] == (
            'https://acme.ucm.example.com:8443/acme/new-order'
        )

    def test_proxy_directory_uses_configured_public_origin(
        self, client, app, set_acme_public_config, monkeypatch
    ):
        # Hermetic: the proxy directory normally fetches the upstream ACME
        # directory — stub it out so the test does not depend on network
        from services.acme.acme_proxy_service import AcmeProxyService

        def _fake_ensure_directory(self):
            self.directory = {
                'newNonce': 'https://upstream.example/acme/new-nonce',
                'newAccount': 'https://upstream.example/acme/new-acct',
                'newOrder': 'https://upstream.example/acme/new-order',
                'revokeCert': 'https://upstream.example/acme/revoke-cert',
                'keyChange': 'https://upstream.example/acme/key-change',
                'meta': {},
            }

        monkeypatch.setattr(
            AcmeProxyService, '_ensure_directory', _fake_ensure_directory
        )
        set_acme_public_config('acme.ucm.example.com', '8443')
        r = client.get('/acme/proxy/directory')
        assert r.status_code == 200
        data = r.get_json()
        assert data['newOrder'] == (
            'https://acme.ucm.example.com:8443/acme/proxy/new-order'
        )

    def test_caa_identity_follows_configured_vhost(self, client, app, set_acme_public_config):
        set_acme_public_config('acme.ucm.example.com', '8443')
        r = client.get('/acme/directory')
        assert r.status_code == 200
        assert r.get_json()['meta']['caaIdentities'] == ['acme.ucm.example.com']


class TestAcmePublicVhostSettingsApi:
    def test_patch_rejects_wildcard_vhost(self, auth_client):
        r = auth_client.patch(
            '/api/v2/settings/general',
            json={'acme_public_vhost': '*.ucm.example.com'},
        )
        assert r.status_code == 400

    def test_patch_rejects_non_string_vhost(self, auth_client):
        r = auth_client.patch(
            '/api/v2/settings/general',
            json={'acme_public_vhost': 123},
        )
        assert r.status_code == 400

    @pytest.mark.parametrize('bad_host', ['..', '.host', 'host-', 'a-.example.com'])
    def test_patch_rejects_malformed_vhost(self, auth_client, bad_host):
        r = auth_client.patch(
            '/api/v2/settings/general',
            json={'acme_public_vhost': bad_host},
        )
        assert r.status_code == 400

    def test_patch_accepts_concrete_vhost(self, auth_client, clear_acme_public_vhost_settings):
        r = auth_client.patch(
            '/api/v2/settings/general',
            json={'acme_public_vhost': 'acme.ucm.example.com',
                  'acme_public_port': 8443},
        )
        assert r.status_code == 200
        data = auth_client.get('/api/v2/settings/general').get_json()['data']
        assert data['acme_public_vhost'] == 'acme.ucm.example.com'
        assert data['acme_public_port'] == 8443

    def test_get_tolerates_garbage_port_row(self, app, auth_client, clear_acme_public_vhost_settings):
        """Out-of-band writes must not 500 the whole Settings GET."""
        from models import db, SystemConfig
        with app.app_context():
            db.session.add(SystemConfig(key='acme_public_port', value=''))
            db.session.commit()
        r = auth_client.get('/api/v2/settings/general')
        assert r.status_code == 200
        assert r.get_json()['data']['acme_public_port'] == 443


class TestJwsExpectedUrls:
    """RFC 8555 §6.4: the canonical (public-origin) URL and the same path on
    the inbound origin are both accepted — in-flight clients survive an
    acme_public_vhost change on the local server AND the proxy."""

    def test_expected_urls_include_inbound_variant(self, app, set_acme_public_config):
        set_acme_public_config('acme.ucm.example.com', '8443')
        with app.test_request_context(
            'https://admin.ucm.example.com:8443/acme/proxy/new-order',
            method='POST',
        ):
            from flask import request
            urls = get_acme_expected_urls(
                request, 'https://acme.ucm.example.com:8443/acme/proxy/new-order'
            )
        assert urls[0] == 'https://acme.ucm.example.com:8443/acme/proxy/new-order'
        assert 'https://admin.ucm.example.com:8443/acme/proxy/new-order' in urls

    def test_expected_urls_single_when_vhost_unset(self, app, set_acme_public_config):
        set_acme_public_config('', '443')
        with app.test_request_context(
            'https://admin.ucm.example.com:8443/acme/new-order',
            method='POST',
        ):
            from flask import request
            urls = get_acme_expected_urls(
                request, 'https://admin.ucm.example.com:8443/acme/new-order'
            )
        assert urls == ['https://admin.ucm.example.com:8443/acme/new-order']

    @staticmethod
    def _jws_with_url(url):
        protected = base64.urlsafe_b64encode(json.dumps({
            'alg': 'ES256',
            'jwk': {'kty': 'EC'},
            'nonce': 'bogus-nonce',
            'url': url,
        }).encode()).rstrip(b'=').decode()
        return {'protected': protected, 'payload': '', 'signature': ''}

    def test_local_verify_jws_accepts_inbound_signed_url(self, app, set_acme_public_config):
        """A client signing the inbound-host URL passes the URL check on the
        LOCAL server when a vhost is configured (fails later on the nonce —
        proving the URL was accepted, without needing a real signature)."""
        from api.acme.acme_api import verify_jws

        set_acme_public_config('acme.ucm.example.com', '8443')
        with app.test_request_context(
            'https://admin.ucm.example.com:8443/acme/new-order',
            method='POST',
        ):
            jws = self._jws_with_url(
                'https://admin.ucm.example.com:8443/acme/new-order'
            )
            ok, _, _, error = verify_jws(
                jws, 'https://acme.ucm.example.com:8443/acme/new-order'
            )
        assert ok is False
        assert 'URL mismatch' not in error
        assert 'nonce' in error.lower()

    def test_local_verify_jws_rejects_foreign_url(self, app, set_acme_public_config):
        from api.acme.acme_api import verify_jws

        set_acme_public_config('acme.ucm.example.com', '8443')
        with app.test_request_context(
            'https://admin.ucm.example.com:8443/acme/new-order',
            method='POST',
        ):
            jws = self._jws_with_url('https://evil.example.net/acme/new-order')
            ok, _, _, error = verify_jws(
                jws, 'https://acme.ucm.example.com:8443/acme/new-order'
            )
        assert ok is False
        assert 'URL mismatch' in error
