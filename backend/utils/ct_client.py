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

from utils.signing_hash import rsa_padding_for

logger = logging.getLogger(__name__)

# Temporally-sharded logs accept only certificates whose notAfter falls in
# their window: two operators (Chrome policy), shards covering the next 200 days
# as of October 2026. Shards retire as they age; override via ct_log_urls.
DEFAULT_CT_LOGS = [
    "https://ct.googleapis.com/logs/us1/argon2026h2/",
    "https://ct.googleapis.com/logs/us1/argon2027h1/",
    "https://ct.cloudflare.com/logs/nimbus2026/",
    "https://ct.cloudflare.com/logs/nimbus2027/",
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
    from utils.ssrf_protection import safe_request_post

    submit_url = log_url.rstrip("/") + endpoint
    try:
        payload = json.dumps({"chain": _pem_chain_to_base64(cert_chain_pem)}).encode("utf-8")
        # Resolved, vetted and pinned; a CT log answers in place (RFC 6962), so
        # a redirect is a failure, never followed.
        with safe_request_post(
            submit_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            timeout=timeout,
            stream=True,
            allow_redirects=False,
        ) as response:
            if response.status_code != 200:
                raise ValueError(f"CT log answered HTTP {response.status_code}")
            raw = response.raw.read(_MAX_CT_RESPONSE_BYTES + 1, decode_content=True)
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
    ).sign(issuer_private_key, algorithm, backend=default_backend(),
           rsa_padding=rsa_padding_for(issuer_private_key, algorithm))

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
    ).sign(issuer_private_key, algorithm, backend=default_backend(),
           rsa_padding=rsa_padding_for(issuer_private_key, algorithm))
    return final_certificate, valid_scts


def _configured_log_urls():
    """``ct_log_urls`` as a list, None for the defaults, [] when malformed."""
    from models import SystemConfig

    row = SystemConfig.query.filter_by(key='ct_log_urls').first()
    if not (row and row.value):
        return None
    try:
        parsed = json.loads(row.value)
        if not isinstance(parsed, list):
            raise ValueError('ct_log_urls must be a JSON list')
        return parsed
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.warning(f"Invalid CT log configuration: {e}")
        return []


AUTO_SUBMIT_THREAD = 'ct-auto-submit'


def _store_auto_submitted(serial, scts, wait_seconds=10):
    """Record the SCTs as ``cert_scts_<id>`` of the certificate with *serial* (an int)."""
    import time
    from models import Certificate, SystemConfig, db

    deadline = time.monotonic() + wait_seconds
    while True:
        # Stored in decimal or in hex depending on the issuance path
        row = Certificate.query.filter(Certificate.serial_number.in_(
            (str(serial), format(serial, 'x'), format(serial, 'X')))).first()
        if row is not None or time.monotonic() >= deadline:
            break
        db.session.rollback()
        time.sleep(0.2)
    if row is None:
        logger.warning(f"CT: no certificate with serial {serial} to attach its SCTs to")
        return
    key = f'cert_scts_{row.id}'
    config = SystemConfig.query.filter_by(key=key).first() or SystemConfig(key=key)
    config.value = json.dumps(scts)
    db.session.add(config)
    db.session.commit()


def _submit_in_background(app, chain, log_urls, serial):
    try:
        with app.app_context():
            scts = collect_scts(chain, log_urls)
            if not scts:
                logger.warning("No CT log accepted the issued certificate")
                return
            _store_auto_submitted(serial, scts)
    except Exception as e:
        logger.warning(f"CT auto-submission failed: {e}")


def _auto_submit(certificate, issuer_certificate):
    """Post-issuance ``add-chain`` when ``ct_enabled`` and ``ct_auto_submit`` are on.

    Runs in a background thread once the issuing transaction commits: a slow or
    refusing log never delays nor fails the issuance. Returns no SCT.
    """
    import threading
    from flask import current_app
    from sqlalchemy import event
    from models import SystemConfig, db

    def on(key):
        row = SystemConfig.query.filter_by(key=key).first()
        return bool(row and str(row.value).lower() == 'true')

    if not (on('ct_enabled') and on('ct_auto_submit')):
        return []
    chain = [c.public_bytes(serialization.Encoding.PEM).decode('ascii')
             for c in (certificate, issuer_certificate)]
    args = (current_app._get_current_object(), chain, _configured_log_urls(),
            certificate.serial_number)
    session = db.session()

    state = {'open': True}

    def committed(_session):
        if state.pop('open', False):
            threading.Thread(target=_submit_in_background, args=args,
                             name=AUTO_SUBMIT_THREAD, daemon=True).start()

    def rolled_back(_session):
        state.pop('open', None)

    event.listen(session, 'after_commit', committed, once=True)
    event.listen(session, 'after_rollback', rolled_back, once=True)
    return []


def apply_ct_policy(certificate, issuer_certificate, issuer_private_key):
    """Apply the configured Certificate Transparency policy to a freshly signed
    leaf certificate. Reads ``ct_enabled`` / ``ct_embed_sct`` / ``ct_required`` / ``ct_log_urls``
    from SystemConfig and, when embedding is enabled, re-issues the certificate
    with an embedded SCT list via the pre-certificate flow.

    Returns ``(certificate, scts)`` — the (possibly re-issued) certificate and
    its embedded SCTs; with embedding off, ``ct_auto_submit`` submits the
    certificate in the background once the issuance commits. Raises ValueError when ``ct_required`` is set but no CT log
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

    def _on(key):
        row = SystemConfig.query.filter_by(key=key).first()
        return bool(row and str(row.value).lower() == 'true')

    # Embedding (and "required") only apply while CT itself is enabled.
    if not (_on('ct_enabled') and _on('ct_embed_sct')):
        return certificate, _auto_submit(certificate, issuer_certificate)

    ct_required = _on('ct_required')

    ct_log_urls = _configured_log_urls()

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
