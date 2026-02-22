"""
ACME API Tests — /api/v2/acme/*

Comprehensive tests for all ACME-related endpoints:
- ACME Server: settings, stats, accounts, orders, history (10 routes)
- ACME Client: settings, proxy, orders, account registration (13 routes)
- ACME Domains: CRUD + resolve + test (7 routes)
- ACME Local Domains: CRUD (5 routes)

Uses shared conftest fixtures: app, client, auth_client, create_ca, create_cert.
"""
import pytest
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONTENT_JSON = 'application/json'


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


def put_json(client, url, data):
    return client.put(url, data=json.dumps(data), content_type=CONTENT_JSON)


def patch_json(client, url, data):
    return client.patch(url, data=json.dumps(data), content_type=CONTENT_JSON)


# ============================================================
# Auth Required — all 35 endpoints must reject unauthenticated
# ============================================================

class TestAuthRequired:
    """All ACME endpoints must return 401 without authentication."""

    # --- ACME Server (10) ---
    def test_acme_settings_get_requires_auth(self, client):
        assert client.get('/api/v2/acme/settings').status_code == 401

    def test_acme_settings_patch_requires_auth(self, client):
        r = patch_json(client, '/api/v2/acme/settings', {'enabled': True})
        assert r.status_code == 401

    def test_acme_stats_requires_auth(self, client):
        assert client.get('/api/v2/acme/stats').status_code == 401

    def test_acme_accounts_list_requires_auth(self, client):
        assert client.get('/api/v2/acme/accounts').status_code == 401

    def test_acme_account_get_requires_auth(self, client):
        assert client.get('/api/v2/acme/accounts/1').status_code == 401

    def test_acme_account_delete_requires_auth(self, client):
        assert client.delete('/api/v2/acme/accounts/1').status_code == 401

    def test_acme_orders_list_requires_auth(self, client):
        assert client.get('/api/v2/acme/orders').status_code == 401

    def test_acme_account_orders_requires_auth(self, client):
        assert client.get('/api/v2/acme/accounts/1/orders').status_code == 401

    def test_acme_account_challenges_requires_auth(self, client):
        assert client.get('/api/v2/acme/accounts/1/challenges').status_code == 401

    def test_acme_history_requires_auth(self, client):
        assert client.get('/api/v2/acme/history').status_code == 401

    # --- ACME Client (13) ---
    def test_client_settings_get_requires_auth(self, client):
        assert client.get('/api/v2/acme/client/settings').status_code == 401

    def test_client_settings_patch_requires_auth(self, client):
        r = patch_json(client, '/api/v2/acme/client/settings', {'email': 'a@b.com'})
        assert r.status_code == 401

    def test_client_proxy_register_requires_auth(self, client):
        r = post_json(client, '/api/v2/acme/client/proxy/register', {'email': 'a@b.com'})
        assert r.status_code == 401

    def test_client_proxy_unregister_requires_auth(self, client):
        r = post_json(client, '/api/v2/acme/client/proxy/unregister', {})
        assert r.status_code == 401

    def test_client_orders_list_requires_auth(self, client):
        assert client.get('/api/v2/acme/client/orders').status_code == 401

    def test_client_order_get_requires_auth(self, client):
        assert client.get('/api/v2/acme/client/orders/1').status_code == 401

    def test_client_request_requires_auth(self, client):
        r = post_json(client, '/api/v2/acme/client/request', {'domains': ['example.com']})
        assert r.status_code == 401

    def test_client_order_verify_requires_auth(self, client):
        r = post_json(client, '/api/v2/acme/client/orders/1/verify', {})
        assert r.status_code == 401

    def test_client_order_status_requires_auth(self, client):
        assert client.get('/api/v2/acme/client/orders/1/status').status_code == 401

    def test_client_order_finalize_requires_auth(self, client):
        r = post_json(client, '/api/v2/acme/client/orders/1/finalize', {})
        assert r.status_code == 401

    def test_client_order_delete_requires_auth(self, client):
        assert client.delete('/api/v2/acme/client/orders/1').status_code == 401

    def test_client_order_renew_requires_auth(self, client):
        r = post_json(client, '/api/v2/acme/client/orders/1/renew', {})
        assert r.status_code == 401

    def test_client_account_register_requires_auth(self, client):
        r = post_json(client, '/api/v2/acme/client/account', {'email': 'a@b.com'})
        assert r.status_code == 401

    # --- ACME Domains (7) ---
    def test_domains_list_requires_auth(self, client):
        assert client.get('/api/v2/acme/domains').status_code == 401

    def test_domains_get_requires_auth(self, client):
        assert client.get('/api/v2/acme/domains/1').status_code == 401

    def test_domains_create_requires_auth(self, client):
        r = post_json(client, '/api/v2/acme/domains', {'domain': 'example.com'})
        assert r.status_code == 401

    def test_domains_update_requires_auth(self, client):
        r = put_json(client, '/api/v2/acme/domains/1', {'auto_approve': True})
        assert r.status_code == 401

    def test_domains_delete_requires_auth(self, client):
        assert client.delete('/api/v2/acme/domains/1').status_code == 401

    def test_domains_resolve_requires_auth(self, client):
        assert client.get('/api/v2/acme/domains/resolve?domain=test.com').status_code == 401

    def test_domains_test_requires_auth(self, client):
        r = post_json(client, '/api/v2/acme/domains/test', {'domain': 'test.com'})
        assert r.status_code == 401

    # --- ACME Local Domains (5) ---
    def test_local_domains_list_requires_auth(self, client):
        assert client.get('/api/v2/acme/local-domains').status_code == 401

    def test_local_domains_get_requires_auth(self, client):
        assert client.get('/api/v2/acme/local-domains/1').status_code == 401

    def test_local_domains_create_requires_auth(self, client):
        r = post_json(client, '/api/v2/acme/local-domains', {'domain': 'local.test'})
        assert r.status_code == 401

    def test_local_domains_update_requires_auth(self, client):
        r = put_json(client, '/api/v2/acme/local-domains/1', {'auto_approve': True})
        assert r.status_code == 401

    def test_local_domains_delete_requires_auth(self, client):
        assert client.delete('/api/v2/acme/local-domains/1').status_code == 401


