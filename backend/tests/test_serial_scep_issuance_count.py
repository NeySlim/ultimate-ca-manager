"""A SCEP enrolment counts its certificate in the CA's issuance counter."""
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import AttributeOID, NameOID

from models import CA, Certificate, db
from services.scep.scep_service import SCEPService
from tests.test_scep_rfc8894_operations import (
    PKI_STATUS_OID, _build_request, _client_identity, _load_ca_material, _response_attributes,
)


def _count(app, ca_id):
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        return ca.serial or 0, Certificate.query.filter_by(caref=ca.refid).count()


def test_scep_issuance_counts_the_certificate(app, create_ca):
    ca_data = create_ca(cn='SCEP issuance count CA')
    challenge = 'count challenge'
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'scep-count.example')]))
           .add_attribute(AttributeOID.CHALLENGE_PASSWORD, challenge.encode())
           .sign(key, hashes.SHA256()))
    with app.app_context():
        ca, ca_cert, _ = _load_ca_material(ca_data['id'])
        signer_cert, _ = _client_identity(key=key)
        request = _build_request(ca_cert, signer_cert, key, 19,
                                 csr.public_bytes(serialization.Encoding.DER), b'scep-count-nonce')
        response, status = SCEPService(ca.refid, challenge_password=challenge,
                                       auto_approve=True).process_pkcs_req(request, '127.0.0.1')
    assert status == 200
    assert _response_attributes(response)[PKI_STATUS_OID] == '0'
    assert _count(app, ca_data['id']) == (1, 1)
