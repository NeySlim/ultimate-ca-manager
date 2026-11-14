"""Every HMAC UCM computes itself goes through the one-shot call (``hmac.digest``).

On the OpenSSL FIPS Provider 3.5 only that call reaches the module's HMAC service and
its key-length check; ``hmac.new`` assembles HMAC in libcrypto around the module's
digests. Each site keeps producing the same bytes: the reference is computed with
``hmac.new`` before it is made unavailable.
"""
import base64
import hashlib
import hmac
import json
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives.asymmetric import ec

# RFC 4231, test case 2
JEFE_KEY, JEFE_DATA = b'Jefe', b'what do ya want for nothing?'
JEFE_SHA256 = '5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843'


@contextmanager
def _without_hmac_new():
    def refuse(*args, **kwargs):
        raise AssertionError('hmac.new is not the one-shot call')
    with patch.object(hmac, 'new', refuse):
        yield


def _webhook_signature(monkeypatch, secret, body):
    from services import webhook_service
    from services.webhook_service import WebhookEndpoint
    sent = {}

    def post(url, data=None, headers=None, timeout=None):
        sent.update(headers)
        return SimpleNamespace(ok=True, status_code=200)

    monkeypatch.setattr('utils.ssrf_protection.safe_request_post', post)
    endpoint = WebhookEndpoint(name='vector', url='https://receiver.test/hook', secret=secret,
                               auth_type='none')
    ok, _, _ = webhook_service.WebhookService._perform_delivery(endpoint, 'test', body)
    assert ok
    return sent['X-UCM-Signature']


def test_webhook_signature_is_the_rfc_4231_vector(app, monkeypatch):
    with app.app_context():
        assert _webhook_signature(monkeypatch, 'Jefe', JEFE_DATA.decode()) == f'sha256={JEFE_SHA256}'
        with _without_hmac_new():
            assert _webhook_signature(monkeypatch, 'Jefe', JEFE_DATA.decode()) == f'sha256={JEFE_SHA256}'


def test_a_short_webhook_secret_does_not_sign_in_fips_mode(app, monkeypatch):
    """A secret under 14 bytes saved before the switch: the delivery fails with the FIPS
    reason on every module, nothing is sent; outside FIPS mode it still signs."""
    import fips_mode
    from services import webhook_service
    from services.webhook_service import WebhookEndpoint
    sent = []
    monkeypatch.setattr('utils.ssrf_protection.safe_request_post',
                        lambda *a, **k: sent.append(k) or SimpleNamespace(ok=True, status_code=200))
    endpoint = WebhookEndpoint(name='short', url='https://receiver.test/hook', secret='Jefe',
                               auth_type='none')
    with app.app_context():
        monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
        ok, code, error = webhook_service.WebhookService._perform_delivery(endpoint, 'test', '{}')
        assert (ok, code, sent) == (False, None, [])
        assert error.startswith('Webhook secret of 4 bytes not available in FIPS mode'), error
        monkeypatch.setattr(fips_mode, 'enabled', lambda: False)
        assert webhook_service.WebhookService._perform_delivery(endpoint, 'test', '{}')[0] is True


def test_csrf_token(app):
    from security.csrf import CSRFProtection
    with app.test_request_context(), patch('security.csrf.time.time', return_value=1700000000), \
            patch('security.csrf.secrets.token_hex', return_value='ab' * 16):
        reference = CSRFProtection.generate_token(7)
        with _without_hmac_new():
            assert CSRFProtection.generate_token(7) == reference
            assert CSRFProtection.validate_token(reference, 7)[0] is True


def test_webauthn_decoy_id():
    from services.webauthn_service import WebAuthnService

    def decoy():
        options = WebAuthnService.generate_decoy_authentication_options('alice', 'ucm.test', b's' * 32)
        return options['allowCredentials'][0]['id']

    reference = decoy()
    with _without_hmac_new():
        assert decoy() == reference


