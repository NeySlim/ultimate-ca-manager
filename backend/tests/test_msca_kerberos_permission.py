"""Who may point a Microsoft CA connection's Kerberos sign-in somewhere.

Any Kerberos configuration signs in as an identity of the system: its keytab,
or without one the tickets the process already holds. Creating one, switching
a row to Kerberos (certsrv or the WinRM transport), moving it, changing its
keytab or principal, and testing it against a target other than the saved one
need admin:system, judged on the configuration the request leaves in effect.
The saved password and client key keep the retype rule, on PUT as on test.
"""
import json
import sys
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from models import db
from models.msca import MicrosoftCA
from tests.conftest import get_json

BASE = '/api/v2/microsoft-cas'
KEYTAB = '/srv/keytabs/ucm-enroll.keytab'
PRINCIPAL = 'svc-ucm@CORP.LOCAL'


@pytest.fixture(scope='module')
def operator_client(app, create_user):
    create_user(username='op_msca_kerberos', role='operator')
    client = app.test_client()
    r = client.post('/api/v2/auth/login',
                    data=json.dumps({'username': 'op_msca_kerberos', 'password': 'TestPass123!'}),
                    content_type='application/json')
    assert r.status_code == 200, r.data
    return client


@pytest.fixture
def outbound(monkeypatch):
    """Every client the service would build: none may exist after a refusal."""
    calls = []

    def factory(**kwargs):
        calls.append(kwargs)
        client = MagicMock()
        client.session.get.return_value.text = '<Option Value="E;WebServer">'
        return client

    class KerberosAuth:  # acquires as it is built: the principal is recorded with the client
        def __init__(self, credential, **kwargs):
            credential()

    from services.msca import connection
    monkeypatch.setitem(sys.modules, 'certsrv', SimpleNamespace(Certsrv=factory))
    monkeypatch.setattr(connection, 'KerberosAuth', KerberosAuth)
    monkeypatch.setattr(connection, 'initiator_credential',
                        lambda kept, principal, keytab, channel='certsrv': calls.append({'principal': principal}))
    return calls


def _row(app, **values):
    with app.app_context():
        row = MicrosoftCA(name=f'krb-perm-{uuid.uuid4().hex[:8]}', server='adcs.corp.local',
                          auth_method='kerberos', kerberos_principal=PRINCIPAL,
                          kerberos_keytab_path=KEYTAB, enabled=True, default_template='WebServer',
                          winrm_enabled=True, winrm_transport='kerberos')
        for key, value in values.items():
            setattr(row, key, value)
        db.session.add(row)
        db.session.commit()
        return row.id


@pytest.fixture
def kerberos_id(app):
    row_id = _row(app)
    yield row_id
    with app.app_context():
        MicrosoftCA.query.filter_by(id=row_id).delete()
        db.session.commit()


def _send(client, method, url, body=None):
    return getattr(client, method)(url, data=json.dumps(body) if body is not None else None,
                                   content_type='application/json')


def _forbidden(r):
    assert r.status_code == 403, r.data
    assert 'admin:system' in get_json(r)['message'], r.data


def _saved(app, row_id):
    with app.app_context():
        row = db.session.get(MicrosoftCA, row_id)
        return (row.server, row.kerberos_principal, row.kerberos_keytab_path, row.winrm_host, row.name)


