"""Revocations UCM publishes and revocations it only records (issue #450).

UCM publishes a CA's revocations when it signs for that CA: its key is held here (software, HSM
or key provider), it is offline with its key set aside, a delegated OCSP responder whose key
UCM holds answers for it, or it serves an external CRL for it. A Microsoft CA or an ACME CA
publishes the revocations UCM tells it of. Under any other CA no CRL or OCSP answer ever carries
a revocation: it is local, may be lifted, and a valid certificate is deleted without one.
"""
from typing import Optional

from models import CA, Certificate, RevokedSerial, db

LOCAL = 'local'
UNKNOWN = 'unknown'
# Why a revocation is never lifted (never exposed: ``local_lift_state`` answers None for them)
_PUBLISHED = 'published'
_TOLD = 'told'
_UNRECORDED = 'unrecorded'

# Issuers outside UCM that UCM tells of a revocation (Microsoft CA, ACME CA)
TOLD_SOURCES = ('msca', 'acme_client')

# The risk a lift of a record older than upgrade step 176 runs, said by the 409 and the dialog
UNKNOWN_RISK = ('this revocation was recorded before UCM noted whether it was published: if its '
                'CA held its key in UCM then, this revocation may have been published')


class LiftRefused(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _has_external_crl(ca: CA) -> bool:
    from models.crl import CRLMetadata
    return db.session.query(CRLMetadata.id).filter_by(ca_id=ca.id, is_external=True).first() is not None


def _signs_for(ca: CA) -> bool:
    if ca.has_private_key or ca.offline or (ca.id is not None and _has_external_crl(ca)):
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
    their records too), or serves an external CRL for one of them."""
    if ca is None:
        return False
    from utils.cert_issuer import same_key_refids
    with db.session.no_autoflush:
        return any(_signs_for(c) for c in CA.query.filter(CA.refid.in_(same_key_refids(ca))))


def issuer_publishes(cert: Certificate, memo: Optional[dict] = None) -> bool:
    """Whether a revocation of ``cert`` reaches relying parties: its issuer outside UCM is told of
    it, or the CA it is linked to publishes it. ``memo`` keeps the answer per CA across calls."""
    if cert.source in TOLD_SOURCES:
        return True
    if not cert.caref:
        return False
    if memo is not None and cert.caref in memo:
        return memo[cert.caref]
    published = publishes_revocations(CA.query.filter_by(refid=cert.caref).first())
    if memo is not None:
        memo[cert.caref] = published
    return published


def note_publication(record: RevokedSerial, ca: Optional[CA], fresh: bool) -> None:
    """Set ``record.published`` at a write under ``ca``: published once UCM signs for it, local for
    a ``fresh`` record it does not sign for; an existing record keeps what it was otherwise."""
    if publishes_revocations(ca):
        record.published = True
    elif fresh:
        record.published = False


def publish_key_records(ca: CA, connection=None) -> None:
    """Every record of ``ca``'s key published: UCM signs for it from now on. No commit."""
    from sqlalchemy import or_
    from utils.cert_issuer import same_key_refids
    table = RevokedSerial.__table__
    statement = table.update().where(
        table.c.caref.in_(same_key_refids(ca)),
        or_(table.c.published.is_(None), table.c.published.is_(False))).values(published=True)
    (connection if connection is not None else db.session).execute(statement)


def publish_serials(ca: CA, serials) -> None:
    """The records of ``serials`` under ``ca``'s key published (an external CRL lists them)."""
    from utils.cert_issuer import same_key_refids
    from utils.serial_format import canonical_serial
    columns = sorted({canonical_serial(s) for s in serials})
    refids = same_key_refids(ca)
    for start in range(0, len(columns), 500):
        RevokedSerial.query.filter(
            RevokedSerial.caref.in_(refids), RevokedSerial.serial_number.in_(columns[start:start + 500]),
            RevokedSerial.published.isnot(True)).update({'published': True}, synchronize_session='fetch')


