"""The Kerberos credential of a Microsoft CA connection and its HTTP Negotiate sign-in.

Each saved connection acquires from its own keytab into its own in-memory ticket cache, kept
while the keytab file and the principal stay the same; nothing goes through the process'
ticket cache or environment. A GSSAPI failure or a refused ticket is an error naming its cause,
never a 401 handed back. python-gssapi is faked (tests/msca_kerberos_support.py).
"""
import base64
import os

import pytest
import requests
from requests.adapters import BaseAdapter
from requests.structures import CaseInsensitiveDict

from tests.msca_kerberos_support import FakeGssapi, sign_in

ENVIRONMENT = ('KRB5_CLIENT_KTNAME', 'KRB5CCNAME', 'KRB5_KTNAME')


@pytest.fixture
def gss(monkeypatch):
    for name in ENVIRONMENT:
        monkeypatch.setenv(name, f'FILE:/before/{name}')
    return FakeGssapi().install(monkeypatch)


@pytest.fixture
def keytabs(tmp_path):
    def make(name, content=b'\x05\x02one'):
        path = tmp_path / name
        path.write_bytes(content)
        return str(path)
    return make


def _credential(*args, **kwargs):
    from services.msca.kerberos import initiator_credential
    return initiator_credential(*args, **kwargs)


def _environment_untouched():
    assert all(os.environ[name] == f'FILE:/before/{name}' for name in ENVIRONMENT)


# --- One credential and one ticket cache per connection --------------------------------------

def test_two_connections_never_share_a_cache_or_a_credential(gss, keytabs):
    one, two = keytabs('one.keytab'), keytabs('two.keytab')
    first = _credential(1, 'svc@ONE.TEST', one)
    second = _credential(2, 'svc@TWO.TEST', two)
    assert first is not second
    (p1, s1), (p2, s2) = gss.acquired
    assert (p1, s1['client_keytab']) == ('svc@ONE.TEST', one)
    assert (p2, s2['client_keytab']) == ('svc@TWO.TEST', two)
    assert s1['ccache'].startswith('MEMORY:') and s2['ccache'].startswith('MEMORY:')
    assert s1['ccache'] != s2['ccache']
    _environment_untouched()


def test_a_connection_keeps_its_credential_while_nothing_changes(gss, keytabs):
    path = keytabs('svc.keytab')
    assert _credential(1, 'svc@ONE.TEST', path) is _credential(1, 'svc@ONE.TEST', path)
    assert len(gss.acquired) == 1


def test_a_replaced_keytab_gets_a_new_credential_in_a_new_cache(gss, keytabs, tmp_path):
    path = keytabs('svc.keytab')
    old = _credential(1, 'svc@ONE.TEST', path)
    old_cache = old.ccache
    replacement = tmp_path / 'new.keytab'
    replacement.write_bytes(b'\x05\x02another key')
    os.replace(replacement, path)
    new = _credential(1, 'svc@ONE.TEST', path)
    assert new is not old and len(gss.acquired) == 2
    assert gss.acquired[1][1]['ccache'] != old_cache
    del old
    assert old_cache in gss.destroyed, 'the tickets of the replaced keytab stay in memory'


def test_a_changed_principal_or_path_gets_a_new_credential(gss, keytabs):
    path, other = keytabs('svc.keytab'), keytabs('other.keytab')
    first = _credential(1, 'svc@ONE.TEST', path)
    assert _credential(1, 'admin@ONE.TEST', path) is not first
    assert _credential(1, 'admin@ONE.TEST', other) is not first
    assert gss.principals == ['svc@ONE.TEST', 'admin@ONE.TEST', 'admin@ONE.TEST']


def test_a_removed_keytab_fails_though_a_credential_was_held(gss, keytabs):
    from services.msca.kerberos import MSCAKerberosError
    path = keytabs('svc.keytab')
    _credential(1, 'svc@ONE.TEST', path)
    os.remove(path)
    with pytest.raises(MSCAKerberosError, match='cannot be read'):
        _credential(1, 'svc@ONE.TEST', path)
    keytabs('svc.keytab')
    _credential(1, 'svc@ONE.TEST', path)
    assert len(gss.acquired) == 2, 'the tickets of the removed keytab were used again'


