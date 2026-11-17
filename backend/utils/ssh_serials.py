"""One serial number per certificate under an SSH CA (PROTOCOL.certkeys; PROTOCOL.krl §2.2).

A KRL names the certificates of a CA by serial, so ``uq_ssh_certificates_ca_serial`` holds every
non-zero serial once per CA (0 means "no number"). Rows issued twice before 3.0 keep their number,
which their signature carries: the oldest stays in the index, so no new row can take the number,
``serial_duplicate`` takes the others out of it; the upgrade lists them and the next start reports
them once. ``ssh_cas.serial_counter`` never trails the serials
its CA holds; every path that writes certificates or counters calls ``raise_counters``. A pair is
revoked as the KRL revokes it, both holders or neither, and so is every certificate bearing the key ID
of a revoked serial 0 certificate of its CA, which ssh-keygen lists by key ID (``align_revocations``).
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
# A listed certificate the upgrade revoked through the key ID of a serial 0 certificate, not a pair
KEY_ID_KIND = 'revoked_by_key_id'
REMEDY = ('the KRL revokes by serial, so revoking one revokes them all: '
          'revoke them and issue new certificates')

_HIGHEST = 'SELECT COALESCE(MAX(c.serial), 0) FROM ssh_certificates c WHERE c.ssh_ca_id = ssh_cas.id'
# The SET re-reads serial_counter: a value another writer stored meanwhile is never lowered
_RAISE = (f'UPDATE ssh_cas SET serial_counter = CASE WHEN serial_counter < ({_HIGHEST}) '
          f'THEN ({_HIGHEST}) ELSE serial_counter END WHERE serial_counter < ({_HIGHEST})')
# An older certificate of the same CA holds the same serial
_OLDER = ('EXISTS (SELECT 1 FROM ssh_certificates o WHERE o.ssh_ca_id = ssh_certificates.ssh_ca_id '
          'AND o.serial = ssh_certificates.serial AND o.id < ssh_certificates.id)')
_TO_MARK = f'SELECT id FROM ssh_certificates WHERE serial <> 0 AND NOT {FLAG} AND {_OLDER} ORDER BY id'
_LAGGING = (f'SELECT id, descr, serial_counter, ({_HIGHEST}) FROM ssh_cas '
            f'WHERE serial_counter < ({_HIGHEST}) ORDER BY id')
_GROUPS = ('SELECT c.id, c.ssh_ca_id, a.descr, c.serial, c.key_id FROM ssh_certificates c '
           'LEFT JOIN ssh_cas a ON a.id = c.ssh_ca_id WHERE c.serial <> 0 AND EXISTS (SELECT 1 FROM '
           'ssh_certificates o WHERE o.ssh_ca_id = c.ssh_ca_id AND o.serial = c.serial AND o.id <> c.id) '
           'ORDER BY c.ssh_ca_id, c.serial, c.id')

# The KRL revokes c through o (PROTOCOL.krl): o holds c's non-zero serial, or o is of serial 0, which
# ssh-keygen -k lists by key ID under the CA, and c bears that key ID, whatever its serial or key
_REVOKES = ('o.ssh_ca_id = c.ssh_ca_id AND o.id <> c.id AND o.revoked AND '
            '((c.serial <> 0 AND o.serial = c.serial) OR (o.serial = 0 AND o.key_id = c.key_id))')
# Each valid certificate the KRL revokes, and the certificate of the oldest revocation revoking it
# (dated before undated, then lowest id)
_UNREVOKED = (f'SELECT c.id, (SELECT o.id FROM ssh_certificates o WHERE {_REVOKES} '
              'ORDER BY CASE WHEN o.revoked_at IS NULL THEN 1 ELSE 0 END, o.revoked_at, o.id LIMIT 1) '
              'FROM ssh_certificates c '
              f'WHERE NOT COALESCE(c.revoked, FALSE) AND EXISTS (SELECT 1 FROM ssh_certificates o WHERE {_REVOKES}) '
              'ORDER BY c.id')
_ZERO_BEARING = ('SELECT id FROM ssh_certificates WHERE ssh_ca_id = :ca AND serial = 0 AND revoked '
                 'AND key_id = :k ORDER BY id LIMIT 1')
_REVOKE_AS = ('UPDATE ssh_certificates SET revoked = TRUE, '
              'revoked_at = (SELECT s.revoked_at FROM ssh_certificates s WHERE s.id = :s), '
              'revoke_reason = (SELECT s.revoke_reason FROM ssh_certificates s WHERE s.id = :s) WHERE id = :i')

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
    """Ids of the certificates under the index that an older certificate of their CA shares a serial with."""
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


def diverging_revocations(run: Run) -> Dict[int, int]:
    """{valid certificate the KRL revokes: the revoked certificate it would be revoked with}."""
    return {row_id: source for row_id, source in run(_UNREVOKED, {}).fetchall()}


def revoking_key_id(run: Run, ca_id: int, key_id: str) -> Optional[int]:
    """The revoked certificate of serial 0 of the CA bearing *key_id*, whose KRL entry revokes it."""
    row = run(_ZERO_BEARING, {'ca': ca_id, 'k': key_id}).fetchone()
    return row[0] if row else None


def refuse_revoked_key_id(ca_id: int, key_id: str, imported: bool = False, named_by_ca: bool = False) -> None:
    """A new certificate bearing a key ID its CA's KRL revokes would be revoked from the start."""
    source = revoking_key_id(session_run, ca_id, key_id)
    if source is not None:
        raise ValueError(f"The KRL of this SSH CA revokes key ID '{key_id}', which revoked certificate "
                         f"#{source} of serial 0 bears: a certificate bearing it would be revoked from the start. "
                         + (f"Delete certificate #{source} once it has expired, then import again" if imported
                            else f'Tick "Let requesters set the key ID" on the CA to use another key ID, or '
                                 f"delete certificate #{source} once it has expired" if named_by_ca
                            else f"Use another key ID, or delete certificate #{source} once it has expired"))


