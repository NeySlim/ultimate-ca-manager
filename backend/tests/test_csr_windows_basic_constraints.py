"""A request carrying BasicConstraints CA:FALSE with a path length, as Windows
clients write it, must still issue on every path."""
import asn1crypto.cms
import asn1crypto.core
import asn1crypto.csr
import asn1crypto.x509
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import AttributeOID, ExtensionOID, NameOID

from models import SystemConfig, db
from services.scep.scep_service import SCEPService
from tests.test_scep_rfc8894_operations import (
    PKI_STATUS_OID, _build_request, _client_identity, _decrypt_response,
    _load_ca_material, _response_attributes,
)
from utils.csr_extensions import csr_extensions

CHALLENGE = 'windows horse battery staple'


class _ExtSet(asn1crypto.core.SetOf):
    _child_spec = asn1crypto.x509.Extensions


class _MsAttr(asn1crypto.core.Sequence):
    _fields = [('type', asn1crypto.core.ObjectIdentifier), ('values', _ExtSet)]


class _MsAttrs(asn1crypto.core.SetOf):
    _child_spec = _MsAttr


def _windows_shaped_csr(key, cn, challenge=None, microsoft_attribute=False):
    """A CSR the way Windows clients write it: SAN, and CA:FALSE with pathLen 0,
    under the PKCS#9 attribute or Microsoft's own."""
    builder = (x509.CertificateSigningRequestBuilder()
               .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
               .add_extension(x509.SubjectAlternativeName([x509.DNSName(cn)]), critical=False))
    if challenge:
        builder = builder.add_attribute(AttributeOID.CHALLENGE_PASSWORD, challenge.encode())
    clean = builder.sign(key, hashes.SHA256())
    req = asn1crypto.csr.CertificationRequest.load(clean.public_bytes(serialization.Encoding.DER))
    info = req['certification_request_info']
    attrs = []
    for attr in info['attributes']:
        if attr['type'].native != 'extension_request':
            attrs.append(attr)
            continue
        exts = list(attr['values'][0])
        exts.append(asn1crypto.x509.Extension({
            'extn_id': 'basic_constraints', 'critical': True,
            'extn_value': asn1crypto.x509.BasicConstraints({'ca': False, 'path_len_constraint': 0}),
        }))
        attrs.append(asn1crypto.csr.CRIAttribute({'type': 'extension_request',
                                                  'values': [asn1crypto.x509.Extensions(exts)]}))
    if microsoft_attribute:
        ext_sets = [a['values'][0] for a in attrs if a['type'].native == 'extension_request']
        ms = _MsAttrs([_MsAttr({'type': '1.3.6.1.4.1.311.2.1.14', 'values': _ExtSet(ext_sets)})])
        attrs = [a for a in attrs if a['type'].native != 'extension_request']
        info['attributes'] = asn1crypto.csr.CRIAttributes.load(
            asn1crypto.csr.CRIAttributes(attrs).dump()[:0] + ms.dump()) if not attrs else \
            asn1crypto.csr.CRIAttributes(attrs + list(asn1crypto.csr.CRIAttributes.load(ms.dump())))
    else:
        info['attributes'] = asn1crypto.csr.CRIAttributes(attrs)
    req['signature'] = key.sign(info.dump(), padding.PKCS1v15(), hashes.SHA256())
    return x509.load_der_x509_csr(req.dump())


