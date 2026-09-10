"""
OCSP Service - Online Certificate Status Protocol (RFC 6960)
Handles OCSP request parsing and response generation
"""
import base64
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from asn1crypto import core as asn1_core
from asn1crypto import ocsp as asn1_ocsp
from asn1crypto import x509 as asn1_x509
from cryptography import x509
from cryptography.x509 import ocsp
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import (
    dsa, ec, ed25519, ed448, padding, rsa, utils,
)
from cryptography.hazmat.backends import default_backend
from sqlalchemy import or_

from models import db, CA, Certificate, OCSPResponse, SystemConfig, RevokedSerial
from utils.datetime_utils import utc_now
from utils.serial_format import serial_to_hex, serial_variants

logger = logging.getLogger(__name__)

_NONCE_OID = '1.3.6.1.5.5.7.48.1.2'
_DEFAULT_RESPONSE_VALIDITY_HOURS = 24
# Upper bound (7 days): a longer-lived response keeps a revocation masked for
# any client that cached the HTTP response, defeating timely revocation.
_MAX_RESPONSE_VALIDITY_HOURS = 168
_HASH_ALGORITHMS = {
    'sha1': hashes.SHA1,
    'sha224': hashes.SHA224,
    'sha256': hashes.SHA256,
    'sha384': hashes.SHA384,
    'sha512': hashes.SHA512,
}


@dataclass(frozen=True)
class OCSPRequestItem:
    """One RFC 6960 CertID from an OCSP request list."""

    serial_number: int
    issuer_name_hash: bytes
    issuer_key_hash: bytes
    hash_algorithm: hashes.HashAlgorithm
    cert_id_der: bytes


@dataclass(frozen=True)
class ParsedOCSPRequest:
    """Request-wide extensions and every requested CertID."""

    requests: Tuple[OCSPRequestItem, ...]
    nonce: Optional[bytes]
    has_unsupported_critical_extension: bool


# Map revoke_reason strings to X.509 ReasonFlags
def _record_holds_serial(record, cert_serial: int):
    """Whether the certificate a record stores carries *cert_serial*: True,
    False, or None when the record holds no readable certificate.

    The serial_number column mixes decimal and hexadecimal writers, and the
    lookup by variants cannot tell "10" (decimal ten) from "10" (hex sixteen);
    the stored certificate can (self-review of #347)."""
    if not record.crt:
        return None
    try:
        return x509.load_pem_x509_certificate(base64.b64decode(record.crt)).serial_number == cert_serial
    except Exception:
        return None


def _child_ca_for_serial(issuer: CA, cert_serial: int, variants) -> Optional[CA]:
    """The CA signed by *issuer* whose certificate carries *cert_serial*.

    The serial_number column is filled at creation since 2.226; older rows
    (and imports) may have it empty, so the children's certificates are
    parsed when the column does not match. A child whose caref no longer
    names its real issuer (renewed or cross-signed under another record) is
    found by its certificate: same serial, issued by and verifying against
    this issuer, as revocation resolves the issuer (self-review of #347)."""
    for child in CA.query.filter(
        CA.caref == issuer.refid,
        CA.serial_number.in_(variants),
    ).all():
        if _record_holds_serial(child, cert_serial) is not False:
            return child
    try:
        issuer_cert = x509.load_pem_x509_certificate(base64.b64decode(issuer.crt))
    except Exception:
        return None
    from utils.cert_issuer import certificate_signed_by
    for candidate in CA.query.filter(CA.id != issuer.id).all():
        if not candidate.crt:
            continue
        try:
            cert = x509.load_pem_x509_certificate(base64.b64decode(candidate.crt))
        except Exception:
            continue
        if cert.serial_number != cert_serial or cert.issuer != issuer_cert.subject:
            continue
        if candidate.caref == issuer.refid:
            return candidate
        try:
            if certificate_signed_by(cert, issuer_cert):
                return candidate
        except Exception:
            continue
    return None


def _build_unknown_certificate(serial: int, issuer: x509.Certificate) -> x509.Certificate:
    """Build a transient certificate so older cryptography can encode UNKNOWN."""
    key = ec.generate_private_key(ec.SECP256R1())
    now = utc_now()
    return (
        x509.CertificateBuilder()
        .subject_name(x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, 'Unknown OCSP certificate')
        ]))
        .issuer_name(issuer.subject)
        .public_key(key.public_key())
        .serial_number(serial)
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(minutes=1))
        .sign(key, hashes.SHA256())
    )


_REASON_MAP = {
    'unspecified': x509.ReasonFlags.unspecified,
    'key_compromise': x509.ReasonFlags.key_compromise,
    'keyCompromise': x509.ReasonFlags.key_compromise,
    'ca_compromise': x509.ReasonFlags.ca_compromise,
    'caCompromise': x509.ReasonFlags.ca_compromise,
    'affiliation_changed': x509.ReasonFlags.affiliation_changed,
    'affiliationChanged': x509.ReasonFlags.affiliation_changed,
    'superseded': x509.ReasonFlags.superseded,
    'cessation_of_operation': x509.ReasonFlags.cessation_of_operation,
    'cessationOfOperation': x509.ReasonFlags.cessation_of_operation,
    'certificate_hold': x509.ReasonFlags.certificate_hold,
    'certificateHold': x509.ReasonFlags.certificate_hold,
    'privilege_withdrawn': x509.ReasonFlags.privilege_withdrawn,
    'privilegeWithdrawn': x509.ReasonFlags.privilege_withdrawn,
    'aa_compromise': x509.ReasonFlags.aa_compromise,
    'aACompromise': x509.ReasonFlags.aa_compromise,
}


