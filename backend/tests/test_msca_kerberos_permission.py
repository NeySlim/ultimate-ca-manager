"""Who may point a Microsoft CA connection's Kerberos keytab somewhere.

The keytab path and the principal are read back in clear by GET, and the
secret is the content of a file the server reads itself: retyping them proves
nothing. Setting or changing them, moving a connection that holds them, and
testing them against a target other than the saved one need admin:system.
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

    class HTTPKerberosAuth:
        def __init__(self, **kwargs):
            calls.append({'principal': kwargs.get('principal')})

    monkeypatch.setitem(sys.modules, 'certsrv', SimpleNamespace(Certsrv=factory))
    monkeypatch.setitem(sys.modules, 'requests_kerberos',
                        SimpleNamespace(HTTPKerberosAuth=HTTPKerberosAuth, OPTIONAL=1))
    return calls


def _row(app, **values):
    with app.app_context():
        row = MicrosoftCA(name=f'krb-perm-{uuid.uuid4().hex[:8]}', server='adcs.corp.local',
                          auth_method='kerberos', kerberos_principal=PRINCIPAL,
                          kerberos_keytab_path=KEYTAB, enabled=True, default_template='WebServer')
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
        {'winrm_transport': 'ntlm'},
        {'kerberos_keytab_path': '/etc/krb5.keytab'},
        {'kerberos_principal': 'host/ucm@CORP.LOCAL'},
        {'kerberos_principal': ''},
    ], ids=['server', 'tls', 'winrm-host', 'channel', 'keytab', 'principal', 'principal-cleared'])
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

    def test_switching_away_from_kerberos(self, app, operator_client, kerberos_id):
        r = _send(operator_client, 'put', f'{BASE}/{kerberos_id}',
                  {'auth_method': 'basic', 'server': 'other.corp.local', 'username': 'u', 'password': 'p'})
        assert r.status_code == 200, r.data
        assert _saved(app, kerberos_id)[:3] == ('other.corp.local', None, None)


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
