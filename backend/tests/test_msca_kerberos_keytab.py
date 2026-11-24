"""The client keytab of a Kerberos Microsoft CA connection, on certsrv and on the WinRM channel.

Both channels sign in with the connection's own credential, acquired from its keytab into its
own memory cache: nothing is named in the process environment, no lock is held, and a WinRM
command never waits for another connection. A file UCM manages itself (its data folder, the
acceptor keytab) is never a client keytab. python-gssapi and pywinrm's network are faked.
"""
import json
import os
import sys
import threading
import uuid
from types import SimpleNamespace

import pytest

from models import db
from models.msca import MicrosoftCA
from tests.msca_kerberos_support import FakeGssapi, sign_in

ENV = 'KRB5_CLIENT_KTNAME'


@pytest.fixture
def kerberos(monkeypatch, tmp_path):
    fake = FakeGssapi().install(monkeypatch)
    monkeypatch.setitem(sys.modules, 'certsrv', SimpleNamespace(
        Certsrv=lambda **kw: SimpleNamespace(session=SimpleNamespace(auth=None, verify=True))))
    monkeypatch.setenv(ENV, 'FILE:/previous.keytab')
    fake.keytab = str(tmp_path / 'svc.keytab')
    open(fake.keytab, 'wb').close()
    return fake


def _row(**extra):
    values = dict(id=1, name='krb', server='ca.example', auth_method='kerberos', kerberos_principal=None,
                  kerberos_keytab_path='/kt/svc.keytab', verify_ssl=True, ca_bundle=None)
    values.update(extra)
    return SimpleNamespace(**values)


def _client(row):
    from services.msca.connection import MicrosoftCAConnectionMixin
    return MicrosoftCAConnectionMixin._get_client(row, typed=True)


def test_a_keytab_without_principal_is_used_and_nothing_is_named_in_the_environment(kerberos):
    sign_in(_client(_row(kerberos_keytab_path=kerberos.keytab)).session.auth)
    (principal, store), = kerberos.acquired
    assert principal is None and store['client_keytab'] == kerberos.keytab
    assert store['ccache'].startswith('MEMORY:')
    assert os.environ[ENV] == 'FILE:/previous.keytab'


def test_a_keytab_with_principal_signs_in_as_that_principal(kerberos):
    sign_in(_client(_row(kerberos_principal='svc@CORP', kerberos_keytab_path=kerberos.keytab)).session.auth)
    assert kerberos.principals == ['svc@CORP']


def test_a_saved_connection_keeps_its_credential_a_form_test_does_not(app, kerberos):
    from services.msca.connection import MicrosoftCAConnectionMixin
    with app.app_context():
        row = MicrosoftCA(name=f'krb-{uuid.uuid4().hex[:8]}', server='ca.example', auth_method='kerberos',
                          kerberos_principal='svc@CORP', kerberos_keytab_path=kerberos.keytab, enabled=True)
        db.session.add(row)
        db.session.commit()
        try:
            for _ in range(2):
                sign_in(MicrosoftCAConnectionMixin._get_client(row).session.auth)
            assert len(kerberos.acquired) == 1
            for _ in range(2):
                sign_in(MicrosoftCAConnectionMixin._get_client(row, typed=True).session.auth)
            assert len(kerberos.acquired) == 3
        finally:
            db.session.delete(row)
            db.session.commit()


# --- pywinrm 0.5.0 (the real Session, Protocol and Transport), its network faked ---

