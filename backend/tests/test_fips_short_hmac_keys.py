"""FIPS mode: an HMAC key the operator gave under 14 bytes is refused by UCM before the
module sees it, with a refusal naming the setting, never the module's raw ValueError.

The 3.5.9 module's one-shot HMAC refuses such a key with ``ValueError: [Provider routines]
invalid key length``; ``module_refusal`` reproduces that here, where no module is loaded.
"""
import base64
import hmac
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives.asymmetric import ec

import fips_mode

_real_digest = hmac.digest


def _module_digest(key, msg, digest):
    if len(key) < fips_mode.MIN_HMAC_KEY_BYTES:
        raise ValueError('[Provider routines] invalid key length')
    return _real_digest(key, msg, digest)


@pytest.fixture
def module_refusal(monkeypatch):
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
    monkeypatch.setattr(hmac, 'digest', _module_digest)


def _fips_refusal(text, setting):
    text = str(text)
    assert 'invalid key length' not in text, text
    assert 'not available in FIPS mode' in text and setting in text, text


def _no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError('no request is sent with a refused key')
    for name in ('request', 'post', 'get'):
        monkeypatch.setattr(f'requests.{name}', refuse)


def test_inwx_shared_secret(module_refusal, monkeypatch):
    from services.acme.dns_providers.inwx import InwxDnsProvider
    secret = base64.b32encode(b'\x01' * 10).decode()  # 80 bits, a common TOTP size
    provider = InwxDnsProvider({'username': 'u', 'password': 'p', 'shared_secret': secret})
    with pytest.raises(fips_mode.FipsRestricted) as refused:
        provider._generate_totp(secret)
    _fips_refusal(refused.value, 'INWX shared secret')


def test_constellix_secret_key(module_refusal, monkeypatch):
    from services.acme.dns_providers.constellix import ConstellixDnsProvider
    _no_network(monkeypatch)
    ok, message = ConstellixDnsProvider({'api_key': 'a', 'secret_key': 'short'})._request('GET', '/domains')
    assert ok is False
    _fips_refusal(message, 'Constellix secret key')


def test_dnsmadeeasy_secret_key(module_refusal, monkeypatch):
    from services.acme.dns_providers.dnsmadeeasy import DnsMadeEasyDnsProvider
    _no_network(monkeypatch)
    with pytest.raises(fips_mode.FipsRestricted) as refused:
        DnsMadeEasyDnsProvider({'api_key': 'a', 'secret_key': 'short'})._request('GET', '/dns/managed/')
    _fips_refusal(refused.value, 'DNS Made Easy secret key')


def test_tencentcloud_secret_key(module_refusal, monkeypatch):
    from services.acme.dns_providers.tencentcloud import TencentCloudDnsProvider
    _no_network(monkeypatch)
    provider = TencentCloudDnsProvider({'secret_id': 'i', 'secret_key': 'short'})
    with pytest.raises(fips_mode.FipsRestricted) as refused:
        provider._post('DescribeDomain', {'Domain': 'example.test'})
    _fips_refusal(refused.value, 'Tencent Cloud secret key')


def test_tencentcloud_key_of_eleven_bytes_signs(module_refusal):
    """The first HMAC key is "TC3" + the secret: 11 bytes of secret reach 14."""
    from services.acme.dns_providers.tencentcloud import TencentCloudDnsProvider
    provider = TencentCloudDnsProvider({'secret_id': 'i', 'secret_key': 's' * 11})
    assert 'Signature=' in provider._make_headers('DescribeDomain', '{}')['Authorization']


def _eab_client():
    from services.acme.acme_client_service import AcmeClientService
    key = ec.generate_private_key(ec.SECP256R1())
    return AcmeClientService, SimpleNamespace(
        _get_account_key=lambda: key, _build_jwk=lambda k: AcmeClientService._build_jwk(None, k))


