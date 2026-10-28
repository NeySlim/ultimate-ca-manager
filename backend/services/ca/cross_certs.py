"""Cross-certificates of a CA's key (#400): attach, serve, revoke, detach.

A cross-certificate carries the CA's subject and key under another issuer. It
sits beside the CA's own certificate, never in place of it. At most one per CA
is served; an expired or revoked one is kept and exportable but never served.
"""
import base64
import hashlib
import logging
from typing import List, Optional, Tuple

from cryptography import x509
from cryptography.hazmat.primitives import serialization

from models import CA, db
from models.ca_cross_certificate import CACrossCertificate
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


class CrossCertError(Exception):
    """A refusal with the HTTP status and a stable code the UI can act on."""

    def __init__(self, message, status=400, code='invalid'):
        super().__init__(message)
        self.message, self.status, self.code = message, status, code


def parse_certificate(data) -> x509.Certificate:
    """A certificate from PEM, base64 PEM or DER bytes/text."""
    if data is not None and not isinstance(data, (str, bytes, bytearray)):
        raise CrossCertError('Certificate must be text or bytes')
    raw = data.encode() if isinstance(data, str) else bytes(data or b'')
    raw = raw.strip()
    if not raw:
        raise CrossCertError('Certificate is required')
    if raw.startswith(b'-----BEGIN'):
        loaders = [x509.load_pem_x509_certificate]
    else:
        try:
            decoded = base64.b64decode(raw, validate=True)
        except Exception:
            decoded = None
        if decoded and decoded.lstrip().startswith(b'-----BEGIN'):
            raw, loaders = decoded, [x509.load_pem_x509_certificate]
        else:
            loaders = [x509.load_der_x509_certificate]
    for load in loaders:
        try:
            return load(raw)
        except Exception:
            continue
    raise CrossCertError('Certificate could not be parsed')


def _spki(cert):
    return cert.public_key().public_bytes(serialization.Encoding.DER,
                                          serialization.PublicFormat.SubjectPublicKeyInfo)


def _naive(moment):
    return moment.replace(tzinfo=None)


def _load_record(record) -> Optional[x509.Certificate]:
    try:
        return x509.load_pem_x509_certificate(base64.b64decode(record.crt))
    except Exception:
        return None


def _issuer_candidates(cert, exclude_id):
    from utils.cert_issuer import authority_key_identifier_hex, cas_by_ski
    found = {}
    for row in CA.query.filter(CA.subject == cert.issuer.rfc4514_string()).all():
        found[row.id] = row
    aki = authority_key_identifier_hex(cert)
    for row in (cas_by_ski(aki) if aki else []):
        found[row.id] = row
    return [row for row in found.values() if row.id != exclude_id and row.crt]


def _resolve_issuer(cert, ca) -> Tuple[Optional[CA], bool]:
    """``(issuer, verified)``: the held CA whose key signed *cert*, or (None, False).

    Raises when held CAs carry the issuer's name and none of them signed it."""
    from utils.cert_issuer import UnsupportedIssuerKey, certificate_signed_by
    candidates = _issuer_candidates(cert, ca.id)
    unverifiable = False
    from utils.cert_issuer import self_signed_first
    for candidate in self_signed_first(sorted(candidates, key=lambda c: c.id)):
        issuer_cert = _load_record(candidate)
        if issuer_cert is None:
            continue
        try:
            if certificate_signed_by(cert, issuer_cert):
                return candidate, True
        except UnsupportedIssuerKey:
            unverifiable = True
    if candidates and not unverifiable:
        raise CrossCertError('The signature does not verify with the issuer held here', 400, 'bad_signature')
    return None, False


def _prefer_self_signed(ca: CA) -> CA:
    """*ca*, or the self-signed record of the same subject and key when one is held."""
    from utils.cert_issuer import same_key_refids, self_signed_first
    refids = same_key_refids(ca)
    if len(refids) == 1:
        return ca
    return self_signed_first(CA.query.filter(CA.refid.in_(refids)).order_by(CA.id).all())[0]


