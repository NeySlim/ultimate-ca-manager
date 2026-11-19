"""Tests for the SID security extension (szOID_NTDS_CA_SECURITY_EXT,
1.3.6.1.4.1.311.25.2) used for KB5014754 strong certificate mapping -- see
services/trust_store/csr_operations_mixin.py's _ad_security_extension and
services/wstep/wstep_service.py's issue().

The golden case is not spec-derived: it's the exact byte sequence captured
this session from a real certificate issued by dc1.hagland.domain's own
Enterprise CA (a genuine Windows Server AD CS install), for a real AD
object's SID. Reproducing those bytes exactly is the strongest available
verification -- this codebase's established practice (PKCS#7 PoP, the
CertificateTemplateOID extension, the naked-CSR msPKI-Certificate-Name-Flag
value) has repeatedly found that Microsoft-proprietary wire formats diverge
from published spec text in ways only caught by testing against a real
ADCS install.
"""
import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from datetime import datetime, timedelta, timezone

from services.trust_store.csr_operations_mixin import (
    _SID_SECURITY_EXT_OID,
    _ad_security_extension,
    ad_security_extension_sid,
)
from services.trust_store.trust_store_service import TrustStoreService

# Captured from dc1.hagland.domain's real Kerberos Authentication
# certificate (issued by the lab's real "Hagland Domain Root CA" Enterprise
# CA), via PowerShell: $c.Extensions | Where-Object Oid -eq
# '1.3.6.1.4.1.311.25.2'. Confirmed non-critical.
_REAL_CAPTURED_EXTENSION_HEX = (
    '303fa03d060a2b060104018237190201a02f042d532d312d352d32312d31363038'
    '3130343635372d3633303738333830352d313437333338373132312d31303030'
)
_REAL_CAPTURED_SID = 'S-1-5-21-1608104657-630783805-1473387121-1000'


class TestAdSecurityExtension:
    def test_matches_real_captured_bytes_exactly(self):
        ext = _ad_security_extension(_REAL_CAPTURED_SID)
        assert ext.value.hex() == _REAL_CAPTURED_EXTENSION_HEX

    def test_oid(self):
        ext = _ad_security_extension(_REAL_CAPTURED_SID)
        assert ext.oid == _SID_SECURITY_EXT_OID
        assert ext.oid.dotted_string == '1.3.6.1.4.1.311.25.2'

    def test_different_sid_produces_different_bytes(self):
        """Not just a hardcoded return value -- the SID string is actually
        encoded into the structure."""
        ext_a = _ad_security_extension('S-1-5-21-1-2-3-1000')
        ext_b = _ad_security_extension('S-1-5-21-1-2-3-1001')
        assert ext_a.value != ext_b.value


def _test_ca():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'SID Extension Test CA')])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    return cert, key


def _csr(common_name='device.hagland.domain'):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    ).sign(key, hashes.SHA256())
    return csr, key


class TestSignCsrRequesterSid:
    """TrustStoreService.sign_csr's requester_sid kwarg -- the plumbing
    that carries a resolved SID into the issued certificate."""

    def test_requester_sid_none_adds_no_extension(self, app):
        ca_cert, ca_key = _test_ca()
        csr, _key = _csr()
        with app.app_context():
            pem = TrustStoreService.sign_csr(
                csr_pem=csr.public_bytes(serialization.Encoding.PEM),
                ca_cert=ca_cert, ca_private_key=ca_key, validity_days=30,
            )
        cert = x509.load_pem_x509_certificate(pem, default_backend())
        with pytest.raises(x509.ExtensionNotFound):
            cert.extensions.get_extension_for_oid(_SID_SECURITY_EXT_OID)

    def test_requester_sid_set_adds_extension(self, app):
        ca_cert, ca_key = _test_ca()
        csr, _key = _csr()
        with app.app_context():
            pem = TrustStoreService.sign_csr(
                csr_pem=csr.public_bytes(serialization.Encoding.PEM),
                ca_cert=ca_cert, ca_private_key=ca_key, validity_days=30,
                requester_sid=_REAL_CAPTURED_SID,
            )
        cert = x509.load_pem_x509_certificate(pem, default_backend())
        ext = cert.extensions.get_extension_for_oid(_SID_SECURITY_EXT_OID)
        assert ext.critical is False
        assert ext.value.value.hex() == _REAL_CAPTURED_EXTENSION_HEX


def _cert_with(ext_value=None):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'sid-reader')])
    now = datetime.now(timezone.utc)
    builder = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
               .serial_number(x509.random_serial_number()).not_valid_before(now)
               .not_valid_after(now + timedelta(days=1)))
    if ext_value is not None:
        builder = builder.add_extension(x509.UnrecognizedExtension(_SID_SECURITY_EXT_OID, ext_value),
                                        critical=False)
    return builder.sign(key, hashes.SHA256())


class TestAdSecurityExtensionSid:
    """Reading the SID back, for a renewal to carry it over unchanged."""

    def test_reads_the_real_captured_extension(self):
        cert = _cert_with(bytes.fromhex(_REAL_CAPTURED_EXTENSION_HEX))
        assert ad_security_extension_sid(cert) == _REAL_CAPTURED_SID

    def test_no_extension_is_none(self):
        assert ad_security_extension_sid(_cert_with()) is None

    @pytest.mark.parametrize('value', [
        b'\x30\x00',  # no entry
        b'garbage',
        # two entries
        bytes.fromhex('307e' + _REAL_CAPTURED_EXTENSION_HEX[4:] * 2),
        # another type OID (…25.2.2) in the entry
        bytes.fromhex(_REAL_CAPTURED_EXTENSION_HEX.replace('2b060104018237190201', '2b060104018237190202')),
        # BER long-form length: not what a renewal would write back
        bytes.fromhex('30813f' + _REAL_CAPTURED_EXTENSION_HEX[4:]),
        # value that is not a SID string
        _ad_security_extension('S-1-5-21-x').value,
        _ad_security_extension('S-1-5').value,
    ])
    def test_unreadable_extension_is_none(self, value):
        assert ad_security_extension_sid(_cert_with(value)) is None
