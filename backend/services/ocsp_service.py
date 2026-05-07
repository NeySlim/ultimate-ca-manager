"""
OCSP Service - Online Certificate Status Protocol (RFC 6960)
Handles OCSP request parsing and response generation
"""
import base64
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple
from cryptography import x509
from cryptography.x509 import ocsp
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa, padding, utils
from cryptography.hazmat.backends import default_backend

from models import db, CA, Certificate, OCSPResponse
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


class _HsmPrivateKeyWrapper:
    """
    Wraps an HSM key to work with cryptography's builder.sign() API.
    Delegates actual signing to the HSM provider.
    """
    
    def __init__(self, hsm_key_id: int, public_key):
        self._hsm_key_id = hsm_key_id
        self._public_key = public_key
        self.key_size = getattr(public_key, 'key_size', 2048)
    
    def sign(self, data: bytes, signature_algorithm, algorithm=None):
        """Sign data via HSM — compatible with cryptography's private key interface"""
        from services.hsm.hsm_signer import sign_with_hsm
        
        # For EC keys, the cryptography lib passes (data, ECDSA(hash))
        # For RSA keys, it passes (data, PKCS1v15(), hash)
        if isinstance(signature_algorithm, ec.ECDSA):
            return sign_with_hsm(data, self._hsm_key_id)
        elif isinstance(signature_algorithm, padding.PKCS1v15):
            return sign_with_hsm(data, self._hsm_key_id)
        else:
            return sign_with_hsm(data, self._hsm_key_id)
    
    def public_key(self):
        return self._public_key

# Map revoke_reason strings to X.509 ReasonFlags
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


