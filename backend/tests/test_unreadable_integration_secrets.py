"""A stored secret this node cannot decrypt stops its integration; it never goes out without it.

Each case stores a token made under another database key (another node, or the
machine-derived key of the single instance a cluster came from).
"""
import logging
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


def _stored(row):
    import json
    return json.loads(row.config)


def test_repairing_legacy_pkcs11_keys_keeps_a_pin_this_node_cannot_open(app):
    import json
    from models.hsm import HsmProvider
    from services.hsm import HsmService
    token = _foreign_token('1234')
    row = HsmProvider(id=12, name='legacy', type='pkcs11', config=json.dumps({
        'library_path': '/usr/lib/softhsm/libsofthsm2.so', 'token_label': 't', 'pin': token}))
    with app.app_context():
        assert HsmService.repair_pkcs11_provider_config(row) is True
    assert _stored(row)['user_pin'] == token and 'pin' not in _stored(row)


def test_a_masked_field_keeps_a_secret_this_node_cannot_open(app):
    import json
    from models.hsm import HsmProvider
    token = _foreign_token()
    row = HsmProvider(id=13, name='bao', type='openbao', config=json.dumps({
        'url': 'http://bao.invalid:8200', 'token': token}))
    with app.app_context():
        row.set_config({'url': 'http://bao.invalid:8200', 'token': '********', 'mount_path': 'm'})
    assert _stored(row)['token'] == token


def test_an_edit_keeps_a_previous_pin_this_node_cannot_open(app):
    import json
    from models import db
    from models.hsm import HsmProvider
    from services.hsm import HsmService
    from utils.encryption import encrypt_value
    old = _foreign_token('0000')
    with app.app_context():
        row = HsmProvider(name=f'pin-{uuid.uuid4().hex[:6]}', type='pkcs11', config=json.dumps({
            'module_path': '/usr/lib/x.so', 'token_label': 't',
            'user_pin': encrypt_value('1234'), 'previous_user_pin': old}))
        db.session.add(row)
        db.session.commit()
        try:
            HsmService.update_provider(row.id, config={
                'module_path': '/usr/lib/x.so', 'token_label': 't', 'user_pin': '********'})
            assert _stored(db.session.get(HsmProvider, row.id))['previous_user_pin'] == old
        finally:
            db.session.delete(db.session.get(HsmProvider, row.id))
            db.session.commit()


@pytest.fixture
def ca_on_unreadable_provider(app):
    """An HSM-backed CA whose provider token was saved under another database key."""
    import base64
    import json
    from datetime import datetime, timedelta, timezone
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    from models import db, CA, Certificate
    from models.hsm import HsmProvider, HsmKey
    tag = uuid.uuid4().hex[:6]
    key = rsa.generate_private_key(65537, 2048)
    now = datetime.now(timezone.utc)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f'Unreadable HSM CA {tag}')])
    ca_cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
               .public_key(key.public_key()).serial_number(x509.random_serial_number())
               .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=365))
               .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
               .sign(key, hashes.SHA256()))
    leaf = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f'leaf-{tag}')]))
            .issuer_name(name).public_key(rsa.generate_private_key(65537, 2048).public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=30)).sign(key, hashes.SHA256()))
    pem = lambda c: base64.b64encode(c.public_bytes(serialization.Encoding.PEM)).decode()
    with app.app_context():
        provider = HsmProvider(name=f'bao-{tag}', type='openbao', config=json.dumps(
            {'url': 'http://bao.invalid:8200', 'token': _foreign_token()}))
        db.session.add(provider)
        db.session.commit()
        hsm_key = HsmKey(provider_id=provider.id, key_identifier=f'k-{tag}', label=f'k-{tag}',
                         algorithm='RSA-2048', key_type='asymmetric', purpose='signing',
                         public_key_pem=key.public_key().public_bytes(
                             serialization.Encoding.PEM,
                             serialization.PublicFormat.SubjectPublicKeyInfo).decode())
        db.session.add(hsm_key)
        db.session.commit()
        ca = CA(refid=f'unreadable-{tag}', descr=f'Unreadable HSM CA {tag}', serial=0, prv=None,
                hsm_key_id=hsm_key.id, crt=pem(ca_cert), subject=name.rfc4514_string(),
                issuer=name.rfc4514_string(), ocsp_enabled=True)
        db.session.add(ca)
        db.session.commit()
        db.session.add(Certificate(refid=f'leaf-{tag}', descr='leaf', caref=ca.refid, crt=pem(leaf),
                                   serial_number=str(leaf.serial_number),
                                   subject=leaf.subject.rfc4514_string(), issuer=name.rfc4514_string()))
        db.session.commit()
        ids = {'ca': ca.id, 'refid': ca.refid, 'key': hsm_key.id, 'provider': provider.id}
    yield ids, ca_cert, leaf
    with app.app_context():
        Certificate.query.filter_by(caref=ids['refid']).delete()
        CA.query.filter_by(id=ids['ca']).delete()
        HsmKey.query.filter_by(id=ids['key']).delete()
        HsmProvider.query.filter_by(id=ids['provider']).delete()
        db.session.commit()


