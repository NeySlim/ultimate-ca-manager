"""Upgrade step 174: the former CAs whose certificates a Windows enrollment profile renews.

``renewal_ca_refids`` (a JSON list of CA refids) is the operator's list; a profile whose CA
changed before this step lists every CA of UCM that issued a certificate it holds, so its
renewals go on as before. A list already set is kept. Idempotent, dual-backend.
"""
import json
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

PROFILES = 'windows_enrollment_profiles'
COLUMN = 'renewal_ca_refids'
DDL = f"ALTER TABLE {PROFILES} ADD COLUMN {COLUMN} TEXT"
# The CAs behind a profile's certificates: its own rows, and for the default the wstep rows naming none
FORMER = ("SELECT DISTINCT c.caref FROM certificates c JOIN certificate_authorities a ON a.refid = c.caref "
          "WHERE c.caref IS NOT NULL AND (c.windows_profile_id = {p} "
          "OR ({default} AND c.windows_profile_id IS NULL AND c.source = 'wstep'))")


def _initial(rows, former):
    """``(id, json)`` for each profile not listed yet: its former CAs, sorted, its own CA left out."""
    out = []
    for profile_id, is_default, issuing in rows:
        refids = sorted({r for r in former(profile_id, bool(is_default)) if r and r != issuing})
        out.append((json.dumps(refids), profile_id))
    return out


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                        (PROFILES,)).fetchone() is None:
            return
        if COLUMN not in {row[1] for row in conn.execute(f"PRAGMA table_info({PROFILES})")}:
            conn.execute(DDL)
        rows = conn.execute(f"SELECT id, is_default, issuing_ca_refid FROM {PROFILES} "
                            f"WHERE {COLUMN} IS NULL").fetchall()
        sql = FORMER.format(p='?', default='?')
        updates = _initial(rows, lambda pid, default: [
            r[0] for r in conn.execute(sql, (pid, 1 if default else 0))])
        conn.executemany(f"UPDATE {PROFILES} SET {COLUMN} = ? WHERE id = ?", updates)
        conn.commit()
        logger.info("[174] renewal CAs of %d Windows enrollment profiles (SQLite)", len(updates))
        return
    from sqlalchemy import inspect, text
    if PROFILES not in inspect(conn).get_table_names():
        return
    if COLUMN not in {c['name'] for c in inspect(conn).get_columns(PROFILES)}:
        conn.execute(text(DDL))
    rows = conn.execute(text(f"SELECT id, is_default, issuing_ca_refid FROM {PROFILES} "
                             f"WHERE {COLUMN} IS NULL")).fetchall()
    sql = text(FORMER.format(p=':p', default=':d'))
    updates = _initial(rows, lambda pid, default: [
        r[0] for r in conn.execute(sql, {'p': pid, 'd': default})])
    for value, profile_id in updates:
        conn.execute(text(f"UPDATE {PROFILES} SET {COLUMN} = :v WHERE id = :i"), {'v': value, 'i': profile_id})
    logger.info("[174] renewal CAs of %d Windows enrollment profiles (PostgreSQL)", len(updates))


def downgrade(conn):
    """No downgrade: 2.254 ignores the column."""
    pass