def test_the_certsrv_and_winrm_identities_of_one_connection_are_kept_apart(gss, keytabs):
    path = keytabs('svc.keytab')
    web = _credential(1, 'web@ONE.TEST', path)
    channel = _credential(1, 'admin@ONE.TEST', path, channel='winrm')
    assert _credential(1, 'web@ONE.TEST', path) is web
    assert _credential(1, 'admin@ONE.TEST', path, channel='winrm') is channel
    assert len(gss.acquired) == 2


def test_a_form_being_tested_keeps_nothing(gss, keytabs):
    path = keytabs('svc.keytab')
    first = _credential(None, 'svc@ONE.TEST', path)
    cache = first.ccache
    assert _credential(None, 'svc@ONE.TEST', path) is not first
    del first
    assert cache in gss.destroyed


def test_a_deleted_connection_drops_its_credential(gss, keytabs):
    from services.msca.kerberos import forget
    path = keytabs('svc.keytab')
    _credential(7, 'svc@ONE.TEST', path)
    forget(7)
    _credential(7, 'svc@ONE.TEST', path)
    assert len(gss.acquired) == 2


def test_without_a_keytab_the_tickets_the_process_holds(gss):
    assert _credential(1, None, None).creds is None
    assert _credential(1, 'svc@ONE.TEST', None).creds.store is None
    assert gss.acquired == [('svc@ONE.TEST', None)]


@pytest.mark.parametrize('error, says', [
    ('Preauthentication failed', 'Preauthentication failed'),
    ("Cannot contact any KDC for realm 'ONE.TEST'", "Cannot contact any KDC for realm 'ONE.TEST'"),
])
def test_an_acquisition_failure_names_its_cause(gss, keytabs, error, says):
    from services.msca.kerberos import MSCAKerberosError
    gss.acquire_error = error
    with pytest.raises(MSCAKerberosError) as raised:
        _credential(1, 'svc@ONE.TEST', keytabs('svc.keytab'))
    assert says in str(raised.value) and 'Major (' not in str(raised.value)


def test_a_keytab_without_the_principal_says_so(gss, keytabs):
    from services.msca.kerberos import MSCAKerberosError
    from tests.msca_kerberos_support import FakeGSSError
    gss.acquire_error = FakeGSSError('No credentials cache found', min_code=2529639107)
    path = keytabs('svc.keytab')
    with pytest.raises(MSCAKerberosError, match=f'the keytab {path} holds no key for other@ONE.TEST'):
        _credential(1, 'other@ONE.TEST', path)


# --- HTTP Negotiate --------------------------------------------------------------------------

class _Server(BaseAdapter):
    """Answers each request with the next scripted (status, WWW-Authenticate) and keeps the requests."""

    def __init__(self, *script):
        super().__init__()
        self.script, self.requests = list(script), []

    def send(self, request, **kwargs):
        self.requests.append(request)
        status, challenge = self.script.pop(0)
        response = requests.Response()
        response.status_code, response.url, response.request = status, request.url, request
        response.headers = CaseInsensitiveDict({'WWW-Authenticate': challenge} if challenge else {})
        response._content, response._content_consumed = b'', True
        response.raw = type('Raw', (), {'release_conn': lambda self: None})()
        response.connection = self
        return response

    def close(self):
        pass


def _session(server, auth):
    session = requests.Session()
    session.mount('https://', server)
    session.auth = auth
    return session


def _auth(gss, keytabs, **kwargs):
    from services.msca.kerberos import KerberosAuth, initiator_credential
    path = keytabs('svc.keytab')
    return KerberosAuth(lambda: initiator_credential(1, 'svc@ONE.TEST', path), **kwargs)


TOKEN = 'Negotiate ' + base64.b64encode(b'server-token').decode()


def test_a_negotiate_challenge_is_answered_with_the_connection_ticket(gss, keytabs):
    server = _Server((401, 'Negotiate'), (200, TOKEN))
    response = _session(server, _auth(gss, keytabs)).get('https://ca.example/certsrv/')
    assert response.status_code == 200
    assert 'Authorization' not in server.requests[0].headers
    assert server.requests[1].headers['Authorization'] == 'Negotiate ' + base64.b64encode(b'client-token').decode()
    assert gss.tokens[0][0] == 'HTTP@ca.example'
    _environment_untouched()


