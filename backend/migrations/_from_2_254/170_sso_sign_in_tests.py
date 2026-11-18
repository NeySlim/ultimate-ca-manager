"""Upgrade step 170: the OIDC and SAML sign-in tests.

``pro_sso_sign_in_tests`` holds a test's transaction while the IdP answers, then its report,
for minutes; shared by every node. Created on SQLite too.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

DDL = ("CREATE TABLE IF NOT EXISTS pro_sso_sign_in_tests ("
       "id {serial} PRIMARY KEY, token VARCHAR(64) NOT NULL, provider_id INTEGER NOT NULL, "
       "user_id INTEGER NOT NULL, protocol VARCHAR(16) NOT NULL, "
       "transaction_hash VARCHAR(64) NOT NULL, browser_hash VARCHAR(64) NOT NULL, secret TEXT, "
       "state VARCHAR(16) NOT NULL, report TEXT, created_at {timestamp} NOT NULL, "
       "expires_at {timestamp} NOT NULL, finished_at {timestamp}, "
       "CONSTRAINT uq_pro_sso_sign_in_tests_token UNIQUE (token), "
       "CONSTRAINT uq_pro_sso_sign_in_tests_transaction UNIQUE (transaction_hash))")
INDEXES = (
    "CREATE INDEX IF NOT EXISTS ix_pro_sso_sign_in_tests_expires_at "
    "ON pro_sso_sign_in_tests (expires_at)",
)


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        conn.execute(DDL.format(serial='INTEGER', timestamp='DATETIME'))
        for statement in INDEXES:
            conn.execute(statement)
        conn.commit()
        logger.info("[170] pro_sso_sign_in_tests (SQLite)")
        return
    from sqlalchemy import text
    conn.execute(text(DDL.format(serial='SERIAL', timestamp='TIMESTAMP WITHOUT TIME ZONE')))
    for statement in INDEXES:
        conn.execute(text(statement))
    logger.info("[170] pro_sso_sign_in_tests (PostgreSQL)")


def downgrade(conn):
    """No downgrade: an unused table is harmless."""
    pass