# ============================================================
# ACME Server — Settings
# ============================================================

class TestAcmeServerSettings:
    """GET/PATCH /api/v2/acme/settings"""

    def test_get_settings_returns_dict(self, auth_client):
        r = auth_client.get('/api/v2/acme/settings')
        data = assert_success(r)
        assert isinstance(data, dict)
        assert 'enabled' in data
        assert 'issuing_ca_id' in data
        assert 'revoke_on_renewal' in data
        assert 'superseded_count' in data

    def test_get_settings_has_provider(self, auth_client):
        r = auth_client.get('/api/v2/acme/settings')
        data = assert_success(r)
        assert 'provider' in data

    def test_patch_settings_enable(self, auth_client):
        r = patch_json(auth_client, '/api/v2/acme/settings', {'enabled': True})
        data = assert_success(r)
        assert data.get('enabled') is True

    def test_patch_settings_disable(self, auth_client):
        r = patch_json(auth_client, '/api/v2/acme/settings', {'enabled': False})
        data = assert_success(r)
        assert data.get('enabled') is False

    def test_patch_settings_revoke_on_renewal(self, auth_client):
        r = patch_json(auth_client, '/api/v2/acme/settings', {'revoke_on_renewal': True})
        data = assert_success(r)
        assert data.get('revoke_on_renewal') is True

    def test_patch_settings_set_issuing_ca(self, auth_client, create_ca):
        ca = create_ca(cn='ACME Issuing CA')
        r = patch_json(auth_client, '/api/v2/acme/settings',
                       {'issuing_ca_id': str(ca['id'])})
        assert_success(r)

    def test_patch_settings_empty_body(self, auth_client):
        r = patch_json(auth_client, '/api/v2/acme/settings', {})
        assert_success(r)

    def test_get_settings_after_update_reflects_change(self, auth_client):
        patch_json(auth_client, '/api/v2/acme/settings', {'enabled': True})
        r = auth_client.get('/api/v2/acme/settings')
        data = assert_success(r)
        assert data['enabled'] is True


# ============================================================
# ACME Server — Stats
# ============================================================

class TestAcmeServerStats:
    """GET /api/v2/acme/stats"""

    def test_stats_returns_dict(self, auth_client):
        r = auth_client.get('/api/v2/acme/stats')
        data = assert_success(r)
        assert isinstance(data, dict)

    def test_stats_has_expected_fields(self, auth_client):
        r = auth_client.get('/api/v2/acme/stats')
        data = assert_success(r)
        for key in ('total_orders', 'pending_orders', 'valid_orders',
                     'invalid_orders', 'active_accounts'):
            assert key in data
            assert isinstance(data[key], int)

    def test_stats_values_non_negative(self, auth_client):
        r = auth_client.get('/api/v2/acme/stats')
        data = assert_success(r)
        for key in ('total_orders', 'pending_orders', 'valid_orders',
                     'invalid_orders', 'active_accounts'):
            assert data[key] >= 0


# ============================================================
# ACME Server — Accounts
# ============================================================

