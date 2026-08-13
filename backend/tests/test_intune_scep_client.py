"""IntuneScepClient (issue #228 part 2): the wire contract for Microsoft
Intune's SCEP challenge validation API. No Flask/DB needed -- these are pure
unit tests against a mocked `requests` module, verifying this client sends
exactly what Microsoft's own reference implementation sends (see the module
docstring in services/scep/intune_client.py for the source cross-check).
"""
import pytest

from services.scep.intune_client import (
    IntuneScepClient,
    IntuneScepError,
    IntuneScepErrorCode,
)


class _FakeResponse:
    def __init__(self, json_body, status_code=200):
        self._json = json_body
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"{self.status_code} error")

    def json(self):
        return self._json


@pytest.fixture
def client():
    return IntuneScepClient(
        tenant_id='contoso.onmicrosoft.com',
        client_id='client-id-123',
        client_secret='super-secret',
        provider_name='UCM-Test/1.0',
    )


class TestConstruction:

    def test_requires_all_fields(self):
        with pytest.raises(ValueError):
            IntuneScepClient(tenant_id='', client_id='x', client_secret='y')
        with pytest.raises(ValueError):
            IntuneScepClient(tenant_id='t', client_id='', client_secret='y')
        with pytest.raises(ValueError):
            IntuneScepClient(tenant_id='t', client_id='x', client_secret='')

    def test_no_network_at_construction(self, monkeypatch):
        # Constructing must never make an HTTP call -- callers (get_scep_service)
        # construct this on every SCEP request, and network I/O belongs only
        # in the lazy token/discovery/validate paths.
        called = []
        monkeypatch.setattr('requests.post', lambda *a, **k: called.append(1))
        monkeypatch.setattr('requests.get', lambda *a, **k: called.append(1))
        IntuneScepClient(tenant_id='t', client_id='c', client_secret='s')
        assert called == []


class TestTokenAcquisition:

    def test_token_request_shape(self, client, monkeypatch):
        captured = {}

        def fake_post(url, data=None, timeout=None):
            captured['url'] = url
            captured['data'] = data
            return _FakeResponse({'access_token': 'tok-1', 'expires_in': 3600})

        monkeypatch.setattr('requests.post', fake_post)
        token = client._get_token('https://graph.microsoft.com/.default')
        assert token == 'tok-1'
        assert captured['url'] == (
            'https://login.microsoftonline.com/contoso.onmicrosoft.com/oauth2/v2.0/token'
        )
        assert captured['data']['grant_type'] == 'client_credentials'
        assert captured['data']['client_id'] == 'client-id-123'
        assert captured['data']['client_secret'] == 'super-secret'
        assert captured['data']['scope'] == 'https://graph.microsoft.com/.default'

    def test_intune_scope_has_double_slash(self, client, monkeypatch):
        # Deliberate: Microsoft's own reference client builds this scope as
        # DEFAULT_INTUNE_RESOURCE_URL ("https://api.manage.microsoft.com/",
        # already trailing-slashed) + "/.default" -- a literal double slash.
        # Replicated byte-for-byte since AAD scope strings are opaque to us.
        captured = {}

        def fake_post(url, data=None, timeout=None):
            captured['scope'] = data['scope']
            return _FakeResponse({'access_token': 'tok', 'expires_in': 3600})

        monkeypatch.setattr('requests.post', fake_post)
        client._intune_token()
        assert captured['scope'] == 'https://api.manage.microsoft.com//.default'

    def test_token_cached_until_near_expiry(self, client, monkeypatch):
        calls = []

        def fake_post(url, data=None, timeout=None):
            calls.append(1)
            return _FakeResponse({'access_token': f'tok-{len(calls)}', 'expires_in': 3600})

        monkeypatch.setattr('requests.post', fake_post)
        t1 = client._get_token('scope-a')
        t2 = client._get_token('scope-a')
        assert t1 == t2
        assert len(calls) == 1

    def test_missing_access_token_raises(self, client, monkeypatch):
        monkeypatch.setattr('requests.post', lambda *a, **k: _FakeResponse({}))
        with pytest.raises(IntuneScepError):
            client._get_token('scope-a')

    def test_http_error_raises(self, client, monkeypatch):
        monkeypatch.setattr(
            'requests.post', lambda *a, **k: _FakeResponse({}, status_code=401)
        )
        with pytest.raises(IntuneScepError):
            client._get_token('scope-a')