def test_acme_client_eab_key(module_refusal):
    service, client = _eab_client()
    short = base64.urlsafe_b64encode(b'e' * 10).rstrip(b'=').decode()
    with pytest.raises(fips_mode.FipsRestricted) as refused:
        service._build_eab_payload(client, 'kid', short, 'https://ca.test/new')
    _fips_refusal(refused.value, 'EAB HMAC key')


def test_acme_client_registration_shows_the_refusal(module_refusal, monkeypatch):
    """Registration renders the exception text: it is the FIPS refusal."""
    from services.acme.acme_client_service import AcmeClientService
    service = AcmeClientService.__new__(AcmeClientService)
    key = ec.generate_private_key(ec.SECP256R1())
    monkeypatch.setattr(service, '_fetch_directory', lambda: {'newAccount': 'https://ca.test/new'},
                        raising=False)
    monkeypatch.setattr(service, '_get_account_key', lambda: key, raising=False)
    monkeypatch.setattr(service, '_get_eab_credentials',
                        lambda: ('kid', base64.urlsafe_b64encode(b'e' * 10).decode()), raising=False)
    monkeypatch.setattr(service, '_post', lambda *a, **k: pytest.fail('nothing is posted'),
                        raising=False)
    ok, message = service.register_account('a@example.test')[:2]
    assert ok is False
    _fips_refusal(message, 'EAB HMAC key')


def test_acme_proxy_eab_key(module_refusal):
    from services.acme.acme_proxy_service import AcmeProxyService
    proxy = SimpleNamespace(account_jwk={'kty': 'EC', 'crv': 'P-256', 'x': 'x', 'y': 'y'})
    short = base64.urlsafe_b64encode(b'e' * 10).rstrip(b'=').decode()
    with pytest.raises(fips_mode.FipsRestricted) as refused:
        AcmeProxyService._build_eab(proxy, 'kid', short, 'https://ca.test/new')
    _fips_refusal(refused.value, 'EAB HMAC key')


def test_csrf_secret_key(app, module_refusal):
    """A short SECRET_KEY: issuing a token is refused with the FIPS reason (the login answers
    the 400 FIPS problem), and a token is not checked against it."""
    from security.csrf import CSRFProtection
    with app.test_request_context():
        with patch.dict(app.config, {'SECRET_KEY': 'short-key', 'SECRET_KEY_FALLBACKS': []}):
            with pytest.raises(fips_mode.FipsRestricted) as refused:
                CSRFProtection.generate_token(7)
            _fips_refusal(refused.value, 'SECRET_KEY')
            ok, reason = CSRFProtection.validate_token(f'{int(time.time())}:ab:cd', 7)
            assert ok is False
            _fips_refusal(reason, 'SECRET_KEY')


def test_long_keys_still_sign(app, module_refusal):
    """At 14 bytes and more nothing is refused."""
    from security.csrf import CSRFProtection
    from services.acme.acme_proxy_service import AcmeProxyService
    from services.acme.dns_providers.dnsmadeeasy import DnsMadeEasyDnsProvider
    with app.test_request_context(), patch.dict(app.config, {'SECRET_KEY': 'k' * 14}):
        token = CSRFProtection.generate_token(7)
        assert CSRFProtection.validate_token(token, 7) == (True, '')
    assert DnsMadeEasyDnsProvider({'api_key': 'a', 'secret_key': 's' * 14})._get_headers()['x-dnsme-hmac']
    proxy = SimpleNamespace(account_jwk={'kty': 'EC'})
    key = base64.urlsafe_b64encode(b'e' * 14).rstrip(b'=').decode()
    assert AcmeProxyService._build_eab(proxy, 'kid', key, 'https://ca.test/new')['signature']


def test_outside_fips_mode_short_keys_sign(monkeypatch):
    from services.acme.dns_providers.constellix import ConstellixDnsProvider
    monkeypatch.setattr(fips_mode, 'enabled', lambda: False)
    assert ConstellixDnsProvider({'api_key': 'a', 'secret_key': 'short'})._get_headers()['Authorization']
