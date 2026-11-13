"""
Certificate Model - Certificates and CSRs
"""
import json
from sqlalchemy import event, text
from sqlalchemy.orm import validates

from models import db
from utils.datetime_utils import utc_now, utc_isoformat


class Certificate(db.Model):
    """Certificate model"""
    __tablename__ = "certificates"
    # RFC 5280 §4.1.2.2: one serial per issuing CA (migration 142 on existing installations)
    __table_args__ = (
        db.Index('uix_certificates_ca_serial', 'caref', 'serial_number', unique=True,
                 sqlite_where=text("caref IS NOT NULL AND serial_number IS NOT NULL AND serial_number <> ''"),
                 postgresql_where=text("caref IS NOT NULL AND serial_number IS NOT NULL AND serial_number <> ''")),
        # Finds the certificates of a CA carrying a subject (migration 157)
        db.Index('ix_certificates_caref_subject_key', 'caref', 'subject_key'),
    )
    
    id = db.Column(db.Integer, primary_key=True)
    refid = db.Column(db.String(36), unique=True, nullable=False, index=True)
    descr = db.Column(db.String(255), nullable=False)
    caref = db.Column(db.String(36), db.ForeignKey("certificate_authorities.refid"), index=True)
    crt = db.Column(db.Text)  # Nullable - CSR doesn't have cert yet
    csr = db.Column(db.Text)  # Base64 encoded CSR
    prv = db.Column(db.Text)  # Base64 encoded private key
    
    # Certificate details
    cert_type = db.Column(db.String(50))  # client_cert, server_cert, combined_cert, ca_cert
    subject = db.Column(db.Text)
    subject_cn = db.Column(db.String(255))  # Extracted CN for sorting
    # utils.dn_match.name_key of the certificate's subject, written with crt
    subject_key = db.Column(db.String(64))
    issuer = db.Column(db.Text)
    serial_number = db.Column(db.String(100), index=True)
    aki = db.Column(db.String(200))  # Authority Key Identifier (hex, colon-separated)
    ski = db.Column(db.String(200))  # Subject Key Identifier (hex, colon-separated)
    valid_from = db.Column(db.DateTime)
    valid_to = db.Column(db.DateTime, index=True)
    key_algo = db.Column(db.String(50))  # RSA 2048, EC P-256, etc. (for sorting)
    # Written with key_algo whenever crt is set: the dashboard counts them without parsing PEM
    key_bits = db.Column(db.Integer)  # RSA/DSA modulus or EC field size; NULL when the key has none
    sig_hash = db.Column(db.String(20))  # 'sha256', 'sha1'; NULL when the scheme has no separate hash
    
    # Subject Alternative Names (SAN)
    san_dns = db.Column(db.Text)  # JSON array of DNS names
    san_ip = db.Column(db.Text)   # JSON array of IP addresses
    san_email = db.Column(db.Text)  # JSON array of email addresses
    san_uri = db.Column(db.Text)  # JSON array of URIs
    san_upn = db.Column(db.Text)  # JSON array of UPN strings (Microsoft OID 1.3.6.1.4.1.311.20.2.3)
    
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
    # RFC 5280 §5.3.2 — optional; may precede revoked_at (key compromise time)
    invalidity_at = db.Column(db.DateTime)
    archived = db.Column(db.Boolean, default=False)  # For renewed certificates
    
    # Metadata
    imported_from = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=utc_now, index=True)
    created_by = db.Column(db.String(80))
    
    # Last in-place renewal (naive UTC) and how many there were
    renewed_at = db.Column(db.DateTime, nullable=True)
    renewed_times = db.Column(db.Integer, nullable=False, default=0, server_default='0')

    # Source tracking (issuance origin). Known values:
    # 'manual', 'import', 'acme', 'letsencrypt', 'scep', 'est', 'msca'.
    # NULL is treated as 'manual'. Kept in sync with the certificate list
    # source filter (api/v2/certificates/cert_list.py) and the UI badges.
    source = db.Column(db.String(20), default='manual')
    
    # Template reference (optional - null if created without template)
    template_id = db.Column(db.Integer, db.ForeignKey("certificate_templates.id"), nullable=True)
    # Windows enrollment profile that issued it; no foreign key, like SCEPRequest.profile_id
    windows_profile_id = db.Column(db.Integer, nullable=True, index=True)

    # Frozen at issuance (issue #258): JSON array of the fields where the
    # effective value diverged from the linked template's declared default
    # ('key_type', 'validity_days', 'digest'). NULL/empty = in sync with the
    # template (or no template used). Not recomputed later — editing the
    # template afterwards does not change this record.
    template_overrides = db.Column(db.Text, nullable=True)
    
    # Ownership (Pro feature - group-based access control)
    # No access control reads it; kept for older databases and backups
    owner_group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=True)
    owner_group = db.relationship('Group', backref='owned_certificates')

    # RFC 9763: on B, the A its id-pe-relatedCert names; on A, B once the pair is mutual
    related_certificate_id = db.Column(db.Integer, nullable=True, index=True)
    hybrid_role = db.Column(db.String(16), nullable=True)  # 'classical' or 'pq'
    
    # Relationships
    ca = db.relationship("CA", back_populates="certificates")
    template = db.relationship("CertificateTemplate", foreign_keys=[template_id])

    DUPLICATE_SERIAL = "already stored under this CA"

    @validates('serial_number')
    def _canonical_serial_number(self, key, value):
        # One stored spelling per serial (utils/serial_format.py), or the unique index misses twins
        from utils.serial_format import canonical_stored_serial
        return canonical_stored_serial(value, self.crt)

    @classmethod
    def stored_under(cls, caref, serial_number):
        """The row uix_certificates_ca_serial would collide with, or None."""
        from utils.serial_format import canonical_serial
        if not caref or not serial_number:
            return None
        return cls.query.filter_by(caref=caref, serial_number=canonical_serial(serial_number)).first()
    
    @property
    def template_overrides_list(self) -> list:
        """JSON-decoded template_overrides as a list of field names ([] when unset)."""
        if not self.template_overrides:
            return []
        try:
            import json
            parsed = json.loads(self.template_overrides)
            return parsed if isinstance(parsed, list) else []
        except (TypeError, ValueError):
            return []

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
    def san_upn_list(self) -> list:
        """Get list of UPN SANs (Microsoft User Principal Name)"""
        import json
        if not self.san_upn:
            return []
        try:
            return json.loads(self.san_upn)
        except Exception:
            return []
            
    def _crt_or_csr(self):
        """The certificate, else the request, parsed; None when the row has neither."""
        import base64
        from cryptography import x509
        if self.crt:
            return x509.load_pem_x509_certificate(base64.b64decode(self.crt))
        if self.csr:
            return x509.load_pem_x509_csr(base64.b64decode(self.csr))
        return None

    @property
    def key_facts(self) -> dict:
        """key_type, key_algorithm, key_size, security_level, post_quantum, verifiable."""
        from utils.key_facts import UNREADABLE, key_facts
        try:
            obj = self._crt_or_csr()
            return key_facts(obj) if obj is not None else dict(UNREADABLE)
        except Exception:
            return dict(UNREADABLE)

    @property
    def key_type(self) -> str:
        """Key type of the certificate or CSR: 'RSA 2048', 'ML-DSA-65', 'N/A'."""
        return self.key_facts['key_type']

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
        """Key algorithm: 'RSA', 'EC', 'ML-DSA-65' (a post-quantum label is whole)."""
        return self.key_facts['key_algorithm']

    @property
    def key_size(self):
        """Key size in bits, 0 when unknown, None for a post-quantum key."""
        return self.key_facts['key_size']

    @property
    def signature_algorithm(self) -> str:
        """Signature algorithm of the certificate, else of the request."""
        try:
            from utils.signature_label import signature_display_name
            obj = self._crt_or_csr()
            return signature_display_name(obj) if obj is not None else "N/A"
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
    def days_remaining(self):
        """Days until expiration; negative once past, None with no expiry.

        See utils/days_remaining for why this is signed and why "no expiry
        date" is None rather than -1.
        """
        from utils.days_remaining import days_remaining as _days_remaining
        return _days_remaining(self.valid_to)
    
    @property
    def san_entries(self) -> list:
        """Every SAN as a "TYPE:value" string, in DNS, IP, Email, URI, UPN order."""
        sans = []
        for prefix, raw in (('DNS', self.san_dns), ('IP', self.san_ip), ('Email', self.san_email),
                            ('URI', self.san_uri), ('UPN', self.san_upn)):
            if not raw:
                continue
            try:
                values = json.loads(raw) if raw.startswith('[') else [raw]
                sans.extend([f"{prefix}:{v}" for v in values])
            except Exception:
                sans.append(f"{prefix}:{raw}")
        return sans

    @property
    def san_combined(self) -> str:
        """Combined SAN string for display"""
        return ', '.join(self.san_entries)

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
    
    def _windows_profile_name(self, names):
        if self.windows_profile_id is None:
            return None
        if names is not None:
            return names.get(self.windows_profile_id)
        from models.windows_profile import WindowsEnrollmentProfile
        profile = db.session.get(WindowsEnrollmentProfile, self.windows_profile_id)
        return profile.name if profile else None

    def to_dict(self, include_private=False, windows_profile_names=None):
        """Convert to dictionary; a list passes ``windows_profile_names`` (id to name) read once"""
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
        
        san_entries = self.san_entries
        key_facts = self.key_facts
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
            "invalidity_at": utc_isoformat(self.invalidity_at),
            "archived": self.archived or False,
            "imported_from": self.imported_from,
            "created_at": utc_isoformat(self.created_at),
            "renewed_at": utc_isoformat(self.renewed_at),
            "renewed_times": self.renewed_times or 0,
            "created_by": self.created_by,
            "source": self.source or 'manual',
            "has_private_key": self.has_private_key,
            "private_key_location": self.private_key_location,
            # Subject Alternative Names
            "san_dns": self.san_dns,
            "san_ip": self.san_ip,
            "san_email": self.san_email,
            "san_uri": self.san_uri,
            "san_upn": self.san_upn,
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
            "key_type": key_facts['key_type'],
            "key_algo": self.key_algo,  # Stored value for sorting
            "key_algorithm": key_facts['key_algorithm'],
            "key_size": key_facts['key_size'],
            "security_level": key_facts['security_level'],
            "post_quantum": key_facts['post_quantum'],
            "verifiable": key_facts['verifiable'],
            "signature_algorithm": self.signature_algorithm,
            # Thumbprints
            "thumbprint_sha1": self.thumbprint_sha1,
            "thumbprint_sha256": self.thumbprint_sha256,
            # Computed
            "days_remaining": self.days_remaining,
            "san_combined": ', '.join(san_entries),
            "san_count": len(san_entries),
            # Ownership (Pro feature)
            "owner_group_name": self.owner_group.name if self.owner_group else None,
            # Template linkage + divergence record (#258)
            "template_id": self.template_id,
            "template_name": self.template.name if self.template_id and self.template else None,
            "template_overrides": self.template_overrides_list,
            # Windows enrollment profile that issued it; the name is null once the profile is gone
            "windows_profile_id": self.windows_profile_id,
            "windows_profile_name": self._windows_profile_name(windows_profile_names),
            # Related certificate pair (RFC 9763)
            "related_certificate_id": self.related_certificate_id,
            "hybrid_role": self.hybrid_role,
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


