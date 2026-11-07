"""Small ACME client and proxy conformance points: ARI renewal instant (RFC 9773
§4.2), readable non-JSON errors, minimal JWK exponent (RFC 7518 §6.3.1.2),
unquoted Link relations (RFC 8288), proxy User-Agent (RFC 8555 §6.1), keyChange
not advertised by the proxy, DNS provider credentials and redirects, Cloudflare
delete failures."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from services import acme_renewal_service as renew_mod


class TestAriRenewalInstant:
    NOW = datetime(2026, 11, 7, 12, 0)

    def _due(self, start, end, draw, key=1):
        certificate = SimpleNamespace(id=key, valid_to=self.NOW + timedelta(days=60))
        row = SimpleNamespace(id=key, certificate_id=key, acme_client_account_id=1,
                              expires_at=certificate.valid_to)
        info = {'suggested_window': {'start': start, 'end': end}}
        with patch.object(renew_mod, '_cached_renewal_info', return_value=info), \
                patch.object(renew_mod.db.session, 'get', return_value=certificate), \
                patch.object(renew_mod.random, 'random', return_value=draw):
            return renew_mod._order_is_due(row, self.NOW, self.NOW + timedelta(days=30))

    @pytest.fixture(autouse=True)
    def _fresh(self):
        renew_mod._ARI_PICKS.clear()
        yield
        renew_mod._ARI_PICKS.clear()

    def test_open_window_waits_for_the_drawn_instant(self):
        start, end = self.NOW - timedelta(hours=1), self.NOW + timedelta(days=30)
        assert self._due(start, end, 0.9) is False

    def test_drawn_instant_before_the_next_pass_renews_now(self):
        start, end = self.NOW - timedelta(hours=1), self.NOW + timedelta(days=30)
        assert self._due(start, end, 0.0) is True

    def test_instant_is_kept_for_the_same_window(self):
        start, end = self.NOW - timedelta(hours=1), self.NOW + timedelta(days=30)
        assert self._due(start, end, 0.9) is False
        assert self._due(start, end, 0.0) is False  # same window: same instant
        assert self._due(start, end + timedelta(seconds=1), 0.0) is True

    def test_window_in_the_future_is_not_due(self):
        assert self._due(self.NOW + timedelta(days=1), self.NOW + timedelta(days=2), 0.0) is False


class TestReadableErrors:
    def test_html_503_on_new_order_names_the_status(self):
        from services.acme.acme_client_service import AcmeClientService
        resp = SimpleNamespace(status_code=503, headers={'Retry-After': '120'},
                               text='<html>busy</html>')
        resp.json = MagicMock(side_effect=ValueError('Expecting value'))
        detail = AcmeClientService._problem_detail(resp)
        assert 'HTTP 503' in detail and '120' in detail
        assert 'Expecting value' not in detail

    def test_problem_detail_is_kept(self):
        from services.acme.acme_client_service import AcmeClientService
        resp = SimpleNamespace(status_code=400, headers={},
                               json=lambda: {'type': 'urn:ietf:params:acme:error:badCSR',
                                             'detail': 'bad key'})
        assert AcmeClientService._problem_detail(resp) == 'bad key'


class TestJwkExponent:
    def test_exponent_uses_the_minimum_number_of_octets(self):
        from cryptography.hazmat.primitives.asymmetric import rsa
        from services.acme.acme_client_service import AcmeClientService
        svc = AcmeClientService.__new__(AcmeClientService)
        key3 = rsa.generate_private_key(public_exponent=3, key_size=1024)
        key65537 = rsa.generate_private_key(public_exponent=65537, key_size=1024)
        assert svc._build_jwk(key3)['e'] == 'Aw'
        assert svc._build_jwk(key65537)['e'] == 'AQAB'


class TestAlternateLink:
    @pytest.mark.parametrize('header', [
        '<https://ca.example/cert/1/1>;rel="alternate"',
        '<https://ca.example/cert/1/1>; rel=alternate',
        '<https://ca.example/cert/1/1>; rel="alternate index"',
        '<https://ca.example/dir>;rel="index", <https://ca.example/cert/1/1>;rel=alternate',
    ])
    def test_alternate_relation_is_recognised(self, header):
        from services.acme.acme_chain_selection import parse_link_rel_alternate
        assert parse_link_rel_alternate(header) == ['https://ca.example/cert/1/1']

    def test_other_relations_are_ignored(self):
        from services.acme.acme_chain_selection import parse_link_rel_alternate
        assert parse_link_rel_alternate('<https://ca.example/dir>;rel="index"') == []


class TestProxyIdentity:
    def test_upstream_posts_carry_the_ucm_user_agent(self, app, monkeypatch):
        from services.acme.acme_proxy_service import AcmeProxyService
        sent = {}

        def _post(url, **kwargs):
            sent.update(kwargs.get('headers') or {})
            return SimpleNamespace(status_code=200, headers={})

        monkeypatch.setattr('utils.ssrf_protection.safe_request_post', _post)
        with app.app_context():
            svc = AcmeProxyService('http://localhost/acme/proxy')
            svc.upstream_directory_url = 'https://ca-ua.example/directory'
            monkeypatch.setattr(svc, '_detect_key_algorithm', lambda: 'ES256')
            monkeypatch.setattr(svc, '_sign_data', lambda _d: b'sig')
            monkeypatch.setattr(svc, '_validate_outbound_acme_url', lambda _u: None)
            svc._account_jwk = {'kty': 'EC'}
            svc._key_loaded = True
            svc._sign_and_post('https://ca-ua.example/acme/new-order', {}, 'nonce', kid='k')
        from config.settings import Config
        assert sent['User-Agent'] == f'UCM-ACME-Client/{Config.APP_VERSION}'

    def test_proxy_directory_does_not_offer_key_change(self, app, monkeypatch):
        from services.acme.acme_proxy_service import AcmeProxyService
        with app.app_context():
            svc = AcmeProxyService('http://localhost/acme/proxy')
            svc.directory = {'newNonce': 'x', 'keyChange': 'https://ca.example/kc', 'meta': {}}
            assert 'keyChange' not in svc.get_directory()


class TestProviderCredentialsAndRedirects:
    def _capture(self, monkeypatch, response):
        seen = {}

        def _request(*args, **kwargs):
            seen.update(kwargs)
            return response
        monkeypatch.setattr('requests.request', _request)
        return seen

    def test_cloudflare_does_not_follow_redirects(self, monkeypatch):
        from services.acme.dns_providers import create_provider
        resp = SimpleNamespace(json=lambda: {'success': True, 'result': []}, status_code=200)
        seen = self._capture(monkeypatch, resp)
        create_provider('cloudflare', {'api_token': 't'})._request('GET', '/zones')
        assert seen['allow_redirects'] is False

    def test_ovh_does_not_follow_redirects(self, monkeypatch):
        from services.acme.dns_providers import create_provider
        resp = SimpleNamespace(status_code=200, text='', json=lambda: None, reason='OK')
        seen = self._capture(monkeypatch, resp)
        provider = create_provider('ovh', {'endpoint': 'ovh-eu', 'application_key': 'a',
                                           'application_secret': 'b', 'consumer_key': 'c'})
        monkeypatch.setattr(provider, '_get_time_delta', lambda: 0)
        provider._request('GET', '/domain/zone')
        assert seen['allow_redirects'] is False

    def test_cloudflare_refused_delete_is_reported(self, monkeypatch):
        from services.acme.dns_providers import create_provider
        provider = create_provider('cloudflare', {'api_token': 't'})
        monkeypatch.setattr(provider, '_get_zone_id', lambda _d: 'z1')
        answers = {'GET': (True, [{'id': 'r1', 'content': '"v"'}]), 'DELETE': (False, 'denied')}
        monkeypatch.setattr(provider, '_request', lambda method, *_a, **_k: answers[method])
        ok, message = provider.delete_txt_record('example.com', '_acme-challenge.example.com', 'v')
        assert not ok and 'denied' in message


class TestFinalizeHtmlError:
    def test_finalize_answered_by_an_html_page_reports_the_status(self, app):
        import json
        from cryptography.hazmat.primitives.asymmetric import ec
        from models import db
        from models.acme_models import AcmeClientOrder
        from services.acme.acme_client_service import AcmeClientService

        page = SimpleNamespace(status_code=503, headers={'Retry-After': '120'}, text='<html/>')
        page.json = MagicMock(side_effect=ValueError('Expecting value'))
        svc = object.__new__(AcmeClientService)
        svc.check_order_status = lambda _order: ('ready', {})
        svc._generate_cert_key = lambda _order: (ec.generate_private_key(ec.SECP256R1()), None)
        svc._build_csr_b64 = lambda *_args: 'csr'
        svc._post = lambda *_args: page
        with app.app_context():
            order = AcmeClientOrder(
                domains=json.dumps(['html503.example.com']), challenge_type='http-01',
                environment='staging', status='ready', order_url='https://ca.example/order/h503',
                finalize_url='https://ca.example/order/h503/finalize')
            db.session.add(order)
            db.session.commit()
            try:
                ok, message, _cert = svc.finalize_order(order)
                assert not ok
                assert 'HTTP 503' in message and 'Expecting value' not in message
            finally:
                db.session.rollback()
                db.session.delete(db.session.get(AcmeClientOrder, order.id))
                db.session.commit()


class TestTlsAlpnSubmissionError:
    def test_html_503_names_the_status(self):
        from services.acme.acme_client_service import AcmeClientService
        svc = AcmeClientService.__new__(AcmeClientService)
        resp = SimpleNamespace(status_code=503, headers={'Retry-After': '60'}, text='<html/>')
        resp.json = MagicMock(side_effect=ValueError('Expecting value'))
        svc._post = MagicMock(return_value=resp)
        svc._create_tls_alpn_listener = MagicMock()
        order = SimpleNamespace(challenges_dict={'a.example': {
            'url': 'https://ca.example/chall/1', 'key_authorization': 'k'}})
        ok, message = svc._verify_tls_alpn_challenge(order, 'a.example')
        assert not ok
        assert 'HTTP 503' in message and '60' in message


class TestHeaderCredentialProvidersDoNotFollowRedirects:
    """requests drops only Authorization on a cross-host redirect: API keys sent in
    other headers or in the body would follow it."""

    @pytest.mark.parametrize('provider_type, credentials, call', [
        ('bunny', {'api_key': 'k'}, lambda p: p._request('GET', '/dnszone')),
        ('dnsmadeeasy', {'api_key': 'k', 'secret_key': 's'},
         lambda p: p._request('GET', '/dns/managed')),
        ('ionos', {'public_prefix': 'p', 'api_key': 'k'}, lambda p: p._request('GET', '/zones')),
        ('ns1', {'api_key': 'k'}, lambda p: p._request('GET', '/zones')),
        ('scaleway', {'api_token': 't'}, lambda p: p._request('GET', '/dns-zones')),
        ('tencentcloud', {'secret_id': 'i', 'secret_key': 's'},
         lambda p: p._post('DescribeDomainList', {})),
        ('rackspace', {'username': 'u', 'api_key': 'k'}, lambda p: p._authenticate()),
        ('dynu', {'api_key': 'k'}, lambda p: p._request('GET', '/dns')),
        ('porkbun', {'api_key': 'k', 'secret_api_key': 's'}, lambda p: p._request('/ping')),
        ('netcup', {'customer_number': 'c', 'api_key': 'k', 'api_password': 'p'},
         lambda p: p._rpc_call('login', {})),
        ('cloudns', {'auth_id': 'i', 'auth_password': 'p'},
         lambda p: p._post('/dns/add-record.json', {})),
        ('inwx', {'username': 'u', 'password': 'p'}, lambda p: p._login()),
    ])
    def test_provider_does_not_follow_redirects(self, monkeypatch, provider_type,
                                                credentials, call):
        from services.acme.dns_providers import create_provider
        seen = []

        def _capture(*_args, **kwargs):
            seen.append(kwargs.get('allow_redirects', True))
            return SimpleNamespace(status_code=400, reason='Bad', text='{}', headers={},
                                   json=lambda: {}, content=b'{}', cookies=None)
        monkeypatch.setattr('requests.request', _capture)
        monkeypatch.setattr('requests.post', _capture)
        call(create_provider(provider_type, credentials))
        assert seen and all(value is False for value in seen)

    def test_rackspace_dns_call_does_not_follow_redirects(self, monkeypatch):
        from services.acme.dns_providers import create_provider
        seen = {}

        def _capture(*_args, **kwargs):
            seen.update(kwargs)
            return SimpleNamespace(status_code=400, reason='Bad', text='', json=lambda: {})
        monkeypatch.setattr('requests.request', _capture)
        provider = create_provider('rackspace', {'username': 'u', 'api_key': 'k'})
        provider._token, provider._dns_endpoint = 't', 'https://dns.example'
        provider._request('GET', '/domains')
        assert seen['allow_redirects'] is False
