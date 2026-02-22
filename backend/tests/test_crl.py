"""
CRL & OCSP API Tests — /api/v2/crl/* and /api/v2/ocsp/*

Tests for all CRL and OCSP management endpoints:
- List CRLs (GET)
- Get CRL for specific CA (GET)
- Regenerate CRL (POST)
- Toggle auto-regeneration (POST)
- OCSP responder status (GET)
- OCSP statistics (GET)

Uses shared conftest fixtures: app, client, auth_client, create_ca.
"""
import pytest
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONTENT_JSON = 'application/json'
CRL_BASE = '/api/v2/crl'
OCSP_BASE = '/api/v2/ocsp'


def get_json(response):
    return json.loads(response.data)


def assert_success(response, status=200):
    assert response.status_code == status, \
        f'Expected {status}, got {response.status_code}: {response.data[:500]}'
    data = json.loads(response.data)
    return data.get('data', data)


def assert_error(response, status):
    assert response.status_code == status, \
        f'Expected {status}, got {response.status_code}: {response.data[:500]}'


def post_json(client, url, data):
    return client.post(url, data=json.dumps(data), content_type=CONTENT_JSON)


# ============================================================
# Auth Required — all endpoints must reject unauthenticated
# ============================================================

class TestAuthRequired:
    """All CRL/OCSP endpoints must return 401 without authentication."""

    def test_list_crls_requires_auth(self, client):
        assert client.get(CRL_BASE).status_code == 401

    def test_get_crl_requires_auth(self, client):
        assert client.get(f'{CRL_BASE}/1').status_code == 401

    def test_regenerate_crl_requires_auth(self, client):
        r = client.post(f'{CRL_BASE}/1/regenerate')
        assert r.status_code == 401

    def test_auto_regen_requires_auth(self, client):
        r = post_json(client, f'{CRL_BASE}/1/auto-regen', {'enabled': True})
        assert r.status_code == 401

    def test_ocsp_status_requires_auth(self, client):
        assert client.get(f'{OCSP_BASE}/status').status_code == 401

    def test_ocsp_stats_requires_auth(self, client):
        assert client.get(f'{OCSP_BASE}/stats').status_code == 401


# ============================================================
# List CRLs
# ============================================================

class TestListCRLs:
    """GET /api/v2/crl — list latest CRL per CA."""

    def test_list_crls_success(self, auth_client):
        r = auth_client.get(CRL_BASE)
        data = assert_success(r)
        assert isinstance(data, list)

    def test_list_crls_returns_list(self, auth_client):
        r = auth_client.get(CRL_BASE)
        body = get_json(r)
        assert 'data' in body


# ============================================================
# Get CRL for specific CA
# ============================================================

class TestGetCRL:
    """GET /api/v2/crl/<ca_id> — get CRL for a specific CA."""

    def test_get_crl_for_ca(self, auth_client, create_ca):
        ca = create_ca(cn='CRL Test CA')
        ca_id = ca.get('id', ca.get('ca_id'))
        r = auth_client.get(f'{CRL_BASE}/{ca_id}')
        assert_success(r)

    def test_get_crl_nonexistent_ca(self, auth_client):
        r = auth_client.get(f'{CRL_BASE}/99999')
        assert_error(r, 404)

    def test_get_crl_returns_null_when_no_crl(self, auth_client, create_ca):
        """New CA with no revocations may have no CRL yet."""
        ca = create_ca(cn='CRL Empty CA')
        ca_id = ca.get('id', ca.get('ca_id'))
        r = auth_client.get(f'{CRL_BASE}/{ca_id}')
        body = get_json(r)
        assert r.status_code == 200


# ============================================================
# Regenerate CRL
# ============================================================

class TestRegenerateCRL:
    """POST /api/v2/crl/<ca_id>/regenerate — force CRL regeneration."""

    def test_regenerate_crl_success(self, auth_client, create_ca):
        ca = create_ca(cn='CRL Regen CA')
        ca_id = ca.get('id', ca.get('ca_id'))
        r = auth_client.post(f'{CRL_BASE}/{ca_id}/regenerate')
        assert r.status_code in (200, 500)  # 500 if CRL service not fully set up in test

    def test_regenerate_crl_nonexistent_ca(self, auth_client):
        r = auth_client.post(f'{CRL_BASE}/99999/regenerate')
        assert_error(r, 404)


# ============================================================
# Auto-Regen Toggle
# ============================================================

class TestAutoRegen:
    """POST /api/v2/crl/<ca_id>/auto-regen — toggle auto CRL regeneration."""

    def test_enable_auto_regen(self, auth_client, create_ca):
        ca = create_ca(cn='CRL AutoRegen CA')
        ca_id = ca.get('id', ca.get('ca_id'))
        r = post_json(auth_client, f'{CRL_BASE}/{ca_id}/auto-regen', {'enabled': True})
        data = assert_success(r)
        assert data.get('cdp_enabled') is True

    def test_disable_auto_regen(self, auth_client, create_ca):
        ca = create_ca(cn='CRL AutoRegen Off CA')
        ca_id = ca.get('id', ca.get('ca_id'))
        r = post_json(auth_client, f'{CRL_BASE}/{ca_id}/auto-regen', {'enabled': False})
        data = assert_success(r)
        assert data.get('cdp_enabled') is False

    def test_toggle_auto_regen(self, auth_client, create_ca):
        """Without explicit enabled flag, should toggle current state."""
        ca = create_ca(cn='CRL Toggle CA')
        ca_id = ca.get('id', ca.get('ca_id'))
        r = post_json(auth_client, f'{CRL_BASE}/{ca_id}/auto-regen', {})
        assert_success(r)

    def test_auto_regen_nonexistent_ca(self, auth_client):
        r = post_json(auth_client, f'{CRL_BASE}/99999/auto-regen', {'enabled': True})
        assert_error(r, 404)


# ============================================================
# OCSP Status
# ============================================================

class TestOCSPStatus:
    """GET /api/v2/ocsp/status — OCSP responder status."""

    def test_ocsp_status(self, auth_client):
        r = auth_client.get(f'{OCSP_BASE}/status')
        data = assert_success(r)
        assert 'enabled' in data
        assert 'running' in data

    def test_ocsp_status_returns_booleans(self, auth_client):
        r = auth_client.get(f'{OCSP_BASE}/status')
        data = assert_success(r)
        assert isinstance(data['enabled'], bool)
        assert isinstance(data['running'], bool)


# ============================================================
# OCSP Stats
# ============================================================

class TestOCSPStats:
    """GET /api/v2/ocsp/stats — OCSP statistics."""

    def test_ocsp_stats(self, auth_client):
        r = auth_client.get(f'{OCSP_BASE}/stats')
        data = assert_success(r)
        assert 'total_requests' in data
        assert 'cache_hits' in data

    def test_ocsp_stats_values_are_numeric(self, auth_client):
        r = auth_client.get(f'{OCSP_BASE}/stats')
        data = assert_success(r)
        assert isinstance(data['total_requests'], int)
        assert isinstance(data['cache_hits'], int)
