"""Certificates sharing one serial under one CA (RFC 5280 §4.1.2.2).

Migration 142 creates ``uix_certificates_ca_serial`` only when this finds nothing;
a backend migration or a restore onto a schema that has the index checks its source
with the same query and refuses, naming the rows, rather than failing on the index.
"""
from typing import Dict, Iterable, List

INDEX = 'uix_certificates_ca_serial'
# SystemConfig key migration 142 leaves while duplicates keep it from creating the index
PENDING_KEY = 'serial_unique_index_pending'
# Rows the index covers: CSRs carry no serial, imported certificates no CA
_COVERED = "caref IS NOT NULL AND serial_number IS NOT NULL AND serial_number <> ''"
DUPLICATES = (f"SELECT caref, serial_number, COUNT(*) FROM certificates WHERE {_COVERED} "
              "GROUP BY caref, serial_number HAVING COUNT(*) > 1 ORDER BY caref, serial_number")
_IDS = (f"SELECT id FROM certificates WHERE {_COVERED} "
        "AND caref = :caref AND serial_number = :serial ORDER BY id")
# Self-contained: packages ship no docs/, so the message is the procedure
CLEANUP = ("Revoke or delete the certificates listed on the installation that holds them, until "
           "each serial appears once under its CA. Then delete the row "
           "'142_serial_per_ca_and_proxy_links' from the _migrations table, so the next start "
           "runs migration 142 again and creates the index.")


def duplicates_in_database(conn) -> List[Dict]:
    """(caref, serial_number, ids) of every serial held twice under one CA, read through *conn*."""
    from sqlalchemy import text
    return [{'caref': caref, 'serial_number': serial,
             'ids': [i for (i,) in conn.execute(text(_IDS), {'caref': caref, 'serial': serial})]}
            for caref, serial, _ in conn.execute(text(DUPLICATES)).fetchall()]


def duplicates_in_rows(rows: Iterable[Dict], id_key: str = 'refid') -> List[Dict]:
    """The same grouping over exported certificate dictionaries (a backup archive)."""
    groups: Dict = {}
    for row in rows:
        caref, serial = row.get('caref'), row.get('serial_number')
        if caref is None or serial is None or serial == '':
            continue
        groups.setdefault((caref, serial), []).append(row.get(id_key))
    return [{'caref': caref, 'serial_number': serial, 'ids': ids}
            for (caref, serial), ids in sorted(groups.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1])))
            if len(ids) > 1]


def describe(duplicates: List[Dict], limit: int = 10) -> str:
    """One line per pair, for a refusal message."""
    shown = '; '.join(f"CA {d['caref']} serial {d['serial_number']}: {', '.join(map(str, d['ids']))}"
                      for d in duplicates[:limit])
    more = f" (and {len(duplicates) - limit} more)" if len(duplicates) > limit else ''
    return shown + more


def check_pending_serial_index(app) -> int:
    """At start: log the pairs migration 142 left pending and keep their count for /health.
    The flag changes only when migrations run, that is at start."""
    import json
    import logging
    from models import SystemConfig
    count = 0
    with app.app_context():
        row = SystemConfig.query.filter_by(key=PENDING_KEY).first()
        if row is not None:
            try:
                count = len(json.loads(row.value or '{}').get('duplicates') or []) or 1
            except (ValueError, AttributeError):
                count = 1
    app.config['SERIAL_INDEX_PENDING'] = count
    if count:
        logging.getLogger(__name__).warning(
            "%s: %d serial number(s) are shared by certificates of one CA, so the unique "
            "serial index is not in place. %s", PENDING_KEY, count, CLEANUP)
    return count
