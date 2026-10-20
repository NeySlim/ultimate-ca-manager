"""Regression tests: proof of possession for PKCS#7/CMC-wrapped WSTEP
requests (``wstep_service._verify_pkcs7_pop``).

Before this fix, ``wstep_service.issue()`` had no cryptographic check at
all that a PKCS#7-wrapped CSR's submitter controlled the CSR's private
key -- a holder of the shared UsernamePassword credential could submit a
public key it doesn't own and receive a UCM-issued certificate for it.

``_REAL_WIN11_CMC_REQUEST`` below is a genuine "Full PKCS#7" (CMC) request
captured from a real Windows 11 client (win11.hagland.domain, 2026-08-09)
via ``certreq -new`` against the lab AD domain, submitted directly to
ucm2.vm.hagland.home's WSTEP UsernamePassword endpoint (confirmed issued:
RequestID 60). It's the ground truth for the wire format this test
suite verifies against -- real CertEnroll embeds no certificate in the
outer envelope at all; the SignerInfo identifies itself purely via a
subjectKeyIdentifier of the CSR's own key, and the CMS signature verifies
directly against that key.
"""
from asn1crypto import cms
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import NameOID

from models import CA, db
from services.wstep import wstep_service
from services.wstep.rst_parser import _unwrap_pkcs7_csr

_REAL_WIN11_CMC_REQUEST = """
-----BEGIN NEW CERTIFICATE REQUEST-----
MIIF4AYJKoZIhvcNAQcCoIIF0TCCBc0CAQMxDzANBglghkgBZQMEAgEFADCCBCYG
CCsGAQUFBwwCoIIEGASCBBQwggQQMG0wawIBAgYKKwYBBAGCNwoKATFaMFgCAQAw
AwIBATFOMEwGCSsGAQQBgjcVFDE/MD0CAQkMFHdpbjExLmhhZ2xhbmQuZG9tYWlu
DBVIQUdMQU5EXEFkbWluaXN0cmF0b3IMC2NlcnRyZXEuZXhlMIIDmaCCA5UCAQEw
ggOOMIICdgIBADAnMSUwIwYDVQQDDBxwb3AtZGlhZy10ZXN0LmhhZ2xhbmQuZG9t
YWluMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA31enK4apkUUX/g8p
YT+smzVqTDsIBJTZZu8+kYor79250b+mf2reKOHWeHKcJVLxeRuVa5E2oDxe3juL
lLf0vo9Wm0zZaGhBFuC75wDGPyWlQtIkYxV/0CysXzrdTXOxrHjbaxe048hjFicQ
CrBmw4QNG46LiKasKEWJnxMJKDJKC1Gse2T++yyVsEq7leh5mePCEuT/CYUofOv3
/S3tf0LoAEzHM8cFHCK1pQ/oQviXfyIGzRCKOz1sw8vENTq5wcso/Y1YlkbAZQpV
u+8a3EkUwe9AhC2BkqaMTjp0+2zetIPUO11PYh4R11hmKo1DYYKgxdNaj2O4xBwl
VVzi/QIDAQABoIIBIDAcBgorBgEEAYI3DQIDMQ4WDDEwLjAuMjYyMDAuMjA+Bgkq
hkiG9w0BCQ4xMTAvMA4GA1UdDwEB/wQEAwIFoDAdBgNVHQ4EFgQU9EwprIfXtbk8
cvhVOftiSLDezjwwTAYJKwYBBAGCNxUUMT8wPQIBCQwUd2luMTEuaGFnbGFuZC5k
b21haW4MFUhBR0xBTkRcQWRtaW5pc3RyYXRvcgwLY2VydHJlcS5leGUwcgYKKwYB
BAGCNw0CAjFkMGICAQEeWgBNAGkAYwByAG8AcwBvAGYAdAAgAFIAUwBBACAAUwBD
AGgAYQBuAG4AZQBsACAAQwByAHkAcAB0AG8AZwByAGEAcABoAGkAYwAgAFAAcgBv
AHYAaQBkAGUAcgMBADANBgkqhkiG9w0BAQsFAAOCAQEAR+Ya1nNVRmBb9DNSbGga
PEEhlMqKnmi8pQcoAXvIyn6eky+08rNdbLkuFNACkcqU4p5ODZkrW2VAZ/O1QFxA
EL9bvYBKkXtUamBeh+hXW785yt2BHdKZmu+jGgTgm2HnwshaT3DuLGZt8Gw6JZLS
HrDjw0o5cgH1Ah4S2rOnC7bJls6hYZ8fgOKFijL6BmWKJiMWiJzRkixpRhjaxxF2
0M2L30H6VQlqtXBlGGn1ESNczQjYAEqT9TB3Sqp4UiOeX7wzUQZoG/2Z+1zXuReW
95hUPd2O9ZvZ0D/DYygZnDzGtji73d7+MQj8bKafba1NWZXpKHJxP4kziYO3KgnP
lDAAMAAxggGLMIIBhwIBA4AU9EwprIfXtbk8cvhVOftiSLDezjwwDQYJYIZIAWUD
BAIBBQCgSjAXBgkqhkiG9w0BCQMxCgYIKwYBBQUHDAIwLwYJKoZIhvcNAQkEMSIE
IKUpeSst8QpjGYnphF3zCrSHhjFIiFV+Nd7oRwis3qNqMA0GCSqGSIb3DQEBAQUA
BIIBACw1uUAMXicM42ptpgHdEX3f4qfn4gMpWeZABk/VC89KEsf5PQ0zWwUHUdqy
IBWsQWDvpTGdoyA2VzQMWyjXajd9lDZ4OFtBQ/ghSluscu1fclzU362Te+1yK8DI
ORN3PqC6ILY11uWYFcLDOj9JdcBXl6EL9KMb/HCBcqKmblJzjmA/T7pz82+mPi14
hQ/0y9jp5pXhAdRSJTTfVjRK3nXqbHNHzqrA7WC+zq/FIIh6btnwTB85mfVnGN3/
VDl6cVR/llwiMubvfdWUFZm86S/UZCcMTxo6+pIgG9S4vbKNSEJccYa3QOGsbvbD
N3vJHaWWVjs9gKOGl/sZpuIeMyI=
-----END NEW CERTIFICATE REQUEST-----
"""