class TestOperatorRefused:

    def test_testing_the_read_back_keytab_against_another_host(self, operator_client, kerberos_id, outbound):
        shown = get_json(operator_client.get(f'{BASE}/{kerberos_id}'))['data']
        body = {'server': 'attacker.example', 'kerberos_principal': shown['kerberos_principal'],
                'kerberos_keytab_path': shown['kerberos_keytab_path']}
        _forbidden(_send(operator_client, 'post', f'{BASE}/{kerberos_id}/test', body))
        _forbidden(_send(operator_client, 'post', f'{BASE}/test', {**body, 'auth_method': 'kerberos'}))
        assert outbound == []

    def test_testing_another_keytab_on_the_saved_target(self, operator_client, kerberos_id, outbound):
        _forbidden(_send(operator_client, 'post', f'{BASE}/{kerberos_id}/test',
                         {'kerberos_keytab_path': '/etc/krb5.keytab'}))
        assert outbound == []

    @pytest.mark.parametrize('body', [
        {'server': 'attacker.example'},
        {'verify_ssl': False},
        {'winrm_host': 'attacker.example'},
        {'kerberos_keytab_path': '/etc/krb5.keytab'},
        {'kerberos_principal': 'host/ucm@CORP.LOCAL'},
        {'kerberos_principal': ''},
    ], ids=['server', 'tls', 'winrm-host', 'keytab', 'principal', 'principal-cleared'])
    def test_moving_or_changing_a_saved_keytab(self, app, operator_client, kerberos_id, body):
        before = _saved(app, kerberos_id)
        _forbidden(_send(operator_client, 'put', f'{BASE}/{kerberos_id}', {**body, 'name': 'renamed'}))
        assert _saved(app, kerberos_id) == before

    def test_creating_a_connection_with_a_keytab(self, app, operator_client):
        name = f'krb-op-{uuid.uuid4().hex[:8]}'
        _forbidden(_send(operator_client, 'post', BASE, {'name': name, 'server': 'adcs.corp.local',
                                                         'auth_method': 'kerberos',
                                                         'kerberos_keytab_path': KEYTAB}))
        with app.app_context():
            assert MicrosoftCA.query.filter_by(name=name).first() is None

    def test_setting_a_keytab_on_a_connection_switched_to_kerberos(self, app, operator_client):
        row_id = _row(app, auth_method='basic', kerberos_principal=None, kerberos_keytab_path=None,
                      username='u')
        _forbidden(_send(operator_client, 'put', f'{BASE}/{row_id}', {'auth_method': 'kerberos',
                                                                    'kerberos_keytab_path': KEYTAB}))
        with app.app_context():
            assert db.session.get(MicrosoftCA, row_id).auth_method == 'basic'


class TestOperatorAllowed:

    def test_other_fields_and_the_saved_test(self, app, operator_client, kerberos_id, outbound):
        r = _send(operator_client, 'put', f'{BASE}/{kerberos_id}', {'name': 'Kerberos renamed',
                                                                   'default_template': 'User'})
        assert r.status_code == 200, r.data
        assert _saved(app, kerberos_id)[4] == 'Kerberos renamed'
        r = _send(operator_client, 'post', f'{BASE}/{kerberos_id}/test')
        assert r.status_code == 200, r.data
        assert {'principal': PRINCIPAL} in outbound

    def test_the_form_sent_back_unchanged(self, operator_client, kerberos_id, outbound):
        url = f'{BASE}/{kerberos_id}'
        form = {k: '' if v is None else v for k, v in get_json(operator_client.get(url))['data'].items()}
        assert _send(operator_client, 'put', url, {**form, 'ca_config': 'DC1\\Corp CA'}).status_code == 200
        tested = {k: form[k] for k in ('server', 'kerberos_principal', 'kerberos_keytab_path', 'verify_ssl')}
        assert _send(operator_client, 'post', f'{url}/test', tested).status_code == 200

    def test_switching_away_from_kerberos(self, app, operator_client):
        # The channel is off: with it on, Kerberos WinRM would follow the new server
        kerberos_id = _row(app, winrm_enabled=False)
        r = _send(operator_client, 'put', f'{BASE}/{kerberos_id}',
                  {'auth_method': 'basic', 'server': 'other.corp.local', 'username': 'u', 'password': 'p'})
        assert r.status_code == 200, r.data
        assert _saved(app, kerberos_id)[:3] == ('other.corp.local', None, None)


# --- Kerberos without keytab or principal: the process's own tickets sign in ---

def _ambient(app, **values):
    """A Kerberos row with neither keytab nor principal (the process's tickets)."""
    return _row(app, kerberos_principal=None, kerberos_keytab_path=None, **values)


