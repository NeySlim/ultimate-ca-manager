"""WS-Security signatures are only accepted with SHA-2 algorithms."""
import base64
import datetime

import pytest
import xmlsec
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import NameOID
from lxml import etree

from services.wstep.soap_envelope import SOAP_NS, WSSE_NS, WSU_NS
from services.wstep.ws_security import WSSecurityError, verify_signed_request


C = xmlsec.constants


def _self_signed(key):
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'wstep-alg.example.test')])
    now = datetime.datetime.now(datetime.timezone.utc)
    return (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )


@pytest.fixture(scope='module')
def rsa_signer():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key, _self_signed(key)


@pytest.fixture(scope='module')
def ec_signer():
    key = ec.generate_private_key(ec.SECP256R1())
    return key, _self_signed(key)


def _signed_security_header(signer, sign_transform, digest_transform):
    """A wsse:Security header whose ds:Signature covers the Body, signed by xmlsec."""
    key, cert = signer
    envelope = etree.Element('{%s}Envelope' % SOAP_NS,
                             nsmap={'s': SOAP_NS, 'wsse': WSSE_NS, 'wsu': WSU_NS})
    header = etree.SubElement(envelope, '{%s}Header' % SOAP_NS)
    security = etree.SubElement(header, '{%s}Security' % WSSE_NS)
    etree.SubElement(security, '{%s}BinarySecurityToken' % WSSE_NS).text = (
        base64.b64encode(cert.public_bytes(serialization.Encoding.DER)).decode()
    )
    body = etree.SubElement(envelope, '{%s}Body' % SOAP_NS)
    body.set('{%s}Id' % WSU_NS, 'body-1')
    body.text = 'payload'

    sig_node = xmlsec.template.create(security, C.TransformExclC14N, sign_transform)
    security.append(sig_node)
    ref = xmlsec.template.add_reference(sig_node, digest_transform, uri='#body-1')
    xmlsec.template.add_transform(ref, C.TransformExclC14N)

    ctx = xmlsec.SignatureContext()
    ctx.register_id(body, id_attr='Id', id_ns=WSU_NS)
    key_pem = key.private_bytes(serialization.Encoding.PEM,
                                serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
    ctx.key = xmlsec.Key.from_memory(key_pem, C.KeyDataFormatPem)
    ctx.sign(sig_node)
    # Reparse so verification sees the document as a client would send it.
    reparsed = etree.fromstring(etree.tostring(envelope))
    return reparsed.find('{%s}Header/{%s}Security' % (SOAP_NS, WSSE_NS))


@pytest.mark.parametrize('sign_transform,digest_transform', [
    (C.TransformRsaSha256, C.TransformSha256),
    (C.TransformRsaSha384, C.TransformSha384),
    (C.TransformRsaSha512, C.TransformSha512),
])
def test_rsa_sha2_signatures_are_accepted(rsa_signer, sign_transform, digest_transform):
    cert_der, _signed = verify_signed_request(
        _signed_security_header(rsa_signer, sign_transform, digest_transform))
    assert cert_der == rsa_signer[1].public_bytes(serialization.Encoding.DER)


@pytest.mark.parametrize('sign_transform', [
    C.TransformEcdsaSha256, C.TransformEcdsaSha384, C.TransformEcdsaSha512,
])
def test_ecdsa_sha2_signatures_are_accepted(ec_signer, sign_transform):
    verify_signed_request(_signed_security_header(ec_signer, sign_transform, C.TransformSha256))


def test_rsa_sha1_signature_is_refused(rsa_signer):
    header = _signed_security_header(rsa_signer, C.TransformRsaSha1, C.TransformSha256)
    with pytest.raises(WSSecurityError, match=r'xmldsig#rsa-sha1'):
        verify_signed_request(header)


def test_ecdsa_sha1_signature_is_refused(ec_signer):
    header = _signed_security_header(ec_signer, C.TransformEcdsaSha1, C.TransformSha256)
    with pytest.raises(WSSecurityError, match=r'ecdsa-sha1'):
        verify_signed_request(header)


def test_sha1_digest_is_refused(rsa_signer):
    header = _signed_security_header(rsa_signer, C.TransformRsaSha256, C.TransformSha1)
    with pytest.raises(WSSecurityError, match=r'xmldsig#sha1'):
        verify_signed_request(header)


def test_sha224_signature_is_refused(rsa_signer):
    header = _signed_security_header(rsa_signer, C.TransformRsaSha224, C.TransformSha256)
    with pytest.raises(WSSecurityError, match=r'rsa-sha224'):
        verify_signed_request(header)


def test_hmac_signature_method_is_refused(rsa_signer):
    """An HMAC SignatureMethod is never a public-key signature, whatever its digest."""
    header = _signed_security_header(rsa_signer, C.TransformRsaSha256, C.TransformSha256)
    method = header.find('.//{http://www.w3.org/2000/09/xmldsig#}SignatureMethod')
    method.set('Algorithm', C.TransformHmacSha256.href)
    with pytest.raises(WSSecurityError, match=r'hmac-sha256'):
        verify_signed_request(header)


def test_missing_signature_method_is_refused(rsa_signer):
    header = _signed_security_header(rsa_signer, C.TransformRsaSha256, C.TransformSha256)
    method = header.find('.//{http://www.w3.org/2000/09/xmldsig#}SignatureMethod')
    method.getparent().remove(method)
    with pytest.raises(WSSecurityError, match=r'SignatureMethod'):
        verify_signed_request(header)
