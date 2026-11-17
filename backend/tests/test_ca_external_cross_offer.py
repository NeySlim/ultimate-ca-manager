"""Renew via CSR: a certificate from another issuer is offered as a cross-certificate (#400)."""
import base64
import json

from cryptography import x509

from models import db, CA
from tests.test_ca_external_csr import (
    _create_external, _make_external_root, _sign_csr_as_external_root, _next_cn, post_json,
)

BASE = '/api/v2/cas'


def _active_under(auth_client, root_key, root_cert):
    data = _create_external(auth_client)
    signed = _sign_csr_as_external_root(data['csr_pem'], root_key, root_cert, days=90)
    assert post_json(auth_client, f"{BASE}/{data['id']}/certificate", {'pem_content': signed}).status_code == 200
    renewed = json.loads(post_json(auth_client, f"{BASE}/{data['id']}/renew-csr", {}).data)['data']
    return data['id'], renewed['csr_pem'], signed


def _crt(app, ca_id):
    with app.app_context():
        return db.session.get(CA, ca_id).crt


def test_intermediate_refusal_carries_the_ca_and_both_options(app, auth_client):
    key_a, cert_a = _make_external_root(cn=_next_cn('OfferA'))
    key_b, cert_b = _make_external_root(cn=_next_cn('OfferB'))
    ca_id, csr, _ = _active_under(auth_client, key_a, cert_a)
    before = _crt(app, ca_id)
    other = _sign_csr_as_external_root(csr, key_b, cert_b, days=200)
    r = post_json(auth_client, f"{BASE}/{ca_id}/certificate", {'pem_content': other})
    assert r.status_code == 409, r.data
    details = json.loads(r.data)['details']
    assert details['code'] == 'cross_certificate_detected'
    assert details['ca_id'] == ca_id and details['options'] == ['attach', 'replace']
    assert _crt(app, ca_id) == before


def test_self_signed_refusal_offers_attach_only(app, auth_client, create_ca):
    root = create_ca(cn=_next_cn('OfferRoot'))
    other_key, other_cert = _make_external_root(cn=_next_cn('OfferOther'))
    csr = json.loads(post_json(auth_client, f"{BASE}/{root['id']}/renew-csr", {}).data)['data']['csr_pem']
    cross = _sign_csr_as_external_root(csr, other_key, other_cert, days=200)
    r = post_json(auth_client, f"{BASE}/{root['id']}/certificate", {'pem_content': cross})
    details = json.loads(r.data)['details']
    assert details['ca_id'] == root['id'] and details['options'] == ['attach']


def test_replace_installs_the_other_issuers_certificate(app, auth_client):
    key_a, cert_a = _make_external_root(cn=_next_cn('ReplA'))
    key_b, cert_b = _make_external_root(cn=_next_cn('ReplB'))
    ca_id, csr, _ = _active_under(auth_client, key_a, cert_a)
    other = _sign_csr_as_external_root(csr, key_b, cert_b, days=200)
    r = post_json(auth_client, f"{BASE}/{ca_id}/certificate", {'pem_content': other, 'cross_mode': 'replace'})
    assert r.status_code == 200, r.data
    stored = x509.load_pem_x509_certificate(base64.b64decode(_crt(app, ca_id)))
    assert stored.serial_number == x509.load_pem_x509_certificate(other.encode()).serial_number


def test_import_route_replace_reaches_a_ca_holding_a_renewal_request(app, auth_client):
    key_a, cert_a = _make_external_root(cn=_next_cn('ImpA'))
    key_b, cert_b = _make_external_root(cn=_next_cn('ImpB'))
    ca_id, csr, _ = _active_under(auth_client, key_a, cert_a)
    other = _sign_csr_as_external_root(csr, key_b, cert_b, days=200)
    r = auth_client.post(f'{BASE}/import', data={'pem_content': other, 'cross_mode': 'replace'},
                         content_type='multipart/form-data')
    assert r.status_code in (200, 201), r.data
    stored = x509.load_pem_x509_certificate(base64.b64decode(_crt(app, ca_id)))
    assert stored.serial_number == x509.load_pem_x509_certificate(other.encode()).serial_number


def test_invalid_cross_mode_is_a_400(auth_client):
    key_a, cert_a = _make_external_root(cn=_next_cn('BadMode'))
    ca_id, csr, _ = _active_under(auth_client, key_a, cert_a)
    signed = _sign_csr_as_external_root(csr, key_a, cert_a, days=200)
    r = post_json(auth_client, f"{BASE}/{ca_id}/certificate", {'pem_content': signed, 'cross_mode': 'nope'})
    assert r.status_code == 400
