"""
Trusted Certificate Model
Store of trusted root/intermediate certificates
"""
from datetime import datetime
from models import db
from utils.datetime_utils import utc_now, utc_isoformat


class TrustedCertificate(db.Model):
    """Trusted certificate for trust store"""
    __tablename__ = "trusted_certificates"
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, index=True)
    description = db.Column(db.Text)
    
    # Certificate data
    certificate_pem = db.Column(db.Text, nullable=False)
    fingerprint_sha256 = db.Column(db.String(64), unique=True, nullable=False, index=True)
    fingerprint_sha1 = db.Column(db.String(40), index=True)
    
    # Certificate details (extracted)
    subject = db.Column(db.String(500))
    issuer = db.Column(db.String(500))
    serial_number = db.Column(db.String(100))
    not_before = db.Column(db.DateTime)
    not_after = db.Column(db.DateTime)
    
    # Purpose
    purpose = db.Column(db.String(100))  # root_ca, intermediate_ca, code_signing, tls_server, custom
    
    # Metadata
    added_by = db.Column(db.String(80))
    added_at = db.Column(db.DateTime, default=utc_now)
    notes = db.Column(db.Text)
    
    @property
    def key_facts(self) -> dict:
        """Key facts and signature algorithm of the stored certificate, as Certificate and CA send them."""
        from cryptography import x509
        from utils.key_facts import UNREADABLE, key_facts
        from utils.signature_label import signature_display_name
        try:
            cert = x509.load_pem_x509_certificate(self.certificate_pem.encode())
            return {**key_facts(cert), 'signature_algorithm': signature_display_name(cert)}
        except Exception:
            return {**UNREADABLE, 'signature_algorithm': 'N/A'}

    def to_dict(self):
        """Convert to dictionary"""
        facts = self.key_facts
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "certificate_pem": self.certificate_pem,
            "fingerprint_sha256": self.fingerprint_sha256,
            "fingerprint_sha1": self.fingerprint_sha1,
            "subject": self.subject,
            "issuer": self.issuer,
            "serial_number": self.serial_number,
            "not_before": utc_isoformat(self.not_before),
            "not_after": utc_isoformat(self.not_after),
            "purpose": self.purpose,
            "added_by": self.added_by,
            "added_at": utc_isoformat(self.added_at),
            "notes": self.notes,
            "key_type": facts['key_type'],
            "key_algorithm": facts['key_algorithm'],
            "key_size": facts['key_size'],
            "security_level": facts['security_level'],
            "post_quantum": facts['post_quantum'],
            "signature_algorithm": facts['signature_algorithm'],
        }