def _snapshot(app, row_id):
    with app.app_context():
        row = db.session.get(MicrosoftCA, row_id)
        return {k: getattr(row, k) for k in ('name', 'server', 'auth_method', 'use_ssl', 'verify_ssl',
                                             'ca_bundle', 'kerberos_principal', 'kerberos_keytab_path',
                                             'winrm_enabled', 'winrm_host', 'winrm_transport')}


class TestOperatorRefusedAnyKerberos:

    @pytest.mark.parametrize('body', [
        {'auth_method': 'kerberos'},
        {'auth_method': 'basic', 'username': 'u', 'password': 'p', 'winrm_enabled': True,
         'winrm_transport': 'kerberos'},
    ], ids=['certsrv', 'winrm'])
    def test_creating_a_kerberos_connection_without_keytab(self, app, operator_client, outbound, body):
        name = f'krb-amb-{uuid.uuid4().hex[:8]}'
        _forbidden(_send(operator_client, 'post', BASE, {'name': name, 'server': 'attacker.example', **body}))
        with app.app_context():
            assert MicrosoftCA.query.filter_by(name=name).first() is None
        assert outbound == []

    @pytest.mark.parametrize('method', ['basic', 'certificate'])
    def test_switching_a_row_to_kerberos(self, app, operator_client, method):
        row_id = _ambient(app, auth_method=method, username='u', winrm_enabled=False)
        before = _snapshot(app, row_id)
        _forbidden(_send(operator_client, 'put', f'{BASE}/{row_id}', {'auth_method': 'kerberos'}))
        assert _snapshot(app, row_id) == before

    @pytest.mark.parametrize('body', [
        {'winrm_transport': 'kerberos'},
        {'winrm_enabled': True},
    ], ids=['transport', 'enabled'])
    def test_switching_the_channel_to_kerberos(self, app, operator_client, body):
        transport = 'ntlm' if 'winrm_transport' in body else 'kerberos'
        row_id = _ambient(app, auth_method='basic', username='u', winrm_transport=transport,
                          winrm_enabled='winrm_transport' in body)
        before = _snapshot(app, row_id)
        _forbidden(_send(operator_client, 'put', f'{BASE}/{row_id}', body))
        assert _snapshot(app, row_id) == before

    @pytest.mark.parametrize('body', [
        {'server': 'attacker.example'},
        {'use_ssl': False},
        {'verify_ssl': False},
        {'ca_bundle': 'PEM'},
        {'winrm_host': 'attacker.example'},
        {'winrm_port': 5985},
        {'winrm_username': 'other@CORP.LOCAL'},
        {'kerberos_principal': 'host/ucm@CORP.LOCAL'},
        {'kerberos_keytab_path': '/srv/keytabs/other.keytab'},
    ], ids=['server', 'use-ssl', 'verify-ssl', 'ca-bundle', 'winrm-host', 'winrm-port', 'winrm-account',
            'principal', 'keytab'])
    def test_moving_a_kerberos_row_without_keytab(self, app, operator_client, body):
        row_id = _ambient(app)
        before = _snapshot(app, row_id)
        _forbidden(_send(operator_client, 'put', f'{BASE}/{row_id}', {**body, 'name': 'renamed'}))
        assert _snapshot(app, row_id) == before

    def test_leaving_kerberos_on_certsrv_leaves_the_channel_on_the_process_tickets(
            self, app, operator_client, kerberos_id):
        """The update clears the keytab and principal: the Kerberos channel would sign in without them."""
        before = _snapshot(app, kerberos_id)
        _forbidden(_send(operator_client, 'put', f'{BASE}/{kerberos_id}', {'auth_method': 'certificate'}))
        assert _snapshot(app, kerberos_id) == before

    def test_an_inline_kerberos_test(self, operator_client, outbound):
        _forbidden(_send(operator_client, 'post', f'{BASE}/test',
                         {'server': 'attacker.example', 'auth_method': 'kerberos'}))
        assert outbound == []

    @pytest.mark.parametrize('body', [
        {'server': 'attacker.example'},
        {'verify_ssl': False},
        {'kerberos_principal': 'host/ucm@CORP.LOCAL'},
    ], ids=['server', 'tls', 'principal'])
    def test_testing_a_kerberos_row_without_keytab_elsewhere(self, app, operator_client, outbound, body):
        row_id = _ambient(app)
        _forbidden(_send(operator_client, 'post', f'{BASE}/{row_id}/test', body))
        assert outbound == []

    @pytest.mark.parametrize('body', [
        {'auth_method': 'kerberos', 'server': 'attacker.example'},
        {'auth_method': 'kerberos'},
    ], ids=['elsewhere', 'same-server'])
    def test_a_kerberos_test_of_a_basic_row_with_a_dormant_keytab(self, app, operator_client, outbound, body):
        row_id = _row(app, auth_method='basic', username='u', winrm_enabled=False)
        _forbidden(_send(operator_client, 'post', f'{BASE}/{row_id}/test', body))
        assert outbound == []


