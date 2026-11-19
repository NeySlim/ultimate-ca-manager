"""RFC 2985 §5.4.1: challengePassword is a DirectoryString, and a PKCS #9
processor MUST recognize every string type it allows."""
import uuid

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.name import _ASN1Type
from cryptography.x509.oid import AttributeOID, NameOID

from services.scep.scep_service import SCEPService

from tests.test_scep_rfc8894_operations import (
    FAIL_INFO_OID, PKI_STATUS_OID, _build_request, _client_identity,
    _load_ca_material, _response_attributes,
)

CHALLENGE = 'sekret-ü'


@pytest.mark.parametrize('tag, encoded', [
    (_ASN1Type.UTF8String, CHALLENGE.encode('utf-8')),
    (_ASN1Type.BMPString, CHALLENGE.encode('utf-16-be')),
    (_ASN1Type.UniversalString, CHALLENGE.encode('utf-32-be')),
], ids=['utf8', 'bmp', 'universal'])
def test_csr_challenge_in_any_directory_string_type(app, create_ca, tag, encoded):
    ca_data = create_ca(cn=f'SCEP Challenge String CA {uuid.uuid4().hex[:8]}')
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    signer, _ = _client_identity('bmp-challenge.example.test', key=key)
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,
                                                       'bmp-challenge.example.test')]))
           .add_attribute(AttributeOID.CHALLENGE_PASSWORD, encoded, _tag=tag)
           .sign(key, hashes.SHA256()))

    with app.app_context():
        ca, ca_cert, _ = _load_ca_material(ca_data['id'])
        request = _build_request(ca_cert, signer, key, 19,
                                 csr.public_bytes(serialization.Encoding.DER),
                                 b'bmp-challenge-16')
        response, _ = SCEPService(ca.refid, challenge_password=CHALLENGE,
                                  auto_approve=True).process_pkcs_req(request, '127.0.0.1')

    attrs = _response_attributes(response)
    assert attrs[PKI_STATUS_OID] == '0', attrs.get(FAIL_INFO_OID)
