"""A relatedCertRequest (RFC 9763) already honoured, bound to the first key B it was presented with."""
from models import db
from utils.datetime_utils import utc_now


class RelatedCertRequestUse(db.Model):
    __tablename__ = 'related_cert_requests'

    id = db.Column(db.Integer, primary_key=True)
    # SHA-256 of what the requester signed and of its signature (related_pair._request_digest)
    request_sha256 = db.Column(db.String(64), nullable=False, unique=True)
    spki_sha256 = db.Column(db.String(64), nullable=False)
    request_time = db.Column(db.DateTime, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=utc_now)