@pytest.fixture
def pywinrm(monkeypatch):
    import winrm.protocol
    import winrm.transport
    state = SimpleNamespace(running=[], hold=None, started=threading.Event(), sent=[], encrypted=[])
    monkeypatch.setattr(winrm.transport, 'HAVE_KERBEROS', False)  # no pykerberos: never needed

    def send(self, session, prepared):
        state.sent.append(prepared.headers.get('Authorization'))
        return SimpleNamespace(content=b'')
    monkeypatch.setattr(winrm.transport.Transport, '_send_message_request', send)
    real_setup = winrm.transport.Transport.setup_encryption

    def setup_encryption(self, session):
        state.encrypted.append(self.endpoint)
        return real_setup(self, session)
    monkeypatch.setattr(winrm.transport.Transport, 'setup_encryption', setup_encryption)

    def open_shell(self, *args, **kwargs):
        if not self.transport.encryption:
            self.transport.send_message('<open/>')
        return 'shell'

    def get_command_output(self, shell_id, command_id):
        state.running.append(os.environ.get(ENV))
        state.started.set()
        if state.hold is not None:
            state.hold.wait(5)
        return b'ok', b'', 0

    monkeypatch.setattr(winrm.protocol.Protocol, 'open_shell', open_shell)
    monkeypatch.setattr(winrm.protocol.Protocol, 'run_command', lambda self, *a, **k: 'command')
    monkeypatch.setattr(winrm.protocol.Protocol, 'get_command_output', get_command_output)
    monkeypatch.setattr(winrm.protocol.Protocol, 'cleanup_command', lambda self, *a: None)
    monkeypatch.setattr(winrm.protocol.Protocol, 'close_shell', lambda self, *a: None)
    monkeypatch.setenv(ENV, 'FILE:/previous.keytab')
    return state


def _channel_row(keytab, **extra):
    values = dict(kerberos_principal='svc@CORP', winrm_effective_host='ca.example', winrm_use_ssl=True,
                  winrm_port=5986, winrm_transport='kerberos', winrm_verify_ssl=True,
                  winrm_effective_username=None, kerberos_keytab_path=keytab)
    values.update(extra)
    return _row(**values)


def _run_ps(row):
    from services.msca.admin_channel import MicrosoftCAAdminChannelMixin
    return MicrosoftCAAdminChannelMixin._run_ps(row, 'x')


@pytest.mark.parametrize('ssl', [True, False], ids=['https', 'http-encrypted'])
def test_the_winrm_channel_signs_in_with_the_connection_credential(pywinrm, kerberos, ssl):
    """Without pykerberos: the first request carries the connection's ticket; over HTTP the
    message encryption is set up on it."""
    assert _run_ps(_channel_row(kerberos.keytab, winrm_use_ssl=ssl, winrm_port=5986 if ssl else 5985)) == 'ok'
    (principal, store), = kerberos.acquired
    assert principal == 'svc@CORP' and store['client_keytab'] == kerberos.keytab
    assert pywinrm.sent[0].startswith('Negotiate ')
    assert kerberos.tokens[0][0] == 'HTTP@ca.example'
    assert pywinrm.encrypted == ([] if ssl else ['http://ca.example:5985/wsman'])
    assert pywinrm.running == ['FILE:/previous.keytab']
    assert os.environ[ENV] == 'FILE:/previous.keytab'


def test_the_winrm_account_signs_in_as_itself(pywinrm, kerberos):
    _run_ps(_channel_row(kerberos.keytab, winrm_effective_username='admin@CORP'))
    assert kerberos.principals == ['admin@CORP']


def test_a_winrm_kerberos_failure_names_its_cause(pywinrm, kerberos):
    from services.msca.admin_channel import MSCAAdminChannelError
    kerberos.acquire_error = 'Preauthentication failed'
    with pytest.raises(MSCAAdminChannelError, match='Kerberos sign-in failed: Preauthentication failed'):
        _run_ps(_channel_row(kerberos.keytab))


def test_an_unexpected_pywinrm_is_refused(pywinrm, kerberos, monkeypatch):
    import winrm.transport
    from services.msca.admin_channel import MSCAAdminChannelError
    monkeypatch.delattr(winrm.transport.Transport, 'setup_encryption')
    with pytest.raises(MSCAAdminChannelError, match='not supported'):
        _run_ps(_channel_row(kerberos.keytab))
    assert kerberos.acquired == []


def test_a_long_command_holds_nothing_another_connection_waits_for(pywinrm, kerberos, tmp_path):
    other_keytab = str(tmp_path / 'other.keytab')
    open(other_keytab, 'wb').close()
    pywinrm.hold = threading.Event()
    channel = threading.Thread(target=_run_ps, args=(_channel_row(kerberos.keytab),))
    channel.start()
    try:
        assert pywinrm.started.wait(5)
        other = _client(_row(id=2, kerberos_keytab_path=other_keytab)).session.auth
        signer = threading.Thread(target=sign_in, args=(other, 'b'))
        signer.start()
        signer.join(2)
        assert [store['client_keytab'] for _p, store in kerberos.acquired] == [kerberos.keytab, other_keytab]
    finally:
        pywinrm.hold.set()
        channel.join(5)


