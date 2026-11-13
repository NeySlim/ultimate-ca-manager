"""Which stored certificate a presented certificate is, and whether it may
still act on behalf of its holder.

Protocol renewals (EST /simplereenroll, SCEP RenewalReq, WSTEP renew)
authenticate the request with the certificate being renewed. Serial number
and subject are public, and the serial column mixes decimal and hexadecimal
forms, so each protocol used to answer the question its own way (byte
equality under the CA for WSTEP, decimal serial only for SCEP, nothing at all
for EST). One rule now: the presented certificate must be, byte for byte, a
certificate this CA issued and still holds, not revoked (row or persistent
revocation record) and not expired.
"""

import base64
from datetime import datetime
from typing import Optional, Tuple

from cryptography import x509
from utils.csr_extensions import extensions_of
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import Encoding

from models import CA, Certificate, RevokedSerial, db
from utils.datetime_utils import utc_isoformat, utc_now
from utils.serial_format import canonical_serial, serial_variants

OK = 'ok'
UNKNOWN = 'unknown'
REVOKED = 'revoked'
EXPIRED = 'expired'
NOT_YET_VALID = 'not_yet_valid'
SUPERSEDED = 'superseded'
# EST and SCEP only: the certificate renews through its Windows enrollment profile (WSTEP)
WINDOWS_PROFILE = 'windows_profile'


def find_issued_rows(ca: CA, cert: x509.Certificate) -> list:
    """Every row under ``ca``, or under another record of its subject and key,
    holding exactly ``cert`` (normally one; a duplicate left by an inconsistent
    restore still counts). Empty when ``ca``'s key did not sign ``cert``: a row
    linked to a CA is not proof that the CA issued what it holds."""
    from utils.cert_issuer import ca_signed, same_key_refids
    rows = _rows_holding(cert, Certificate.caref.in_(same_key_refids(ca)))
    return rows if rows and ca_signed(ca, cert) else []


def find_stored_rows(cert: x509.Certificate) -> list:
    """Every row, under any issuer, holding exactly ``cert``: its serial alone is public."""
    return _rows_holding(cert)


def acme_ordered_first(rows: list) -> list:
    """``rows`` with those an ACME order names first, then by id: a client order names its
    row, or the one its renewal moved off, and says which CA account to tell; a server order
    names the row it issued. A copy stored again never stands in for them."""
    from models.acme_models import AcmeClientOrder, AcmeOrder
    ids = [row.id for row in rows]
    named = set()
    for model in (AcmeClientOrder, AcmeOrder):
        named.update(cid for (cid,) in model.query.with_entities(model.certificate_id)
                     .filter(model.certificate_id.in_(ids)))
    rank = {row.id: 0 if row.id in named else 2 for row in rows}
    for row in rows:
        if row.id in named or not row.serial_number:
            continue
        for order in AcmeClientOrder.query.filter(
                AcmeClientOrder.replaced_certificates.contains(row.serial_number, autoescape=True)):
            if order.names_replaced(row):
                # The id a renewal recorded tells the row it moved from the copies of the same certificate
                recorded = any(e.get('certificate_id') == row.id for e in order._replaced_entries())
                rank[row.id] = min(rank[row.id], 0 if recorded else 1)
    return sorted(rows, key=lambda row: (rank[row.id], row.id))


def _rows_holding(cert: x509.Certificate, *criteria) -> list:
    presented = cert.public_bytes(Encoding.DER)
    candidates = Certificate.query.filter(
        *criteria,
        # Every spelling: rows the upgrade step 144 left pending may hold the revoked twin
        Certificate.serial_number.in_(serial_variants(cert.serial_number)),
        Certificate.crt.isnot(None),
    ).all()
    rows = []
    for row in candidates:
        try:
            stored = x509.load_pem_x509_certificate(base64.b64decode(row.crt), default_backend())
        except Exception:
            continue
        if stored.public_bytes(Encoding.DER) == presented:
            rows.append(row)
    return rows


def find_issued_row(ca: CA, cert: x509.Certificate) -> Optional[Certificate]:
    """The row under ``ca`` (or a record of its key) holding exactly ``cert``, or None."""
    rows = find_issued_rows(ca, cert)
    return rows[0] if rows else None


_REASON_RANK = {x509.ReasonFlags.key_compromise: 0, x509.ReasonFlags.ca_compromise: 0,
                x509.ReasonFlags.aa_compromise: 0, x509.ReasonFlags.certificate_hold: 2,
                x509.ReasonFlags.remove_from_crl: 3}


def reason_rank(reason) -> int:
    """0 for a compromise, 1 for any other final reason, 2 for a suspension, 3 for removeFromCRL."""
    from utils.revocation_reasons import REASON_FLAGS
    return _REASON_RANK.get(REASON_FLAGS.get(reason or 'unspecified', x509.ReasonFlags.unspecified), 1)


