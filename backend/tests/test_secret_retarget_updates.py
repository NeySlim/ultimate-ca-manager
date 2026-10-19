"""Saving a configuration never moves its saved secret to a new target.

A blank or masked secret on update means "keep the saved one". Changing the
host, URL, port, TLS trust or account in the same request is refused until
the secret is typed again, and nothing is written.
"""
import json
import uuid

import pytest

from models import db

MESSAGE = 'Re-enter the secret to change the target'


def _send(client, method, url, body):
    return getattr(client, method)(url, data=json.dumps(body), content_type='application/json')


def _refused(r):
    assert r.status_code == 400, r.data
    assert MESSAGE in r.get_data(as_text=True)


def _suffix():
    return uuid.uuid4().hex[:8]


class TestSmtp:
    URL = '/api/v2/settings/email'

    @pytest.fixture
    def smtp(self, app):
        from models.email_notification import SMTPConfig
        with app.app_context():
            SMTPConfig.query.delete()
            row = SMTPConfig(smtp_host='smtp.corp.example', smtp_port=587, smtp_user='mailer',
                             smtp_use_tls=True, smtp_use_ssl=False, smtp_auth=True,
                             smtp_auth_method='password')
            row.smtp_password = 'saved-smtp'
            row.smtp_oauth_client_id = 'oauth-client'
            row.smtp_oauth_token_url = 'https://login.corp.example/token'
            row.smtp_oauth_client_secret = 'saved-oauth'
            row.smtp_oauth_refresh_token = 'saved-refresh'
            db.session.add(row)
            db.session.commit()
        yield
        with app.app_context():
            SMTPConfig.query.delete()
            db.session.commit()

    def _row(self, app):
        from models.email_notification import SMTPConfig
        with app.app_context():
            row = SMTPConfig.query.first()
            return (row.smtp_host, row.smtp_port, row.smtp_user, row.smtp_use_tls,
                    row.smtp_password, row.smtp_oauth_token_url, row.smtp_oauth_refresh_token,
                    row.smtp_from_name)

    @pytest.mark.parametrize('over', [
        {'smtp_host': 'smtp.attacker.example'},
        {'smtp_host': 'smtp.attacker.example', 'smtp_password': '********'},
        {'smtp_port': 2525},
        {'smtp_security': 'none'},
        {'smtp_username': 'other'},
        {'smtp_auth_method': 'oauth2', 'smtp_oauth_token_url': 'https://login.attacker.example/token'},
        {'smtp_auth_method': 'oauth2', 'smtp_oauth_client_id': 'other', 'smtp_password': 'typed'},
    ], ids=['host', 'host-masked', 'port', 'plaintext', 'account', 'token-url', 'oauth-client'])
    def test_moving_the_target_without_the_secret_is_refused(self, app, auth_client, smtp, over):
        before = self._row(app)
        _refused(_send(auth_client, 'patch', self.URL, dict(over, from_name='Changed')))
        assert self._row(app) == before

    def test_the_form_sent_back_unchanged_is_accepted(self, app, auth_client, smtp):
        r = _send(auth_client, 'patch', self.URL, {
            'smtp_host': 'smtp.corp.example', 'smtp_port': '587', 'smtp_username': 'mailer',
            'smtp_security': 'starttls', 'smtp_password': '********',
            'smtp_oauth_client_secret': '', 'from_name': 'Changed'})
        assert r.status_code == 200, r.data
        assert self._row(app)[4:] == ('saved-smtp', 'https://login.corp.example/token',
                                      'saved-refresh', 'Changed')

    def test_an_unused_secret_is_dropped_not_moved(self, app, auth_client, smtp):
        from models.email_notification import SMTPConfig
        r = _send(auth_client, 'patch', self.URL, {
            'smtp_oauth_token_url': 'https://login.new.example/token'})
        assert r.status_code == 200, r.data
        r = _send(auth_client, 'patch', self.URL, {'smtp_auth_method': 'none',
                                                   'smtp_host': 'smtp.new.example'})
        assert r.status_code == 200, r.data
        with app.app_context():
            row = SMTPConfig.query.first()
            assert (row.smtp_oauth_client_secret, row.smtp_oauth_refresh_token,
                    row.smtp_password) == (None, None, None)

    def test_turning_authentication_off_needs_no_secret(self, app, auth_client, smtp):
        r = _send(auth_client, 'patch', self.URL, {'smtp_auth_method': 'none', 'smtp_username': '',
                                                   'smtp_password': ''})
        assert r.status_code == 200, r.data
        _refused(_send(auth_client, 'patch', self.URL, {'smtp_auth_method': 'password',
                                                        'smtp_username': 'other'}))

    def test_a_typed_secret_moves_the_target(self, app, auth_client, smtp):
        r = _send(auth_client, 'patch', self.URL, {'smtp_host': 'smtp.new.example',
                                                   'smtp_password': 'typed'})
        assert r.status_code == 200, r.data
        # The refresh token cannot be re-entered: a new server needs a new consent
        assert (self._row(app)[0], self._row(app)[6]) == ('smtp.new.example', None)

    def test_a_moved_oauth_target_drops_the_refresh_token(self, app, auth_client, smtp):
        r = _send(auth_client, 'patch', self.URL, {
            'smtp_oauth_token_url': 'https://login.new.example/token',
            'smtp_oauth_client_secret': 'typed-oauth'})
        assert r.status_code == 200, r.data
        assert self._row(app)[5:7] == ('https://login.new.example/token', None)