class TestOperatorRefusedChannelIdentity:
    """The Kerberos WinRM channel signs in as its account (its own, else the basic user, else the
    principal) with the keytab, toward winrm_host or else the server: each one changing is a 403."""

    def _basic(self, app):
        row_id = _row(app, auth_method='basic', username='svc', kerberos_principal=None,
                      kerberos_keytab_path=None, winrm_host=None)
        with app.app_context():
            db.session.get(MicrosoftCA, row_id).password = 'saved-password'
            db.session.commit()
        return row_id

    def _refused(self, app, client, row_id, body):
        before = _snapshot(app, row_id)
        _forbidden(_send(client, 'put', f'{BASE}/{row_id}', body))
        assert _snapshot(app, row_id) == before

    def test_the_keytab_leaves_a_channel_with_its_own_account(self, app, operator_client):
        row_id = _row(app, winrm_username='officer@CORP.LOCAL')
        self._refused(app, operator_client, row_id, {'auth_method': 'basic', 'username': 'u', 'password': 'p'})

    def test_the_server_a_channel_without_host_falls_back_to(self, app, operator_client):
        self._refused(app, operator_client, self._basic(app), {'server': 'attacker.example', 'password': 'p'})

    def test_the_principal_leaves_a_channel_without_account(self, app, operator_client):
        row_id = _row(app, kerberos_keytab_path=None)
        self._refused(app, operator_client, row_id, {'auth_method': 'certificate'})

    def test_the_basic_user_the_channel_signs_in_as(self, app, operator_client):
        self._refused(app, operator_client, self._basic(app), {'username': 'other', 'password': 'p'})


class TestOperatorAllowedKerberos:

    def test_renaming_and_the_saved_test(self, app, operator_client, outbound):
        row_id = _ambient(app)
        r = _send(operator_client, 'put', f'{BASE}/{row_id}', {'name': f'amb-{uuid.uuid4().hex[:6]}',
                                                              'default_template': 'User'})
        assert r.status_code == 200, r.data
        assert _send(operator_client, 'post', f'{BASE}/{row_id}/test').status_code == 200
        assert outbound[0]['server'] == 'adcs.corp.local'

    def test_the_form_sent_back_unchanged(self, operator_client, outbound, app):
        row_id = _ambient(app)
        url = f'{BASE}/{row_id}'
        form = {k: '' if v is None else v for k, v in get_json(operator_client.get(url))['data'].items()}
        assert _send(operator_client, 'put', url, {**form, 'default_template': 'User'}).status_code == 200
        tested = {k: form[k] for k in ('server', 'auth_method', 'kerberos_principal', 'kerberos_keytab_path',
                                       'use_ssl', 'verify_ssl', 'ca_bundle', 'ca_name')}
        assert _send(operator_client, 'post', f'{url}/test', tested).status_code == 200

    def test_leaving_kerberos_with_the_new_secret(self, app, operator_client):
        row_id = _ambient(app, winrm_enabled=False)
        r = _send(operator_client, 'put', f'{BASE}/{row_id}', {'auth_method': 'basic', 'server': 'other.corp.local',
                                                              'username': 'u', 'password': 'p'})
        assert r.status_code == 200, r.data
        assert _snapshot(app, row_id)['auth_method'] == 'basic'

    def test_leaving_kerberos_for_the_channel(self, app, operator_client, kerberos_id):
        r = _send(operator_client, 'put', f'{BASE}/{kerberos_id}', {'winrm_transport': 'ntlm'})
        assert r.status_code == 200, r.data
        assert _snapshot(app, kerberos_id)['winrm_transport'] == 'ntlm'

    def test_signing_through_a_kerberos_connection_ignores_any_target_in_the_body(
            self, app, operator_client, outbound):
        from services.cert_service import CertificateService
        row_id = _ambient(app)
        with app.app_context():
            csr_id = CertificateService.generate_csr(descr='krb-sign', dn={'CN': 'krb-sign.test.local'},
                                                     key_type='2048').id
            db.session.commit()
        r = _send(operator_client, 'post', f'{BASE}/{row_id}/sign/{csr_id}',
                  {'template': 'WebServer', 'server': 'attacker.example', 'auth_method': 'basic'})
        assert r.status_code != 403, r.data
        assert [c['server'] for c in outbound if 'server' in c] == ['adcs.corp.local']


