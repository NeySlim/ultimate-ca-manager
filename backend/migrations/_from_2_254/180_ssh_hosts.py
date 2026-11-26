"""Upgrade step 180: enrolled SSH hosts and their enrollment tokens (issue #451).

``ssh_host_enrollment_tokens`` keeps the SHA-256 of single-use tokens, ``ssh_hosts`` the servers
enrolled with a host CA and the certificate each presents. Both backends; idempotent.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

TABLES = (
    "CREATE TABLE IF NOT EXISTS ssh_host_enrollment_tokens ("
    "id {serial} PRIMARY KEY, "
    "ssh_ca_id INTEGER NOT NULL REFERENCES ssh_cas (id) ON DELETE CASCADE, "
    "token_hash VARCHAR(64) NOT NULL UNIQUE, token_prefix VARCHAR(16) NOT NULL, descr VARCHAR(255), "
    "principals TEXT NOT NULL, validity_seconds INTEGER, renew_percent INTEGER NOT NULL DEFAULT 30, "
    "expires_at {timestamp} NOT NULL, used_at {timestamp}, used_by_host_id INTEGER, revoked_at {timestamp}, "
    "created_at {timestamp} NOT NULL, created_by VARCHAR(80))",
    "CREATE TABLE IF NOT EXISTS ssh_hosts ("
    "id {serial} PRIMARY KEY, refid VARCHAR(36) NOT NULL UNIQUE, "
    "ssh_ca_id INTEGER NOT NULL REFERENCES ssh_cas (id) ON DELETE CASCADE, "
    "name VARCHAR(255) NOT NULL, principals TEXT NOT NULL, public_key TEXT NOT NULL, "
    "key_type VARCHAR(20) NOT NULL, fingerprint VARCHAR(100) NOT NULL, validity_seconds INTEGER, "
    "renew_percent INTEGER NOT NULL DEFAULT 30, "
    "certificate_id INTEGER REFERENCES ssh_certificates (id) ON DELETE SET NULL, "
    "auto_renew BOOLEAN NOT NULL DEFAULT {true}, revoked_at {timestamp}, enrolled_at {timestamp} NOT NULL, "
    "enrolled_ip VARCHAR(45), token_id INTEGER, last_renewed_at {timestamp}, last_seen_at {timestamp}, "
    "last_krl_sync_at {timestamp}, challenge VARCHAR(64), challenge_expires_at {timestamp})",
)
INDEXES = (
    "CREATE INDEX IF NOT EXISTS ix_ssh_host_enrollment_tokens_ssh_ca_id ON ssh_host_enrollment_tokens (ssh_ca_id)",
    "CREATE INDEX IF NOT EXISTS ix_ssh_hosts_ssh_ca_id ON ssh_hosts (ssh_ca_id)",
    "CREATE INDEX IF NOT EXISTS ix_ssh_hosts_fingerprint ON ssh_hosts (fingerprint)",
)


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        for ddl in TABLES:
            conn.execute(ddl.format(serial='INTEGER', timestamp='DATETIME', true='1'))
        for statement in INDEXES:
            conn.execute(statement)
        conn.commit()
        logger.info("[180] ssh_hosts, ssh_host_enrollment_tokens (SQLite)")
        return
    from sqlalchemy import text
    for ddl in TABLES:
        conn.execute(text(ddl.format(serial='SERIAL', timestamp='TIMESTAMP WITHOUT TIME ZONE', true='true')))
    for statement in INDEXES:
        conn.execute(text(statement))
    logger.info("[180] ssh_hosts, ssh_host_enrollment_tokens (PostgreSQL)")


def downgrade(conn):
    """No downgrade: unused tables are harmless."""
    pass