# --- The keytab alone makes the Kerberos admin channel usable ---

def test_a_keytab_without_principal_or_account_is_a_usable_channel():
    from services.msca.admin_channel import MicrosoftCAAdminChannelMixin
    row = SimpleNamespace(winrm_enabled=True, winrm_transport='kerberos', kerberos_principal=None,
                          winrm_username=None, kerberos_keytab_path='/kt/svc.keytab')
    assert MicrosoftCAAdminChannelMixin.admin_channel_available(row)
    row.kerberos_keytab_path = None
    assert not MicrosoftCAAdminChannelMixin.admin_channel_available(row)


# --- A file UCM manages is never a client keytab ------------------------------

def _managed_paths(tmp_path):
    from services.kerberos import negotiate_auth
    from config.settings import DATA_DIR
    link = tmp_path / 'innocent.keytab'
    link.symlink_to(negotiate_auth.KEYTAB_PATH)
    return [str(negotiate_auth.KEYTAB_PATH), f'FILE:{negotiate_auth.KEYTAB_PATH}',
            str(link), str(DATA_DIR / 'sub' / '..' / 'ucm.db'), 'MEMORY:acceptor']


@pytest.fixture
def kerberos_row(app):
    with app.app_context():
        row = MicrosoftCA(name=f'krb-{uuid.uuid4().hex[:8]}', server='ca.example', auth_method='kerberos',
                          kerberos_principal='svc@CORP', kerberos_keytab_path='/etc/krb5.keytab', enabled=True)
        db.session.add(row)
        db.session.commit()
        row_id = row.id
    yield row_id
    with app.app_context():
        MicrosoftCA.query.filter_by(id=row_id).delete()
        db.session.commit()


def _post(client, url, body, method='post'):
    return getattr(client, method)(url, data=json.dumps(body), content_type='application/json')


def test_a_managed_file_is_refused_as_client_keytab(auth_client, kerberos_row, kerberos, tmp_path):
    for path in _managed_paths(tmp_path):
        bodies = [
            ('post', '/api/v2/microsoft-cas', {'name': f'n-{uuid.uuid4().hex[:6]}', 'server': 'ca.example',
                                               'auth_method': 'kerberos', 'kerberos_keytab_path': path}),
            ('put', f'/api/v2/microsoft-cas/{kerberos_row}', {'kerberos_keytab_path': path}),
            ('post', f'/api/v2/microsoft-cas/{kerberos_row}/test',
             {'server': 'evil.example', 'kerberos_principal': 'HTTP/ucm@CORP', 'kerberos_keytab_path': path}),
            ('post', '/api/v2/microsoft-cas/test', {'server': 'evil.example', 'auth_method': 'kerberos',
                                                    'kerberos_principal': 'HTTP/ucm@CORP',
                                                    'kerberos_keytab_path': path}),
        ]
        for method, url, body in bodies:
            r = _post(auth_client, url, body, method)
            assert r.status_code == 400, (path, url, r.data)
            assert 'kerberos_keytab_path' in r.get_json()['message']
    assert kerberos.acquired == []


def test_a_keytab_outside_the_data_folder_is_accepted(auth_client, kerberos_row, kerberos, tmp_path):
    path = str(tmp_path / 'msca.keytab')
    r = _post(auth_client, f'/api/v2/microsoft-cas/{kerberos_row}', {'kerberos_keytab_path': path}, 'put')
    assert r.status_code == 200, r.data


def test_a_managed_file_saved_earlier_is_not_used(kerberos):
    from services.kerberos import negotiate_auth
    auth = _client(_row(kerberos_keytab_path=str(negotiate_auth.KEYTAB_PATH))).session.auth
    with pytest.raises(ValueError):
        sign_in(auth)
    assert kerberos.acquired == []
