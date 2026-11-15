"""A stored secret this node cannot decrypt stops its integration; it never goes out without it.

Each case stores a token made under another database key (another node, or the
machine-derived key of the single instance a cluster came from).
"""
import smtplib
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from cryptography.fernet import Fernet

from utils.encryption import SecretUnreadable


def _foreign_token(value='a-secret-from-another-node'):
    return Fernet(Fernet.generate_key()).encrypt(value.encode()).decode()


@pytest.fixture
def sent(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(ok=True, status_code=200)

    monkeypatch.setattr('utils.ssrf_protection.safe_request_post', fake_post)
    return calls


def _endpoint(**fields):
    from services.webhook_service import WebhookEndpoint
    return WebhookEndpoint(id=1, name='wh', url='https://hooks.example/x', auth_type='none', **fields)


def test_webhook_with_an_unreadable_secret_is_not_sent_unsigned(app, sent):
    from services.webhook_service import WebhookService
    with app.app_context():
        ok, status, error = WebhookService._perform_delivery(
            _endpoint(secret=_foreign_token()), 'certificate.issued', '{}')
    assert sent == []
    assert ok is False and status is None
    assert 'webhook 1 secret' in error and 'cannot be decrypted' in error


def test_webhook_with_an_unreadable_auth_token_is_not_sent_without_it(app, sent):
    from services.webhook_service import WebhookService
    endpoint = _endpoint()
    endpoint.auth_type = 'bearer'
    endpoint._auth_token = _foreign_token()
    with app.app_context():
        ok, _, error = WebhookService._perform_delivery(endpoint, 'certificate.issued', '{}')
    assert sent == []
    assert ok is False and 'webhook 1 auth token' in error


def test_webhook_with_a_readable_secret_is_still_signed(app, sent):
    from services.webhook_service import WebhookService
    from utils.encryption import encrypt_value
    with app.app_context():
        ok, _, _ = WebhookService._perform_delivery(
            _endpoint(secret=encrypt_value('s' * 32)), 'certificate.issued', '{}')
    assert ok is True and sent[0]['headers']['X-UCM-Signature'].startswith('sha256=')


def test_smtp_with_an_unreadable_password_never_sends_unauthenticated(app):
    from models.email_notification import SMTPConfig
    from services.email_service import _smtp_authenticate
    config = SMTPConfig(smtp_host='mail.example', smtp_user='ucm', smtp_auth_method='password')
    config._smtp_password = _foreign_token()
    server = MagicMock(spec=smtplib.SMTP)
    with app.app_context(), pytest.raises(SecretUnreadable, match='SMTP password'):
        _smtp_authenticate(server, config)
    server.login.assert_not_called()


def test_msca_basic_auth_with_an_unreadable_password_sends_nothing(app):
    from models.msca import MicrosoftCA
    from services.msca.connection import MicrosoftCAConnectionMixin
    msca = MicrosoftCA(id=3, name='adcs', server='ca.example', auth_method='basic',
                       username='svc', verify_ssl=True)
    msca._password = _foreign_token()
    with app.app_context(), pytest.raises(SecretUnreadable, match='Microsoft CA 3 password'):
        MicrosoftCAConnectionMixin._get_client(msca)


def test_msca_certificate_auth_with_an_unreadable_key_sends_nothing(app):
    from models.msca import MicrosoftCA
    from services.msca.connection import MicrosoftCAConnectionMixin
    msca = MicrosoftCA(id=4, name='adcs', server='ca.example', auth_method='certificate',
                       client_cert_pem='-----BEGIN CERTIFICATE-----', verify_ssl=True)
    msca._client_key_pem = _foreign_token()
    with app.app_context(), pytest.raises(SecretUnreadable, match='Microsoft CA 4 client key'):
        MicrosoftCAConnectionMixin._get_client(msca)


def test_oauth2_login_with_an_unreadable_client_secret_is_not_attempted(app, monkeypatch):
    from api.v2.sso import login_routes
    from models import db
    from models.sso import SSOProvider

    posted = []
    monkeypatch.setattr(login_routes, 'safe_request_post', lambda *a, **k: posted.append(k))
    with app.app_context():
        others = [(p.id, p.enabled) for p in SSOProvider.query.filter_by(provider_type='oauth2').all()]
        for pid, _ in others:
            db.session.get(SSOProvider, pid).enabled = False
        row = SSOProvider(
            name=f'unreadable-{uuid.uuid4().hex[:6]}', provider_type='oauth2', enabled=True,
            oauth2_client_id='ucm-client', oauth2_auth_url='https://idp.example/authorize',
            oauth2_token_url='https://idp.example/token',
            oauth2_userinfo_url='https://idp.example/userinfo', default_role='viewer')
        row._oauth2_client_secret = _foreign_token()
        db.session.add(row)
        db.session.commit()
        pid = row.id
    try:
        client = app.test_client()
        with client.session_transaction() as s:
            s['sso_state'] = 'st'
            s['sso_pkce_verifier'] = 'v'
        r = client.get('/api/v2/sso/callback/oauth2?state=st&code=c')
        assert r.status_code == 302
        assert 'error=token_exchange_failed' in r.headers['Location']
        assert posted == []
    finally:
        with app.app_context():
            db.session.delete(db.session.get(SSOProvider, pid))
            for opid, enabled in others:
                db.session.get(SSOProvider, opid).enabled = enabled
            db.session.commit()


def _gcp_row(provider_id, service_account_json):
    import json
    from models.hsm import HsmProvider
    return HsmProvider(id=provider_id, name='kms', type='google-kms', config=json.dumps({
        'project_id': 'p', 'key_ring': 'r', 'service_account_json': service_account_json}))


def test_gcp_kms_with_an_unreadable_service_account_never_falls_back_to_default_credentials(
        app, monkeypatch):
    from services.hsm import HsmService
    from services.hsm import gcp_provider
    from services.hsm.base_provider import HsmConfigError
    built = []
    monkeypatch.setattr(gcp_provider.kms_v1, 'KeyManagementServiceClient',
                        lambda *a, **k: built.append(k) or MagicMock())
    with app.app_context(), pytest.raises(
            HsmConfigError, match='HSM provider 7 service_account_json cannot be decrypted'):
        HsmService._get_provider_instance(_gcp_row(7, _foreign_token('{"type": "service_account"}'))).connect()
    assert built == []


def test_hsm_connection_test_with_an_unreadable_secret_names_the_field(app, monkeypatch):
    from models import db
    from services.hsm import HsmService, gcp_provider
    built = []
    monkeypatch.setattr(gcp_provider.kms_v1, 'KeyManagementServiceClient',
                        lambda *a, **k: built.append(k) or MagicMock())
    with app.app_context():
        row = _gcp_row(None, _foreign_token('{"type": "service_account"}'))
        row.name = f'kms-{uuid.uuid4().hex[:6]}'
        db.session.add(row)
        db.session.commit()
        try:
            result = HsmService.test_provider(row.id)
            assert result['success'] is False
            assert f'HSM provider {row.id} service_account_json' in result['message']
            assert built == []
        finally:
            db.session.delete(row)
            db.session.commit()


def test_hsm_provider_with_a_readable_secret_still_gets_it(app):
    from services.hsm import HsmService
    from utils.encryption import encrypt_value
    with app.app_context():
        hsm = HsmService._get_provider_instance(_gcp_row(8, encrypt_value('{"a": 1}')))
    assert hsm.service_account_json == '{"a": 1}'


def test_hsm_provider_listing_stays_readable_with_an_unreadable_secret(app):
    with app.app_context():
        row = _gcp_row(9, _foreign_token())
        assert row.get_config()['service_account_json'] is None
        assert row.to_dict()['type'] == 'google-kms'


def _never(built, name):
    return lambda *a, **k: built.append(name) or MagicMock()


@pytest.mark.parametrize('ptype,config,field,entry_points', [
    ('pkcs11', {'module_path': '/usr/lib/softhsm/libsofthsm2.so', 'token_label': 't'},
     'user_pin', [('pkcs11_provider', 'cryptoki_library')]),
    ('aws-cloudhsm', {'module_path': '/opt/cloudhsm/lib/libcloudhsm_pkcs11.so', 'token_label': 't',
                      'hsm_user': 'cu'}, 'hsm_password', [('pkcs11_provider', 'cryptoki_library')]),
    ('openbao', {'url': 'http://bao.invalid:8200'}, 'token', [('openbao_provider', 'requests.Session')]),
    ('azure-keyvault', {'vault_url': 'https://v.vault.azure.net/', 'tenant_id': 't', 'client_id': 'c'},
     'client_secret', [('azure_provider', 'ClientSecretCredential'), ('azure_provider', 'KeyClient')]),
])
def test_each_provider_type_with_an_unreadable_secret_builds_no_client(
        app, monkeypatch, ptype, config, field, entry_points):
    import importlib
    import json
    from models.hsm import HsmProvider
    from services.hsm import HsmService
    from services.hsm.base_provider import HsmConfigError
    built = []
    for module, attr in entry_points:
        mod = importlib.import_module(f'services.hsm.{module}')
        target = mod
        *path, leaf = attr.split('.')
        for part in path:
            target = getattr(target, part)
        if not hasattr(target, leaf):
            pytest.skip(f'{module} client library not installed')
        monkeypatch.setattr(target, leaf, _never(built, attr))
    row = HsmProvider(id=11, name='p', type=ptype,
                      config=json.dumps({**config, field: _foreign_token()}))
    with app.app_context(), pytest.raises(
            HsmConfigError, match=f'HSM provider 11 {field} cannot be decrypted'):
        HsmService._get_provider_instance(row).connect()
    assert built == []
