"""ACME client TLS-ALPN-01 and RFC 8738 IP identifier coverage."""
import base64
import ipaddress
import json
import socket
import ssl
from unittest.mock import MagicMock

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization

from models import AcmeClientOrder, db
from models.acme_client_account import AcmeClientAccount
from services.acme.acme_client_service import AcmeClientService


class _Response:
    def __init__(self, status_code, payload=None, location=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = {'Location': location} if location else {}

    def json(self):
        return self._payload


def _registered_account():
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1(), default_backend())
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    account = AcmeClientAccount(
        directory_url='https://ca.example/directory',
        label='IP test CA',
        email='admin@example.com',
        account_url='https://ca.example/acct/1',
        account_key=key_pem,
        account_key_algorithm='ES256',
    )
    db.session.add(account)
    db.session.commit()
    return account


def test_client_new_order_sends_ip_identifier_and_canonicalizes_ipv6(app, monkeypatch):
    with app.app_context():
        account = _registered_account()
        service = AcmeClientService(account=account)
        monkeypatch.setattr(service, 'ensure_account', lambda _email: (True, 'ok'))
        monkeypatch.setattr(service, '_fetch_directory', lambda: {
            'newOrder': 'https://ca.example/new-order',
        })
        submitted = {}
        authorizations = {
            'https://ca.example/authz/dns': {'type': 'dns', 'value': 'example.com'},
            'https://ca.example/authz/ip': {'type': 'ip', 'value': '2001:db8::1'},
        }

        def fake_post(url, payload, use_jwk=False):
            if url == 'https://ca.example/new-order':
                submitted.update(payload)
                return _Response(201, {
                    'expires': '2027-01-01T00:00:00Z',
                    'finalize': 'https://ca.example/order/1/finalize',
                    'authorizations': list(authorizations),
                }, 'https://ca.example/order/1')
            identifier = authorizations[url]
            return _Response(200, {
                'identifier': identifier,
                'status': 'pending',
                'challenges': [{
                    'type': 'tls-alpn-01',
                    'token': f"token-{identifier['type']}",
                    'url': f'{url}/challenge',
                    'status': 'pending',
                }],
            })

        monkeypatch.setattr(service, '_post', fake_post)
        ok, message, order = service.create_order(
            ['example.com', '2001:0db8:0:0:0:0:0:1'],
            'admin@example.com',
            challenge_type='tls-alpn-01',
        )

        assert ok, message
        assert submitted['identifiers'] == [
            {'type': 'dns', 'value': 'example.com'},
            {'type': 'ip', 'value': '2001:db8::1'},
        ]
        assert order.domains_list == ['example.com', '2001:db8::1']
        assert set(order.challenges_dict) == {'example.com', '2001:db8::1'}
        db.session.delete(order)
        db.session.delete(account)
        db.session.commit()


def test_generated_csr_uses_ipaddress_san():
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1(), default_backend())
    encoded = AcmeClientService._build_csr_b64(
        key,
        ['example.com', '192.0.2.10', '2001:db8::10'],
        'example.com',
    )
    csr = x509.load_der_x509_csr(
        base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4))
    )
    san = csr.extensions.get_extension_for_class(x509.SubjectAlternativeName).value

    assert san.get_values_for_type(x509.DNSName) == ['example.com']
    assert san.get_values_for_type(x509.IPAddress) == [
        ipaddress.ip_address('192.0.2.10'),
        ipaddress.ip_address('2001:db8::10'),
    ]

    from services.acme.acme_client_service import csr_identifiers_match_order
    assert csr_identifiers_match_order(
        csr, ['example.com', '192.0.2.10', '2001:db8::10']
    )[0]


def test_tls_alpn_certificate_and_high_port_listener():
    from utils.acme_ip import ACME_IDENTIFIER_OID, TlsAlpn01Listener

    key_authorization = 'token.account-thumbprint'
    listener = TlsAlpn01Listener(
        '127.0.0.1',
        key_authorization,
        bind_host='127.0.0.1',
        port=0,
    )
    listener.start()
    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        context.set_alpn_protocols(['acme-tls/1'])
        with socket.create_connection(('127.0.0.1', listener.port), timeout=3) as raw:
            with context.wrap_socket(raw, server_hostname='1.0.0.127.in-addr.arpa') as tls:
                assert tls.selected_alpn_protocol() == 'acme-tls/1'
                cert_der = tls.getpeercert(binary_form=True)

        cert = x509.load_der_x509_certificate(cert_der)
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        assert san.get_values_for_type(x509.IPAddress) == [ipaddress.ip_address('127.0.0.1')]
        acme_identifier = cert.extensions.get_extension_for_oid(ACME_IDENTIFIER_OID)
        assert acme_identifier.critical is True
        assert acme_identifier.value.value[:2] == b'\x04\x20'
        assert len(acme_identifier.value.value) == 34
    finally:
        listener.stop()

    assert not listener.is_running