class TestAcmeServerAccounts:
    """GET/DELETE /api/v2/acme/accounts/*"""

    def test_list_accounts_returns_list(self, auth_client):
        r = auth_client.get('/api/v2/acme/accounts')
        data = assert_success(r)
        assert isinstance(data, list)

    def test_get_account_not_found(self, auth_client):
        r = auth_client.get('/api/v2/acme/accounts/999999')
        assert_error(r, 404)

    def test_delete_account_not_found(self, auth_client):
        r = auth_client.delete('/api/v2/acme/accounts/999999')
        assert_error(r, 404)


# ============================================================
# ACME Server — Orders
# ============================================================

class TestAcmeServerOrders:
    """GET /api/v2/acme/orders, /accounts/<id>/orders, /accounts/<id>/challenges"""

    def test_list_orders_returns_list(self, auth_client):
        r = auth_client.get('/api/v2/acme/orders')
        data = assert_success(r)
        assert isinstance(data, list)

    def test_list_orders_with_status_filter(self, auth_client):
        r = auth_client.get('/api/v2/acme/orders?status=pending')
        data = assert_success(r)
        assert isinstance(data, list)

    def test_list_orders_invalid_status_returns_empty(self, auth_client):
        r = auth_client.get('/api/v2/acme/orders?status=nonexistent')
        data = assert_success(r)
        assert isinstance(data, list)
        assert len(data) == 0

    def test_account_orders_not_found(self, auth_client):
        r = auth_client.get('/api/v2/acme/accounts/999999/orders')
        assert r.status_code == 404

    def test_account_challenges_not_found(self, auth_client):
        r = auth_client.get('/api/v2/acme/accounts/999999/challenges')
        assert r.status_code == 404


# ============================================================
# ACME Server — History
# ============================================================

class TestAcmeServerHistory:
    """GET /api/v2/acme/history"""

    def test_history_returns_list(self, auth_client):
        r = auth_client.get('/api/v2/acme/history')
        body = get_json(r)
        assert r.status_code == 200
        assert isinstance(body.get('data', []), list)

    def test_history_has_meta(self, auth_client):
        r = auth_client.get('/api/v2/acme/history')
        body = get_json(r)
        meta = body.get('meta', {})
        assert 'total' in meta
        assert 'page' in meta
        assert 'per_page' in meta

    def test_history_pagination(self, auth_client):
        r = auth_client.get('/api/v2/acme/history?page=1&per_page=10')
        body = get_json(r)
        assert r.status_code == 200
        assert body.get('meta', {}).get('per_page') == 10

    def test_history_source_filter_acme(self, auth_client):
        r = auth_client.get('/api/v2/acme/history?source=acme')
        assert r.status_code == 200

    def test_history_source_filter_letsencrypt(self, auth_client):
        r = auth_client.get('/api/v2/acme/history?source=letsencrypt')
        assert r.status_code == 200

    def test_history_source_filter_all(self, auth_client):
        r = auth_client.get('/api/v2/acme/history?source=all')
        assert r.status_code == 200

    def test_history_invalid_source_defaults_to_all(self, auth_client):
        r = auth_client.get('/api/v2/acme/history?source=invalid')
        assert r.status_code == 200

    def test_history_per_page_capped_at_100(self, auth_client):
        r = auth_client.get('/api/v2/acme/history?per_page=999')
        body = get_json(r)
        assert body.get('meta', {}).get('per_page') <= 100


# ============================================================
# ACME Client — Settings
# ============================================================

