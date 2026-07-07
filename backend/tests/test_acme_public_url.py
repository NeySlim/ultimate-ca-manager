"""Tests for public ACME endpoint URLs and TLS hostname / wildcard SAN rules.

Reference topology (example.com — no production hostnames):

- Admin GUI base URL: ``admin.ucm.example.com``
- ACME proxy vhost: ``acme.ucm.example.com``
- Wildcard ``*.ucm.example.com`` covers both admin and ACME vhosts

See ``docs/testing/ACME-PUBLIC-VHOST.md`` for the full test plan and wildcard guide.
"""

from __future__ import annotations

import pytest
from werkzeug.test import EnvironBuilder

from models import db, SystemConfig
from utils.acme_public_url import get_acme_public_origin


def _make_request(app, host='admin.ucm.example.com', scheme='https'):
    builder = EnvironBuilder(
        path='/',
        base_url=f'{scheme}://{host}/',
        headers={'Host': host},
    )
    with app.app_context():
        return builder.get_request()


def _set_acme_public_config(app, vhost: str = '', port: str = '443'):
    with app.app_context():
        for key, value in (
            ('acme_proxy_vhost', vhost),
            ('acme_proxy_port', port),
        ):
            row = SystemConfig.query.filter_by(key=key).first()
            if not row:
                row = SystemConfig(key=key)
                db.session.add(row)
            row.value = value
        db.session.commit()


def wildcard_san_matches(hostname: str, san: str) -> bool:
    """Return whether *hostname* is valid for TLS server certificate SAN *san*.

    Mirrors CA/Browser Forum baseline requirements for DNS names:
    - ``*.ucm.example.com`` matches one leftmost label only (not the apex).
    - Exact SAN matches only that FQDN.
    """
    hostname = hostname.lower().rstrip('.')
    san = san.lower().rstrip('.')
    if san.startswith('*.'):
        base = san[2:]
        if hostname == base:
            return False
        suffix = f'.{base}'
        if not hostname.endswith(suffix):
            return False
        prefix = hostname[: -len(suffix)]
        return '.' not in prefix
    return hostname == san


def certificate_covers_hostname(hostname: str, sans: list[str]) -> bool:
    return any(wildcard_san_matches(hostname, san) for san in sans)


class TestGetAcmePublicOrigin:
    def test_uses_configured_acme_vhost_and_non_default_port(self, app):
        _set_acme_public_config(app, 'acme.ucm.example.com', '8443')
        with app.app_context():
            origin = get_acme_public_origin(_make_request(app))
        assert origin == 'https://acme.ucm.example.com:8443'

    def test_omits_port_when_443(self, app):
        _set_acme_public_config(app, 'acme.ucm.example.com', '443')
        with app.app_context():
            origin = get_acme_public_origin(_make_request(app))
        assert origin == 'https://acme.ucm.example.com'

    def test_falls_back_to_request_host_when_vhost_unset(self, app):
        _set_acme_public_config(app, '', '8443')
        with app.app_context():
            origin = get_acme_public_origin(
                _make_request(app, host='admin.ucm.example.com:8443')
            )
        assert origin == 'https://admin.ucm.example.com:8443'

    def test_admin_request_host_does_not_override_configured_acme_vhost(self, app):
        """Directory URLs must advertise the ACME vhost, not the admin Host header."""
        _set_acme_public_config(app, 'acme.ucm.example.com', '8443')
        with app.app_context():
            origin = get_acme_public_origin(
                _make_request(app, host='admin.ucm.example.com:8443')
            )
        assert origin == 'https://acme.ucm.example.com:8443'


class TestWildcardSanHostnameCompatibility:
    """Regression table for split admin vs ACME vhost TLS planning."""

    @pytest.mark.parametrize(
        'hostname,san,expected',
        [
            # *.ucm.example.com — typical UCM split (admin + acme)
            ('admin.ucm.example.com', '*.ucm.example.com', True),
            ('acme.ucm.example.com', '*.ucm.example.com', True),
            ('api.ucm.example.com', '*.ucm.example.com', True),
            ('ucm.example.com', '*.ucm.example.com', False),
            # *.example.com does not cover ucm subdomains
            ('admin.ucm.example.com', '*.example.com', False),
            ('acme.ucm.example.com', '*.example.com', False),
            ('acme.example.com', '*.example.com', True),
            # explicit SAN
            ('admin.ucm.example.com', 'admin.ucm.example.com', True),
            ('acme.ucm.example.com', 'acme.ucm.example.com', True),
        ],
    )
    def test_wildcard_san_rules(self, hostname, san, expected):
        assert wildcard_san_matches(hostname, san) is expected

    def test_wildcard_ucm_example_com_covers_admin_and_acme_vhosts(self):
        sans = ['*.ucm.example.com']
        assert certificate_covers_hostname('admin.ucm.example.com', sans) is True
        assert certificate_covers_hostname('acme.ucm.example.com', sans) is True
        assert certificate_covers_hostname('ucm.example.com', sans) is False

    def test_wildcard_example_com_does_not_cover_ucm_subdomains(self):
        sans = ['*.example.com']
        assert certificate_covers_hostname('acme.example.com', sans) is True
        assert certificate_covers_hostname('admin.ucm.example.com', sans) is False
        assert certificate_covers_hostname('acme.ucm.example.com', sans) is False

    def test_explicit_sans_cover_split_vhost_topology(self):
        sans = ['admin.ucm.example.com', 'acme.ucm.example.com']
        assert certificate_covers_hostname('admin.ucm.example.com', sans) is True
        assert certificate_covers_hostname('acme.ucm.example.com', sans) is True


class TestAcmeDirectoryPublicUrls:
    """Integration: configured vhost appears in ACME directory link headers."""

    def test_local_directory_uses_configured_public_origin(self, client, app):
        _set_acme_public_config(app, 'acme.ucm.example.com', '8443')
        r = client.get('/acme/directory')
        assert r.status_code == 200
        data = r.get_json()
        assert data['newOrder'] == (
            'https://acme.ucm.example.com:8443/acme/new-order'
        )

    def test_proxy_directory_uses_configured_public_origin(self, client, app):
        _set_acme_public_config(app, 'acme.ucm.example.com', '8443')
        r = client.get('/acme/proxy/directory')
        assert r.status_code == 200
        data = r.get_json()
        assert data['newOrder'] == (
            'https://acme.ucm.example.com:8443/acme/proxy/new-order'
        )
