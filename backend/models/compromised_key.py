"""Keys revoked as compromised, whatever CA issued their certificate.

Independent of certificates and CAs (no foreign key): deleting either never forgets a key.
"""
import logging

from sqlalchemy.exc import IntegrityError

from models import db
from utils.datetime_utils import utc_now, utc_isoformat

logger = logging.getLogger(__name__)


class CompromisedKeyRecord(db.Model):
    __tablename__ = 'compromised_keys'

    id = db.Column(db.Integer, primary_key=True)
    # SHA-256 of the SubjectPublicKeyInfo (utils/spki_digest.py)
    public_key_sha256 = db.Column(db.String(64), nullable=False, unique=True, index=True)
    revoked_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    # Issuer of the certificate: local (a CA held here), acme_client, msca or external
    source = db.Column(db.String(20), nullable=False)
    cert_refid = db.Column(db.String(36))
    subject = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utc_now)

    def to_dict(self):
        return {
            'id': self.id,
            'public_key_sha256': self.public_key_sha256,
            'revoked_at': utc_isoformat(self.revoked_at),
            'source': self.source,
            'cert_refid': self.cert_refid,
            'subject': self.subject,
            'created_at': utc_isoformat(self.created_at),
        }


def remember_compromised_key(digest, source, *, revoked_at=None, cert_refid=None, subject=None) -> bool:
    """Record ``digest`` once, in a savepoint of the caller's transaction; never raises."""
    if not digest:
        return False
    try:
        with db.session.begin_nested():
            if CompromisedKeyRecord.query.filter_by(public_key_sha256=digest).first() is None:
                db.session.add(CompromisedKeyRecord(public_key_sha256=digest, source=source,
                                                    revoked_at=revoked_at or utc_now(),
                                                    cert_refid=cert_refid, subject=subject))
        return True
    except IntegrityError:  # recorded meanwhile by another worker
        return True
    except Exception as exc:
        logger.error("Compromised key %s not recorded: %s", digest, exc)
        return False


def key_source(certificate) -> str:
    if certificate.caref:
        return 'local'
    return certificate.source if certificate.source in ('acme_client', 'msca') else 'external'


def remember_if_compromised(certificate, digest=None) -> bool:
    """Keep the key of a certificate row revoked as compromised; True once recorded, never raises."""
    from utils.revocation_reasons import normalize_revocation_reason
    from utils.spki_digest import certificate_key_sha256
    if not certificate.revoked or normalize_revocation_reason(certificate.revoke_reason) != 'keyCompromise':
        return False
    return remember_compromised_key(digest or certificate_key_sha256(certificate.crt), key_source(certificate),
                                    revoked_at=certificate.revoked_at, cert_refid=certificate.refid,
                                    subject=certificate.subject)