class TestWebhook:
    @pytest.fixture
    def hook_id(self, auth_client):
        r = _send(auth_client, 'post', '/api/v2/webhooks', {
            'name': f'retarget-{_suffix()}', 'url': 'https://hooks.example.com/saved',
            'auth_type': 'bearer', 'auth_token': 'saved-token'})
        assert r.status_code == 201, r.data
        return json.loads(r.data)['data']['id']

    def _url(self, app, hook_id):
        from services.webhook_service import WebhookEndpoint
        with app.app_context():
            row = db.session.get(WebhookEndpoint, hook_id)
            return row.url, row.auth_token, row.name

    def test_moving_the_url_without_the_token_is_refused(self, app, auth_client, hook_id):
        before = self._url(app, hook_id)
        _refused(_send(auth_client, 'put', f'/api/v2/webhooks/{hook_id}',
                       {'url': 'https://hooks.attacker.example/x', 'name': 'renamed'}))
        assert self._url(app, hook_id) == before

    def test_same_url_or_typed_token_is_accepted(self, app, auth_client, hook_id):
        url = f'/api/v2/webhooks/{hook_id}'
        assert _send(auth_client, 'put', url, {'url': 'https://hooks.example.com/saved',
                                               'name': 'renamed'}).status_code == 200
        r = _send(auth_client, 'put', url, {'url': 'https://hooks.example.com/new',
                                            'auth_token': 'typed'})
        assert r.status_code == 200, r.data
        assert self._url(app, hook_id)[:2] == ('https://hooks.example.com/new', 'typed')

    def test_switching_authentication_off_clears_the_token(self, app, auth_client, hook_id):
        r = _send(auth_client, 'put', f'/api/v2/webhooks/{hook_id}',
                  {'url': 'https://hooks.example.com/other', 'auth_type': 'none'})
        assert r.status_code == 200, r.data
        assert self._url(app, hook_id)[:2] == ('https://hooks.example.com/other', None)

    def test_saved_custom_headers_stay_with_their_url(self, app, auth_client):
        r = _send(auth_client, 'post', '/api/v2/webhooks', {
            'name': f'retarget-h-{_suffix()}', 'url': 'https://hooks.example.com/h',
            'custom_headers': {'X-Api-Key': 'saved-header'}})
        hook_id = json.loads(r.data)['data']['id']
        url = f'/api/v2/webhooks/{hook_id}'
        _refused(_send(auth_client, 'put', url, {'url': 'https://hooks.attacker.example/h'}))
        assert _send(auth_client, 'put', url, {
            'url': 'https://hooks.example.com/h2',
            'custom_headers': {'X-Api-Key': 'typed-header'}}).status_code == 200
        assert json.loads(auth_client.get(url).data)['data']['custom_headers_set'] is True
        # Dropping them is the other way to move the URL
        assert _send(auth_client, 'put', url, {'url': 'https://hooks.example.com/h3',
                                               'custom_headers': {}}).status_code == 200
        assert json.loads(auth_client.get(url).data)['data']['custom_headers_set'] is False