def _pem_to_der(pem_text):
    import base64
    lines = [l for l in pem_text.strip().splitlines() if '-----' not in l]
    return base64.b64decode(''.join(lines))


def _real_csr_and_signed_data():
    der = _pem_to_der(_REAL_WIN11_CMC_REQUEST)
    csr_der, _body_part_id, signed_data = _unwrap_pkcs7_csr(der)
    csr = x509.load_der_x509_csr(csr_der)
    return csr, signed_data


def _unrelated_csr():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'unrelated.example.test')])
    ).sign(key, hashes.SHA256())


class TestVerifyPkcs7Pop:
    def test_accepts_real_captured_windows_request(self):
        csr, signed_data = _real_csr_and_signed_data()
        err = wstep_service._verify_pkcs7_pop(csr, signed_data)
        assert err is None

    def test_rejects_csr_with_different_key(self):
        """A CSR the outer envelope was never signed for -- the actual
        attack this check exists to stop: submitting a public key you
        don't control alongside someone else's (or a fresh, unrelated)
        signed envelope."""
        _real_csr, signed_data = _real_csr_and_signed_data()
        unrelated_csr = _unrelated_csr()
        err = wstep_service._verify_pkcs7_pop(unrelated_csr, signed_data)
        assert err is not None
        assert 'does not match' in err

    def test_rejects_tampered_signature(self):
        """Same signer/SKI, but the signature bytes no longer verify --
        proves verify_cms_signature is actually being called, not just
        the SKI-equality shortcut."""
        csr, signed_data = _real_csr_and_signed_data()

        # Re-encode signer_infos[0]['signature'] with one bit flipped.
        signer_info = signed_data['signer_infos'][0]
        original_sig = signer_info['signature'].native
        tampered_sig = bytearray(original_sig)
        tampered_sig[0] ^= 0xFF
        signer_info['signature'] = bytes(tampered_sig)

        err = wstep_service._verify_pkcs7_pop(csr, signed_data)
        assert err is not None
        assert 'invalid' in err.lower()

    def test_rejects_no_signer_infos(self):
        der = _pem_to_der(_REAL_WIN11_CMC_REQUEST)
        content_info = cms.ContentInfo.load(der)
        signed_data = content_info['content']
        signed_data['signer_infos'] = cms.SignerInfos([])
        csr, _ = _real_csr_and_signed_data()
        err = wstep_service._verify_pkcs7_pop(csr, signed_data)
        assert err == 'PKCS#7 envelope has no signature'

    def test_fips_refusal_is_named(self, monkeypatch):
        from fips_mode import FipsRestricted
        from services.scep import message_parser

        def refuse(*_a, **_k):
            raise FipsRestricted('SHA-1 CMS signatures not available in FIPS mode')
        monkeypatch.setattr(message_parser, 'verify_cms_signature', refuse)
        csr, signed_data = _real_csr_and_signed_data()
        err = wstep_service._verify_pkcs7_pop(csr, signed_data)
        assert 'FIPS' in err and 'proof of possession' not in err


def test_issue_accepts_real_windows_request_end_to_end(app, create_ca):
    """Full pipeline: wstep_service.issue() with the real captured
    envelope succeeds and the issued cert matches the CSR's subject --
    proves the PoP check doesn't break the actual working lab flow."""
    ca_data = create_ca(cn='WSTEP PoP CA')
    with app.app_context():
        ca = db.session.get(CA, ca_data['id'])
        csr, signed_data = _real_csr_and_signed_data()
        cert_pem, err = wstep_service.issue(
            ca, csr.public_bytes(Encoding.DER),
            validity_days=30, require_pop=False, outer_signed_data=signed_data,
        )
        assert err is None, err
        cert = x509.load_pem_x509_certificate(cert_pem.encode())
        assert cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == 'pop-diag-test.hagland.domain'


def test_issue_rejects_pkcs7_request_with_mismatched_key(app, create_ca):
    """End-to-end: outer_signed_data proving possession of a *different*
    key than the CSR's must reject the whole issuance, not just log a
    warning."""
    ca_data = create_ca(cn='WSTEP PoP Reject CA')
    with app.app_context():
        ca = db.session.get(CA, ca_data['id'])
        _real_csr, signed_data = _real_csr_and_signed_data()
        unrelated_csr = _unrelated_csr()
        cert_pem, err = wstep_service.issue(
            ca, unrelated_csr.public_bytes(Encoding.DER),
            validity_days=30, require_pop=False, outer_signed_data=signed_data,
        )
        assert cert_pem is None
        assert err is not None
