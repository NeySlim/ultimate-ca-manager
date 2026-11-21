"""Certificates sharing one serial under one CA (RFC 5280 §4.1.2.2).

The upgrade from 2.254 (migration 300, steps 142 and 144) creates ``uix_certificates_ca_serial``
only when this finds nothing, and leaves unconverted the rows that would share a serial once canonical.
A backend migration checks its source, and a restore its archive only when the target
carries the index, refusing with the rows named rather than failing on the index; both
compare canonical serials (utils/serial_format.py), whatever spelling a row holds.
The pending flag describes this database's schema and never travels in a backup.
"""
from typing import Dict, Iterable, List

from utils.serial_format import canonical_stored_serial

INDEX = 'uix_certificates_ca_serial'
# SystemConfig key the upgrade from 2.254 leaves while duplicates keep it from creating the index
PENDING_KEY = 'serial_unique_index_pending'
# Rows the index covers: CSRs carry no serial, imported certificates no CA
_COVERED = "caref IS NOT NULL AND serial_number IS NOT NULL AND serial_number <> ''"
DUPLICATES = (f"SELECT caref, serial_number, COUNT(*) FROM certificates WHERE {_COVERED} "
              "GROUP BY caref, serial_number HAVING COUNT(*) > 1 ORDER BY caref, serial_number")
ROWS_OF_COVERED = f"SELECT id, caref, serial_number FROM certificates WHERE {_COVERED} ORDER BY id"
_ROWS = f"SELECT id, caref, serial_number, crt FROM certificates WHERE {_COVERED} ORDER BY id"
# Self-contained: packages ship no docs/, so the message is the procedure
CLEANUP = ("Delete all but one certificate of each listed serial on the installation that holds "
           "them, found by the certificate ids and stored spellings shown with it where there are any (revoke it first if it is in use; a revoked row still counts), until each serial "
           "appears once under its CA. Then restart UCM: while this warning stands, every start runs step "
           "144 of the upgrade from 2.254 again, which creates the index and stores every serial in decimal.")


def duplicates_in_database(conn) -> List[Dict]:
    """(caref, serial_number, ids) of every serial held twice under one CA, read through *conn*."""
    from sqlalchemy import text
    groups: Dict = {}
    # Streamed: one batch of PEMs in memory at a time, as in the upgrade step 144
    for row_id, caref, serial, crt in conn.execute(text(_ROWS), execution_options={'yield_per': 500}):
        groups.setdefault((caref, canonical_stored_serial(serial, crt)), []).append((row_id, serial))
    return _shared(groups)


def duplicates_in_rows(rows: Iterable[Dict], id_key: str = 'refid') -> List[Dict]:
    """The same grouping over exported certificate dictionaries (a backup archive)."""
    groups: Dict = {}
    for row in rows:
        caref, serial = row.get('caref'), row.get('serial_number')
        if caref is None or serial is None or serial == '':
            continue
        canonical = canonical_stored_serial(serial, row.get('certificate_pem'))
        groups.setdefault((caref, canonical), []).append((row.get(id_key), serial))
    return _shared(groups)


def _shared(groups: Dict) -> List[Dict]:
    return [{'caref': caref, 'serial_number': serial, 'ids': [i for i, _ in held], 'stored': [s for _, s in held]}
            for (caref, serial), held in sorted(groups.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1])))
            if len(held) > 1]


def stored_rows(ids, raw) -> List[Dict]:
    """The rows a pending entry points at: certificate id and the spelling stored now."""
    return [{'id': row_id, 'stored': raw[row_id]} for row_id in ids]


def describe_pending(entry: Dict) -> str:
    """One pending entry as the log shows it; entries stored without `rows` still read."""
    head = (f"CA {entry.get('caref')} serial {entry.get('serial_number')} waits for {entry['waits_for']}"
            if entry.get('waits_for')
            else f"CA {entry.get('caref')} serial {entry.get('serial_number')} x{entry.get('count', '?')}")
    rows = entry.get('rows') or []
    if not rows:
        return head
    return head + ' [certificate ids ' + ', '.join(f"{r.get('id')} stored as '{r.get('stored')}'" for r in rows) + ']'


def describe(duplicates: List[Dict], limit: int = 10) -> str:
    """One line per pair, each id with the spelling it stores, for a refusal message."""
    def rows(d):
        stored = d.get('stored')
        return ', '.join(f"{i} (stored as '{s}')" for i, s in zip(d['ids'], stored)) if stored \
            else ', '.join(map(str, d['ids']))
    shown = '; '.join(f"CA {d['caref']} serial {d['serial_number']}: {rows(d)}" for d in duplicates[:limit])
    more = f" (and {len(duplicates) - limit} more)" if len(duplicates) > limit else ''
    return shown + more


def check_pending_serial_index(app) -> int:
    """At start: log the pairs the upgrade from 2.254 left pending and keep their count for /health.
    The flag changes only when migrations run, that is at start."""
    import json
    import logging
    from models import SystemConfig
    count, pairs = 0, []
    with app.app_context():
        row = SystemConfig.query.filter_by(key=PENDING_KEY).first()
        if row is not None:
            try:
                pairs = json.loads(row.value or '{}').get('duplicates') or []
            except (ValueError, AttributeError):
                pairs = []
            count = len(pairs) or 1
    app.config['SERIAL_INDEX_PENDING'] = count
    if count:
        listed = '; '.join(describe_pending(d) for d in pairs[:10]) or 'see the log of migration 300_upgrade_from_2_254'
        logging.getLogger(__name__).warning(
            "%s: %d serial number(s) are shared by certificates of one CA or wait for one that is (%s), so the unique "
            "serial index does not cover them. %s", PENDING_KEY, count, listed, CLEANUP)
    return count
