"""KRB5_KTNAME names the keytab XCEP and WSTEP accept with: a Kerberos Microsoft CA
connection, a client, never points it at its own keytab."""
import os
import sys
import types


def test_a_kerberos_msca_connection_leaves_krb5_ktname_alone(monkeypatch):
    from services.msca.connection import MicrosoftCAConnectionMixin
    monkeypatch.setitem(sys.modules, 'certsrv', types.SimpleNamespace(
        Certsrv=lambda **kw: types.SimpleNamespace(session=types.SimpleNamespace(auth=None, verify=True))))
    monkeypatch.setitem(sys.modules, 'requests_kerberos', types.SimpleNamespace(
        HTTPKerberosAuth=lambda **kw: object(), OPTIONAL=1))
    monkeypatch.setenv('KRB5_KTNAME', 'FILE:/acceptor.keytab')
    monkeypatch.setenv('KRB5_CLIENT_KTNAME', '')  # set, so the write below is undone
    msca = types.SimpleNamespace(server='ca.example.test', verify_ssl=True, ca_bundle=None,
                                 auth_method='kerberos', kerberos_keytab_path='/msca.keytab',
                                 kerberos_principal='svc@EXAMPLE.TEST')
    MicrosoftCAConnectionMixin._get_client(msca)
    assert os.environ['KRB5_KTNAME'] == 'FILE:/acceptor.keytab'
    # The client keytab is still the connection's own
    assert os.environ['KRB5_CLIENT_KTNAME'] == '/msca.keytab'
