"""
SCEP Service - Simple Certificate Enrollment Protocol orchestration.
Implements RFC 8894 (SCEP).
"""
import base64
import hmac
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import asn1crypto.cms
import asn1crypto.x509
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtensionOID

from config.settings import Config
from models import CA, Certificate, SCEPRequest, db
from services.crl_service import CRLService
from utils.key_codec import load_pem_bytes
from utils.datetime_utils import utc_now
from utils.file_naming import cert_cert_path

from services.scep.crypto_helpers import (
    AES128_CBC,
    select_response_content_encryption_algorithm,
)
from services.scep.message_parser import (
    decrypt_scep_envelope,
    extract_scep_attributes,
    extract_signer_certificate,
    verify_cms_signature,
)
from services.scep.response_builder import (
    FAIL_BAD_ALG,       # noqa: F401  re-exported for callers
    FAIL_BAD_CERT_ID,   # noqa: F401
    FAIL_BAD_MESSAGE_CHECK,
    FAIL_BAD_REQUEST,
    FAIL_BAD_TIME,      # noqa: F401
    STATUS_FAILURE,     # noqa: F401
    STATUS_PENDING,     # noqa: F401
    STATUS_SUCCESS,     # noqa: F401
    build_cert_rep_pending,
    build_cert_rep_success,
    build_crl_rep_success,
    build_error_response,
)

logger = logging.getLogger(__name__)


def _scep_allow_no_challenge() -> bool:
    """Opt-in to allow SCEP auto-approval without a challenge password.

    Default-deny: only a truthy env override re-enables the RFC 8894 §2.4
    unauthenticated-authorisation behaviour, for deployments that gate SCEP
    another way (isolated network, mTLS front).
    """
    return os.environ.get('UCM_SCEP_ALLOW_NO_CHALLENGE', '').lower() in ('1', 'true', 'yes')


