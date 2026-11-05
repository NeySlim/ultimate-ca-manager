"""Keys revoked as compromised, which the ACME client never sends to a CA again."""
import base64
import logging

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from sqlalchemy.orm import load_only

from models import Certificate, RevokedSerial
from utils.revocation_reasons import normalize_revocation_reason
from utils.spki_digest import public_key_sha256

logger = logging.getLogger(__name__)

COMPROMISED_CSR = 'The key of this CSR was revoked as compromised: submit a new CSR'
_SPKI = (serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)


class CompromisedKey(Exception):
    """A key revoked as compromised was about to go to the CA again."""


def revoked_as_compromised(row) -> bool:
    return bool(row.revoked and normalize_revocation_reason(row.revoke_reason) == 'keyCompromise')


def _row_public_key_der(row) -> bytes:
    raw = base64.b64decode(row.crt)
    if raw.lstrip().startswith(b'-----BEGIN'):
        cert = x509.load_pem_x509_certificate(raw)
    else:
        cert = x509.load_der_x509_certificate(raw)
    return cert.public_key().public_bytes(*_SPKI)


def key_revoked_as_compromised(public_key) -> bool:
    """Whether any row holding this key was revoked as compromised: a key reused along
    renewals sits on several certificates, and only one of them may carry the revocation."""
    wanted = public_key.public_bytes(*_SPKI)
    # The revocation records first: they outlive a deleted certificate
    records = RevokedSerial.query.filter_by(public_key_sha256=public_key_sha256(public_key)).all()
    if any(normalize_revocation_reason(r.revoke_reason) == 'keyCompromise' for r in records):
        return True
    rows = Certificate.query.options(load_only(Certificate.id, Certificate.crt, Certificate.revoked,
                                               Certificate.revoke_reason))
    for row in rows.filter(Certificate.revoked.is_(True)).all():
        if not row.crt or not revoked_as_compromised(row):
            continue
        try:
            held = _row_public_key_der(row)
        except Exception as exc:  # unreadable here (algorithm, FIPS provider): says nothing of this key
            logger.debug("Key of certificate %s not compared: %s", row.id, exc)
            continue
        if held == wanted:
            return True
    return False


def refuse_compromised_csr(csr) -> None:
    """CompromisedKey when the key of ``csr`` was revoked as compromised."""
    if key_revoked_as_compromised(csr.public_key()):
        raise CompromisedKey(COMPROMISED_CSR)
