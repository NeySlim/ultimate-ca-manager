"""CA export: include_key with a format that carries no key is refused, not ignored."""
import json

import pytest

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')


def _export(client, ca_id, body):
    return client.post(f'/api/v2/cas/{ca_id}/export', data=json.dumps(body),
                       content_type='application/json')


@pytest.mark.parametrize('fmt', ['der', 'p7b', 'pkcs7'])
def test_include_key_with_a_keyless_format_is_refused(auth_client, create_ca, fmt):
    ca = create_ca(cn=f'Include key refusal {fmt}')
    r = _export(auth_client, ca['id'], {'format': fmt, 'include_key': True})
    assert r.status_code == 400, r.data[:200]
    assert 'include_key' in r.get_json()['message']


@pytest.mark.parametrize('fmt', ['der', 'p7b'])
def test_the_same_formats_without_include_key_still_export(auth_client, create_ca, fmt):
    ca = create_ca(cn=f'Keyless export {fmt}')
    r = _export(auth_client, ca['id'], {'format': fmt, 'include_key': False, 'password': 'ignored-as-no-key'})
    assert r.status_code == 200, r.data[:200]


def test_pem_with_include_key_still_carries_the_key(auth_client, create_ca):
    ca = create_ca(cn='Include key pem')
    r = _export(auth_client, ca['id'], {'format': 'pem', 'include_key': True})
    assert r.status_code == 200 and b'PRIVATE KEY' in r.data