class TestServiceDiscovery:

    def _mock_graph(self, monkeypatch, entries, token='graph-tok'):
        monkeypatch.setattr(
            'requests.post',
            lambda *a, **k: _FakeResponse({'access_token': token, 'expires_in': 3600}),
        )
        captured = {}

        def fake_get(url, headers=None, timeout=None):
            captured['url'] = url
            captured['headers'] = headers
            return _FakeResponse({'value': entries})

        monkeypatch.setattr('requests.get', fake_get)
        return captured

    def test_discovers_by_provider_name_case_insensitive(self, client, monkeypatch):
        captured = self._mock_graph(monkeypatch, [
            {'providerName': 'ScepRequestValidationFEService', 'uri': 'https://fef.example/scep'},
            {'providerName': 'SomeOtherService', 'uri': 'https://fef.example/other'},
        ])
        endpoint = client._get_service_endpoint()
        assert endpoint == 'https://fef.example/scep'
        assert 'appId=0000000a-0000-0000-c000-000000000000' in captured['url']
        assert captured['headers']['Authorization'] == 'Bearer graph-tok'
        assert 'client-request-id' in captured['headers']

    def test_falls_back_to_service_name_field(self, client, monkeypatch):
        self._mock_graph(monkeypatch, [
            {'serviceName': 'ScepRequestValidationFEService', 'uri': 'https://fef.example/scep2'},
        ])
        assert client._get_service_endpoint() == 'https://fef.example/scep2'

    def test_endpoint_cached(self, client, monkeypatch):
        calls = []

        def fake_get(url, headers=None, timeout=None):
            calls.append(1)
            return _FakeResponse({'value': [
                {'providerName': 'ScepRequestValidationFEService', 'uri': 'https://fef.example/scep'}
            ]})

        monkeypatch.setattr(
            'requests.post',
            lambda *a, **k: _FakeResponse({'access_token': 't', 'expires_in': 3600}),
        )
        monkeypatch.setattr('requests.get', fake_get)
        client._get_service_endpoint()
        client._get_service_endpoint()
        assert len(calls) == 1

    def test_service_not_in_map_raises(self, client, monkeypatch):
        self._mock_graph(monkeypatch, [
            {'providerName': 'SomeOtherService', 'uri': 'https://fef.example/other'},
        ])
        with pytest.raises(IntuneScepError):
            client._get_service_endpoint()


class TestValidateRequest:

    def _mock_full_pipeline(self, monkeypatch, validate_response):
        def fake_post(url, data=None, json=None, headers=None, timeout=None):
            # Token requests pass data=; the actual ScepActions/* call passes
            # json= -- that's what distinguishes the two mocked legs here.
            if data is not None:
                return _FakeResponse({'access_token': 't', 'expires_in': 3600})
            return _FakeResponse(validate_response)

        monkeypatch.setattr('requests.post', fake_post)
        monkeypatch.setattr(
            'requests.get',
            lambda *a, **k: _FakeResponse({'value': [
                {'providerName': 'ScepRequestValidationFEService', 'uri': 'https://fef.example/scep'}
            ]}),
        )

    def test_success_does_not_raise(self, client, monkeypatch):
        self._mock_full_pipeline(monkeypatch, {'code': 'Success', 'errorDescription': ''})
        client.validate_request('txn-1', b'der-csr-bytes')

    def test_rejection_raises_with_parsed_code(self, client, monkeypatch):
        self._mock_full_pipeline(
            monkeypatch,
            {'code': 'ChallengeExpired', 'errorDescription': 'too old'},
        )
        with pytest.raises(IntuneScepError) as exc_info:
            client.validate_request('txn-1', b'der-csr-bytes')
        assert exc_info.value.code == IntuneScepErrorCode.CHALLENGE_EXPIRED
        assert exc_info.value.description == 'too old'

    def test_unrecognized_code_parses_as_unknown(self, client, monkeypatch):
        self._mock_full_pipeline(
            monkeypatch, {'code': 'SomeNewCodeNotInOurEnum', 'errorDescription': 'x'}
        )
        with pytest.raises(IntuneScepError) as exc_info:
            client.validate_request('txn-1', b'der-csr-bytes')
        assert exc_info.value.code == IntuneScepErrorCode.UNKNOWN

    def test_request_body_shape(self, client, monkeypatch):
        captured = {}

        def fake_post(url, data=None, json=None, headers=None, timeout=None):
            if 'oauth2' in url:
                return _FakeResponse({'access_token': 't', 'expires_in': 3600})
            captured['url'] = url
            captured['json'] = json
            captured['headers'] = headers
            return _FakeResponse({'code': 'Success', 'errorDescription': ''})

        monkeypatch.setattr('requests.post', fake_post)
        monkeypatch.setattr(
            'requests.get',
            lambda *a, **k: _FakeResponse({'value': [
                {'providerName': 'ScepRequestValidationFEService', 'uri': 'https://fef.example/scep'}
            ]}),
        )
        client.validate_request('txn-42', b'\x01\x02\x03')
        assert captured['url'] == 'https://fef.example/scep/ScepActions/validateRequest'
        req = captured['json']['request']
        assert req['transactionId'] == 'txn-42'
        assert req['certificateRequest'] == 'AQID'  # base64(b'\x01\x02\x03')
        assert req['callerInfo'] == 'UCM-Test/1.0'
        assert captured['headers']['api-version'] == '2018-02-20'
        assert 'client-request-id' in captured['headers']

    def test_transport_failure_raises_and_clears_endpoint_cache(self, client, monkeypatch):
        monkeypatch.setattr(
            'requests.post',
            lambda *a, **k: _FakeResponse({'access_token': 't', 'expires_in': 3600}),
        )
        monkeypatch.setattr(
            'requests.get',
            lambda *a, **k: _FakeResponse({'value': [
                {'providerName': 'ScepRequestValidationFEService', 'uri': 'https://fef.example/scep'}
            ]}),
        )
        client._get_service_endpoint()  # populate cache
        assert client._service_endpoint == 'https://fef.example/scep'

        def failing_post(url, data=None, json=None, headers=None, timeout=None):
            if 'oauth2' in url:
                return _FakeResponse({'access_token': 't', 'expires_in': 3600})
            return _FakeResponse({}, status_code=500)

        monkeypatch.setattr('requests.post', failing_post)
        with pytest.raises(IntuneScepError):
            client.validate_request('txn-1', b'x')
        assert client._service_endpoint is None