class OCSPSigningUnavailable(ValueError):
    """No usable signing identity for this CA (no key, no delegated responder).

    Mapped to an RFC 6960 'unauthorized' OCSPResponse rather than
    internalError: the responder cannot sign for this CA at all."""


_CERT_STATUS_MAP = {
    'good': ocsp.OCSPCertStatus.GOOD,
    'revoked': ocsp.OCSPCertStatus.REVOKED,
    'unknown': ocsp.OCSPCertStatus.UNKNOWN,
}


class OCSPService:
    """Service for OCSP operations"""
    
    def __init__(self):
        self.backend = default_backend()
    
    def parse_request(self, request_der: bytes) -> Optional[ocsp.OCSPRequest]:
        """
        Parse a single-entry OCSP request with cryptography.

        Multi-entry requests must use :meth:`parse_request_details` because
        cryptography currently rejects requestList sequences longer than one.
        """
        try:
            return ocsp.load_der_ocsp_request(request_der)
        except Exception as e:
            logger.error(f"Failed to parse OCSP request: {e}")
            return None

    def parse_request_details(
        self, request_der: bytes
    ) -> Optional[ParsedOCSPRequest]:
        """Parse every CertID and request extension from DER (RFC 6960 §4.1)."""
        try:
            parsed = asn1_ocsp.OCSPRequest.load(request_der, strict=True)
            tbs_request = parsed['tbs_request']
            request_list = tbs_request['request_list']
            if len(request_list) == 0:
                raise ValueError('OCSP requestList must not be empty')

            items = tuple(self._parse_request_item(item) for item in request_list)
            nonce, unsupported_critical = self._parse_request_extensions(
                tbs_request
            )
            return ParsedOCSPRequest(
                requests=items,
                nonce=nonce,
                has_unsupported_critical_extension=unsupported_critical,
            )
        except Exception as e:
            logger.warning(f"Failed to parse OCSP request details: {e}")
            return None

    @staticmethod
    def _parse_request_item(request_item) -> OCSPRequestItem:
        cert_id = request_item['req_cert']
        algorithm_name = cert_id['hash_algorithm']['algorithm'].native
        algorithm_type = _HASH_ALGORITHMS.get(algorithm_name)
        if algorithm_type is None:
            raise ValueError(f'Unsupported OCSP CertID hash algorithm: {algorithm_name}')
        serial_number = cert_id['serial_number'].native
        if serial_number <= 0:
            raise ValueError('OCSP CertID serial number must be positive')
        return OCSPRequestItem(
            serial_number=serial_number,
            issuer_name_hash=cert_id['issuer_name_hash'].native,
            issuer_key_hash=cert_id['issuer_key_hash'].native,
            hash_algorithm=algorithm_type(),
            cert_id_der=cert_id.dump(),
        )

    @staticmethod
    def _parse_request_extensions(tbs_request) -> Tuple[Optional[bytes], bool]:
        nonce = None
        unsupported_critical = False
        extensions = tbs_request['request_extensions']
        if extensions.native is not None:
            for extension in extensions:
                oid = extension['extn_id'].dotted
                if extension['critical'].native and oid != _NONCE_OID:
                    unsupported_critical = True
                if oid == _NONCE_OID:
                    if nonce is not None:
                        raise ValueError('Duplicate OCSP nonce extension')
                    nonce = extension['extn_value'].parsed.native
                    if not isinstance(nonce, bytes):
                        raise ValueError('Malformed OCSP nonce extension')
                    # RFC 8954 §2.1: the nonce is 1..32 octets. Unbounded input
                    # would be echoed back into the signed response, letting a
                    # client inflate the work and bandwidth of every reply.
                    if not 1 <= len(nonce) <= 32:
                        raise ValueError(
                            'OCSP nonce must be 1-32 octets (RFC 8954 §2.1)'
                        )

        for request_item in tbs_request['request_list']:
            single_extensions = request_item['single_request_extensions']
            if single_extensions.native is None:
                continue
            for extension in single_extensions:
                if (extension['critical'].native
                        and extension['extn_id'].dotted != _NONCE_OID):
                    unsupported_critical = True
        return nonce, unsupported_critical

    def _resolve_signing(self, ca: CA, ca_cert: x509.Certificate):
        """Pick the OCSP signing identity: delegated responder first, else CA key.

        Trying the responder first matters for key-less/offline CAs (#302): a
        certificate-only import or a file-exported offline CA has no usable CA
        key, but a delegated responder whose own key stays online can still
        sign. Returns (signing_cert, signing_key, use_delegated); raises
        OCSPSigningUnavailable for the EXPECTED no-identity states — CA taken
        offline (both password-protected and file-exported modes), or no key
        at all. Real faults (HSM failure, corrupt key material) keep
        propagating so they surface as internalError, not unauthorized.
        """
        responder_cert, responder_key = self._get_delegated_responder(ca)
        if responder_cert is not None and responder_key is not None:
            return responder_cert, responder_key, True
        # Signing-freeze invariant: an offline CA never signs with its own key
        # — a password-protected offline CA still holds an (encrypted) key,
        # but using it is exactly what taking the CA offline forbids.
        # A configured responder that failed the rule is named in the message:
        # "no delegated responder" alone misdescribed that state
        refused = getattr(self, '_refusal_reason', None)
        responder_state = (
            f"its delegated responder was refused ({refused})" if refused
            else "has no delegated responder"
        )
        if ca.offline:
            raise OCSPSigningUnavailable(
                f"CA {ca.descr} is offline and {responder_state}"
            )
        if not ca.has_private_key:
            raise OCSPSigningUnavailable(
                f"CA {ca.descr} has no private key and {responder_state}"
            )
        return ca_cert, self._load_ca_key(ca), False

    def _load_ca_key(self, ca: CA):
        """The CA's signing key: a software key, or the HSM wrapper registered
        as an RSA/EC private key, which cryptography's builders accept. A local
        wrapper that was not registered made the single-CertID path fail with
        internalError for every HSM-backed CA while the multi-CertID path,
        duck-typed, answered (self-review of #347)."""
        from services.hsm.ca_key_loader import get_ca_signing_key
        return get_ca_signing_key(ca, allow_revoked=True)

    @staticmethod
    def _bound_next_update(next_update, signing_cert, use_delegated):
        """A response must not claim currency beyond its signer's life: a
        delegated responder's nextUpdate is capped at its notAfter. The
        cache lives until nextUpdate, and a client rejects a response whose
        signer has expired (self-review of #347)."""
        if not use_delegated or signing_cert is None:
            return next_update
        not_after = signing_cert.not_valid_after_utc
        if next_update.tzinfo is None:
            not_after = not_after.replace(tzinfo=None)
        return min(next_update, not_after)

    def _load_cert(self, certificate: Certificate) -> Optional[x509.Certificate]:
        """Safely load a certificate's X.509 object, returning None if unavailable"""
        if not certificate or not certificate.crt:
            return None
        try:
            crt_pem = base64.b64decode(certificate.crt).decode('utf-8')
            return x509.load_pem_x509_certificate(crt_pem.encode(), self.backend)
        except Exception:
            return None
    
    def check_delegated_responder(self, ca: CA, responder_record) -> Optional[str]:
        """Why *responder_record* cannot sign OCSP responses for *ca*, or None.

        The single rule for a delegated responder (RFC 6960 §4.2.2.2): issued
        by this CA and verifiably signed by it, currently valid, not revoked,
        holding its key, carrying the OCSPSigning EKU and id-pkix-ocsp-nocheck.
        The responder applies it at answer time; the assignment and the list
        of eligible certificates apply the same one, so a certificate the
        responder would refuse is never offered or accepted only to be ignored
        (#347 review).
        """
        if not responder_record:
            return 'certificate not found'
        if not responder_record.crt:
            return 'certificate has no certificate yet'
        if not responder_record.prv:
            return 'certificate has no private key'
        if responder_record.revoked:
            return 'certificate is revoked'
        resp_cert = self._load_cert(responder_record)
        if not resp_cert:
            return 'certificate could not be parsed'
        try:
            ca_cert = x509.load_pem_x509_certificate(base64.b64decode(ca.crt), self.backend)
        except Exception:
            return 'CA certificate could not be parsed'
        if resp_cert.issuer != ca_cert.subject:
            return 'certificate was not issued by this CA'
        if not self._certificate_is_currently_valid(resp_cert):
            return 'certificate is expired or not yet valid'
        try:
            self._verify_certificate_signature(resp_cert, ca_cert)
        except Exception:
            return 'certificate signature does not verify against this CA'
        try:
            eku = resp_cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage)
        except x509.ExtensionNotFound:
            return 'certificate has no Extended Key Usage'
        if x509.oid.ExtendedKeyUsageOID.OCSP_SIGNING not in eku.value:
            return 'certificate lacks the OCSPSigning Extended Key Usage'
        # RFC 5280 §4.2.1.3: a Key Usage extension that omits digitalSignature
        # forbids signing anything but certificates and CRLs, OCSP responses
        # included; clients that honour it reject the signature (#347 review)
        try:
            key_usage = resp_cert.extensions.get_extension_for_class(x509.KeyUsage).value
        except x509.ExtensionNotFound:
            key_usage = None
        if key_usage is not None and not key_usage.digital_signature:
            return 'certificate Key Usage does not permit digitalSignature'
        # RFC 6960 §4.2.2.2.1: without it clients would check the responder's
        # own revocation status and loop; UCM refuses to sign with such a
        # certificate rather than produce answers clients reject
        try:
            resp_cert.extensions.get_extension_for_oid(x509.oid.ExtensionOID.OCSP_NO_CHECK)
        except x509.ExtensionNotFound:
            return 'certificate lacks the id-pkix-ocsp-nocheck extension (RFC 6960)'
        # The key must be loadable and be this certificate's key: a stored
        # key that belongs to another certificate signs answers no client
        # can verify (#347 review)
        try:
            key = self._load_responder_key(responder_record)
        except Exception:
            return 'private key could not be loaded'
        from utils.cert_issuer import private_key_matches
        if not private_key_matches(key, resp_cert):
            return 'private key does not match the certificate'
        return None

    def _load_responder_key(self, responder_record):
        try:
            from security.encryption import decrypt_private_key
            prv_decrypted = decrypt_private_key(responder_record.prv)
        except ImportError:
            prv_decrypted = responder_record.prv
        pem = base64.b64decode(prv_decrypted).decode('utf-8')
        return serialization.load_pem_private_key(pem.encode(), password=None, backend=self.backend)

    def _get_delegated_responder(self, ca: CA):
        """The configured delegated responder as (cert, key), or (None, None).

        A configured certificate that fails check_delegated_responder is
        refused with a warning and the CA signs itself.
        """
        self._refusal_reason = None
        config_row = SystemConfig.query.filter_by(key=f'ocsp_responder_cert_{ca.id}').first()
        responder_cert_id = config_row.value if config_row else ''
        if not responder_cert_id:
            return None, None

        try:
            responder_record = db.session.get(Certificate, int(responder_cert_id))
            reason = self.check_delegated_responder(ca, responder_record)
            if reason:
                logger.warning(
                    f"Delegated OCSP responder cert {responder_cert_id} for CA {ca.id} "
                    f"refused: {reason}; signing with the CA key"
                )
                self._refusal_reason = reason
                return None, None
            resp_cert = self._load_cert(responder_record)
            resp_key = self._load_responder_key(responder_record)
            logger.debug(f"Using delegated OCSP responder for CA {ca.descr}")
            return resp_cert, resp_key

        except Exception as e:
            logger.error(f"Failed to load delegated OCSP responder: {e}")
            return None, None

    @staticmethod
    def _certificate_is_currently_valid(cert: x509.Certificate) -> bool:
        now = datetime.now(timezone.utc)
        not_before = (
            cert.not_valid_before_utc
            if hasattr(cert, 'not_valid_before_utc')
            else cert.not_valid_before.replace(tzinfo=timezone.utc)
        )
        not_after = (
            cert.not_valid_after_utc
            if hasattr(cert, 'not_valid_after_utc')
            else cert.not_valid_after.replace(tzinfo=timezone.utc)
        )
        return not_before <= now <= not_after

    @staticmethod
    def _verify_certificate_signature(
        certificate: x509.Certificate, issuer: x509.Certificate
    ) -> None:
        public_key = issuer.public_key()
        signature_hash = certificate.signature_hash_algorithm
        if isinstance(public_key, rsa.RSAPublicKey):
            signature_padding = getattr(
                certificate, 'signature_algorithm_parameters', None
            ) or padding.PKCS1v15()
            public_key.verify(
                certificate.signature,
                certificate.tbs_certificate_bytes,
                signature_padding,
                signature_hash,
            )
        elif isinstance(public_key, ec.EllipticCurvePublicKey):
            public_key.verify(
                certificate.signature,
                certificate.tbs_certificate_bytes,
                ec.ECDSA(signature_hash),
            )
        elif isinstance(public_key, dsa.DSAPublicKey):
            public_key.verify(
                certificate.signature,
                certificate.tbs_certificate_bytes,
                signature_hash,
            )
        elif isinstance(public_key, (ed25519.Ed25519PublicKey, ed448.Ed448PublicKey)):
            public_key.verify(
                certificate.signature, certificate.tbs_certificate_bytes
            )
        else:
            raise ValueError('Unsupported delegated responder issuer key type')

    @staticmethod
    def _response_validity_hours() -> int:
        config = SystemConfig.query.filter_by(
            key='ocsp_response_validity_hours'
        ).first()
        raw_value = config.value if config else str(_DEFAULT_RESPONSE_VALIDITY_HOURS)
        try:
            hours = int(raw_value)
            if hours <= 0:
                raise ValueError
            if hours > _MAX_RESPONSE_VALIDITY_HOURS:
                logger.warning(
                    "ocsp_response_validity_hours %s exceeds max %s; clamping",
                    hours, _MAX_RESPONSE_VALIDITY_HOURS,
                )
                return _MAX_RESPONSE_VALIDITY_HOURS
            return hours
        except (TypeError, ValueError):
            logger.warning(
                "Invalid ocsp_response_validity_hours value %r; using default %s",
                raw_value,
                _DEFAULT_RESPONSE_VALIDITY_HOURS,
            )
            return _DEFAULT_RESPONSE_VALIDITY_HOURS

    @staticmethod
    def _status_for_serial(ca: CA, cert_serial: int):
        variants = serial_variants(cert_serial)
        certificate = None
        for row in Certificate.query.filter(
            Certificate.caref == ca.refid,
            Certificate.serial_number.in_(variants),
        ).all():
            if _record_holds_serial(row, cert_serial) is not False:
                certificate = row
                break
        if certificate and certificate.revoked:
            return (
                certificate,
                'revoked',
                certificate.revoked_at or utc_now(),
                _REASON_MAP.get(
                    certificate.revoke_reason, x509.ReasonFlags.unspecified
                ),
            )
        if not certificate:
            # The certificate of a CA signed by this issuer lives in the CA
            # table, not with the end-entity certificates (#344): answer for
            # it too, revoked when its parent revoked it (#343), else good
            # unless a persistent or external revocation record says otherwise.
            child_ca = _child_ca_for_serial(ca, cert_serial, variants)
            if child_ca is not None:
                if child_ca.revoked:
                    return (
                        child_ca,
                        'revoked',
                        child_ca.revoked_at or utc_now(),
                        _REASON_MAP.get(
                            child_ca.revoke_reason, x509.ReasonFlags.unspecified
                        ),
                    )
                certificate = child_ca
        if certificate is None or isinstance(certificate, CA):
            # Persistent revocation table: deleted certificates, and a CA
            # deleted after its revocation and imported again (its row is
            # new, the parent's record is not)
            rs = RevokedSerial.query.filter(
                RevokedSerial.caref == ca.refid,
                RevokedSerial.serial_number.in_(variants),
            ).first()
            if rs:
                return certificate, 'revoked', rs.revoked_at or utc_now(), _REASON_MAP.get(
                    rs.revoke_reason, x509.ReasonFlags.unspecified
                )
        # Externally-signed CRL uploaded for a key-less/offline CA (#302):
        # revocations decided next to the offline key exist only on that CRL,
        # so it overrides a 'good'/absent local record for this issuer.
        from services.crl_service import CRLService
        ext = CRLService.get_external_revocation(ca.id, cert_serial)
        if ext:
            # reason may be None (CRL entry without CRLReason) — the response
            # then omits revocationReason instead of claiming 'unspecified'.
            revoked_at, reason = ext
            return certificate, 'revoked', revoked_at or utc_now(), reason
        if not certificate:
            return None, 'unknown', None, None
        return certificate, 'good', None, None

    @staticmethod
    def _asn1_time(value: datetime) -> datetime:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)
        return value.replace(microsecond=0)

    @staticmethod
    def _asn1_certificate_status(
        status: str,
        revocation_time: Optional[datetime],
        revocation_reason: Optional[x509.ReasonFlags],
    ):
        if status == 'good':
            return {'good': None}
        if status == 'unknown':
            return {'unknown': None}
        revoked_info = {
            'revocation_time': OCSPService._asn1_time(revocation_time),
        }
        if revocation_reason is not None:
            revoked_info['revocation_reason'] = revocation_reason.name
        return {'revoked': revoked_info}

    @staticmethod
    def _sign_response_data(signing_key, response_data_der: bytes):
        public_key = signing_key.public_key()
        if isinstance(public_key, rsa.RSAPublicKey):
            signature = signing_key.sign(
                response_data_der, padding.PKCS1v15(), hashes.SHA256()
            )
            return signature, 'sha256_rsa'
        if isinstance(public_key, ec.EllipticCurvePublicKey):
            signature = signing_key.sign(
                response_data_der, ec.ECDSA(hashes.SHA256())
            )
            return signature, 'sha256_ecdsa'
        if isinstance(public_key, ed25519.Ed25519PublicKey):
            return signing_key.sign(response_data_der), 'ed25519'
        if isinstance(public_key, ed448.Ed448PublicKey):
            return signing_key.sign(response_data_der), 'ed448'
        if isinstance(public_key, dsa.DSAPublicKey):
            # Accepted as a responder like any other key type, so it has to
            # sign the multi-CertID answer too (#347 review)
            signature = signing_key.sign(response_data_der, hashes.SHA256())
            return signature, 'sha256_dsa'
        raise ValueError('Unsupported OCSP response signing key type')

    def generate_multi_response(
        self,
        ca: CA,
        request_items: Tuple[OCSPRequestItem, ...],
        request_nonce: Optional[bytes] = None,
    ) -> Tuple[bytes, Tuple[str, ...]]:
        """Build one BasicOCSPResponse containing every requested CertID."""
        try:
            ca_cert = x509.load_pem_x509_certificate(
                base64.b64decode(ca.crt), self.backend
            )
            # Signing identity: delegated responder first, else CA key
            signing_cert, signing_key, use_delegated = self._resolve_signing(ca, ca_cert)

            this_update = utc_now().replace(microsecond=0)
            next_update = this_update + timedelta(
                hours=self._response_validity_hours()
            )
            next_update = self._bound_next_update(next_update, signing_cert, use_delegated)
            single_responses = []
            statuses = []
            for item in request_items:
                _, status, revoked_at, revoked_reason = self._status_for_serial(
                    ca, item.serial_number
                )
                single_responses.append(asn1_ocsp.SingleResponse({
                    'cert_id': asn1_ocsp.CertId.load(
                        item.cert_id_der, strict=True
                    ),
                    'cert_status': self._asn1_certificate_status(
                        status, revoked_at, revoked_reason
                    ),
                    'this_update': self._asn1_time(this_update),
                    'next_update': self._asn1_time(next_update),
                }))
                statuses.append(status)

            signing_cert_asn1 = asn1_x509.Certificate.load(
                signing_cert.public_bytes(serialization.Encoding.DER)
            )
            subject_public_key = signing_cert_asn1[
                'tbs_certificate'
            ]['subject_public_key_info']['public_key'].contents[1:]
            response_data_fields = {
                'responder_id': {
                    'by_key': hashlib.sha1(subject_public_key).digest()
                },
                'produced_at': self._asn1_time(this_update),
                'responses': single_responses,
            }
            if request_nonce is not None:
                response_data_fields['response_extensions'] = [
                    asn1_ocsp.ResponseDataExtension({
                        'extn_id': 'nonce',
                        'critical': False,
                        'extn_value': asn1_core.OctetString(request_nonce),
                    })
                ]
            response_data = asn1_ocsp.ResponseData(response_data_fields)
            signature, signature_algorithm = self._sign_response_data(
                signing_key, response_data.dump()
            )
            basic_response_fields = {
                'tbs_response_data': response_data,
                'signature_algorithm': {'algorithm': signature_algorithm},
                'signature': signature,
            }
            if use_delegated:
                basic_response_fields['certs'] = [signing_cert_asn1]
            basic_response = asn1_ocsp.BasicOCSPResponse(basic_response_fields)
            response = asn1_ocsp.OCSPResponse({
                'response_status': 'successful',
                'response_bytes': {
                    'response_type': 'basic_ocsp_response',
                    'response': basic_response,
                },
            })
            logger.info(
                "Generated multi-certificate OCSP response with %d entries",
                len(single_responses),
            )
            return response.dump(), tuple(statuses)
        except OCSPSigningUnavailable as e:
            logger.warning(f"OCSP multi-response unauthorized: {e}")
            error_response = ocsp.OCSPResponseBuilder.build_unsuccessful(
                ocsp.OCSPResponseStatus.UNAUTHORIZED
            )
            return (
                error_response.public_bytes(serialization.Encoding.DER),
                ('unauthorized',),
            )
        except Exception as e:
            logger.error(
                f"Failed to generate multi-certificate OCSP response: {e}",
                exc_info=True,
            )
            error_response = ocsp.OCSPResponseBuilder.build_unsuccessful(
                ocsp.OCSPResponseStatus.INTERNAL_ERROR
            )
            return (
                error_response.public_bytes(serialization.Encoding.DER),
                ('error',),
            )

    def generate_response(
        self,
        ca: CA,
        cert_serial: int,
        request_nonce: Optional[bytes] = None,
        hash_algorithm: Optional[hashes.HashAlgorithm] = None,
        issuer_name_hash: Optional[bytes] = None,
        issuer_key_hash: Optional[bytes] = None,
    ) -> Tuple[bytes, str]:
        """
        Generate OCSP response for a certificate
        
        Args:
            ca: CA object
            cert_serial: Certificate serial number
            request_nonce: Optional nonce from request (for replay protection)
            hash_algorithm: Hash algorithm of the request CertID (RFC 6960 §4.1.1).
                The response SingleResponse MUST echo the request's CertID so
                clients (e.g. Cisco ASA) can correlate the status. Defaults to
                SHA-256 for legacy/internal callers.
            issuer_name_hash: Request's issuer name hash (echoed for unknown
                serials where no issuer cert is needed to recompute).
            issuer_key_hash: Request's issuer key hash (same as above).
            
        Returns:
            Tuple of (DER-encoded response, status string)
        """
        try:
            # RFC 6960 §4.2.1: the response CertID MUST use the same hash
            # algorithm as the request. A SHA-1 request gets a SHA-1 response,
            # a SHA-256 request gets SHA-256. Defaulting to SHA-256 keeps the
            # legacy internal contract (tests, scheduled pre-generation).
            algo = hash_algorithm or hashes.SHA256()
            algo_name = getattr(algo, 'name', 'sha256')

            # Load CA certificate
            ca_crt_pem = base64.b64decode(ca.crt).decode('utf-8')
            ca_cert = x509.load_pem_x509_certificate(ca_crt_pem.encode(), self.backend)

            # Signing identity: delegated responder first, else CA key
            signing_cert, signing_key, use_delegated = self._resolve_signing(ca, ca_cert)

            cert_serial_hex = format(cert_serial, 'x')

            # Single source of truth for revocation status — shared with the
            # multi-CertID path, includes external CRLs for key-less CAs (#302)
            certificate, cert_status, revocation_time, revocation_reason = \
                self._status_for_serial(ca, cert_serial)
            status = _CERT_STATUS_MAP[cert_status]
            
            # Build OCSP response
            this_update = utc_now()
            next_update = this_update + timedelta(
                hours=self._response_validity_hours()
            )
            next_update = self._bound_next_update(next_update, signing_cert, use_delegated)
            
            builder = ocsp.OCSPResponseBuilder()
            
            # Load the actual certificate (may be None for unknown serials)
            cert_x509 = self._load_cert(certificate) if certificate else None
            
            if cert_x509:
                # Standard path: recompute the CertID hashes from the issuer
                # cert using the REQUEST's hash algorithm, so the SingleResponse
                # CertID matches what the client sent (RFC 6960 §4.2.1). This is
                # what Cisco ASA (and other strict clients) rely on to map the
                # returned status back to their request.
                builder = builder.add_response(
                    cert=cert_x509,
                    issuer=ca_cert,
                    algorithm=algo,
                    cert_status=status,
                    this_update=this_update,
                    next_update=next_update,
                    revocation_time=revocation_time,
                    revocation_reason=revocation_reason
                )
            else:
                # Hash-based response for unknown serials or missing .crt
                # RFC 6960: unknown serial gets UNKNOWN status in a successful
                # response. Echo the request's issuer hashes directly when
                # provided (they were already validated against this CA in
                # _find_ca_by_issuer_hash); otherwise compute them fresh from
                # the CA cert with the chosen algorithm.
                if issuer_name_hash is None or issuer_key_hash is None:
                    h_name = hashes.Hash(algo)
                    h_name.update(ca_cert.subject.public_bytes(
                        serialization.Encoding.DER))
                    issuer_name_hash = h_name.finalize()
                    pubkey = ca_cert.public_key()
                    if isinstance(pubkey, rsa.RSAPublicKey):
                        spki_value = pubkey.public_bytes(
                            encoding=serialization.Encoding.DER,
                            format=serialization.PublicFormat.PKCS1,
                        )
                    elif isinstance(pubkey, ec.EllipticCurvePublicKey):
                        spki_value = pubkey.public_bytes(
                            encoding=serialization.Encoding.X962,
                            format=serialization.PublicFormat.UncompressedPoint,
                        )
                    else:
                        spki_value = pubkey.public_bytes(
                            encoding=serialization.Encoding.Raw,
                            format=serialization.PublicFormat.Raw,
                        )
                    h_key = hashes.Hash(algo)
                    h_key.update(spki_value)
                    issuer_key_hash = h_key.finalize()
                if hasattr(builder, 'add_response_by_hash'):
                    builder = builder.add_response_by_hash(
                        issuer_name_hash=issuer_name_hash,
                        issuer_key_hash=issuer_key_hash,
                        serial_number=cert_serial,
                        algorithm=algo,
                        cert_status=status,
                        this_update=this_update,
                        next_update=next_update,
                        revocation_time=revocation_time,
                        revocation_reason=revocation_reason
                    )
                else:
                    # cryptography <45 has no hash-only builder API. A
                    # transient certificate with the requested serial lets it
                    # encode the same UNKNOWN CertID without querying another
                    # issuer's certificate.
                    unknown_cert = _build_unknown_certificate(cert_serial, ca_cert)
                    builder = builder.add_response(
                        cert=unknown_cert,
                        issuer=ca_cert,
                        algorithm=algo,
                        cert_status=status,
                        this_update=this_update,
                        next_update=next_update,
                        revocation_time=revocation_time,
                        revocation_reason=revocation_reason
                    )
            
            builder = builder.responder_id(
                ocsp.OCSPResponderEncoding.HASH, signing_cert
            )

            # RFC 6960 §4.2.2.3: when signed by a delegated responder, the
            # response MUST include the responder's certificate so the
            # client can verify the signature without a separate fetch.
            if use_delegated:
                builder = builder.certificates([signing_cert])

            # Add nonce if provided (replay protection)
            if request_nonce is not None:
                builder = builder.add_extension(
                    x509.OCSPNonce(request_nonce),
                    critical=False
                )
            
            # Sign response (with CA key or delegated responder key)
            # For delegated responder, include responder cert chain
            # Ed25519/Ed448 take no digest choice; the multi-response path
            # already knew that, this one handed them SHA-256 and every answer
            # from such a responder came back as an error (#347 review)
            signing_public = signing_key.public_key()
            sign_algorithm = (
                None
                if isinstance(signing_public, (ed25519.Ed25519PublicKey, ed448.Ed448PublicKey))
                else hashes.SHA256()
            )
            response = builder.sign(signing_key, sign_algorithm)
            response_der = response.public_bytes(serialization.Encoding.DER)
            
            # Cache response — key includes the hash algorithm because a SHA-1
            # and a SHA-256 response for the same serial are different DER blobs.
            # Reusing one for the other would re-introduce issue #143.
            if request_nonce is None:
                cache_serial = f"{cert_serial_hex}:{algo_name}"
                self._cache_response(
                    ca_id=ca.id,
                    cert_serial=cache_serial,
                    response_der=response_der,
                    status=cert_status,
                    this_update=this_update,
                    next_update=next_update,
                    revocation_time=revocation_time,
                    revocation_reason=revocation_reason.value if revocation_reason else None
                )
            
            logger.info(f"Generated OCSP response for serial {cert_serial_hex}: {cert_status}")
            return response_der, cert_status

        except OCSPSigningUnavailable as e:
            logger.warning(f"OCSP response unauthorized: {e}")
            error_response = ocsp.OCSPResponseBuilder.build_unsuccessful(
                ocsp.OCSPResponseStatus.UNAUTHORIZED
            )
            return error_response.public_bytes(serialization.Encoding.DER), 'unauthorized'
        except Exception as e:
            logger.error(f"Failed to generate OCSP response: {e}", exc_info=True)
            error_response = ocsp.OCSPResponseBuilder.build_unsuccessful(
                ocsp.OCSPResponseStatus.INTERNAL_ERROR
            )
            return error_response.public_bytes(serialization.Encoding.DER), 'error'
    
    @staticmethod
    def invalidate_ca_cache(ca_id: int) -> int:
        """Delete every cached response of a CA.

        Called when the identity that signs its responses changes, a
        delegated responder assigned, removed or revoked: a cached response
        keeps the previous signer, and would be served with it until it
        expires (#347 review).
        """
        try:
            deleted = OCSPResponse.query.filter(
                OCSPResponse.ca_id == ca_id
            ).delete(synchronize_session=False)
            db.session.commit()
            logger.info(f"Invalidated {deleted} OCSP cache entries for CA {ca_id}")
            return deleted
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to invalidate OCSP cache for CA {ca_id}: {e}")
            return 0

    @staticmethod
    def responder_cas_for_certificate(cert_id: int) -> list:
        """Ids of the CAs whose delegated responder is this certificate."""
        rows = SystemConfig.query.filter(
            SystemConfig.key.like('ocsp_responder_cert_%'),
            SystemConfig.value == str(cert_id),
        ).all()
        cas = []
        for row in rows:
            try:
                cas.append(int(row.key.rsplit('_', 1)[1]))
            except (ValueError, IndexError):
                continue
        return cas

    @staticmethod
    def invalidate_cached_responses(serial, ca_id: Optional[int] = None) -> int:
        """Delete every cached response for a serial, across hash algorithms."""
        serial_hex = serial_to_hex(serial)
        if not serial_hex:
            return 0

        try:
            query = OCSPResponse.query
            if ca_id is not None:
                query = query.filter(OCSPResponse.ca_id == ca_id)
            deleted_count = query.filter(or_(
                OCSPResponse.cert_serial == serial_hex,
                OCSPResponse.cert_serial.like(f'{serial_hex}:%'),
            )).delete(synchronize_session=False)
            db.session.commit()
            logger.info(
                f"Invalidated {deleted_count} OCSP cache entries for serial {serial_hex}"
            )
            return deleted_count
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to invalidate OCSP cache for serial {serial_hex}: {e}")
            return 0

    def _cache_response(
        self,
        ca_id: int,
        cert_serial: str,
        response_der: bytes,
        status: str,
        this_update: datetime,
        next_update: datetime,
        revocation_time: Optional[datetime],
        revocation_reason: Optional[int]
    ):
        """Cache OCSP response in database"""
        try:
            # Check if response already exists
            existing = OCSPResponse.query.filter_by(
                ca_id=ca_id,
                cert_serial=cert_serial
            ).first()
            
            if existing:
                # Update existing
                existing.response_der = response_der
                existing.status = status
                existing.this_update = this_update
                existing.next_update = next_update
                existing.revocation_time = revocation_time
                existing.revocation_reason = revocation_reason
                existing.updated_at = utc_now()
            else:
                # Create new
                new_response = OCSPResponse(
                    ca_id=ca_id,
                    cert_serial=cert_serial,
                    response_der=response_der,
                    status=status,
                    this_update=this_update,
                    next_update=next_update,
                    revocation_time=revocation_time,
                    revocation_reason=revocation_reason
                )
                db.session.add(new_response)
            
            db.session.commit()
            logger.debug(f"Cached OCSP response for serial {cert_serial}")
            
        except Exception as e:
            logger.error(f"Failed to cache OCSP response: {e}")
            db.session.rollback()
    
    def get_cached_response(
        self,
        ca_id: int,
        cert_serial: str,
        hash_algorithm: Optional[hashes.HashAlgorithm] = None,
    ) -> Optional[bytes]:
        """
        Get cached OCSP response if still valid
        
        Args:
            ca_id: CA ID
            cert_serial: Certificate serial number (hex string)
            hash_algorithm: Hash algorithm of the request CertID. The cache is
                keyed per-algorithm because the same serial yields distinct
                responses for SHA-1 vs SHA-256 requests (issue #143).
            
        Returns:
            DER-encoded response or None if not cached or expired
        """
        try:
            algo_name = getattr(hash_algorithm, 'name', 'sha256') if hash_algorithm else 'sha256'
            cache_serial = f"{cert_serial}:{algo_name}"
            cached = OCSPResponse.query.filter_by(
                ca_id=ca_id,
                cert_serial=cache_serial
            ).first()
            
            if not cached:
                return None
            
            # Check if still valid
            if cached.next_update and cached.next_update < utc_now():
                logger.debug(f"Cached OCSP response expired for serial {cert_serial}")
                return None
            
            logger.debug(f"Using cached OCSP response for serial {cert_serial}")
            return cached.response_der
            
        except Exception as e:
            logger.error(f"Failed to retrieve cached OCSP response: {e}")
            return None
    
    def cleanup_expired_responses(self):
        """Remove expired OCSP responses from cache"""
        try:
            expired_count = OCSPResponse.query.filter(
                OCSPResponse.next_update < utc_now()
            ).delete()
            
            db.session.commit()
            logger.info(f"Cleaned up {expired_count} expired OCSP responses")
            
        except Exception as e:
            logger.error(f"Failed to cleanup expired OCSP responses: {e}")
            db.session.rollback()