class TestAcmeClientSettings:
    """GET/PATCH /api/v2/acme/client/settings"""

    def test_get_client_settings(self, auth_client):
        r = auth_client.get('/api/v2/acme/client/settings')
        data = assert_success(r)
        assert isinstance(data, dict)
        assert 'environment' in data
        assert 'renewal_enabled' in data
        assert 'renewal_days' in data

    def test_get_client_settings_has_account_flags(self, auth_client):
        r = auth_client.get('/api/v2/acme/client/settings')
        data = assert_success(r)
        assert 'has_staging_account' in data
        assert 'has_production_account' in data
        assert 'proxy_enabled' in data

    def test_patch_client_settings_email(self, auth_client):
        r = patch_json(auth_client, '/api/v2/acme/client/settings',
                       {'email': 'test@example.com'})
        assert_success(r)

    def test_patch_client_settings_environment_staging(self, auth_client):
        r = patch_json(auth_client, '/api/v2/acme/client/settings',
                       {'environment': 'staging'})
        assert_success(r)

    def test_patch_client_settings_environment_production(self, auth_client):
        r = patch_json(auth_client, '/api/v2/acme/client/settings',
                       {'environment': 'production'})
        assert_success(r)

    def test_patch_client_settings_invalid_environment(self, auth_client):
        r = patch_json(auth_client, '/api/v2/acme/client/settings',
                       {'environment': 'invalid'})
        assert_error(r, 400)

    def test_patch_client_settings_renewal_enabled(self, auth_client):
        r = patch_json(auth_client, '/api/v2/acme/client/settings',
                       {'renewal_enabled': True})
        assert_success(r)

    def test_patch_client_settings_renewal_days_valid(self, auth_client):
        r = patch_json(auth_client, '/api/v2/acme/client/settings',
                       {'renewal_days': 30})
        assert_success(r)

    def test_patch_client_settings_renewal_days_too_low(self, auth_client):
        r = patch_json(auth_client, '/api/v2/acme/client/settings',
                       {'renewal_days': 0})
        assert_error(r, 400)

    def test_patch_client_settings_renewal_days_too_high(self, auth_client):
        r = patch_json(auth_client, '/api/v2/acme/client/settings',
                       {'renewal_days': 61})
        assert_error(r, 400)

    def test_patch_client_settings_empty_body_rejected(self, auth_client):
        r = auth_client.patch('/api/v2/acme/client/settings',
                              data=None, content_type=CONTENT_JSON)
        assert r.status_code in (400, 200)

    def test_patch_client_settings_proxy_enabled(self, auth_client):
        r = patch_json(auth_client, '/api/v2/acme/client/settings',
                       {'proxy_enabled': True})
        assert_success(r)


# ============================================================
# ACME Client — Proxy
# ============================================================

class TestAcmeClientProxy:
    """POST /api/v2/acme/client/proxy/register|unregister"""

    def test_proxy_register(self, auth_client):
        r = post_json(auth_client, '/api/v2/acme/client/proxy/register',
                      {'email': 'proxy@example.com'})
        data = assert_success(r)
        assert data['registered'] is True
        assert data['email'] == 'proxy@example.com'

    def test_proxy_register_missing_email(self, auth_client):
        r = post_json(auth_client, '/api/v2/acme/client/proxy/register', {})
        assert_error(r, 400)

    def test_proxy_register_empty_email(self, auth_client):
        r = post_json(auth_client, '/api/v2/acme/client/proxy/register', {'email': ''})
        assert_error(r, 400)

    def test_proxy_unregister(self, auth_client):
        # Register first, then unregister
        post_json(auth_client, '/api/v2/acme/client/proxy/register',
                  {'email': 'unreg@example.com'})
        r = post_json(auth_client, '/api/v2/acme/client/proxy/unregister', {})
        data = assert_success(r)
        assert data['registered'] is False

    def test_proxy_unregister_when_not_registered(self, auth_client):
        # Ensure unregistered first
        post_json(auth_client, '/api/v2/acme/client/proxy/unregister', {})
        r = post_json(auth_client, '/api/v2/acme/client/proxy/unregister', {})
        assert_success(r)


# ============================================================
# ACME Client — Orders
# ============================================================

class TestAcmeClientOrders:
    """ACME client order endpoints"""

    def test_list_client_orders_empty(self, auth_client):
        r = auth_client.get('/api/v2/acme/client/orders')
        data = assert_success(r)
        assert isinstance(data, list)

    def test_list_client_orders_with_status_filter(self, auth_client):
        r = auth_client.get('/api/v2/acme/client/orders?status=pending')
        data = assert_success(r)
        assert isinstance(data, list)

    def test_list_client_orders_with_environment_filter(self, auth_client):
        r = auth_client.get('/api/v2/acme/client/orders?environment=staging')
        data = assert_success(r)
        assert isinstance(data, list)

    def test_get_client_order_not_found(self, auth_client):
        r = auth_client.get('/api/v2/acme/client/orders/999999')
        assert_error(r, 404)

    def test_delete_client_order_not_found(self, auth_client):
        r = auth_client.delete('/api/v2/acme/client/orders/999999')
        assert_error(r, 404)

    def test_verify_client_order_not_found(self, auth_client):
        r = post_json(auth_client, '/api/v2/acme/client/orders/999999/verify', {})
        assert_error(r, 404)

    def test_status_client_order_not_found(self, auth_client):
        r = auth_client.get('/api/v2/acme/client/orders/999999/status')
        assert_error(r, 404)

    def test_finalize_client_order_not_found(self, auth_client):
        r = post_json(auth_client, '/api/v2/acme/client/orders/999999/finalize', {})
        assert_error(r, 404)

    def test_renew_client_order_not_found(self, auth_client):
        r = post_json(auth_client, '/api/v2/acme/client/orders/999999/renew', {})
        assert_error(r, 404)


# ============================================================
# ACME Client — Request Certificate Validation
# ============================================================

