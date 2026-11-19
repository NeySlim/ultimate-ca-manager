"""The client keytab of a Kerberos Microsoft CA connection.

KRB5_CLIENT_KTNAME names the connection's keytab only while its Kerberos
credential is acquired, whatever the principal, and on both channels. A file
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
