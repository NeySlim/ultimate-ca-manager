"""
AuditLog Model - Audit log for all operations
"""
import hashlib
import hmac
import json

from models import db
from utils.datetime_utils import utc_now, utc_isoformat, to_naive_utc


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
    # Hash chain: each entry seals its content and the hash of the entry before it
    prev_hash = db.Column(db.String(64))
    entry_hash = db.Column(db.String(64))
    # NULL or 1: SHA-256, recomputable by anyone. 2: HMAC-SHA256 under a key
    # derived from the master key, named by hash_key_id.
    hash_version = db.Column(db.Integer)
    hash_key_id = db.Column(db.String(16))
    # Set on the first entry under a key and on a purge record: the first id
    # the ledger holds from then on, so a prefix removed otherwise is seen.
    chain_start = db.Column(db.Integer)

    def compute_hash(self, prev_hash: str = None, key: bytes = None) -> str:
        """Seal of this entry: SHA-256 without a key, HMAC-SHA256 with one."""
        if key is None:
            data = f"{self.id}|{self.timestamp}|{self.username}|{self.action}|{self.resource_type}|{self.resource_id}|{self.details}|{self.success}|{prev_hash or ''}"
            return hashlib.sha256(data.encode()).hexdigest()
        # JSON, not a joined string: a separator inside a field must not let
        # text move from one field to the next under the same seal.
        timestamp = to_naive_utc(self.timestamp)
        message = json.dumps([
            'ucm-audit/2', self.hash_key_id, self.id, self.chain_start,
            timestamp.isoformat(timespec='microseconds') if timestamp else None,
            self.username, self.action, self.resource_type, self.resource_id,
            self.resource_name, self.details, self.ip_address, self.user_agent,
            None if self.success is None else bool(self.success), prev_hash or '',
        ], ensure_ascii=False, separators=(',', ':'))
        # One-shot HMAC through hashlib's OpenSSL backend (FIPS provider in FIPS mode)
        return hmac.digest(key, message.encode('utf-8'), 'sha256').hex()

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
