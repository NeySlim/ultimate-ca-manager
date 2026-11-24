"""The inline connection test (before a Microsoft CA is saved) reaches certsrv
with the plaintext credentials typed in the form."""
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def certsrv(monkeypatch):
    calls = []

    def factory(**kwargs):
        calls.append(kwargs)
        client = MagicMock()
        client.server = kwargs['server']
        client.session.get.return_value.text = '<Option Value="E;WebServer">'
        return client

    monkeypatch.setitem(sys.modules, 'certsrv', SimpleNamespace(Certsrv=factory))
    return calls


@pytest.fixture
def clients(monkeypatch):
    """The certsrv clients built; ``sign_in()`` makes their Kerberos handlers acquire."""
    from services.msca.connection import MicrosoftCAConnectionMixin
    from tests.msca_kerberos_support import sign_in
    built = []
    real = MicrosoftCAConnectionMixin._get_client

    def get_client(msca, typed=False):
        client = real(msca, typed)
        built.append(client)
        return client
    monkeypatch.setattr(MicrosoftCAConnectionMixin, '_get_client', staticmethod(get_client))

    def sign_in_all():
        for client in built:
            sign_in(client.session.auth)
    return SimpleNamespace(sign_in=sign_in_all)


def test_inline_test_with_basic_auth_uses_the_typed_password(app, certsrv):
    from services.msca.connection import MicrosoftCAConnectionMixin
    with app.app_context():
        result = MicrosoftCAConnectionMixin.test_connection_inline(
            {'server': 'ca.example', 'auth_method': 'basic', 'username': 'u', 'password': 'p'})
    assert result.get('success') is True, result
    assert certsrv[0]['username'] == 'u'
    assert certsrv[0]['password'] == 'p'


def test_inline_test_with_certificate_auth_writes_the_typed_key(app, certsrv):
    from services.msca.connection import MicrosoftCAConnectionMixin
    key = '-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n'
    seen = {}
    real_cleanup = MicrosoftCAConnectionMixin._cleanup_client

    def cleanup(client):
        with open(certsrv[0]['password']) as f:
            seen['key'] = f.read()
        real_cleanup(client)

    with app.app_context():
        MicrosoftCAConnectionMixin._cleanup_client = staticmethod(cleanup)
        try:
            result = MicrosoftCAConnectionMixin.test_connection_inline(
                {'server': 'ca.example', 'auth_method': 'certificate',
                 'client_cert_pem': '-----BEGIN CERTIFICATE-----', 'client_key_pem': key})
        finally:
            MicrosoftCAConnectionMixin._cleanup_client = staticmethod(real_cleanup)
    assert result.get('success') is True, result
    assert certsrv[0]['auth_method'] == 'cert'
    assert seen['key'] == key


def test_a_typed_password_shaped_like_a_token_is_sent_as_typed(app, certsrv):
    # A value typed in the form is never ciphertext, whatever it starts with
    from services.msca.connection import MicrosoftCAConnectionMixin
    typed = 'gAAAAA' + 'p' * 60
    with app.app_context():
        result = MicrosoftCAConnectionMixin.test_connection_inline(
            {'server': 'ca.example', 'auth_method': 'basic', 'username': 'u', 'password': typed})
    assert result.get('success') is True, result
    assert certsrv[0]['password'] == typed


def test_a_typed_key_shaped_like_a_token_is_written_as_typed(app, certsrv):
    from services.msca.connection import MicrosoftCAConnectionMixin
    typed = 'gAAAAA' + 'k' * 60
    seen = {}
    real_cleanup = MicrosoftCAConnectionMixin._cleanup_client

    def cleanup(client):
        with open(certsrv[0]['password']) as f:
            seen['key'] = f.read()
        real_cleanup(client)

    with app.app_context():
        MicrosoftCAConnectionMixin._cleanup_client = staticmethod(cleanup)
        try:
            result = MicrosoftCAConnectionMixin.test_connection_inline(
                {'server': 'ca.example', 'auth_method': 'certificate',
                 'client_cert_pem': '-----BEGIN CERTIFICATE-----', 'client_key_pem': typed})
        finally:
            MicrosoftCAConnectionMixin._cleanup_client = staticmethod(real_cleanup)
    assert result.get('success') is True, result
    assert seen['key'] == typed


def test_kerberos_principal_picks_the_identity(app, certsrv, clients, monkeypatch, tmp_path):
    # python-gssapi is faked at the library boundary: no KDC is contacted
    from tests.msca_kerberos_support import FakeGssapi
    gss = FakeGssapi().install(monkeypatch)
    keytab = tmp_path / 'ucm.keytab'
    keytab.write_bytes(b'')
    from services.msca.connection import MicrosoftCAConnectionMixin
    with app.app_context():
        result = MicrosoftCAConnectionMixin.test_connection_inline(
            {'server': 'ca.example', 'auth_method': 'kerberos',
             'kerberos_principal': 'svc-ucm@CORP.LOCAL', 'kerberos_keytab_path': str(keytab)})
    assert result.get('success') is True, result
    clients.sign_in()
    assert gss.principals == ['svc-ucm@CORP.LOCAL']
    assert gss.acquired[0][1]['client_keytab'] == str(keytab)


def test_kerberos_without_a_principal_uses_the_ambient_identity(app, certsrv, clients, monkeypatch):
    from tests.msca_kerberos_support import FakeGssapi
    gss = FakeGssapi().install(monkeypatch)
    from services.msca.connection import MicrosoftCAConnectionMixin
    with app.app_context():
        MicrosoftCAConnectionMixin.test_connection_inline(
            {'server': 'ca.example', 'auth_method': 'kerberos'})
    clients.sign_in()
    assert gss.acquired == [] and len(gss.tokens) == 1 and gss.tokens[0][1] is None