def note_told_issuer(cert: Certificate) -> None:
    """The issuer outside UCM was told of ``cert``'s revocation, or owes it: its records say
    published. Commits; never raises (the revocation itself is already committed)."""
    import logging
    try:
        ca, serial = _target(cert)
        if ca is not None and serial is not None:
            publish_serials(ca, [serial])
            db.session.commit()
    except Exception as e:  # noqa: BLE001
        db.session.rollback()
        logging.getLogger(__name__).error("Certificate %s: publication not noted: %s", cert.id, e)


def _gained(session, obj) -> bool:
    from sqlalchemy.orm.attributes import get_history
    from models import SystemConfig
    if isinstance(obj, CA):
        return bool(obj.crt) and (obj in session.new or any(
            get_history(obj, name).added for name in ('prv', 'hsm_key_id', 'offline', 'crt')))
    return isinstance(obj, SystemConfig) and (obj.key or '').startswith('ocsp_responder_cert_') and (
        obj in session.new or bool(get_history(obj, 'value').added))


def publish_on_flush(session) -> None:
    """After a flush that gave a CA its key, an offline state or a delegated responder: every
    record of its key is published, written after the CA row as the lift locks them."""
    from flask import has_app_context
    from models import SystemConfig
    if not has_app_context() or session is not db.session():
        return
    changed = [obj for obj in list(session.new) + list(session.dirty)
               if isinstance(obj, (CA, SystemConfig)) and _gained(session, obj)]
    if not changed:
        return
    with session.no_autoflush:
        for obj in changed:
            ca_id = obj.key.rsplit('_', 1)[1] if isinstance(obj, SystemConfig) else None
            if ca_id is not None and not ca_id.isdigit():
                continue
            ca = obj if ca_id is None else session.get(CA, int(ca_id))
            if ca is not None and ca.refid and _signs_for(ca):
                publish_key_records(ca, session.connection())


def _state(records, ca, copies=()) -> str:
    if publishes_revocations(ca) or any(r.published is True for r in records):
        return _PUBLISHED
    if any(row.source in TOLD_SOURCES for row in copies):
        return _TOLD
    # A row revoked with no record: its records may have gone with a deleted CA of its key
    if not records:
        return _UNRECORDED
    if any(r.published is None for r in records):
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
    state = _state(revocation_records(ca, serial), ca, [cert, *_copies(ca, serial)])
    return state if state in (LOCAL, UNKNOWN) else None


def _refusal(cert, ca, serial, records, copies, acknowledge_unknown) -> Optional[LiftRefused]:
    from services.crl.external import ExternalCRLMixin
    from utils.revocation_reasons import HOLD_REASONS
    state = _state(records, ca, copies)
    name = cert.descr or cert.refid
    held = all(r.revoke_reason in HOLD_REASONS for r in records) and (
        not cert.revoked or cert.revoke_reason in HOLD_REASONS)
    hint = (' It is on hold: remove the hold with Unhold.' if held
            else ' RFC 5280 lifts only a certificateHold.')
    if state == _PUBLISHED:
        return LiftRefused(409, f'Certificate "{name}": this revocation was published, so it '
                                f'cannot be lifted.{hint}')
    if state == _TOLD:
        return LiftRefused(409, f'Certificate "{name}" was issued by a CA outside UCM (Microsoft '
                                f'CA or ACME CA) that is told of its revocation, so it cannot be '
                                f'lifted.{hint}')
    if state == _UNRECORDED:
        return LiftRefused(409, f'Certificate "{name}": UCM holds no record of this revocation, so '
                                'it cannot tell whether it was published: it cannot be lifted.')
    from utils.cert_issuer import same_key_refids
    if any(ExternalCRLMixin.get_external_revocation(c.id, serial) is not None
           for c in CA.query.filter(CA.refid.in_(same_key_refids(ca)))):
        return LiftRefused(409, f'Certificate "{name}": the external CRL UCM serves for its CA '
                                'lists this revocation, so it cannot be lifted.')
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