def revocation_order(record):
    """Sort key of a revocation record: a compromise first, then any final revocation,
    then a suspension; between equals the earliest date."""
    return reason_rank(record.revoke_reason), record.revoked_at or datetime.max, record.id or 0


def gravest_revocation(*holders):
    """Of the revoked rows and records given (None skipped), the one with the gravest reason;
    the first given between equals. The CRL and OCSP answer with it."""
    present = [h for h in holders if h is not None]
    return min(present, key=lambda h: reason_rank(h.revoke_reason)) if present else None


def record_serial_clause(serial):
    """The records of ``serial``: the column is canonical decimal (upgrade step 144), so only
    equality names it; another serial's all-digit hex spelling never does."""
    return RevokedSerial.serial_number == canonical_serial(serial)


def record_reason_replaceable(record, reason) -> bool:
    """Whether a writer may put ``reason`` (and its date) in ``record``: over a suspension, or
    with a graver reason; a final reason is never replaced by an equal or milder one."""
    from utils.revocation_reasons import HOLD_REASONS
    return record.revoke_reason in HOLD_REASONS or reason_rank(reason) < reason_rank(record.revoke_reason)


def revocation_records(ca: CA, serial: int) -> list:
    """Every record of ``ca``'s key (or a record of the same subject and key) for
    ``serial`` (``record_serial_clause``), gravest first."""
    from utils.cert_issuer import same_key_refids
    return sorted(RevokedSerial.query.filter(
        RevokedSerial.caref.in_(same_key_refids(ca)), record_serial_clause(serial)).all(),
        key=revocation_order)


def persisted_revocation(ca: CA, serial: int):
    """The record that says ``serial`` is revoked under ``ca``, or None. Any record does,
    whichever row it is linked to (migration 154 deleted the holds older releases left lifted)."""
    records = revocation_records(ca, serial)
    return records[0] if records else None


def lift_persisted_revocation(ca: CA, serial: int) -> int:
    """Delete every record of ``serial`` under ``ca``'s key (``record_serial_clause``). No commit."""
    from utils.cert_issuer import same_key_refids
    return RevokedSerial.query.filter(
        RevokedSerial.caref.in_(same_key_refids(ca)),
        record_serial_clause(serial),
    ).delete(synchronize_session='fetch')


def gravest_records_by_serial(records) -> dict:
    """The gravest of ``records`` per serial they name (``revocation_order``), keyed by the
    canonical column ``record_serial_clause`` compares: ``records`` are read once, not per row."""
    gravest = {}
    for record in sorted(records, key=revocation_order):
        gravest.setdefault(record.serial_number, record)
    return gravest


def answered_revocation(row: Certificate, ca: CA, records: Optional[dict] = None):
    """What the CRL and OCSP say of the revoked ``row``: itself, or when it is only held, the
    final record of its serial under ``ca`` (or a record of its key), the graver of the two.
    ``records`` (``gravest_records_by_serial`` of the key's records) spares a query per row."""
    from utils.revocation_reasons import HOLD_REASONS
    from services.cert.serial_resolution import resolve_record_serial
    if row.revoke_reason not in HOLD_REASONS:
        return row
    serial = resolve_record_serial(row)
    if serial is None:
        return row
    record = records.get(canonical_serial(serial)) if records is not None else persisted_revocation(ca, serial)
    return gravest_revocation(row, record)


def _row_serial(row: Certificate) -> Optional[int]:
    try:
        return x509.load_pem_x509_certificate(base64.b64decode(row.crt), default_backend()).serial_number
    except Exception:
        return None


def row_persisted_revocation(row: Certificate, ca: Optional[CA] = None):
    """The record that says ``row``'s certificate is revoked under ``ca`` (default: its
    ``caref``), or None; a row whose certificate cannot be read has none."""
    if ca is None:
        ca = CA.query.filter_by(refid=row.caref).first() if row.caref else None
    if ca is None or not row.crt:
        return None
    serial = _row_serial(row)
    return None if serial is None else persisted_revocation(ca, serial)


def row_revoked(row: Certificate) -> bool:
    """Whether ``row`` is revoked, by its own columns or by the record of its serial."""
    return bool(row.revoked) or row_persisted_revocation(row) is not None


def effective_revocation(row: Certificate):
    """What revokes ``row``: the graver of its own revocation and its serial's record, or None."""
    return gravest_revocation(row if row.revoked else None, row_persisted_revocation(row))


