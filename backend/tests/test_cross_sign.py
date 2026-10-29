"""Generating a cross-certificate in UCM: POST /api/v2/cas/<A>/cross-sign (#400)."""
import base64
import uuid
from datetime import timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import ExtensionOID, SignatureAlgorithmOID

from models import CA, AuditLog, db
from models.ca_cross_certificate import CACrossCertificate
from models.policy import CertificatePolicy
from services.smart_import.importer import SmartImporter
from tests.fixtures.cross_pki import build_cross_pki, key_pem, openssl_verify, pem
from utils.datetime_utils import utc_now
from utils.key_codec import store_pem_bytes


def _spki(cert):
    return cert.public_key().public_bytes(serialization.Encoding.DER,
                                          serialization.PublicFormat.SubjectPublicKeyInfo)


def _world(app, kind='ec', a_key=True, scheme=None):
    """Root A (with its key), Root B (certificate only) and Int B, imported; returns (pki, a_id, b_id)."""
    pki = build_cross_pki(kind)
    with app.app_context():
        for cert in (pki.root_a, pki.root_b, pki.int_b):
            SmartImporter().execute(pem(cert))
        a = CA.query.filter_by(descr=pki.name_a).one()
        b = CA.query.filter_by(descr=pki.name_b).one()
        if a_key:
            a.prv = store_pem_bytes(key_pem(pki.key_a).encode())
        if scheme:
            a.signature_scheme = scheme
        db.session.commit()
        return pki, a.id, b.id


@pytest.fixture
def world(app):
    return _world(app)


def _sign(client, a, b, **extra):
    return client.post(f'/api/v2/cas/{a}/cross-sign', json={'subject_ca_id': b, **extra})


def _cert_of(response):
    return x509.load_pem_x509_certificate(response.get_json()['data']['certificate'].encode())


def test_cross_sign_produces_a_chain_each_root_verifies_alone(app, auth_client, world):
    pki, a, b = world
    r = _sign(auth_client, a, b, validity_days=730)
    assert r.status_code == 201, r.data
    data = r.get_json()['data']
    cross = _cert_of(r)
    assert cross.subject == pki.root_b.subject and cross.issuer == pki.root_a.subject
    assert _spki(cross) == _spki(pki.root_b)
    aki = cross.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_KEY_IDENTIFIER).value
    assert aki.key_identifier == pki.root_a.extensions.get_extension_for_class(
        x509.SubjectKeyIdentifier).value.digest
    assert data['served'] is False and data['issuer'] != data['subject']
    ok, out = openssl_verify(pki.leaf, [pki.root_a], untrusted=[pki.int_b, cross])
    assert ok, out
    ok, out = openssl_verify(pki.leaf, [pki.root_b], untrusted=[pki.int_b])
    assert ok, out
    ok, _ = openssl_verify(pki.leaf, [pki.root_a], untrusted=[pki.int_b])
    assert not ok
    with app.app_context():
        row = CACrossCertificate.query.filter_by(ca_id=b).one()
        assert row.issuer_caref == db.session.get(CA, a).refid
        assert row.created_by and str(cross.serial_number) == row.serial_number
        assert db.session.get(CA, b).issuer == db.session.get(CA, b).subject  # B's own certificate stays


def test_cross_sign_carries_issuer_aia_and_cdp(app, auth_client, world):
    _, a, b = world
    with app.app_context():
        ca = db.session.get(CA, a)
        ca.cdp_enabled = True
        ca.set_cdp_urls(['http://pki.example/cdp/{ca_refid}.crl'])
        ca.ocsp_enabled = True
        ca.set_ocsp_urls(['http://pki.example/ocsp'])
        ca.aia_ca_issuers_enabled = True
        ca.set_aia_urls(['http://pki.example/ca/{ca_refid}.cer'])
        db.session.commit()
        ref = ca.url_ref
    cross = _cert_of(_sign(auth_client, a, b))
    cdp = cross.extensions.get_extension_for_class(x509.CRLDistributionPoints).value
    assert cdp[0].full_name[0].value == f'http://pki.example/cdp/{ref}.crl'
    aia = cross.extensions.get_extension_for_class(x509.AuthorityInformationAccess).value
    assert {d.access_location.value for d in aia} == {'http://pki.example/ocsp', f'http://pki.example/ca/{ref}.cer'}