class TestNotifications:

    def _mock(self, monkeypatch, capture_into):
        def fake_post(url, data=None, json=None, headers=None, timeout=None):
            if 'oauth2' in url:
                return _FakeResponse({'access_token': 't', 'expires_in': 3600})
            capture_into['url'] = url
            capture_into['json'] = json
            return _FakeResponse({'code': 'Success', 'errorDescription': ''})

        monkeypatch.setattr('requests.post', fake_post)
        monkeypatch.setattr(
            'requests.get',
            lambda *a, **k: _FakeResponse({'value': [
                {'providerName': 'ScepRequestValidationFEService', 'uri': 'https://fef.example/scep'}
            ]}),
        )

    def test_success_notification_shape(self, client, monkeypatch):
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
        from datetime import datetime, timedelta, timezone

        captured = {}
        self._mock(monkeypatch, captured)

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'issuer-ca')])
        now = datetime.now(timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'device1')]))
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(12345)
            .not_valid_before(now)
            .not_valid_after(now + timedelta(days=30))
            .sign(key, hashes.SHA256())
        )

        client.send_success_notification('txn-1', b'\x01\x02', cert)
        assert captured['url'] == 'https://fef.example/scep/ScepActions/successNotification'
        n = captured['json']['notification']
        assert n['transactionId'] == 'txn-1'
        assert n['certificateSerialNumber'] == format(12345, 'X')
        assert n['certificateThumbprint'] == cert.fingerprint(hashes.SHA1()).hex().upper()
        assert n['issuingCertificateAuthority'] == 'CN=issuer-ca'
        assert n['callerInfo'] == 'UCM-Test/1.0'
        assert n['certificateExpirationDateUtc'].endswith('Z')

    def test_failure_notification_shape(self, client, monkeypatch):
        captured = {}
        self._mock(monkeypatch, captured)
        client.send_failure_notification('txn-2', b'\x01', 0x80004005, 'boom')
        n = captured['json']['notification']
        assert n['transactionId'] == 'txn-2'
        assert n['hResult'] == 0x80004005
        assert n['errorDescription'] == 'boom'


def test_test_connection_only_discovers_no_scep_actions(client, monkeypatch):
    """test_connection() must never touch ScepActions/* -- it should not
    spend a real Intune challenge just to check credentials."""
    posted_urls = []

    def fake_post(url, **kwargs):
        posted_urls.append(url)
        return _FakeResponse({'access_token': 't', 'expires_in': 3600})

    monkeypatch.setattr('requests.post', fake_post)
    monkeypatch.setattr(
        'requests.get',
        lambda *a, **k: _FakeResponse({'value': [
            {'providerName': 'ScepRequestValidationFEService', 'uri': 'https://fef.example/scep'}
        ]}),
    )
    client.test_connection()
    assert all('ScepActions' not in u for u in posted_urls)
