"""Which certificate is the EST key generator of a CA: it signs serverkeygen key packages
(RFC 7030 §4.4.2). The certificate and its key live in an ordinary Certificate row, listed
and revocable like a delegated OCSP responder; this pointer is derivable and never archived."""
from models import db
from utils.datetime_utils import utc_now


class EstSignerCert(db.Model):
    __tablename__ = 'est_signer_certs'

    id = db.Column(db.Integer, primary_key=True)
    ca_id = db.Column(db.Integer, db.ForeignKey('certificate_authorities.id', ondelete='CASCADE'),
                      nullable=False, unique=True, index=True)
    certificate_id = db.Column(db.Integer, db.ForeignKey('certificates.id', ondelete='CASCADE'),
                               nullable=False)
    # SHA-256 of the CA certificate that issued it: a re-issued CA certificate gets a new delegate
    issuer_fingerprint = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now)
