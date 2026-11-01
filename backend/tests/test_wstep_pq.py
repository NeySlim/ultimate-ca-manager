"""WSTEP and ML-DSA: a bare CSR and a PKCS#7 proof of possession signed per RFC 9882
are accepted; certificate-bound renewal (XML-DSig) is refused with a message."""
import json

import asn1crypto.cms
import asn1crypto.core
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import mldsa, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from models import CA, CATemplatePin, db
from models.certificate_template import CertificateTemplate
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


def _client_auth_csr(key, cn):
    builder = (x509.CertificateSigningRequestBuilder()
               .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
               .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False))
    return builder.sign(key, None if key_algorithms.label_for_private_key(key).startswith('ML-DSA')
                        else hashes.SHA256())


@pytest.fixture
def pinned_templates(app, create_ca):
    """A CA pinned to client-auth templates of the given key types; name -> template id."""
    made = []

    def _pin(cn, *key_types):
        ca_data = create_ca(cn=cn)
        ids = {}
        for key_type in key_types:
            t = CertificateTemplate(
                name=f'{cn} {key_type}', template_type='usr_cert', key_type=key_type,
                validity_days=30, digest='sha256', is_active=True,
                extensions_template=json.dumps({'extended_key_usage': ['clientAuth']}))
            db.session.add(t)
            db.session.flush()
            db.session.add(CATemplatePin(ca_id=ca_data['id'], template_id=t.id))
            db.session.commit()
            made.append(t.id)
            ids[key_type] = t.id
        return db.session.get(CA, ca_data['id']), ids
    yield _pin
    with app.app_context():
        CATemplatePin.query.filter(CATemplatePin.template_id.in_(made)).delete(synchronize_session=False)
        CertificateTemplate.query.filter(CertificateTemplate.id.in_(made)).delete(synchronize_session=False)
        db.session.commit()


def _names_template(cert, policy_oid):
    """Whether the MS-CRTD CertificateTemplate extension names *policy_oid*."""
    return cert.extensions.get_extension_for_class(
        x509.MSCertificateTemplate).value.template_id.dotted_string == policy_oid


class TestTemplateKeyFamily:
    """WSTEP picks a template by EKU: the key must still be of the template's family."""

    @pytest.mark.parametrize('template_key, csr_key, csr_label', [
        ('ML-DSA-65', 'RSA-2048', 'RSA-2048'),
        ('RSA-2048', 'ML-DSA-65', 'ML-DSA-65'),
    ])
    def test_a_key_of_another_family_is_refused(self, app, pinned_templates,
                                                template_key, csr_key, csr_label):
        with app.app_context():
            ca, _ = pinned_templates(f'WSTEP family CA {template_key}', template_key)
            csr = _client_auth_csr(key_algorithms.generate(csr_key), 'family.pq.example.test')
            cert_pem, err = wstep_service.issue(ca, csr.public_bytes(serialization.Encoding.DER),
                                                validity_days=30)
        assert cert_pem is None
        assert err == (f"Template 'WSTEP family CA {template_key} {template_key}' issues "
                       f'{template_key} keys, not {csr_label}'), err

    @pytest.mark.parametrize('csr_key', ['ML-DSA-65', 'RSA-2048'])
    def test_the_template_of_the_key_family_wins_an_eku_tie(self, app, pinned_templates, csr_key):
        from services.xcep.policy_builder import _policy_oid_for_template
        with app.app_context():
            ca, ids = pinned_templates(f'WSTEP family tie CA {csr_key}', 'RSA-2048', 'ML-DSA-65')
            csr = _client_auth_csr(key_algorithms.generate(csr_key), 'tie.pq.example.test')
            cert_pem, err = wstep_service.issue(ca, csr.public_bytes(serialization.Encoding.DER),
                                                validity_days=30)
            assert err is None, err
            expected = _policy_oid_for_template(ca, db.session.get(CertificateTemplate, ids[csr_key]))
        cert = x509.load_pem_x509_certificate(cert_pem.encode())
        assert key_algorithms.label_for_public_key(cert.public_key()) == csr_key
        assert _names_template(cert, expected)


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