def issuer_of(row: CACrossCertificate) -> Optional[CA]:
    """The held CA that signed *row*; a missing or dangling link is resolved by signature and stored."""
    if row.issuer_caref:
        linked = CA.query.filter_by(refid=row.issuer_caref).first()
        if linked is not None:
            return _prefer_self_signed(linked)
    cert = _load_record(row)
    if cert is None or row.ca is None:
        return None
    try:
        issuer, _ = _resolve_issuer(cert, row.ca)
    except CrossCertError:
        return None
    if issuer is not None:
        row.issuer_caref = issuer.refid
        db.session.flush()
    return issuer


def rows_of_issuer(issuer: CA, variants) -> List[CACrossCertificate]:
    """Cross-certificates *issuer* (or a record of its key) signed, among those with one of the serial *variants*."""
    from utils.cert_issuer import same_key_refids
    refids = set(same_key_refids(issuer))
    found, relinked = [], False
    for row in CACrossCertificate.query.filter(CACrossCertificate.serial_number.in_(list(variants))).all():
        if row.issuer_caref in refids:
            found.append(row)
        elif row.issuer == issuer.subject:
            before = row.issuer_caref
            linked = issuer_of(row)
            relinked = relinked or row.issuer_caref != before
            if linked is not None and linked.refid in refids:
                found.append(row)
    if relinked:
        db.session.commit()
    return found


def attach_certificate(ca: CA, cert: x509.Certificate, username: str = 'system', *,
                       served: bool = False, commit: bool = True) -> Tuple[CACrossCertificate, List[str]]:
    """Store *cert* as a cross-certificate of *ca*; returns (row, warnings)."""
    from utils.cert_issuer import is_self_signed
    own = _load_record(ca) if ca.crt else None
    if own is None:
        raise CrossCertError('CA has no certificate yet', 409, 'ca_pending')
    try:
        basic = cert.extensions.get_extension_for_class(x509.BasicConstraints).value
    except x509.ExtensionNotFound:
        basic = None
    if basic is None or not basic.ca:
        raise CrossCertError('Not a CA certificate')
    if cert.subject != own.subject:
        raise CrossCertError("The subject differs from the CA's subject")
    if _spki(cert) != _spki(own):
        raise CrossCertError("The public key differs from the CA's key")
    if is_self_signed(cert):
        raise CrossCertError('A self-signed certificate is not a cross-certificate')
    fingerprint = hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()
    if hashlib.sha256(own.public_bytes(serialization.Encoding.DER)).hexdigest() == fingerprint:
        raise CrossCertError("This is the CA's own certificate", 409, 'duplicate')
    if CACrossCertificate.query.filter_by(fingerprint_sha256=fingerprint).first():
        raise CrossCertError('This cross-certificate is already attached', 409, 'duplicate')
    issuer, _ = _resolve_issuer(cert, ca)

    warnings = []
    for ext_class, label in ((x509.NameConstraints, 'name constraints'),
                             (x509.PolicyConstraints, 'policy constraints')):
        try:
            cert.extensions.get_extension_for_class(ext_class)
            warnings.append(f'The cross-certificate carries {label}: chains through it are restricted')
        except x509.ExtensionNotFound:
            pass
    if _naive(cert.not_valid_after_utc) <= utc_now():
        warnings.append('The cross-certificate is expired: it is kept but never served')

    from utils.cert_issuer import authority_key_identifier_hex
    row = CACrossCertificate(
        ca_id=ca.id,
        crt=base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode(),
        fingerprint_sha256=fingerprint,
        subject=cert.subject.rfc4514_string(),
        issuer=cert.issuer.rfc4514_string(),
        issuer_caref=issuer.refid if issuer else None,
        serial_number=str(cert.serial_number),
        aki=authority_key_identifier_hex(cert),
        valid_from=_naive(cert.not_valid_before_utc),
        valid_to=_naive(cert.not_valid_after_utc),
        served=False,
        created_by=username,
    )
    db.session.add(row)
    _apply_persisted_revocation(row)
    db.session.flush()
    if served:
        _serve(ca, row)
    if commit:
        db.session.commit()
    return row, warnings


