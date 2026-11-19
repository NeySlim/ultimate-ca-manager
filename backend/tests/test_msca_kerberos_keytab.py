"""The client keytab of a Kerberos Microsoft CA connection.

KRB5_CLIENT_KTNAME names the connection's keytab only while its Kerberos
credential is acquired, whatever the principal, and on both channels.
requests-kerberos, gssapi and pywinrm are faked at their boundary.
"""
import os
import sys
import threading
from types import SimpleNamespace

import pytest


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


def test_the_winrm_channel_uses_the_same_principal_and_keytab(monkeypatch):
    seen = {}

    class Session:
        def __init__(self, endpoint, auth, transport, server_cert_validation):
            seen['auth'] = auth

        def run_ps(self, script):
            seen['env'] = os.environ.get(ENV)
            return SimpleNamespace(status_code=0, std_out=b'ok', std_err=b'')

    monkeypatch.setitem(sys.modules, 'winrm', SimpleNamespace(Session=Session))
    monkeypatch.setenv(ENV, 'FILE:/previous.keytab')
    from services.msca.admin_channel import MicrosoftCAAdminChannelMixin
    row = _row(kerberos_principal='svc@CORP', winrm_effective_host='ca.example', winrm_use_ssl=True,
               winrm_port=5986, winrm_transport='kerberos', winrm_verify_ssl=True,
               winrm_effective_username=None)
    assert MicrosoftCAAdminChannelMixin._run_ps(row, 'x') == 'ok'
    assert seen == {'auth': ('svc@CORP', ''), 'env': '/kt/svc.keytab'}
    assert os.environ[ENV] == 'FILE:/previous.keytab'
