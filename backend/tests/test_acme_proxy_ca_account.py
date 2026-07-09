"""Tests for ACME proxy upstream linked to AcmeClientAccount rows."""
import pytest
from models import db, AcmeClientAccount, SystemConfig
from services.acme.acme_proxy_account import resolve_proxy_account, PROXY_ACCOUNT_ID_KEY


@pytest.fixture
def clean_proxy_state(app):
    with app.app_context():
        AcmeClientAccount.query.delete()
        for key in (
            PROXY_ACCOUNT_ID_KEY,
            'acme.proxy.upstream_url',
            'acme.proxy.upstream_mode',
            'acme.proxy.account_key',
            'acme.proxy.account_url',
        ):
            SystemConfig.query.filter_by(key=key).delete()
        db.session.commit()
        yield
        AcmeClientAccount.query.delete()
        for key in (
            PROXY_ACCOUNT_ID_KEY,
            'acme.proxy.upstream_url',
            'acme.proxy.upstream_mode',
            'acme.proxy.account_key',
            'acme.proxy.account_url',
        ):
            SystemConfig.query.filter_by(key=key).delete()
        db.session.commit()


CUSTOM_DIR = 'https://acme-proxy-test.example/directory'


def _seed_account(**kwargs):
    defaults = dict(
        directory_url=CUSTOM_DIR,
        label="Test CA",
        email='ops@example.com',
        is_default=False,
    )
    defaults.update(kwargs)
    acct = AcmeClientAccount(**defaults)
    db.session.add(acct)
    db.session.commit()
    return acct


class TestResolveProxyAccount:
    def test_explicit_config_id(self, app, clean_proxy_state):
        with app.app_context():
            staging = _seed_account()
            prod = _seed_account(
                directory_url=AcmeClientAccount.LE_PRODUCTION_URL,
                label='LE Production',
            )
            db.session.add(SystemConfig(
                key=PROXY_ACCOUNT_ID_KEY,
                value=str(prod.id),
                description='test',
            ))
            db.session.commit()
            assert resolve_proxy_account().id == prod.id
            assert resolve_proxy_account(staging.id).id == staging.id

    def test_legacy_upstream_url_match(self, app, clean_proxy_state):
        with app.app_context():
            acct = _seed_account()
            db.session.add(SystemConfig(
                key='acme.proxy.upstream_url',
                value=CUSTOM_DIR,
                description='legacy',
            ))
            db.session.commit()
            assert resolve_proxy_account().id == acct.id

    def test_default_account_fallback(self, app, clean_proxy_state):
        with app.app_context():
            acct = _seed_account(is_default=True)
            assert resolve_proxy_account().id == acct.id


class TestProxySettingsApi:
    def test_get_settings_includes_proxy_acme_account_id(self, auth_client, app, clean_proxy_state):
        with app.app_context():
            acct = _seed_account()
            account_id = acct.id
            db.session.add(SystemConfig(
                key=PROXY_ACCOUNT_ID_KEY,
                value=str(account_id),
                description='test',
            ))
            db.session.commit()
        r = auth_client.get('/api/v2/acme/client/settings')
        from tests.conftest import assert_success
        data = assert_success(r)
        assert data['proxy_acme_account_id'] == account_id
        assert data['proxy_upstream_url'] == CUSTOM_DIR
        assert data['proxy_upstream_mode'] == 'custom'

    def test_patch_proxy_acme_account_id(self, auth_client, app, clean_proxy_state):
        with app.app_context():
            acct = _seed_account(
                directory_url=AcmeClientAccount.LE_PRODUCTION_URL,
                label='LE Production',
            )
            account_id = acct.id
        r = auth_client.patch(
            '/api/v2/acme/client/settings',
            json={'proxy_acme_account_id': account_id},
        )
        assert r.status_code == 200
        r2 = auth_client.get('/api/v2/acme/client/settings')
        data = r2.get_json()['data']
        assert data['proxy_acme_account_id'] == account_id
        assert data['proxy_upstream_mode'] == 'production'

    def test_patch_rejects_unknown_account(self, auth_client):
        r = auth_client.patch(
            '/api/v2/acme/client/settings',
            json={'proxy_acme_account_id': 99999},
        )
        assert r.status_code == 404


