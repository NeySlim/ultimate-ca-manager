"""The client keytab of a Kerberos Microsoft CA connection.

KRB5_CLIENT_KTNAME names the connection's keytab, and KRB5CCNAME a ticket cache
of its own, only while its Kerberos credential is acquired, whatever the
principal, and on both channels; a connection without keytab takes no lock. A file
UCM manages itself (its data folder, the acceptor keytab) is never a client keytab.
requests-kerberos, gssapi and pywinrm are faked at their boundary.
"""
import json
import os
import sys
import threading
import uuid
from types import SimpleNamespace

import pytest
import requests.auth

from models import db
from models.msca import MicrosoftCA

ENV = 'KRB5_CLIENT_KTNAME'


class _FakeKerberosAuth:
    """requests_kerberos.HTTPKerberosAuth: the credential is acquired in generate_request_header."""
    seen = []
    hold = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def generate_request_header(self, response, host, is_preemptive=False):
        type(self).seen.append((self.kwargs.get('principal'), os.environ.get(ENV)))
        if type(self).hold is not None and os.environ.get(ENV) == '/kt/first':
            type(self).hold.wait(5)
        return 'Negotiate x'


@pytest.fixture
def kerberos(monkeypatch, tmp_path):
    _FakeKerberosAuth.seen = []
    _FakeKerberosAuth.hold = None
    monkeypatch.setitem(sys.modules, 'requests_kerberos',
                        SimpleNamespace(HTTPKerberosAuth=_FakeKerberosAuth, OPTIONAL=1))
    monkeypatch.setitem(sys.modules, 'certsrv', SimpleNamespace(
        Certsrv=lambda **kw: SimpleNamespace(session=SimpleNamespace(auth=None, verify=True))))
    monkeypatch.setenv(ENV, 'FILE:/previous.keytab')
    return _FakeKerberosAuth


def _row(**extra):
    values = dict(id=1, name='krb', server='ca.example', auth_method='kerberos', kerberos_principal=None,
                  kerberos_keytab_path='/kt/svc.keytab', verify_ssl=True, ca_bundle=None)
    values.update(extra)
    return SimpleNamespace(**values)


def _client(row):
    from services.msca.connection import MicrosoftCAConnectionMixin
    return MicrosoftCAConnectionMixin._get_client(row, typed=True)


def test_a_keytab_without_principal_is_used_and_the_variable_restored(kerberos):
    client = _client(_row())
    assert os.environ[ENV] == 'FILE:/previous.keytab'
    client.session.auth.generate_request_header(None, 'ca.example')
    assert kerberos.seen == [(None, '/kt/svc.keytab')]
    assert os.environ[ENV] == 'FILE:/previous.keytab'


def test_a_keytab_with_principal_leaves_nothing_for_the_next_connection(kerberos, monkeypatch):
    monkeypatch.delenv(ENV)
    _client(_row(kerberos_principal='svc@CORP')).session.auth.generate_request_header(None, 'ca.example')
    assert kerberos.seen == [('svc@CORP', '/kt/svc.keytab')]
    assert ENV not in os.environ


def test_two_connections_never_share_the_variable(kerberos):
    """The second credential waits for the first: neither reads the other's keytab."""
    kerberos.hold = threading.Event()
    first = _client(_row(kerberos_keytab_path='/kt/first')).session.auth
    second = _client(_row(kerberos_keytab_path='/kt/second')).session.auth
    t1 = threading.Thread(target=first.generate_request_header, args=(None, 'a'))
    t1.start()
    for _ in range(100):
        if kerberos.seen:
            break
        threading.Event().wait(0.01)
    t2 = threading.Thread(target=second.generate_request_header, args=(None, 'b'))
    t2.start()
    t2.join(0.3)
    assert [k for _p, k in kerberos.seen] == ['/kt/first']
    kerberos.hold.set()
    t1.join(5)
    t2.join(5)
    assert [k for _p, k in kerberos.seen] == ['/kt/first', '/kt/second']
    assert os.environ[ENV] == 'FILE:/previous.keytab'


# --- pywinrm 0.5.0 (the real Session, Protocol and Transport), its Kerberos auth faked ---

