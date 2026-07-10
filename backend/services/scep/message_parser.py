"""
SCEP Message Parser - PKCS#7 message parsing, envelope decryption,
and CMS signature verification (RFC 8894 §3.2.1, §5.4 of RFC 5652).
"""
import logging
from typing import Dict, Any, Optional

import asn1crypto.cms
import asn1crypto.core
import asn1crypto.x509
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

logger = logging.getLogger(__name__)


# Mapping for SignerInfo.digest_algorithm (cms native names) → cryptography hash
_DIGEST_MAP = {
    "sha1": hashes.SHA1,
    "sha224": hashes.SHA224,
    "sha256": hashes.SHA256,
    "sha384": hashes.SHA384,
    "sha512": hashes.SHA512,
}

# Hash algorithms we are *willing to verify* on incoming CMS signatures.
# MD5 and SHA-1 are intentionally accepted on inbound messages because some
# legacy SCEP clients still sign with them, but we never *advertise* them in
# GetCACaps and never sign outbound responses with them.
_INBOUND_DIGEST_ALLOWED = {"sha1", "sha224", "sha256", "sha384", "sha512"}


def _coerce_message_type(raw) -> Optional[int]:
    """Normalize a SCEP messageType attribute value to int.

    RFC 8894 §3.2.1.2 says messageType is a PrintableString containing the
    decimal representation of the message type. Some old clients still send
    raw INTEGER, so we accept both.
    """
    if raw is None:
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, bytes):
        try:
            return int(raw.decode("ascii"))
        except (UnicodeDecodeError, ValueError):
            try:
                return int.from_bytes(raw, "big")
            except Exception:
                return None
    if isinstance(raw, str):
        try:
            return int(raw)
        except ValueError:
            return None
    return None


def extract_scep_attributes(signed_data) -> Dict[str, Any]:
    """Extract SCEP attributes from the SignerInfo signed attributes.

    Returns a dict with normalized values:
        transactionID    → str
        messageType      → int (always)
        senderNonce      → bytes
        challengePassword→ str
    """
    attrs: Dict[str, Any] = {}
    try:
        signer_infos = signed_data["signer_infos"]
        if len(signer_infos) == 0:
            return attrs
        signer_info = signer_infos[0]
        signed_attrs = signer_info["signed_attrs"]
        for attr in signed_attrs:
            attr_type = attr["type"].native
            attr_values = attr["values"]
            if len(attr_values) == 0:
                continue
            value = attr_values[0]
            native = value.native
            if attr_type == "2.16.840.1.113733.1.9.7":  # transactionID
                attrs["transactionID"] = (
                    native.decode("utf-8") if isinstance(native, bytes) else native
                )
            elif attr_type == "2.16.840.1.113733.1.9.2":  # messageType
                attrs["messageType"] = _coerce_message_type(native)
            elif attr_type == "2.16.840.1.113733.1.9.5":  # senderNonce
                attrs["senderNonce"] = native
            elif attr_type == "1.2.840.113549.1.9.7":  # challengePassword
                attrs["challengePassword"] = native
    except Exception as e:
        logger.error(f"SCEP: Error extracting attributes: {e}")
    return attrs


def extract_signer_certificate(signed_data) -> Optional[x509.Certificate]:
    """Return the first end-entity Certificate carried in SignedData, if any."""
    try:
        certs = signed_data["certificates"]
    except KeyError:
        return None
    if not certs or len(certs) == 0:
        return None
    for choice in certs:
        # CertificateChoices: only 'certificate' carries an X.509 cert
        try:
            name = choice.name
        except AttributeError:
            name = None
        if name and name != "certificate":
            continue
        try:
            cert_der = choice.chosen.dump() if name == "certificate" else choice.dump()
            return x509.load_der_x509_certificate(cert_der, default_backend())
        except Exception:
            continue
    return None


