"""
CA Model - Certificate Authority
"""
import json
from models import db
from utils.datetime_utils import utc_now, utc_isoformat


class CA(db.Model):
    """Certificate Authority model"""
    __tablename__ = "certificate_authorities"
    
    id = db.Column(db.Integer, primary_key=True)
    refid = db.Column(db.String(36), unique=True, nullable=False, index=True)
    descr = db.Column(db.String(255), nullable=False)
    crt = db.Column(db.Text, nullable=False)  # Base64 encoded
    prv = db.Column(db.Text)  # Base64 encoded private key
    serial = db.Column(db.Integer, default=0)
    caref = db.Column(db.String(36))  # Parent CA refid for intermediate
    
    # Certificate details (parsed from crt)
    subject = db.Column(db.Text)
    issuer = db.Column(db.Text)
    serial_number = db.Column(db.String(100))  # Certificate serial number for duplicate detection
    ski = db.Column(db.String(200))  # Subject Key Identifier (hex, colon-separated)
    valid_from = db.Column(db.DateTime)
    valid_to = db.Column(db.DateTime)
    
    # Metadata
    imported_from = db.Column(db.String(50))  # 'opnsense', 'manual', 'generated'
    created_at = db.Column(db.DateTime, default=utc_now)
    created_by = db.Column(db.String(80))
    
    # Ownership (Pro feature - group-based access control)
    owner_group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=True)
    owner_group = db.relationship('Group', backref='owned_cas')
    
    # CRL Distribution Points (CDP)
    cdp_enabled = db.Column(db.Boolean, default=False)
    cdp_url = db.Column(db.String(512))  # Ex: http://ucm.local:8443/cdp/{ca_refid}/crl.pem
    delta_crl_enabled = db.Column(db.Boolean, default=False)
    delta_crl_interval = db.Column(db.Integer, default=4)  # Hours between delta CRLs
    
    # OCSP (Online Certificate Status Protocol)
    ocsp_enabled = db.Column(db.Boolean, default=False)
    ocsp_url = db.Column(db.String(512))  # Ex: http://ucm.local:8443/ocsp
    
    # AIA CA Issuers (RFC 5280 §4.2.2.1)
    aia_ca_issuers_enabled = db.Column(db.Boolean, default=False)
    aia_ca_issuers_url = db.Column(db.String(512))  # JSON array of URLs

    # Certificate Policies / CPS (RFC 5280 §4.2.1.4)
    cps_enabled = db.Column(db.Boolean, default=False)
    cps_uri = db.Column(db.Text)  # CPS URI (e.g., http://ca.example.com/cps.pdf)
    cps_oid = db.Column(db.Text, default='2.5.29.32.0')  # Policy OID (default: anyPolicy)
    
    # RFC 5280 §4.2.1.9 — BasicConstraints pathLenConstraint
    path_length = db.Column(db.Integer, nullable=True)  # None = unlimited
    
    # RFC 5280 §4.2.1.10 — NameConstraints (permitted/excluded subtrees)
    name_constraints_permitted = db.Column(db.Text)  # JSON: [{"type":"dns","value":".example.com"}]
    name_constraints_excluded = db.Column(db.Text)   # JSON: [{"type":"dns","value":".evil.com"}]
    
    # RFC 5280 §4.2.1.11 — PolicyConstraints
    policy_constraints_require = db.Column(db.Integer, nullable=True)  # requireExplicitPolicy skip certs
    policy_constraints_inhibit = db.Column(db.Integer, nullable=True)  # inhibitPolicyMapping skip certs
    
    # RFC 5280 §4.2.1.11 — InhibitAnyPolicy
    inhibit_any_policy = db.Column(db.Integer, nullable=True)  # skip certs
    
    # RFC 5280 §4.2.2.2 — Subject Information Access
    sia_enabled = db.Column(db.Boolean, default=False)
    sia_urls = db.Column(db.Text)  # JSON array of caRepository URLs
    
    # HSM Support - private key stored in Hardware Security Module
    hsm_key_id = db.Column(db.Integer, db.ForeignKey('hsm_keys.id'), nullable=True)
    hsm_key = db.relationship('HsmKey', backref='cas')
    
    # Relationships
    certificates = db.relationship("Certificate", back_populates="ca", lazy="dynamic")
    
    @property
    def has_private_key(self) -> bool:
        """Check if CA has a private key (local or HSM)"""
        return bool(self.prv and len(self.prv) > 0) or bool(self.hsm_key_id)
    
    @property
    def uses_hsm(self) -> bool:
        """Check if CA uses HSM for private key"""
        return bool(self.hsm_key_id)
    
    # Mapping of short DN field names to their OID long equivalents
    _DN_FIELD_ALIASES = {
        'CN': 'commonName',
        'O': 'organizationName',
        'OU': 'organizationalUnitName',
        'C': 'countryName',
        'ST': 'stateOrProvinceName',
        'L': 'localityName',
    }

    def _extract_dn_field(self, dn_string, field):
        """Extract a field from DN string, supporting both short (CN) and long (commonName) formats"""
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
    def common_name(self) -> str:
        """Extract Common Name from subject"""
        return self._extract_dn_field(self.subject, 'CN')
    
    @property
    def organization(self) -> str:
        """Extract Organization from subject"""
        return self._extract_dn_field(self.subject, 'O')
    
    @property
    def organizational_unit(self) -> str:
        """Extract Organizational Unit from subject"""
        return self._extract_dn_field(self.subject, 'OU')
    
    @property
    def country(self) -> str:
        """Extract Country from subject"""
        return self._extract_dn_field(self.subject, 'C')
    
    @property
    def state(self) -> str:
        """Extract State/Province from subject"""
        return self._extract_dn_field(self.subject, 'ST')
    
    @property
    def locality(self) -> str:
        """Extract Locality/City from subject"""
        return self._extract_dn_field(self.subject, 'L')
    
    @property
    def is_root(self) -> bool:
        """Check if this is a root CA (self-signed)"""
        return self.subject == self.issuer if self.subject and self.issuer else False
    
    @property
    def key_type(self) -> str:
        """Parse key type from certificate"""
        if not self.crt:
            return "N/A"
        try:
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend
            from cryptography.hazmat.primitives.asymmetric import rsa, ec, dsa
            import base64
            
            cert_pem = base64.b64decode(self.crt).decode('utf-8')
            cert = x509.load_pem_x509_certificate(cert_pem.encode(), default_backend())
            public_key = cert.public_key()
            
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
    def hash_algorithm(self) -> str:
        """Parse hash algorithm from certificate"""
        if not self.crt:
            return "N/A"
        try:
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend
            import base64
            
            cert_pem = base64.b64decode(self.crt).decode('utf-8')
            cert = x509.load_pem_x509_certificate(cert_pem.encode(), default_backend())
            return cert.signature_algorithm_oid._name.upper().replace('SHA', 'SHA-')
        except Exception:
            return "N/A"

    # --- URL helpers (JSON array storage with backward compat) ---

    def _get_urls(self, column_value):
        """Parse URL column value: JSON array or plain string → list"""
        if not column_value:
            return []
        if isinstance(column_value, str) and column_value.startswith('['):
            try:
                urls = json.loads(column_value)
                if isinstance(urls, list):
                    return [u for u in urls if u]
            except (json.JSONDecodeError, TypeError):
                pass
        return [column_value]

    def _get_primary_url(self, column_value):
        """Get first URL from column value"""
        urls = self._get_urls(column_value)
        return urls[0] if urls else None

    @staticmethod
    def _encode_urls(urls):
        """Encode URL list as JSON array string"""
        if not urls:
            return None
        if isinstance(urls, str):
            return json.dumps([urls])
        return json.dumps([u for u in urls if u])

    def get_cdp_urls(self):
        return self._get_urls(self.cdp_url)

    def get_primary_cdp_url(self):
        return self._get_primary_url(self.cdp_url)

    def set_cdp_urls(self, urls):
        self.cdp_url = self._encode_urls(urls)

    def get_ocsp_urls(self):
        return self._get_urls(self.ocsp_url)

    def get_primary_ocsp_url(self):
        return self._get_primary_url(self.ocsp_url)

    def set_ocsp_urls(self, urls):
        self.ocsp_url = self._encode_urls(urls)

    def get_aia_urls(self):
        return self._get_urls(self.aia_ca_issuers_url)

    def get_primary_aia_url(self):
        return self._get_primary_url(self.aia_ca_issuers_url)

    def set_aia_urls(self, urls):
        self.aia_ca_issuers_url = self._encode_urls(urls)
    
    # SIA URL helpers (same pattern as CDP/OCSP/AIA)
    def get_sia_urls(self):
        return self._get_urls(self.sia_urls)
    
    def get_primary_sia_url(self):
        return self._get_primary_url(self.sia_urls)
    
    def set_sia_urls(self, urls):
        self.sia_urls = self._encode_urls(urls)
    
    # NameConstraints helpers
    def get_name_constraints_permitted(self):
        if not self.name_constraints_permitted:
            return []
        try:
            return json.loads(self.name_constraints_permitted)
        except (json.JSONDecodeError, TypeError):
            return []
    
    def get_name_constraints_excluded(self):
        if not self.name_constraints_excluded:
            return []
        try:
            return json.loads(self.name_constraints_excluded)
        except (json.JSONDecodeError, TypeError):
            return []
    
    def set_name_constraints_permitted(self, constraints):
        self.name_constraints_permitted = json.dumps(constraints) if constraints else None
    
    def set_name_constraints_excluded(self, constraints):
        self.name_constraints_excluded = json.dumps(constraints) if constraints else None
    
    def to_dict(self, include_private=False):
        """Convert to dictionary"""
        # Determine CA type (lowercase for frontend)
        ca_type = "root" if self.is_root else "intermediate"
        
        # Determine status based on expiry
        status = "Active"
        if self.valid_to:
            if self.valid_to < utc_now():
                status = "Expired"
        
        # Format dates for frontend
        issued = self.valid_from.strftime("%Y-%m-%d") if self.valid_from else ""
        expires = self.valid_to.strftime("%Y-%m-%d") if self.valid_to else ""
        expiry = self.valid_to.strftime("%Y-%m-%d") if self.valid_to else ""
        
        # Get parent_id (numeric id) from caref (uuid)
        parent_id = None
        if self.caref:
            parent_ca = CA.query.filter_by(refid=self.caref).first()
            parent_id = parent_ca.id if parent_ca else None
        
        data = {
            "id": self.id,
            "refid": self.refid,
            "descr": self.descr,
            "name": self.descr,  # Alias for frontend
            "serial": self.serial,
            "caref": self.caref,
            "parent_id": parent_id,  # Numeric parent ID for frontend tree
            "ski": self.ski,
            "subject": self.subject,
            "issuer": self.issuer,
            "valid_from": utc_isoformat(self.valid_from),
            "valid_to": utc_isoformat(self.valid_to),
            "issued": issued,  # Frontend-friendly date
            "expires": expires,  # Frontend-friendly date
            "expiry": expiry,  # Frontend-friendly date
            "imported_from": self.imported_from,
            "created_at": utc_isoformat(self.created_at),
            "created_by": self.created_by,
            "has_private_key": self.has_private_key,
            # Computed properties for display
            "common_name": self.common_name,
            "organization": self.organization,
            "organizational_unit": self.organizational_unit,
            "country": self.country,
            "state": self.state,
            "locality": self.locality,
            "is_root": self.is_root,
            "type": ca_type,  # "Root CA" or "Intermediate"
            "status": status,  # "Active" or "Expired"
            "certs": self.certificates.count() if self.certificates else 0,  # Count of issued certificates
            "key_type": self.key_type,
            "hash_algorithm": self.hash_algorithm,
            # CRL/CDP configuration
            "cdp_enabled": self.cdp_enabled,
            "cdp_url": self.get_primary_cdp_url(),
            "cdp_urls": self.get_cdp_urls(),
            "delta_crl_enabled": self.delta_crl_enabled,
            "delta_crl_interval": self.delta_crl_interval or 4,
            # OCSP configuration
            "ocsp_enabled": self.ocsp_enabled,
            "ocsp_url": self.get_primary_ocsp_url(),
            "ocsp_urls": self.get_ocsp_urls(),
            # AIA CA Issuers
            "aia_ca_issuers_enabled": self.aia_ca_issuers_enabled,
            "aia_ca_issuers_url": self.get_primary_aia_url(),
            "aia_ca_issuers_urls": self.get_aia_urls(),
            # Certificate Policies / CPS (RFC 5280 §4.2.1.4)
            "cps_enabled": self.cps_enabled,
            "cps_uri": self.cps_uri,
            "cps_oid": self.cps_oid or '2.5.29.32.0',
            # RFC 5280 constraints
            "path_length": self.path_length,
            "name_constraints_permitted": self.get_name_constraints_permitted(),
            "name_constraints_excluded": self.get_name_constraints_excluded(),
            "policy_constraints_require": self.policy_constraints_require,
            "policy_constraints_inhibit": self.policy_constraints_inhibit,
            "inhibit_any_policy": self.inhibit_any_policy,
            "sia_enabled": self.sia_enabled,
            "sia_urls": self.get_sia_urls(),
            # Ownership (Pro feature)
            "owner_group_id": self.owner_group_id,
            "owner_group_name": self.owner_group.name if self.owner_group else None,
            # HSM backing (Issue #77.3)
            "uses_hsm": self.uses_hsm,
            "hsm_key_id": self.hsm_key_id,
            "hsm_provider_id": self.hsm_key.provider_id if self.hsm_key else None,
            "hsm_provider_name": (self.hsm_key.provider.name if (self.hsm_key and self.hsm_key.provider) else None),
            "hsm_key_label": self.hsm_key.label if self.hsm_key else None,
            # PEM for display/copy
            "pem": self._decode_pem(self.crt),
        }
        if include_private:
            data["crt"] = self.crt
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
