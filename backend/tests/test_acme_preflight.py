"""Tests for ACME preflight / dry-run — issue #162."""
import json

from tests.conftest import get_json

CONTENT_JSON = 'application/json'


def post_json(client, url, data):
    return client.post(url, data=json.dumps(data), content_type=CONTENT_JSON)


class TestAcmePreflightAuth:
    def test_preflight_requires_auth(self, client):
        r = post_json(client, '/api/v2/acme/client/preflight', {
            'domains': ['example.com'],
            'email': 'a@example.com',
        })
        assert r.status_code == 401


class TestAcmePreflightValidateOnly:
    def test_validate_only_reports_domain_step(self, auth_client, monkeypatch):
        from services.acme.acme_preflight_service import AcmePreflightService

        def fake_run(**kwargs):
            return {
                'ok': True,
                'mode': kwargs.get('mode', 'validate_only'),
                'staging_environment': 'staging',
                'steps': [
                    {'name': 'domains', 'label': 'Domain validation', 'status': 'pass', 'detail': 'OK', 'data': {}},
                ],
                'txt_records': [],
            }

        monkeypatch.setattr(AcmePreflightService, 'run', staticmethod(lambda **kw: fake_run(**kw)))

        r = post_json(auth_client, '/api/v2/acme/client/preflight', {
            'domains': ['preflight.example.com'],
            'email': 'admin@example.com',
            'challenge_type': 'http-01',
            'mode': 'validate_only',
        })
        assert r.status_code == 200
        body = get_json(r)
        assert body['data']['ok'] is True
        assert any(s['name'] == 'domains' for s in body['data']['steps'])

    def test_preflight_invalid_mode(self, auth_client):
        r = post_json(auth_client, '/api/v2/acme/client/preflight', {
            'domains': ['example.com'],
            'email': 'admin@example.com',
            'mode': 'invalid',
        })
        assert r.status_code == 400


class TestAcmePreflightServiceUnit:
    def test_domain_validation_fails_on_bad_syntax(self, app):
        from services.acme.acme_preflight_service import AcmePreflightService

        with app.app_context():
            report = AcmePreflightService.run(
                domains=['not a domain!!!'],
                email='admin@example.com',
                mode='validate_only',
            )
        assert report['ok'] is False
        dom_step = next(s for s in report['steps'] if s['name'] == 'domains')
        assert dom_step['status'] == 'fail'
