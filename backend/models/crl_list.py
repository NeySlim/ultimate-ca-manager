"""
CRL Model - Legacy Certificate Revocation List list
"""
from models import db
from utils.datetime_utils import utc_now, utc_isoformat


class CRL(db.Model):
    """Certificate Revocation List model"""
    __tablename__ = "crls"
    
    id = db.Column(db.Integer, primary_key=True)
    caref = db.Column(db.String(36), nullable=False, index=True)
    descr = db.Column(db.String(255), nullable=False)
    text = db.Column(db.Text, nullable=False)  # Base64 encoded CRL
    serial = db.Column(db.Integer, default=0)
    lifetime = db.Column(db.Integer, default=9999)
    
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    
    def to_dict(self, include_crl=False):
        """Convert to dictionary"""
        data = {
            "id": self.id,
            "caref": self.caref,
            "descr": self.descr,
            "serial": self.serial,
            "lifetime": self.lifetime,
            "created_at": utc_isoformat(self.created_at),
            "updated_at": utc_isoformat(self.updated_at),
        }
        if include_crl:
            data["text"] = self.text
        return data