def _apply_persisted_revocation(row):
    """A cross-certificate its issuer revoked before it was detached stays revoked."""
    issuer = CA.query.filter_by(refid=row.issuer_caref).first() if row.issuer_caref else None
    record = published_record(row, issuer) if issuer is not None else None
    if record is not None:
        row.revoked, row.revoked_at, row.revoke_reason = True, record.revoked_at, record.revoke_reason


def _serve(ca, row):
    if not row.servable:
        raise CrossCertError('An expired or revoked cross-certificate cannot be served', 409, 'not_servable')
    for other in CACrossCertificate.query.filter(CACrossCertificate.ca_id == ca.id,
                                                 CACrossCertificate.id != row.id).all():
        other.served = False
    row.served = True


def set_served(ca: CA, row: CACrossCertificate, served: bool, *, commit: bool = True):
    if served:
        _serve(ca, row)
    else:
        row.served = False
    if commit:
        db.session.commit()
    return row


def detach(row: CACrossCertificate, *, commit: bool = True):
    """Remove the row; the issuer's revocation record, if any, stays."""
    db.session.delete(row)
    if commit:
        db.session.commit()


def list_for(ca: CA) -> List[CACrossCertificate]:
    return CACrossCertificate.query.filter_by(ca_id=ca.id).order_by(CACrossCertificate.id).all()


def served_for(ca: CA) -> Optional[CACrossCertificate]:
    """The cross-certificate this CA serves now; never an expired or revoked one."""
    for row in CACrossCertificate.query.filter_by(ca_id=ca.id, served=True).all():
        if row.servable:
            return row
    return None


def certificate_of(row: CACrossCertificate) -> x509.Certificate:
    cert = _load_record(row)
    if cert is None:
        raise CrossCertError('Stored certificate could not be read', 500, 'corrupt')
    return cert


def published_record(row: CACrossCertificate, issuer: CA):
    """The issuer's revocation record for *row*'s serial, or None."""
    from models.revoked_serial import RevokedSerial
    from utils.cert_issuer import same_key_refids
    from utils.serial_format import serial_variants
    return RevokedSerial.query.filter(
        RevokedSerial.caref.in_(same_key_refids(issuer)),
        RevokedSerial.serial_number.in_(serial_variants(int(row.serial_number)))).first()


def _close_pending_requests(row, username):
    from services.approval_gate import resolve_moot_requests
    resolve_moot_requests('cross_revocation', 'cross_certificate_id', row.id, outcome='approved',
                          username=username, reason='Revoked directly', commit=False)


def revoke(row: CACrossCertificate, reason: str = 'unspecified', username: str = 'system',
           invalidity_at=None) -> List[str]:
    """Revoke the cross-certificate at its issuer (CRL and OCSP); the CA it certifies stays valid."""
    issuer = issuer_of(row)
    if issuer is None:
        raise CrossCertError('The issuing CA is not held here: revoke it at that issuer', 400, 'issuer_not_held')
    if row.revoked:
        raise CrossCertError('Cross-certificate is already revoked', 409, 'already_revoked')
    if reason in ('certificateHold', 'certificate_hold'):
        raise CrossCertError('A cross-certificate cannot be put on hold: revocation is permanent')
    from models.revoked_serial import RevokedSerial
    existing = published_record(row, issuer)
    if existing:
        # The issuer already publishes it: keep its date and reason, and only record that here
        row.revoked, row.revoked_at, row.revoke_reason, row.served = (
            True, existing.revoked_at, existing.revoke_reason, False)
        _close_pending_requests(row, username)
        db.session.flush()
        return ['The issuing CA already published this revocation: its date and reason were kept.']
    now = utc_now()
    row.revoked, row.revoked_at, row.revoke_reason, row.served = True, now, reason, False
    db.session.add(RevokedSerial(caref=issuer.refid, serial_number=row.serial_number, revoked_at=now,
                                 revoke_reason=reason, invalidity_at=invalidity_at,
                                 valid_to=row.valid_to, certificate_id=None))
    _close_pending_requests(row, username)
    db.session.commit()
    from models.ca import clear_request_caches
    clear_request_caches()
    return _publish_revocation(issuer, row, username)


