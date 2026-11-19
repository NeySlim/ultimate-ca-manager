"""Testing a saved Microsoft CA connection uses the values on the form.

The test ran against the saved row whatever the form held, so a corrected
server or password was reported as fine or broken on the old values. Typed
values are used (saved secrets stay for what was not retyped) and nothing is saved.
"""
import json
import sys
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from models import db
from models.msca import MicrosoftCA


@pytest.fixture
def certsrv(monkeypatch):
    calls = []

    def factory(**kwargs):
        calls.append(kwargs)
        client = MagicMock()
        client.session.get.return_value.text = '<Option Value="E;WebServer">'
        return client

    monkeypatch.setitem(sys.modules, 'certsrv', SimpleNamespace(Certsrv=factory))
    return calls


@pytest.fixture
def connection(app):
    with app.app_context():
        row = MicrosoftCA(name=f'form-test-{uuid.uuid4().hex[:8]}', server='saved.example',
                          auth_method='basic', username='saved-user', enabled=True)
        row.password = 'saved-password'
        db.session.add(row)
        db.session.commit()
        connection_id = row.id
    yield connection_id
    with app.app_context():
        MicrosoftCA.query.filter_by(id=connection_id).delete()
        db.session.commit()


def _test(client, connection_id, body=None):
    return client.post(f'/api/v2/microsoft-cas/{connection_id}/test',
                       data=json.dumps(body) if body is not None else None,
                       content_type='application/json')


def test_no_body_tests_the_saved_connection(auth_client, connection, certsrv):
    r = _test(auth_client, connection)
    assert r.status_code == 200, r.data
    assert certsrv[0]['server'] == 'saved.example'
    assert certsrv[0]['username'] == 'saved-user'
    assert certsrv[0]['password'] == 'saved-password'


def test_typed_values_are_used_and_the_saved_secret_stays_for_the_rest(auth_client, connection, certsrv):
    r = _test(auth_client, connection, {'ca_name': 'Typed CA', 'password': '********', 'verify_ssl': True})
    assert r.status_code == 200, r.data
    assert r.get_json()['data']['ca_name'] == 'Typed CA'
    assert certsrv[0]['password'] == 'saved-password'
    assert certsrv[0]['server'] == 'saved.example'


def test_the_saved_password_does_not_follow_another_account(auth_client, connection, certsrv):
    r = _test(auth_client, connection, {'username': 'typed-user'})
    assert r.status_code == 400
    assert certsrv == []


def test_a_typed_password_goes_to_a_typed_server(auth_client, connection, certsrv):
    r = _test(auth_client, connection, {'server': 'typed.example', 'password': 'typed-password'})
    assert r.status_code == 200, r.data
    assert (certsrv[0]['server'], certsrv[0]['password']) == ('typed.example', 'typed-password')


def test_the_saved_password_does_not_follow_another_server(auth_client, connection, certsrv):
    r = _test(auth_client, connection, {'server': 'elsewhere.example'})
    assert r.status_code == 400
    assert certsrv == []


def test_the_test_saves_nothing(app, auth_client, connection, certsrv):
    assert _test(auth_client, connection, {'username': 'typed-user', 'password': 'typed'}).status_code == 200
    assert certsrv[0]['username'] == 'typed-user'
    with app.app_context():
        row = db.session.get(MicrosoftCA, connection)
        assert (row.username, row.password, row.last_test_at) == ('saved-user', 'saved-password', None)


@pytest.mark.parametrize('body, status', [({'server': ''}, 400), ({'server': 'x' * 501, 'password': 'p'}, 413),
                                          ({'auth_method': 'bogus'}, 400), ({'username': 5}, 400),
                                          (['not', 'an', 'object'], 400)])
def test_an_invalid_value_is_refused(auth_client, connection, certsrv, body, status):
    assert _test(auth_client, connection, body).status_code == status
    assert certsrv == []


# The test never hands a saved secret to a target the body changed: a blank
# password is no password, and a new auth method brings no saved secret along.
@pytest.mark.parametrize('body', [
    {'server': 'evil.example', 'password': ''},
    {'server': 'evil.example', 'verify_ssl': False, 'username': 'x', 'password': '   '},
])
def test_a_blank_password_is_no_password_on_another_target(auth_client, connection, certsrv, body):
    r = _test(auth_client, connection, body)
    assert all(call['password'] != 'saved-password' for call in certsrv)
    if r.status_code == 200:
        assert certsrv[0]['password'] == ''


def test_a_new_auth_method_brings_no_saved_password(app, auth_client, certsrv):
    with app.app_context():
        row = MicrosoftCA(name=f'form-cert-{uuid.uuid4().hex[:8]}', server='saved.example',
                          auth_method='certificate', client_cert_pem='CERT', enabled=True)
        row.password = 'saved-password'
        row.client_key_pem = 'saved-key'
        db.session.add(row)
        db.session.commit()
        row_id = row.id
    try:
        r = _test(auth_client, row_id, {'auth_method': 'basic', 'server': 'evil.example'})
        assert r.status_code == 400, r.data
        assert 'auth_method' in r.get_json()['details']['fields']
        assert certsrv == []
        # Same target: the saved key serves the connection it was saved for
        assert _test(auth_client, row_id, {'ca_name': 'Typed', 'client_key_pem': '***'}).status_code == 200
        assert len(certsrv) == 1
        # Another server with the saved key: refused, nothing built
        r = _test(auth_client, row_id, {'server': 'evil.example'})
        assert r.status_code == 400 and r.get_json()['details']['fields'] == ['server']
        assert len(certsrv) == 1
    finally:
        with app.app_context():
            MicrosoftCA.query.filter_by(id=row_id).delete()
            db.session.commit()


def test_the_saved_kerberos_principal_does_not_follow_another_server(app, auth_client, certsrv, monkeypatch):
    principals = []

    class HTTPKerberosAuth:
        def __init__(self, **kw):
            principals.append(kw.get('principal'))

    monkeypatch.setitem(sys.modules, 'requests_kerberos', SimpleNamespace(
        OPTIONAL=1, HTTPKerberosAuth=HTTPKerberosAuth))
    with app.app_context():
        row = MicrosoftCA(name=f'form-krb-{uuid.uuid4().hex[:8]}', server='saved.example',
                          auth_method='kerberos', kerberos_principal='svc@CORP',
                          kerberos_keytab_path='/saved/svc.keytab', enabled=True)
        db.session.add(row)
        db.session.commit()
        row_id = row.id
    try:
        r = _test(auth_client, row_id, {'server': 'evil.example'})
        assert r.status_code == 400, r.data
        assert r.get_json()['details']['fields'] == ['server']
        assert certsrv == [] and principals == []
        # Retyped with the new server, the principal is the caller's own
        body = {'server': 'typed.example', 'kerberos_principal': 'svc@CORP',
                'kerberos_keytab_path': '/saved/svc.keytab'}
        assert _test(auth_client, row_id, body).status_code == 200
        assert certsrv[0]['server'] == 'typed.example' and principals == ['svc@CORP']
    finally:
        with app.app_context():
            MicrosoftCA.query.filter_by(id=row_id).delete()
            db.session.commit()


def test_the_service_itself_keeps_the_saved_password_home(app, connection, certsrv):
    from services.msca_service import MicrosoftCAService
    with app.app_context():
        result = MicrosoftCAService.test_connection(connection, {'server': 'evil.example'})
    assert result['success'] is False and certsrv == []