def _by_key_id(run: Run, source: int) -> bool:
    row = run('SELECT serial FROM ssh_certificates WHERE id = :i', {'i': source}).fetchone()
    return row is not None and row[0] == 0


def align_revocations(run: Run) -> Dict[int, int]:
    """Each valid certificate the KRL revokes (``_REVOKES``) is revoked with the date and reason of
    the oldest revocation revoking it, until none is left. {id revoked here: id it was revoked with}."""
    aligned: Dict[int, int] = {}
    while True:
        diverging = diverging_revocations(run)
        if not diverging:
            return aligned
        for row_id, source in diverging.items():
            run(_REVOKE_AS, {'i': row_id, 's': source})
            logger.warning("SSH certificate #%s revoked with #%s, which %s under their CA (the KRL revokes "
                           "it)", row_id, source,
                           'is of serial 0 and bears its key ID' if _by_key_id(run, source) else 'holds its serial')
        aligned.update(diverging)


def revocation_entries(run: Run, aligned: Dict[int, int]) -> List[Dict]:
    """One audit entry per certificate *aligned* revoked, in a fixed phrase: ids, serial and key id only."""
    entries = []
    for row_id, source in sorted(aligned.items()):
        row = run('SELECT serial, key_id FROM ssh_certificates WHERE id = :i', {'i': row_id}).fetchone()
        if row is None:
            continue
        details = (f'SSH certificate revoked with #{source}, of serial 0 and the same key ID under their CA: '
                   'the KRL revokes that key ID' if _by_key_id(run, source) else
                   f'SSH certificate revoked with #{source}, which holds serial {row[0]} '
                   'under their CA: the KRL revokes by serial')
        entries.append(dict(action='ssh_cert_revoked', resource_type='ssh_certificate', resource_id=str(row_id),
                            resource_name=row[1], success=True, details=details))
    return entries


