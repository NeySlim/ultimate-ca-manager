"""HTTP deploy targets (discussion #428): a certificate pushed to an API in
one request built from a body template, through the same queue as SFTP."""
import base64
import json

import pytest

from tests.conftest import assert_error, assert_success

BASE = '/api/v2/deploy'
_seq = [0]

TEMPLATE = ('{"name": "{{name}}", "cn": "{{cn}}", "cert": {{cert_pem|json}}, '
            '"chain": {{fullchain_pem|json}}, "serial": "{{serial_hex}}"}')
KEY_TEMPLATE = '{"cert": {{cert_pem|json}}, "key": {{key_pem|json}}}'


def _name(prefix='http'):
    _seq[0] += 1
    return f'{prefix}-{_seq[0]}'


def post_json(client, url, payload):
    return client.post(url, data=json.dumps(payload), content_type='application/json')


def patch_json(client, url, payload):
    return client.patch(url, data=json.dumps(payload), content_type='application/json')


def _error_body(response, status):
    assert_error(response, status)
    return json.loads(response.data)


def _target_payload(**overrides):
    payload = {
        'name': _name(), 'kind': 'http', 'url': 'https://fw.example.test/api/trust/cert/add',
        'http_method': 'POST', 'http_headers': 'Authorization: Bearer s3cret\nX-Api-Key: k',
        'body_template': TEMPLATE,
    }
    payload.update(overrides)
    return payload


def _create_target(auth_client, **overrides):
    return assert_success(post_json(auth_client, f'{BASE}/targets', _target_payload(**overrides)), status=201)


def _create_binding(auth_client, target_id, cert_id, **overrides):
    payload = {'target_id': target_id, 'certificate_id': cert_id}
    payload.update(overrides)
    return assert_success(post_json(auth_client, f'{BASE}/bindings', payload), status=201)


class _FakeHTTP:
    """Records what the transport would send and answers what the test says."""

    def __init__(self, monkeypatch):
        import services.deploy.http as http_mod
        self.calls = []
        self.answer = (200, '{"result": "saved"}')
        self.error = None

        def fake_request(target, method, url, headers, body):
            self.calls.append({'target_id': target.id, 'method': method, 'url': url,
                               'headers': dict(headers), 'body': body})
            if self.error:
                raise http_mod.DeployHTTPError(self.error)
            return self.answer

        monkeypatch.setattr(http_mod, '_request', fake_request)


@pytest.fixture()
def fake_http(monkeypatch):
    return _FakeHTTP(monkeypatch)


def _call_for(fake_http, target):
    """The last request sent to *target*: a drain also runs deliveries other tests left pending."""
    return [c for c in fake_http.calls if c['target_id'] == target['id']][-1]


def _drain(app):
    from services.deploy import DeployService
    with app.app_context():
        return DeployService.process_pending_deliveries()


def _delivery(auth_client, binding_id):
    rows = assert_success(auth_client.get(f'{BASE}/deliveries?binding_id={binding_id}'))
    rows = rows['items'] if isinstance(rows, dict) else rows
    return rows[0]