class OCSPService:
    """Service for OCSP operations"""
    
    def __init__(self):
        self.backend = default_backend()
    
    def parse_request(self, request_der: bytes) -> Optional[ocsp.OCSPRequest]:
        """
        Parse OCSP request from DER-encoded bytes
        
        Args:
            request_der: DER-encoded OCSP request
            
        Returns:
            OCSPRequest object or None if parsing fails
        """
        try:
            ocsp_request = ocsp.load_der_ocsp_request(request_der)
            return ocsp_request
        except Exception as e:
            logger.error(f"Failed to parse OCSP request: {e}")
            return None
    
    def _load_ca_key(self, ca: CA):
        """Load CA private key, supporting both local and HSM storage"""
        if ca.uses_hsm:
            try:
                from services.hsm import HsmService
                from services.hsm.hsm_signer import get_hsm_public_key
                # Get public key to determine algorithm, then create a wrapper
                pub_pem = get_hsm_public_key(ca.hsm_key_id)
                pub_key = serialization.load_pem_public_key(
                    pub_pem.encode() if isinstance(pub_pem, str) else pub_pem,
                    backend=self.backend
                )
                # Return an HSM signing wrapper
                return _HsmPrivateKeyWrapper(ca.hsm_key_id, pub_key)
            except Exception as e:
                logger.warning(f"HSM signing unavailable for CA {ca.descr}: {e}")
                raise ValueError(f"HSM signing failed for CA {ca.descr}: {e}")
        
        if not ca.prv:
            raise ValueError(f"CA {ca.descr} has no private key")
        
        # Decrypt private key (stored encrypted in DB)
        try:
            from security.encryption import decrypt_private_key
            prv_decrypted = decrypt_private_key(ca.prv)
        except ImportError:
            prv_decrypted = ca.prv
        
        ca_key_pem = base64.b64decode(prv_decrypted).decode('utf-8')
        return serialization.load_pem_private_key(
            ca_key_pem.encode(),
            password=None,
            backend=self.backend
        )
    
    def _load_cert(self, certificate: Certificate) -> Optional[x509.Certificate]:
        """Safely load a certificate's X.509 object, returning None if unavailable"""
        if not certificate or not certificate.crt:
            return None
        try:
            crt_pem = base64.b64decode(certificate.crt).decode('utf-8')
            return x509.load_pem_x509_certificate(crt_pem.encode(), self.backend)
        except Exception:
            return None
    
    def _get_delegated_responder(self, ca: CA):
        """
        Check if CA has a delegated OCSP responder certificate (RFC 5019/6960).
        
        A delegated responder is a certificate issued by the CA with:
        - id-kp-OCSPSigning EKU (OID 1.3.6.1.5.5.7.3.9)
        - The OCSP No Check extension (OID 1.3.6.1.5.5.7.48.1.5)
        
        Returns (responder_cert, responder_key) or (None, None) if not configured.
        """
        from models import SystemConfig
        
        # Check if delegated responder is configured for this CA
        config_row = SystemConfig.query.filter_by(key=f'ocsp_responder_cert_{ca.id}').first()
        responder_cert_id = config_row.value if config_row else ''
        if not responder_cert_id:
            return None, None
        
        try:
            responder_record = Certificate.query.get(int(responder_cert_id))
            if not responder_record or not responder_record.crt or not responder_record.prv:
                logger.warning(f"Delegated OCSP responder cert {responder_cert_id} not found or incomplete")
                return None, None
            
            # Load and verify responder certificate has OCSPSigning EKU
            resp_cert = self._load_cert(responder_record)
            if not resp_cert:
                return None, None
            
            try:
                eku = resp_cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage)
                if x509.oid.ExtendedKeyUsageOID.OCSP_SIGNING not in eku.value:
                    logger.warning(f"Delegated responder cert {responder_cert_id} missing OCSPSigning EKU")
                    return None, None
            except x509.ExtensionNotFound:
                logger.warning(f"Delegated responder cert {responder_cert_id} has no EKU extension")
                return None, None

            # RFC 6960 §4.2.2.2.1: a delegated responder cert SHOULD include
            # the id-pkix-ocsp-nocheck extension so clients know not to
            # check its revocation status (which would loop). We refuse to
            # use a responder cert without it — clients will reject the
            # response anyway and fall through to the CA-signed path is
            # preferable to silently producing unverifiable responses.
            try:
                resp_cert.extensions.get_extension_for_oid(
                    x509.ObjectIdentifier('1.3.6.1.5.5.7.48.1.5')
                )
            except x509.ExtensionNotFound:
                logger.warning(
                    f"Delegated responder cert {responder_cert_id} missing "
                    f"id-pkix-ocsp-nocheck extension; refusing to use it"
                )
                return None, None
            
            # Load responder private key
            try:
                from security.encryption import decrypt_private_key
                prv_decrypted = decrypt_private_key(responder_record.prv)
            except ImportError:
                prv_decrypted = responder_record.prv
            
            resp_key_pem = base64.b64decode(prv_decrypted).decode('utf-8')
            resp_key = serialization.load_pem_private_key(
                resp_key_pem.encode(), password=None, backend=self.backend
            )
            
            logger.debug(f"Using delegated OCSP responder for CA {ca.descr}")
            return resp_cert, resp_key
            
        except Exception as e:
            logger.error(f"Failed to load delegated OCSP responder: {e}")
            return None, None
    
    def generate_response(
        self,
        ca: CA,
        cert_serial: int,
        request_nonce: Optional[bytes] = None
    ) -> Tuple[bytes, str]:
        """
        Generate OCSP response for a certificate
        
        Args:
            ca: CA object
            cert_serial: Certificate serial number
            request_nonce: Optional nonce from request (for replay protection)
            
        Returns:
            Tuple of (DER-encoded response, status string)
        """
        try:
            # Load CA certificate
            ca_crt_pem = base64.b64decode(ca.crt).decode('utf-8')
            ca_cert = x509.load_pem_x509_certificate(ca_crt_pem.encode(), self.backend)
            
            # Load CA private key (with decryption and HSM check)
            ca_key = self._load_ca_key(ca)
            
            # Check for delegated OCSP responder (RFC 5019/6960)
            responder_cert, responder_key = self._get_delegated_responder(ca)
            use_delegated = responder_cert is not None and responder_key is not None
            
            signing_cert = responder_cert if use_delegated else ca_cert
            signing_key = responder_key if use_delegated else ca_key
            
            # Find certificate in database. RFC 6960 sends the serial as an
            # ASN.1 INTEGER; UCM stores serials as the decimal string form
            # (Certificate.serial_number) while the OCSP cache uses the
            # lowercase hex form. Convert accordingly.
            cert_serial_dec = str(cert_serial)
            cert_serial_hex = format(cert_serial, 'x')
            certificate = Certificate.query.filter_by(serial_number=cert_serial_dec).first()
            
            # Determine certificate status
            if not certificate:
                status = ocsp.OCSPCertStatus.UNKNOWN
                cert_status = 'unknown'
                revocation_time = None
                revocation_reason = None
            elif certificate.revoked:
                status = ocsp.OCSPCertStatus.REVOKED
                cert_status = 'revoked'
                revocation_time = certificate.revoked_at or utc_now()
                revocation_reason = _REASON_MAP.get(
                    certificate.revoke_reason, x509.ReasonFlags.unspecified
                )
            else:
                status = ocsp.OCSPCertStatus.GOOD
                cert_status = 'good'
                revocation_time = None
                revocation_reason = None
            
            # Build OCSP response
            this_update = utc_now()
            next_update = this_update + timedelta(hours=24)
            
            builder = ocsp.OCSPResponseBuilder()
            
            # Load the actual certificate (may be None for unknown serials)
            cert_x509 = self._load_cert(certificate) if certificate else None
            
            if cert_x509:
                # Standard path: use cert object
                builder = builder.add_response(
                    cert=cert_x509,
                    issuer=ca_cert,
                    algorithm=hashes.SHA256(),
                    cert_status=status,
                    this_update=this_update,
                    next_update=next_update,
                    revocation_time=revocation_time,
                    revocation_reason=revocation_reason
                )
            else:
                # Hash-based response for unknown serials or missing .crt
                # RFC 6960: unknown serial gets UNKNOWN status in a successful response
                issuer_name_hash = hashes.Hash(hashes.SHA256())
                issuer_name_hash.update(ca_cert.subject.public_bytes())
                issuer_key_hash = hashes.Hash(hashes.SHA256())
                issuer_key_hash.update(
                    ca_cert.public_key().public_bytes(
                        serialization.Encoding.DER,
                        serialization.PublicFormat.SubjectPublicKeyInfo
                    )
                )
                builder = builder.add_response_by_hash(
                    issuer_name_hash=issuer_name_hash.finalize(),
                    issuer_key_hash=issuer_key_hash.finalize(),
                    serial_number=cert_serial,
                    algorithm=hashes.SHA256(),
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
            if request_nonce:
                builder = builder.add_extension(
                    x509.OCSPNonce(request_nonce),
                    critical=False
                )
            
            # Sign response (with CA key or delegated responder key)
            # For delegated responder, include responder cert chain
            if use_delegated:
                response = builder.sign(signing_key, hashes.SHA256())
            else:
                response = builder.sign(signing_key, hashes.SHA256())
            response_der = response.public_bytes(serialization.Encoding.DER)
            
            # Cache response
            self._cache_response(
                ca_id=ca.id,
                cert_serial=cert_serial_hex,
                response_der=response_der,
                status=cert_status,
                this_update=this_update,
                next_update=next_update,
                revocation_time=revocation_time,
                revocation_reason=revocation_reason.value if revocation_reason else None
            )
            
            logger.info(f"Generated OCSP response for serial {cert_serial_hex}: {cert_status}")
            return response_der, cert_status
            
        except Exception as e:
            logger.error(f"Failed to generate OCSP response: {e}", exc_info=True)
            error_response = ocsp.OCSPResponseBuilder.build_unsuccessful(
                ocsp.OCSPResponseStatus.INTERNAL_ERROR
            )
            return error_response.public_bytes(serialization.Encoding.DER), 'error'
    
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
    
    def get_cached_response(self, ca_id: int, cert_serial: str) -> Optional[bytes]:
        """
        Get cached OCSP response if still valid
        
        Args:
            ca_id: CA ID
            cert_serial: Certificate serial number (hex string)
            
        Returns:
            DER-encoded response or None if not cached or expired
        """
        try:
            cached = OCSPResponse.query.filter_by(
                ca_id=ca_id,
                cert_serial=cert_serial
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
