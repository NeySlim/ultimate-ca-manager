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
    # Opt-in named protocol URLs (#207): immutable slug used instead of refid
    # in CDP/OCSP/AIA paths. NULL = refid-based URLs (default).
    url_slug = db.Column(db.String(64), unique=True)
    descr = db.Column(db.String(255), nullable=False)
    # Base64 encoded. '' (empty) = pending external-CSR CA awaiting its
    # certificate (#298) — sentinel keeps the NOT NULL constraint so SQLite
    # never needs a table rebuild.
    crt = db.Column(db.Text, nullable=False)
    prv = db.Column(db.Text)  # Base64 encoded private key
    # Base64 encoded PEM CSR (same encoding as Certificate.csr). Non-NULL =
    # a CSR is outstanding: awaiting first certificate (pending CA) or a
    # renewal via the external signer (#298).
    csr = db.Column(db.Text)
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
    # Full CRL schedule (#207): nextUpdate window, publish cadence (NULL =
    # legacy regen-near-expiry behaviour), signature digest (NULL = sha256)
    crl_validity_days = db.Column(db.Integer)
    crl_publish_interval_hours = db.Column(db.Integer)
    crl_digest = db.Column(db.String(20))
    
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
    
    # Offline mode — root CA can be taken offline
    offline = db.Column(db.Boolean, default=False)
    offline_reason = db.Column(db.String(1024), nullable=True)
    offline_mode = db.Column(db.String(32), nullable=True)

    # Revocation of an intermediate CA by its parent (#343): the parent's CRL
    # and OCSP carry the serial through revoked_serials; these columns hold
    # the state shown on the CA and the reason it was revoked for
    revoked = db.Column(db.Boolean, default=False)
    revoked_at = db.Column(db.DateTime, nullable=True)
    revoke_reason = db.Column(db.String(100), nullable=True)
    invalidity_at = db.Column(db.DateTime, nullable=True)
    
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

    @property
    def is_pending(self) -> bool:
        """External-CSR CA still awaiting its signed certificate (#298)"""
        return not self.crt

    @property
    def url_ref(self) -> str:
        """Path segment for protocol URLs: opt-in slug, else refid (#207)"""
        return self.url_slug or self.refid or ''
    
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

    def issuing_ca(self):
        """The CA held in UCM whose key signed this certificate, or None.

        Candidates come from caref, then from the AKI (a CA whose SKI
        matches), then from the issuer DN (an imported intermediate has no
        caref until chain repair); a candidate counts only if this
        certificate's signature verifies with its key. Two CAs can carry
        the same DN, and a decoy root imported under the parent's name must
        not stand in for it (#343 review)."""
        if self.is_root or not self.crt:
            return None
        import base64
        from cryptography import x509
        from utils.cert_issuer import authority_key_identifier_hex, certificate_signed_by
        try:
            cert = x509.load_pem_x509_certificate(base64.b64decode(self.crt))
        except Exception:
            return None

        candidates, seen = [], set()

        def _add(rows):
            for row in rows:
                if row is not None and row.id != self.id and row.id not in seen and row.crt:
                    seen.add(row.id)
                    candidates.append(row)

        if self.caref:
            _add([CA.query.filter_by(refid=self.caref).first()])
        aki = authority_key_identifier_hex(cert)
        if aki:
            _add(CA.query.filter(CA.ski == aki).all())
        if self.issuer:
            _add(CA.query.filter(CA.subject == self.issuer).all())

        for candidate in candidates:
            try:
                issuer_cert = x509.load_pem_x509_certificate(base64.b64decode(candidate.crt))
            except Exception:
                continue
            if certificate_signed_by(cert, issuer_cert):
                return candidate
        return None

    def persisted_revocation(self):
        """The parent's revoked_serials row for this CA's certificate, or None.

        The record outlives the CA row (#343): a CA deleted after its
        revocation and imported again must not come back as good, so the
        record, not the row's flag, is what the signing guard and the OCSP
        responder trust."""
        if not self.crt:
            return None
        parent = self.issuing_ca()
        if parent is None:
            return None
        from models.revoked_serial import RevokedSerial
        from utils.serial_format import serial_to_int, serial_variants
        serial = serial_to_int(self.serial_number) if self.serial_number else None
        if serial is None:
            try:
                import base64
                from cryptography import x509
                serial = x509.load_pem_x509_certificate(base64.b64decode(self.crt)).serial_number
            except Exception:
                return None
        return RevokedSerial.query.filter(
            RevokedSerial.caref == parent.refid,
            RevokedSerial.serial_number.in_(serial_variants(serial)),
        ).first()

    @property
    def is_revoked(self) -> bool:
        """Revoked flag, or a revocation the parent still holds for this serial."""
        return bool(self.revoked) or self.persisted_revocation() is not None

    @property
    def revoked_in_chain(self) -> bool:
        """Whether this CA or one of its ancestors held in UCM is revoked.

        A revoked ancestor breaks path validation for everything below it,
        so a CA under one must not issue either (#343)."""
        ca, depth = self, 0
        while ca is not None and depth < 16:
            if ca.is_revoked:
                return True
            ca = ca.issuing_ca()
            depth += 1
        return False
    
    @property
    def key_type(self) -> str:
        """Parse key type from certificate (or from the CSR while pending)"""
        if not self.crt and not self.csr:
            return "N/A"
        try:
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend
            from cryptography.hazmat.primitives.asymmetric import rsa, ec, dsa
            import base64

            if self.crt:
                cert_pem = base64.b64decode(self.crt).decode('utf-8')
                cert = x509.load_pem_x509_certificate(cert_pem.encode(), default_backend())
                public_key = cert.public_key()
            else:
                csr_pem = base64.b64decode(self.csr).decode('utf-8')
                public_key = x509.load_pem_x509_csr(
                    csr_pem.encode(), default_backend()
                ).public_key()

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
        
        # Determine status: pending (awaiting external certificate) wins,
        # otherwise derived from expiry
        status = "Active"
        if self.is_pending:
            status = "Pending"
        elif self.revoked:
            status = "Revoked"
        elif self.valid_to:
            if self.valid_to < utc_now():
                status = "Expired"
        
        # Offline state (separate from expiry-based status)
        offline_label = "Offline" if self.offline else None
        
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
            "url_slug": self.url_slug,
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
            "status": status,  # "Pending", "Revoked", "Active" or "Expired"
            # Revocation by the parent CA (#343)
            "revoked": bool(self.revoked),
            "revoked_at": utc_isoformat(self.revoked_at),
            "revoke_reason": self.revoke_reason,
            "invalidity_at": utc_isoformat(self.invalidity_at),
            # External-CSR lifecycle (#298)
            "pending": self.is_pending,
            "has_csr": bool(self.csr),
            "certs": self.certificates.count() if self.certificates else 0,  # Count of issued certificates
            "key_type": self.key_type,
            "hash_algorithm": self.hash_algorithm,
            # CRL/CDP configuration
            "cdp_enabled": self.cdp_enabled,
            "cdp_url": self.get_primary_cdp_url(),
            "cdp_urls": self.get_cdp_urls(),
            "delta_crl_enabled": self.delta_crl_enabled,
            "delta_crl_interval": self.delta_crl_interval or 4,
            "crl_validity_days": self.crl_validity_days or 7,
            "crl_publish_interval_hours": self.crl_publish_interval_hours,
            "crl_digest": self.crl_digest or 'sha256',
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
            # Offline state
            "offline": self.offline,
            "offline_reason": self.offline_reason,
            "offline_mode": self.offline_mode,
            "offline_label": offline_label,
            # PEM for display/copy
            "pem": self._decode_pem(self.crt),
            # Outstanding CSR (external-CSR mode, #298)
            "csr_pem": self._decode_pem(self.csr),
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
