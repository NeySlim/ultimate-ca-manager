"""
AuditLog Model - Audit log for all operations
"""
from models import db
from utils.datetime_utils import utc_now, utc_isoformat


class AuditLog(db.Model):
    """Audit log for all operations"""
    __tablename__ = "audit_logs"
    
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=utc_now, index=True)
    username = db.Column(db.String(80), index=True)
    action = db.Column(db.String(100), nullable=False)  # create_ca, revoke_cert, etc.
    resource_type = db.Column(db.String(50))  # ca, certificate, user, etc.
    resource_id = db.Column(db.String(100))
    resource_name = db.Column(db.String(255))  # Human-readable name (cert CN, user name, CA name)
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(255))
    success = db.Column(db.Boolean, default=True)
    # Tamper-evident hash chain: SHA-256(prev_hash + this_entry)
    prev_hash = db.Column(db.String(64))  # Hash of previous log entry
    entry_hash = db.Column(db.String(64))  # Hash of this entry (includes prev_hash)
    
    def compute_hash(self, prev_hash: str = None) -> str:
        """Compute SHA-256 hash of this entry for tamper detection"""
        import hashlib
        data = f"{self.id}|{self.timestamp}|{self.username}|{self.action}|{self.resource_type}|{self.resource_id}|{self.details}|{self.success}|{prev_hash or ''}"
        return hashlib.sha256(data.encode()).hexdigest()
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": self.id,
            "timestamp": (utc_isoformat(self.timestamp)) if self.timestamp else None,
            "username": self.username,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "resource_name": self.resource_name,
            "details": self.details,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "success": self.success,
            "entry_hash": self.entry_hash,
            "prev_hash": self.prev_hash,
        }