class TestDnsProvider:
    @pytest.fixture
    def provider_id(self, app):
        from models import DnsProvider
        with app.app_context():
            row = DnsProvider(name=f'retarget-{_suffix()}', provider_type='powerdns',
                              credentials=json.dumps({'server_url': 'https://pdns.example.com',
                                                      'api_key': 'saved-key'}))
            db.session.add(row)
            db.session.commit()
            return row.id

    def _creds(self, app, provider_id):
        from models import DnsProvider
        with app.app_context():
            row = db.session.get(DnsProvider, provider_id)
            return row.name, json.loads(row.credentials)

    def test_moving_the_server_without_the_key_is_refused(self, app, auth_client, provider_id):
        before = self._creds(app, provider_id)
        _refused(_send(auth_client, 'patch', f'/api/v2/dns-providers/{provider_id}', {
            'name': 'renamed', 'credentials': {'server_url': 'https://pdns.attacker.example',
                                               'api_key': ''}}))
        assert self._creds(app, provider_id) == before

    def test_same_server_or_typed_key_is_accepted(self, app, auth_client, provider_id):
        url = f'/api/v2/dns-providers/{provider_id}'
        assert _send(auth_client, 'patch', url, {'credentials': {
            'server_url': 'https://pdns.example.com', 'api_key': ''}}).status_code == 200
        r = _send(auth_client, 'patch', url, {'credentials': {
            'server_url': 'https://pdns2.example.com', 'api_key': 'typed'}})
        assert r.status_code == 200, r.data
        assert self._creds(app, provider_id)[1] == {'server_url': 'https://pdns2.example.com',
                                                    'api_key': 'typed'}


def _drop_sso(app, provider_id):
    from models.sso import SSOProvider
    with app.app_context():
        db.session.delete(db.session.get(SSOProvider, provider_id))
        db.session.commit()


class TestSsoProvider:
    @pytest.fixture
    def oauth_id(self, app):
        from models.sso import SSOProvider
        with app.app_context():
            row = SSOProvider(name=f'retarget-oauth-{_suffix()}', provider_type='oauth2',
                              enabled=False, oauth2_client_id='client',
                              oauth2_token_url='https://idp.example.com/token')
            row.oauth2_client_secret = 'saved-oauth'
            db.session.add(row)
            db.session.commit()
            provider_id = row.id
        yield provider_id
        _drop_sso(app, provider_id)  # one provider per type

    @pytest.fixture
    def ldap_id(self, app):
        from models.sso import SSOProvider
        with app.app_context():
            row = SSOProvider(name=f'retarget-ldap-{_suffix()}', provider_type='ldap',
                              enabled=False, ldap_server='ldap.example.com', ldap_port=636,
                              ldap_use_ssl=True, ldap_bind_dn='cn=svc')
            row.ldap_bind_password = 'saved-bind'
            db.session.add(row)
            db.session.commit()
            provider_id = row.id
        yield provider_id
        _drop_sso(app, provider_id)  # one provider per type

    def _row(self, app, provider_id):
        from models.sso import SSOProvider
        with app.app_context():
            row = db.session.get(SSOProvider, provider_id)
            return (row.display_name, row.oauth2_token_url, row.oauth2_client_secret,
                    row.ldap_server, row.ldap_port, row.ldap_bind_password)

    @pytest.mark.parametrize('over', [
        {'oauth2_token_url': 'https://idp.attacker.example/token'},
        {'oauth2_token_url': 'https://idp.attacker.example/token', 'oauth2_client_secret': '***'},
        {'oauth2_client_id': 'other'},
        {'oauth2_verify_ssl': False},
    ], ids=['token-url', 'token-url-masked', 'client-id', 'no-verify'])
    def test_oauth2_target_needs_the_secret(self, app, auth_client, oauth_id, over):
        before = self._row(app, oauth_id)
        _refused(_send(auth_client, 'put', f'/api/v2/sso/providers/{oauth_id}',
                       dict(over, display_name='Changed')))
        assert self._row(app, oauth_id) == before

    def test_oauth2_masked_secret_is_kept_not_stored(self, app, auth_client, oauth_id):
        r = _send(auth_client, 'put', f'/api/v2/sso/providers/{oauth_id}', {
            'oauth2_token_url': 'https://idp.example.com/token', 'oauth2_client_secret': '***',
            'oauth2_ca_bundle': True, 'display_name': 'Changed'})
        assert r.status_code == 200, r.data
        assert self._row(app, oauth_id)[:3] == ('Changed', 'https://idp.example.com/token',
                                               'saved-oauth')

    @pytest.mark.parametrize('over', [
        {'ldap_server': 'ldap.attacker.example'},
        {'ldap_port': 389, 'ldap_bind_password': ''},
        {'ldap_bind_dn': 'cn=other'},
    ], ids=['server', 'port', 'bind-dn'])
    def test_ldap_target_needs_the_password(self, app, auth_client, ldap_id, over):
        before = self._row(app, ldap_id)
        _refused(_send(auth_client, 'put', f'/api/v2/sso/providers/{ldap_id}', over))
        assert self._row(app, ldap_id) == before

    def test_ldap_typed_password_moves_the_server(self, app, auth_client, ldap_id):
        r = _send(auth_client, 'put', f'/api/v2/sso/providers/{ldap_id}', {
            'ldap_server': 'ldap2.example.com', 'ldap_bind_password': 'typed'})
        assert r.status_code == 200, r.data
        assert self._row(app, ldap_id)[3:] == ('ldap2.example.com', 636, 'typed')