def _route_errors(caplog, logger_name):
    return [r.getMessage() for r in caplog.records
            if r.name == logger_name and r.levelno == logging.ERROR]


def test_issuance_from_a_ca_on_an_unreadable_provider_names_the_secret(
        auth_client, ca_on_unreadable_provider, caplog):
    import json
    ids, _, _ = ca_on_unreadable_provider
    caplog.set_level(logging.ERROR)
    r = auth_client.post('/api/v2/certificates', data=json.dumps(
        {'cn': 'unreadable.example.test', 'ca_id': ids['ca'], 'validity_days': 30}),
        content_type='application/json')
    assert r.status_code == 500
    named = f"HSM provider {ids['provider']} token cannot be decrypted"
    assert named in r.get_json()['message']
    # Logged like every other failure of the route
    assert any(named in m for m in _route_errors(caplog, 'api.v2.certificates.cert_create'))


def test_crl_of_a_ca_on_an_unreadable_provider_names_the_secret(auth_client, ca_on_unreadable_provider,
                                                              caplog):
    ids, _, _ = ca_on_unreadable_provider
    caplog.set_level(logging.ERROR)
    r = auth_client.post(f"/api/v2/crl/{ids['ca']}/regenerate")
    assert r.status_code == 500
    named = f"HSM provider {ids['provider']} token cannot be decrypted"
    assert named in r.get_json()['message']
    assert any(named in m for m in _route_errors(caplog, 'api.v2.crl'))


def test_ocsp_of_a_ca_on_an_unreadable_provider_answers_internal_error(
        auth_client, ca_on_unreadable_provider):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.x509 import ocsp
    _, ca_cert, leaf = ca_on_unreadable_provider
    request = ocsp.OCSPRequestBuilder().add_certificate(leaf, ca_cert, hashes.SHA1()).build()
    r = auth_client.post('/ocsp', data=request.public_bytes(serialization.Encoding.DER),
                         content_type='application/ocsp-request')
    assert r.status_code == 200
    assert ocsp.load_der_ocsp_response(r.data).response_status == ocsp.OCSPResponseStatus.INTERNAL_ERROR


def test_a_kept_unreadable_secret_never_leaves_as_cleartext(auth_client, app, caplog):
    """editable_config keeps a foreign token as is: never exposed, never re-wrapped as a value."""
    import json
    from models import db
    from models.hsm import HsmProvider
    from models.audit_log import AuditLog
    from services.backup.key_material import decrypt_stored_fields
    from services.backup.manifest import SECTIONS
    from services.backup.restore.apply import _secret_as_stored
    token = _foreign_token('0000')
    with app.app_context():
        row = HsmProvider(name=f'kept-{uuid.uuid4().hex[:6]}', type='openbao', config=json.dumps(
            {'url': 'http://bao.invalid:8200', 'mount_path': 'm', 'token': token}))
        db.session.add(row)
        db.session.commit()
        pid = row.id
    try:
        r = auth_client.put(f'/api/v2/hsm/providers/{pid}', data=json.dumps({'config': {
            'url': 'http://bao.invalid:8200', 'token': '********', 'mount_path': 'm'}}),
            content_type='application/json')
        assert r.status_code == 200, r.get_data(as_text=True)
        assert token not in r.get_data(as_text=True)
        assert r.get_json()['data']['config']['token'] == '********'
        with app.app_context():
            row = db.session.get(HsmProvider, pid)
            assert json.loads(row.config)['token'] == token  # stored once, not wrapped again
            assert token not in json.dumps(row.to_dict(include_config=True))
            assert all(token not in (a.details or '') for a in AuditLog.query.all())
            archived = decrypt_stored_fields(row.config, label='hsm')
            assert json.loads(archived)['token'] == token
            restored = HsmProvider(name='r', type='openbao')
            restored.config = _secret_as_stored(SECTIONS['hsm_providers'], 'config', archived)
            assert 'token' not in json.loads(restored.config)
        assert token not in caplog.text
    finally:
        with app.app_context():
            db.session.delete(db.session.get(HsmProvider, pid))
            db.session.commit()