class TestTargets:
    def test_create_exposes_the_request_but_never_the_header_values(self, auth_client):
        data = _create_target(auth_client)
        assert data['kind'] == 'http'
        assert data['http_method'] == 'POST'
        assert data['http_header_names'] == ['Authorization', 'X-Api-Key']
        assert data['allow_private_key'] is False
        assert data['host'] == 'fw.example.test' and data['port'] == 443
        assert 'public_key' not in data and 'host_key_pinned' not in data
        assert 's3cret' not in json.dumps(data)
        listed = assert_success(auth_client.get(f'{BASE}/targets'))
        assert 's3cret' not in json.dumps(listed)
        one = assert_success(auth_client.get(f"{BASE}/targets/{data['id']}"))
        assert 's3cret' not in json.dumps(one)

    def test_headers_are_encrypted_at_rest(self, app, auth_client):
        data = _create_target(auth_client)
        from models import db, DeployTarget
        from security.encryption import encrypt_text
        from services.deploy.http import load_headers
        with app.app_context():
            target = db.session.get(DeployTarget, data['id'])
            if encrypt_text('probe') != 'probe':
                assert 's3cret' not in (target.http_headers or '')
            assert load_headers(target.http_headers) == {'Authorization': 'Bearer s3cret', 'X-Api-Key': 'k'}

    @pytest.mark.parametrize('overrides, fragment', [
        ({'body_template': '{"x": "{{nope}}"}'}, 'Unknown template variable'),
        ({'body_template': '{"x": {{cert_pem|rot13}}}'}, 'Unknown template filter'),
        ({'body_template': KEY_TEMPLATE}, 'send private key'),
        ({'body_template': KEY_TEMPLATE, 'allow_private_key': True,
          'url': 'http://fw.example.test/api'}, 'only be sent over https'),
        ({'body_template': '{"cert": "{{cert_pem}}"}'}, 'valid JSON'),
        ({'body_template': ''}, 'body_template is required'),
        ({'http_method': 'DELETE'}, 'POST, PUT or PATCH'),
        ({'http_headers': 'Host: evil'}, 'set by UCM'),
        ({'http_headers': 'no colon here'}, 'without a colon'),
        ({'url': 'https://{{cn}}.example.test/api'}, 'not in the host'),
        ({'url': 'ftp://fw.example.test/x'}, 'http:// or https://'),
        ({'tls_ca_pem': 'not a certificate'}, 'PEM certificates'),
        ({'allow_private_key': 'yes'}, 'must be a boolean'),
        ({'kind': 'ftp'}, 'ssh or http'),
    ])
    def test_create_validation(self, auth_client, overrides, fragment):
        r = post_json(auth_client, f'{BASE}/targets', _target_payload(**overrides))
        assert fragment in json.dumps(_error_body(r, 400))

    def test_a_raw_pem_is_fine_outside_json(self, auth_client):
        data = _create_target(auth_client, body_template='cert={{cert_pem|urlencode}}',
                              http_headers='Content-Type: application/x-www-form-urlencoded')
        assert data['http_header_names'] == ['Content-Type']

    def test_update_checks_the_whole_target_and_keeps_headers_when_omitted(self, auth_client):
        data = _create_target(auth_client, url='http://fw.example.test/api')
        # The opt-in alone must fail on a plain http URL already stored
        assert_error(patch_json(auth_client, f"{BASE}/targets/{data['id']}", {'allow_private_key': True}), 400)
        # A template naming the key needs the opt-in, even when sent alone
        assert_error(patch_json(auth_client, f"{BASE}/targets/{data['id']}", {'body_template': KEY_TEMPLATE}), 400)
        updated = assert_success(patch_json(auth_client, f"{BASE}/targets/{data['id']}", {
            'url': 'https://fw.example.test/api/v2', 'allow_private_key': True, 'body_template': KEY_TEMPLATE}))
        assert updated['allow_private_key'] is True
        assert updated['http_header_names'] == ['Authorization', 'X-Api-Key']
        cleared = assert_success(patch_json(auth_client, f"{BASE}/targets/{data['id']}", {'http_headers': {}}))
        assert cleared['http_header_names'] == []
        assert_error(patch_json(auth_client, f"{BASE}/targets/{data['id']}", {'kind': 'ssh'}), 400)

    def test_ssh_targets_are_unchanged(self, auth_client):
        data = assert_success(post_json(auth_client, f'{BASE}/targets', {
            'name': _name('ssh'), 'host': 'web.example.test', 'username': 'deploy'}), status=201)
        assert data['kind'] == 'ssh'
        assert data['public_key'].startswith('ssh-')
        assert 'url' not in data

    def test_probe_reports_any_http_answer_and_fails_on_transport(self, auth_client, fake_http):
        data = _create_target(auth_client, url='https://fw.example.test/api/{{cn}}/add')
        fake_http.answer = (405, '')
        result = assert_success(post_json(auth_client, f"{BASE}/targets/{data['id']}/test", {}))
        assert result['status_code'] == 405
        call = fake_http.calls[-1]
        assert call['method'] == 'HEAD' and call['body'] is None
        assert call['headers']['Authorization'] == 'Bearer s3cret'
        assert call['url'] == 'https://fw.example.test/api/sample.example.net/add'
        fake_http.error = 'Request failed: connection refused'
        assert_error(post_json(auth_client, f"{BASE}/targets/{data['id']}/test", {}), 502)