class TestMicrosoftCA:
    def _make(self, app, winrm_password):
        from models.msca import MicrosoftCA
        with app.app_context():
            row = MicrosoftCA(name=f'Retarget CA {_suffix()}', server='adcs.corp.example',
                              auth_method='basic', username='u', enabled=True)
            row.password = 'saved-basic'
            row.winrm_enabled, row.winrm_transport = True, 'ntlm'
            row.winrm_use_ssl, row.winrm_port = True, 5986
            if winrm_password:
                row.winrm_host = 'winrm.corp.example'
                row.winrm_password = winrm_password
            db.session.add(row)
            db.session.commit()
            return row.id

    def _row(self, app, msca_id):
        from models.msca import MicrosoftCA
        with app.app_context():
            row = db.session.get(MicrosoftCA, msca_id)
            return (row.server, row.username, row.password, row.winrm_host, row.winrm_port,
                    row.winrm_password, row.default_template)

    @pytest.mark.parametrize('over', [
        {'server': 'adcs.attacker.example'},
        {'server': 'adcs.attacker.example', 'password': '***'},
        {'username': 'other'},
        {'verify_ssl': False},
        {'winrm_host': 'winrm.attacker.example'},
        {'winrm_port': 5985},
    ], ids=['server', 'server-masked', 'account', 'no-verify', 'winrm-host', 'winrm-port'])
    def test_basic_password_stays_with_its_hosts(self, app, auth_client, over):
        msca_id = self._make(app, None)  # the basic password also serves WinRM
        before = self._row(app, msca_id)
        _refused(_send(auth_client, 'put', f'/api/v2/microsoft-cas/{msca_id}',
                       dict(over, default_template='Changed')))
        assert self._row(app, msca_id) == before

    @pytest.mark.parametrize('over', [
        {'winrm_host': 'winrm.attacker.example'},
        {'winrm_username': 'other'},
        {'winrm_transport': 'kerberos', 'winrm_password': '***'},
    ], ids=['host', 'account', 'transport'])
    def test_winrm_password_stays_with_its_host(self, app, auth_client, over):
        msca_id = self._make(app, 'saved-winrm')
        before = self._row(app, msca_id)
        _refused(_send(auth_client, 'put', f'/api/v2/microsoft-cas/{msca_id}', over))
        assert self._row(app, msca_id) == before

    def test_winrm_password_follows_the_server_it_falls_back_to(self, app, auth_client):
        msca_id = self._make(app, 'saved-winrm')
        url = f'/api/v2/microsoft-cas/{msca_id}'
        assert _send(auth_client, 'put', url, {'winrm_host': '', 'winrm_password': 'typed-winrm'}
                     ).status_code == 200
        before = self._row(app, msca_id)
        _refused(_send(auth_client, 'put', url, {'server': 'adcs.attacker.example',
                                                 'password': 'typed'}))
        assert self._row(app, msca_id) == before

    def test_the_basic_password_never_falls_back_to_another_host(self, app, auth_client):
        # Typed WinRM password, moved with another typed one, then cleared
        from models.msca import MicrosoftCA
        msca_id = self._make(app, None)
        url = f'/api/v2/microsoft-cas/{msca_id}'
        for body in ({'winrm_password': 'x'},
                     {'winrm_host': 'winrm.attacker.example', 'winrm_password': 'y'},
                     {'winrm_password': ''}):
            assert _send(auth_client, 'put', url, body).status_code == 200
        with app.app_context():
            row = db.session.get(MicrosoftCA, msca_id)
            assert row.winrm_effective_host == 'winrm.attacker.example'
            assert row.winrm_effective_password is None
            row.winrm_host = 'ADCS.corp.example'  # the CA's own host, any case
            assert row.winrm_effective_password == 'saved-basic'

    def test_clearing_the_winrm_password_on_the_ca_host_needs_the_basic_one(self, app, auth_client):
        msca_id = self._make(app, None)
        url = f'/api/v2/microsoft-cas/{msca_id}'
        assert _send(auth_client, 'put', url, {'winrm_password': 'x', 'winrm_port': 5985}).status_code == 200
        before = self._row(app, msca_id)
        _refused(_send(auth_client, 'put', url, {'winrm_password': ''}))
        assert self._row(app, msca_id) == before
        assert _send(auth_client, 'put', url, {'winrm_password': '', 'password': 'typed'}).status_code == 200

    @pytest.mark.parametrize('mask', ['***', '********'])
    def test_a_masked_winrm_password_is_kept_not_stored(self, app, auth_client, mask):
        msca_id = self._make(app, 'saved-winrm')
        r = _send(auth_client, 'put', f'/api/v2/microsoft-cas/{msca_id}',
                  {'winrm_password': mask, 'password': mask})
        assert r.status_code == 200, r.data
        assert self._row(app, msca_id)[2::3] == ('saved-basic', 'saved-winrm')

    def test_winrm_fields_are_typed_strictly(self, app, auth_client):
        from models.msca import MicrosoftCA
        msca_id = self._make(app, 'saved-winrm')
        url = f'/api/v2/microsoft-cas/{msca_id}'
        assert _send(auth_client, 'put', url, {'winrm_verify_ssl': 'false', 'winrm_password': 'typed'}
                     ).status_code == 200
        with app.app_context():
            assert db.session.get(MicrosoftCA, msca_id).winrm_verify_ssl is False
        for body in ({'winrm_use_ssl': 'maybe', 'winrm_password': 'typed'},
                     {'winrm_password': 12345}):
            assert _send(auth_client, 'put', url, body).status_code == 400, body

    def test_unchanged_targets_and_typed_secrets_are_accepted(self, app, auth_client):
        msca_id = self._make(app, 'saved-winrm')
        url = f'/api/v2/microsoft-cas/{msca_id}'
        assert _send(auth_client, 'put', url, {
            'server': 'adcs.corp.example', 'password': '***', 'winrm_host': 'winrm.corp.example',
            'winrm_port': 5986, 'winrm_password': '***', 'default_template': 'T'}).status_code == 200
        # The WinRM host has its own password: the server moves with the basic one
        assert _send(auth_client, 'put', url, {
            'server': 'adcs2.corp.example', 'password': 'typed'}).status_code == 200
        assert _send(auth_client, 'put', url, {
            'winrm_host': 'winrm2.corp.example', 'winrm_password': 'typed-winrm'}).status_code == 200
        assert self._row(app, msca_id)[:6] == ('adcs2.corp.example', 'u', 'typed',
                                               'winrm2.corp.example', 5986, 'typed-winrm')


