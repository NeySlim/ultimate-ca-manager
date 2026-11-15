"""Upgrade step 162: a 2.x TSA that signs with its CA certificate keeps signing that way.

3.0 reads an absent ``tsa_require_dedicated_cert`` as true (RFC 3161 §2.3 dedicated signer).
A 2.x install whose TSA is on (no ``tsa_enabled`` row, or one 2.x read as true), points at an
existing CA and has no dedicated signer gets the key written ``false``, over a key row 2.x read
as "no" (any value but lower case ``true``); nothing else is written.
"""
import logging
import sqlite3

from services.tsa_upgrade import KEY, READ, ca_signer_refid_kept

logger = logging.getLogger(__name__)
pg_compatible = True

SETTINGS = 'system_config'
CAS = 'certificate_authorities'


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if not {SETTINGS, CAS} <= tables:
            return
        settings = dict(conn.execute(
            f"SELECT key, value FROM {SETTINGS} WHERE key IN ({','.join('?' * len(READ))})", READ))
        refid = ca_signer_refid_kept(settings)
        if refid and conn.execute(f"SELECT 1 FROM {CAS} WHERE refid = ?", (refid,)).fetchone():
            conn.execute(f"UPDATE {SETTINGS} SET value = 'false' WHERE key = ?" if KEY in settings
                         else f"INSERT INTO {SETTINGS} (key, value) VALUES (?, 'false')", (KEY,))
            logger.info("[162] the TSA keeps signing with its CA certificate (SQLite)")
        conn.commit()
        return
    from sqlalchemy import bindparam, inspect, text
    if not {SETTINGS, CAS} <= set(inspect(conn).get_table_names()):
        return
    settings = dict(conn.execute(
        text(f"SELECT key, value FROM {SETTINGS} WHERE key IN :keys").bindparams(
            bindparam('keys', expanding=True)), {'keys': list(READ)}).fetchall())
    refid = ca_signer_refid_kept(settings)
    if refid and conn.execute(text(f"SELECT 1 FROM {CAS} WHERE refid = :r"), {'r': refid}).first():
        conn.execute(text(f"UPDATE {SETTINGS} SET value = 'false' WHERE key = :k" if KEY in settings
                          else f"INSERT INTO {SETTINGS} (key, value) VALUES (:k, 'false')"), {'k': KEY})
        logger.info("[162] the TSA keeps signing with its CA certificate (PostgreSQL)")


def downgrade(conn):
    """No downgrade: 2.254 reads the explicit false as its own default."""