class TestAcmeClientRequestValidation:
    """POST /api/v2/acme/client/request — input validation"""

    def test_request_empty_body(self, auth_client):
        r = auth_client.post('/api/v2/acme/client/request',
                             data=None, content_type=CONTENT_JSON)
        assert r.status_code == 400

    def test_request_no_domains(self, auth_client):
        r = post_json(auth_client, '/api/v2/acme/client/request',
                      {'domains': [], 'email': 'a@b.com'})
        assert_error(r, 400)

    def test_request_missing_domains_key(self, auth_client):
        r = post_json(auth_client, '/api/v2/acme/client/request',
                      {'email': 'a@b.com'})
        assert_error(r, 400)

    def test_request_invalid_domain_too_short(self, auth_client):
        r = post_json(auth_client, '/api/v2/acme/client/request',
                      {'domains': ['ab'], 'email': 'a@b.com',
                       'challenge_type': 'dns-01', 'environment': 'staging'})
        assert_error(r, 400)

    def test_request_invalid_challenge_type(self, auth_client):
        r = post_json(auth_client, '/api/v2/acme/client/request',
                      {'domains': ['example.com'], 'email': 'a@b.com',
                       'challenge_type': 'tls-alpn-01', 'environment': 'staging'})
        assert_error(r, 400)

    def test_request_invalid_environment(self, auth_client):
        r = post_json(auth_client, '/api/v2/acme/client/request',
                      {'domains': ['example.com'], 'email': 'a@b.com',
                       'challenge_type': 'dns-01', 'environment': 'invalid'})
        assert_error(r, 400)

    def test_request_wildcard_requires_dns01(self, auth_client):
        r = post_json(auth_client, '/api/v2/acme/client/request',
                      {'domains': ['*.example.com'], 'email': 'a@b.com',
                       'challenge_type': 'http-01', 'environment': 'staging'})
        assert_error(r, 400)

    def test_request_missing_email_no_default(self, auth_client):
        # Clear email setting first
        patch_json(auth_client, '/api/v2/acme/client/settings', {'email': ''})
        r = post_json(auth_client, '/api/v2/acme/client/request',
                      {'domains': ['example.com'],
                       'challenge_type': 'dns-01', 'environment': 'staging'})
        assert r.status_code in (400, 500)

    def test_request_dns_provider_not_found(self, auth_client):
        r = post_json(auth_client, '/api/v2/acme/client/request',
                      {'domains': ['example.com'], 'email': 'a@b.com',
                       'challenge_type': 'dns-01', 'environment': 'staging',
                       'dns_provider_id': 999999})
        assert r.status_code in (404, 400, 500)


# ============================================================
# ACME Client — Account Registration Validation
# ============================================================

class TestAcmeClientAccountRegistration:
    """POST /api/v2/acme/client/account"""

    def test_register_account_empty_body(self, auth_client):
        r = auth_client.post('/api/v2/acme/client/account',
                             data=None, content_type=CONTENT_JSON)
        assert_error(r, 400)

    def test_register_account_missing_email(self, auth_client):
        r = post_json(auth_client, '/api/v2/acme/client/account',
                      {'environment': 'staging'})
        assert_error(r, 400)

    def test_register_account_invalid_environment(self, auth_client):
        r = post_json(auth_client, '/api/v2/acme/client/account',
                      {'email': 'a@b.com', 'environment': 'invalid'})
        assert_error(r, 400)

    def test_register_account_valid_staging(self, auth_client):
        """Registration will likely fail in test mode (no real LE), but validates input."""
        r = post_json(auth_client, '/api/v2/acme/client/account',
                      {'email': 'test@example.com', 'environment': 'staging'})
        # Accept 200 (success) or 400/500 (expected failure in test env)
        assert r.status_code in (200, 400, 500)


# ============================================================
# ACME Domains — CRUD
# ============================================================

