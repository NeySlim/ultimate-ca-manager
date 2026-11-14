"""Every HMAC UCM computes itself goes through the one-shot call (``hmac.digest``).

On the OpenSSL FIPS Provider 3.5 only that call reaches the module's HMAC service and
its key-length check; ``hmac.new`` assembles HMAC in libcrypto around the module's
digests. Each site keeps producing the same bytes: the reference is a published vector
(RFC 4231, RFC 6238) or ``hmac.new`` called here with the digest written out, never a
value the code under test computed.
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


def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def test_csrf_token(app):
    from security.csrf import CSRFProtection
    secret = 'k' * 32
    expected = hmac.new(secret.encode(), b'1700000000:' + b'ab' * 16 + b':7', hashlib.sha256).hexdigest()
    with app.test_request_context(), patch.dict(app.config, {'SECRET_KEY': secret}), \
            patch('security.csrf.time.time', return_value=1700000000), \
            patch('security.csrf.secrets.token_hex', return_value='ab' * 16):
        with _without_hmac_new():
            token = CSRFProtection.generate_token(7)
            assert token == f"1700000000:{'ab' * 16}:{expected}"
            assert CSRFProtection.validate_token(token, 7)[0] is True


def test_webauthn_decoy_id():
    from services.webauthn_service import WebAuthnService
    expected = hmac.new(b's' * 32, b'webauthn-decoy:alice', hashlib.sha256).digest()
    with _without_hmac_new():
        options = WebAuthnService.generate_decoy_authentication_options('Alice', 'ucm.test', b's' * 32)
    assert options['allowCredentials'][0]['id'] == _b64url(expected)


def _assert_eab_signed(eab, key):
    signing_input = f"{eab['protected']}.{eab['payload']}".encode()
    assert eab['signature'] == _b64url(hmac.new(key, signing_input, hashlib.sha256).digest())


def test_acme_client_and_proxy_eab():
    from services.acme.acme_client_service import AcmeClientService
    from services.acme.acme_proxy_service import AcmeProxyService
    key = ec.generate_private_key(ec.SECP256R1())
    client = SimpleNamespace(_get_account_key=lambda: key,
                             _build_jwk=lambda k: AcmeClientService._build_jwk(None, k))
    proxy = SimpleNamespace(account_jwk={'kty': 'EC', 'crv': 'P-256', 'x': 'x', 'y': 'y'})
    raw = bytes(range(32))
    with _without_hmac_new():
        both = (AcmeClientService._build_eab_payload(client, 'kid', _b64url(raw), 'https://ca.test/new'),
                AcmeProxyService._build_eab(proxy, 'kid', _b64url(raw), 'https://ca.test/new'))
    for eab in both:
        assert json.loads(base64.urlsafe_b64decode(eab['protected'] + '=='))['alg'] == 'HS256'
        _assert_eab_signed(eab, raw)


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


DNS_CREDS = {'api_key': 'a', 'secret_key': 's' * 32, 'secret_id': 'i', 'username': 'u',
             'password': 'p'}


def test_dnsmadeeasy_signature():
    from services.acme.dns_providers.dnsmadeeasy import DnsMadeEasyDnsProvider
    with _without_hmac_new():
        headers = DnsMadeEasyDnsProvider(DNS_CREDS)._get_headers()
    expected = hmac.new(b's' * 32, headers['x-dnsme-requestDate'].encode(), hashlib.sha1).hexdigest()
    assert headers['x-dnsme-hmac'] == expected


def test_constellix_signature():
    from services.acme.dns_providers.constellix import ConstellixDnsProvider
    with patch('time.time', return_value=1700000000.0), _without_hmac_new():
        token = ConstellixDnsProvider(DNS_CREDS)._get_headers()['Authorization']
    expected = base64.b64encode(hmac.new(b's' * 32, b'1700000000000', hashlib.sha1).digest()).decode()
    assert token == f'Bearer a:{expected}:1700000000000'


def test_tencentcloud_signature():
    """TC3-HMAC-SHA256: the key chain and the string to sign of Tencent Cloud API 3.0."""
    from services.acme.dns_providers.tencentcloud import TencentCloudDnsProvider
    provider = TencentCloudDnsProvider(DNS_CREDS)
    with patch('time.time', return_value=1700000000.0), _without_hmac_new():
        authorization = provider._make_headers('DescribeDomain', '{}')['Authorization']

    def sign(key, msg):
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()
    host = provider.BASE_URL.split('://')[1]
    canonical = '\n'.join(['POST', '/', '', f'content-type:application/json\nhost:{host}\n',
                           'content-type;host', hashlib.sha256(b'{}').hexdigest()])
    scope = f'2023-11-14/{provider.SERVICE}/tc3_request'
    to_sign = '\n'.join(['TC3-HMAC-SHA256', '1700000000', scope,
                         hashlib.sha256(canonical.encode()).hexdigest()])
    key = sign(sign(sign(b'TC3' + b's' * 32, '2023-11-14'), provider.SERVICE), 'tc3_request')
    expected = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    assert authorization.endswith(f'Signature={expected}'), authorization


def test_inwx_totp_is_the_rfc_6238_vector():
    from services.acme.dns_providers.inwx import InwxDnsProvider
    with patch('time.time', return_value=59.0), _without_hmac_new():
        assert InwxDnsProvider(DNS_CREDS)._generate_totp('GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ') == '287082'


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