def test_rsa_pss_issuer_signs_the_cross_certificate_with_pss(app, auth_client):
    pki, a, b = _world(app, 'rsa', scheme='pss')
    r = _sign(auth_client, a, b)
    assert r.status_code == 201, r.data
    cross = _cert_of(r)
    assert cross.signature_algorithm_oid == SignatureAlgorithmOID.RSASSA_PSS
    ok, out = openssl_verify(pki.leaf, [pki.root_a], untrusted=[pki.int_b, cross])
    assert ok, out


@pytest.mark.parametrize('days', [3651, 0, -5, 'ten', True, 1.5])
def test_validity_is_capped_at_3650_days(auth_client, world, days):
    _, a, b = world
    assert _sign(auth_client, a, b, validity_days=days).status_code == 400


def test_validity_is_clamped_to_the_issuer_window(app, auth_client):
    pki, a, b = _world(app)
    with app.app_context():
        remaining = (db.session.get(CA, a).valid_to - utc_now()).days
    assert remaining < 400
    cross = _cert_of(_sign(auth_client, a, b, validity_days=3650))
    assert cross.not_valid_after_utc <= pki.root_a.not_valid_after_utc


def test_expired_issuer_cannot_sign(app, auth_client, world):
    from datetime import datetime, timezone
    from tests.fixtures.cross_pki import make_cert
    _, _, b = world
    pki = build_cross_pki()
    with app.app_context():
        old = make_cert(f'Old Root {pki.tag}', pki.key_a, days=-2,
                        not_before=datetime.now(timezone.utc) - timedelta(days=10))
        SmartImporter().execute(pem(old))
        ca = CA.query.filter_by(descr=f'Old Root {pki.tag}').one()
        ca.prv = store_pem_bytes(key_pem(pki.key_a).encode())
        db.session.commit()
        old_id = ca.id
    r = _sign(auth_client, old_id, b)
    assert r.status_code == 400 and 'expired' in r.get_json()['message'].lower()


def test_offline_issuer_is_refused(app, auth_client, world):
    _, a, b = world
    with app.app_context():
        db.session.get(CA, a).offline = True
        db.session.commit()
    assert _sign(auth_client, a, b).status_code == 409
    with app.app_context():
        assert CACrossCertificate.query.filter_by(ca_id=b).count() == 0


def test_issuer_without_a_key_is_refused(app, auth_client):
    _, a, b = _world(app, a_key=False)
    r = _sign(auth_client, a, b)
    assert r.status_code == 400
    with app.app_context():
        assert CACrossCertificate.query.filter_by(ca_id=b).count() == 0


def test_path_length_defaults_to_the_subject_and_is_capped_by_subject_and_issuer(app, auth_client):
    from tests.fixtures.cross_pki import make_cert
    pki = build_cross_pki()
    with app.app_context():
        for cert in (make_cert(f'Cap Root A {pki.tag}', pki.key_a, path_length=5),
                     make_cert(f'Cap Root B {pki.tag}', pki.key_b, path_length=1)):
            SmartImporter().execute(pem(cert))
        a = CA.query.filter_by(descr=f'Cap Root A {pki.tag}').one()
        a.prv = store_pem_bytes(key_pem(pki.key_a).encode())
        db.session.commit()
        a_id, b_id = a.id, CA.query.filter_by(descr=f'Cap Root B {pki.tag}').one().id

    def length(**extra):
        r = _sign(auth_client, a_id, b_id, **extra)
        assert r.status_code == 201, r.data
        return _cert_of(r).extensions.get_extension_for_class(x509.BasicConstraints).value.path_length
    assert length() == 1
    assert length(path_length=0) == 0
    assert length(path_length=None) == 1  # never looser than the subject's own limit
    assert length(path_length=9) == 1
    assert _sign(auth_client, a_id, b_id, path_length=-1).status_code == 400
    assert _sign(auth_client, a_id, b_id, path_length='x').status_code == 400