class TestCsrExtensionsHelper:
    def test_windows_basic_constraints_is_read_as_an_end_entity(self):
        key = rsa.generate_private_key(65537, 2048)
        csr = _windows_shaped_csr(key, 'win.example.test')
        with pytest.raises(ValueError):
            _ = csr.extensions  # the shape cryptography refuses
        exts = csr_extensions(csr)
        bc = exts.get_extension_for_class(x509.BasicConstraints).value
        assert bc == x509.BasicConstraints(ca=False, path_length=None)
        san = exts.get_extension_for_class(x509.SubjectAlternativeName).value
        assert san.get_values_for_type(x509.DNSName) == ['win.example.test']

    def test_microsoft_attribute_is_read_the_same_way(self):
        key = rsa.generate_private_key(65537, 2048)
        csr = _windows_shaped_csr(key, 'ms.example.test', microsoft_attribute=True)
        with pytest.raises(ValueError):
            _ = csr.extensions
        exts = csr_extensions(csr)
        assert exts.get_extension_for_class(x509.BasicConstraints).value == \
            x509.BasicConstraints(ca=False, path_length=None)
        assert exts.get_extension_for_class(x509.SubjectAlternativeName).value \
            .get_values_for_type(x509.DNSName) == ['ms.example.test']

    def test_a_well_formed_csr_is_read_as_is(self):
        key = rsa.generate_private_key(65537, 2048)
        csr = (x509.CertificateSigningRequestBuilder()
               .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'plain')]))
               .add_extension(x509.SubjectAlternativeName([x509.DNSName('plain')]), critical=False)
               .sign(key, hashes.SHA256()))
        assert list(csr_extensions(csr)) == list(csr.extensions)


@pytest.fixture
def scep_ca(app, create_ca):
    ca_data = create_ca(cn='SCEP Windows CSR CA')
    with app.app_context():
        db.session.add(SystemConfig(key=f'scep_challenge_{ca_data["id"]}', value=CHALLENGE))
        db.session.commit()
    yield ca_data
    with app.app_context():
        row = SystemConfig.query.filter_by(key=f'scep_challenge_{ca_data["id"]}').first()
        if row:
            db.session.delete(row)
            db.session.commit()


def test_windows_shaped_request_is_issued(app, scep_ca):
    with app.app_context():
        ca, ca_cert, _ = _load_ca_material(scep_ca['id'])
        signer_cert, key = _client_identity('windows device')
        csr = _windows_shaped_csr(key, 'win-device.example.test', CHALLENGE)
        request = _build_request(ca_cert, signer_cert, key, 19,
                                 csr.public_bytes(serialization.Encoding.DER), b'windows-nonce-16')
        response, status = SCEPService(ca.refid, challenge_password=CHALLENGE,
                                       auto_approve=True).process_pkcs_req(request, '127.0.0.1')
        attrs = _response_attributes(response)
        assert status == 200 and attrs[PKI_STATUS_OID] == '0', attrs
        degenerate = asn1crypto.cms.ContentInfo.load(_decrypt_response(response, key, signer_cert))
        issued = x509.load_der_x509_certificate(degenerate['content']['certificates'][0].chosen.dump())
        assert issued.extensions.get_extension_for_class(x509.BasicConstraints).value == \
            x509.BasicConstraints(ca=False, path_length=None)
        assert issued.extensions.get_extension_for_class(x509.SubjectAlternativeName).value \
            .get_values_for_type(x509.DNSName) == ['win-device.example.test']


def test_sign_csr_issues_a_windows_shaped_request():
    """The shared signer behind WSTEP, EST, ACME and the REST sign path."""
    from datetime import datetime, timedelta, timezone
    from services.trust_store.trust_store_service import TrustStoreService
    ca_key = rsa.generate_private_key(65537, 2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Windows CSR CA')])
    ca_cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
               .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
               .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
               .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365))
               .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
               .sign(ca_key, hashes.SHA256()))
    key = rsa.generate_private_key(65537, 2048)
    csr = _windows_shaped_csr(key, 'signed.example.test')
    cert_pem = TrustStoreService.sign_csr(csr_pem=csr.public_bytes(serialization.Encoding.PEM),
                                          ca_cert=ca_cert, ca_private_key=ca_key, validity_days=30)
    issued = x509.load_pem_x509_certificate(cert_pem if isinstance(cert_pem, bytes) else cert_pem.encode())
    assert issued.extensions.get_extension_for_class(x509.BasicConstraints).value == \
        x509.BasicConstraints(ca=False, path_length=None)
    assert issued.extensions.get_extension_for_class(x509.SubjectAlternativeName).value \
        .get_values_for_type(x509.DNSName) == ['signed.example.test']
