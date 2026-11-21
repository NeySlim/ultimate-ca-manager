"""An export option that its format cannot carry is refused, not ignored."""
import pytest

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')


@pytest.fixture
def cert_id(create_cert):
    return create_cert(cn='inapplicable-options.example')['id']


@pytest.mark.parametrize('fmt, option', [
    ('der', 'include_key'),
    ('pkcs7', 'include_key'),
    ('p7b', 'include_key'),
    ('der', 'include_chain'),
])
def test_impossible_combination_is_a_400_naming_the_field(auth_client, cert_id, fmt, option):
    r = auth_client.post(f'/api/v2/certificates/{cert_id}/export',
                         json={'format': fmt, option: True})
    assert r.status_code == 400, r.data
    assert option in r.get_json()['message']


@pytest.mark.parametrize('fmt, body', [
    ('der', {}),
    ('der', {'include_key': False, 'include_chain': False}),
    ('pkcs7', {'include_chain': True}),
    ('p7b', {}),
    ('pem', {'include_chain': True, 'include_key': True}),
])
def test_possible_combination_still_exports(auth_client, cert_id, fmt, body):
    r = auth_client.post(f'/api/v2/certificates/{cert_id}/export',
                         json={'format': fmt, **body})
    assert r.status_code == 200, r.data