class TestBindings:
    def test_binding_has_no_paths_and_queues_the_first_push(self, auth_client, create_cert):
        target = _create_target(auth_client)
        cert = create_cert()
        binding = _create_binding(auth_client, target['id'], cert['id'])
        assert binding['target_kind'] == 'http'
        assert binding['cert_path'] is None
        listed = assert_success(auth_client.get(f"{BASE}/bindings?certificate_id={cert['id']}"))
        assert listed[0]['last_delivery']['event_type'] == 'initial'

    def test_paths_and_reload_are_refused(self, auth_client, create_cert):
        target = _create_target(auth_client)
        cert = create_cert()
        r = post_json(auth_client, f'{BASE}/bindings', {
            'target_id': target['id'], 'certificate_id': cert['id'], 'cert_path': '/etc/ssl/x.pem'})
        assert 'does not apply' in json.dumps(_error_body(r, 400))
        r = post_json(auth_client, f'{BASE}/bindings', {
            'target_id': target['id'], 'certificate_id': cert['id'], 'reload_command': 'reboot'})
        assert_error(r, 400)
        binding = _create_binding(auth_client, target['id'], cert['id'])
        assert_error(patch_json(auth_client, f"{BASE}/bindings/{binding['id']}", {'key_path': '/k'}), 400)
        updated = assert_success(patch_json(auth_client, f"{BASE}/bindings/{binding['id']}", {'include_root': True}))
        assert updated['include_root'] is True

    def test_key_template_needs_a_key_in_ucm(self, app, auth_client, create_cert, fake_http):
        target = _create_target(auth_client, body_template=KEY_TEMPLATE, allow_private_key=True)
        cert = create_cert()
        from models import db, Certificate
        with app.app_context():
            db.session.get(Certificate, cert['id']).prv = None
            db.session.commit()
        r = post_json(auth_client, f'{BASE}/bindings', {'target_id': target['id'], 'certificate_id': cert['id']})
        assert 'no private key' in json.dumps(_error_body(r, 400))

    def test_crl_bindings_need_an_ssh_target(self, auth_client, create_ca):
        target = _create_target(auth_client)
        ca = create_ca(cn='HTTP CRL CA')
        r = post_json(auth_client, f'{BASE}/crl-bindings', {
            'target_id': target['id'], 'ca_id': ca['id'], 'crl_path': '/var/www/ca.crl'})
        assert 'SSH target' in json.dumps(_error_body(r, 400))


class TestDelivery:
    def test_push_renders_the_request_from_the_certificate(self, app, auth_client, create_cert, fake_http):
        target = _create_target(auth_client, url='https://fw.example.test/api/{{cn}}/add')
        cert = create_cert(cn='push.example.test')
        binding = _create_binding(auth_client, target['id'], cert['id'], include_root=True)
        assert _drain(app)['delivered'] >= 1
        call = _call_for(fake_http, target)
        assert call['method'] == 'POST'
        assert call['url'] == 'https://fw.example.test/api/push.example.test/add'
        assert call['headers']['Authorization'] == 'Bearer s3cret'
        assert call['headers']['Content-Type'] == 'application/json'
        body = json.loads(call['body'])
        assert body['cn'] == 'push.example.test'
        assert body['cert'].startswith('-----BEGIN CERTIFICATE-----')
        assert body['chain'].startswith(body['cert'])
        assert body['chain'].count('BEGIN CERTIFICATE') == 2  # the root, asked for by include_root
        assert b'PRIVATE KEY' not in call['body']
        from models import db, Certificate
        with app.app_context():
            pem = base64.b64decode(db.session.get(Certificate, cert['id']).crt).decode()
        assert body['cert'] == pem.split('-----END CERTIFICATE-----')[0] + '-----END CERTIFICATE-----\n'
        delivery = _delivery(auth_client, binding['id'])
        assert delivery['status'] == 'delivered'
        assert delivery['detail']['status'] == 200
        assert 's3cret' not in json.dumps(delivery)
        refreshed = assert_success(auth_client.get(f"{BASE}/targets/{target['id']}"))
        assert refreshed['last_success_at'] and refreshed['failure_count'] == 0

    def test_private_key_leaves_only_with_the_opt_in(self, app, auth_client, create_cert, fake_http):
        target = _create_target(auth_client, body_template=KEY_TEMPLATE, allow_private_key=True)
        cert = create_cert()
        _create_binding(auth_client, target['id'], cert['id'])
        assert _drain(app)['delivered'] >= 1
        body = json.loads(_call_for(fake_http, target)['body'])
        assert 'PRIVATE KEY' in body['key']

    def test_key_withdrawn_after_binding_is_a_permanent_failure(self, app, auth_client, create_cert, fake_http):
        target = _create_target(auth_client, body_template=KEY_TEMPLATE, allow_private_key=True)
        cert = create_cert()
        binding = _create_binding(auth_client, target['id'], cert['id'])
        from models import db, Certificate
        with app.app_context():
            db.session.get(Certificate, cert['id']).prv = None
            db.session.commit()
        assert _drain(app)['failed'] >= 1
        delivery = _delivery(auth_client, binding['id'])
        assert delivery['status'] == 'failed' and 'key_pem' in delivery['last_error']
        assert not [c for c in fake_http.calls if c['target_id'] == target['id']]

    @pytest.mark.parametrize('answer, fragment', [
        ((500, 'boom'), 'HTTP 500: boom'),
        ((302, ''), 'redirects are not followed'),
        ((401, ''), 'HTTP 401'),
    ])
    def test_non_2xx_is_retried_with_backoff(self, app, auth_client, create_cert, fake_http, answer, fragment):
        target = _create_target(auth_client)
        cert = create_cert()
        binding = _create_binding(auth_client, target['id'], cert['id'])
        fake_http.answer = answer
        assert _drain(app)['retry'] >= 1
        delivery = _delivery(auth_client, binding['id'])
        assert delivery['status'] == 'pending' and fragment in delivery['last_error']
        assert delivery['attempts'] == 1
        refreshed = assert_success(auth_client.get(f"{BASE}/targets/{target['id']}"))
        assert refreshed['failure_count'] == 1

    def test_transport_error_is_retried(self, app, auth_client, create_cert, fake_http):
        target = _create_target(auth_client)
        cert = create_cert()
        binding = _create_binding(auth_client, target['id'], cert['id'])
        fake_http.error = 'Request failed: connection refused'
        assert _drain(app)['retry'] >= 1
        assert 'connection refused' in _delivery(auth_client, binding['id'])['last_error']

    def test_renewal_event_reaches_the_api(self, app, auth_client, create_cert, fake_http):
        target = _create_target(auth_client, body_template='{"event": "{{event}}", "cert": {{cert_pem|json}}}')
        cert = create_cert()
        _create_binding(auth_client, target['id'], cert['id'])
        assert _drain(app)['delivered'] >= 1
        assert json.loads(_call_for(fake_http, target)['body'])['event'] == 'initial'
        assert_success(post_json(auth_client, f"/api/v2/certificates/{cert['id']}/renew", {}))
        _drain(app)
        assert json.loads(_call_for(fake_http, target)['body'])['event'] == 'certificate.renewed'


