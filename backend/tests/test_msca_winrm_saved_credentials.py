"""A saved credential of the WinRM admin channel and who may move it.

The saved NTLM password only goes to the saved channel unless it is retyped.
A Kerberos keytab path and principal are read back in clear, so retyping them
proves nothing: moving them is the admin:system permission (the channel test
route requires it; saves are covered in test_msca_kerberos_permission).
"""
import json
import uuid

import pytest

from models import db
from tests.conftest import get_json

BASE = '/api/v2/microsoft-cas'
KEYTAB = '/srv/keytabs/ucm-enroll.keytab'
PRINCIPAL = 'svc-ucm@CORP.LOCAL'


def _post(client, url, body):
    return client.post(url, data=json.dumps(body), content_type='application/json')


def _put(client, url, body):
    return client.put(url, data=json.dumps(body), content_type='application/json')


@pytest.fixture
def seen(monkeypatch):
    from services.msca.admin_channel import MicrosoftCAAdminChannelMixin
    calls = []

    def fake_run_ps(cfg, script):
        principal = cfg.winrm_effective_username or cfg.kerberos_principal
        calls.append((cfg.winrm_effective_host, cfg.winrm_transport, principal,
                      cfg.kerberos_keytab_path, cfg.winrm_effective_password))
        return 'UCM_CERTSVC=Running\n'

    monkeypatch.setattr(MicrosoftCAAdminChannelMixin, '_run_ps', staticmethod(fake_run_ps))
    return calls


def _row(app, **winrm):
    from models.msca import MicrosoftCA
    with app.app_context():
        msca = MicrosoftCA(name=f'WinRM Kerberos CA {uuid.uuid4().hex[:8]}', server='adcs.corp.local',
                           auth_method='kerberos', kerberos_principal=PRINCIPAL,
                           kerberos_keytab_path=KEYTAB, enabled=True)
        msca.winrm_enabled, msca.winrm_use_ssl, msca.winrm_verify_ssl = True, True, True
        msca.winrm_port, msca.winrm_transport = 5986, 'kerberos'
        for key, value in winrm.items():
            setattr(msca, key, value)
        db.session.add(msca)
        db.session.commit()
        return msca.id


@pytest.fixture
def kerberos_id(app):
    return _row(app)


def _refused(r, field):
    assert r.status_code == 400, r.data
    details = get_json(r).get('details') or {}
    assert details.get('code') == 'secret_required_for_target', r.data
    assert field in details.get('fields', []), r.data


class TestKerberosChannelTest:
    """The channel test is admin:system: its Kerberos keytab and principal may go where it points."""

    def _test(self, client, msca_id, body):
        return _post(client, f'{BASE}/{msca_id}/admin-channel/test', body)

    def test_the_saved_channel_uses_the_saved_keytab(self, auth_client, kerberos_id, seen):
        r = self._test(auth_client, kerberos_id, {'winrm_host': '', 'winrm_port': 5986, 'winrm_use_ssl': True,
                                                  'winrm_verify_ssl': True, 'winrm_transport': 'kerberos',
                                                  'winrm_username': ''})
        assert r.status_code == 200, r.data
        assert seen[-1][:4] == ('adcs.corp.local', 'kerberos', PRINCIPAL, KEYTAB)

    @pytest.mark.parametrize('over, expected', [
        ({'winrm_host': 'other.example'}, ('other.example', PRINCIPAL)),
        ({'winrm_username': 'other@CORP.LOCAL'}, ('adcs.corp.local', 'other@CORP.LOCAL')),
    ], ids=['host', 'account'])
    def test_an_administrator_moves_the_saved_keytab(self, auth_client, kerberos_id, seen, over, expected):
        assert self._test(auth_client, kerberos_id, over).status_code == 200
        assert (seen[-1][0], seen[-1][2], seen[-1][3]) == (*expected, KEYTAB)

    def test_retyped_keytab_and_principal_may_go_anywhere(self, auth_client, kerberos_id, seen):
        r = self._test(auth_client, kerberos_id, {'winrm_host': 'other.example',
                                                  'kerberos_principal': 'other@CORP.LOCAL',
                                                  'kerberos_keytab_path': '/srv/keytabs/other.keytab'})
        assert r.status_code == 200, r.data
        assert seen[-1][:4] == ('other.example', 'kerberos', 'other@CORP.LOCAL', '/srv/keytabs/other.keytab')

    def test_an_operator_cannot_test_the_channel(self, app, create_user, kerberos_id, seen):
        create_user(username='op_msca_channel', role='operator')
        client = app.test_client()
        assert _post(client, '/api/v2/auth/login', {'username': 'op_msca_channel',
                                                    'password': 'TestPass123!'}).status_code == 200
        r = self._test(client, kerberos_id, {})
        assert r.status_code == 403, r.data
        assert not seen

    def test_a_keytab_inside_the_data_folder_is_refused(self, auth_client, kerberos_id, seen):
        from config.settings import DATA_DIR
        r = self._test(auth_client, kerberos_id, {'kerberos_keytab_path': f'{DATA_DIR}/kerberos.keytab',
                                                  'kerberos_principal': PRINCIPAL})
        assert r.status_code == 400, r.data
        assert not seen


class TestNtlmChannelAccount:

    def test_another_account_needs_the_password_typed(self, app, auth_client, seen):
        msca_id = _row(app, winrm_transport='ntlm', winrm_username='officer', winrm_password='saved-winrm')
        url = f'{BASE}/{msca_id}/admin-channel/test'
        _refused(_post(auth_client, url, {'winrm_username': 'administrator', 'winrm_password': ''}),
                 'winrm_username')
        assert not seen
        assert _post(auth_client, url, {'winrm_username': 'officer'}).status_code == 200
        assert seen[-1][4] == 'saved-winrm'


class TestKerberosChannelSave:

    def test_an_administrator_moves_the_channel_of_a_saved_keytab(self, app, auth_client, kerberos_id):
        from models.msca import MicrosoftCA
        assert _put(auth_client, f'{BASE}/{kerberos_id}', {'winrm_host': 'winrm.corp.local'}).status_code == 200
        with app.app_context():
            assert db.session.get(MicrosoftCA, kerberos_id).winrm_host == 'winrm.corp.local'

    def test_the_form_sent_back_saves(self, app, auth_client, kerberos_id):
        from models.msca import MicrosoftCA
        url = f'{BASE}/{kerberos_id}'
        # As the form sends it: the read's nulls come back as empty fields
        form = {k: '' if v is None else v for k, v in get_json(auth_client.get(url))['data'].items()}
        assert _put(auth_client, url, {**form, 'winrm_host': 'winrm.corp.local'}).status_code == 200
        with app.app_context():
            assert db.session.get(MicrosoftCA, kerberos_id).winrm_host == 'winrm.corp.local'

    def test_an_unchanged_channel_keeps_the_saved_keytab(self, auth_client, kerberos_id):
        assert _put(auth_client, f'{BASE}/{kerberos_id}', {'ca_config': 'DC1\\Corp CA'}).status_code == 200
