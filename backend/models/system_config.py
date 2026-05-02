"""
SystemConfig Model - System configuration stored in database
"""
from models import db
from utils.datetime_utils import utc_now, utc_isoformat


class SystemConfig(db.Model):
    """System configuration stored in database"""
    __tablename__ = "system_config"
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    value = db.Column(db.Text)
    encrypted = db.Column(db.Boolean, default=False)
    description = db.Column(db.String(255))
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    updated_by = db.Column(db.String(80))
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": self.id,
            "key": self.key,
            "value": self.value if not self.encrypted else "***",
            "encrypted": self.encrypted,
            "description": self.description,
            "updated_at": utc_isoformat(self.updated_at),
            "updated_by": self.updated_by,
        }