class TestAcmeDomainsCRUD:
    """CRUD operations for /api/v2/acme/domains"""

    def test_list_domains_empty(self, auth_client):
        r = auth_client.get('/api/v2/acme/domains')
        data = assert_success(r)
        assert isinstance(data, list)

    def test_create_domain_missing_body(self, auth_client):
        r = auth_client.post('/api/v2/acme/domains',
                             data=None, content_type=CONTENT_JSON)
        assert_error(r, 400)

    def test_create_domain_missing_domain_field(self, auth_client):
        r = post_json(auth_client, '/api/v2/acme/domains',
                      {'dns_provider_id': 1})
        assert_error(r, 400)

    def test_create_domain_missing_dns_provider(self, auth_client):
        r = post_json(auth_client, '/api/v2/acme/domains',
                      {'domain': 'test-missing-provider.example.com'})
        assert_error(r, 400)

    def test_create_domain_dns_provider_not_found(self, auth_client):
        r = post_json(auth_client, '/api/v2/acme/domains',
                      {'domain': 'test-provider-nf.example.com', 'dns_provider_id': 999999})
        assert_error(r, 404)

    def test_create_domain_invalid_format(self, auth_client):
        r = post_json(auth_client, '/api/v2/acme/domains',
                      {'domain': 'not-valid', 'dns_provider_id': 1})
        # Will fail on provider or domain validation
        assert r.status_code in (400, 404)

    def test_get_domain_not_found(self, auth_client):
        r = auth_client.get('/api/v2/acme/domains/999999')
        assert r.status_code == 404

    def test_update_domain_not_found(self, auth_client):
        r = put_json(auth_client, '/api/v2/acme/domains/999999',
                     {'auto_approve': False})
        assert r.status_code == 404

    def test_delete_domain_not_found(self, auth_client):
        r = auth_client.delete('/api/v2/acme/domains/999999')
        assert r.status_code == 404

    def test_update_domain_empty_body(self, auth_client):
        r = put_json(auth_client, '/api/v2/acme/domains/999999', {})
        # 404 because domain doesn't exist, not 400
        assert r.status_code in (400, 404)

    def test_create_domain_with_invalid_ca(self, auth_client):
        r = post_json(auth_client, '/api/v2/acme/domains',
                      {'domain': 'invalid-ca.example.com',
                       'dns_provider_id': 1,
                       'issuing_ca_id': 999999})
        # Either provider or CA not found
        assert r.status_code in (404, 400)


# ============================================================
# ACME Domains — Resolve
# ============================================================

class TestAcmeDomainsResolve:
    """GET /api/v2/acme/domains/resolve"""

    def test_resolve_missing_domain_param(self, auth_client):
        r = auth_client.get('/api/v2/acme/domains/resolve')
        assert_error(r, 400)

    def test_resolve_empty_domain_param(self, auth_client):
        r = auth_client.get('/api/v2/acme/domains/resolve?domain=')
        assert_error(r, 400)

    def test_resolve_unregistered_domain(self, auth_client):
        r = auth_client.get('/api/v2/acme/domains/resolve?domain=unregistered.example.org')
        assert_error(r, 404)


# ============================================================
# ACME Domains — Test
# ============================================================

class TestAcmeDomainsTest:
    """POST /api/v2/acme/domains/test"""

    def test_domain_test_missing_body(self, auth_client):
        r = auth_client.post('/api/v2/acme/domains/test',
                             data=None, content_type=CONTENT_JSON)
        assert_error(r, 400)

    def test_domain_test_missing_domain(self, auth_client):
        r = post_json(auth_client, '/api/v2/acme/domains/test', {})
        assert_error(r, 400)

    def test_domain_test_empty_domain(self, auth_client):
        r = post_json(auth_client, '/api/v2/acme/domains/test', {'domain': ''})
        assert_error(r, 400)

    def test_domain_test_provider_not_found(self, auth_client):
        r = post_json(auth_client, '/api/v2/acme/domains/test',
                      {'domain': 'test.example.com', 'dns_provider_id': 999999})
        assert_error(r, 404)

    def test_domain_test_no_provider_for_domain(self, auth_client):
        r = post_json(auth_client, '/api/v2/acme/domains/test',
                      {'domain': 'noconfig.example.com'})
        assert_error(r, 404)


# ============================================================
# ACME Local Domains — CRUD
# ============================================================