def test_acme_client_and_proxy_eab():
    from services.acme.acme_client_service import AcmeClientService
    from services.acme.acme_proxy_service import AcmeProxyService
    key = ec.generate_private_key(ec.SECP256R1())
    client = SimpleNamespace(_get_account_key=lambda: key,
                             _build_jwk=lambda k: AcmeClientService._build_jwk(None, k))
    proxy = SimpleNamespace(account_jwk={'kty': 'EC', 'crv': 'P-256', 'x': 'x', 'y': 'y'})
    hmac_key = base64.urlsafe_b64encode(b'e' * 32).rstrip(b'=').decode()

    def both():
        return (AcmeClientService._build_eab_payload(client, 'kid', hmac_key, 'https://ca.test/new'),
                AcmeProxyService._build_eab(proxy, 'kid', hmac_key, 'https://ca.test/new'))

    reference = both()
    with _without_hmac_new():
        assert both() == reference


@pytest.mark.parametrize('alg, digest', [('HS256', hashlib.sha256), ('HS384', hashlib.sha384),
                                         ('HS512', hashlib.sha512)])
def test_acme_server_eab_verification(app, alg, digest):
    import uuid

    from models import db
    from models.acme_models import AcmeEabCredential
    from services.acme.acme_service import AcmeService
    jwk = {'kty': 'EC', 'crv': 'P-256', 'x': 'f83OJ3D2xF1Bg8vub9tLe1gHMzV76e8Tus9uPHvRVEU',
           'y': 'x_FEzRu9m36HLN_tue659LNpXW6pCyStikYjKIWI5a0'}
    kid, key = f'one-shot-{uuid.uuid4().hex[:8]}', b'k' * 32

    def b64(data):
        return base64.urlsafe_b64encode(data).rstrip(b'=').decode()

    protected = b64(json.dumps({'alg': alg, 'kid': kid, 'url': 'http://localhost/new'}).encode())
    payload = b64(json.dumps(jwk).encode())
    eab = {'protected': protected, 'payload': payload,
           'signature': b64(hmac.new(key, f'{protected}.{payload}'.encode(), digest).digest())}
    with app.app_context():
        db.session.add(AcmeEabCredential(kid=kid, hmac_key_b64=b64(key), status='active'))
        db.session.commit()
        try:
            with _without_hmac_new():
                assert AcmeService(base_url='http://localhost').validate_eab(
                    eab, jwk, 'http://localhost/new') == (True, None)
        finally:
            AcmeEabCredential.query.filter_by(kid=kid).delete()
            db.session.commit()


def test_dns_provider_signatures():
    from services.acme.dns_providers.constellix import ConstellixDnsProvider
    from services.acme.dns_providers.dnsmadeeasy import DnsMadeEasyDnsProvider
    from services.acme.dns_providers.inwx import InwxDnsProvider
    from services.acme.dns_providers.tencentcloud import TencentCloudDnsProvider
    creds = {'api_key': 'a', 'secret_key': 's' * 32, 'secret_id': 'i', 'username': 'u',
             'password': 'p'}

    def all_of():
        with patch('time.time', return_value=1700000000.0):
            return (DnsMadeEasyDnsProvider(creds)._get_headers()['x-dnsme-hmac'],
                    ConstellixDnsProvider(creds)._get_headers(),
                    TencentCloudDnsProvider(creds)._make_headers('Action', '{}')['Authorization'],
                    InwxDnsProvider(creds)._generate_totp('JBSWY3DPEHPK3PXPJBSWY3DPEH'))

    reference = all_of()
    with _without_hmac_new():
        assert all_of() == reference


def test_pkcs12_mac_check():
    from asn1crypto import pkcs12 as asn1_pkcs12
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.serialization import PrivateFormat, pkcs12

    from utils import pkcs12_layers
    blob = pkcs12.serialize_key_and_certificates(
        b'k', ec.generate_private_key(ec.SECP256R1()), None, None,
        PrivateFormat.PKCS12.encryption_builder().kdf_rounds(2048).hmac_hash(hashes.SHA256())
        .key_cert_algorithm(pkcs12.PBES.PBESv2SHA256AndAES256CBC).build(b'right'))
    check = pkcs12_layers._mac(asn1_pkcs12.Pfx.load(blob))
    with _without_hmac_new():
        assert check(b'right') is True
        assert check(b'wrong') is False
