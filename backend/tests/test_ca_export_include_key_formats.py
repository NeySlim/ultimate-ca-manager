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


@pytest.mark.parametrize('field', ['include_key', 'include_chain'])
@pytest.mark.parametrize('value', ['false', 'true', 0, 1, None])
def test_a_boolean_option_that_is_not_a_boolean_is_a_400(auth_client, create_ca, field, value):
    ca = create_ca(cn=f'Strict boolean {field}')
    r = _export(auth_client, ca['id'], {'format': 'pem', field: value})
    assert r.status_code == 400, r.data[:200]
    assert b'PRIVATE KEY' not in r.data
    assert field in r.get_json()['message']


def test_the_boolean_is_checked_before_an_hsm_refusal(app, auth_client, create_ca):
    """A CA on an HSM answers 409 only to a well-formed request."""
    from models import CA, db
    ca = create_ca(cn='Strict boolean HSM order')
    with app.app_context():
        row = db.session.get(CA, ca['id'])
        saved = row.hsm_key_id
        row.hsm_key_id = 1
        db.session.commit()
    try:
        r = _export(auth_client, ca['id'], {'format': 'pem', 'include_key': 'false'})
        assert r.status_code == 400, r.data[:200]
    finally:
        with app.app_context():
            row = db.session.get(CA, ca['id'])
            row.hsm_key_id = saved
            db.session.commit()


@pytest.mark.parametrize('value', ['1', 'yes', 'on'])
def test_a_query_boolean_other_than_true_or_false_is_a_400(auth_client, create_ca, value):
    """Guard of the documented change: 2.x read `include_chain=1` as false."""
    ca = create_ca(cn=f'Strict query boolean {value}')
    r = auth_client.get(f"/api/v2/cas/{ca['id']}/export?format=pem&include_chain={value}")
    assert r.status_code == 400, r.data[:200]
    assert 'include_chain' in r.get_json()['message']