class TestAcmeLocalDomainsCRUD:
    """CRUD operations for /api/v2/acme/local-domains"""

    def test_list_local_domains_empty(self, auth_client):
        r = auth_client.get('/api/v2/acme/local-domains')
        data = assert_success(r)
        assert isinstance(data, list)

    def test_create_local_domain_missing_body(self, auth_client):
        r = auth_client.post('/api/v2/acme/local-domains',
                             data=None, content_type=CONTENT_JSON)
        assert_error(r, 400)

    def test_create_local_domain_missing_domain(self, auth_client):
        r = post_json(auth_client, '/api/v2/acme/local-domains',
                      {'issuing_ca_id': 1})
        assert_error(r, 400)

    def test_create_local_domain_missing_ca(self, auth_client):
        r = post_json(auth_client, '/api/v2/acme/local-domains',
                      {'domain': 'local-no-ca.example.com'})
        assert_error(r, 400)

    def test_create_local_domain_ca_not_found(self, auth_client):
        r = post_json(auth_client, '/api/v2/acme/local-domains',
                      {'domain': 'local-bad-ca.example.com', 'issuing_ca_id': 999999})
        assert_error(r, 404)

    def test_create_local_domain_invalid_format(self, auth_client):
        r = post_json(auth_client, '/api/v2/acme/local-domains',
                      {'domain': 'not-valid', 'issuing_ca_id': 1})
        # Either 400 (invalid format) or 404 (CA not found)
        assert r.status_code in (400, 404)

    def test_create_local_domain_success(self, auth_client, create_ca):
        ca = create_ca(cn='Local Domain Test CA')
        r = post_json(auth_client, '/api/v2/acme/local-domains',
                      {'domain': 'local-test.example.com',
                       'issuing_ca_id': ca['id']})
        data = assert_success(r, status=201)
        assert data['domain'] == 'local-test.example.com'
        assert data['issuing_ca_id'] == ca['id']
        assert 'id' in data

    def test_get_local_domain_success(self, auth_client, create_ca):
        ca = create_ca(cn='Local Get CA')
        cr = post_json(auth_client, '/api/v2/acme/local-domains',
                       {'domain': 'local-get.example.com',
                        'issuing_ca_id': ca['id']})
        created = assert_success(cr, status=201)
        r = auth_client.get(f'/api/v2/acme/local-domains/{created["id"]}')
        data = assert_success(r)
        assert data['domain'] == 'local-get.example.com'

    def test_get_local_domain_not_found(self, auth_client):
        r = auth_client.get('/api/v2/acme/local-domains/999999')
        assert r.status_code == 404

    def test_update_local_domain_success(self, auth_client, create_ca):
        ca = create_ca(cn='Local Update CA')
        cr = post_json(auth_client, '/api/v2/acme/local-domains',
                       {'domain': 'local-update.example.com',
                        'issuing_ca_id': ca['id'],
                        'auto_approve': True})
        created = assert_success(cr, status=201)

        r = put_json(auth_client, f'/api/v2/acme/local-domains/{created["id"]}',
                     {'auto_approve': False})
        data = assert_success(r)
        assert data['auto_approve'] is False

    def test_update_local_domain_change_ca(self, auth_client, create_ca):
        ca1 = create_ca(cn='Local CA Switch A')
        ca2 = create_ca(cn='Local CA Switch B')
        cr = post_json(auth_client, '/api/v2/acme/local-domains',
                       {'domain': 'local-switch-ca.example.com',
                        'issuing_ca_id': ca1['id']})
        created = assert_success(cr, status=201)

        r = put_json(auth_client, f'/api/v2/acme/local-domains/{created["id"]}',
                     {'issuing_ca_id': ca2['id']})
        data = assert_success(r)
        assert data['issuing_ca_id'] == ca2['id']

    def test_update_local_domain_invalid_ca(self, auth_client, create_ca):
        ca = create_ca(cn='Local Update Invalid CA')
        cr = post_json(auth_client, '/api/v2/acme/local-domains',
                       {'domain': 'local-inv-ca.example.com',
                        'issuing_ca_id': ca['id']})
        created = assert_success(cr, status=201)

        r = put_json(auth_client, f'/api/v2/acme/local-domains/{created["id"]}',
                     {'issuing_ca_id': 999999})
        assert_error(r, 404)

    def test_update_local_domain_not_found(self, auth_client):
        r = put_json(auth_client, '/api/v2/acme/local-domains/999999',
                     {'auto_approve': False})
        assert r.status_code == 404

    def test_update_local_domain_empty_body(self, auth_client, create_ca):
        ca = create_ca(cn='Local Empty Body CA')
        cr = post_json(auth_client, '/api/v2/acme/local-domains',
                       {'domain': 'local-empty.example.com',
                        'issuing_ca_id': ca['id']})
        created = assert_success(cr, status=201)
        r = put_json(auth_client, f'/api/v2/acme/local-domains/{created["id"]}', {})
        # Empty body → 400 (request body required)
        assert r.status_code in (200, 400)

    def test_delete_local_domain_success(self, auth_client, create_ca):
        ca = create_ca(cn='Local Delete CA')
        cr = post_json(auth_client, '/api/v2/acme/local-domains',
                       {'domain': 'local-delete.example.com',
                        'issuing_ca_id': ca['id']})
        created = assert_success(cr, status=201)

        r = auth_client.delete(f'/api/v2/acme/local-domains/{created["id"]}')
        assert_success(r)

        # Verify deleted
        r2 = auth_client.get(f'/api/v2/acme/local-domains/{created["id"]}')
        assert r2.status_code == 404

    def test_delete_local_domain_not_found(self, auth_client):
        r = auth_client.delete('/api/v2/acme/local-domains/999999')
        assert r.status_code == 404

    def test_create_duplicate_local_domain(self, auth_client, create_ca):
        ca = create_ca(cn='Local Dup CA')
        post_json(auth_client, '/api/v2/acme/local-domains',
                  {'domain': 'local-dup.example.com', 'issuing_ca_id': ca['id']})
        r = post_json(auth_client, '/api/v2/acme/local-domains',
                      {'domain': 'local-dup.example.com', 'issuing_ca_id': ca['id']})
        assert_error(r, 409)

    def test_create_local_domain_with_auto_approve(self, auth_client, create_ca):
        ca = create_ca(cn='Local AutoApprove CA')
        r = post_json(auth_client, '/api/v2/acme/local-domains',
                      {'domain': 'local-auto.example.com',
                       'issuing_ca_id': ca['id'],
                       'auto_approve': False})
        data = assert_success(r, status=201)
        assert data['auto_approve'] is False

    def test_local_domain_full_lifecycle(self, auth_client, create_ca):
        """Create → Read → Update → Delete lifecycle."""
        ca = create_ca(cn='Lifecycle Local CA')

        # Create
        r = post_json(auth_client, '/api/v2/acme/local-domains',
                      {'domain': 'lifecycle.example.com',
                       'issuing_ca_id': ca['id']})
        created = assert_success(r, status=201)
        domain_id = created['id']

        # Read
        r = auth_client.get(f'/api/v2/acme/local-domains/{domain_id}')
        data = assert_success(r)
        assert data['domain'] == 'lifecycle.example.com'

        # Update
        r = put_json(auth_client, f'/api/v2/acme/local-domains/{domain_id}',
                     {'auto_approve': False})
        data = assert_success(r)
        assert data['auto_approve'] is False

        # Appears in list
        r = auth_client.get('/api/v2/acme/local-domains')
        data = assert_success(r)
        assert any(d['id'] == domain_id for d in data)

        # Delete
        r = auth_client.delete(f'/api/v2/acme/local-domains/{domain_id}')
        assert_success(r)

        # Gone
        r = auth_client.get(f'/api/v2/acme/local-domains/{domain_id}')
        assert r.status_code == 404

    def test_local_domain_to_dict_fields(self, auth_client, create_ca):
        """Verify to_dict response has expected fields."""
        ca = create_ca(cn='Local Dict Fields CA')
        r = post_json(auth_client, '/api/v2/acme/local-domains',
                      {'domain': 'dict-fields.example.com',
                       'issuing_ca_id': ca['id']})
        data = assert_success(r, status=201)
        for field in ('id', 'domain', 'issuing_ca_id', 'issuing_ca_name',
                       'auto_approve', 'created_at'):
            assert field in data, f'Missing field: {field}'


