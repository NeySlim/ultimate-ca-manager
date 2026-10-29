"""AIA caIssuers: .cer and .pem follow the served cross-certificate, .p7c bundles, one URL per cross-certificate (#400)."""
from datetime import timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding, pkcs7

from models import CA, db
from models.ca_cross_certificate import CACrossCertificate
from tests.fixtures.cross_pki import openssl_verify, pem
from tests.fixtures.cross_world import build_world, set_served
from tests.test_cross_chain_paths import _der
from utils.datetime_utils import utc_now


@pytest.fixture
def world(app, auth_client):
    return build_world(app, auth_client)


def _ref(app, ca_id):
    with app.app_context():
        return db.session.get(CA, ca_id).refid


def _bundle(response):
    return sorted(_der(c) for c in pkcs7.load_der_pkcs7_certificates(response.data))


def test_cer_and_pem_are_the_own_certificate_until_a_cross_certificate_is_served(app, client, world):
    ref = _ref(app, world.b_id)
    assert client.get(f'/ca/{ref}.cer').data == _der(world.pki.root_b)
    assert x509.load_pem_x509_certificate(client.get(f'/ca/{ref}.pem').data) == world.pki.root_b


def test_cer_and_pem_follow_the_served_cross_certificate(app, auth_client, client, world):
    set_served(auth_client, world, True)
    ref = _ref(app, world.b_id)
    r = client.get(f'/ca/{ref}.cer')
    assert r.data == _der(world.pki.cross_b) and r.mimetype == 'application/pkix-cert'
    assert x509.load_pem_x509_certificate(client.get(f'/ca/{ref}.pem').data) == world.pki.cross_b
    pki = world.pki
    ok, out = openssl_verify(pki.leaf, [pki.root_a],
                             untrusted=[x509.load_der_x509_certificate(client.get(f'/ca/{_ref(app, world.int_id)}.cer').data),
                                        x509.load_der_x509_certificate(r.data)])
    assert ok, out


def test_a_ca_without_cross_certificate_is_unchanged_when_another_ca_serves_one(app, auth_client, client, world):
    set_served(auth_client, world, True)
    assert client.get(f'/ca/{_ref(app, world.int_id)}.cer').data == _der(world.pki.int_b)


def test_a_cross_certificate_that_cannot_be_served_is_not_substituted(app, auth_client, client, world):
    set_served(auth_client, world, True)
    with app.app_context():
        db.session.get(CACrossCertificate, world.xid).valid_to = utc_now() - timedelta(days=1)
        db.session.commit()
    assert client.get(f'/ca/{_ref(app, world.b_id)}.cer').data == _der(world.pki.root_b)


def test_p7c_bundles_the_own_certificate_and_every_servable_cross_certificate(app, auth_client, client, world):
    ref = _ref(app, world.b_id)
    r = client.get(f'/ca/{ref}.p7c')
    assert r.status_code == 200 and r.mimetype == 'application/pkcs7-mime'
    assert _bundle(r) == sorted([_der(world.pki.root_b), _der(world.pki.cross_b)])
    assert _bundle(client.get(f'/ca/{_ref(app, world.int_id)}.p7c')) == [_der(world.pki.int_b)]
    auth_client.post(f'/api/v2/cas/{world.b_id}/cross-certificates/{world.xid}/revoke', json={})
    assert _bundle(client.get(f'/ca/{ref}.p7c')) == [_der(world.pki.root_b)]


def test_each_cross_certificate_has_its_own_url_even_when_not_served(app, client, world):
    ref = _ref(app, world.b_id)
    r = client.get(f'/ca/{ref}/cross/{world.xid}.cer')
    assert r.status_code == 200 and r.data == _der(world.pki.cross_b) and r.mimetype == 'application/pkix-cert'


def test_a_cross_certificate_url_is_refused_for_another_ca_unknown_ids_and_unservable_rows(app, auth_client, client, world):
    other = _ref(app, world.int_id)
    assert client.get(f'/ca/{other}/cross/{world.xid}.cer').status_code == 404
    assert client.get(f'/ca/{_ref(app, world.b_id)}/cross/999999.cer').status_code == 404
    auth_client.post(f'/api/v2/cas/{world.b_id}/cross-certificates/{world.xid}/revoke', json={})
    assert client.get(f'/ca/{_ref(app, world.b_id)}/cross/{world.xid}.cer').status_code == 404


@pytest.mark.parametrize('suffix', ['.cer', '.pem', '.p7c'])
def test_every_aia_answer_is_cacheable_for_a_day(app, client, world, suffix):
    r = client.get(f'/ca/{_ref(app, world.b_id)}{suffix}')
    assert r.headers['Cache-Control'] == 'public, max-age=86400, must-revalidate'