class TestTransport:
    def test_request_goes_through_the_ssrf_client_without_redirects_and_with_the_pinned_ca(
            self, app, auth_client, create_cert, monkeypatch):
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization
        from models import db, CA
        with app.app_context():
            ca_pem = base64.b64decode(CA.query.first().crt).decode()
        x509.load_pem_x509_certificate(ca_pem.encode())  # the bench CA is a valid PEM
        target = _create_target(auth_client, tls_ca_pem=ca_pem)
        assert target['tls_ca_pem'].strip() == ca_pem.strip()
        cert = create_cert()
        _create_binding(auth_client, target['id'], cert['id'])

        seen = {}
        import utils.ssrf_protection as ssrf

        class _Resp:
            status_code = 201

            def iter_content(self, n):
                yield b'ok'

            def close(self):
                seen['closed'] = True

        def fake_safe_request(method, url, **kwargs):
            seen.update(method=method, url=url, **kwargs)
            with open(kwargs['verify']) as handle:
                seen['verify_pem'] = handle.read()
            return _Resp()

        monkeypatch.setattr(ssrf, 'safe_request', fake_safe_request)
        assert _drain(app)['delivered'] >= 1
        assert seen['method'] == 'POST' and seen['allow_redirects'] is False
        assert seen['verify_pem'].strip() == ca_pem.strip()
        assert seen['closed'] is True
        assert seen['headers']['User-Agent'].startswith('UCM-Deploy/')
        import os
        assert not os.path.exists(seen['verify'])  # the CA file does not outlive the request

    def test_url_rejected_by_ssrf_checks_is_a_transport_error(self, app, auth_client, create_cert, monkeypatch):
        target = _create_target(auth_client, url='https://169.254.169.254/latest/api')
        cert = create_cert()
        binding = _create_binding(auth_client, target['id'], cert['id'])
        assert _drain(app)['retry'] >= 1
        assert 'URL rejected' in _delivery(auth_client, binding['id'])['last_error']


class TestTemplate:
    def test_filters(self):
        from services.deploy.http import render
        variables = {'cert_pem': 'a\nb', 'cn': 'x y&z'}
        assert render('{{cert_pem|json}}', variables) == '"a\\nb"'
        assert render('{{cert_pem|b64}}', variables) == 'YQpi'
        assert render('{{ cn | urlencode }}', variables) == 'x%20y%26z'
        assert render('{{cn}}', variables, default_filter='urlencode') == 'x%20y%26z'
        assert render('{{cn|raw}}', variables, default_filter='urlencode') == 'x y&z'
        with pytest.raises(ValueError, match='not available'):
            render('{{key_pem}}', variables)