def mark_duplicates(run: Run, aligned: Optional[Dict[int, int]] = None) -> List[Dict]:
    """Mark every certificate but the oldest of a shared serial; the groups newly marked or holding
    a certificate of *aligned* (``align_revocations``), which each group lists under 'revoked'."""
    aligned = aligned or {}
    ids = unmarked_duplicates(run)
    if not ids and not aligned:
        return []
    groups = duplicate_groups(run, set(ids) | set(aligned))
    for row_id in ids:
        run(f'UPDATE ssh_certificates SET {FLAG} = TRUE WHERE id = :i', {'i': row_id})
    for entry in groups:
        revoked = [[i, aligned[i]] for i in entry['ids'] if i in aligned]
        if revoked:
            entry['revoked'] = revoked
    return groups


def key_id_revocations(run: Run, aligned: Dict[int, int], groups: List[Dict]) -> List[Dict]:
    """One entry per certificate of *aligned* revoked through the key ID of a serial 0 certificate
    that no group of *groups* already lists, in the form ``list_for_next_start`` keeps."""
    listed = {i for entry in groups for i, _ in entry.get('revoked') or []}
    entries = []
    for row_id, source in sorted(aligned.items()):
        if row_id in listed or not _by_key_id(run, source):
            continue
        row = run('SELECT c.ssh_ca_id, a.descr, c.key_id FROM ssh_certificates c LEFT JOIN ssh_cas a '
                  'ON a.id = c.ssh_ca_id WHERE c.id = :i', {'i': row_id}).fetchone()
        if row is not None:
            entries.append({'kind': KEY_ID_KIND, 'ssh_ca_id': row[0], 'ca': row[1], 'ids': [row_id],
                            'key_ids': [row[2]], 'revoked': [[row_id, source]]})
    return entries


def settle_marks(run: Run) -> Dict[int, int]:
    """The oldest holder of each serial under the index, every other one marked; marks first, so
    no statement ever puts two holders under the index. Then ``align_revocations``, returned."""
    mark_duplicates(run)
    run(f'UPDATE ssh_certificates SET {FLAG} = FALSE WHERE {FLAG} AND NOT {_OLDER}', {})
    return align_revocations(run)


def describe(entry: Dict) -> str:
    """One group, or one certificate revoked through a key ID, as the log and the audit entry show it."""
    if entry.get('kind') == KEY_ID_KIND:
        (row_id, source), = entry.get('revoked') or [[None, None]]
        return (f"SSH CA '{entry.get('ca') or ''}' (#{entry.get('ssh_ca_id')}): certificate #{row_id} "
                f"'{(entry.get('key_ids') or [''])[0]}' revoked with #{source}, of serial 0 and the same key ID: "
                "the KRL revokes that key ID")
    held = ', '.join(f"#{i} '{k}'" for i, k in zip(entry.get('ids') or [], entry.get('key_ids') or []))
    revoked = ''.join(f"; #{i} revoked with #{s}, as the KRL already revoked it"
                      for i, s in entry.get('revoked') or [])
    return (f"SSH CA '{entry.get('ca') or ''}' (#{entry.get('ssh_ca_id')}) issued serial "
            f"{entry.get('serial')} to {len(entry.get('ids') or [])} certificates ({held}){revoked}: {REMEDY}")


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
            "'SSH certificates the upgrade found sharing a serial or revoked through a key ID', CURRENT_TIMESTAMP)",
            {'k': MARKED_KEY, 'v': value})


def session_run(sql, params=None):
    """*run* on the application session, inside its transaction."""
    from sqlalchemy import text
    from models import db
    return db.session.execute(text(sql), params or {})


def report_marked_duplicates(app) -> int:
    """At start: one WARNING and one audit entry per serial the upgrade found shared, and per
    certificate it revoked through a key ID, once.

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
            if entry.get('kind') == KEY_ID_KIND:
                AuditService.log_action(action='ssh_cert_revoked', resource_type='ssh_certificate',
                                        resource_id=str((entry.get('ids') or [''])[0]),
                                        resource_name=(entry.get('key_ids') or [''])[0],
                                        details=text, success=True, username='system')
                continue
            AuditService.log_action(action=MARKED_ACTION, resource_type='ssh_ca',
                                    resource_id=str(entry.get('ssh_ca_id')), resource_name=entry.get('ca'),
                                    details=text, success=True, username='system')
        return len(entries)
