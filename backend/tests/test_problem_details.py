"""RFC 7807 Problem Details for API errors.

UCM emits a **superset**: the 7807 members (`type`, `title`, `status`,
`detail`, `instance`) alongside the historical `error`/`message`/`code` keys,
served as `application/problem+json`. Existing clients keep working; new ones
get a conformant document.
"""
import json

import pytest

from utils.response import (
    PROBLEM_CONTENT_TYPE, PROBLEM_TYPE_BLANK, build_problem, error_response,
)

BASE = '/api/v2'


class TestProblemBody:

    def test_contains_both_rfc7807_and_legacy_members(self, app):
        with app.test_request_context('/api/v2/things/42'):
            body = build_problem('Certificate not found', 404)

        # RFC 7807
        assert body['type'] == PROBLEM_TYPE_BLANK
        assert body['title'] == 'Not Found'  # status phrase for about:blank
        assert body['status'] == 404
        assert body['detail'] == 'Certificate not found'
        assert body['instance'] == '/api/v2/things/42'
        # Legacy contract, unchanged
        assert body['error'] is True
        assert body['message'] == 'Certificate not found'
        assert body['code'] == 404

    def test_detail_and_message_carry_the_same_text(self, app):
        with app.test_request_context('/api/v2/x'):
            body = build_problem('Boom', 500)
        assert body['detail'] == body['message'] == 'Boom'

    def test_explicit_type_and_title_are_honoured(self, app):
        with app.test_request_context('/api/v2/x'):
            body = build_problem(
                'Quota exceeded', 429,
                problem_type='https://example.test/problems/quota',
                title='Quota Exceeded',
            )
        assert body['type'] == 'https://example.test/problems/quota'
        assert body['title'] == 'Quota Exceeded'

    def test_details_are_kept_as_extension_member(self, app):
        with app.test_request_context('/api/v2/x'):
            body = build_problem('Invalid input', 400, details={'field': 'name'})
        assert body['details'] == {'field': 'name'}

    def test_works_without_request_context(self, app):
        """No request context → no `instance`, but still a valid document."""
        with app.app_context():
            body = build_problem('Offline failure', 500)
        assert 'instance' not in body
        assert body['status'] == 500


class TestErrorResponseWire:

    def test_content_type_is_problem_json(self, app):
        with app.test_request_context('/api/v2/x'):
            response, code = error_response('Nope', 403)
        assert code == 403
        assert response.mimetype == PROBLEM_CONTENT_TYPE

    def test_real_endpoint_returns_problem_document(self, auth_client):
        """A genuine 404 from the API carries the full superset."""
        r = auth_client.get(f'{BASE}/certificates/99999999')
        assert r.status_code == 404
        assert r.mimetype == PROBLEM_CONTENT_TYPE
        body = json.loads(r.data)
        assert body['status'] == 404
        assert body['type'] == PROBLEM_TYPE_BLANK
        assert body['title'] == 'Not Found'
        assert body['detail']
        # Legacy keys still present for existing clients
        assert body['message'] == body['detail']
        assert body['code'] == 404
        assert body['error'] is True
        assert body['instance'].startswith('/api/v2/certificates/')

    def test_unauthenticated_error_is_also_a_problem_document(self, client):
        r = client.get(f'{BASE}/certificates')
        assert r.status_code in (401, 403)
        body = json.loads(r.data)
        assert body['status'] == r.status_code
        assert body['message']

    def test_framework_level_404_uses_the_same_shape(self, client):
        """Errors raised by Flask itself (unrouted /api path), not a handler."""
        r = client.get(f'{BASE}/definitely-not-a-route-xyz')
        assert r.status_code == 404
        body = json.loads(r.data)
        assert body['status'] == 404
        assert body['detail']
        assert body['message'] == body['detail']
        assert r.mimetype == PROBLEM_CONTENT_TYPE


class TestProtocolErrorsUnaffected:
    """ACME/EST build their own problem documents with registered type URNs —
    they must not be reshaped by the generic API helper."""

    def test_acme_error_keeps_its_urn_type(self, client):
        r = client.post(
            '/acme/new-order',
            data=json.dumps({'protected': 'x', 'payload': 'y', 'signature': 'z'}),
            content_type='application/jose+json',
        )
        body = json.loads(r.data)
        assert body['type'].startswith('urn:ietf:params:acme:error:')
        # ACME documents do not carry UCM's legacy keys
        assert 'code' not in body
