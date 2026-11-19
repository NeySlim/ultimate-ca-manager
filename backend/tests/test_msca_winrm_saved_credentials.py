"""A saved credential of the WinRM admin channel only goes to the saved channel.

The channel test and the save both take a target from the request. With a
Kerberos transport the credential is the saved keytab and principal, not a
WinRM password: typing a password that Kerberos never uses must not carry
the saved keytab to another host, port, TLS setting, transport or account.
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

    def _test(self, client, msca_id, body):
        return _post(client, f'{BASE}/{msca_id}/admin-channel/test', body)

    def test_the_saved_channel_uses_the_saved_keytab(self, auth_client, kerberos_id, seen):
        r = self._test(auth_client, kerberos_id, {'winrm_host': '', 'winrm_port': 5986, 'winrm_use_ssl': True,
                                                  'winrm_verify_ssl': True, 'winrm_transport': 'kerberos',
                                                  'winrm_username': ''})
        assert r.status_code == 200, r.data
        assert seen[-1][:4] == ('adcs.corp.local', 'kerberos', PRINCIPAL, KEYTAB)

    @pytest.mark.parametrize('over, field', [
        ({'winrm_host': 'attacker.example'}, 'winrm_host'),
        ({'winrm_port': 5985}, 'winrm_port'),
        ({'winrm_use_ssl': False}, 'winrm_use_ssl'),
        ({'winrm_verify_ssl': False}, 'winrm_verify_ssl'),
        ({'winrm_username': 'other@CORP.LOCAL'}, 'winrm_username'),
    ], ids=['host', 'port', 'plaintext', 'no-verify', 'account'])
    def test_a_typed_password_does_not_carry_the_saved_keytab(self, auth_client, kerberos_id, seen,
                                                               over, field):
        r = self._test(auth_client, kerberos_id, {**over, 'winrm_password': 'typed-but-unused'})
        _refused(r, field)
        assert not seen, 'the saved keytab and principal went to a channel from the request'

    def test_clearing_the_winrm_host_falls_back_to_the_server(self, app, auth_client, seen):
        msca_id = _row(app, winrm_host='winrm.corp.local')
        _refused(self._test(auth_client, msca_id, {'winrm_host': '', 'winrm_password': 'typed'}),
                 'winrm_host')
        assert not seen

    @pytest.mark.parametrize('typed', [{'kerberos_keytab_path': '/srv/keytabs/other.keytab'},
                                       {'kerberos_principal': 'other@CORP.LOCAL'}],
                             ids=['keytab-only', 'principal-only'])
    def test_half_retyped_is_still_refused(self, auth_client, kerberos_id, seen, typed):
        _refused(self._test(auth_client, kerberos_id, {'winrm_host': 'attacker.example', **typed}),
                 'winrm_host')
        assert not seen

    def test_retyped_keytab_and_principal_may_go_anywhere(self, auth_client, kerberos_id, seen):
        r = self._test(auth_client, kerberos_id, {'winrm_host': 'other.example',
                                                  'kerberos_principal': 'other@CORP.LOCAL',
                                                  'kerberos_keytab_path': '/srv/keytabs/other.keytab'})
        assert r.status_code == 200, r.data
        assert seen[-1][:4] == ('other.example', 'kerberos', 'other@CORP.LOCAL', '/srv/keytabs/other.keytab')

    def test_a_typed_account_and_keytab_may_go_anywhere(self, auth_client, kerberos_id, seen):
        r = self._test(auth_client, kerberos_id, {'winrm_host': 'other.example',
                                                  'winrm_username': 'admin@CORP.LOCAL',
                                                  'kerberos_keytab_path': '/srv/keytabs/other.keytab'})
        assert r.status_code == 200, r.data
        assert seen[-1][2:4] == ('admin@CORP.LOCAL', '/srv/keytabs/other.keytab')

    def test_a_saved_principal_alone_stays_with_the_saved_channel(self, app, auth_client, seen):
        msca_id = _row(app, kerberos_keytab_path=None)
        _refused(self._test(auth_client, msca_id, {'winrm_host': 'attacker.example', 'winrm_password': 'x'}),
                 'winrm_host')
        assert not seen

    def test_switching_to_kerberos_does_not_carry_the_saved_keytab(self, app, auth_client, seen):
        msca_id = _row(app, winrm_transport='ntlm', winrm_username='officer')
        _refused(self._test(auth_client, msca_id, {'winrm_transport': 'kerberos',
                                                   'winrm_password': 'typed'}), 'winrm_transport')
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

    def test_a_moved_channel_needs_the_keytab_retyped(self, app, auth_client, kerberos_id):
        from models.msca import MicrosoftCA
        url = f'{BASE}/{kerberos_id}'
        _refused(_put(auth_client, url, {'winrm_host': 'attacker.example'}), 'winrm_host')
        _refused(_put(auth_client, url, {'winrm_host': 'attacker.example', 'winrm_password': 'x'}),
                 'winrm_host')
        _refused(_put(auth_client, url, {'winrm_host': 'attacker.example', 'kerberos_principal': PRINCIPAL}),
                 'winrm_host')
        with app.app_context():
            assert db.session.get(MicrosoftCA, kerberos_id).winrm_host is None

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