@pytest.fixture
def ldap_binds(monkeypatch):
    import ldap3
    calls = []

    def connection(*args, **kwargs):
        calls.append(kwargs)
        raise AssertionError('no bind may be attempted')

    monkeypatch.setattr(ldap3, 'Connection', connection)
    return calls


def _ldap_provider():
    from models.sso import SSOProvider
    row = SSOProvider(id=21, name='ldap', provider_type='ldap', ldap_server='ldap.invalid',
                      ldap_port=389, ldap_use_ssl=False, ldap_bind_dn='cn=svc,dc=example',
                      ldap_base_dn='dc=example', ldap_user_filter='(uid={username})')
    row._ldap_bind_password = _foreign_token()
    return row


def test_ldap_login_with_an_unreadable_bind_password_binds_nothing(app, ldap_binds, caplog):
    # ldap3 binds anonymously when the password is missing: no bind at all instead
    from api.v2.sso.connection_tests import _ldap_authenticate_user
    with app.app_context():
        user, error = _ldap_authenticate_user(_ldap_provider(), 'alice', 'pw')
    assert user is None and error == 'LDAP authentication failed'
    assert ldap_binds == []
    assert 'SSO provider 21 LDAP bind password cannot be decrypted' in caplog.text


def test_ldap_connection_test_with_an_unreadable_bind_password_names_it(app, ldap_binds):
    from api.v2.sso.connection_tests import _test_ldap_connection
    with app.test_request_context():
        response = _test_ldap_connection(_ldap_provider())
    response = response[0] if isinstance(response, tuple) else response
    assert ldap_binds == []
    assert 'SSO provider 21 LDAP bind password cannot be decrypted' in response.get_json()['message']


def test_ad_connector_with_an_unreadable_bind_password_binds_nothing(app, ldap_binds):
    from models.ad_connector import ADConnectorConfig
    from services.ad_connector import lookup
    config = ADConnectorConfig(id=22, name='ad', server='dc.invalid', port=389, use_ssl=False,
                         verify_ssl=True, base_dn='dc=example', bind_dn='cn=svc,dc=example')
    config._bind_password = _foreign_token()
    with app.app_context():
        with pytest.raises(ValueError, match='AD connector 22 bind password cannot be decrypted'):
            lookup._connect(config)
        with pytest.raises(SecretUnreadable, match='AD connector 22 bind password'):
            lookup._connect_to(config, 'dc.invalid', None)
    assert ldap_binds == []


def test_intune_with_an_unreadable_client_secret_names_it(app):
    from models.scep import IntuneApp, ScepProfile
    from services.scep import intune_client
    profile = ScepProfile(name='p', intune_enabled=True)
    profile.intune_app = IntuneApp(id=23, name='entra', tenant_id='t', client_id='c',
                                   client_secret=_foreign_token())
    with app.app_context(), pytest.raises(SecretUnreadable, match='Intune app 23 client secret'):
        intune_client.client_for_profile(profile)


def _ad_config_with_unreadable_password():
    from models.ad_connector import ADConnectorConfig
    config = ADConnectorConfig(id=24, name='ad', server='dc.invalid', port=389, use_ssl=False,
                               verify_ssl=True, base_dn='dc=example', bind_dn='cn=svc,dc=example')
    config._bind_password = _foreign_token()
    return config


def test_ad_connector_test_names_an_unreadable_bind_password(app, ldap_binds):
    from services.ad_connector import lookup
    with app.app_context():
        result = lookup.test_connection(_ad_config_with_unreadable_password())
    assert result['success'] is False
    assert 'AD connector 24 bind password cannot be decrypted' in result['message']
    assert ldap_binds == []


def test_ad_connector_inline_test_with_a_blank_password_names_the_saved_one(app, ldap_binds):
    from api.v2.ad_connector import run_unsaved_test
    with app.test_request_context():
        response = run_unsaved_test({'server': 'dc.invalid', 'port': 389, 'bind_dn': 'cn=svc,dc=example',
                                     'bind_password': ''}, _ad_config_with_unreadable_password())
    response, status = response if isinstance(response, tuple) else (response, response.status_code)
    assert status == 400
    assert 'AD connector 24 bind password cannot be decrypted' in response.get_json()['message']
    assert ldap_binds == []