def _lock_issuer(ca) -> None:
    """The CA records of ``ca``'s key locked for update (PostgreSQL) by ascending id and read
    afresh, before the serial's records: a key gained meanwhile is seen, its writer waits."""
    from utils.cert_issuer import same_key_refids
    CA.query.filter(CA.refid.in_(same_key_refids(ca))).order_by(CA.id) \
        .with_for_update().populate_existing().all()


def _keep_key_refused(cert, rows, records) -> None:
    """A key revoked as compromised stays refused once its records go: kept in compromised_keys."""
    from models import compromised_key
    from utils.revocation_reasons import normalize_revocation_reason
    from utils.spki_digest import certificate_key_sha256
    compromised = [r for r in records if normalize_revocation_reason(r.revoke_reason) == 'keyCompromise']
    revoked_rows = [row for row in rows if row.revoked
                    and normalize_revocation_reason(row.revoke_reason) == 'keyCompromise']
    if not compromised and not revoked_rows:
        return
    digests = {r.public_key_sha256 for r in compromised if r.public_key_sha256}
    digests |= {d for d in (certificate_key_sha256(row.crt) for row in rows) if d}
    dates = [h.revoked_at for h in (*compromised, *revoked_rows) if h.revoked_at]
    if not digests or not all(compromised_key.remember_compromised_key(
            digest, compromised_key.key_source(cert), revoked_at=min(dates) if dates else None,
            cert_refid=cert.refid, subject=cert.subject) for digest in sorted(digests)):
        raise LiftRefused(500, f'Certificate "{cert.descr or cert.refid}": its key was revoked as '
                               'compromised and could not be kept refused: nothing was lifted')


def lift_local_revocation(cert: Certificate, acknowledge_unknown: bool = False) -> list:
    """Clear the revocation of every copy of ``cert`` and delete its serial's records, or raise
    LiftRefused (no commit). The CA records of its key are locked, then the serial's records,
    then the rows, as a key import and the hourly pass take them; a change seen under lock refuses."""
    from services.cert.issued_lookup import (effective_revocation, lift_persisted_revocation,
                                             lock_serial_records)
    if effective_revocation(cert) is None:
        raise LiftRefused(400, 'Certificate is not revoked')
    ca, serial = _target(cert)
    if ca is None or serial is None:
        raise LiftRefused(409, f'Certificate "{cert.descr or cert.refid}" is linked to no CA in '
                               'UCM: there is no local revocation record to lift')
    targets = [(ca, serial)]
    _lock_issuer(ca)
    locked = lock_serial_records(targets)
    before = {r.id: r.published for r in locked}
    copies = _copies(ca, serial)
    refused = _refusal(cert, ca, serial, locked, [cert, *copies], acknowledge_unknown)
    if refused is not None:
        raise refused
    rows = [row for row in copies if row.revoked or row.id == cert.id]
    _keep_key_refused(cert, rows, locked)
    Certificate.query.filter(Certificate.id.in_([row.id for row in rows])).update(
        {'revoked': False, 'revoked_at': None, 'revoke_reason': None, 'invalidity_at': None},
        synchronize_session='fetch')
    # Read again under the rows' write locks: SQLite takes its lock only at the UPDATE above
    # (PostgreSQL already holds every lock, so this second order is free)
    locked = lock_serial_records(targets)
    if {r.id: r.published for r in locked} != before:
        raise LiftRefused(409, f'Certificate "{cert.descr or cert.refid}" was revoked again '
                               'meanwhile: nothing was lifted')
    _lock_issuer(ca)
    refused = _refusal(cert, ca, serial, locked, [cert, *copies], acknowledge_unknown)
    if refused is not None:
        raise refused
    lift_persisted_revocation(ca, serial)
    return rows