CCACHE = 'KRB5CCNAME'


class _WinrmKerberosAuth(requests.auth.AuthBase):
    """winrm.vendor.requests_kerberos.HTTPKerberosAuth: with force_preemptive its __call__
    acquires the credential (generate_request_header) on the first request."""
    winrm_encryption_available = True
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.auth_done = False
        self.seen = []
        type(self).instances.append(self)

    def generate_request_header(self, response, host, is_preemptive=False):
        self.seen.append((os.environ.get(ENV), os.environ.get(CCACHE)))
        return 'Negotiate x'

    def __call__(self, request):
        if not self.auth_done:
            request.headers['Authorization'] = self.generate_request_header(None, 'ca.example', True)
            self.auth_done = True
        return request

    def wrap_winrm(self, host, message):
        return message, b''

    def unwrap_winrm(self, host, message, header):
        return message


@pytest.fixture
def pywinrm(monkeypatch):
    import winrm.protocol
    import winrm.transport
    _WinrmKerberosAuth.instances = []
    state = SimpleNamespace(running=[], hold=None, started=threading.Event())
    monkeypatch.setattr(winrm.transport, 'HAVE_KERBEROS', True)
    monkeypatch.setattr(winrm.transport, 'REQUIRED', 1, raising=False)
    monkeypatch.setattr(winrm.transport, 'HTTPKerberosAuth', _WinrmKerberosAuth, raising=False)
    monkeypatch.setattr(winrm.transport.Transport, '_send_message_request',
                        lambda self, session, prepared: SimpleNamespace(content=b''))

    def open_shell(self, *args, **kwargs):
        if not self.transport.endpoint.startswith('http:'):
            self.transport.send_message('<open/>')
        return 'shell'

    def get_command_output(self, shell_id, command_id):
        state.running.append((os.environ.get(ENV), os.environ.get(CCACHE)))
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
    monkeypatch.setenv(CCACHE, 'FILE:/previous.ccache')
    return state


def _channel_row(**extra):
    values = dict(kerberos_principal='svc@CORP', winrm_effective_host='ca.example', winrm_use_ssl=True,
                  winrm_port=5986, winrm_transport='kerberos', winrm_verify_ssl=True,
                  winrm_effective_username=None)
    values.update(extra)
    return _row(**values)


def _run_ps(row):
    from services.msca.admin_channel import MicrosoftCAAdminChannelMixin
    return MicrosoftCAAdminChannelMixin._run_ps(row, 'x')


@pytest.mark.parametrize('ssl', [True, False], ids=['https', 'http-encrypted'])
def test_the_winrm_channel_names_the_keytab_only_while_it_acquires(pywinrm, ssl):
    """Over HTTPS the first request acquires; over HTTP the message encryption setup does."""
    from services.msca.client_keytab import ccache_name
    assert _run_ps(_channel_row(winrm_use_ssl=ssl, winrm_port=5986 if ssl else 5985)) == 'ok'
    auth, = _WinrmKerberosAuth.instances
    assert auth.kwargs['principal'] == 'svc@CORP'
    assert auth.seen == [('/kt/svc.keytab', ccache_name(1, '/kt/svc.keytab', 'svc@CORP'))]
    assert pywinrm.running == [('FILE:/previous.keytab', 'FILE:/previous.ccache')]
    assert (os.environ[ENV], os.environ[CCACHE]) == ('FILE:/previous.keytab', 'FILE:/previous.ccache')


def test_a_long_command_holds_no_kerberos_lock(pywinrm, kerberos):
    """Another connection signs in while a WinRM command of the first one is still running."""
    pywinrm.hold = threading.Event()
    channel = threading.Thread(target=_run_ps, args=(_channel_row(),))
    channel.start()
    try:
        assert pywinrm.started.wait(5)
        other = _client(_row(id=2, kerberos_keytab_path='/kt/other')).session.auth
        signer = threading.Thread(target=other.generate_request_header, args=(None, 'b'))
        signer.start()
        signer.join(2)
        assert [k for _p, k in kerberos.seen] == ['/kt/other'], 'the running command held the lock'
    finally:
        pywinrm.hold.set()
        channel.join(5)


