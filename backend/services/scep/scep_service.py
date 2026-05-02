"""
SCEP Service - Simple Certificate Enrollment Protocol orchestration.
Implements RFC 8894 (SCEP).
"""
import base64
import hmac
import json
import logging
import uuid
from datetime import timedelta
from typing import Optional, Tuple

import asn1crypto.cms
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509.oid import ExtensionOID

from config.settings import Config
from models import CA, Certificate, SCEPRequest, db
from security.encryption import decrypt_private_key
from utils.datetime_utils import utc_now
from utils.file_naming import cert_cert_path

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
    build_error_response,
)

logger = logging.getLogger(__name__)


class SCEPService:
    """SCEP Protocol Implementation (RFC 8894)."""

    # SCEP message types (RFC 8894 §3.2.1.2)
    MSG_TYPE_CERT_REP = 3
    MSG_TYPE_RENEWAL_REQ = 17
    MSG_TYPE_PKI_REQ = 19
    MSG_TYPE_GET_CERT_INITIAL = 20

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
    ):
        """
        Initialize SCEP service for a specific CA.

        Args:
            ca_refid: Reference ID of the CA to use for SCEP
            challenge_password: Optional challenge password for enrollment
            auto_approve: If True, automatically approve enrollment requests
        """
        self.ca_refid = ca_refid
        self.challenge_password = challenge_password
        self.auto_approve = auto_approve

        self.ca = CA.query.filter_by(refid=ca_refid).first()
        if not self.ca:
            raise ValueError(f"CA not found: {ca_refid}")

        self.ca_cert = x509.load_pem_x509_certificate(
            base64.b64decode(self.ca.crt), default_backend()
        )
        self.ca_key = serialization.load_pem_private_key(
            base64.b64decode(decrypt_private_key(self.ca.prv)),
            password=None,
            backend=default_backend(),
        )

    # ------------------------------------------------------------------
    # Public protocol methods
    # ------------------------------------------------------------------

    def get_ca_caps(self) -> str:
        """Return CA capabilities for SCEP GetCACaps.

        We deliberately do *not* advertise SHA-1 (deprecated, MUST NOT be used
        for new signatures per RFC 8894 §3.5.2) nor SCEPStandard (would
        require failInfoText support, currently absent). DES is rejected on
        input, so we don't advertise it either.
        """
        capabilities = [
            "POSTPKIOperation",
            "SHA-256",
            "SHA-384",
            "SHA-512",
            "AES",
            "Renewal",
            "GetNextCACert",
        ]
        return "\n".join(capabilities)

    def get_ca_cert(self) -> bytes:
        """Return CA certificate in DER format for SCEP GetCACert."""
        return self.ca_cert.public_bytes(serialization.Encoding.DER)

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
        try:
            content_info = asn1crypto.cms.ContentInfo.load(pkcs7_data)
            if content_info["content_type"].native != "signed_data":
                return self._create_error_response(
                    self.FAIL_BAD_REQUEST, "Expected SignedData"
                ), 200

            signed_data = content_info["content"]

            # ---- 1. Outer CMS signature MUST verify (RFC 8894 §3.1) ----
            signer_cert = extract_signer_certificate(signed_data)
            if signer_cert is None:
                return self._create_error_response(
                    self.FAIL_BAD_MESSAGE_CHECK,
                    "Missing signer certificate in SignedData",
                ), 200
            try:
                verify_cms_signature(signed_data, signer_cert)
            except InvalidSignature:
                logger.warning(
                    f"SCEP: CMS signature verification failed (client_ip={client_ip})"
                )
                return self._create_error_response(
                    self.FAIL_BAD_MESSAGE_CHECK, "CMS signature verification failed"
                ), 200
            except ValueError as e:
                logger.warning(f"SCEP: CMS signature malformed: {e}")
                return self._create_error_response(
                    self.FAIL_BAD_ALG, "Unsupported or malformed CMS signature"
                ), 200

            # ---- 2. Extract SCEP attributes ----
            attrs = extract_scep_attributes(signed_data)
            transaction_id = attrs.get("transactionID")
            message_type = attrs.get("messageType")  # always int (or None)
            sender_nonce = attrs.get("senderNonce")
            challenge_pwd = attrs.get("challengePassword")

            if not transaction_id:
                return self._create_error_response(
                    self.FAIL_BAD_REQUEST, "Missing transactionID",
                    transaction_id="", recipient_nonce=sender_nonce,
                ), 200

            logger.debug(
                f"SCEP: txn_id={transaction_id} msg_type={message_type} "
                f"client_ip={client_ip} ca={self.ca_refid}"
            )

            # ---- 3. Dispatch on messageType ----
            if message_type == self.MSG_TYPE_GET_CERT_INITIAL:
                return self._handle_get_cert_initial(
                    transaction_id, sender_nonce
                ), 200

            if message_type not in (
                self.MSG_TYPE_PKI_REQ, self.MSG_TYPE_RENEWAL_REQ
            ):
                return self._create_error_response(
                    self.FAIL_BAD_REQUEST,
                    f"Unsupported messageType: {message_type}",
                    transaction_id=transaction_id, recipient_nonce=sender_nonce,
                ), 200

            # ---- 4. Decrypt the inner EnvelopedData → CSR ----
            encap_content = signed_data["encap_content_info"]
            encrypted_content = encap_content["content"]
            encrypted_bytes = (
                encrypted_content.native
                if hasattr(encrypted_content, "native")
                else bytes(encrypted_content)
            )
            try:
                csr_data = decrypt_scep_envelope(encrypted_bytes, self.ca_key)
            except Exception as e:
                logger.error(f"SCEP: Failed to decrypt envelopedData: {e}")
                return self._create_error_response(
                    self.FAIL_BAD_MESSAGE_CHECK,
                    "Failed to decrypt SCEP envelope",
                    transaction_id=transaction_id, recipient_nonce=sender_nonce,
                ), 200

            try:
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

            # ---- 6. Also check challengePassword in CSR attributes (scepclient) ----
            if not challenge_pwd:
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

            # ---- 7. Validate challenge password (constant-time) ----
            if self.challenge_password:
                if not challenge_pwd or not hmac.compare_digest(
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
                    existing, sender_nonce, signer_cert
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
                cert_refid = self._auto_approve_request(scep_req, csr)
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
                logger.debug("SCEP: Returning SUCCESS response")
                return self._create_cert_rep_success(
                    cert_obj, transaction_id, sender_nonce, signer_cert
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
                self.FAIL_BAD_REQUEST, "Internal SCEP processing error"
            ), 200

    def _handle_get_cert_initial(
        self, transaction_id: str, sender_nonce
    ) -> bytes:
        """Polling request (RFC 8894 §3.3.2.2).

        The client re-sends the *same* transactionID it used for the original
        PKCSReq; we look it up scoped to this CA and return the current
        status. We don't bother decrypting the IssuerAndSubject payload
        because transactionID is unique per (client, CA) and the lookup is
        cheaper.
        """
        existing = SCEPRequest.query.filter_by(
            transaction_id=transaction_id, ca_refid=self.ca_refid
        ).first()
        if not existing:
            return self._create_error_response(
                self.FAIL_BAD_CERT_ID, "Unknown transactionID",
                transaction_id=transaction_id, recipient_nonce=sender_nonce,
            )
        # For GetCertInitial the recipient cert is not in our message — best
        # effort: load the CSR and synthesize a self-signed-like recipient by
        # reusing the cert we already issued (success path), or just return
        # PENDING/FAILURE which carry no encrypted payload.
        if existing.status == "approved" and existing.cert_refid:
            cert = Certificate.query.filter_by(refid=existing.cert_refid).first()
            if cert:
                cert_obj = x509.load_pem_x509_certificate(
                    base64.b64decode(cert.crt), default_backend()
                )
                # In the absence of a client signer cert (it's not transmitted
                # in GetCertInitial), encrypt to the issued cert's public key:
                # the requester proved possession of that key during PKCSReq.
                return self._create_cert_rep_success(
                    cert_obj, transaction_id, sender_nonce, cert_obj
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
    ) -> bytes:
        """Return an appropriate CertRep for an already-seen transaction ID."""
        if existing.status == "approved" and existing.cert_refid:
            cert = Certificate.query.filter_by(refid=existing.cert_refid).first()
            if cert:
                cert_obj = x509.load_pem_x509_certificate(
                    base64.b64decode(cert.crt), default_backend()
                )
                return self._create_cert_rep_success(
                    cert_obj, existing.transaction_id, sender_nonce, signer_cert
                )

        if existing.status == "rejected":
            return self._create_error_response(
                self.FAIL_BAD_REQUEST,
                existing.rejection_reason or "Request rejected",
                transaction_id=existing.transaction_id,
                recipient_nonce=sender_nonce,
            )

        return self._create_cert_rep_pending(existing.transaction_id, sender_nonce)

    def _auto_approve_request(
        self,
        scep_req: SCEPRequest,
        csr: x509.CertificateSigningRequest,
        validity_days: int = 365,
    ) -> str:
        """Issue a certificate for the given SCEP request. Returns the cert refid."""
        cert_refid = str(uuid.uuid4())
        public_key = csr.public_key()

        # Clamp validity to the CA's own expiry — issuing a leaf that outlives
        # its issuer is invalid per RFC 5280 §6.1 and breaks every chain
        # validator the moment the CA expires.
        not_before = utc_now()
        requested_not_after = not_before + timedelta(days=validity_days)
        ca_not_after = self.ca_cert.not_valid_after_utc
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
        _ALLOWED_EKU_OIDS = {
            x509.ExtendedKeyUsageOID.SERVER_AUTH,
            x509.ExtendedKeyUsageOID.CLIENT_AUTH,
            x509.ExtendedKeyUsageOID.EMAIL_PROTECTION,
            x509.ExtendedKeyUsageOID.CODE_SIGNING,
            x509.ExtendedKeyUsageOID.TIME_STAMPING,
            x509.ExtendedKeyUsageOID.OCSP_SIGNING,
            x509.ExtendedKeyUsageOID.IPSEC_IKE,
        }
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
                url.replace('{ca_refid}', self.ca.refid)
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
                            url.replace('{ca_refid}', self.ca.refid)
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
    ) -> bytes:
        return build_cert_rep_success(
            cert, transaction_id, sender_nonce, recipient_cert,
            self.ca_cert, self.ca_key,
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
