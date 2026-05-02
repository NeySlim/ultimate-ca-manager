"""
Certificate Model - Certificates and CSRs
"""
import json
from models import db
from utils.datetime_utils import utc_now, utc_isoformat


class Certificate(db.Model):
    """Certificate model"""
    __tablename__ = "certificates"
    
    id = db.Column(db.Integer, primary_key=True)
    refid = db.Column(db.String(36), unique=True, nullable=False, index=True)
    descr = db.Column(db.String(255), nullable=False)
    caref = db.Column(db.String(36), db.ForeignKey("certificate_authorities.refid"))
    crt = db.Column(db.Text)  # Nullable - CSR doesn't have cert yet
    csr = db.Column(db.Text)  # Base64 encoded CSR
    prv = db.Column(db.Text)  # Base64 encoded private key
    
    # Certificate details
    cert_type = db.Column(db.String(50))  # client_cert, server_cert, combined_cert, ca_cert
    subject = db.Column(db.Text)
    subject_cn = db.Column(db.String(255))  # Extracted CN for sorting
    issuer = db.Column(db.Text)
    serial_number = db.Column(db.String(100))
    aki = db.Column(db.String(200))  # Authority Key Identifier (hex, colon-separated)
    ski = db.Column(db.String(200))  # Subject Key Identifier (hex, colon-separated)
    valid_from = db.Column(db.DateTime)
    valid_to = db.Column(db.DateTime)
    key_algo = db.Column(db.String(50))  # RSA 2048, EC P-256, etc. (for sorting)
    
    # Subject Alternative Names (SAN)
    san_dns = db.Column(db.Text)  # JSON array of DNS names
    san_ip = db.Column(db.Text)   # JSON array of IP addresses
    san_email = db.Column(db.Text)  # JSON array of email addresses
    san_uri = db.Column(db.Text)  # JSON array of URIs
    
    # OCSP
    ocsp_uri = db.Column(db.String(255))
    
    # RFC 6066 — OCSP Must-Staple (TLS Feature extension)
    ocsp_must_staple = db.Column(db.Boolean, default=False)
    
    # Private key management
    private_key_location = db.Column(db.String(20), default='stored')  # 'stored' or 'download_only'
    
    # Status
    revoked = db.Column(db.Boolean, default=False)
    revoked_at = db.Column(db.DateTime)
    revoke_reason = db.Column(db.String(100))
    archived = db.Column(db.Boolean, default=False)  # For renewed certificates
    
    # Metadata
    imported_from = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=utc_now)
    created_by = db.Column(db.String(80))
    
    # Source tracking: 'manual', 'acme', 'scep', 'import', 'csr'
    source = db.Column(db.String(20), default='manual')
    
    # Template reference (optional - null if created without template)
    template_id = db.Column(db.Integer, db.ForeignKey("certificate_templates.id"), nullable=True)
    
    # Ownership (Pro feature - group-based access control)
    owner_group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=True)
    owner_group = db.relationship('Group', backref='owned_certificates')
    
    # Relationships
    ca = db.relationship("CA", back_populates="certificates")
    template = db.relationship("CertificateTemplate", foreign_keys=[template_id])
    
    @property
    def has_private_key(self) -> bool:
        """Check if certificate has a private key"""
        return bool(self.prv and len(self.prv) > 0)
    
    @property
    def san_dns_list(self) -> list:
        """Get list of DNS SANs"""
        import json
        if not self.san_dns:
            return []
        try:
            return json.loads(self.san_dns)
        except Exception:
            return []
    
    @property
    def san_ip_list(self) -> list:
        """Get list of IP SANs"""
        import json
        if not self.san_ip:
            return []
        try:
            return json.loads(self.san_ip)
        except Exception:
            return []
    
    @property
    def san_email_list(self) -> list:
        """Get list of Email SANs"""
        import json
        if not self.san_email:
            return []
        try:
            return json.loads(self.san_email)
        except Exception:
            return []
    
    @property
    def san_uri_list(self) -> list:
        """Get list of URI SANs"""
        import json
        if not self.san_uri:
            return []
        try:
            return json.loads(self.san_uri)
        except Exception:
            return []
            
    @property
    def key_type(self) -> str:
        """Parse key type from certificate or CSR"""
        try:
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend
            from cryptography.hazmat.primitives.asymmetric import rsa, ec, dsa
            import base64
            
            # Try parsing CRT first
            if self.crt:
                pem_data = base64.b64decode(self.crt).decode('utf-8')
                obj = x509.load_pem_x509_certificate(pem_data.encode(), default_backend())
                public_key = obj.public_key()
            # Then try parsing CSR
            elif self.csr:
                pem_data = base64.b64decode(self.csr).decode('utf-8')
                obj = x509.load_pem_x509_csr(pem_data.encode(), default_backend())
                public_key = obj.public_key()
            else:
                return "N/A"
            
            if isinstance(public_key, rsa.RSAPublicKey):
                return f"RSA {public_key.key_size}"
            elif isinstance(public_key, ec.EllipticCurvePublicKey):
                return f"EC {public_key.curve.name}"
            elif isinstance(public_key, dsa.DSAPublicKey):
                return f"DSA {public_key.key_size}"
            return "Unknown"
        except Exception:
            return "N/A"
    
    @property
    def common_name(self) -> str:
        """Extract Common Name from subject, or fallback to first SAN DNS"""
        cn = self._extract_dn_field('CN')
        if cn:
            return cn
        # Fallback: use first SAN DNS if available
        if self.san_dns:
            try:
                dns_list = json.loads(self.san_dns) if self.san_dns.startswith('[') else [self.san_dns]
                if dns_list:
                    return dns_list[0]
            except (json.JSONDecodeError, TypeError):
                pass
        # Last fallback: use descr
        if self.descr:
            return self.descr
        return ""
    
    @property
    def organization(self) -> str:
        """Extract Organization from subject"""
        return self._extract_dn_field('O')

    @property
    def organizational_unit(self) -> str:
        """Extract Organizational Unit from subject"""
        return self._extract_dn_field('OU')
    
    @property
    def issuer_name(self) -> str:
        """Extract issuer Common Name"""
        if not self.issuer:
            return ""
        cn = self._extract_dn_field('CN', self.issuer)
        return cn if cn else self.issuer
    
    @property
    def country(self) -> str:
        """Extract Country from subject"""
        return self._extract_dn_field('C')
    
    @property
    def state(self) -> str:
        """Extract State from subject"""
        return self._extract_dn_field('ST')
    
    @property
    def locality(self) -> str:
        """Extract Locality from subject"""
        return self._extract_dn_field('L')
    
    @property
    def email(self) -> str:
        """Extract Email from subject"""
        # Try emailAddress OID first, then 1.2.840.113549.1.9.1
        email = self._extract_dn_field('emailAddress')
        if not email:
            email = self._extract_dn_field('1.2.840.113549.1.9.1')
        return email
    
    # Mapping of short DN field names to their OID long equivalents
    _DN_FIELD_ALIASES = {
        'CN': 'commonName',
        'O': 'organizationName',
        'OU': 'organizationalUnitName',
        'C': 'countryName',
        'ST': 'stateOrProvinceName',
        'L': 'localityName',
    }

    def _extract_dn_field(self, field: str, dn_string: str = None) -> str:
        """Extract a field from DN string, supporting both short (CN) and long (commonName) formats"""
        if dn_string is None:
            dn_string = self.subject
        if not dn_string:
            return ""
        prefixes = [f'{field}=']
        alias = self._DN_FIELD_ALIASES.get(field)
        if alias:
            prefixes.append(f'{alias}=')
        for short, long in self._DN_FIELD_ALIASES.items():
            if field == long:
                prefixes.append(f'{short}=')
                break
        for part in dn_string.split(','):
            part = part.strip()
            for prefix in prefixes:
                if part.startswith(prefix):
                    return part[len(prefix):]
        return ""
    
    @property
    def key_algorithm(self) -> str:
        """Get key algorithm name (RSA, EC, etc.)"""
        key_info = self.key_type
        if key_info and key_info != "N/A":
            return key_info.split()[0]  # "RSA 2048" -> "RSA"
        return "Unknown"
    
    @property
    def key_size(self) -> int:
        """Get key size in bits"""
        key_info = self.key_type
        if key_info and key_info != "N/A":
            parts = key_info.split()
            if len(parts) >= 2:
                try:
                    return int(parts[1])
                except ValueError:
                    pass
        return 0
    
    @property
    def signature_algorithm(self) -> str:
        """Get signature algorithm from certificate"""
        try:
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend
            import base64
            
            if not self.crt:
                return "N/A"
            
            pem_data = base64.b64decode(self.crt).decode('utf-8')
            cert = x509.load_pem_x509_certificate(pem_data.encode(), default_backend())
            
            # Get signature algorithm
            sig_oid = cert.signature_algorithm_oid
            # Map common OIDs to friendly names
            sig_map = {
                '1.2.840.113549.1.1.11': 'SHA256-RSA',
                '1.2.840.113549.1.1.12': 'SHA384-RSA',
                '1.2.840.113549.1.1.13': 'SHA512-RSA',
                '1.2.840.113549.1.1.5': 'SHA1-RSA',
                '1.2.840.10045.4.3.2': 'ECDSA-SHA256',
                '1.2.840.10045.4.3.3': 'ECDSA-SHA384',
                '1.2.840.10045.4.3.4': 'ECDSA-SHA512',
            }
            return sig_map.get(sig_oid.dotted_string, sig_oid._name or str(sig_oid))
        except Exception:
            return "N/A"
    
    @property
    def thumbprint_sha1(self) -> str:
        """Get SHA1 thumbprint/fingerprint"""
        return self._get_thumbprint('sha1')
    
    @property
    def thumbprint_sha256(self) -> str:
        """Get SHA256 thumbprint/fingerprint"""
        return self._get_thumbprint('sha256')
    
    def _get_thumbprint(self, algorithm: str) -> str:
        """Calculate certificate thumbprint"""
        try:
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend
            from cryptography.hazmat.primitives import hashes
            import base64
            
            if not self.crt:
                return ""
            
            pem_data = base64.b64decode(self.crt).decode('utf-8')
            cert = x509.load_pem_x509_certificate(pem_data.encode(), default_backend())
            
            if algorithm == 'sha1':
                digest = cert.fingerprint(hashes.SHA1())
            else:
                digest = cert.fingerprint(hashes.SHA256())
            
            return ':'.join(f'{b:02X}' for b in digest)
        except Exception:
            return ""
    
    @property
    def days_remaining(self) -> int:
        """Days until expiration"""
        if not self.valid_to:
            return -1
        delta = self.valid_to - utc_now()
        return max(0, delta.days)
    
    @property
    def san_combined(self) -> str:
        """Combined SAN string for display"""
        sans = []
        if self.san_dns:
            try:
                import json
                dns_list = json.loads(self.san_dns) if self.san_dns.startswith('[') else [self.san_dns]
                sans.extend([f"DNS:{d}" for d in dns_list])
            except Exception:
                sans.append(f"DNS:{self.san_dns}")
        if self.san_ip:
            try:
                import json
                ip_list = json.loads(self.san_ip) if self.san_ip.startswith('[') else [self.san_ip]
                sans.extend([f"IP:{ip}" for ip in ip_list])
            except Exception:
                sans.append(f"IP:{self.san_ip}")
        if self.san_email:
            try:
                import json
                email_list = json.loads(self.san_email) if self.san_email.startswith('[') else [self.san_email]
                sans.extend([f"Email:{e}" for e in email_list])
            except Exception:
                sans.append(f"Email:{self.san_email}")
        return ', '.join(sans) if sans else ""
    
    @property
    def not_valid_before(self) -> str:
        """Formatted valid from date"""
        if not self.valid_from:
            return ""
        return self.valid_from.strftime("%Y-%m-%d %H:%M:%S UTC")
    
    @property
    def not_valid_after(self) -> str:
        """Formatted valid until date"""
        if not self.valid_to:
            return ""
        return self.valid_to.strftime("%Y-%m-%d %H:%M:%S UTC")
    
    def to_dict(self, include_private=False):
        """Convert to dictionary"""
        from datetime import datetime, timedelta
        
        # Calculate status
        status = "valid"
        if self.revoked:
            status = "revoked"
        elif self.valid_to:
            now = utc_now()
            if self.valid_to < now:
                status = "expired"
            elif self.valid_to < now + timedelta(days=30):
                status = "expiring"
        
        data = {
            "id": self.id,
            "refid": self.refid,
            "descr": self.descr,
            "caref": self.caref,
            "cert_type": self.cert_type,
            "subject": self.subject,
            "issuer": self.issuer,
            "serial_number": self.serial_number,
            "aki": self.aki,
            "ski": self.ski,
            "valid_from": utc_isoformat(self.valid_from),
            "valid_to": utc_isoformat(self.valid_to),
            "revoked": self.revoked,
            "revoked_at": utc_isoformat(self.revoked_at),
            "revoke_reason": self.revoke_reason,
            "archived": self.archived or False,
            "imported_from": self.imported_from,
            "created_at": utc_isoformat(self.created_at),
            "created_by": self.created_by,
            "source": self.source or 'manual',
            "has_private_key": self.has_private_key,
            "private_key_location": self.private_key_location,
            # Subject Alternative Names
            "san_dns": self.san_dns,
            "san_ip": self.san_ip,
            "san_email": self.san_email,
            "san_uri": self.san_uri,
            # OCSP
            "ocsp_uri": self.ocsp_uri,
            "ocsp_must_staple": self.ocsp_must_staple,
            # Computed properties for display
            "common_name": self.common_name,
            "cn": self.common_name,  # Alias
            "organization": self.organization,
            "country": self.country,
            "state": self.state,
            "locality": self.locality,
            "email": self.email,
            "organizational_unit": self.organizational_unit,
            "issuer_name": self.issuer_name,
            "not_valid_before": self.not_valid_before,
            "not_valid_after": self.not_valid_after,
            "status": status,
            # Key and signature info
            "key_type": self.key_type,
            "key_algo": self.key_algo,  # Stored value for sorting
            "key_algorithm": self.key_algorithm,
            "key_size": self.key_size,
            "signature_algorithm": self.signature_algorithm,
            # Thumbprints
            "thumbprint_sha1": self.thumbprint_sha1,
            "thumbprint_sha256": self.thumbprint_sha256,
            # Computed
            "days_remaining": self.days_remaining,
            "san_combined": self.san_combined,
            # Ownership (Pro feature)
            "owner_group_id": self.owner_group_id,
            "owner_group_name": self.owner_group.name if self.owner_group else None,
            # PEM for display/copy
            "pem": self._decode_pem(self.crt),
        }
        if include_private:
            data["crt"] = self.crt
            data["csr"] = self.csr
            data["prv"] = self.prv
        return data
    
    def _decode_pem(self, encoded):
        """Decode base64 encoded PEM"""
        if not encoded:
            return None
        try:
            import base64
            return base64.b64decode(encoded).decode('utf-8')
        except Exception:
            return None