def persisted_revocations_of(rows) -> dict:
    """``{row id: record}`` as ``row_persisted_revocation`` answers each of ``rows``: one query
    of their serials' records, then two per distinct CA of the rows that have one (the CA and
    its same-key records), so a page costs at most ``1 + 2 * per_page`` and never one per row."""
    from utils.cert_issuer import same_key_refids
    serials = {row.id: serial for row in rows if row.caref and row.crt
               and (serial := _row_serial(row)) is not None}
    if not serials:
        return {}
    by_column = {}
    for record in RevokedSerial.query.filter(
            RevokedSerial.serial_number.in_({canonical_serial(s) for s in serials.values()})):
        by_column.setdefault(record.serial_number, []).append(record)
    refids, found = {}, {}
    for row in rows:
        records = by_column.get(canonical_serial(serials[row.id])) if row.id in serials else None
        if not records:
            continue
        if row.caref not in refids:
            ca = CA.query.filter_by(refid=row.caref).first()
            refids[row.caref] = set(same_key_refids(ca)) if ca is not None else set()
        mine = [r for r in records if r.caref in refids[row.caref]]
        if mine:
            found[row.id] = min(mine, key=revocation_order)
    return found


def show_effective_revocation(data: dict, row: Certificate, record) -> dict:
    """``data`` (``row.to_dict()``) with the revocation ``record`` makes when it is graver
    than the row's own, as OCSP and the CRL answer it."""
    holder = gravest_revocation(row if row.revoked else None, record)
    if holder is not None and holder is not row:
        data.update(revoked=True, status='revoked', revoke_reason=holder.revoke_reason,
                    revoked_at=utc_isoformat(holder.revoked_at), invalidity_at=utc_isoformat(holder.invalidity_at))
    return data


def apply_persisted_revocation(row: Certificate, record=None) -> bool:
    """Mark ``row`` revoked from the record its CA still holds for its serial: a certificate
    revoked, deleted and imported again comes back revoked. A given final ``record`` also
    replaces a suspension of the row. No commit; returns whether one applied."""
    from sqlalchemy import inspect
    from utils.revocation_reasons import HOLD_REASONS
    if record is None:
        if row.revoked:
            return False
        record = row_persisted_revocation(row)
        if record is None:
            return False
        # A stored row is locked first, then marked by a statement that checks the record with a
        # snapshot taken after any wait, never under a share lock on the record (deadlock)
        if inspect(row).persistent:
            db.session.query(Certificate.id).filter(Certificate.id == row.id).with_for_update().first()
            return _mark_while_recorded(row, record)
        if not _record_still_held(record):
            return False
    elif row.revoked and row.revoke_reason not in HOLD_REASONS:
        return False
    row.revoked = True
    row.revoked_at = record.revoked_at
    row.revoke_reason = record.revoke_reason
    row.invalidity_at = record.invalidity_at
    return True


def _records_still_held(records) -> set:
    """The ids of ``records`` still stored, read again under share locks (PostgreSQL) held to the
    commit and taken by ascending id, the order an unhold locks a pair's records in: an unhold
    that deleted one first wins, and one deleting it later waits for the mark. The records take
    the values they hold under the lock: a revocation committed meanwhile is what gets marked."""
    ids, held = sorted({record.id for record in records}), set()
    for start in range(0, len(ids), 500):
        held.update(r.id for r in RevokedSerial.query.filter(
            RevokedSerial.id.in_(ids[start:start + 500])).order_by(RevokedSerial.id)
            .with_for_update(read=True).populate_existing())
    return held


def _record_still_held(record) -> bool:
    """``_records_still_held`` of one record."""
    return record.id in _records_still_held([record])


def _mark_while_recorded(row: Certificate, record) -> bool:
    """Mark the unrevoked ``row`` from ``record`` in one statement conditioned on the record still
    being stored: SQLite takes its write lock there, so a lift committed before it is seen."""
    from sqlalchemy import exists, or_
    from sqlalchemy.orm.attributes import set_committed_value
    values = {'revoked': True, 'revoked_at': record.revoked_at,
              'revoke_reason': record.revoke_reason, 'invalidity_at': record.invalidity_at}
    done = Certificate.query.filter(
        Certificate.id == row.id,
        or_(Certificate.revoked.is_(False), Certificate.revoked.is_(None)),
        exists().where(RevokedSerial.id == record.id),
    ).update(values, synchronize_session=False)
    if done:
        for field, value in values.items():
            set_committed_value(row, field, value)
    return bool(done)


def interrupted_lift(row: Certificate) -> bool:
    """A row in removeFromCRL is an unhold stopped between its two commits unless a record
    of its serial says otherwise: a hold record or none is a lift to finish, a final one is not."""
    from utils.revocation_reasons import HOLD_REASONS
    from services.cert.serial_resolution import resolve_record_serial
    ca = CA.query.filter_by(refid=row.caref).first() if row.caref else None
    serial = resolve_record_serial(row)
    records = revocation_records(ca, serial) if ca is not None and serial is not None else []
    return all(r.revoke_reason in HOLD_REASONS for r in records)


