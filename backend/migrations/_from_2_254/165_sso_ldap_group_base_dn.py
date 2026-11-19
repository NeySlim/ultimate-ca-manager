"""Upgrade step 165: an optional LDAP group search base; one SSO provider per type.

``ldap_group_base_dn``: empty keeps the derived base. The unique index
``uq_pro_sso_providers_provider_type`` holds the rule 2.254 enforced only at creation: two
providers of one type refuse the upgrade before migration 300 writes anything (``refusal``).
A blank name, which 2.254 accepted on a rename, becomes the provider's type (numbered when another
provider holds it). Idempotent, dual-backend (SQLite + PostgreSQL).
"""
import logging
import sqlite3

from utils.unique_names import first_free

logger = logging.getLogger(__name__)
pg_compatible = True

TABLE = 'pro_sso_providers'
COLUMN = 'ldap_group_base_dn'
DDL = f"ALTER TABLE {TABLE} ADD COLUMN {COLUMN} VARCHAR(500)"
INDEX = f"CREATE UNIQUE INDEX IF NOT EXISTS uq_pro_sso_providers_provider_type ON {TABLE} (provider_type)"
_SHARED = (f"SELECT provider_type, id, name FROM {TABLE} WHERE provider_type IN "
           f"(SELECT provider_type FROM {TABLE} GROUP BY provider_type HAVING COUNT(*) > 1) "
           f"ORDER BY provider_type, id")


def _refusal_text(rows):
    if not rows:
        return None
    types = {}
    for provider_type, provider_id, name in rows:
        types.setdefault(provider_type, []).append(f"'{name}' (#{provider_id})")
    named = '; '.join(f"{len(held)} SSO providers of type {kind}: {', '.join(held)}"
                      for kind, held in types.items())
    return (f"Upgrade refused: {named}. UCM uses one SSO provider per type: start 2.254 again, keep one "
            f"provider of each type and delete the others, then upgrade. Nothing was changed: 2.254 "
            f"still starts on this database.")


def _has_table(conn):
    if isinstance(conn, sqlite3.Connection):
        return conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                            (TABLE,)).fetchone() is not None
    from sqlalchemy import inspect
    return TABLE in inspect(conn).get_table_names()


def refusal(conn):
    """The message that stops the upgrade when two SSO providers share a type, else None. Reads only."""
    if not _has_table(conn):
        return None
    if isinstance(conn, sqlite3.Connection):
        return _refusal_text(conn.execute(_SHARED).fetchall())
    from sqlalchemy import text
    return _refusal_text([tuple(r) for r in conn.execute(text(_SHARED))])


def blank_names(rows):
    """{id: new name} for the (id, name, provider_type) rows whose name is blank."""
    taken = {name for _id, name, _type in rows if name and name.strip()}
    renamed = {}
    for provider_id, name, provider_type in sorted(rows, key=lambda row: row[0]):
        if not (name and name.strip()):
            renamed[provider_id] = first_free(provider_type, taken)
            taken.add(renamed[provider_id])
    return renamed


def _name_blank_providers(conn):
    select = f"SELECT id, name, provider_type FROM {TABLE}"
    if isinstance(conn, sqlite3.Connection):
        renamed = blank_names(conn.execute(select).fetchall())
        conn.executemany(f"UPDATE {TABLE} SET name = ? WHERE id = ?",
                         [(name, provider_id) for provider_id, name in renamed.items()])
    else:
        from sqlalchemy import text
        renamed = blank_names([tuple(r) for r in conn.execute(text(select))])
        for provider_id, name in renamed.items():
            conn.execute(text(f"UPDATE {TABLE} SET name = :name WHERE id = :id"),
                         {'name': name, 'id': provider_id})
    for provider_id, name in renamed.items():
        logger.info(f"[165] SSO provider #{provider_id} had a blank name, now {name!r}")


def upgrade(conn):
    if not _has_table(conn):
        if isinstance(conn, sqlite3.Connection):
            conn.commit()
        return
    message = refusal(conn)
    if message:
        raise RuntimeError(message)
    if isinstance(conn, sqlite3.Connection):
        if COLUMN not in {row[1] for row in conn.execute(f"PRAGMA table_info({TABLE})")}:
            conn.execute(DDL)
            logger.info("[165] LDAP group search base (SQLite)")
        conn.execute(INDEX)
        _name_blank_providers(conn)
        conn.commit()
        return
    from sqlalchemy import inspect, text
    if COLUMN not in {c['name'] for c in inspect(conn).get_columns(TABLE)}:
        conn.execute(text(DDL))
        logger.info("[165] LDAP group search base (PostgreSQL)")
    conn.execute(text(INDEX))
    _name_blank_providers(conn)


def downgrade(conn):
    """No downgrade: 2.254 ignores the column and keeps one provider per type."""