def test_issuer_with_path_length_zero_cannot_cross_sign(app, auth_client):
    from tests.fixtures.cross_pki import make_cert
    pki = build_cross_pki()
    with app.app_context():
        for cert in (make_cert(f'Zero Root {pki.tag}', pki.key_a, path_length=0), pki.root_b):
            SmartImporter().execute(pem(cert))
        zero = CA.query.filter_by(descr=f'Zero Root {pki.tag}').one()
        zero.prv = store_pem_bytes(key_pem(pki.key_a).encode())
        db.session.commit()
        zid, b = zero.id, CA.query.filter_by(descr=pki.name_b).one().id
    assert _sign(auth_client, zid, b).status_code == 400


def test_subject_must_be_another_ca_with_a_different_key(app, auth_client, world):
    pki, a, b = world
    r = _sign(auth_client, a, a)
    assert r.status_code == 400 and 'one key' in r.get_json()['message']
    assert _sign(auth_client, a, 99999999).status_code == 404
    assert auth_client.post(f'/api/v2/cas/{a}/cross-sign', json={}).status_code == 400
    assert _sign(auth_client, 99999999, b).status_code == 404
    assert _sign(auth_client, a, 'x').status_code == 400
    with app.app_context():
        twin = CA(refid=str(uuid.uuid4()), descr='twin of A', crt=db.session.get(CA, a).crt,
                  subject=db.session.get(CA, a).subject, issuer=db.session.get(CA, a).issuer)
        db.session.add(twin)
        db.session.commit()
        twin_id = twin.id
    r = _sign(auth_client, a, twin_id)
    assert r.status_code == 400 and 'one key' in r.get_json()['message']


def test_subject_awaiting_its_certificate_is_refused(app, auth_client, world):
    _, a, _ = world
    with app.app_context():
        pending = CA(refid=str(uuid.uuid4()), descr=f'pending {uuid.uuid4().hex[:6]}', crt='')
        db.session.add(pending)
        db.session.commit()
        pid = pending.id
    assert _sign(auth_client, a, pid).status_code == 409


def test_key_type_policy_binds_the_cross_certificate(app, auth_client, world):
    _, a, b = world
    with app.app_context():
        pol = CertificatePolicy(name=f'no-ec-{uuid.uuid4().hex[:8]}', policy_type='issuance', ca_id=a,
                                requires_approval=False, min_approvers=1, is_active=True, priority=100)
        pol.set_rules({'allowed_key_types': ['RSA-4096']})
        db.session.add(pol)
        db.session.commit()
        pid = pol.id
    try:
        r = _sign(auth_client, a, b)
        assert r.status_code == 400 and 'olicy' in r.get_json()['message']
        with app.app_context():
            assert CACrossCertificate.query.filter_by(ca_id=b).count() == 0
    finally:
        with app.app_context():
            CertificatePolicy.query.filter_by(id=pid).delete()
            db.session.commit()


def test_validity_policy_caps_the_cross_certificate(app, auth_client, world):
    _, a, b = world
    with app.app_context():
        pol = CertificatePolicy(name=f'cap-{uuid.uuid4().hex[:8]}', policy_type='issuance', ca_id=a,
                                requires_approval=False, min_approvers=1, is_active=True, priority=100)
        pol.set_rules({'max_validity_days': 100})
        db.session.add(pol)
        db.session.commit()
        pid = pol.id
    try:
        r = _sign(auth_client, a, b, validity_days=300)
        assert r.status_code == 201, r.data
        cross = _cert_of(r)
        assert (cross.not_valid_after_utc - cross.not_valid_before_utc).days <= 101
    finally:
        with app.app_context():
            CertificatePolicy.query.filter_by(id=pid).delete()
            db.session.commit()


def test_viewer_cannot_cross_sign(viewer_client, world):
    _, a, b = world
    assert _sign(viewer_client, a, b).status_code == 403


def test_cross_sign_is_audited(app, auth_client, world):
    _, a, b = world
    assert _sign(auth_client, a, b).status_code == 201
    with app.app_context():
        assert AuditLog.query.filter_by(action='ca_cross_certificate_issued', resource_id=str(b)).count() == 1


def test_signing_twice_gives_two_distinct_certificates(app, auth_client, world):
    _, a, b = world
    assert _sign(auth_client, a, b).status_code == 201
    assert _sign(auth_client, a, b).status_code == 201
    with app.app_context():
        assert CACrossCertificate.query.filter_by(ca_id=b).count() == 2