def _hold_the_lock():
    from services.msca import client_keytab as module
    taken, release = threading.Event(), threading.Event()

    def holder():
        with module._LOCK:
            taken.set()
            release.wait(5)

    thread = threading.Thread(target=holder)
    thread.start()
    assert taken.wait(5)
    return thread, release


def test_no_keytab_never_waits_for_the_lock():
    from services.msca.client_keytab import client_keytab
    holder, release = _hold_the_lock()
    done = []
    try:
        worker = threading.Thread(target=lambda: done.extend(client_keytab(None).__enter__() or [1]))
        worker.start()
        worker.join(2)
        assert done, 'a connection without keytab waited for another one'
    finally:
        release.set()
        holder.join(5)


def test_the_wait_for_another_sign_in_is_bounded(monkeypatch):
    from services.msca import client_keytab as module
    monkeypatch.setattr(module, 'LOCK_WAIT_SECONDS', 0.2, raising=False)
    holder, release = _hold_the_lock()
    outcome = []

    def attempt():
        try:
            with module.client_keytab('/kt/svc.keytab'):
                outcome.append('entered')
        except Exception as e:  # noqa: BLE001
            outcome.append(e)

    try:
        worker = threading.Thread(target=attempt)
        worker.start()
        worker.join(3)
        assert outcome, 'the wait for the Kerberos lock has no end'
        assert isinstance(outcome[0], RuntimeError) and 'Kerberos' in str(outcome[0])
    finally:
        release.set()
        holder.join(5)
        worker.join(5)


# --- Each connection signs in with its own ticket cache ---

def test_each_identity_has_its_own_memory_cache(monkeypatch):
    from services.msca.client_keytab import client_keytab
    monkeypatch.setenv(CCACHE, 'FILE:/previous.ccache')
    names = {}
    for key, args in {'a': (1, '/kt/a', 'p@CORP'), 'a-again': (1, '/kt/a', 'p@CORP'),
                      'other-connection': (2, '/kt/a', 'p@CORP'), 'other-keytab': (1, '/kt/b', 'p@CORP'),
                      'other-principal': (1, '/kt/a', 'q@CORP'), 'no-principal': (1, '/kt/a', None)}.items():
        owner, path, principal = args
        with client_keytab(path, principal=principal, owner=owner):
            names[key] = os.environ[CCACHE]
        assert os.environ[CCACHE] == 'FILE:/previous.ccache'
    assert all(name.startswith('MEMORY:') for name in names.values())
    assert names['a'] == names['a-again']
    assert len({names[k] for k in names if k != 'a-again'}) == 5
    with client_keytab(None, principal='p@CORP', owner=1):
        assert os.environ[CCACHE] == 'FILE:/previous.ccache'


def test_the_certsrv_channel_uses_the_connection_cache(kerberos, monkeypatch):
    from services.msca.client_keytab import ccache_name
    seen = []
    monkeypatch.setattr(kerberos, 'generate_request_header',
                        lambda self, *a, **k: seen.append(os.environ.get(CCACHE)) or 'Negotiate x')
    _client(_row(id=7, kerberos_principal='svc@CORP')).session.auth.generate_request_header(None, 'ca.example')
    assert seen == [ccache_name(7, '/kt/svc.keytab', 'svc@CORP')]


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
    assert kerberos.seen == []


def test_a_keytab_outside_the_data_folder_is_accepted(auth_client, kerberos_row, kerberos, tmp_path):
    path = str(tmp_path / 'msca.keytab')
    r = _post(auth_client, f'/api/v2/microsoft-cas/{kerberos_row}', {'kerberos_keytab_path': path}, 'put')
    assert r.status_code == 200, r.data


def test_a_managed_file_saved_earlier_is_not_used(kerberos):
    from services.kerberos import negotiate_auth
    auth = _client(_row(kerberos_keytab_path=str(negotiate_auth.KEYTAB_PATH))).session.auth
    with pytest.raises(ValueError):
        auth.generate_request_header(None, 'ca.example')
    assert kerberos.seen == []