class TestADConnector:
    URL = '/api/v2/ad-connector'

    @pytest.fixture
    def saved(self, app):
        from models import ADConnectorConfig
        with app.app_context():
            ADConnectorConfig.query.delete()
            row = ADConnectorConfig(server='dc1.corp.local,dc2.corp.local', port=636, use_ssl=True,
                                    verify_ssl=True, base_dn='DC=corp,DC=local',
                                    bind_dn='CN=svc,DC=corp,DC=local')
            row.bind_password = 'saved-bind'
            db.session.add(row)
            db.session.commit()

    def _row(self, app):
        from models import ADConnectorConfig
        with app.app_context():
            row = ADConnectorConfig.get_singleton()
            return row.server, row.port, row.verify_ssl, row.bind_dn, row.bind_password, row.base_dn

    @pytest.mark.parametrize('over', [
        {'servers': ['dc1.corp.local', 'dc.attacker.example']},
        {'port': 389, 'use_ssl': False},
        {'verify_ssl': False, 'bind_password': '***'},
        {'bind_dn': 'CN=other,DC=corp,DC=local'},
    ], ids=['added-dc', 'plaintext', 'no-verify', 'bind-dn'])
    def test_target_needs_the_password(self, app, auth_client, saved, over):
        before = self._row(app)
        _refused(_send(auth_client, 'put', self.URL, dict(over, base_dn='DC=changed')))
        assert self._row(app) == before

    def test_dropping_a_dc_or_typing_the_password_is_accepted(self, app, auth_client, saved):
        assert _send(auth_client, 'put', self.URL, {
            'servers': ['dc1.corp.local'], 'port': 636, 'bind_password': '***'}).status_code == 200
        assert _send(auth_client, 'put', self.URL, {
            'servers': ['dc3.corp.local'], 'bind_password': 'typed'}).status_code == 200
        assert self._row(app)[0] == 'dc3.corp.local'


