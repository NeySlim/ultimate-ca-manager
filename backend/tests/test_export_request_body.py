"""Export routes read their options from a JSON object body or from the query string.

A private key never leaves in clear from a request that carried a password,
wherever it was, and the requested format is never swapped for another in
silence: a body that is not JSON, a JSON body that is not an object, and a
`password` in the query string all answer 400.
"""
import json

import pytest

from tests.test_mtls_pem_chain import enrolled  # noqa: F401
from tests.test_user_certificate_key_export_guard import _enrolment_for

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates', 'drop_new_users')

PASSWORD = 'Passw0rd!2026'
ROUTES = ['certificate', 'ca', 'user_certificate', 'csr', 'mtls']
# A format that carries a private key on each route
KEY_FORMAT = {'certificate': 'key', 'ca': 'key', 'user_certificate': 'key', 'csr': 'key', 'mtls': 'p12'}


def _csr_route(auth_client, cn):
    r = auth_client.post('/api/v2/csrs', json={
        'cn': cn, 'organization': 'O', 'country': 'US', 'key_type': 'RSA 2048'})
    assert r.status_code == 201, r.data[:200]
    return f"/api/v2/csrs/{r.get_json()['data']['id']}/export"


@pytest.fixture(params=ROUTES)
def route(request, app, auth_client, create_ca, create_cert, create_user):
    kind = request.param
    if kind == 'certificate':
        url = f"/api/v2/certificates/{create_cert(cn='body-rule.example.com')['id']}/export"
    elif kind == 'ca':
        url = f"/api/v2/cas/{create_ca(cn='Body Rule CA')['id']}/export"
    elif kind == 'user_certificate':
        create_user(username='body_rule_owner', role='viewer')
        rid, _ = _enrolment_for(app, create_cert, 'body_rule_owner', 'body-rule-user')
        url = f'/api/v2/user-certificates/{rid}/export'
    elif kind == 'csr':
        url = _csr_route(auth_client, 'body-rule-csr.example.com')
    else:
        url = request.getfixturevalue('enrolled')
    return kind, url


def _refused(r):
    assert r.status_code == 400, r.data[:300]
    assert b'PRIVATE KEY' not in r.data
    assert 'JSON body' in r.get_json()['message']


def test_csr_form_body_asking_for_the_key_with_a_password_is_refused(auth_client):
    url = _csr_route(auth_client, 'form-key-csr.example.com')
    _refused(auth_client.post(f'{url}?format=key', data={'format': 'key', 'password': PASSWORD}))


def test_csr_post_without_json_asking_for_the_key_is_refused(auth_client):
    url = _csr_route(auth_client, 'post-key-csr.example.com')
    _refused(auth_client.post(f'{url}?format=key'))


def test_form_body_is_refused(auth_client, route):
    kind, url = route
    _refused(auth_client.post(url, data={'format': KEY_FORMAT[kind], 'password': PASSWORD}))


def test_plain_text_body_is_refused(auth_client, route):
    kind, url = route
    body = json.dumps({'format': KEY_FORMAT[kind], 'password': PASSWORD})
    _refused(auth_client.post(url, data=body, content_type='text/plain'))


def test_query_string_password_with_a_json_body_is_refused(auth_client, route):
    kind, url = route
    fmt = 'pem' if kind == 'mtls' else 'key'
    _refused(auth_client.post(f'{url}?password={PASSWORD}', json={'format': fmt}))


def test_query_string_password_on_a_get_is_refused(auth_client, route):
    kind, url = route
    _refused(auth_client.get(f'{url}?format={KEY_FORMAT[kind]}&password={PASSWORD}'))


@pytest.mark.parametrize('raw', ['null', '[]', '"key"', '3'])
def test_json_body_that_is_not_an_object_is_refused(auth_client, route, raw):
    _kind, url = route
    _refused(auth_client.post(url, data=raw, content_type='application/json'))


def test_get_of_the_certificate_alone_still_works(auth_client, route):
    kind, url = route
    r = auth_client.get(url if kind == 'csr' else f'{url}?format=pem')
    assert r.status_code == 200, r.data[:300]
    assert b'PRIVATE KEY' not in r.data
    assert b'-----BEGIN' in r.data


def test_csr_get_of_the_key_without_a_password_still_works(auth_client):
    url = _csr_route(auth_client, 'get-key-csr.example.com')
    r = auth_client.get(f'{url}?format=key')
    assert r.status_code == 200, r.data[:300]
    assert b'PRIVATE KEY' in r.data


def test_json_body_still_exports_the_protected_key(auth_client, route):
    kind, url = route
    r = auth_client.post(url, json={'format': KEY_FORMAT[kind], 'password': PASSWORD})
    assert r.status_code == 200, r.data[:300]
    if kind == 'mtls':
        assert r.mimetype == 'application/x-pkcs12'
    else:
        assert b'ENCRYPTED PRIVATE KEY' in r.data
