"""
Tests for /api/v2/settings/auto-renewal — generic certificate auto-renewal.
"""
import json
from unittest.mock import patch

CONTENT_JSON = 'application/json'
URL = '/api/v2/settings/auto-renewal'
URL_RUN = '/api/v2/settings/auto-renewal/run'


def _patch(client, data):
    return client.patch(URL, data=json.dumps(data), content_type=CONTENT_JSON)


class TestAuth:
    def test_get_requires_auth(self, client):
        assert client.get(URL).status_code == 401

    def test_patch_requires_auth(self, client):
        assert _patch(client, {'enabled': True}).status_code == 401

    def test_run_requires_auth(self, client):
        assert client.post(URL_RUN).status_code == 401


class TestGet:
    def test_returns_defaults(self, auth_client):
        r = auth_client.get(URL)
        assert r.status_code == 200
        data = r.get_json()['data']
        assert 'enabled' in data
        assert 'days_before_expiry' in data
        assert 'renewal_sources' in data
        assert 'notify_on_renewal' in data
        assert 'notify_on_failure' in data
        assert 'notify_emails' in data
        assert isinstance(data['renewal_sources'], list)
        assert isinstance(data['notify_emails'], list)


class TestPatchValidation:
    def test_days_must_be_int(self, auth_client):
        r = _patch(auth_client, {'days_before_expiry': 'abc'})
        assert r.status_code == 400

    def test_days_out_of_range_low(self, auth_client):
        r = _patch(auth_client, {'days_before_expiry': 0})
        assert r.status_code == 400

    def test_days_out_of_range_high(self, auth_client):
        r = _patch(auth_client, {'days_before_expiry': 9999})
        assert r.status_code == 400

    def test_sources_must_be_list(self, auth_client):
        r = _patch(auth_client, {'renewal_sources': 'scep'})
        assert r.status_code == 400

    def test_emails_must_be_list(self, auth_client):
        r = _patch(auth_client, {'notify_emails': 'a@b.com'})
        assert r.status_code == 400

    def test_invalid_email_rejected(self, auth_client):
        r = _patch(auth_client, {'notify_emails': ['not-an-email']})
        assert r.status_code == 400


class TestPatchPersist:
    def test_happy_path_updates_and_persists(self, auth_client):
        payload = {
            'enabled': True,
            'days_before_expiry': 21,
            'renewal_sources': ['scep', 'acme', 'invalid_source'],
            'notify_on_renewal': False,
            'notify_on_failure': True,
            'notify_emails': ['ops@example.com', '  '],
        }
        r = _patch(auth_client, payload)
        assert r.status_code == 200, r.data
        data = r.get_json()['data']
        assert data['enabled'] is True
        assert data['days_before_expiry'] == 21
        # invalid_source dropped, scep+acme kept
        assert data['renewal_sources'] == ['scep', 'acme']
        assert data['notify_on_renewal'] is False
        assert data['notify_on_failure'] is True
        assert data['notify_emails'] == ['ops@example.com']

        # Re-GET confirms persistence
        r2 = auth_client.get(URL)
        data2 = r2.get_json()['data']
        assert data2['days_before_expiry'] == 21
        assert data2['notify_emails'] == ['ops@example.com']


class TestRunNow:
    def test_run_returns_stats(self, auth_client):
        fake_stats = {'renewed': 2, 'failed': 0, 'skipped': 5, 'errors': []}
        with patch(
            'api.v2.settings.auto_renewal.AutoRenewalService.run_auto_renewal',
            return_value=fake_stats,
        ):
            r = auth_client.post(URL_RUN)
        assert r.status_code == 200, r.data
        assert r.get_json()['data'] == fake_stats

    def test_run_handles_exception(self, auth_client):
        with patch(
            'api.v2.settings.auto_renewal.AutoRenewalService.run_auto_renewal',
            side_effect=RuntimeError('boom'),
        ):
            r = auth_client.post(URL_RUN)
        assert r.status_code == 500