class TestAdministratorAnyKerberos:

    def test_creates_and_tests_a_kerberos_connection_without_keytab(self, app, auth_client, outbound):
        name = f'krb-adm-{uuid.uuid4().hex[:8]}'
        r = _send(auth_client, 'post', BASE, {'name': name, 'server': 'adcs.corp.local',
                                              'auth_method': 'kerberos'})
        assert r.status_code == 201, r.data
        row_id = get_json(r)['data']['id']
        assert _send(auth_client, 'put', f'{BASE}/{row_id}', {'server': 'other.corp.local'}).status_code == 200
        r = _send(auth_client, 'post', f'{BASE}/test', {'server': 'x.corp.local', 'auth_method': 'kerberos'})
        assert r.status_code == 200, r.data

    def test_a_dormant_keytab_is_never_tested(self, app, auth_client, outbound):
        """The Kerberos columns of a row saved under another method are not read by a test."""
        from services.msca.connection import MicrosoftCAConnectionMixin
        row_id = _row(app, auth_method='basic', username='u', winrm_enabled=False)
        r = _send(auth_client, 'post', f'{BASE}/{row_id}/test', {'auth_method': 'kerberos'})
        assert r.status_code == 200, r.data
        assert {'principal': None} in outbound
        with app.app_context():
            tested = MicrosoftCAConnectionMixin._with_form_values(db.session.get(MicrosoftCA, row_id),
                                                                  {'auth_method': 'kerberos'})
        assert (tested.kerberos_principal, tested.kerberos_keytab_path) == (None, None)


class TestKerberosColumnsFollowTheMethod:

    def test_leaving_kerberos_clears_its_columns(self, app, auth_client, kerberos_id):
        r = _send(auth_client, 'put', f'{BASE}/{kerberos_id}', {'auth_method': 'certificate'})
        assert r.status_code == 200, r.data
        snap = _snapshot(app, kerberos_id)
        assert (snap['kerberos_principal'], snap['kerberos_keytab_path']) == (None, None)

    def test_the_same_method_clears_nothing(self, app, auth_client, kerberos_id):
        """Guard: naming the saved method again keeps the keytab and the principal."""
        r = _send(auth_client, 'put', f'{BASE}/{kerberos_id}', {'auth_method': 'kerberos'})
        assert r.status_code == 200, r.data
        snap = _snapshot(app, kerberos_id)
        assert (snap['kerberos_principal'], snap['kerberos_keytab_path']) == (PRINCIPAL, KEYTAB)


class TestAdministrator:

    def test_moves_and_tests_the_saved_keytab(self, app, auth_client, kerberos_id, outbound):
        r = _send(auth_client, 'post', f'{BASE}/{kerberos_id}/test', {'server': 'other.corp.local'})
        assert r.status_code == 200, r.data
        assert outbound[0]['server'] == 'other.corp.local'
        r = _send(auth_client, 'put', f'{BASE}/{kerberos_id}', {'server': 'other.corp.local',
                                                               'winrm_host': 'winrm.corp.local'})
        assert r.status_code == 200, r.data
        assert _saved(app, kerberos_id)[0] == 'other.corp.local'


