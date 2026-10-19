"""A stored secret only goes to the stored target.

Connection tests accept the form as typed, and a blank secret means "the one
already saved". With the target taken from the request too, anyone allowed to
run the test could point it at a server of their own and receive the saved
secret. The saved secret is now reused only for the saved target; any other
target needs the secret typed in.
"""
import json
import uuid

import pytest

from models import ADConnectorConfig, db

SAVED_PASSWORD = 'saved-bind-secret'


def _post(client, url, body):
    return client.post(url, data=json.dumps(body), content_type='application/json')


class TestADConnectorTest:
    URL = '/api/v2/ad-connector/test'

    @pytest.fixture
    def captured(self, app, monkeypatch):
        from services.ad_connector import lookup
        calls = []
        monkeypatch.setattr(lookup, 'test_connection',
                            lambda cfg: calls.append(cfg) or {'success': True, 'message': 'ok'})
        with app.app_context():
            ADConnectorConfig.query.delete()
            config = ADConnectorConfig(server='dc1.corp.local,dc2.corp.local', port=636, use_ssl=True,
                                       verify_ssl=True, base_dn='DC=corp,DC=local',
                                       bind_dn='CN=svc,DC=corp,DC=local')
            config.bind_password = SAVED_PASSWORD
            db.session.add(config)
            db.session.commit()
        return calls

    def _form(self, **over):
        body = {'servers': ['dc1.corp.local'], 'port': 636, 'use_ssl': True, 'verify_ssl': True,
                'bind_dn': 'CN=svc,DC=corp,DC=local', 'bind_password': ''}
        body.update(over)
        return body

    def test_the_saved_target_reuses_the_saved_secret(self, auth_client, captured):
        assert _post(auth_client, self.URL, self._form()).status_code == 200
        assert captured[-1].bind_password == SAVED_PASSWORD

    @pytest.mark.parametrize('over', [
        {'servers': ['attacker.example']},
        {'servers': ['dc1.corp.local', 'attacker.example']},
        {'port': 1636},
        {'use_ssl': False, 'port': 636},
        {'verify_ssl': False},
        {'ca_bundle': '-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----'},
    ], ids=['server', 'extra-server', 'port', 'plaintext', 'no-verify', 'own-ca'])
    def test_another_target_needs_the_secret_typed(self, auth_client, captured, over):
        r = _post(auth_client, self.URL, self._form(**over))
        assert r.status_code == 400, r.data
        assert not captured, 'the saved bind password was sent to a target from the request'

    def test_a_typed_secret_may_go_anywhere(self, auth_client, captured):
        r = _post(auth_client, self.URL, self._form(servers=['other.example'], bind_password='typed'))
        assert r.status_code == 200
        assert captured[-1].bind_password == 'typed'


