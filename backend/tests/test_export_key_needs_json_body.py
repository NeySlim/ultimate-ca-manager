"""A private key leaves the certificate export routes only for a JSON body.

A form or plain-text body used to fall through to the query-string branch,
which never reads the body: its password was ignored and the key came back
in clear. Such requests, and every GET that asks for a key, now answer 400.
"""
import pytest

from tests.test_user_certificate_key_export_guard import _enrolment_for

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates', 'drop_new_users')

PASSWORD = 'Passw0rd!2026'


@pytest.fixture
def cert_route(create_cert):
    cert = create_cert(cn='json-only-key.example.com')
    return f"/api/v2/certificates/{cert['id']}/export"


@pytest.fixture
def user_cert_route(app, create_user, create_cert):
    create_user(username='json_only_key_owner', role='viewer')
    rid, _owner = _enrolment_for(app, create_cert, 'json_only_key_owner', 'json-only-key')
    return f'/api/v2/user-certificates/{rid}/export'


@pytest.fixture(params=['certificate', 'user_certificate'])
def route(request):
    return request.getfixturevalue('cert_route' if request.param == 'certificate'
                                   else 'user_cert_route')


def _assert_refused(r):
    assert r.status_code == 400, r.data
    assert b'PRIVATE KEY' not in r.data
    assert 'JSON body' in r.get_json()['message']


@pytest.mark.parametrize('fmt', ['key', 'pem'])
def test_form_body_with_a_password_is_refused(auth_client, route, fmt):
    body = {'format': fmt, 'password': PASSWORD, 'include_key': 'true'}
    _assert_refused(auth_client.post(f'{route}?format={fmt}&include_key=true', data=body))


def test_plain_text_body_is_refused(auth_client, route):
    r = auth_client.post(f'{route}?format=key',
                         data=f'{{"format": "key", "password": "{PASSWORD}"}}',
                         content_type='text/plain')
    _assert_refused(r)


@pytest.mark.parametrize('query', ['format=key', 'format=pem&include_key=true'])
def test_get_asking_for_a_key_is_refused(auth_client, route, query):
    _assert_refused(auth_client.get(f'{route}?{query}'))


def test_get_of_the_certificate_alone_still_works(auth_client, route):
    r = auth_client.get(f'{route}?format=pem')
    assert r.status_code == 200, r.data
    assert b'BEGIN CERTIFICATE' in r.data
    assert b'PRIVATE KEY' not in r.data


def test_json_body_still_exports_the_encrypted_key(auth_client, route):
    r = auth_client.post(route, json={'format': 'key', 'password': PASSWORD})
    assert r.status_code == 200, r.data
    assert b'ENCRYPTED PRIVATE KEY' in r.data
