"""
SCEPRequest Model - SCEP enrollment request tracking
"""
from models import db
from utils.datetime_utils import utc_now, utc_isoformat


class SCEPRequest(db.Model):
    """SCEP enrollment request tracking"""
    __tablename__ = "scep_requests"
    
    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    csr = db.Column(db.Text, nullable=False)  # Base64 encoded
    status = db.Column(db.String(20), default="pending")  # pending, approved, rejected
    approved_by = db.Column(db.String(80))
    approved_at = db.Column(db.DateTime)
    rejection_reason = db.Column(db.String(255))
    
    # Generated certificate
    cert_refid = db.Column(db.String(36))
    
    # Request details
    subject = db.Column(db.Text)
    client_ip = db.Column(db.String(45))
    
    created_at = db.Column(db.DateTime, default=utc_now)
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": self.id,
            "transaction_id": self.transaction_id,
            "status": self.status,
            "subject": self.subject,
            "client_ip": self.client_ip,
            "approved_by": self.approved_by,
            "approved_at": utc_isoformat(self.approved_at),
            "rejection_reason": self.rejection_reason,
            "cert_refid": self.cert_refid,
            "created_at": utc_isoformat(self.created_at),
        }