class TestMicrosoftCAAdminChannelTest:
    @pytest.fixture
    def seen(self, app, monkeypatch):
        from services.msca.admin_channel import MicrosoftCAAdminChannelMixin
        calls = []

        def fake_run_ps(cfg, script):
            calls.append((cfg.winrm_effective_host, cfg.winrm_effective_password))
            return 'UCM_CERTSVC=Running\n'

        monkeypatch.setattr(MicrosoftCAAdminChannelMixin, '_run_ps', staticmethod(fake_run_ps))
        return calls

    @pytest.fixture
    def msca_id(self, app):
        from models.msca import MicrosoftCA
        with app.app_context():
            msca = MicrosoftCA(name=f'Saved Secret Target CA {uuid.uuid4().hex[:8]}', server='adcs.corp.local',
                               auth_method='basic', username='u', enabled=True)
            msca.password = 'saved-basic'
            msca.winrm_enabled, msca.winrm_transport = True, 'ntlm'
            msca.winrm_use_ssl, msca.winrm_port = True, 5986
            msca.winrm_password = 'saved-winrm'
            db.session.add(msca)
            db.session.commit()
            return msca.id

    def _test(self, client, msca_id, body):
        return _post(client, f'/api/v2/microsoft-cas/{msca_id}/admin-channel/test', body)

    def test_the_saved_target_reuses_the_saved_secret(self, auth_client, msca_id, seen):
        assert self._test(auth_client, msca_id, {'winrm_password': '***'}).status_code == 200
        assert seen[-1] == ('adcs.corp.local', 'saved-winrm')

    @pytest.mark.parametrize('over', [
        {'winrm_host': 'attacker.example'}, {'winrm_port': 5985}, {'winrm_use_ssl': False},
        {'winrm_verify_ssl': False}, {'winrm_transport': 'kerberos'},
    ], ids=['host', 'port', 'plaintext', 'no-verify', 'transport'])
    def test_another_target_needs_the_secret_typed(self, auth_client, msca_id, seen, over):
        r = self._test(auth_client, msca_id, {**over, 'winrm_password': ''})
        assert r.status_code == 400, r.data
        assert not seen, 'a saved WinRM or basic password went to a target from the request'

    def test_a_typed_secret_may_go_anywhere(self, auth_client, msca_id, seen):
        r = self._test(auth_client, msca_id, {'winrm_host': 'other.example', 'winrm_password': 'typed'})
        assert r.status_code == 200, r.data
        assert seen[-1] == ('other.example', 'typed')


    def test_the_basic_password_stays_off_another_winrm_host(self, app, auth_client, msca_id, seen):
        from models.msca import MicrosoftCA
        with app.app_context():
            row = db.session.get(MicrosoftCA, msca_id)
            row.winrm_password, row.winrm_host = None, 'winrm.elsewhere.example'
            db.session.commit()
        self._test(auth_client, msca_id, {})
        assert all(password != 'saved-basic' for _, password in seen)
        with app.app_context():
            db.session.get(MicrosoftCA, msca_id).winrm_host = None
            db.session.commit()
        assert self._test(auth_client, msca_id, {}).status_code == 200
        assert seen[-1] == ('adcs.corp.local', 'saved-basic')


class TestIntuneTests:
    @pytest.fixture
    def seen(self, monkeypatch):
        from services.scep.intune_client import IntuneScepClient
        calls = []
        monkeypatch.setattr(IntuneScepClient, 'test_connection',
                            lambda self: calls.append((self.tenant_id, self.client_id, self.client_secret)))
        return calls

    @pytest.fixture
    def app_id(self, auth_client):
        suffix = uuid.uuid4().hex[:8]
        r = _post(auth_client, '/api/v2/scep/intune-apps', {
            'name': f'saved-secret-{suffix}', 'tenant_id': 'corp.onmicrosoft.com',
            'client_id': f'saved-secret-{suffix}-client', 'client_secret': 'saved-intune'})
        assert r.status_code == 200, r.data
        return json.loads(r.data)['data']['id']

    def test_the_saved_registration_reuses_its_secret(self, auth_client, app_id, seen):
        r = _post(auth_client, '/api/v2/scep/intune-apps/test', {'app_id': app_id})
        assert r.status_code == 200, r.data
        assert seen[-1][2] == 'saved-intune'

    @pytest.mark.parametrize('route,body', [
        ('/api/v2/scep/intune-apps/test', {'tenant_id': 'other.onmicrosoft.com'}),
        ('/api/v2/scep/intune-apps/test', {'client_id': 'other-client'}),
        ('/api/v2/scep/profiles/test-intune-connection', {'intune_tenant_id': 'other.onmicrosoft.com'}),
        ('/api/v2/scep/profiles/test-intune-connection', {'intune_client_id': 'other-client'}),
    ], ids=['apps-tenant', 'apps-client', 'profile-tenant', 'profile-client'])
    def test_another_tenant_or_client_needs_the_secret_typed(self, auth_client, app_id, seen, route, body):
        key = 'app_id' if 'intune-apps' in route else 'intune_app_id'
        r = _post(auth_client, route, {**body, key: app_id})
        assert r.status_code == 400, r.data
        assert not seen, 'the saved client secret was paired with a tenant or client from the request'