class SCEPService:
    """SCEP Protocol Implementation (RFC 8894)."""

    # SCEP message types (RFC 8894 §3.2.1.2)
    MSG_TYPE_CERT_REP = 3
    MSG_TYPE_RENEWAL_REQ = 17
    MSG_TYPE_PKI_REQ = 19
    MSG_TYPE_GET_CERT_INITIAL = 20
    MSG_TYPE_GET_CERT = 21
    MSG_TYPE_GET_CRL = 22

    CAPABILITIES = (
        "POSTPKIOperation",
        "SHA-256",
        "SHA-384",
        "SHA-512",
        "AES",
        "Renewal",
        "GetNextCACert",
        "SCEPStandard",
    )

    # SCEP status codes (mirrors response_builder constants for backward compat)
    STATUS_SUCCESS = STATUS_SUCCESS
    STATUS_FAILURE = STATUS_FAILURE
    STATUS_PENDING = STATUS_PENDING

    # Failure reasons
    FAIL_BAD_ALG = FAIL_BAD_ALG
    FAIL_BAD_MESSAGE_CHECK = FAIL_BAD_MESSAGE_CHECK
    FAIL_BAD_REQUEST = FAIL_BAD_REQUEST
    FAIL_BAD_TIME = FAIL_BAD_TIME
    FAIL_BAD_CERT_ID = FAIL_BAD_CERT_ID

    def __init__(
        self,
        ca_refid: str,
        challenge_password: Optional[str] = None,
        auto_approve: bool = False,
        challenge_expired: bool = False,
    ):
        """
        Initialize SCEP service for a specific CA.

        Args:
            ca_refid: Reference ID of the CA to use for SCEP
            challenge_password: Optional challenge password for enrollment
            auto_approve: If True, automatically approve enrollment requests
            challenge_expired: True when a challenge IS configured but has
                outlived ``scep_challenge_validity``. Kept separate from a
                blank challenge so expiry is an explicit refusal rather than a
                fallback to the weaker no-challenge path.
        """
        self.ca_refid = ca_refid
        self.challenge_password = challenge_password
        self.auto_approve = auto_approve
        self.challenge_expired = challenge_expired

        self.ca = CA.query.filter_by(refid=ca_refid).first()
        if not self.ca:
            raise ValueError(f"CA not found: {ca_refid}")

        self._config_cache = {}

        self.ca_cert = x509.load_pem_x509_certificate(
            base64.b64decode(self.ca.crt), default_backend()
        )
        self.ca_key = serialization.load_pem_private_key(
            load_pem_bytes(self.ca.prv, context=f"SCEP CA {self.ca.id}"),
            password=None,
            backend=default_backend(),
        )

    # ------------------------------------------------------------------
    # Public protocol methods
    # ------------------------------------------------------------------

    def get_ca_caps(self) -> str:
        """Return the capabilities implemented by this RFC 8894 service."""
        return "\n".join(self.CAPABILITIES)

    def get_ca_cert(self) -> bytes:
        """Return CA certificate in DER format for SCEP GetCACert."""
        return self.ca_cert.public_bytes(serialization.Encoding.DER)

    def get_ca_chain(self) -> list[x509.Certificate]:
        """Return the configured CA followed by its parents up to the root."""
        chain = [self.ca_cert]
        parent_refid = self.ca.caref
        visited = {self.ca.refid}
        while parent_refid:
            if parent_refid in visited:
                raise ValueError("Cycle detected in SCEP CA chain")
            parent = CA.query.filter_by(refid=parent_refid).first()
            if parent is None:
                raise ValueError("SCEP CA chain is incomplete")
            chain.append(x509.load_pem_x509_certificate(
                base64.b64decode(parent.crt), default_backend()
            ))
            visited.add(parent.refid)
            parent_refid = parent.caref
        return chain

    def process_pkcs_req(self, pkcs7_data: bytes, client_ip: str) -> Tuple[bytes, int]:
        """
        Process a SCEP PKCSReq / RenewalReq / GetCertInitial request.

        Args:
            pkcs7_data: PKCS#7 signed data from client
            client_ip: Client IP address for logging

        Returns:
            Tuple of (PKCS#7 response bytes, HTTP status code)
        """
        # All SCEP error responses are returned with HTTP 200 — failures are
        # signalled inside the signed PKIMessage (RFC 8894 §3.3.2). HTTP-level
        # errors (4xx/5xx) are reserved for transport problems.
        transaction_id = ''
        sender_nonce = None
        challenge_pwd = None
        response_encryption_algorithm = AES128_CBC
        try:
            content_info = asn1crypto.cms.ContentInfo.load(pkcs7_data)
            if content_info["content_type"].native != "signed_data":
                return self._create_error_response(
                    self.FAIL_BAD_REQUEST, "Expected SignedData"
                ), 200

            signed_data = content_info["content"]
            attrs = extract_scep_attributes(signed_data)
            transaction_id = attrs.get("transactionID") or ''
            message_type = attrs.get("messageType")
            sender_nonce = attrs.get("senderNonce")
            challenge_pwd = attrs.get("challengePassword")
            signing_time = attrs.get("signingTime")

            if signed_data["encap_content_info"]["content_type"].native != "data":
                return self._create_error_response(
                    self.FAIL_BAD_MESSAGE_CHECK,
                    "SignedData encapsulated content type must be data",
                    transaction_id=transaction_id,
                    recipient_nonce=sender_nonce,
                ), 200

            # ---- 1. Outer CMS signature MUST verify (RFC 8894 §3.1) ----
            signer_cert = extract_signer_certificate(signed_data)
            if signer_cert is None:
                return self._create_error_response(
                    self.FAIL_BAD_MESSAGE_CHECK,
                    "Missing signer certificate in SignedData",
                    transaction_id=transaction_id,
                    recipient_nonce=sender_nonce,
                ), 200
            try:
                verify_cms_signature(signed_data, signer_cert)
            except InvalidSignature:
                logger.warning(
                    f"SCEP: CMS signature verification failed (client_ip={client_ip})"
                )
                return self._create_error_response(
                    self.FAIL_BAD_MESSAGE_CHECK,
                    "CMS signature verification failed",
                    transaction_id=transaction_id,
                    recipient_nonce=sender_nonce,
                ), 200
            except ValueError as e:
                logger.warning(f"SCEP: CMS signature malformed: {e}")
                return self._create_error_response(
                    self.FAIL_BAD_ALG,
                    "Unsupported or malformed CMS signature",
                    transaction_id=transaction_id,
                    recipient_nonce=sender_nonce,
                ), 200

            # ---- 2. Validate mandatory transaction attributes ----
            if not transaction_id:
                return self._create_error_response(
                    self.FAIL_BAD_REQUEST, "Missing transactionID",
                    recipient_nonce=sender_nonce,
                ), 200

            # RFC 8894 specifies a 16-byte senderNonce, but pre-RFC clients
            # (old IOS, embedded stacks, some jscep forks) omit it or send 8
            # bytes. Rejecting them broke enrolled fleets on upgrade — accept
            # with a warning instead (pre-2.200 behaviour).
            if isinstance(sender_nonce, (bytes, bytearray)):
                sender_nonce = bytes(sender_nonce)
                if len(sender_nonce) != 16:
                    logger.warning(
                        "SCEP senderNonce is %d bytes (RFC 8894 specifies 16); "
                        "accepting for compatibility", len(sender_nonce),
                    )
            else:
                if sender_nonce is not None:
                    logger.warning("SCEP senderNonce has unexpected type; ignoring")
                sender_nonce = None

            # signingTime is optional in CMS and RFC 8894 does not require it.
            # Devices without NTP (or with a dead RTC) legitimately drift —
            # enforce the skew only when scep_enforce_signing_time is enabled.
            enforce_signing_time = self._config_flag('scep_enforce_signing_time')
            if isinstance(signing_time, datetime):
                if signing_time.tzinfo is None:
                    signing_time = signing_time.replace(tzinfo=timezone.utc)
                skew_minutes = self._config_int('scep_time_skew_minutes', 10, 1, 1440)
                time_skew = abs(datetime.now(timezone.utc) - signing_time)
                if time_skew > timedelta(minutes=skew_minutes):
                    if enforce_signing_time:
                        return self._create_error_response(
                            self.FAIL_BAD_TIME,
                            "signingTime outside the allowed clock skew",
                            transaction_id=transaction_id,
                            recipient_nonce=sender_nonce,
                        ), 200
                    logger.warning(
                        "SCEP signingTime is %s outside the %d-minute skew; "
                        "accepting (enable scep_enforce_signing_time to reject)",
                        time_skew, skew_minutes,
                    )
            elif enforce_signing_time:
                return self._create_error_response(
                    self.FAIL_BAD_TIME,
                    "Missing or invalid signingTime",
                    transaction_id=transaction_id,
                    recipient_nonce=sender_nonce,
                ), 200

            logger.debug(
                f"SCEP: txn_id={transaction_id} msg_type={message_type} "
                f"client_ip={client_ip} ca={self.ca_refid}"
            )

            # ---- 3. Validate messageType ----
            supported_enveloped_types = (
                self.MSG_TYPE_PKI_REQ,
                self.MSG_TYPE_RENEWAL_REQ,
                self.MSG_TYPE_GET_CERT_INITIAL,
                self.MSG_TYPE_GET_CERT,
                self.MSG_TYPE_GET_CRL,
            )
            if message_type not in supported_enveloped_types:
                return self._create_error_response(
                    self.FAIL_BAD_REQUEST,
                    f"Unsupported messageType: {message_type}",
                    transaction_id=transaction_id, recipient_nonce=sender_nonce,
                ), 200

            # ---- 4. Decrypt the inner EnvelopedData ----
            encap_content = signed_data["encap_content_info"]
            encrypted_content = encap_content["content"]
            encrypted_bytes = (
                encrypted_content.native
                if hasattr(encrypted_content, "native")
                else bytes(encrypted_content)
            )
            try:
                response_encryption_algorithm = (
                    select_response_content_encryption_algorithm(encrypted_bytes)
                )
                message_data = decrypt_scep_envelope(
                    encrypted_bytes, self.ca_key, self.ca_cert
                )
            except Exception as e:
                logger.error(f"SCEP: Failed to decrypt envelopedData: {e}")
                return self._create_error_response(
                    self.FAIL_BAD_MESSAGE_CHECK,
                    "Failed to decrypt SCEP envelope",
                    transaction_id=transaction_id, recipient_nonce=sender_nonce,
                ), 200

            if message_type in {
                self.MSG_TYPE_GET_CERT_INITIAL,
                self.MSG_TYPE_GET_CERT,
                self.MSG_TYPE_GET_CRL,
            } and self._recipient_requires_password(
                signer_cert
            ) and not self._has_usable_challenge_password(challenge_pwd):
                return self._create_error_response(
                    self.FAIL_BAD_MESSAGE_CHECK,
                    "challengePassword required for signing-only recipient key",
                    transaction_id=transaction_id,
                    recipient_nonce=sender_nonce,
                ), 200

            if message_type == self.MSG_TYPE_GET_CERT_INITIAL:
                return self._handle_get_cert_initial(
                    transaction_id,
                    sender_nonce,
                    signer_cert,
                    challenge_pwd,
                    response_encryption_algorithm,
                ), 200
            if message_type == self.MSG_TYPE_GET_CERT:
                return self._handle_get_cert(
                    message_data,
                    transaction_id,
                    sender_nonce,
                    signer_cert,
                    challenge_pwd,
                    response_encryption_algorithm,
                ), 200
            if message_type == self.MSG_TYPE_GET_CRL:
                return self._handle_get_crl(
                    message_data,
                    transaction_id,
                    sender_nonce,
                    signer_cert,
                    challenge_pwd,
                    response_encryption_algorithm,
                ), 200

            try:
                csr_data = message_data
                csr = x509.load_der_x509_csr(csr_data, default_backend())
            except Exception as e:
                logger.warning(f"SCEP: Malformed CSR: {e}")
                return self._create_error_response(
                    self.FAIL_BAD_REQUEST, "Malformed CSR",
                    transaction_id=transaction_id, recipient_nonce=sender_nonce,
                ), 200

            # ---- 5. Verify CSR self-signature (proof of possession) ----
            if not csr.is_signature_valid:
                logger.warning(
                    f"SCEP: CSR self-signature invalid "
                    f"(subject={csr.subject.rfc4514_string()})"
                )
                return self._create_error_response(
                    self.FAIL_BAD_MESSAGE_CHECK,
                    "CSR signature invalid (proof of possession failed)",
                    transaction_id=transaction_id, recipient_nonce=sender_nonce,
                ), 200

            logger.debug(f"SCEP: CSR parsed, subject={csr.subject.rfc4514_string()}")

            # ---- 5b. Key-strength policy — refuse weak/exotic enrollment keys ----
            from utils.key_type import validate_enrollment_public_key
            key_err = validate_enrollment_public_key(csr.public_key())
            if key_err:
                logger.warning("SCEP: rejecting weak enrollment key: %s", key_err)
                return self._create_error_response(
                    self.FAIL_BAD_REQUEST, key_err,
                    transaction_id=transaction_id, recipient_nonce=sender_nonce,
                ), 200

            # ---- 6. Also check challengePassword in CSR attributes (scepclient) ----
            if not self._has_usable_challenge_password(challenge_pwd):
                try:
                    from cryptography.x509.oid import AttributeOID
                    for attr in csr.attributes:
                        if attr.oid == AttributeOID.CHALLENGE_PASSWORD:
                            challenge_pwd = attr.value
                            if isinstance(challenge_pwd, bytes):
                                try:
                                    challenge_pwd = challenge_pwd.decode("utf-8")
                                except UnicodeDecodeError:
                                    pass
                            break
                except Exception as e:
                    logger.debug(f"SCEP: Could not extract challenge from CSR: {e}")

            if self._recipient_requires_password(
                signer_cert
            ) and not self._has_usable_challenge_password(challenge_pwd):
                return self._create_error_response(
                    self.FAIL_BAD_MESSAGE_CHECK,
                    "challengePassword required for signing-only recipient key",
                    transaction_id=transaction_id,
                    recipient_nonce=sender_nonce,
                ), 200

            # ---- 7. Validate challenge password (constant-time) ----
            # An expired challenge is refused outright: renewals stay allowed
            # because they authenticate with the existing certificate
            # (_validate_renewal), so an expired secret does not strand a fleet
            # that is already enrolled.
            if self.challenge_expired and message_type != self.MSG_TYPE_RENEWAL_REQ:
                return self._create_error_response(
                    self.FAIL_BAD_MESSAGE_CHECK,
                    "Challenge password has expired",
                    transaction_id=transaction_id, recipient_nonce=sender_nonce,
                ), 200

            if self.challenge_password:
                if not self._has_usable_challenge_password(
                    challenge_pwd
                ) or not hmac.compare_digest(
                    challenge_pwd.encode() if isinstance(challenge_pwd, str)
                    else challenge_pwd,
                    self.challenge_password.encode()
                    if isinstance(self.challenge_password, str)
                    else self.challenge_password,
                ):
                    return self._create_error_response(
                        self.FAIL_BAD_MESSAGE_CHECK, "Invalid challenge password",
                        transaction_id=transaction_id, recipient_nonce=sender_nonce,
                    ), 200

            # ---- 7b. Fail closed: no challenge + auto-approve = anonymous cert ----
            # RFC 8894 §2.4 permits omitting the challengePassword, but then the
            # request "allows for unauthenticated authorisation" and the CA
            # should place it in manual approval mode or reject it. An initial
            # PKCSReq is signed by an ephemeral self-signed key, so with no
            # challenge configured AND auto-approve on, ANY anonymous client on
            # the public /pkiclient.exe endpoint would receive a CA-signed cert.
            # Refuse auto-issuance in that case (manual queue stays allowed, and
            # renewals are authenticated by the existing cert via _validate_renewal).
            # UCM_SCEP_ALLOW_NO_CHALLENGE=1 opts back in for a cloistered network.
            if (
                message_type != self.MSG_TYPE_RENEWAL_REQ
                and self.auto_approve
                and not self.challenge_password
                and not _scep_allow_no_challenge()
            ):
                logger.warning(
                    "SCEP: refusing auto-approval with no challengePassword "
                    "configured (set a SCEP challenge or UCM_SCEP_ALLOW_NO_CHALLENGE=1)"
                )
                return self._create_error_response(
                    self.FAIL_BAD_MESSAGE_CHECK,
                    "Enrollment requires a challenge password",
                    transaction_id=transaction_id, recipient_nonce=sender_nonce,
                ), 200

            # ---- 8. Renewal linkage validation (RFC 8894 §2.3) ----
            if message_type == self.MSG_TYPE_RENEWAL_REQ:
                err = self._validate_renewal(signer_cert, csr)
                if err is not None:
                    return self._create_error_response(
                        err[0], err[1],
                        transaction_id=transaction_id, recipient_nonce=sender_nonce,
                    ), 200

            # ---- 9. Idempotency (scoped to this CA) ----
            existing = SCEPRequest.query.filter_by(
                transaction_id=transaction_id, ca_refid=self.ca_refid
            ).first()
            if existing:
                return self._status_for_existing(
                    existing,
                    sender_nonce,
                    signer_cert,
                    challenge_pwd,
                    response_encryption_algorithm,
                ), 200

            # ---- 10. Persist new request ----
            scep_req = SCEPRequest(
                transaction_id=transaction_id,
                ca_refid=self.ca_refid,
                csr=base64.b64encode(csr_data).decode("utf-8"),
                status="pending",
                subject=csr.subject.rfc4514_string(),
                client_ip=client_ip,
            )
            db.session.add(scep_req)

            if self.auto_approve:
                cert_refid = self._auto_approve_request(
                    scep_req, csr,
                    renewal_of=(signer_cert
                                if message_type == self.MSG_TYPE_RENEWAL_REQ
                                else None),
                )
                scep_req.status = "approved"
                scep_req.cert_refid = cert_refid
                scep_req.approved_by = "auto"
                scep_req.approved_at = utc_now()
                try:
                    db.session.commit()
                except Exception as e:
                    db.session.rollback()
                    logger.error(f"SCEP: DB commit failed during auto-approve: {e}")
                    return self._create_error_response(
                        self.FAIL_BAD_REQUEST, "Server error persisting request",
                        transaction_id=transaction_id, recipient_nonce=sender_nonce,
                    ), 200

                cert = Certificate.query.filter_by(refid=cert_refid).first()
                cert_obj = x509.load_pem_x509_certificate(
                    base64.b64decode(cert.crt), default_backend()
                )
                try:
                    from services.webhook_service import emit_cert_issued
                    if cert:
                        emit_cert_issued(cert.to_dict(), ca_refid=cert.caref)
                except Exception as e:
                    logger.error(f"Webhook emit (SCEP issuance) failed: {e}")
                logger.debug("SCEP: Returning SUCCESS response")
                return self._create_cert_rep_success(
                    cert_obj,
                    transaction_id,
                    sender_nonce,
                    signer_cert,
                    challenge_pwd,
                    response_encryption_algorithm,
                ), 200
            else:
                logger.debug("SCEP: auto_approve=False, returning PENDING")
                try:
                    db.session.commit()
                except Exception as e:
                    db.session.rollback()
                    logger.error(f"SCEP: DB commit failed: {e}")
                    return self._create_error_response(
                        self.FAIL_BAD_REQUEST, "Server error persisting request",
                        transaction_id=transaction_id, recipient_nonce=sender_nonce,
                    ), 200
                return self._create_cert_rep_pending(transaction_id, sender_nonce), 200

        except Exception as e:
            # Last-resort sanitized error — never leak str(e) to the wire.
            logger.error(f"SCEP PKCSReq error: {e}", exc_info=True)
            return self._create_error_response(
                self.FAIL_BAD_REQUEST,
                "Internal SCEP processing error",
                transaction_id=transaction_id,
                recipient_nonce=sender_nonce,
            ), 200

    def _handle_get_cert(
        self,
        message_data: bytes,
        transaction_id: str,
        sender_nonce: bytes,
        signer_cert: x509.Certificate,
        challenge_password,
        content_encryption_algorithm: str,
    ) -> bytes:
        """Return a certificate identified by issuer and serial (RFC 8894 §4.5)."""
        try:
            requested = asn1crypto.cms.IssuerAndSerialNumber.load(message_data)
            requested_serial = requested["serial_number"].native
            ca_asn1 = asn1crypto.x509.Certificate.load(self.get_ca_cert())
        except Exception as e:
            logger.warning(f"SCEP GetCert: malformed IssuerAndSerialNumber: {e}")
            return self._create_error_response(
                self.FAIL_BAD_REQUEST, "Malformed IssuerAndSerialNumber",
                transaction_id=transaction_id, recipient_nonce=sender_nonce,
            )

        if requested["issuer"].dump() != ca_asn1.subject.dump():
            return self._create_error_response(
                self.FAIL_BAD_CERT_ID, "Unknown certificate issuer",
                transaction_id=transaction_id, recipient_nonce=sender_nonce,
            )

        serial_hex = format(requested_serial, "x")
        serial_candidates = {
            str(requested_serial),
            serial_hex,
            serial_hex.upper(),
            f"0x{serial_hex}",
            f"0X{serial_hex.upper()}",
        }
        cert_rows = Certificate.query.filter(
            Certificate.caref == self.ca_refid,
            Certificate.crt.isnot(None),
            Certificate.serial_number.in_(serial_candidates),
        ).all()
        for cert_row in cert_rows:
            try:
                cert = x509.load_pem_x509_certificate(
                    base64.b64decode(cert_row.crt), default_backend()
                )
            except Exception as e:
                logger.error(
                    f"SCEP GetCert: stored certificate {cert_row.id} is invalid: {e}"
                )
                continue
            if (
                cert.serial_number == requested_serial
                and cert.issuer == self.ca_cert.subject
            ):
                return self._create_cert_rep_success(
                    cert,
                    transaction_id,
                    sender_nonce,
                    signer_cert,
                    challenge_password,
                    content_encryption_algorithm,
                )

        return self._create_error_response(
            self.FAIL_BAD_CERT_ID, "Unknown certificate serial number",
            transaction_id=transaction_id, recipient_nonce=sender_nonce,
        )

    def _handle_get_crl(
        self,
        message_data: bytes,
        transaction_id: str,
        sender_nonce: bytes,
        signer_cert: x509.Certificate,
        challenge_password,
        content_encryption_algorithm: str,
    ) -> bytes:
        """Return the configured CA's current CRL (RFC 8894 §4.6)."""
        try:
            requested = asn1crypto.cms.IssuerAndSerialNumber.load(message_data)
            ca_asn1 = asn1crypto.x509.Certificate.load(self.get_ca_cert())
            # RFC 8894 §4.6: the issuer name identifies the CA whose CRL is
            # requested; the serial is that of the certificate whose status is
            # being checked (NOT the CA's own serial). Match on the issuer DN
            # only — UCM serves the single CRL for that CA regardless of which
            # leaf serial the client cited.
            identifies_ca = (
                requested["issuer"].dump() == ca_asn1.subject.dump()
            )
        except Exception as e:
            logger.warning(f"SCEP GetCRL: malformed IssuerAndSerialNumber: {e}")
            return self._create_error_response(
                self.FAIL_BAD_REQUEST, "Malformed IssuerAndSerialNumber",
                transaction_id=transaction_id, recipient_nonce=sender_nonce,
            )

        if not identifies_ca:
            return self._create_error_response(
                self.FAIL_BAD_CERT_ID, "Unknown CA certificate",
                transaction_id=transaction_id, recipient_nonce=sender_nonce,
            )

        try:
            crl_meta = CRLService.get_latest_crl(self.ca.id)
            if crl_meta is None or crl_meta.is_stale or not crl_meta.crl_der:
                crl_meta = CRLService.generate_crl(self.ca.id, username="scep")
            if crl_meta is None or not crl_meta.crl_der:
                raise ValueError("CRL service returned no CRL")
            crl = x509.load_der_x509_crl(crl_meta.crl_der, default_backend())
        except Exception as e:
            logger.warning(f"SCEP GetCRL: current CRL unavailable: {e}")
            return self._create_error_response(
                self.FAIL_BAD_CERT_ID, "CRL is unavailable",
                transaction_id=transaction_id, recipient_nonce=sender_nonce,
            )
        return self._create_crl_rep_success(
            crl,
            transaction_id,
            sender_nonce,
            signer_cert,
            challenge_password,
            content_encryption_algorithm,
        )

    def _handle_get_cert_initial(
        self,
        transaction_id: str,
        sender_nonce,
        signer_cert: x509.Certificate,
        challenge_password,
        content_encryption_algorithm: str,
    ) -> bytes:
        """Polling request (RFC 8894 §3.3.2.2).

        The client re-sends the *same* transactionID it used for the original
        PKCSReq; we look it up scoped to this CA and return the current
        status. The IssuerAndSubject envelope is validated and decrypted by
        the caller, but transactionID is the scoped lookup key.
        """
        existing = SCEPRequest.query.filter_by(
            transaction_id=transaction_id, ca_refid=self.ca_refid
        ).first()
        if not existing:
            return self._create_error_response(
                self.FAIL_BAD_CERT_ID, "Unknown transactionID",
                transaction_id=transaction_id, recipient_nonce=sender_nonce,
            )
        # PENDING and FAILURE carry no encrypted payload. SUCCESS is encrypted
        # to the signer certificate carried by this polling request.
        if existing.status == "approved" and existing.cert_refid:
            cert = Certificate.query.filter_by(refid=existing.cert_refid).first()
            if cert:
                cert_obj = x509.load_pem_x509_certificate(
                    base64.b64decode(cert.crt), default_backend()
                )
                return self._create_cert_rep_success(
                    cert_obj,
                    transaction_id,
                    sender_nonce,
                    signer_cert,
                    challenge_password,
                    content_encryption_algorithm,
                )
        if existing.status == "rejected":
            return self._create_error_response(
                self.FAIL_BAD_REQUEST,
                existing.rejection_reason or "Request rejected",
                transaction_id=transaction_id, recipient_nonce=sender_nonce,
            )
        return self._create_cert_rep_pending(transaction_id, sender_nonce)

    def approve_request(
        self,
        transaction_id: str,
        approved_by: str,
        validity_days: int = 365,
    ) -> Optional[str]:
        """
        Approve a pending SCEP request.

        Returns:
            Certificate refid if successful, None otherwise
        """
        scep_req = SCEPRequest.query.filter_by(
            transaction_id=transaction_id, ca_refid=self.ca_refid
        ).first()
        if not scep_req or scep_req.status != "pending":
            return None

        csr = x509.load_der_x509_csr(base64.b64decode(scep_req.csr), default_backend())
        cert_refid = self._auto_approve_request(scep_req, csr, validity_days)

        scep_req.status = "approved"
        scep_req.cert_refid = cert_refid
        scep_req.approved_by = approved_by
        scep_req.approved_at = utc_now()
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"SCEP approve_request: DB commit failed: {e}")
            return None

        return cert_refid

    def reject_request(self, transaction_id: str, reason: str) -> bool:
        """
        Reject a pending SCEP request.

        Returns:
            True if successful
        """
        scep_req = SCEPRequest.query.filter_by(
            transaction_id=transaction_id, ca_refid=self.ca_refid
        ).first()
        if not scep_req or scep_req.status != "pending":
            return False

        scep_req.status = "rejected"
        scep_req.rejection_reason = reason
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"SCEP reject_request: DB commit failed: {e}")
            return False
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _recipient_requires_password(signer_cert: x509.Certificate) -> bool:
        """Return whether the signer key cannot receive an RSA KTRI response."""
        return not isinstance(signer_cert.public_key(), rsa.RSAPublicKey)

    @staticmethod
    def _has_usable_challenge_password(challenge_password) -> bool:
        return (
            isinstance(challenge_password, (str, bytes))
            and len(challenge_password) > 0
        )

    def _validate_renewal(self, signer_cert: x509.Certificate, csr) \
            -> Optional[Tuple[int, str]]:
        """Validate signer certificate for RenewalReq (messageType 17).

        Returns ``(failInfo, message)`` if validation fails, ``None`` if OK.

        This is fail-CLOSED: any unexpected exception is treated as a
        validation failure rather than swallowed (the previous behaviour
        allowed renewal forgery if the verify code itself raised).
        """
        try:
            # The signer cert MUST have been issued by this CA.
            try:
                signer_cert.verify_directly_issued_by(self.ca_cert)
            except Exception:
                logger.warning(
                    f"SCEP renewal: signer cert not issued by this CA "
                    f"(subject={signer_cert.subject.rfc4514_string()}, "
                    f"ca={self.ca_refid})"
                )
                return (
                    self.FAIL_BAD_MESSAGE_CHECK,
                    "Renewal: signer certificate not issued by this CA",
                )

            # Subject must match the CSR (renewal of the same identity).
            if signer_cert.subject != csr.subject:
                logger.warning(
                    f"SCEP renewal: subject mismatch "
                    f"(signer={signer_cert.subject.rfc4514_string()}, "
                    f"csr={csr.subject.rfc4514_string()})"
                )
                return (
                    self.FAIL_BAD_MESSAGE_CHECK,
                    "Renewal: CSR subject must match existing certificate",
                )

            # The signer cert must still be within its validity period — an
            # attacker who recovers an old/expired key MUST NOT be able to
            # bootstrap a new cert via renewal. RFC 8894 §3.3.2 implies the
            # renewal is performed by a currently-valid certificate.
            # nb/na below are timezone-aware; utc_now() is naive-UTC (project
            # convention), so make now aware too or the comparison raises
            # "can't compare offset-naive and offset-aware datetimes".
            now = utc_now().replace(tzinfo=timezone.utc)
            try:
                nb = signer_cert.not_valid_before_utc
                na = signer_cert.not_valid_after_utc
            except Exception:
                # Older cryptography fallback (naive datetimes)
                nb = signer_cert.not_valid_before.replace(tzinfo=timezone.utc)
                na = signer_cert.not_valid_after.replace(tzinfo=timezone.utc)
            if now < nb or now > na:
                logger.warning(
                    f"SCEP renewal: signer cert outside validity window "
                    f"(serial={signer_cert.serial_number}, nb={nb}, na={na})"
                )
                return (
                    self.FAIL_BAD_MESSAGE_CHECK,
                    "Renewal: signer certificate is expired or not yet valid",
                )

            # The signer cert must not be revoked.
            existing = Certificate.query.filter_by(
                caref=self.ca_refid,
                serial_number=str(signer_cert.serial_number),
            ).first()
            if existing is not None and getattr(existing, "revoked", False):
                logger.warning(
                    f"SCEP renewal: signer cert is revoked "
                    f"(serial={signer_cert.serial_number}, ca={self.ca_refid})"
                )
                return (
                    self.FAIL_BAD_MESSAGE_CHECK,
                    "Renewal: signer certificate has been revoked",
                )

        except Exception as e:
            # Fail closed: never accept a renewal we couldn't fully validate.
            logger.error(f"SCEP renewal validation error: {e}", exc_info=True)
            return (
                self.FAIL_BAD_MESSAGE_CHECK,
                "Renewal validation failed",
            )

        return None

    def _status_for_existing(
        self,
        existing: SCEPRequest,
        sender_nonce,
        signer_cert: x509.Certificate,
        challenge_password,
        content_encryption_algorithm: str,
    ) -> bytes:
        """Return an appropriate CertRep for an already-seen transaction ID."""
        if existing.status == "approved" and existing.cert_refid:
            cert = Certificate.query.filter_by(refid=existing.cert_refid).first()
            if cert:
                cert_obj = x509.load_pem_x509_certificate(
                    base64.b64decode(cert.crt), default_backend()
                )
                return self._create_cert_rep_success(
                    cert_obj,
                    existing.transaction_id,
                    sender_nonce,
                    signer_cert,
                    challenge_password,
                    content_encryption_algorithm,
                )

        if existing.status == "rejected":
            return self._create_error_response(
                self.FAIL_BAD_REQUEST,
                existing.rejection_reason or "Request rejected",
                transaction_id=existing.transaction_id,
                recipient_nonce=sender_nonce,
            )

        return self._create_cert_rep_pending(existing.transaction_id, sender_nonce)

    def _config_value(self, key: str):
        if key not in self._config_cache:
            try:
                from models import SystemConfig
                row = SystemConfig.query.filter_by(key=key).first()
                self._config_cache[key] = row.value if row else None
            except Exception:
                self._config_cache[key] = None
        return self._config_cache[key]

    def _config_flag(self, key: str) -> bool:
        return str(self._config_value(key) or '').lower() == 'true'

    def _config_int(self, key: str, default: int, lo: int, hi: int) -> int:
        try:
            value = int(self._config_value(key))
        except (TypeError, ValueError):
            return default
        return max(lo, min(hi, value))

    def _auto_approve_request(
        self,
        scep_req: SCEPRequest,
        csr: x509.CertificateSigningRequest,
        validity_days: int = 365,
        renewal_of: Optional[x509.Certificate] = None,
    ) -> str:
        """Issue a certificate for the given SCEP request. Returns the cert refid."""
        # Offline CAs must not sign (consistent with CSR/CRL/TSA signing paths)
        if self.ca.offline:
            raise ValueError(
                f"CA is offline: {self.ca.offline_reason or 'no reason provided'}"
            )

        cert_refid = str(uuid.uuid4())
        public_key = csr.public_key()

        # Enforce the CA chain's NameConstraints on the CSR's subject + SANs
        # (RFC 5280 §4.2.1.10). SCEP is unauthenticated beyond the challenge,
        # so a constrained CA must not be tricked into issuing out-of-scope
        # names here just as on the web/ACME/EST paths.
        try:
            _scep_sans = list(
                csr.extensions.get_extension_for_oid(
                    ExtensionOID.SUBJECT_ALTERNATIVE_NAME
                ).value
            )
        except x509.ExtensionNotFound:
            _scep_sans = None
        from services.trust_store.constraints_mixin import validate_name_constraints
        # renewal_of (the cert authenticating a RenewalReq) grants renewal at
        # par: an enrolled fleet must stay renewable even if the CA's
        # constraints tightened after enrollment.
        validate_name_constraints(self.ca_cert, csr.subject, _scep_sans,
                                  renewal_of=renewal_of)

        # Clamp validity to the CA's own expiry — issuing a leaf that outlives
        # its issuer is invalid per RFC 5280 §6.1 and breaks every chain
        # validator the moment the CA expires.
        not_before = utc_now()
        requested_not_after = not_before + timedelta(days=validity_days)
        # not_valid_after_utc is timezone-aware; utc_now() is naive-UTC (project
        # convention). Drop the tzinfo so the comparisons below stay naive-vs-naive
        # — mixing the two raises "can't compare offset-naive and offset-aware".
        ca_not_after = self.ca_cert.not_valid_after_utc.replace(tzinfo=None)
        # Leave a small safety margin so we don't issue a cert valid up to the
        # exact second of CA expiry.
        max_not_after = ca_not_after - timedelta(minutes=1)
        if max_not_after <= not_before:
            # CA already expired (or about to) — refuse to issue.
            raise ValueError("CA certificate has expired or is about to expire")
        not_after = min(requested_not_after, max_not_after)

        builder = (
            x509.CertificateBuilder()
            .subject_name(csr.subject)
            .issuer_name(self.ca_cert.subject)
            .public_key(public_key)
            .serial_number(x509.random_serial_number())
            .not_valid_before(not_before)
            .not_valid_after(not_after)
        )

        # Copy SAN / Key Usage / Extended Key Usage from CSR.
        # CRITICAL: do NOT copy KU/EKU verbatim — a malicious SCEP client can
        # request keyCertSign/cRLSign or arbitrary EKUs in its CSR. Even
        # though we hardcode BasicConstraints(ca=False) below, downstream
        # validators that trust KeyUsage flags (or EKU like 1.3.6.1.5.5.7.3.X)
        # would accept the issued cert for purposes the operator never
        # authorised. Whitelist what an end-entity SCEP cert may legitimately
        # carry.
        # NB: OCSPSigning and timeStamping are deliberately EXCLUDED. A SCEP
        # client that only knows the challenge password must not be able to mint
        # an OCSP delegated-responder cert (which validators trust to sign OCSP
        # responses for the whole CA) or a trusted timestamping cert.
        _ALLOWED_EKU_OIDS = {
            x509.ExtendedKeyUsageOID.SERVER_AUTH,
            x509.ExtendedKeyUsageOID.CLIENT_AUTH,
            x509.ExtendedKeyUsageOID.EMAIL_PROTECTION,
            x509.ExtendedKeyUsageOID.CODE_SIGNING,
            x509.ExtendedKeyUsageOID.IPSEC_IKE,
        }
        # Renewal at par: EKUs the authenticated client's current certificate
        # already carries stay allowed — silently stripping them (e.g. a
        # delegated OCSP responder or TSA cert renewing over SCEP) breaks the
        # service downstream with no error anywhere.
        if renewal_of is not None:
            try:
                old_eku = renewal_of.extensions.get_extension_for_oid(
                    ExtensionOID.EXTENDED_KEY_USAGE
                )
                extra = set(old_eku.value) - _ALLOWED_EKU_OIDS
                if extra:
                    logger.info(
                        "SCEP renewal: preserving existing EKUs %s",
                        [oid.dotted_string for oid in extra],
                    )
                    _ALLOWED_EKU_OIDS = _ALLOWED_EKU_OIDS | extra
            except x509.ExtensionNotFound:
                pass
        try:
            for ext in csr.extensions:
                if ext.oid == ExtensionOID.SUBJECT_ALTERNATIVE_NAME:
                    builder = builder.add_extension(ext.value, critical=False)
                elif ext.oid == ExtensionOID.KEY_USAGE:
                    ku = ext.value
                    # Force-clear bits that would let the cert act as a CA or
                    # sign CRLs. Encipher-only / decipher-only are only valid
                    # when key_agreement is set.
                    safe_key_agreement = bool(ku.key_agreement)
                    safe_ku = x509.KeyUsage(
                        digital_signature=bool(ku.digital_signature),
                        content_commitment=bool(ku.content_commitment),
                        key_encipherment=bool(ku.key_encipherment),
                        data_encipherment=bool(ku.data_encipherment),
                        key_agreement=safe_key_agreement,
                        key_cert_sign=False,
                        crl_sign=False,
                        encipher_only=bool(ku.encipher_only) if safe_key_agreement else False,
                        decipher_only=bool(ku.decipher_only) if safe_key_agreement else False,
                    )
                    builder = builder.add_extension(safe_ku, critical=True)
                elif ext.oid == ExtensionOID.EXTENDED_KEY_USAGE:
                    safe_ekus = [oid for oid in ext.value if oid in _ALLOWED_EKU_OIDS]
                    if safe_ekus:
                        builder = builder.add_extension(
                            x509.ExtendedKeyUsage(safe_ekus), critical=False
                        )
                # All other extensions (BasicConstraints, NameConstraints,
                # PolicyConstraints, AuthorityInfoAccess, custom OIDs, ...)
                # from the CSR are silently dropped — they MUST be set by us
                # below or not at all.
        except x509.ExtensionNotFound:
            pass

        builder = builder.add_extension(
            x509.BasicConstraints(ca=False, path_length=None), critical=True
        )
        builder = builder.add_extension(
            x509.SubjectKeyIdentifier.from_public_key(public_key), critical=False
        )
        builder = builder.add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(self.ca_cert.public_key()),
            critical=False,
        )

        # CRL Distribution Points
        if self.ca.cdp_enabled:
            cdp_urls = [
                url.replace('{ca_refid}', self.ca.url_ref)
                for url in self.ca.get_cdp_urls()
            ]
            if cdp_urls:
                builder = builder.add_extension(
                    x509.CRLDistributionPoints([
                        x509.DistributionPoint(
                            full_name=[x509.UniformResourceIdentifier(url)],
                            relative_name=None,
                            reasons=None,
                            crl_issuer=None,
                        )
                        for url in cdp_urls
                    ]),
                    critical=False,
                )

        # Authority Information Access
        aia_descriptions = []
        if self.ca.ocsp_enabled:
            for uri in self.ca.get_ocsp_urls():
                aia_descriptions.append(
                    x509.AccessDescription(
                        x509.oid.AuthorityInformationAccessOID.OCSP,
                        x509.UniformResourceIdentifier(uri),
                    )
                )
        if self.ca.aia_ca_issuers_enabled:
            for url in self.ca.get_aia_urls():
                aia_descriptions.append(
                    x509.AccessDescription(
                        x509.oid.AuthorityInformationAccessOID.CA_ISSUERS,
                        x509.UniformResourceIdentifier(
                            url.replace('{ca_refid}', self.ca.url_ref)
                        ),
                    )
                )
        if aia_descriptions:
            builder = builder.add_extension(
                x509.AuthorityInformationAccess(aia_descriptions), critical=False
            )

        # Certificate Policies / CPS
        if self.ca.cps_enabled and self.ca.cps_uri:
            policy_oid = x509.ObjectIdentifier(self.ca.cps_oid or '2.5.29.32.0')
            builder = builder.add_extension(
                x509.CertificatePolicies([
                    x509.PolicyInformation(
                        policy_identifier=policy_oid,
                        policy_qualifiers=[self.ca.cps_uri],
                    )
                ]),
                critical=False,
            )

        cert = builder.sign(self.ca_key, hashes.SHA256(), default_backend())
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)

        # Extract SANs
        san_dns_list, san_ip_list, san_email_list, san_uri_list = [], [], [], []
        try:
            ext = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
            for name in ext.value:
                if isinstance(name, x509.DNSName):
                    san_dns_list.append(name.value)
                elif isinstance(name, x509.IPAddress):
                    san_ip_list.append(str(name.value))
                elif isinstance(name, x509.RFC822Name):
                    san_email_list.append(name.value)
                elif isinstance(name, x509.UniformResourceIdentifier):
                    san_uri_list.append(name.value)
        except x509.ExtensionNotFound:
            pass

        cn_value = None
        for part in csr.subject.rfc4514_string().split(','):
            if part.strip().upper().startswith('CN='):
                cn_value = part.strip()[3:]
                break
        if not cn_value and san_dns_list:
            cn_value = san_dns_list[0]

        cert_obj = Certificate(
            refid=cert_refid,
            caref=self.ca_refid,
            descr=f"SCEP: {csr.subject.rfc4514_string()}",
            crt=base64.b64encode(cert_pem).decode('utf-8'),
            prv=None,
            cert_type="server_cert",
            subject=csr.subject.rfc4514_string(),
            subject_cn=cn_value,
            issuer=cert.issuer.rfc4514_string(),
            serial_number=str(cert.serial_number),
            valid_from=cert.not_valid_before_utc,
            valid_to=cert.not_valid_after_utc,
            san_dns=json.dumps(san_dns_list) if san_dns_list else None,
            san_ip=json.dumps(san_ip_list) if san_ip_list else None,
            san_email=json.dumps(san_email_list) if san_email_list else None,
            san_uri=json.dumps(san_uri_list) if san_uri_list else None,
            source="scep",
            created_by="scep",
        )
        db.session.add(cert_obj)

        Config.CERT_DIR.mkdir(parents=True, exist_ok=True)
        with open(cert_cert_path(cert_obj), "wb") as f:
            f.write(cert_pem)

        return cert_refid

    # ------------------------------------------------------------------
    # Private wrappers — delegate to response_builder / crypto_helpers
    # ------------------------------------------------------------------

    def _create_cert_rep_success(
        self,
        cert: x509.Certificate,
        transaction_id: str,
        sender_nonce,
        recipient_cert: x509.Certificate,
        challenge_password=None,
        content_encryption_algorithm: str = AES128_CBC,
    ) -> bytes:
        return build_cert_rep_success(
            cert,
            transaction_id,
            sender_nonce,
            recipient_cert,
            self.ca_cert,
            self.ca_key,
            challenge_password=challenge_password,
            content_encryption_algorithm=content_encryption_algorithm,
        )

    def _create_crl_rep_success(
        self,
        crl: x509.CertificateRevocationList,
        transaction_id: str,
        sender_nonce: bytes,
        recipient_cert: x509.Certificate,
        challenge_password=None,
        content_encryption_algorithm: str = AES128_CBC,
    ) -> bytes:
        return build_crl_rep_success(
            crl,
            transaction_id,
            sender_nonce,
            recipient_cert,
            self.ca_cert,
            self.ca_key,
            challenge_password=challenge_password,
            content_encryption_algorithm=content_encryption_algorithm,
        )

    def _create_cert_rep_pending(
        self, transaction_id: str, sender_nonce
    ) -> bytes:
        return build_cert_rep_pending(
            transaction_id, sender_nonce, self.ca_key, self.ca_cert
        )

    def _create_error_response(
        self,
        fail_info: int,
        message: str,
        transaction_id: str = '',
        recipient_nonce=None,
    ) -> bytes:
        return build_error_response(
            fail_info, message, self.ca_key, self.ca_cert,
            transaction_id=transaction_id,
            recipient_nonce=recipient_nonce,
        )
