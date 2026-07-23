"""Certificate Transparency client and SCT embedding helpers (RFC 6962)."""
import base64
import binascii
import json
import logging
import struct
from typing import Any, Dict, List, Optional, Tuple

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

logger = logging.getLogger(__name__)

# Temporally-sharded logs: entries must land in the shard covering the
# certificate's notAfter. Keep both current-year shards listed; operators
# should override via ct_log_urls as shards roll over.
DEFAULT_CT_LOGS = [
    "https://ct.googleapis.com/logs/us1/argon2026h1/",
    "https://ct.googleapis.com/logs/us1/argon2026h2/",
]

SCT_LIST_OID = "1.3.6.1.4.1.11129.2.4.2"
CT_POISON_OID = "1.3.6.1.4.1.11129.2.4.3"
_SCT_LIST_OBJECT_ID = x509.ObjectIdentifier(SCT_LIST_OID)
_CT_POISON_OBJECT_ID = x509.ObjectIdentifier(CT_POISON_OID)
_MAX_CT_RESPONSE_BYTES = 1024 * 1024
_MAX_UINT16 = (1 << 16) - 1
_MAX_UINT64 = (1 << 64) - 1


def _pem_chain_to_base64(cert_chain_pem: List[str]) -> List[str]:
    chain_b64 = []
    for pem in cert_chain_pem:
        if isinstance(pem, bytes):
            pem = pem.decode("ascii")
        lines = pem.strip().splitlines()
        encoded = "".join(line.strip() for line in lines if not line.startswith("-----"))
        if not encoded:
            raise ValueError("CT submission chain contains an empty certificate")
        chain_b64.append(encoded)
    if not chain_b64:
        raise ValueError("CT submission chain is empty")
    return chain_b64