def verify_cms_signature(signed_data, signer_cert: x509.Certificate) -> None:
    """Verify the CMS SignerInfo signature against signer_cert's public key.

    This is the *outer* signature wrapping the SCEP envelope. RFC 8894 §3.1
    requires it to be validated before processing the payload — without this
    check, an attacker who can deliver bytes to /scep can submit any CSR for
    enrollment.

    Raises:
        ValueError: if the message is malformed or unsupported.
        InvalidSignature: if the signature does not verify.
    """
    signer_infos = signed_data["signer_infos"]
    if len(signer_infos) == 0:
        raise ValueError("SCEP CMS message has no SignerInfo")
    signer_info = signer_infos[0]

    digest_name = signer_info["digest_algorithm"]["algorithm"].native
    if digest_name not in _INBOUND_DIGEST_ALLOWED:
        raise ValueError(f"Unsupported digest algorithm in CMS signature: {digest_name}")
    hash_cls = _DIGEST_MAP.get(digest_name)
    if hash_cls is None:
        raise ValueError(f"Unknown digest algorithm: {digest_name}")

    sig_alg = signer_info["signature_algorithm"]["algorithm"].native
    if sig_alg not in ("rsassa_pkcs1v15", "rsa", "sha1_rsa", "sha256_rsa",
                       "sha384_rsa", "sha512_rsa"):
        raise ValueError(f"Unsupported CMS signature algorithm: {sig_alg}")

    signature = signer_info["signature"].native
    if not isinstance(signature, (bytes, bytearray)):
        raise ValueError("CMS SignerInfo.signature is not OCTET STRING")

    # The bytes covered by the signature are the DER encoding of signedAttrs
    # *re-tagged* from the IMPLICIT [0] of SignerInfo (0xA0) to the explicit
    # SET-OF tag (0x31), per RFC 5652 §5.4.
    signed_attrs = signer_info["signed_attrs"]
    raw = signed_attrs.dump()  # IMPLICIT [0], starts with 0xA0
    if not raw or raw[0] != 0xA0:
        # Some encoders may already produce SET; just verify as-is in that case.
        signed_bytes = raw
    else:
        signed_bytes = b"\x31" + raw[1:]

    public_key = signer_cert.public_key()
    public_key.verify(
        bytes(signature),
        signed_bytes,
        padding.PKCS1v15(),
        hash_cls(),
    )

    # Additionally enforce that the messageDigest signed-attribute matches
    # the actual encapsulated content (RFC 5652 §11.2). Without this check,
    # an attacker could swap the EnvelopedData while keeping the outer
    # signature valid.
    try:
        encap = signed_data["encap_content_info"]
        content_field = encap["content"]
        if content_field is None or not content_field.contents:
            return  # detached / empty content — nothing to bind
        content_bytes = content_field.native
        if not isinstance(content_bytes, (bytes, bytearray)):
            return
    except Exception:
        return

    declared_digest = None
    for attr in signed_attrs:
        if attr["type"].native == "message_digest":
            vals = attr["values"]
            if len(vals) > 0:
                declared_digest = vals[0].native
                break
    if declared_digest is None:
        raise ValueError("CMS signedAttrs missing required messageDigest attribute")

    h = hashes.Hash(hash_cls())
    h.update(bytes(content_bytes))
    actual_digest = h.finalize()
    if not _consteq(declared_digest, actual_digest):
        raise InvalidSignature(
            "CMS messageDigest does not match encapsulated content"
        )


def _consteq(a: bytes, b: bytes) -> bool:
    if len(a) != len(b):
        return False
    r = 0
    for x, y in zip(a, b):
        r |= x ^ y
    return r == 0


def decrypt_scep_envelope(encrypted_bytes: bytes, ca_key) -> bytes:
    """
    Decrypt a SCEP EnvelopedData structure using the CA private key.

    Args:
        encrypted_bytes: DER-encoded ContentInfo containing EnvelopedData
        ca_key: CA RSA private key for CEK decryption

    Returns:
        Decrypted plaintext (the CSR DER bytes for PKCSReq/RenewalReq, or
        IssuerAndSubject DER for GetCertInitial).

    Raises:
        ValueError: on unsupported algorithm or bad padding
    """
    envdata = asn1crypto.cms.ContentInfo.load(encrypted_bytes)

    if envdata["content_type"].native != "enveloped_data":
        # Not enveloped — return as-is (shouldn't happen in modern SCEP)
        return encrypted_bytes

    # asn1crypto handles both DER and BER (including Apple's indefinite-length
    # BER encoding) — pyasn1's DER decoder rejected it with "Indefinite length
    # encoding not supported".
    env = envdata["content"]

    # Get recipient info — KTRI (RSA key transport) for SCEP
    ktri = env["recipient_infos"][0].chosen
    encrypted_key_bytes = ktri["encrypted_key"].native

    content_encryption_key = ca_key.decrypt(encrypted_key_bytes, padding.PKCS1v15())

    eci = env["encrypted_content_info"]
    encrypted_content_bytes = eci["encrypted_content"].native
    alg_id = eci["content_encryption_algorithm"]
    alg_oid = alg_id["algorithm"].dotted

    # Extract IV — CBC parameter is a plain OctetString (RFC 3370/3565)
    params = alg_id["parameters"]
    if params:
        iv = asn1crypto.core.OctetString.load(params.dump()).native
    else:
        iv = b"\x00" * 8

    if "1.3.14.3.2.7" in alg_oid:  # DES
        logger.warning("SCEP client using DES encryption — rejected (insecure)")
        raise ValueError("DES encryption is not supported — use AES or 3DES")
    elif "1.2.840.113549.3.7" in alg_oid:  # 3DES
        logger.warning("SCEP client using 3DES encryption — deprecated, prefer AES")
        decryptor = Cipher(TripleDES(content_encryption_key), modes.CBC(iv)).decryptor()
        plaintext = decryptor.update(encrypted_content_bytes) + decryptor.finalize()
        pad_len = plaintext[-1]
        if pad_len < 1 or pad_len > 8 or not all(  # 3DES block size = 8 bytes
            b == pad_len for b in plaintext[-pad_len:]
        ):
            raise ValueError("Invalid PKCS#7 padding in SCEP message")
        return plaintext[:-pad_len]
    elif "2.16.840.1.101.3.4.1" in alg_oid:  # AES (any variant)
        decryptor = Cipher(algorithms.AES(content_encryption_key), modes.CBC(iv)).decryptor()
        plaintext = decryptor.update(encrypted_content_bytes) + decryptor.finalize()
        pad_len = plaintext[-1]
        if pad_len < 1 or pad_len > 16 or not all(  # AES block size = 16 bytes
            b == pad_len for b in plaintext[-pad_len:]
        ):
            raise ValueError("Invalid PKCS#7 padding in SCEP message")
        return plaintext[:-pad_len]
    else:
        raise ValueError(f"Unsupported encryption algorithm: {alg_oid}")