# --- The saved password and client key stay with the saved certsrv target on save ---

def _secret_row(app, method, winrm_host, winrm_enabled):
    values = dict(auth_method=method, kerberos_principal=None, kerberos_keytab_path=None,
                  winrm_host=winrm_host, winrm_enabled=winrm_enabled, winrm_transport='kerberos')
    if method == 'basic':
        values['username'] = 'svc'
    else:
        values['client_cert_pem'] = 'CERT'
    row_id = _row(app, **values)
    with app.app_context():
        row = db.session.get(MicrosoftCA, row_id)
        if method == 'basic':
            row.password = 'saved-password'
        else:
            row.client_key_pem = 'saved-key'
        db.session.commit()
    return row_id


@pytest.mark.parametrize('method', ['certificate', 'basic'])
@pytest.mark.parametrize('winrm_host', [None, 'winrm.corp.local'], ids=['no-winrm-host', 'winrm-host'])
@pytest.mark.parametrize('winrm_enabled', [False, True], ids=['channel-off', 'channel-on'])
def test_a_moved_server_needs_the_saved_secret_retyped(app, auth_client, method, winrm_host, winrm_enabled):
    row_id = _secret_row(app, method, winrm_host, winrm_enabled)
    r = _send(auth_client, 'put', f'{BASE}/{row_id}', {'server': 'attacker.example'})
    assert r.status_code == 400, r.data
    details = get_json(r)['details']
    assert details['code'] == 'secret_required_for_target' and 'server' in details['fields']
    assert _saved(app, row_id)[0] == 'adcs.corp.local'
    secret = {'password': 'typed'} if method == 'basic' else {'client_key_pem': 'typed-key'}
    assert _send(auth_client, 'put', f'{BASE}/{row_id}', {'server': 'new.corp.local', **secret}).status_code == 200


# --- A Kerberos sign-in that fails: the CA read nothing, nothing is recorded ---

def _signing_fails_with(app, monkeypatch, error):
    """A Kerberos connection and a CSR whose submission raises ``error``: (connection id, CSR id)."""
    from services.cert_service import CertificateService

    def factory(**kwargs):
        client = MagicMock()
        client.get_cert.side_effect = error
        return client

    monkeypatch.setitem(sys.modules, 'certsrv', SimpleNamespace(Certsrv=factory))
    row_id = _row(app)
    with app.app_context():
        csr_id = CertificateService.generate_csr(descr='krb-sign', dn={'CN': f'krb-{uuid.uuid4().hex[:8]}.test.local'},
                                                 key_type='2048').id
        db.session.commit()
    return row_id, csr_id


def test_another_signing_error_keeps_its_failed_request(app, operator_client, monkeypatch):
    from models.msca import MSCARequest
    row_id, csr_id = _signing_fails_with(app, monkeypatch, RuntimeError('CA unreachable'))
    r = _send(operator_client, 'post', f'{BASE}/{row_id}/sign/{csr_id}', {'template': 'WebServer'})
    assert r.status_code == 500, r.data
    with app.app_context():
        assert [(q.status, q.error_message) for q in MSCARequest.query.filter_by(msca_id=row_id)] == [
            ('failed', 'CA unreachable')]


def test_a_failed_kerberos_sign_in_at_signing_is_a_400_without_a_request(app, operator_client, monkeypatch):
    from models.msca import MSCARequest
    from services.msca.kerberos import MSCAKerberosError
    row_id, csr_id = _signing_fails_with(
        app, monkeypatch, MSCAKerberosError('Kerberos sign-in failed: Preauthentication failed'))
    r = _send(operator_client, 'post', f'{BASE}/{row_id}/sign/{csr_id}', {'template': 'WebServer'})
    assert r.status_code == 400, r.data
    assert get_json(r)['message'] == 'Kerberos sign-in failed: Preauthentication failed'
    with app.app_context():
        assert MSCARequest.query.filter_by(msca_id=row_id).count() == 0