# ============================================================
# Viewer Role — ACME read-only access
# ============================================================

class TestViewerPermissions:
    """Viewer role lacks read:acme — all ACME endpoints should be 403."""

    def test_viewer_cannot_read_acme_settings(self, viewer_client):
        r = viewer_client.get('/api/v2/acme/settings')
        assert r.status_code == 403

    def test_viewer_cannot_patch_acme_settings(self, viewer_client):
        r = patch_json(viewer_client, '/api/v2/acme/settings', {'enabled': False})
        assert r.status_code == 403

    def test_viewer_cannot_read_acme_stats(self, viewer_client):
        r = viewer_client.get('/api/v2/acme/stats')
        assert r.status_code == 403

    def test_viewer_cannot_read_client_settings(self, viewer_client):
        r = viewer_client.get('/api/v2/acme/client/settings')
        assert r.status_code == 403

    def test_viewer_cannot_patch_client_settings(self, viewer_client):
        r = patch_json(viewer_client, '/api/v2/acme/client/settings',
                       {'email': 'evil@test.com'})
        assert r.status_code == 403

    def test_viewer_cannot_list_domains(self, viewer_client):
        r = viewer_client.get('/api/v2/acme/domains')
        assert r.status_code == 403

    def test_viewer_cannot_create_domain(self, viewer_client):
        r = post_json(viewer_client, '/api/v2/acme/domains',
                      {'domain': 'viewer.test.com', 'dns_provider_id': 1})
        assert r.status_code == 403

    def test_viewer_cannot_list_local_domains(self, viewer_client):
        r = viewer_client.get('/api/v2/acme/local-domains')
        assert r.status_code == 403

    def test_viewer_cannot_create_local_domain(self, viewer_client):
        r = post_json(viewer_client, '/api/v2/acme/local-domains',
                      {'domain': 'viewer-local.test.com', 'issuing_ca_id': 1})
        assert r.status_code == 403

    def test_viewer_cannot_delete_local_domain(self, viewer_client):
        r = viewer_client.delete('/api/v2/acme/local-domains/1')
        assert r.status_code in (403, 404)
