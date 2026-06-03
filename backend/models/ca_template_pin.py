"""
CA-Template Pin Model
Allows pinning templates to specific CAs for better organization.
"""
from datetime import datetime
from models import db
from utils.datetime_utils import utc_now, utc_isoformat


class CATemplatePin(db.Model):
    """Pin a template to a specific CA"""
    __tablename__ = "ca_template_pins"
    
    id = db.Column(db.Integer, primary_key=True)
    ca_id = db.Column(db.Integer, db.ForeignKey('certificate_authorities.id', ondelete='CASCADE'), nullable=False, index=True)
    template_id = db.Column(db.Integer, db.ForeignKey('certificate_templates.id', ondelete='CASCADE'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    created_by = db.Column(db.String(80))
    
    # Relationships
    ca = db.relationship('CA', backref=db.backref('template_pins', cascade='all, delete-orphan'))
    template = db.relationship('CertificateTemplate', backref=db.backref('ca_pins', cascade='all, delete-orphan'))
    
    # Unique constraint on (ca_id, template_id) is enforced at DB level
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": self.id,
            "ca_id": self.ca_id,
            "template_id": self.template_id,
            "created_at": utc_isoformat(self.created_at),
            "created_by": self.created_by,
        }