def key_algo_for_certificate(cert):
    """The ``key_algo`` spelling of a parsed certificate, whatever pyca can load of its key."""
    from utils.key_algorithms import key_algo_for_public_key
    from utils.foreign_algorithms import describe_public_key
    foreign = describe_public_key(cert)
    if foreign:
        return foreign['label'][:50]
    return key_algo_for_public_key(cert.public_key())


def key_bits_for_certificate(cert):
    """Modulus or field size of the certificate's key; None when the key has no size."""
    from utils.foreign_algorithms import describe_public_key
    foreign = describe_public_key(cert)
    if foreign:
        return foreign['key_size'] or None
    return getattr(cert.public_key(), 'key_size', None)


def sig_hash_for_certificate(cert):
    """Lowercase name of the hash the issuer signed with ('sha256'), None when the scheme has none."""
    try:
        algorithm = cert.signature_hash_algorithm
    except Exception:
        return None
    return algorithm.name.lower()[:20] if algorithm is not None else None


@event.listens_for(Certificate.crt, 'set')
def _key_fields_follow_crt(target, value, oldvalue, initiator):
    # Every issuance path sets crt; key_algo, key_bits, sig_hash (sorting, compliance),
    # subject_key (subject uniqueness) and the AKI/SKI columns (ACME ARI, chain lookups) follow it
    if not value:
        return
    import base64
    from cryptography import x509
    from utils.cert_issuer import authority_key_identifier_hex
    try:
        cert = x509.load_pem_x509_certificate(base64.b64decode(value))
    except Exception:
        return
    from utils.serial_format import serial_readings
    if target.serial_number and cert.serial_number in serial_readings(target.serial_number):
        target.serial_number = str(cert.serial_number)  # set before crt: the certificate settles it
    try:
        target.key_algo = key_algo_for_certificate(cert) or target.key_algo
        target.key_bits = key_bits_for_certificate(cert)
    except Exception:
        pass
    target.sig_hash = sig_hash_for_certificate(cert)
    try:
        # Inside the guard: a certificate is stored even when its subject cannot be keyed
        from utils.dn_match import name_key
        target.subject_key = name_key(cert.subject)
    except Exception:
        target.subject_key = None
    try:
        target.aki = authority_key_identifier_hex(cert)
        target.ski = cert.extensions.get_extension_for_class(
            x509.SubjectKeyIdentifier).value.key_identifier.hex(':').upper()
    except x509.ExtensionNotFound:
        target.ski = None
    except Exception:
        pass  # extensions pyca cannot parse: the backfill leaves them unset too