def _publish_revocation(issuer, row, username):
    warnings = []
    if issuer.cdp_enabled:
        from services.crl_service import CRLService
        try:
            CRLService.generate_crl(issuer.id, username=username)
        except Exception as e:
            logger.warning(f"CRL of CA {issuer.descr} not regenerated after revoking a cross-certificate: {e}")
            warnings.append(f"The CRL of the issuing CA '{issuer.descr}' could not be regenerated: "
                            "the CRL currently served does not list this certificate yet.")
    else:
        warnings.append(f"CDP is disabled on the issuing CA '{issuer.descr}': "
                        "relying parties learn the revocation through OCSP only.")
    from services.ocsp_service import OCSPService
    OCSPService.invalidate_cached_responses(row.serial_number, ca_id=issuer.id)
    return warnings


def announce(ca: CA, action: str, row: CACrossCertificate, username: str, changes=None):
    """Audit entry and webhook; the CA snapshot is taken before the emit (subscribers may commit)."""
    from services.audit_service import AuditService
    AuditService.log_ca(f'ca_cross_certificate_{action}', ca,
                        f'Cross-certificate {action} on CA {ca.descr}: {row.subject} by {row.issuer}',
                        username=username)
    snapshot = ca.to_dict()
    from services.webhook_service import emit_ca_updated
    emit_ca_updated(snapshot, actor=username,
                    changes={'cross_certificate': action, 'cross_certificate_id': row.id, **(changes or {})})


def self_signed_counterpart(cert: x509.Certificate) -> Optional[CA]:
    """The stored self-signed CA whose subject and key *cert* re-certifies, or None."""
    from utils.cert_issuer import is_self_signed
    if is_self_signed(cert):
        return None
    wanted = _spki(cert)
    for ca in CA.query.filter(CA.subject == cert.subject.rfc4514_string()).order_by(CA.id).all():
        stored = _load_record(ca) if ca.crt else None
        if stored is not None and is_self_signed(stored) and _spki(stored) == wanted:
            return ca
    return None


def attach_to_counterpart(encoded_pem, username: str = 'system'):
    """Attach a base64 PEM that cross-certifies a stored self-signed CA; no commit.

    Returns ``(ca, row)``, or None when the certificate is not such a cross-certificate
    (the caller imports it as it would any CA). Raises CrossCertError on a refusal,
    a duplicate included, so the caller does not create a second record for the key."""
    try:
        cert = x509.load_pem_x509_certificate(base64.b64decode(encoded_pem))
    except Exception:
        return None
    ca = self_signed_counterpart(cert)
    if ca is None:
        return None
    row, _ = attach_certificate(ca, cert, username, commit=False)
    return ca, row


def _alert_payload(row, now):
    from utils.days_remaining import days_remaining
    from utils.datetime_utils import utc_isoformat
    return {'type': 'ca_cross_certificate', 'cross_certificate_id': row.id, 'ca_id': row.ca_id,
            'ca_refid': row.ca.refid, 'subject': row.subject,
            'issuer': row.issuer, 'serial_number': row.serial_number, 'served': bool(row.served),
            'valid_to': utc_isoformat(row.valid_to), 'days_until_expiry': days_remaining(row.valid_to, now)}


def _alert_scope(row):
    if row.issuer_caref and CA.query.filter_by(refid=row.issuer_caref).first() is not None:
        return row.issuer_caref
    return row.ca.refid


def expiring_alerts(days: int = 30, expired_within_hours: int = 24):
    """``(expiring, just_expired)`` payloads, each ``(scope_refid, dict)``, for unrevoked cross-certificates.

    The scope is the issuing CA while it is held, else the certified CA; ``ca_refid`` in the payload is the certified CA."""
    from datetime import timedelta
    now = utc_now()
    base = CACrossCertificate.query.join(CA, CA.id == CACrossCertificate.ca_id).filter(
        CACrossCertificate.revoked.is_(False))
    soon = base.filter(CACrossCertificate.valid_to > now,
                       CACrossCertificate.valid_to <= now + timedelta(days=days)).all()
    gone = base.filter(CACrossCertificate.valid_to <= now,
                       CACrossCertificate.valid_to > now - timedelta(hours=expired_within_hours)).all()
    return ([(_alert_scope(row), _alert_payload(row, now)) for row in soon],
            [(_alert_scope(row), _alert_payload(row, now)) for row in gone])