class TestHsmProvider:
    def _make(self, app, kind, config):
        from models.hsm import HsmProvider
        with app.app_context():
            row = HsmProvider(name=f'retarget-{kind}-{_suffix()}', type=kind)
            row.set_config(config)
            db.session.add(row)
            db.session.commit()
            return row.id

    def _config(self, app, provider_id):
        from models.hsm import HsmProvider
        with app.app_context():
            return db.session.get(HsmProvider, provider_id).get_config()

    @pytest.mark.parametrize('kind,config,over', [
        ('openbao', {'url': 'https://bao.example.com', 'mount_path': 'transit', 'token': 'saved'},
         {'url': 'https://bao.attacker.example', 'token': '***'}),
        ('openbao', {'url': 'https://bao.example.com', 'mount_path': 'transit', 'token': 'saved'},
         {'tls_skip_verify': True, 'token': '********'}),
        ('azure-keyvault', {'vault_url': 'https://v.vault.azure.net', 'tenant_id': 't',
                            'client_id': 'c', 'client_secret': 'saved'},
         {'tenant_id': 'other', 'client_secret': '***'}),
        ('pkcs11', {'module_path': '/usr/lib/softhsm/libsofthsm2.so', 'token_label': 'ucm',
                    'user_pin': 'saved'},
         {'module_path': '/tmp/evil.so', 'user_pin': '***'}),
    ], ids=['openbao-url', 'openbao-tls', 'azure-tenant', 'pkcs11-module'])
    def test_target_needs_the_credential(self, app, auth_client, kind, config, over):
        provider_id = self._make(app, kind, config)
        r = _send(auth_client, 'put', f'/api/v2/hsm/providers/{provider_id}',
                  {'config': dict(config, **over)})
        _refused(r)
        assert self._config(app, provider_id) == config

    def test_the_carried_over_previous_pin_counts_as_kept(self, app, auth_client):
        config = {'module_path': '/usr/lib/softhsm/libsofthsm2.so', 'token_label': 'ucm',
                  'user_pin': 'saved', 'previous_user_pin': 'old'}
        provider_id = self._make(app, 'pkcs11', config)
        url = f'/api/v2/hsm/providers/{provider_id}'
        _refused(_send(auth_client, 'put', url, {'config': {'module_path': '/tmp/evil.so',
                                                            'token_label': 'ucm'}}))
        assert self._config(app, provider_id) == config
        assert _send(auth_client, 'put', url, {'config': {
            'module_path': '/usr/lib/other.so', 'token_label': 'ucm', 'user_pin': 'typed'}}
        ).status_code == 200

    def test_a_moved_module_does_not_carry_the_previous_pin(self, app, auth_client):
        config = {'module_path': '/usr/lib/softhsm/libsofthsm2.so', 'token_label': 'ucm',
                  'user_pin': 'saved', 'previous_user_pin': 'old'}
        provider_id = self._make(app, 'pkcs11', config)
        url = f'/api/v2/hsm/providers/{provider_id}'
        assert _send(auth_client, 'put', url, {'config': dict(config, user_pin='***', previous_user_pin='***')}
                     ).status_code == 200
        assert self._config(app, provider_id)['previous_user_pin'] == 'old'
        assert _send(auth_client, 'put', url, {'config': {
            'module_path': '/usr/lib/other.so', 'token_label': 'ucm', 'user_pin': 'typed'}}).status_code == 200
        assert not self._config(app, provider_id).get('previous_user_pin')

    def test_same_target_or_typed_credential_is_accepted(self, app, auth_client):
        config = {'url': 'https://bao.example.com', 'mount_path': 'transit', 'token': 'saved'}
        provider_id = self._make(app, 'openbao', config)
        url = f'/api/v2/hsm/providers/{provider_id}'
        assert _send(auth_client, 'put', url, {'config': dict(config, token='***')}).status_code == 200
        assert self._config(app, provider_id)['token'] == 'saved'
        r = _send(auth_client, 'put', url, {'config': dict(config, url='https://bao2.example.com',
                                                           token='typed')})
        assert r.status_code == 200, r.data
        assert self._config(app, provider_id)['url'] == 'https://bao2.example.com'


