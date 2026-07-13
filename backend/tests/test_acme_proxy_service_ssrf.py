"""SSRF hardening for ACME proxy upstream URLs from directory JSON."""
import pytest

from models import db, AcmeClientAccount
from services.acme.acme_proxy_service import AcmeProxyService


@pytest.fixture
def proxy_svc(app):
    with app.app_context():
        AcmeClientAccount.query.delete()
        db.session.commit()
        acct = AcmeClientAccount(
            directory_url='https://acme.example/directory',
            label='Proxy SSRF test',
            email='proxy-ssrf@example.com',
        )
        db.session.add(acct)
        db.session.commit()
        yield AcmeProxyService(base_url='https://ucm.example/acme/proxy', account_id=acct.id)
        AcmeClientAccount.query.delete()
        db.session.commit()


class TestAcmeProxyUpstreamSsrf:
    def test_get_nonce_rejects_loopback_new_nonce_url(self, proxy_svc):
        proxy_svc.directory = {
            'newNonce': 'https://127.0.0.1/new-nonce',
        }
        with pytest.raises(ValueError, match='loopback'):
            proxy_svc._get_nonce()

    def test_sign_and_post_rejects_cloud_metadata_url(self, proxy_svc, monkeypatch):
        proxy_svc._account_jwk = {'kty': 'RSA', 'n': 'x', 'e': 'AQAB'}
        proxy_svc._key_loaded = True
        monkeypatch.setattr(proxy_svc, '_detect_key_algorithm', lambda: 'RS256')
        monkeypatch.setattr(proxy_svc, '_sign_data', lambda _data: b'\x00' * 32)
        with pytest.raises(ValueError, match='metadata'):
            proxy_svc._sign_and_post(
                'https://169.254.169.254/latest/meta-data/',
                {},
                'nonce-1',
                kid='https://acme.example/acct/1',
            )

    def test_get_nonce_uses_pinned_safe_request_head(self, proxy_svc, monkeypatch):
        proxy_svc.directory = {
            'newNonce': 'https://93.184.216.34/new-nonce',
        }
        called = {}

        class _Resp:
            headers = {'Replay-Nonce': 'nonce-xyz'}

        def fake_head(url, **kwargs):
            called['url'] = url
            called['kwargs'] = kwargs
            return _Resp()

        monkeypatch.setattr('utils.ssrf_protection.safe_request_head', fake_head)
        assert proxy_svc._get_nonce() == 'nonce-xyz'
        assert called['url'] == 'https://93.184.216.34/new-nonce'
        assert called['kwargs'].get('verify') is proxy_svc.verify_ssl

    def test_sign_and_post_uses_pinned_safe_request_post(self, proxy_svc, monkeypatch):
        proxy_svc._account_jwk = {'kty': 'RSA', 'n': 'x', 'e': 'AQAB'}
        proxy_svc._key_loaded = True
        called = {}

        class _Resp:
            status_code = 200

        def fake_post(url, **kwargs):
            called['url'] = url
            called['kwargs'] = kwargs
            return _Resp()

        monkeypatch.setattr('utils.ssrf_protection.safe_request_post', fake_post)
        monkeypatch.setattr(proxy_svc, '_detect_key_algorithm', lambda: 'RS256')
        monkeypatch.setattr(proxy_svc, '_sign_data', lambda _data: b'\x00' * 32)

        proxy_svc._sign_and_post(
            'https://93.184.216.34/cert/1',
            '',
            'nonce-1',
            kid='https://acme.example/acct/1',
        )
        assert called['url'] == 'https://93.184.216.34/cert/1'
        assert called['kwargs']['json']['protected']
        assert called['kwargs'].get('verify') is proxy_svc.verify_ssl

    def test_ensure_directory_uses_pinned_safe_request_get(self, proxy_svc, monkeypatch):
        called = {}

        class _Resp:
            @staticmethod
            def raise_for_status():
                return None

            @staticmethod
            def json():
                return {'newNonce': 'https://93.184.216.34/new-nonce'}

        def fake_get(url, **kwargs):
            called['url'] = url
            called['kwargs'] = kwargs
            return _Resp()

        monkeypatch.setattr('utils.ssrf_protection.safe_request_get', fake_get)
        proxy_svc._ensure_directory()
        assert proxy_svc.directory['newNonce'] == 'https://93.184.216.34/new-nonce'
        assert called['url'] == proxy_svc.upstream_directory_url
        assert called['kwargs'].get('verify') is proxy_svc.verify_ssl