class TestProxyServiceBinding:
    def test_proxy_service_uses_linked_account_directory(self, app, clean_proxy_state):
        from services.acme.acme_proxy_service import AcmeProxyService

        with app.app_context():
            acct = _seed_account(
                directory_url=AcmeClientAccount.LE_PRODUCTION_URL,
                label='LE Production',
            )
            db.session.add(SystemConfig(
                key=PROXY_ACCOUNT_ID_KEY,
                value=str(acct.id),
                description='test',
            ))
            db.session.commit()
            svc = AcmeProxyService('https://ucm.example')
            assert svc.account.id == acct.id
            assert svc.upstream_directory_url == AcmeClientAccount.LE_PRODUCTION_URL

    def test_bg_thread_refreshes_detached_account(self, app, clean_proxy_state):
        """Regression: background DNS thread must re-bind ORM account before signing JWS."""
        from unittest.mock import MagicMock, patch
        from services.acme.acme_proxy_service import AcmeProxyService

        with app.app_context():
            acct = _seed_account()
            db.session.add(SystemConfig(
                key=PROXY_ACCOUNT_ID_KEY,
                value=str(acct.id),
                description='test',
            ))
            db.session.commit()

            svc = AcmeProxyService('https://ucm.example')
            db.session.expunge(svc.account)

            svc._refresh_account_session()
            assert svc.account.id == acct.id
            # Must not raise DetachedInstanceError when building JWS helpers
            assert svc._detect_key_algorithm() in ('ES256', 'RS256')

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = '{}'
            mock_resp.json.return_value = {'status': 'processing'}

            with patch.object(svc, '_post_with_account', return_value=mock_resp) as post_mock, \
                 patch('api.v2.acme_domains.find_provider_for_domain') as find_prov, \
                 patch('services.acme.dns_providers.create_provider') as create_prov, \
                 patch('services.acme.acme_proxy_service.wait_for_txt', return_value={'ok': True, 'missing': [], 'waited': 0}):
                from models import AcmeClientOrder
                order = AcmeClientOrder(
                    domains='["test.example.com"]',
                    environment='custom',
                    challenge_type='dns-01',
                    status='pending',
                    is_proxy_order=True,
                )
                db.session.add(order)
                db.session.commit()

                provider_model = MagicMock()
                provider_model.id = 1
                provider_model.provider_type = 'gandi'
                provider_model.credentials = '{}'
                find_prov.return_value = {'provider': provider_model}
                provider = MagicMock()
                provider.get_zone_for_domain.return_value = 'example.com'
                provider.get_acme_challenge_name.return_value = '_acme-challenge.test.example.com'
                create_prov.return_value = provider

                svc._bg_respond_challenge(
                    app,
                    'https://acme-proxy-test.example/chall/1',
                    'token.thumb',
                    'test.example.com',
                    order.id,
                )

            post_mock.assert_called_once()

    def test_bg_thread_skips_upstream_when_dns_not_ready(self, app, clean_proxy_state):
        """If DNS TXT is still missing after timeout, do not submit upstream."""
        from unittest.mock import MagicMock, patch
        from services.acme.acme_proxy_service import AcmeProxyService
        from models import AcmeClientOrder

        with app.app_context():
            acct = _seed_account()
            db.session.add(SystemConfig(
                key=PROXY_ACCOUNT_ID_KEY,
                value=str(acct.id),
                description='test',
            ))
            db.session.commit()

            svc = AcmeProxyService('https://ucm.example')

            order = AcmeClientOrder(
                domains='["test.example.com"]',
                environment='custom',
                challenge_type='dns-01',
                status='pending',
                is_proxy_order=True,
            )
            db.session.add(order)
            db.session.commit()

            with patch('api.v2.acme_domains.find_provider_for_domain') as find_prov, \
                 patch('services.acme.dns_providers.create_provider') as create_prov, \
                 patch('services.acme.acme_proxy_service.wait_for_txt', return_value={'ok': False, 'missing': ['_single_'], 'waited': 5}), \
                 patch.object(svc, '_post_with_account') as post_mock:
                provider_model = MagicMock()
                provider_model.id = 1
                provider_model.provider_type = 'gandi'
                provider_model.credentials = '{}'
                find_prov.return_value = {'provider': provider_model}
                provider = MagicMock()
                provider.get_zone_for_domain.return_value = 'example.com'
                provider.get_acme_challenge_name.return_value = '_acme-challenge.test.example.com'
                create_prov.return_value = provider

                svc._bg_respond_challenge(
                    app,
                    'https://acme-proxy-test.example/chall/2',
                    'token.thumb',
                    'test.example.com',
                    order.id,
                )

            post_mock.assert_not_called()
            db.session.refresh(order)
            entry = order.challenges_dict.get('https://acme-proxy-test.example/chall/2', {})
            assert entry.get('status') == 'dns_not_ready'


class TestProxyMultiPath:
    @pytest.fixture(autouse=True)
    def _stub_upstream(self, monkeypatch):
        fake_directory = {
            'newNonce': 'https://acme-stub.example/acme/new-nonce',
            'newAccount': 'https://acme-stub.example/acme/new-account',
            'newOrder': 'https://acme-stub.example/acme/new-order',
            'meta': {},
        }

        class _FakeResp:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return fake_directory

        monkeypatch.setattr(
            'services.acme.acme_proxy_service.requests.get',
            lambda *args, **kwargs: _FakeResp(),
        )

    def test_resolve_proxy_by_slug(self, app, clean_proxy_state):
        from services.acme.acme_proxy_account import resolve_proxy_by_slug

        with app.app_context():
            acct = _seed_account(label='Actalis Production')
            acct.proxy_slug = 'actalis'
            acct.proxy_enabled = True
            db.session.commit()
            resolved = resolve_proxy_by_slug('actalis')
            assert resolved.id == acct.id

    def test_directory_by_slug(self, client, app, clean_proxy_state):
        with app.app_context():
            acct = _seed_account(label='Actalis Production')
            acct.proxy_slug = 'actalis'
            acct.proxy_enabled = True
            db.session.commit()

        r = client.get('/acme/proxy/actalis/directory')
        assert r.status_code == 200
        data = r.get_json()
        assert data['newOrder'].endswith('/acme/proxy/actalis/new-order')

    def test_unknown_slug_returns_error(self, client):
        r = client.get('/acme/proxy/unknown-ca/directory')
        assert r.status_code == 500
        assert 'not configured' in r.get_json().get('detail', '').lower()

    def test_reserved_slug_rejected_on_update(self, auth_client, app, clean_proxy_state):
        with app.app_context():
            acct = _seed_account()
            db.session.commit()
            account_id = acct.id

        r = auth_client.patch(
            f'/api/v2/acme/client/accounts/{account_id}',
            json={'proxy_enabled': True, 'proxy_slug': 'directory'},
        )
        assert r.status_code == 400
