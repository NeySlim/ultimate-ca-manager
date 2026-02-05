"""
SCEP Service - Simple Certificate Enrollment Protocol
Implements RFC 8894 (SCEP)
"""
import os
import base64
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.backends import default_backend
from cryptography.x509.oid import NameOID, ExtensionOID
from Crypto.Cipher import DES3, AES
from Crypto.Protocol.KDF import PBKDF2
import asn1crypto.core
import asn1crypto.cms
import asn1crypto.x509
from pyasn1.codec.der import decoder as pyasn1_decoder
from pyasn1_modules import rfc5652

from models import db, CA, Certificate, SCEPRequest


class SCEPService:
    """SCEP Protocol Implementation"""
    
    # SCEP message types
    MSG_TYPE_CERT_REP = 3
    MSG_TYPE_PKI_REQ = 19
    MSG_TYPE_GET_CERT_INITIAL = 20
    
    # SCEP status codes
    STATUS_SUCCESS = 0
    STATUS_FAILURE = 2
    STATUS_PENDING = 3
    
    # Failure reasons
    FAIL_BAD_ALG = 0
    FAIL_BAD_MESSAGE_CHECK = 1
    FAIL_BAD_REQUEST = 2
    FAIL_BAD_TIME = 3
    FAIL_BAD_CERT_ID = 4
    
    def __init__(self, ca_refid: str, challenge_password: Optional[str] = None,
                 auto_approve: bool = False):
        """
        Initialize SCEP service for a specific CA
        
        Args:
            ca_refid: Reference ID of the CA to use for SCEP
            challenge_password: Optional challenge password for enrollment
            auto_approve: If True, automatically approve enrollment requests
        """
        self.ca_refid = ca_refid
        self.challenge_password = challenge_password
        self.auto_approve = auto_approve
        
        # Load CA from database
        self.ca = CA.query.filter_by(refid=ca_refid).first()
        if not self.ca:
            raise ValueError(f"CA not found: {ca_refid}")
        
        # Load CA certificate and private key
        self.ca_cert = x509.load_pem_x509_certificate(
            base64.b64decode(self.ca.crt), default_backend()
        )
        self.ca_key = serialization.load_pem_private_key(
            base64.b64decode(self.ca.prv),
            password=None,
            backend=default_backend()
        )
    
    def get_ca_caps(self) -> str:
        """
        Get CA capabilities for SCEP
        Returns plaintext list of capabilities
        """
        capabilities = [
            "POSTPKIOperation",  # Support POST for PKIOperation
            "SHA-1",             # Support SHA-1
            "SHA-256",           # Support SHA-256
            "SHA-512",           # Support SHA-512
            "DES3",              # Support 3DES encryption
            "AES",               # Support AES encryption
            "SCEPStandard",      # Standard SCEP implementation
            "Renewal",           # Support certificate renewal
        ]
        return "\n".join(capabilities)
    
    def get_ca_cert(self) -> bytes:
        """
        Get CA certificate in DER format for SCEP GetCACert
        Returns raw DER bytes
        """
        return self.ca_cert.public_bytes(serialization.Encoding.DER)
    
    def get_ca_cert_chain(self) -> bytes:
        """
        Get CA certificate chain in degenerate PKCS#7 format
        Used when CA has issuer chain
        """
        # For now, return single cert in PKCS#7
        # TODO: Include full chain if intermediate CA
        return self._create_degenerate_pkcs7([self.ca_cert])
    
    def process_pkcs_req(self, pkcs7_data: bytes, client_ip: str) -> Tuple[bytes, int]:
        """
        Process SCEP PKCSReq enrollment request
        
        Args:
            pkcs7_data: PKCS#7 signed data from client
            client_ip: Client IP address for logging
            
        Returns:
            Tuple of (PKCS#7 response, HTTP status code)
        """
        try:
            # Parse PKCS#7 message
            content_info = asn1crypto.cms.ContentInfo.load(pkcs7_data)
            
            if content_info['content_type'].native != 'signed_data':
                return self._create_error_response(
                    self.FAIL_BAD_REQUEST, "Expected SignedData"
                ), 200
            
            signed_data = content_info['content']
            
            # Extract CSR from encapsulated content
            encap_content = signed_data['encap_content_info']
            
            # The content is an OctetString containing encrypted data
            encrypted_content = encap_content['content']
            encrypted_bytes = encrypted_content.native if hasattr(encrypted_content, 'native') else bytes(encrypted_content)
            
            # The encrypted content is a PKCS#7 envelopedData containing the CSR
            # We need to decrypt it using our CA private key
            try:
                # Parse the enveloped data with asn1crypto first to check type
                envdata = asn1crypto.cms.ContentInfo.load(encrypted_bytes)
                
                if envdata['content_type'].native == 'enveloped_data':
                    # This is envelopedData - use pyasn1 to handle constructed OctetString
                    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
                    
                    # Parse with pyasn1 to handle BER constructed OctetString
                    content_info_inner, _ = pyasn1_decoder.decode(encrypted_bytes, asn1Spec=rfc5652.ContentInfo())
                    env_data, _ = pyasn1_decoder.decode(bytes(content_info_inner['content']), asn1Spec=rfc5652.EnvelopedData())
                    
                    # Get recipient info - it's a CHOICE, need to get the component
                    recipient_info = env_data['recipientInfos'][0]
                    recipient_ktri = recipient_info.getComponent()  # Get KeyTransRecipientInfo from CHOICE
                    encrypted_key_bytes = bytes(recipient_ktri['encryptedKey'])
                    
                    # Decrypt the content encryption key with CA private key
                    content_encryption_key = self.ca_key.decrypt(
                        encrypted_key_bytes,
                        padding.PKCS1v15()
                    )
                    
                    # Get encrypted content and algorithm
                    enc_info = env_data['encryptedContentInfo']
                    encrypted_content_bytes = bytes(enc_info['encryptedContent'])
                    alg_oid = str(enc_info['contentEncryptionAlgorithm']['algorithm'])
                    alg_params = enc_info['contentEncryptionAlgorithm']['parameters']
                    
                    # Extract IV from parameters (ASN.1 encoded OctetString)
                    if alg_params and alg_params.hasValue():
                        params_bytes = bytes(alg_params)
                        # Parameters are DER-encoded OctetString
                        from pyasn1.type import univ
                        iv_octets, _ = pyasn1_decoder.decode(params_bytes, asn1Spec=univ.OctetString())
                        iv = bytes(iv_octets)
                    else:
                        iv = b'\x00' * 8  # Default IV
                    
                    # Decrypt the encrypted content to get CSR
                    if '1.3.14.3.2.7' in alg_oid:  # DES
                        # DES-CBC
                        from Crypto.Cipher import DES
                        cipher = DES.new(content_encryption_key, DES.MODE_CBC, iv)
                        csr_data = cipher.decrypt(encrypted_content_bytes)
                        # Remove PKCS#7 padding
                        pad_len = csr_data[-1]
                        csr_data = csr_data[:-pad_len]
                    elif '1.2.840.113549.3.7' in alg_oid:  # 3DES
                        cipher = DES3.new(content_encryption_key, DES3.MODE_CBC, iv)
                        csr_data = cipher.decrypt(encrypted_content_bytes)
                        # Remove PKCS#7 padding
                        pad_len = csr_data[-1]
                        csr_data = csr_data[:-pad_len]
                    else:
                        raise ValueError(f"Unsupported encryption algorithm: {alg_oid}")
                else:
                    # Not enveloped, use as-is (shouldn't happen in modern SCEP)
                    csr_data = encrypted_bytes
                    
            except Exception as e:
                # If decryption fails, try using the data as-is
                import traceback
                print(f"Warning: Could not decrypt envelopedData: {e}", flush=True)
                traceback.print_exc()
                csr_data = encrypted_bytes
            
            # Parse CSR
            csr = x509.load_der_x509_csr(csr_data, default_backend())
            
            print(f"DEBUG: CSR parsed successfully, subject = {csr.subject.rfc4514_string()}", flush=True)
            
            # Extract attributes from SCEP message
            attrs = self._extract_scep_attributes(signed_data)
            transaction_id = attrs.get('transactionID')
            message_type = attrs.get('messageType')
            sender_nonce = attrs.get('senderNonce')
            challenge_pwd = attrs.get('challengePassword')
            
            # Also check for challengePassword in CSR attributes (where scepclient puts it)
            if not challenge_pwd:
                try:
                    from cryptography.x509.oid import AttributeOID
                    for attr in csr.attributes:
                        if attr.oid == AttributeOID.CHALLENGE_PASSWORD:
                            challenge_pwd = attr.value
                            break
                except Exception as e:
                    print(f"DEBUG: Could not extract challenge from CSR: {e}", flush=True)
            
            print(f"DEBUG: Extracted attributes: txn_id={transaction_id}, msg_type={message_type}, challenge_pwd={'***' if challenge_pwd else None}", flush=True)
            
            if not transaction_id:
                return self._create_error_response(
                    self.FAIL_BAD_REQUEST, "Missing transactionID"
                ), 200
            
            # Validate challenge password if configured
            if self.challenge_password:
                # SECURITY: Use constant-time comparison to prevent timing attacks
                import hmac
                if not challenge_pwd or not hmac.compare_digest(
                    challenge_pwd.encode() if isinstance(challenge_pwd, str) else challenge_pwd,
                    self.challenge_password.encode() if isinstance(self.challenge_password, str) else self.challenge_password
                ):
                    return self._create_error_response(
                        self.FAIL_BAD_MESSAGE_CHECK, "Invalid challenge password"
                    ), 200
            
            # Check if request already exists
            existing = SCEPRequest.query.filter_by(
                transaction_id=transaction_id
            ).first()
            
            if existing:
                # Return status of existing request
                if existing.status == "approved" and existing.cert_refid:
                    # Return issued certificate
                    cert = Certificate.query.filter_by(
                        refid=existing.cert_refid
                    ).first()
                    if cert:
                        cert_obj = x509.load_pem_x509_certificate(
                            base64.b64decode(cert.crt), default_backend()
                        )
                        # Load CSR from existing request
                        existing_csr_data = base64.b64decode(existing.csr)
                        existing_csr = x509.load_der_x509_csr(existing_csr_data, default_backend())
                        return self._create_cert_rep_success(
                            cert_obj, transaction_id, sender_nonce, existing_csr
                        ), 200
                
                elif existing.status == "rejected":
                    return self._create_error_response(
                        self.FAIL_BAD_REQUEST,
                        existing.rejection_reason or "Request rejected"
                    ), 200
                
                else:  # pending
                    return self._create_cert_rep_pending(
                        transaction_id, sender_nonce
                    ), 200
            
            # Create new SCEP request
            subject_str = csr.subject.rfc4514_string()
            
            scep_req = SCEPRequest(
                transaction_id=transaction_id,
                csr=base64.b64encode(csr_data).decode('utf-8'),
                status="pending",
                subject=subject_str,
                client_ip=client_ip
            )
            db.session.add(scep_req)
            
            # Auto-approve if configured
            print(f"DEBUG: auto_approve = {self.auto_approve}, challenge_password = {self.challenge_password}", flush=True)
            if self.auto_approve:
                print(f"DEBUG: Auto-approve enabled, creating certificate...", flush=True)
                cert_refid = self._auto_approve_request(scep_req, csr)
                print(f"DEBUG: Certificate created with refid: {cert_refid}", flush=True)
                scep_req.status = "approved"
                scep_req.cert_refid = cert_refid
                scep_req.approved_by = "auto"
                scep_req.approved_at = datetime.utcnow()
                
                db.session.commit()
                
                # Return issued certificate
                cert = Certificate.query.filter_by(refid=cert_refid).first()
                cert_obj = x509.load_pem_x509_certificate(
                    base64.b64decode(cert.crt), default_backend()
                )
                print(f"DEBUG: Returning SUCCESS response", flush=True)
                return self._create_cert_rep_success(
                    cert_obj, transaction_id, sender_nonce, csr
                ), 200
            
            else:
                # Manual approval required
                print(f"DEBUG: auto_approve is FALSE, returning PENDING", flush=True)
                db.session.commit()
                return self._create_cert_rep_pending(
                    transaction_id, sender_nonce
                ), 200
        
        except Exception as e:
            print(f"SCEP PKCSReq error: {e}")
            import traceback
            traceback.print_exc()
            return self._create_error_response(
                self.FAIL_BAD_REQUEST, str(e)
            ), 200
    
    def approve_request(self, transaction_id: str, approved_by: str,
                       validity_days: int = 365) -> Optional[str]:
        """
        Approve a pending SCEP request
        
        Args:
            transaction_id: Transaction ID of the request
            approved_by: Username approving the request
            validity_days: Certificate validity in days
            
        Returns:
            Certificate refid if successful, None otherwise
        """
        scep_req = SCEPRequest.query.filter_by(
            transaction_id=transaction_id
        ).first()
        
        if not scep_req or scep_req.status != "pending":
            return None
        
        # Load CSR
        csr_data = base64.b64decode(scep_req.csr)
        csr = x509.load_der_x509_csr(csr_data, default_backend())
        
        # Issue certificate
        cert_refid = self._auto_approve_request(scep_req, csr, validity_days)
        
        # Update request
        scep_req.status = "approved"
        scep_req.cert_refid = cert_refid
        scep_req.approved_by = approved_by
        scep_req.approved_at = datetime.utcnow()
        db.session.commit()
        
        return cert_refid
    
    def reject_request(self, transaction_id: str, reason: str) -> bool:
        """
        Reject a pending SCEP request
        
        Args:
            transaction_id: Transaction ID of the request
            reason: Reason for rejection
            
        Returns:
            True if successful
        """
        scep_req = SCEPRequest.query.filter_by(
            transaction_id=transaction_id
        ).first()
        
        if not scep_req or scep_req.status != "pending":
            return False
        
        scep_req.status = "rejected"
        scep_req.rejection_reason = reason
        db.session.commit()
        
        return True
    
    def _auto_approve_request(self, scep_req: SCEPRequest,
                             csr: x509.CertificateSigningRequest,
                             validity_days: int = 365) -> str:
        """
        Auto-approve and issue certificate for SCEP request
        
        Returns:
            Certificate refid
        """
        import uuid
        
        # Generate unique refid
        cert_refid = str(uuid.uuid4())
        
        # Build certificate
        subject = csr.subject
        public_key = csr.public_key()
        
        # Create certificate
        builder = x509.CertificateBuilder()
        builder = builder.subject_name(subject)
        builder = builder.issuer_name(self.ca_cert.subject)
        builder = builder.public_key(public_key)
        builder = builder.serial_number(x509.random_serial_number())
        builder = builder.not_valid_before(datetime.utcnow())
        builder = builder.not_valid_after(
            datetime.utcnow() + timedelta(days=validity_days)
        )
        
        # Add extensions from CSR
        try:
            extensions = csr.extensions
            for ext in extensions:
                if ext.oid == ExtensionOID.SUBJECT_ALTERNATIVE_NAME:
                    builder = builder.add_extension(
                        ext.value, critical=False
                    )
                elif ext.oid == ExtensionOID.KEY_USAGE:
                    builder = builder.add_extension(
                        ext.value, critical=True
                    )
                elif ext.oid == ExtensionOID.EXTENDED_KEY_USAGE:
                    builder = builder.add_extension(
                        ext.value, critical=False
                    )
        except x509.ExtensionNotFound:
            pass
        
        # Add basic constraints
        builder = builder.add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True
        )
        
        # Add key identifiers
        builder = builder.add_extension(
            x509.SubjectKeyIdentifier.from_public_key(public_key),
            critical=False
        )
        builder = builder.add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(
                self.ca_cert.public_key()
            ),
            critical=False
        )
        
        # Sign certificate
        cert = builder.sign(self.ca_key, hashes.SHA256(), default_backend())
        
        # Save to database and file
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        
        # Extract SANs from issued certificate
        import json
        san_dns_list = []
        san_ip_list = []
        san_email_list = []
        san_uri_list = []
        
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
            pass  # No SAN extension
        
        # Extract CN from subject, fallback to SAN DNS
        cn_value = None
        subject_str = subject.rfc4514_string()
        for part in subject_str.split(','):
            if part.strip().upper().startswith('CN='):
                cn_value = part.strip()[3:]
                break
        if not cn_value and san_dns_list:
            cn_value = san_dns_list[0]
        
        # Save certificate to database
        cert_obj = Certificate(
            refid=cert_refid,
            caref=self.ca_refid,
            descr=f"SCEP: {subject.rfc4514_string()}",
            crt=base64.b64encode(cert_pem).decode('utf-8'),
            prv=None,  # No private key (client has it)
            cert_type="server_cert",
            subject=subject.rfc4514_string(),
            subject_cn=cn_value,
            issuer=cert.issuer.rfc4514_string(),
            serial_number=str(cert.serial_number),
            valid_from=cert.not_valid_before,
            valid_to=cert.not_valid_after,
            # Store extracted SANs
            san_dns=json.dumps(san_dns_list) if san_dns_list else None,
            san_ip=json.dumps(san_ip_list) if san_ip_list else None,
            san_email=json.dumps(san_email_list) if san_email_list else None,
            san_uri=json.dumps(san_uri_list) if san_uri_list else None,
            source="scep",
            created_by="scep"
        )
        db.session.add(cert_obj)
        
        # Save to file
        data_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "data"
        )
        certs_dir = os.path.join(data_dir, "certs")
        os.makedirs(certs_dir, exist_ok=True)
        
        cert_file = os.path.join(certs_dir, f"{cert_refid}.crt")
        with open(cert_file, "wb") as f:
            f.write(cert_pem)
        
        return cert_refid
    
    def _extract_scep_attributes(self, signed_data) -> Dict[str, Any]:
        """Extract SCEP attributes from SignedData"""
        attrs = {}
        
        try:
            # Get signer info
            signer_infos = signed_data['signer_infos']
            if len(signer_infos) > 0:
                signer_info = signer_infos[0]
                signed_attrs = signer_info['signed_attrs']
                
                for attr in signed_attrs:
                    attr_type = attr['type'].native
                    attr_values = attr['values']
                    
                    if len(attr_values) > 0:
                        value = attr_values[0]
                        
                        if attr_type == '2.16.840.1.113733.1.9.7':  # transactionID
                            attrs['transactionID'] = value.native.decode('utf-8') if isinstance(value.native, bytes) else value.native
                        elif attr_type == '2.16.840.1.113733.1.9.2':  # messageType
                            attrs['messageType'] = int.from_bytes(value.native, 'big') if isinstance(value.native, bytes) else value.native
                        elif attr_type == '2.16.840.1.113733.1.9.5':  # senderNonce
                            attrs['senderNonce'] = value.native
                        elif attr_type == '1.2.840.113549.1.9.7':  # challengePassword
                            attrs['challengePassword'] = value.native
        
        except Exception as e:
            print(f"Error extracting SCEP attributes: {e}")
        
        return attrs
    
    def _create_cert_rep_success(self, cert: x509.Certificate,
                                transaction_id: str,
                                sender_nonce: Optional[bytes],
                                client_csr: x509.CertificateSigningRequest) -> bytes:
        """Create successful CertRep PKCS#7 response with encrypted certificate"""
        # Create degenerate PKCS#7 with issued certificate and CA cert
        certs = [cert, self.ca_cert]
        pkcs7_data = self._create_degenerate_pkcs7(certs)
        
        # Encrypt the PKCS#7 data with client's public key (from CSR)
        encrypted_data = self._encrypt_for_client(pkcs7_data, client_csr)
        
        # Wrap in signed CertRep
        return self._create_cert_rep(
            self.STATUS_SUCCESS, encrypted_data, transaction_id, sender_nonce
        )
    
    def _create_cert_rep_pending(self, transaction_id: str,
                                sender_nonce: Optional[bytes]) -> bytes:
        """Create pending CertRep PKCS#7 response"""
        return self._create_cert_rep(
            self.STATUS_PENDING, b'', transaction_id, sender_nonce
        )
    
    def _create_error_response(self, fail_info: int, message: str) -> bytes:
        """Create error CertRep PKCS#7 response"""
        # For now, return simple failure
        # TODO: Include proper failInfo attribute
        return self._create_cert_rep(self.STATUS_FAILURE, b'', '', None)
    
    def _create_cert_rep(self, status: int, data: bytes,
                        transaction_id: str,
                        recipient_nonce: Optional[bytes]) -> bytes:
        """
        Create CertRep PKCS#7 response with proper SCEP signature
        
        Args:
            status: SCEP status (SUCCESS, PENDING, FAILURE)
            data: Content data (certificates for success, empty for others)
            transaction_id: SCEP transaction ID
            recipient_nonce: Recipient nonce for response
            
        Returns:
            Signed PKCS#7 CertRep message
        """
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
        import secrets
        
        # Create recipient nonce if not provided
        if recipient_nonce is None:
            recipient_nonce = secrets.token_bytes(16)
        
        # Prepare SCEP attributes for SignerInfo
        scep_attrs = []
        
        # transactionID (required)
        if transaction_id:
            scep_attrs.append({
                'type': '2.16.840.1.113733.1.9.7',  # transactionID
                'values': [asn1crypto.core.PrintableString(transaction_id)]
            })
        
        # messageType = 3 (CertRep)
        scep_attrs.append({
            'type': '2.16.840.1.113733.1.9.2',  # messageType
            'values': [asn1crypto.core.PrintableString('3')]
        })
        
        # pkiStatus
        print(f"DEBUG _create_cert_rep: status={status}, data_len={len(data) if data else 0}", flush=True)
        scep_attrs.append({
            'type': '2.16.840.1.113733.1.9.3',  # pkiStatus
            'values': [asn1crypto.core.PrintableString(str(status))]
        })
        
        # senderNonce (our nonce)
        sender_nonce = secrets.token_bytes(16)
        scep_attrs.append({
            'type': '2.16.840.1.113733.1.9.5',  # senderNonce
            'values': [asn1crypto.core.OctetString(sender_nonce)]
        })
        
        # recipientNonce (echo back the sender's nonce)
        if recipient_nonce:
            scep_attrs.append({
                'type': '2.16.840.1.113733.1.9.6',  # recipientNonce
                'values': [asn1crypto.core.OctetString(recipient_nonce)]
            })
        
        # Create encapsulated content
        if data:
            encap_content = {
                'content_type': 'data',
                'content': asn1crypto.core.OctetString(data)
            }
        else:
            encap_content = {
                'content_type': 'data',
            }
        
        # Sign the content with CA key
        # For SCEP, we sign the hash of the encapsulated content + signed attributes
        digest_algo = hashes.SHA256()
        
        # Compute message digest of content (the encrypted/enveloped data for SUCCESS)
        if data:
            from cryptography.hazmat.primitives import hashes as crypto_hashes
            digest_obj = crypto_hashes.Hash(crypto_hashes.SHA256())
            digest_obj.update(data)
            message_digest = digest_obj.finalize()
        else:
            # Empty data - hash of empty string
            from cryptography.hazmat.primitives import hashes as crypto_hashes
            digest_obj = crypto_hashes.Hash(crypto_hashes.SHA256())
            message_digest = digest_obj.finalize()
        
        # Build SignedAttributes structure with correct message digest
        from datetime import datetime
        import pytz
        
        signed_attrs = asn1crypto.cms.CMSAttributes(scep_attrs + [
            {
                'type': 'content_type',
                'values': ['data']
            },
            {
                'type': 'message_digest',
                'values': [asn1crypto.core.OctetString(message_digest)]
            },
            {
                'type': 'signing_time',
                'values': [asn1crypto.core.UTCTime(datetime.now(pytz.UTC))]
            }
        ])
        
        # Sign the DER-encoded signed attributes
        signed_attrs_der = signed_attrs.dump()
        # Replace the outer tag from SET to [0] IMPLICIT SET for signing
        signed_attrs_for_signing = b'\x31' + signed_attrs_der[1:]
        
        signature = self.ca_key.sign(
            signed_attrs_for_signing,
            asym_padding.PKCS1v15(),
            hashes.SHA256()
        )
        
        # Get CA certificate for SignerInfo
        ca_cert_der = self.ca_cert.public_bytes(serialization.Encoding.DER)
        ca_cert_asn1 = asn1crypto.x509.Certificate.load(ca_cert_der)
        
        # Create SignerInfo
        signer_info = asn1crypto.cms.SignerInfo({
            'version': 'v1',
            'sid': asn1crypto.cms.SignerIdentifier({
                'issuer_and_serial_number': {
                    'issuer': ca_cert_asn1.issuer,
                    'serial_number': ca_cert_asn1.serial_number
                }
            }),
            'digest_algorithm': {'algorithm': 'sha256'},
            'signed_attrs': signed_attrs,
            'signature_algorithm': {'algorithm': 'rsassa_pkcs1v15'},
            'signature': asn1crypto.core.OctetString(signature),
        })
        
        # Create SignedData
        signed_data = asn1crypto.cms.SignedData({
            'version': 'v1',
            'digest_algorithms': [{'algorithm': 'sha256'}],
            'encap_content_info': encap_content,
            'certificates': [ca_cert_asn1],
            'signer_infos': [signer_info],
        })
        
        # Wrap in ContentInfo
        content_info = asn1crypto.cms.ContentInfo({
            'content_type': 'signed_data',
            'content': signed_data,
        })
        
        return content_info.dump()
    
    def _create_degenerate_pkcs7(self, certs: list) -> bytes:
        """
        Create degenerate PKCS#7 (certs-only) structure
        
        Args:
            certs: List of x509.Certificate objects
            
        Returns:
            DER-encoded PKCS#7 structure
        """
        # Build certificates sequence
        cert_ders = []
        for cert in certs:
            cert_der = cert.public_bytes(serialization.Encoding.DER)
            cert_ders.append(asn1crypto.x509.Certificate.load(cert_der))
        
        # Create SignedData structure (degenerate - no signatures)
        signed_data = asn1crypto.cms.SignedData({
            'version': 1,
            'digest_algorithms': [],
            'encap_content_info': {
                'content_type': 'data',
            },
            'certificates': cert_ders,
            'signer_infos': [],
        })
        
        # Wrap in ContentInfo
        content_info = asn1crypto.cms.ContentInfo({
            'content_type': 'signed_data',
            'content': signed_data,
        })
        
        return content_info.dump()
    
    def _encrypt_for_client(self, data: bytes, client_csr: x509.CertificateSigningRequest) -> bytes:
        """
        Encrypt data for SCEP client using EnvelopedData
        
        Args:
            data: Data to encrypt (usually the degenerate PKCS#7 with certificates)
            client_csr: Client's CSR
            
        Returns:
            PKCS#7 EnvelopedData structure
        """
        from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
        from Crypto.Cipher import DES
        import secrets
        
        client_public_key = client_csr.public_key()
        
        # Generate random content encryption key (DES = 8 bytes)
        content_key = secrets.token_bytes(8)
        
        # Generate random IV for DES-CBC
        iv = secrets.token_bytes(8)
        
        # Encrypt data with DES-CBC
        cipher = DES.new(content_key, DES.MODE_CBC, iv)
        
        # Pad data to DES block size (8 bytes) using PKCS#7 padding
        block_size = 8
        padding_len = block_size - (len(data) % block_size)
        padded_data = data + bytes([padding_len] * padding_len)
        
        encrypted_content = cipher.encrypt(padded_data)
        
        # Encrypt the content key with client's public key
        encrypted_key = client_public_key.encrypt(
            content_key,
            asym_padding.PKCS1v15()
        )
        
        # RecipientInfo - use CSR subject as issuer
        from cryptography.x509.oid import NameOID
        from cryptography import x509 as crypto_x509
        
        # Use CSR subject for recipient identifier
        csr_subject_der = client_csr.subject.public_bytes(serialization.Encoding.DER)
        recipient_name = asn1crypto.x509.Name.load(csr_subject_der)
        
        recipient_info = asn1crypto.cms.RecipientInfo({
            'ktri': {
                'version': 'v0',
                'rid': {
                    'issuer_and_serial_number': {
                        'issuer': recipient_name,  # Use CSR subject
                        'serial_number': 1  # Use 1 as dummy serial
                    }
                },
                'key_encryption_algorithm': {
                    'algorithm': 'rsaes_pkcs1v15'
                },
                'encrypted_key': asn1crypto.core.OctetString(encrypted_key)
            }
        })
        
        # Create EncryptedContentInfo
        encrypted_content_info = {
            'content_type': 'data',
            'content_encryption_algorithm': {
                'algorithm': '1.3.14.3.2.7',  # DES-CBC
                'parameters': asn1crypto.core.OctetString(iv)
            },
            'encrypted_content': asn1crypto.core.OctetString(encrypted_content)
        }
        
        # Create EnvelopedData
        enveloped_data = asn1crypto.cms.EnvelopedData({
            'version': 'v0',
            'recipient_infos': [recipient_info],
            'encrypted_content_info': encrypted_content_info
        })
        
        # Wrap in ContentInfo
        content_info = asn1crypto.cms.ContentInfo({
            'content_type': 'enveloped_data',
            'content': enveloped_data
        })
        
        return content_info.dump()