class TestIntune:
    @pytest.fixture
    def app_id(self, auth_client):
        r = _send(auth_client, 'post', '/api/v2/scep/intune-apps', {
            'name': f'retarget-{_suffix()}', 'tenant_id': 'corp.onmicrosoft.com',
            'client_id': f'client-{_suffix()}', 'client_secret': 'saved-intune'})
        assert r.status_code in (200, 201), r.data
        return json.loads(r.data)['data']['id']

    def _row(self, app, app_id):
        from models import IntuneApp
        with app.app_context():
            row = db.session.get(IntuneApp, app_id)
            return row.name, row.tenant_id, row.client_id, row.decrypted_secret()

    @pytest.mark.parametrize('over', [{'tenant_id': 'attacker.onmicrosoft.com'},
                                      {'client_id': 'other-client', 'client_secret': ''}],
                             ids=['tenant', 'client'])
    def test_app_registration_target_needs_the_secret(self, app, auth_client, app_id, over):
        before = self._row(app, app_id)
        _refused(_send(auth_client, 'patch', f'/api/v2/scep/intune-apps/{app_id}',
                       dict(over, name='renamed')))
        assert self._row(app, app_id) == before

    def test_profile_trio_moves_the_bound_app_only_with_the_secret(self, app, auth_client,
                                                                   app_id, create_ca):
        ca = create_ca(cn=f'Retarget Intune CA {_suffix()}')
        r = _send(auth_client, 'post', '/api/v2/scep/profiles', {
            'name': f'retarget-{_suffix()}', 'ca_id': ca['id'], 'auto_approve': True,
            'intune_enabled': True, 'intune_app_id': app_id})
        assert r.status_code in (200, 201), r.data
        url = f"/api/v2/scep/profiles/{json.loads(r.data)['data']['id']}"
        try:
            before = self._row(app, app_id)
            for body in ({'intune_tenant_id': 'attacker.onmicrosoft.com'},
                         {'intune_enabled': False, 'intune_client_id': 'other-client'}):
                _refused(_send(auth_client, 'patch', url, body))
                assert self._row(app, app_id) == before
            r = _send(auth_client, 'patch', url, {'intune_tenant_id': 'new.onmicrosoft.com',
                                                  'intune_client_secret': 'typed'})
            assert r.status_code == 200, r.data
            assert self._row(app, app_id)[1:] == ('new.onmicrosoft.com', before[2], 'typed')
        finally:
            # Other suites count the SCEP profiles on file
            auth_client.delete(url)
