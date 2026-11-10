"""Certificates sharing one serial under one CA (RFC 5280 §4.1.2.2).

Migration 142 creates ``uix_certificates_ca_serial`` only when this finds nothing;
a backend migration or a restore onto a schema that has the index checks its source
with the same query and refuses, naming the rows, rather than failing on the index.
"""
from typing import Dict, Iterable, List

INDEX = 'uix_certificates_ca_serial'
# Rows the index covers: CSRs carry no serial, imported certificates no CA
_COVERED = "caref IS NOT NULL AND serial_number IS NOT NULL AND serial_number <> ''"
DUPLICATES = (f"SELECT caref, serial_number, COUNT(*) FROM certificates WHERE {_COVERED} "
              "GROUP BY caref, serial_number HAVING COUNT(*) > 1 ORDER BY caref, serial_number")
_IDS = (f"SELECT id FROM certificates WHERE {_COVERED} "
        "AND caref = :caref AND serial_number = :serial ORDER BY id")
CLEANUP = ("resolve them on the source and run migration 142 again there, "
           "as docs/CONCURRENCY.md describes")


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