def lock_serial_records(targets) -> list:
    """The records of every ``(ca, serial)`` of ``targets`` (``revocation_records``), locked for
    update (PostgreSQL) to the commit in one statement by ascending id: taken before the rows,
    in the order the hourly pass takes them, so an unhold of a pair and the pass never deadlock."""
    from sqlalchemy import and_, or_
    from utils.cert_issuer import same_key_refids
    clauses = [and_(RevokedSerial.caref.in_(same_key_refids(ca)), record_serial_clause(serial))
               for ca, serial in targets]
    if not clauses:
        return []
    return RevokedSerial.query.filter(or_(*clauses)).order_by(RevokedSerial.id) \
        .with_for_update().populate_existing().all()


def apply_persisted_revocations(ids=None) -> list:
    """Mark revoked every linked, unrevoked row holding a serial its CA recorded as revoked
    (rows stored by an earlier release), only the rows of ``ids`` when given (what a restore
    wrote). No commit; returns ``(row, record)`` per row marked."""
    from sqlalchemy import or_
    # Read afresh: a revocation or hold another worker made since this session loaded it counts
    db.session.flush()
    db.session.expire_all()
    # Both columns are canonical (upgrade step 144): a record names the rows of its own serial only
    columns = sorted({column for (column,) in RevokedSerial.query.with_entities(
        RevokedSerial.serial_number).distinct() if column})
    found = []
    for start in range(0, len(columns), 500):
        for row in Certificate.query.filter(
                Certificate.serial_number.in_(columns[start:start + 500]),
                Certificate.caref.isnot(None), Certificate.crt.isnot(None),
                or_(Certificate.revoked.is_(False), Certificate.revoked.is_(None))).all():
            if ids is not None and row.id not in ids:
                continue
            record = row_persisted_revocation(row)
            if record is not None:
                found.append((row, record))
    # Every record locked before any row is marked, as an unhold takes them
    held = _records_still_held(record for _, record in found)
    return [(row, record) for row, record in found
            if record.id in held and _mark_while_recorded(row, record)]


def issued_certificate_status(ca: CA, cert: x509.Certificate) -> Tuple[Optional[Certificate], str]:
    """``(row, status)`` with status one of OK, UNKNOWN, REVOKED, EXPIRED,
    NOT_YET_VALID, SUPERSEDED.

    A certificate revoked and then deleted keeps its persistent revocation
    record, and answers REVOKED rather than UNKNOWN."""
    rows = find_issued_rows(ca, cert)
    row = rows[0] if rows else None
    persistent = persisted_revocation(ca, cert.serial_number)
    if row is None:
        return None, (REVOKED if persistent is not None else UNKNOWN)
    if any(r.revoked for r in rows) or persistent is not None:
        return row, REVOKED
    if all(r.archived for r in rows):
        # Replaced by a renewal: the holder presents the newer certificate,
        # the replaced one must not go on producing certificates
        return row, SUPERSEDED
    # A restored duplicate may sit beside the archived original: the live row answers
    row = next(r for r in rows if not r.archived)
    now = utc_now()
    if cert.not_valid_before_utc.replace(tzinfo=None) > now:
        return row, NOT_YET_VALID
    not_after = cert.not_valid_after_utc.replace(tzinfo=None)
    if not_after <= now or (row.valid_to and row.valid_to < now):
        return row, EXPIRED
    return row, OK


def protocol_renewal_status(ca: CA, cert: x509.Certificate) -> Tuple[Optional[Certificate], str]:
    """``issued_certificate_status`` for an EST or SCEP renewal: a certificate a Windows enrollment
    profile holds (an id, even of a profile deleted since, or a ``wstep`` row) answers WINDOWS_PROFILE,
    expired or superseded alike; only REVOKED takes precedence."""
    row, status = issued_certificate_status(ca, cert)
    # The row that carries the profile answers, not a plain twin beside it: the audit names it
    held = next((r for r in find_issued_rows(ca, cert)
                 if r.windows_profile_id is not None or r.source == 'wstep'), None)
    if status != REVOKED and held is not None:
        return held, WINDOWS_PROFILE
    return row, status


def _san_identity(cert_or_csr):
    try:
        ext = extensions_of(cert_or_csr).get_extension_for_oid(x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
    except x509.ExtensionNotFound:
        return None
    return {(type(name).__name__, str(getattr(name, 'value', name))) for name in ext.value}


def san_identity_matches(cert: x509.Certificate, csr: x509.CertificateSigningRequest) -> bool:
    """A renewal keeps its identity: the CSR's SAN set equals the renewed
    certificate's (order and criticality aside); a CSR without SAN is
    accepted, as on EST re-enrolment."""
    requested = _san_identity(csr)
    if requested is None:
        return True
    return requested == (_san_identity(cert) or set())
