"""
Certificate Template Model
Pre-configured certificate profiles for common use cases
"""
from datetime import datetime
from models import db


class CertificateTemplate(db.Model):
    """Certificate Template for pre-configured certificate profiles"""
    __tablename__ = "certificate_templates"
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False, index=True)
    description = db.Column(db.Text)
    template_type = db.Column(db.String(50), nullable=False)  # web_server, email, vpn_server, vpn_client, code_signing, client_auth, piv, custom
    
    # Key configuration
    key_type = db.Column(db.String(20), default='RSA-2048')  # RSA-2048, RSA-4096, EC-P256, EC-P384
    validity_days = db.Column(db.Integer, default=397)
    digest = db.Column(db.String(20), default='sha256')
    
    # DN Template (JSON) - Can use variables like {username}, {email}, {hostname}
    # Example: {"CN": "{hostname}", "O": "My Company", "OU": "IT"}
    dn_template = db.Column(db.Text)
    
    # Extensions Template (JSON)
    # Example: {
    #   "key_usage": ["digitalSignature", "keyEncipherment"],
    #   "extended_key_usage": ["serverAuth"],
    #   "basic_constraints": {"ca": false},
    #   "san_types": ["dns", "ip"]  # Which SAN types to show in UI
    # }
    extensions_template = db.Column(db.Text, nullable=False)
    
    # Flags
    is_system = db.Column(db.Boolean, default=False)  # System templates can't be deleted
    is_active = db.Column(db.Boolean, default=True)
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.String(80))
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    updated_by = db.Column(db.String(80))
    
    def to_dict(self):
        """Convert to dictionary"""
        import json
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "template_type": self.template_type,
            "key_type": self.key_type,
            "validity_days": self.validity_days,
            "digest": self.digest,
            "dn_template": json.loads(self.dn_template) if self.dn_template else {},
            "extensions_template": json.loads(self.extensions_template) if self.extensions_template else {},
            "is_system": self.is_system,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "created_by": self.created_by,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "updated_by": self.updated_by,
        }
