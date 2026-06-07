"""Migration 039: ACME Terms of Service defaults.

Seeds default English ToS if the SystemConfig key doesn't exist yet.
"""
import logging
import sqlite3
import json

logger = logging.getLogger(__name__)
pg_compatible = True

DEFAULT_TOS = {
    "title": "Terms of Service",
    "body": "By using this ACME server, you agree to these terms.\n\n1. No abusive or unlawful use.\n2. Rate limits apply — excessive requests may be temporarily blocked.\n3. Accounts that violate these terms may be revoked."
}

def _seed_sqlite(conn):
    existing = conn.execute(
        "SELECT COUNT(*) FROM system_config WHERE key='acme.terms_of_service'"
    ).fetchone()[0]
    if existing == 0:
        conn.execute(
            "INSERT INTO system_config (key, value, description, created_at) "
            "VALUES ('acme.terms_of_service', ?, 'ACME Terms of Service (title + body, JSON)', datetime('now'))",
            (json.dumps(DEFAULT_TOS),)
        )
        conn.commit()
        logger.info("[039] seeded default ACME ToS (SQLite)")

def _seed_pg(conn):
    from sqlalchemy import text, inspect
    insp = inspect(conn)
    has_key = conn.execute(
        text("SELECT COUNT(*) FROM system_config WHERE key = 'acme.terms_of_service'")
    ).scalar()
    if has_key == 0:
        conn.execute(
            text("INSERT INTO system_config (key, value, description, created_at) "
                 "VALUES ('acme.terms_of_service', :val, 'ACME Terms of Service (title + body, JSON)', NOW())"),
            {"val": json.dumps(DEFAULT_TOS)}
        )
        logger.info("[039] seeded default ACME ToS (PostgreSQL)")

def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _seed_sqlite(conn)
    else:
        _seed_pg(conn)

def downgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        conn.execute(
            "DELETE FROM system_config WHERE key='acme.terms_of_service'"
        )
        conn.commit()
    else:
        conn.execute(
            text("DELETE FROM system_config WHERE key = 'acme.terms_of_service'")
        )
