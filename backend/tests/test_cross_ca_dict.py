"""The CA record tells the UI how many cross-certificates it carries and whether one is served (#400)."""
import pytest

from models import CA
from services.smart_import.importer import SmartImporter
from tests.fixtures.cross_pki import build_cross_pki, pem


@pytest.fixture
def pki():
    return build_cross_pki()


def test_ca_dict_counts_cross_certificates_and_flags_the_served_one(app, auth_client, pki):
    with app.app_context():
        SmartImporter().execute(pem(pki.root_a))
        SmartImporter().execute(pem(pki.root_b))
        a = CA.query.filter_by(descr=pki.name_a).one().id
        b = CA.query.filter_by(descr=pki.name_b).one().id
    before = auth_client.get(f'/api/v2/cas/{b}').get_json()['data']
    assert before['cross_certificate_count'] == 0 and before['cross_certificate_served'] is False
    r = auth_client.post(f'/api/v2/cas/{b}/cross-certificates', json={'certificate': pem(pki.cross_b), 'served': True})
    assert r.status_code == 201, r.data
    after = auth_client.get(f'/api/v2/cas/{b}').get_json()['data']
    assert after['cross_certificate_count'] == 1 and after['cross_certificate_served'] is True
    other = auth_client.get(f'/api/v2/cas/{a}').get_json()['data']
    assert other['cross_certificate_count'] == 0


def test_chain_variants_route_names_what_each_variant_swaps_in(app, auth_client, pki):
    with app.app_context():
        SmartImporter().execute(pem(pki.root_a))
        SmartImporter().execute(pem(pki.root_b))
        b = CA.query.filter_by(descr=pki.name_b).one().id
    xid = auth_client.post(f'/api/v2/cas/{b}/cross-certificates',
                           json={'certificate': pem(pki.cross_b)}).get_json()['data']['id']
    r = auth_client.get(f'/api/v2/cas/{b}/chain-variants')
    assert r.status_code == 200, r.data
    by_id = {v['id']: v for v in r.get_json()['data']}
    assert set(by_id) == {'primary', f'cross:{xid}'}
    cross = by_id[f'cross:{xid}']
    assert cross['ca_name'] == pki.name_b and pki.name_a in cross['issuer'] and cross['valid_to']
    assert auth_client.get('/api/v2/cas/999999/chain-variants').status_code == 404
