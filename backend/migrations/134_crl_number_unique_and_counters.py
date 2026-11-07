"""Migration 134: one CRL per (CA, number), and the number each CRL issuer reached.

RFC 5280 §5.2.3: two CRLs of one issuer MUST NOT share a number. The unique
index only existed where migration 004 ran; installations built by create_all
lacked it. Duplicates are removed first, the most recent row of each kept.
crl_number_counters then records the highest number per issuer (name + key),
the floor that outlives a deleted CA and travels in the archive.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

# The names SQLAlchemy gives the models' indexes, so create_all and this agree
_UNIQUE_NUMBER = "CREATE UNIQUE INDEX IF NOT EXISTS uix_crl_ca_number ON crl_metadata (ca_id, crl_number)"
_DEDUPE = ("DELETE FROM crl_metadata WHERE id NOT IN "
           "(SELECT MAX(id) FROM crl_metadata GROUP BY ca_id, crl_number)")
_COUNTER_INDEX = ("CREATE UNIQUE INDEX IF NOT EXISTS ix_crl_number_counters_issuer_key "
                  "ON crl_number_counters (issuer_key)")
_HIGHEST = ("SELECT ca.crt, MAX(m.crl_number) FROM certificate_authorities ca "
            "JOIN crl_metadata m ON m.ca_id = ca.id GROUP BY ca.id, ca.crt")


def _counter_table(pk, ts):
    return f"""
    CREATE TABLE IF NOT EXISTS crl_number_counters (
        id {pk},
        issuer_key VARCHAR(64) NOT NULL,
        last_number INTEGER NOT NULL,
        updated_at {ts}
    )"""


def _floors(rows):
    """{issuer key: highest number} over every CA record of that issuer."""
    from utils.crl_issuer import crl_issuer_key_of_stored
    floors = {}
    for crt, highest in rows:
        key = crl_issuer_key_of_stored(crt)
        if key is not None and highest is not None:
            floors[key] = max(floors.get(key, 0), int(highest))
    return floors


def _upgrade_sqlite(conn):
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    conn.execute(_counter_table('INTEGER PRIMARY KEY AUTOINCREMENT', 'DATETIME'))
    conn.execute(_COUNTER_INDEX)
    if 'crl_metadata' in tables:
        removed = conn.execute(_DEDUPE).rowcount
        conn.execute(_UNIQUE_NUMBER)
        if removed:
            logger.info("Migration 134: removed %s CRL row(s) sharing a number", removed)
        if 'certificate_authorities' in tables:
            for key, number in _floors(conn.execute(_HIGHEST).fetchall()).items():
                conn.execute("INSERT OR IGNORE INTO crl_number_counters (issuer_key, last_number, "
                             "updated_at) VALUES (?, 0, CURRENT_TIMESTAMP)", (key,))
                conn.execute("UPDATE crl_number_counters SET last_number = ? "
                             "WHERE issuer_key = ? AND last_number < ?", (number, key, number))
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    tables = set(inspect(conn).get_table_names())
    conn.execute(text(_counter_table('SERIAL PRIMARY KEY', 'TIMESTAMP WITHOUT TIME ZONE')))
    conn.execute(text(_COUNTER_INDEX))
    if 'crl_metadata' in tables:
        removed = conn.execute(text(_DEDUPE)).rowcount
        conn.execute(text(_UNIQUE_NUMBER))
        if removed:
            logger.info("Migration 134: removed %s CRL row(s) sharing a number", removed)
        if 'certificate_authorities' in tables:
            for key, number in _floors(conn.execute(text(_HIGHEST)).fetchall()).items():
                conn.execute(text(
                    "INSERT INTO crl_number_counters (issuer_key, last_number, updated_at) "
                    "VALUES (:k, 0, CURRENT_TIMESTAMP AT TIME ZONE 'UTC') "
                    "ON CONFLICT (issuer_key) DO NOTHING"), {'k': key})
                conn.execute(text(
                    "UPDATE crl_number_counters SET last_number = :n "
                    "WHERE issuer_key = :k AND last_number < :n"), {'k': key, 'n': number})


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    pass
