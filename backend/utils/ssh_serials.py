"""One serial number per certificate under an SSH CA (PROTOCOL.certkeys; PROTOCOL.krl §2.2).

A KRL names the certificates of a CA by serial, so ``uq_ssh_certificates_ca_serial`` holds every
non-zero serial once per CA (0 means "no number"). Rows issued twice before 3.0 keep their number,
which their signature carries: ``serial_duplicate`` takes them out of the index, the upgrade lists
them and the next start reports them once. ``ssh_cas.serial_counter`` never trails the serials
its CA holds; every path that writes certificates or counters calls ``raise_counters``.
"""
import json
import logging
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

INDEX = 'uq_ssh_certificates_ca_serial'
FLAG = 'serial_duplicate'
# Same text on both backends: the index, the model and the upgrade step agree on it
COVERED = f'serial <> 0 AND NOT {FLAG}'
CREATE_INDEX = (f'CREATE UNIQUE INDEX IF NOT EXISTS {INDEX} '
                f'ON ssh_certificates (ssh_ca_id, serial) WHERE {COVERED}')
# SystemConfig key the upgrade leaves for the next start, and the audit action it becomes
MARKED_KEY = 'ssh_serial_duplicates_marked'
MARKED_ACTION = 'ssh_serial_duplicate_marked'
REMEDY = ('the KRL revokes by serial, so revoking one revokes them all: '
          'revoke them and issue new certificates')

_HIGHEST = 'SELECT COALESCE(MAX(c.serial), 0) FROM ssh_certificates c WHERE c.ssh_ca_id = ssh_cas.id'
# The SET re-reads serial_counter: a value another writer stored meanwhile is never lowered
_RAISE = (f'UPDATE ssh_cas SET serial_counter = CASE WHEN serial_counter < ({_HIGHEST}) '
          f'THEN ({_HIGHEST}) ELSE serial_counter END WHERE serial_counter < ({_HIGHEST})')
_SIBLING = ('EXISTS (SELECT 1 FROM ssh_certificates o WHERE o.ssh_ca_id = ssh_certificates.ssh_ca_id '
            'AND o.serial = ssh_certificates.serial AND o.id <> ssh_certificates.id)')
_TO_MARK = f'SELECT id FROM ssh_certificates WHERE serial <> 0 AND NOT {FLAG} AND {_SIBLING} ORDER BY id'
_LAGGING = (f'SELECT id, descr, serial_counter, ({_HIGHEST}) FROM ssh_cas '
            f'WHERE serial_counter < ({_HIGHEST}) ORDER BY id')
_GROUPS = ('SELECT c.id, c.ssh_ca_id, a.descr, c.serial, c.key_id FROM ssh_certificates c '
           'LEFT JOIN ssh_cas a ON a.id = c.ssh_ca_id WHERE c.serial <> 0 AND EXISTS (SELECT 1 FROM '
           'ssh_certificates o WHERE o.ssh_ca_id = c.ssh_ca_id AND o.serial = c.serial AND o.id <> c.id) '
           'ORDER BY c.ssh_ca_id, c.serial, c.id')

Run = Callable[..., object]


def raise_counters(run: Run, ca_id: Optional[int] = None) -> None:
    """Move each CA's counter up to the highest serial it holds, never down; *run(sql, params)*."""
    if ca_id is None:
        run(_RAISE, {})
    else:
        run(_RAISE + ' AND id = :ca', {'ca': ca_id})


def lagging_counters(run: Run) -> List[tuple]:
    """(id, descr, counter, highest serial) of every CA whose counter trails its certificates."""
    return [tuple(r) for r in run(_LAGGING, {}).fetchall()]


def unmarked_duplicates(run: Run) -> List[int]:
    """Ids of the certificates sharing a non-zero serial under their CA and not marked so."""
    return [r[0] for r in run(_TO_MARK, {}).fetchall()]


def duplicate_groups(run: Run, ids=None) -> List[Dict]:
    """Every serial held twice under one CA, with the certificates holding it (limited to *ids*)."""
    groups: Dict = {}
    for row_id, ca_id, ca, serial, key_id in run(_GROUPS, {}).fetchall():
        entry = groups.setdefault((ca_id, serial), {'ssh_ca_id': ca_id, 'ca': ca, 'serial': serial,
                                                    'ids': [], 'key_ids': []})
        entry['ids'].append(row_id)
        entry['key_ids'].append(key_id)
    wanted = None if ids is None else set(ids)
    return [g for g in groups.values() if wanted is None or wanted & set(g['ids'])]


def mark_duplicates(run: Run) -> List[Dict]:
    """Mark the unmarked certificates that share their serial; the groups they belong to."""
    ids = unmarked_duplicates(run)
    if not ids:
        return []
    groups = duplicate_groups(run, ids)
    for row_id in ids:
        run(f'UPDATE ssh_certificates SET {FLAG} = TRUE WHERE id = :i', {'i': row_id})
    return groups


def describe(entry: Dict) -> str:
    """One group as the log and the audit entry show it."""
    held = ', '.join(f"#{i} '{k}'" for i, k in zip(entry.get('ids') or [], entry.get('key_ids') or []))
    return (f"SSH CA '{entry.get('ca') or ''}' (#{entry.get('ssh_ca_id')}) issued serial "
            f"{entry.get('serial')} to {len(entry.get('ids') or [])} certificates ({held}): {REMEDY}")


def list_for_next_start(run: Run, groups: List[Dict]) -> None:
    """Add *groups* to the list the next start reports (``report_marked_duplicates``)."""
    if not groups:
        return
    held = run('SELECT value FROM system_config WHERE key = :k', {'k': MARKED_KEY}).fetchone()
    try:
        listed = json.loads(held[0] or '[]') if held else []
    except ValueError:
        listed = []
    value = json.dumps(listed + groups)
    if held:
        run('UPDATE system_config SET value = :v WHERE key = :k', {'v': value, 'k': MARKED_KEY})
    else:
        run("INSERT INTO system_config (key, value, description, updated_at) VALUES (:k, :v, "
            "'SSH certificates the upgrade found sharing a serial under their CA', CURRENT_TIMESTAMP)",
            {'k': MARKED_KEY, 'v': value})


def session_run(sql, params=None):
    """*run* on the application session, inside its transaction."""
    from sqlalchemy import text
    from models import db
    return db.session.execute(text(sql), params or {})


def report_marked_duplicates(app) -> int:
    """At start: one WARNING and one audit entry per serial the upgrade found shared, once.

    The list is deleted in the transaction of the first entry: a node that finds it gone reports nothing."""
    from models import db, SystemConfig
    from services.audit_service import AuditService
    with app.app_context():
        row = SystemConfig.query.filter_by(key=MARKED_KEY).first()
        if row is None:
            return 0
        try:
            entries = [e for e in json.loads(row.value or '[]') if isinstance(e, dict)]
        except ValueError:
            entries = []
        if not db.session.execute(db.delete(SystemConfig).where(SystemConfig.key == MARKED_KEY)).rowcount:
            db.session.rollback()
            return 0
        if not entries:
            db.session.commit()
            return 0
        for entry in entries:
            text = describe(entry)
            logger.warning("%s", text)
            AuditService.log_action(action=MARKED_ACTION, resource_type='ssh_ca',
                                    resource_id=str(entry.get('ssh_ca_id')), resource_name=entry.get('ca'),
                                    details=text, success=True, username='system')
        return len(entries)