@pytest.mark.parametrize('route,body', [
    ('/api/v2/scep/intune-apps/test', lambda app_id: {'app_id': app_id}),
    ('/api/v2/scep/profiles/test-intune-connection', lambda app_id: {'intune_app_id': app_id}),
], ids=['app', 'pre-092'])
def test_intune_test_names_an_unreadable_saved_secret(app, auth_client, monkeypatch, route, body):
    from api.v2 import scep as scep_api
    from models import db
    from models.scep import IntuneApp
    tried = []
    monkeypatch.setattr(scep_api, '_test_intune_credentials', lambda *a: tried.append(a))
    token = _foreign_token('the-intune-secret')
    with app.app_context():
        row = IntuneApp(name=f'unreadable-{uuid.uuid4().hex[:6]}', tenant_id='t.example',
                        client_id=f'c-{uuid.uuid4().hex[:6]}', client_secret=token)
        db.session.add(row)
        db.session.commit()
        app_id = row.id
    try:
        r = auth_client.post(route, json=body(app_id))
        assert r.status_code == 400
        text = r.get_data(as_text=True)
        assert f'Intune app {app_id} client secret cannot be decrypted' in text
        assert token not in text and 'the-intune-secret' not in text
        assert tried == []
    finally:
        with app.app_context():
            db.session.delete(db.session.get(IntuneApp, app_id))
            db.session.commit()


UNREADABLE_AD = 'AD connector 24 bind password cannot be decrypted'


def test_ad_health_probe_names_an_unreadable_bind_password(app, ldap_binds, caplog):
    from services.ad_connector import health
    config = _ad_config_with_unreadable_password()
    config.enabled = True
    with app.app_context(), caplog.at_level(logging.WARNING):
        assert health.probe(config) is None
        outcome = health._probe_one(config)
    assert outcome['status'] == 'skipped' and UNREADABLE_AD in outcome['reason']
    assert UNREADABLE_AD in caplog.text and 'credentials missing' not in caplog.text
    assert ldap_binds == []


def test_ad_domain_sid_read_names_an_unreadable_bind_password(app, ldap_binds, caplog):
    from services.ad_connector import lookup
    with app.app_context(), caplog.at_level(logging.WARNING):
        assert lookup.fetch_domain_sid(_ad_config_with_unreadable_password()) is None
    assert UNREADABLE_AD in caplog.text
    assert ldap_binds == []


@pytest.mark.parametrize('data,refused', [
    ({'base_dn': 'DC=corp,DC=example'}, True),
    ({'enabled': True}, True),
    ({'bind_password': 'typed-again'}, False),
    ({'enabled': False}, False),
], ids=['other-field', 'enable', 'password-typed', 'disable'])
def test_an_enabled_ad_connector_with_an_unreadable_password_saves_only_a_new_one(
        app, data, refused):
    from api.v2.ad_connector import apply_fields
    config = _ad_config_with_unreadable_password()
    config.enabled = True
    token = config._bind_password
    with app.test_request_context():
        err = apply_fields(config, data)
    if refused:
        response, status = err if isinstance(err, tuple) else (err, err.status_code)
        assert status == 400
        assert UNREADABLE_AD in response.get_json()['message']
        assert token not in response.get_data(as_text=True)
    else:
        assert err is None


@pytest.fixture
def unreadable_rfc2136(app):
    """An RFC 2136 provider whose credentials this node's key does not open."""
    from models import db, DnsProvider
    token = _foreign_token('{"server": "ns1.example", "tsig_key_name": "k.", '
                           '"tsig_key_secret": "c2VjcmV0LXNlY3JldC1zZWNyZXQ="}')
    with app.app_context():
        row = DnsProvider(name=f'dns-{uuid.uuid4().hex[:6]}', provider_type='rfc2136')
        row._credentials = token
        db.session.add(row)
        db.session.commit()
        pid = row.id
    yield pid, token
    with app.app_context():
        db.session.delete(db.session.get(DnsProvider, pid))
        db.session.commit()


def _stored_credentials(app, pid):
    from models import db, DnsProvider
    with app.app_context():
        return db.session.get(DnsProvider, pid)._credentials


@pytest.mark.parametrize('credentials', [
    {'server': 'ns2.example'},
    {'tsig_key_secret': ''},
    {'server': 'ns1.example', 'tsig_key_name': 'k.', 'tsig_key_secret': ''},
], ids=['moved', 'blank', 'all-but-the-secret'])
def test_dns_credentials_this_node_cannot_open_are_kept_until_entered_again(
        app, auth_client, unreadable_rfc2136, credentials):
    pid, token = unreadable_rfc2136
    r = auth_client.patch(f'/api/v2/dns-providers/{pid}', json={'credentials': credentials})
    assert r.status_code == 400
    assert f'DNS provider {pid} credentials cannot be decrypted' in r.get_json()['message']
    assert token not in r.get_data(as_text=True)
    assert _stored_credentials(app, pid) == token


