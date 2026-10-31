"""WSTEP and ML-DSA: a bare CSR and a PKCS#7 proof of possession signed per RFC 9882
are accepted; certificate-bound renewal (XML-DSig) is refused with a message."""
import asn1crypto.cms
import asn1crypto.core
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import mldsa, rsa
from cryptography.x509.oid import NameOID

from models import CA, db
from services.ca_service import CAService
from services.wstep import wstep_service, ws_security
from services.wstep.rst_parser import parse_rst
from tests.pqc_fixtures import load_mldsa_key, scep_wstep_mldsa_signed_cms
from tests.test_wstep_renew import _build_signed_rst
from utils import key_algorithms

pytestmark = pytest.mark.skipif(not key_algorithms.mldsa_supported(),
                                reason='this build has no ML-DSA')


def _csr(key, cn='wstep-pq.example.test'):
    return (x509.CertificateSigningRequestBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
            .sign(key, None))


def _ca(app, create_ca, cn):
    ca_data = create_ca(cn=cn)
    return db.session.get(CA, ca_data['id'])


def _pop_envelope(csr, signer_key):
    """Windows-style "Full PKCS#7": no certificate, signer named by the SKI of the CSR key."""
    der = scep_wstep_mldsa_signed_cms(csr.public_bytes(serialization.Encoding.DER),
                                      signer_key, sid='ski', with_certificate=False)
    return asn1crypto.cms.ContentInfo.load(der)['content']


def test_bare_mldsa_csr_is_issued(app, create_ca):
    key = load_mldsa_key()
    with app.app_context():
        ca = _ca(app, create_ca, 'WSTEP RSA CA for ML-DSA CSR')
        cert_pem, err = wstep_service.issue(ca, _csr(key).public_bytes(serialization.Encoding.DER),
                                            validity_days=30)
    assert err is None, err
    cert = x509.load_pem_x509_certificate(cert_pem.encode())
    assert isinstance(cert.public_key(), mldsa.MLDSA65PublicKey)


class TestPkcs7ProofOfPossession:
    def test_mldsa_envelope_proves_possession(self):
        key = load_mldsa_key()
        csr = _csr(key)
        assert wstep_service._verify_pkcs7_pop(csr, _pop_envelope(csr, key)) is None

    def test_envelope_signed_by_another_mldsa_key_is_refused(self):
        key = load_mldsa_key()
        csr = _csr(key)
        envelope = _pop_envelope(csr, key_algorithms.generate('ML-DSA-65'))
        assert 'does not match' in wstep_service._verify_pkcs7_pop(csr, envelope)

    def test_forged_mldsa_signature_is_refused(self):
        key = load_mldsa_key()
        csr = _csr(key)
        envelope = _pop_envelope(csr, key)
        sig = bytearray(envelope['signer_infos'][0]['signature'].native)
        sig[0] ^= 0xFF
        envelope['signer_infos'][0]['signature'] = asn1crypto.core.OctetString(bytes(sig))
        assert 'proof of possession failed' in wstep_service._verify_pkcs7_pop(csr, envelope)

    def test_issue_with_mldsa_envelope(self, app, create_ca):
        key = load_mldsa_key()
        csr = _csr(key, 'wstep-pq-pop.example.test')
        with app.app_context():
            ca = _ca(app, create_ca, 'WSTEP RSA CA for ML-DSA PoP')
            cert_pem, err = wstep_service.issue(
                ca, csr.public_bytes(serialization.Encoding.DER), validity_days=30,
                require_pop=False, outer_signed_data=_pop_envelope(csr, key))
        assert err is None, err
        cert = x509.load_pem_x509_certificate(cert_pem.encode())
        assert cert.public_key() == key.public_key()


def _mldsa_leaf(app, ca):
    key = load_mldsa_key()
    cert_pem, _serial = CAService.sign_csr_from_crypto(
        ca=ca, csr=_csr(key, 'wstep-pq-renew.example.test'), validity_days=30, source='test')
    return x509.load_pem_x509_certificate(cert_pem.encode()), key


def _renew_parsed(rst_xml):
    parsed = parse_rst(rst_xml)
    return parsed.security_header, parsed.csr_der, parsed.csr_element


@pytest.mark.parametrize('method', [
    None,   # what an RSA signer would announce
    'http://www.w3.org/2001/04/xmldsig-more#ml-dsa-65',
])
def test_certificate_bound_renewal_names_mldsa(app, create_ca, method):
    """XML-DSig has no ML-DSA method UCM can verify: the renewal says so instead of failing late."""
    with app.app_context():
        ca = _ca(app, create_ca, 'WSTEP RSA CA for ML-DSA renewal')
        cert, key = _mldsa_leaf(app, ca)
        # The signature itself cannot be ML-DSA: an RSA key signs, the token carries the ML-DSA cert.
        rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        rst = _build_signed_rst(cert, rsa_key, _csr(key, 'wstep-pq-renew.example.test'))
        if method:
            rst = rst.replace(b'http://www.w3.org/2001/04/xmldsig-more#rsa-sha256', method.encode())
        header, csr_der, csr_element = _renew_parsed(rst)
        with pytest.raises(ws_security.WSSecurityError, match='ML-DSA-65'):
            ws_security.verify_signed_request(header)
        cert_pem, err = wstep_service.renew(ca, csr_der, header, csr_element, validity_days=30)
    assert cert_pem is None
    assert 'not supported' in err and 'ML-DSA-65' in err