def test_tls_alpn_listener_bind_error_suggests_other_challenges():
    from utils.acme_ip import TlsAlpn01Listener, TlsAlpn01ListenerError

    occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupied.bind(('127.0.0.1', 0))
    occupied.listen(1)
    port = occupied.getsockname()[1]
    listener = TlsAlpn01Listener(
        'example.com',
        'token.thumbprint',
        bind_host='127.0.0.1',
        port=port,
    )
    try:
        with pytest.raises(TlsAlpn01ListenerError) as exc:
            listener.start()
        message = str(exc.value)
        assert str(port) in message
        assert 'http-01' in message
        assert 'dns-01' in message
    finally:
        listener.stop()
        occupied.close()


def test_tls_alpn_verification_stops_listener_after_poll(app, monkeypatch):
    with app.app_context():
        service = object.__new__(AcmeClientService)
        listener = MagicMock()
        monkeypatch.setattr(service, '_create_tls_alpn_listener', lambda *_args: listener)
        monkeypatch.setattr(service, 'get_poll_settings', lambda: {
            'order_poll_timeout_sec': 5,
            'order_poll_interval_sec': 1,
            'http_timeout_sec': 5,
        })
        monkeypatch.setattr(service, '_post', lambda _url, _payload: _Response(
            200, {'status': 'processing'}
        ))
        statuses = iter([
            ('pending', {}),
            ('valid', {'status': 'valid'}),
        ])
        monkeypatch.setattr(service, 'check_authorization_status', lambda *_args: next(statuses))

        order = AcmeClientOrder(
            domains=json.dumps(['example.com']),
            challenge_type='tls-alpn-01',
            environment='custom',
            status='pending',
        )
        order.set_challenges_dict({
            'example.com': {
                'url': 'https://ca.example/challenge/1',
                'authz_url': 'https://ca.example/authz/1',
                'key_authorization': 'token.thumbprint',
                'status': 'pending',
                'authz_status': 'pending',
            },
        })
        db.session.add(order)
        db.session.commit()

        ok, message = service.verify_challenge(order, 'example.com')

        assert ok, message
        listener.start.assert_called_once_with()
        listener.stop.assert_called_once_with()
        db.session.delete(order)
        db.session.commit()


def test_client_api_rejects_dns01_for_ip(auth_client):
    response = auth_client.post('/api/v2/acme/client/request', json={
        'domains': ['192.0.2.25'],
        'email': 'admin@example.com',
        'challenge_type': 'dns-01',
        'environment': 'staging',
    })
    assert response.status_code == 400
    assert 'dns-01' in response.get_json()['message'].lower()


def test_client_api_accepts_tls_alpn01_and_ipv6(auth_client, monkeypatch):
    fake_client = MagicMock()
    fake_client.create_order.return_value = (False, 'upstream marker', None)
    monkeypatch.setattr(
        AcmeClientService,
        'for_issuance',
        lambda **_kwargs: fake_client,
    )

    response = auth_client.post('/api/v2/acme/client/request', json={
        'domains': ['2001:0db8:0:0:0:0:0:25'],
        'email': 'admin@example.com',
        'challenge_type': 'tls-alpn-01',
        'environment': 'staging',
    })

    assert response.status_code == 400
    assert response.get_json()['message'] == 'upstream marker'
    assert fake_client.create_order.call_args.kwargs['domains'] == ['2001:db8::25']


@pytest.mark.parametrize('payload, expected_type', [
    ({'identifiers': [{'type': 'ip', 'value': '192.0.2.44'}]}, 'unsupportedIdentifier'),
    ({
        'identifiers': [{'type': 'dns', 'value': 'example.com'}],
        'challenge_type': 'tls-alpn-01',
    }, 'malformed'),
])
def test_proxy_rejects_ip_and_tls_alpn_requests(client, monkeypatch, payload, expected_type):
    from api.acme import acme_proxy_api

    service_factory = MagicMock()
    monkeypatch.setattr(
        acme_proxy_api,
        'verify_proxy_jws',
        lambda: (True, payload, None, None),
    )
    monkeypatch.setattr(acme_proxy_api, 'get_proxy_service', service_factory)
    monkeypatch.setattr(acme_proxy_api, '_kid_account_thumbprint', lambda _protected: None)

    response = client.post(
        '/acme/proxy/new-order',
        data=json.dumps({'protected': 'stub', 'payload': 'stub', 'signature': 'stub'}),
        content_type='application/jose+json',
    )

    assert response.status_code == 400
    assert response.get_json()['type'].endswith(expected_type)
    assert 'dns-01' in response.get_json()['detail']
    service_factory.assert_not_called()
