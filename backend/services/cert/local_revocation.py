"""Revocations UCM publishes and revocations it only records (issue #450).

UCM publishes a CA's revocations when it signs for that CA: its key is held here (software, HSM
or key provider), it is offline with its key set aside, or a delegated OCSP responder whose key
UCM holds answers for it. Under any other CA no CRL or OCSP answer ever carries a revocation:
it is local, may be lifted, and a valid certificate is deleted without one.
"""
from typing import Optional

from models import CA, Certificate, RevokedSerial, db

LOCAL = 'local'
UNKNOWN = 'unknown'

# The risk a lift of a record older than upgrade step 176 runs, said by the 409 and the dialog
UNKNOWN_RISK = ('this revocation was recorded before UCM noted whether it was published: if its '
                'CA held its key in UCM then, this revocation may have been published')


class LiftRefused(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _signs_for(ca: CA) -> bool:
    if ca.has_private_key or ca.offline:
        return True
    from models import SystemConfig
    config = SystemConfig.query.filter_by(key=f'ocsp_responder_cert_{ca.id}').first()
    try:
        responder = db.session.get(Certificate, int(config.value)) if config and config.value else None
    except (TypeError, ValueError):
        return False
    return responder is not None and bool(responder.prv)


def publishes_revocations(ca: Optional[CA]) -> bool:
    """Whether UCM signs a CRL or an OCSP answer for ``ca`` or a record of its key (its CRL lists
    their records too): any of them holding its key, offline, or with a delegated responder."""
    if ca is None:
        return False
    from utils.cert_issuer import same_key_refids
    with db.session.no_autoflush:
        return any(_signs_for(c) for c in CA.query.filter(CA.refid.in_(same_key_refids(ca))))


def issuer_publishes(cert: Certificate) -> bool:
    """Whether the CA ``cert`` is linked to publishes its revocations; no CA in UCM never does."""
    ca = CA.query.filter_by(refid=cert.caref).first() if cert.caref else None
    return publishes_revocations(ca)


def note_publication(record: RevokedSerial, ca: Optional[CA], fresh: bool) -> None:
    """Set ``record.published`` at a write under ``ca``: published once UCM signs for it, local for
    a ``fresh`` record it does not sign for; an existing record keeps what it was otherwise."""
    if publishes_revocations(ca):
        record.published = True
    elif fresh:
        record.published = False


def _state(records, ca) -> Optional[str]:
    if publishes_revocations(ca) or any(r.published is True for r in records):
        return None
    # A row revoked with no record is older than the records: nothing says it was never published
    if not records or any(r.published is None for r in records):
        return UNKNOWN
    return LOCAL


def _target(cert: Certificate):
    from services.cert.serial_resolution import resolve_record_serial
    ca = CA.query.filter_by(refid=cert.caref).first() if cert.caref else None
    return ca, resolve_record_serial(cert)


def local_lift_state(cert: Certificate) -> Optional[str]:
    """LOCAL or UNKNOWN when an administrator may lift ``cert``'s revocation, else None."""
    from services.cert.issued_lookup import effective_revocation, revocation_records
    if effective_revocation(cert) is None:
        return None
    ca, serial = _target(cert)
    if ca is None or serial is None:
        return None
    return _state(revocation_records(ca, serial), ca)


def _refusal(cert, ca, records, acknowledge_unknown) -> Optional[LiftRefused]:
    from utils.revocation_reasons import HOLD_REASONS
    state = _state(records, ca)
    name = cert.descr or cert.refid
    if state is None:
        held = all(r.revoke_reason in HOLD_REASONS for r in records) and (
            not cert.revoked or cert.revoke_reason in HOLD_REASONS)
        hint = (' It is on hold: remove the hold with Unhold.' if held
                else ' RFC 5280 lifts only a certificateHold.')
        return LiftRefused(409, f'Certificate "{name}" has a published revocation: its CA signs '
                                f'CRLs or OCSP answers in UCM, so it cannot be lifted.{hint}')
    if state == UNKNOWN and not acknowledge_unknown:
        return LiftRefused(409, f'Certificate "{name}": {UNKNOWN_RISK}. Acknowledge the risk '
                                '(acknowledge_unknown_publication) to lift it.')
    return None


def _copies(ca, serial) -> list:
    """Every stored row of ``serial`` under ``ca``'s key: one revocation, whichever copy it names."""
    from services.cert.issued_lookup import _row_serial
    from utils.cert_issuer import same_key_refids
    from utils.serial_format import serial_variants
    rows = Certificate.query.filter(
        Certificate.caref.in_(same_key_refids(ca)),
        Certificate.serial_number.in_(serial_variants(serial)),
        Certificate.crt.isnot(None)).order_by(Certificate.id).all()
    return [row for row in rows if _row_serial(row) == serial]


def lift_local_revocation(cert: Certificate, acknowledge_unknown: bool = False) -> list:
    """Clear the revocation of every copy of ``cert`` and delete its serial's records, or raise
    LiftRefused (no commit). Records are locked before the rows, as unhold and the hourly pass
    take them; a record added or published meanwhile, seen under lock, refuses."""
    from services.cert.issued_lookup import (effective_revocation, lift_persisted_revocation,
                                             lock_serial_records)
    if effective_revocation(cert) is None:
        raise LiftRefused(400, 'Certificate is not revoked')
    ca, serial = _target(cert)
    if ca is None or serial is None:
        raise LiftRefused(409, f'Certificate "{cert.descr or cert.refid}" is linked to no CA in '
                               'UCM: there is no local revocation record to lift')
    targets = [(ca, serial)]
    locked = lock_serial_records(targets)
    before = {r.id: r.published for r in locked}
    refused = _refusal(cert, ca, locked, acknowledge_unknown)
    if refused is not None:
        raise refused
    rows = [row for row in _copies(ca, serial) if row.revoked or row.id == cert.id]
    Certificate.query.filter(Certificate.id.in_([row.id for row in rows])).update(
        {'revoked': False, 'revoked_at': None, 'revoke_reason': None, 'invalidity_at': None},
        synchronize_session='fetch')
    # Read again under the rows' write locks: SQLite takes its lock only at the UPDATE above
    after = {r.id: r.published for r in lock_serial_records(targets)}
    if after != before:
        raise LiftRefused(409, f'Certificate "{cert.descr or cert.refid}" was revoked again '
                               'meanwhile: nothing was lifted')
    lift_persisted_revocation(ca, serial)
    return rows