def _submit_chain(
    log_url: str,
    cert_chain_pem: List[str],
    endpoint: str,
    timeout: int,
) -> Optional[Dict[str, Any]]:
    import ssl
    import urllib.request

    submit_url = log_url.rstrip("/") + endpoint
    try:
        from utils.ssrf_protection import validate_url_not_cloud_metadata

        validate_url_not_cloud_metadata(submit_url)
        payload = json.dumps({"chain": _pem_chain_to_base64(cert_chain_pem)}).encode("utf-8")
        request = urllib.request.Request(
            submit_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        context = ssl.create_default_context()
        with urllib.request.urlopen(request, context=context, timeout=timeout) as response:
            raw = response.read(_MAX_CT_RESPONSE_BYTES + 1)
        if len(raw) > _MAX_CT_RESPONSE_BYTES:
            raise ValueError("CT log response exceeds size limit")
        result = json.loads(raw.decode("utf-8"))
        if not isinstance(result, dict):
            raise ValueError("CT log returned a non-object response")
        return {**result, "log_url": log_url}
    except Exception as exc:
        logger.warning("CT log submission to %s failed: %s", log_url, exc)
        return None


def submit_to_ct_log(
    log_url: str,
    cert_chain_pem: List[str],
    timeout: int = 10,
) -> Optional[Dict[str, Any]]:
    """Submit an already-issued certificate through ``add-chain``."""
    return _submit_chain(log_url, cert_chain_pem, "/ct/v1/add-chain", timeout)


def submit_precert_to_ct_log(
    log_url: str,
    precert_chain_pem: List[str],
    timeout: int = 10,
) -> Optional[Dict[str, Any]]:
    """Submit a CA-signed poisoned pre-certificate through ``add-pre-chain``."""
    return _submit_chain(log_url, precert_chain_pem, "/ct/v1/add-pre-chain", timeout)


def _collect(
    cert_chain_pem: List[str],
    ct_log_urls: Optional[List[str]],
    submitter,
) -> List[Dict[str, Any]]:
    log_urls = DEFAULT_CT_LOGS if ct_log_urls is None else ct_log_urls
    scts = []
    for log_url in log_urls:
        if not isinstance(log_url, str) or not log_url.strip():
            logger.warning("Skipping invalid CT log URL")
            continue
        sct = submitter(log_url, cert_chain_pem)
        if sct:
            scts.append(sct)
            logger.info("Got SCT from %s", log_url)
    return scts


def collect_scts(
    cert_chain_pem: List[str],
    ct_log_urls: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Submit an issued certificate to multiple logs through ``add-chain``."""
    return _collect(cert_chain_pem, ct_log_urls, submit_to_ct_log)


def collect_precert_scts(
    precert_chain_pem: List[str],
    ct_log_urls: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Submit a pre-certificate to multiple logs through ``add-pre-chain``."""
    return _collect(precert_chain_pem, ct_log_urls, submit_precert_to_ct_log)


def _decode_sct(sct: Dict[str, Any]) -> bytes:
    version = sct["sct_version"]
    timestamp = sct["timestamp"]
    if not isinstance(version, int) or version != 0:
        raise ValueError("unsupported SCT version")
    if not isinstance(timestamp, int) or not 0 <= timestamp <= _MAX_UINT64:
        raise ValueError("invalid SCT timestamp")

    log_id = base64.b64decode(sct["id"], validate=True)
    extensions = base64.b64decode(sct.get("extensions", ""), validate=True)
    signature = base64.b64decode(sct["signature"], validate=True)
    if len(log_id) != 32:
        raise ValueError("SCT log ID must be 32 bytes")
    if len(extensions) > _MAX_UINT16:
        raise ValueError("SCT extensions are too large")
    if len(signature) < 4:
        raise ValueError("SCT DigitallySigned value is truncated")
    signature_length = struct.unpack("!H", signature[2:4])[0]
    if len(signature) != signature_length + 4:
        raise ValueError("SCT DigitallySigned length is invalid")

    return b"".join((
        struct.pack("!B", version),
        log_id,
        struct.pack("!Q", timestamp),
        struct.pack("!H", len(extensions)),
        extensions,
        signature,
    ))


def _der_octet_string(value: bytes) -> bytes:
    length = len(value)
    if length < 128:
        encoded_length = bytes([length])
    else:
        length_bytes = length.to_bytes((length.bit_length() + 7) // 8, "big")
        encoded_length = bytes([0x80 | len(length_bytes)]) + length_bytes
    return b"\x04" + encoded_length + value


def _encode_sct_list(
    scts: List[Dict[str, Any]],
) -> Tuple[bytes, List[Dict[str, Any]]]:
    encoded_scts = []
    valid_scts = []
    total_length = 0
    for sct in scts:
        try:
            sct_data = _decode_sct(sct)
            if len(sct_data) > _MAX_UINT16:
                raise ValueError("SCT is too large")
            framed = struct.pack("!H", len(sct_data)) + sct_data
            if total_length + len(framed) > _MAX_UINT16:
                raise ValueError("SCT list is too large")
            encoded_scts.append(framed)
            valid_scts.append(sct)
            total_length += len(framed)
        except (KeyError, TypeError, ValueError, binascii.Error) as exc:
            logger.warning("Failed to encode SCT: %s", exc)

    if not encoded_scts:
        return b"", []

    serialized_list = struct.pack("!H", total_length) + b"".join(encoded_scts)
    return _der_octet_string(serialized_list), valid_scts


def encode_sct_list(scts: List[Dict[str, Any]]) -> bytes:
    """Encode SCTs as the RFC 6962 X.509 extension value.

    The inner value is the TLS ``SignedCertificateTimestampList``. RFC 6962
    §3.3 defines the X.509 extension itself as an ASN.1 OCTET STRING, so the
    returned bytes include that DER wrapper and can be passed directly to
    :class:`~cryptography.x509.UnrecognizedExtension`.
    """
    encoded, _valid_scts = _encode_sct_list(scts)
    return encoded


def _base_builder(certificate: x509.Certificate) -> x509.CertificateBuilder:
    builder = (
        x509.CertificateBuilder()
        .subject_name(certificate.subject)
        .issuer_name(certificate.issuer)
        .public_key(certificate.public_key())
        .serial_number(certificate.serial_number)
        .not_valid_before(certificate.not_valid_before_utc)
        .not_valid_after(certificate.not_valid_after_utc)
    )
    for extension in certificate.extensions:
        if extension.oid in (_SCT_LIST_OBJECT_ID, _CT_POISON_OBJECT_ID):
            continue
        builder = builder.add_extension(extension.value, extension.critical)
    return builder


def embed_scts_in_certificate(
    certificate: x509.Certificate,
    issuer_certificate: x509.Certificate,
    issuer_private_key,
    ct_log_urls: Optional[List[str]] = None,
) -> Tuple[x509.Certificate, List[Dict[str, Any]]]:
    """Run the RFC 6962 pre-certificate flow and return the final certificate.

    The pre-certificate and final certificate share all TBS fields. Their last
    extension is respectively the critical CT poison and the non-critical SCT
    list, and both are signed by the issuing CA.
    """
    base_builder = _base_builder(certificate)
    algorithm = certificate.signature_hash_algorithm
    precertificate = base_builder.add_extension(
        x509.PrecertPoison(), critical=True
    ).sign(issuer_private_key, algorithm, backend=default_backend())

    precert_chain = [
        precertificate.public_bytes(serialization.Encoding.PEM).decode("ascii"),
        issuer_certificate.public_bytes(serialization.Encoding.PEM).decode("ascii"),
    ]
    scts = collect_precert_scts(precert_chain, ct_log_urls)
    encoded_scts, valid_scts = _encode_sct_list(scts)
    if not encoded_scts:
        return certificate, []

    final_certificate = base_builder.add_extension(
        x509.UnrecognizedExtension(_SCT_LIST_OBJECT_ID, encoded_scts),
        critical=False,
    ).sign(issuer_private_key, algorithm, backend=default_backend())
    return final_certificate, valid_scts


def apply_ct_policy(certificate, issuer_certificate, issuer_private_key):
    """Apply the configured Certificate Transparency policy to a freshly signed
    leaf certificate. Reads ``ct_embed_sct`` / ``ct_required`` / ``ct_log_urls``
    from SystemConfig and, when embedding is enabled, re-issues the certificate
    with an embedded SCT list via the pre-certificate flow.

    Returns ``(certificate, embedded_scts)`` — the (possibly re-issued)
    certificate and the list of embedded SCTs (empty when embedding is off or
    produced none). Raises ValueError when ``ct_required`` is set but no CT log
    accepted the pre-certificate — so the policy is enforced identically on
    every issuance path (web, ACME, EST).
    """
    from flask import has_app_context
    # No app/DB context (e.g. a pure-crypto unit test calling sign_csr
    # directly) → CT config is unreadable and this isn't a real issuance
    # request; treat as CT disabled.
    if not has_app_context():
        return certificate, []

    from models import SystemConfig

    ct_embed = SystemConfig.query.filter_by(key='ct_embed_sct').first()
    if not (ct_embed and str(ct_embed.value).lower() == 'true'):
        return certificate, []

    ct_required_config = SystemConfig.query.filter_by(key='ct_required').first()
    ct_required = bool(
        ct_required_config and str(ct_required_config.value).lower() == 'true'
    )

    ct_log_urls = None
    ct_log_urls_config = SystemConfig.query.filter_by(key='ct_log_urls').first()
    if ct_log_urls_config and ct_log_urls_config.value:
        try:
            parsed = json.loads(ct_log_urls_config.value)
            if not isinstance(parsed, list):
                raise ValueError('ct_log_urls must be a JSON list')
            ct_log_urls = parsed
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            logger.warning(f"Invalid CT log configuration: {e}")
            ct_log_urls = []

    embedded_scts = []
    try:
        certificate, embedded_scts = embed_scts_in_certificate(
            certificate=certificate,
            issuer_certificate=issuer_certificate,
            issuer_private_key=issuer_private_key,
            ct_log_urls=ct_log_urls,
        )
    except Exception as e:
        logger.warning(f"CT pre-certificate flow failed: {e}")
        embedded_scts = []

    if embedded_scts:
        logger.info(f"Embedded {len(embedded_scts)} SCT(s) in certificate")
    elif ct_required:
        raise ValueError(
            "Certificate Transparency is required but no CT log accepted "
            "the pre-certificate"
        )
    else:
        logger.warning("All CT log submissions failed; issuing without embedded SCT")

    return certificate, embedded_scts
