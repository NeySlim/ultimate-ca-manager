"""An export password that is present but not a string is refused with a 400 naming the
field, on every route that takes one. `0`, `false`, `[]` and `{}` used to read as "no
password" and the private key came back in clear with a 200."""
import json

import pytest

from tests.test_key_recovery import _open_request, _set_dual_control
from tests.test_mtls_pem_chain import enrolled  # noqa: F401
from tests.test_user_certificate_key_export_guard import (
    _enrolment_for, an_operator, somebody_elses_certificate)  # noqa: F401

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates', 'drop_new_users')

NOT_STRINGS = [0, False, [], {}, 12345678]


def _post(client, url, body):
    return client.post(url, data=json.dumps(body), content_type='application/json')


def _refused(response, field='password'):
    assert response.status_code == 400, response.data[:200]
    assert b'PRIVATE KEY' not in response.data
    assert field in response.get_data(as_text=True)


@pytest.fixture(scope='module')
def cert_id(create_cert):
    return create_cert(cn='pw-type.example.com')['id']


@pytest.fixture(scope='module')
def ca_id(create_ca):
    return create_ca(cn='Pw Type CA')['id']


@pytest.mark.parametrize('password', NOT_STRINGS)
@pytest.mark.parametrize('body', [
    {'format': 'pem', 'include_key': True},
    {'format': 'key'},
    {'format': 'pkcs12'},
])
def test_certificate_export(auth_client, cert_id, body, password):
    _refused(_post(auth_client, f'/api/v2/certificates/{cert_id}/export', {**body, 'password': password}))


@pytest.mark.parametrize('password', NOT_STRINGS)
@pytest.mark.parametrize('body', [
    {'format': 'pem', 'include_key': True},
    {'format': 'key'},
    {'format': 'pkcs12'},
])
def test_ca_export(auth_client, ca_id, body, password):
    _refused(_post(auth_client, f'/api/v2/cas/{ca_id}/export', {**body, 'password': password}))


@pytest.mark.parametrize('password', NOT_STRINGS)
def test_csr_key_export(auth_client, password):
    created = _post(auth_client, '/api/v2/csrs', {
        'cn': 'pw-type-csr.example.com', 'organization': 'O', 'country': 'US', 'key_type': 'RSA 2048'})
    csr_id = created.get_json()['data']['id']
    _refused(_post(auth_client, f'/api/v2/csrs/{csr_id}/export', {'format': 'key', 'password': password}))


@pytest.mark.parametrize('password', NOT_STRINGS)
@pytest.mark.parametrize('body', [
    {'format': 'pem', 'include_key': True},
    {'format': 'key'},
    {'format': 'pkcs12'},
])
def test_user_certificate_export(app, auth_client, create_user, create_cert, body, password):
    create_user(username='pw_type_owner', role='viewer')
    rid, _ = _enrolment_for(app, create_cert, 'pw_type_owner', 'pw-type-user')
    _refused(_post(auth_client, f'/api/v2/user-certificates/{rid}/export', {**body, 'password': password}))


@pytest.mark.parametrize('password', NOT_STRINGS)
def test_mtls_download(auth_client, enrolled, password):  # noqa: F811
    _refused(_post(auth_client, enrolled, {'format': 'p12', 'password': password}))


@pytest.mark.parametrize('password', NOT_STRINGS)
def test_key_recovery(app, auth_client, create_cert, password):
    _set_dual_control(app, False)
    rid = _open_request(auth_client, create_cert(cn='pw-type-recovery.example.com')['id'])
    assert _post(auth_client, f'/api/v2/key-recovery/{rid}/approve', {}).status_code == 200
    _refused(_post(auth_client, f'/api/v2/key-recovery/{rid}/recover', {'password': password}))


@pytest.mark.parametrize('password', NOT_STRINGS)
@pytest.mark.parametrize('field', ['output_password', 'pkcs12_password'])
def test_converter(auth_client, create_cert, field, password):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    key = ec.generate_private_key(ec.SECP256R1()).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode()
    r = _post(auth_client, '/api/v2/tools/convert',
              {'pem': key, 'output_format': 'pem', field: password})
    _refused(r, field)
