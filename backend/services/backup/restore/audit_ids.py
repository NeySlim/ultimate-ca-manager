"""Audit entries keep, through a replacing restore, the id their seal covers.

`AuditLog.compute_hash` seals the id with the rest of the entry, so an entry
written under another id reads as tampered. An archive of this version carries
the ids; a replacing restore writes each entry back under its own, and the id
counter goes past them. A merge, and an archive without ids, still number the
entries here, and the report says that those do not verify.
"""
import json
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from models import db

from .plan import RestoreValidationError, _normalise, shared_identity_warning

SECTION = 'audit_logs'
# Half the range of the column, an integer on PostgreSQL: an archive cannot bring the
# sequence to its end, after which no entry would be written
ID_LIMIT = 2 ** 30
KEYED_CHAIN = 2

OTHER_KEY = ("{count} audit log entries sealed under another master key cannot be verified "
             "here; putting the original master key back before restoring keeps the history "
             "verifiable")
WITHOUT_IDS = ("{count} audit log entries do not verify on this installation: the archive, "
               "written by an earlier version, does not carry their ids, which their seal covers")
IMPORTED = ("{count} audit log entries imported from the archive do not verify on this "
            "installation: a merge writes them under new ids, which their seal covers")


def carried_ids(rows: Optional[List[Dict[str, Any]]]) -> bool:
    """Whether every archived entry carries its id (False when none does).

    Anything else is refused before the first write: an id that is not a whole number in
    the column's range, one repeated, or an id on some rows and not on others."""
    carrying = None
    seen = set()
    for position, row in enumerate(rows or []):
        has = 'id' in row
        if carrying is None:
            carrying = has
        elif has != carrying:
            raise RestoreValidationError(
                f"Invalid backup: row {position} of section '{SECTION}' "
                f"{'carries' if has else 'lacks'} the id the rows before it "
                f"{'lack' if has else 'carry'}; nothing has been changed")
        if not has:
            continue
        value = row['id']
        if type(value) is not int or not 1 <= value <= ID_LIMIT:
            raise RestoreValidationError(
                f"Invalid backup: row {position} of section '{SECTION}' holds an id that is "
                f"not a whole number from 1 to {ID_LIMIT}; nothing has been changed")
        if value in seen:
            raise RestoreValidationError(
                f"Invalid backup: row {position} of section '{SECTION}' repeats the id "
                f"{value}; nothing has been changed")
        seen.add(value)
    return bool(carrying)


def rows_to_remove(archived_rows: List[Dict[str, Any]], plan) -> List[Any]:
    """The entries here that are not an archived entry under its own id.

    One sealed like an archived entry but under another id goes too: the archived one
    takes that id, so every entry left is the archive's, and no id is held twice."""
    archived = {(_normalise(row.get('entry_hash')), row['id']) for row in archived_rows}
    here = plan.target_ids.get(SECTION) or {}
    shared = plan.shared.get(SECTION) or {}
    doomed = []
    for key, oldest in here.items():
        ids = shared.get(key, [oldest])
        gone = [entry_id for entry_id in ids if (key[0], entry_id) not in archived]
        doomed.extend(gone)
        if key in shared:
            plan.warnings.append(shared_identity_warning(
                SECTION, key, ids, 'removed', gone,
                taken="the archive's rows of it go back under their own id"))
    # An entry without a seal is no archived entry here: removed, as the generic path does
    incomplete = plan.incomplete.get(SECTION) or []
    if incomplete:
        doomed.extend(incomplete)
        plan.warnings.append(
            f"{SECTION}: {len(incomplete)} row(s) here without a complete entry_hash "
            f"(id {', '.join(map(str, incomplete))}) are removed, then those the archive "
            "carries are restored from it as new rows")
    return doomed


def hold_appends() -> None:
    """On PostgreSQL, the lock every append takes (`append_entry`), until the commit: no
    entry is numbered or chained while the archived ids are written and the counter moved."""
    from services.audit.chain import _APPEND_LOCK
    if db.session.get_bind().dialect.name == 'postgresql':
        db.session.execute(text('SELECT pg_advisory_xact_lock(:k)'), {'k': _APPEND_LOCK})


def advance_counter() -> None:
    """PostgreSQL's sequence past the highest id; SQLite numbers from the highest row already."""
    conn = db.session.connection()
    if conn.dialect.name != 'postgresql':
        return
    sequence = conn.execute(text("SELECT pg_get_serial_sequence('audit_logs', 'id')")).scalar()
    if not sequence:
        return
    highest = conn.execute(text("SELECT MAX(id) FROM audit_logs")).scalar() or 0
    current = conn.execute(text("SELECT pg_sequence_last_value(CAST(:s AS regclass))"),
                           {'s': sequence}).scalar() or 0
    if highest > current:
        conn.execute(text("SELECT setval(CAST(:s AS regclass), :n, true)"),
                     {'s': sequence, 'n': highest})


def sealed_under_a_key_unknown_here(rows: List[Dict[str, Any]], local: Optional[str]) -> int:
    """Keyed entries this server cannot verify: neither under its key, nor under a key the
    first entry sealed with its key records the ledger rotated from (as the verification reads it)."""
    other = [row for row in rows if row.get('hash_version') == KEYED_CHAIN
             and row.get('hash_key_id') != local]
    own = [row for row in rows if row.get('hash_version') == KEYED_CHAIN
           and row.get('hash_key_id') == local]
    if not other or not own:
        return len(other)
    first = min(own, key=lambda row: row['id'])
    try:
        limits = json.loads(first.get('retired_keys') or '{}').get('keys')
    except (TypeError, ValueError, AttributeError):
        limits = None
    if not isinstance(limits, dict):
        limits = {}

    def recorded(row) -> bool:
        key_id = row.get('hash_key_id')
        limit = limits.get(key_id) if isinstance(key_id, str) else None
        return type(limit) is int and row['id'] <= limit and row['id'] < first['id']
    return sum(1 for row in other if not recorded(row))


def settle(plan) -> None:
    """After the section is written: the counter, and what the report says of the entries."""
    rows = plan.rows.get(SECTION) or []
    if not rows:
        return
    if plan.keep_audit_ids:
        db.session.flush()
        advance_counter()
        from services.audit.chain import chain_key
        key = chain_key()
        other = sealed_under_a_key_unknown_here(rows, key[1] if key else None)
        if other:
            plan.warnings.append(OTHER_KEY.format(count=other))
    elif plan.audit_new:
        merged = SECTION not in plan.pruned
        plan.warnings.append((IMPORTED if merged else WITHOUT_IDS).format(count=plan.audit_new))
