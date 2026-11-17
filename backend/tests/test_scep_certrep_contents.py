"""The CertRep carries the issued certificate and nothing else: Apple's client
pairs the first certificate of the reply with its key, and DER sorting put a
shorter CA certificate first (#228)."""
import asn1crypto.cms
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509.oid import AttributeOID

from models import Certificate, db
from models.certificate_template import CertificateTemplate
from services.scep.scep_service import SCEPService
from tests.test_scep_rfc8894_operations import (
    PKI_STATUS_OID, _build_request, _client_identity, _decrypt_response,
    _load_ca_material, _response_attributes,
)

CHALLENGE = 'certrep horse battery staple'


def _enroll_request(ca_cert, identity):
    key_cert, key = identity
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(key_cert.subject)
           .add_attribute(AttributeOID.CHALLENGE_PASSWORD, CHALLENGE.encode())
           .sign(key, hashes.SHA256()))
    request = _build_request(ca_cert, key_cert, key, 19,
                             csr.public_bytes(serialization.Encoding.DER), b'certrep-nonce-16')
    return request, csr


@pytest.fixture
def scep_ca(create_ca):
    # One CA per test: the harness stamps every PKCSReq with the same transactionID
    return create_ca(cn='SCEP CertRep CA')


def test_certrep_carries_only_the_issued_certificate(app, scep_ca):
    with app.app_context():
        ca, ca_cert, _ = _load_ca_material(scep_ca['id'])
        identity = _client_identity('certrep device')
        request, csr = _enroll_request(ca_cert, identity)
        response, status = SCEPService(ca.refid, challenge_password=CHALLENGE,
                                       auto_approve=True).process_pkcs_req(request, '127.0.0.1')
        assert status == 200 and _response_attributes(response)[PKI_STATUS_OID] == '0'
        degenerate = asn1crypto.cms.ContentInfo.load(_decrypt_response(response, identity[1], identity[0]))
        certs = [c.chosen for c in degenerate['content']['certificates']]
        assert len(certs) == 1
        issued = x509.load_der_x509_certificate(certs[0].dump())
        spki = serialization.PublicFormat.SubjectPublicKeyInfo
        assert issued.public_key().public_bytes(serialization.Encoding.DER, spki) == \
            csr.public_key().public_bytes(serialization.Encoding.DER, spki)
        assert issued.issuer == ca_cert.subject


def test_scep_issuance_is_counted_against_the_bound_template(app, scep_ca):
    with app.app_context():
        tpl = CertificateTemplate(name='scep-counted-template', template_type='custom',
                                  validity_days=90, extensions_template='{"extended_key_usage": ["clientAuth"]}')
        db.session.add(tpl)
        db.session.commit()
        ca, ca_cert, _ = _load_ca_material(scep_ca['id'])
        identity = _client_identity('counted device')
        request, _csr = _enroll_request(ca_cert, identity)
        response, _ = SCEPService(ca.refid, challenge_password=CHALLENGE, auto_approve=True,
                                  template=tpl).process_pkcs_req(request, '127.0.0.1')
        assert _response_attributes(response)[PKI_STATUS_OID] == '0'
        row = Certificate.query.filter_by(caref=ca.refid).order_by(Certificate.id.desc()).first()
        try:
            assert row.template_id == tpl.id
        finally:
            db.session.delete(row)
            db.session.delete(tpl)
            db.session.commit()
