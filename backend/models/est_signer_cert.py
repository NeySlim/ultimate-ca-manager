"""The EST key generator certificate of a CA: it signs serverkeygen key packages (RFC 7030 §4.4.2).

One row per CA, issued by that CA and replaced in place; derivable, so never archived.
"""
from models import db
from utils.datetime_utils import utc_now


class EstSignerCert(db.Model):
    __tablename__ = 'est_signer_certs'

    id = db.Column(db.Integer, primary_key=True)
    ca_id = db.Column(db.Integer, db.ForeignKey('certificate_authorities.id', ondelete='CASCADE'),
                      nullable=False, unique=True, index=True)
    crt = db.Column(db.Text, nullable=False)  # PEM
    prv = db.Column(db.Text, nullable=False)  # store_pem_bytes, under the master key
    # SHA-256 of the CA certificate that issued crt: a re-issued CA certificate gets a new delegate
    issuer_fingerprint = db.Column(db.String(64), nullable=False)
    not_after = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now)