def test_dns_credentials_this_node_cannot_open_are_replaced_by_a_full_entry(
        app, auth_client, unreadable_rfc2136):
    import json
    from utils.encryption import decrypt_value
    pid, token = unreadable_rfc2136
    entry = {'server': 'ns1.example', 'tsig_key_name': 'k.',
             'tsig_key_secret': 'bmV3LXNlY3JldC1uZXctc2VjcmV0'}
    r = auth_client.patch(f'/api/v2/dns-providers/{pid}', json={'credentials': entry})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert json.loads(decrypt_value(_stored_credentials(app, pid))) == entry


def test_dns_provider_rename_keeps_credentials_this_node_cannot_open(
        app, auth_client, unreadable_rfc2136):
    pid, token = unreadable_rfc2136
    r = auth_client.patch(f'/api/v2/dns-providers/{pid}',
                          json={'name': f'renamed-{uuid.uuid4().hex[:6]}'})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert _stored_credentials(app, pid) == token


def _unreadable_provider(app, provider_type):
    from models import db, DnsProvider
    token = _foreign_token('{"saved": "under-another-key"}')
    with app.app_context():
        row = DnsProvider(name=f'dns-{uuid.uuid4().hex[:6]}', provider_type=provider_type)
        row._credentials = token
        db.session.add(row)
        db.session.commit()
        return row.id, token


def _drop_provider(app, pid):
    from models import db, DnsProvider
    with app.app_context():
        db.session.delete(db.session.get(DnsProvider, pid))
        db.session.commit()


def _full_entry(provider_class):
    """Every required field, plus a secret when the schema declares one."""
    from api.v2.dns_providers import _secret_names
    schema = provider_class.get_credential_schema()
    secret = _secret_names(schema, {f['name'] for f in schema})
    wanted = set(provider_class.REQUIRED_CREDENTIALS)
    if secret and not wanted & secret:
        wanted.add(sorted(secret)[0])
    entry = {}
    for field in schema:
        name = field['name']
        if name not in wanted:
            continue
        if field.get('type') == 'select':
            entry[name] = field['options'][0]['value']
        elif field.get('type') == 'checkbox':
            entry[name] = True
        elif field.get('type') == 'number':
            entry[name] = field.get('default') or 30
        elif name in secret:
            entry[name] = 'bmV3LXNlY3JldC1uZXctc2VjcmV0'
        elif 'url' in name.lower():
            entry[name] = 'https://dns.example'
        else:
            entry[name] = 'ns1.example'
    return entry


@pytest.mark.parametrize('provider_type', sorted(
    __import__('services.acme.dns_providers', fromlist=['PROVIDER_REGISTRY']).PROVIDER_REGISTRY))
def test_every_dns_provider_with_unreadable_credentials_is_repaired_by_a_full_entry(
        app, auth_client, provider_type):
    import json
    from services.acme.dns_providers import get_provider_class
    from utils.encryption import decrypt_value
    entry = _full_entry(get_provider_class(provider_type))
    if not entry:
        pytest.skip('this provider has no credentials')
    pid, token = _unreadable_provider(app, provider_type)
    try:
        r = auth_client.patch(f'/api/v2/dns-providers/{pid}', json={'credentials': entry})
        assert r.status_code == 200, r.get_data(as_text=True)
        assert json.loads(decrypt_value(_stored_credentials(app, pid))) == entry
    finally:
        _drop_provider(app, pid)


def test_custom_command_credentials_this_node_cannot_open_need_every_required_field(
        app, auth_client):
    pid, token = _unreadable_provider(app, 'custom_command')
    try:
        r = auth_client.patch(f'/api/v2/dns-providers/{pid}',
                              json={'credentials': {'delete_command': '/bin/true'}})
        assert r.status_code == 400
        assert _stored_credentials(app, pid) == token
    finally:
        _drop_provider(app, pid)


def test_a_partial_dns_entry_over_unreadable_credentials_names_what_is_missing(
        app, auth_client, unreadable_rfc2136):
    pid, token = unreadable_rfc2136
    r = auth_client.patch(f'/api/v2/dns-providers/{pid}', json={
        'credentials': {'tsig_key_secret': 'bmV3LXNlY3JldC1uZXctc2VjcmV0'}})
    assert r.status_code == 400
    message = r.get_json()['message']
    assert 'missing: server, tsig_key_name' in message
    assert 'bmV3LXNlY3JldC1uZXctc2VjcmV0' not in message
    r = auth_client.patch(f'/api/v2/dns-providers/{pid}', json={
        'credentials': {'server': 'ns1.example', 'tsig_key_name': 'k.'}})
    assert r.get_json()['message'].endswith('missing: tsig_key_secret')
    assert _stored_credentials(app, pid) == token