def test_a_gssapi_failure_is_an_error_not_the_401(gss, keytabs):
    """requests-kerberos logged the GSSAPI error and returned the 401, which became a 500."""
    from services.msca.kerberos import MSCAKerberosError
    gss.step_error = 'Preauthentication failed'
    server = _Server((401, 'Negotiate'))
    with pytest.raises(MSCAKerberosError, match='Kerberos sign-in to ca.example failed: Preauthentication failed'):
        _session(server, _auth(gss, keytabs)).get('https://ca.example/certsrv/')


def test_a_refused_ticket_is_an_error(gss, keytabs):
    from services.msca.kerberos import MSCAKerberosError
    server = _Server((401, 'Negotiate'), (401, 'Negotiate'))
    with pytest.raises(MSCAKerberosError, match='refused the ticket'):
        _session(server, _auth(gss, keytabs)).get('https://ca.example/certsrv/')


def test_a_refusal_carrying_a_kerberos_error_names_it(gss, keytabs):
    from services.msca.kerberos import MSCAKerberosError
    gss.krb_error = 'Clock skew too great'
    krb_error = 'Negotiate ' + base64.b64encode(b'krb-error').decode()
    server = _Server((401, 'Negotiate'), (401, krb_error))
    with pytest.raises(MSCAKerberosError, match='Clock skew too great'):
        _session(server, _auth(gss, keytabs)).get('https://ca.example/certsrv/')


def test_a_server_without_negotiate_is_an_error(gss, keytabs):
    from services.msca.kerberos import MSCAKerberosError
    server = _Server((401, 'Basic realm="ca"'))
    with pytest.raises(MSCAKerberosError, match='does not offer Negotiate'):
        _session(server, _auth(gss, keytabs)).get('https://ca.example/certsrv/')


def test_a_server_that_fails_mutual_authentication_is_not_believed(gss, keytabs):
    from services.msca.kerberos import MSCAKerberosError
    forged = 'Negotiate ' + base64.b64encode(b'forged').decode()
    server = _Server((401, 'Negotiate'), (200, forged))
    with pytest.raises(MSCAKerberosError, match='mutual authentication'):
        _session(server, _auth(gss, keytabs)).get('https://ca.example/certsrv/')


@pytest.mark.parametrize('required', [True, False])
def test_an_answer_without_mutual_token(gss, keytabs, required):
    from services.msca.kerberos import MSCAKerberosError
    server = _Server((401, 'Negotiate'), (200, None))
    session = _session(server, _auth(gss, keytabs, mutual_required=required))
    if required:
        with pytest.raises(MSCAKerberosError, match='did not authenticate itself'):
            session.get('https://ca.example/certsrv/')
    else:
        assert session.get('https://ca.example/certsrv/').status_code == 200


def test_a_preemptive_sign_in_sends_the_ticket_first(gss, keytabs):
    server = _Server((200, TOKEN))
    auth = _auth(gss, keytabs, preemptive=True, mutual_required=True)
    assert _session(server, auth).post('https://ca.example/wsman', data=b'x').status_code == 200
    assert server.requests[0].headers['Authorization'].startswith('Negotiate ')
    assert auth.auth_done


def test_the_credential_is_acquired_at_the_first_ticket(gss, keytabs):
    auth = _auth(gss, keytabs)
    assert gss.acquired == []
    sign_in(auth)
    sign_in(auth)
    assert gss.principals == ['svc@ONE.TEST']


def test_without_gssapi_the_error_names_the_package(monkeypatch, keytabs):
    import sys
    from services.msca.kerberos import KerberosAuth, MSCAKerberosError, initiator_credential
    monkeypatch.setitem(sys.modules, 'gssapi', None)
    path = keytabs('svc.keytab')
    auth = KerberosAuth(lambda: initiator_credential(1, 'svc@ONE.TEST', path))
    with pytest.raises(MSCAKerberosError, match=r'pyspnego\[kerberos\]'):
        sign_in(auth)
