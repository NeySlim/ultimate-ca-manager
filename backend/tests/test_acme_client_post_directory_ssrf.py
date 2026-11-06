"""SSRF hardening for ACME client URLs taken from directory JSON (GHSA-5p92 follow-up)."""
import pytest
from tests.acme_rows import delete_client_accounts

from models import db, AcmeClientAccount
from services.acme.acme_client_service import AcmeClientService


@pytest.fixture
def acme_client_svc(app):
    with app.app_context():
        delete_client_accounts(AcmeClientAccount.query)
        db.session.commit()
        acct = AcmeClientAccount(
            directory_url='https://acme.example/directory',
            label='SSRF test CA',
            email='ssrf-test@example.com',
        )
        db.session.add(acct)
        db.session.commit()
        yield AcmeClientService(account=acct)
        delete_client_accounts(AcmeClientAccount.query)
        db.session.commit()


class TestAcmeClientPostDirectorySsrf:
    def test_get_nonce_rejects_loopback_new_nonce_url(self, acme_client_svc):
        acme_client_svc.directory = {
            'newNonce': 'https://127.0.0.1/new-nonce',
            'newAccount': 'https://acme.example/new-account',
        }
        with pytest.raises(ValueError, match='loopback'):
            acme_client_svc._get_nonce()

    def test_post_rejects_cloud_metadata_url(self, acme_client_svc):
        with pytest.raises(ValueError, match='metadata'):
            acme_client_svc._post(
                'https://169.254.169.254/latest/meta-data/',
                {'termsOfServiceAgreed': True},
                use_jwk=True,
            )

    def test_get_nonce_uses_pinned_safe_request_head(self, acme_client_svc, monkeypatch):
        acme_client_svc.directory = {
            'newNonce': 'https://93.184.216.34/new-nonce',
        }
        called = {}

        class _Resp:
            headers = {'Replay-Nonce': 'nonce-abc'}

            @staticmethod
            def raise_for_status():
                return None

        def fake_head(url, **kwargs):
            called['url'] = url
            called['kwargs'] = kwargs
            return _Resp()

        monkeypatch.setattr(
            'utils.ssrf_protection.safe_request_head',
            fake_head,
        )
        assert acme_client_svc._get_nonce() == 'nonce-abc'
        assert called['url'] == 'https://93.184.216.34/new-nonce'
        assert called['kwargs'].get('verify') is acme_client_svc.verify_ssl

    def test_post_uses_pinned_safe_request_post(self, acme_client_svc, monkeypatch):
        called = {}

        class _Resp:
            status_code = 200

        def fake_post(url, **kwargs):
            called['url'] = url
            called['kwargs'] = kwargs
            return _Resp()

        monkeypatch.setattr(
            'utils.ssrf_protection.safe_request_post',
            fake_post,
        )
        monkeypatch.setattr(
            acme_client_svc,
            '_sign_jws',
            lambda url, payload, use_jwk=False: {'protected': 'p', 'payload': '', 'signature': 's'},
        )
        acme_client_svc._post('https://93.184.216.34/new-account', {}, use_jwk=True)
        assert called['url'] == 'https://93.184.216.34/new-account'
        assert called['kwargs']['json']['protected'] == 'p'
        assert called['kwargs'].get('verify') is acme_client_svc.verify_ssl
