"""
Migration 018: Add SSH Certificate Authority tables

Creates ssh_cas and ssh_certificates tables for OpenSSH certificate management.
SSH CAs are separate from X.509 CAs — they use the OpenSSH certificate format.
"""
import logging

logger = logging.getLogger(__name__)

UPGRADE_SQL = """
CREATE TABLE IF NOT EXISTS ssh_cas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    refid VARCHAR(36) NOT NULL UNIQUE,
    descr VARCHAR(255) NOT NULL,
    ca_type VARCHAR(10) NOT NULL,
    public_key TEXT NOT NULL,
    private_key TEXT NOT NULL,
    key_type VARCHAR(20) NOT NULL,
    fingerprint VARCHAR(100) NOT NULL,
    serial_counter INTEGER NOT NULL DEFAULT 0,
    default_ttl INTEGER DEFAULT 86400,
    max_ttl INTEGER DEFAULT 0,
    default_extensions TEXT,
    allowed_principals TEXT,
    comment TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(80),
    owner_group_id INTEGER REFERENCES groups(id)
);

CREATE INDEX IF NOT EXISTS idx_ssh_cas_refid ON ssh_cas(refid);
CREATE INDEX IF NOT EXISTS idx_ssh_cas_ca_type ON ssh_cas(ca_type);
CREATE INDEX IF NOT EXISTS idx_ssh_cas_fingerprint ON ssh_cas(fingerprint);

CREATE TABLE IF NOT EXISTS ssh_certificates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    refid VARCHAR(36) NOT NULL UNIQUE,
    descr VARCHAR(255),
    ssh_ca_id INTEGER NOT NULL REFERENCES ssh_cas(id),
    cert_type VARCHAR(10) NOT NULL,
    key_id VARCHAR(255) NOT NULL,
    public_key TEXT NOT NULL,
    certificate TEXT NOT NULL,
    principals TEXT NOT NULL,
    serial INTEGER NOT NULL,
    valid_from DATETIME NOT NULL,
    valid_to DATETIME NOT NULL,
    key_type VARCHAR(20) NOT NULL,
    fingerprint VARCHAR(100) NOT NULL,
    extensions TEXT,
    critical_options TEXT,
    revoked BOOLEAN DEFAULT 0,
    revoked_at DATETIME,
    revoke_reason VARCHAR(255),
    source VARCHAR(20) DEFAULT 'web',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(80),
    owner_group_id INTEGER REFERENCES groups(id)
);

CREATE INDEX IF NOT EXISTS idx_ssh_certs_refid ON ssh_certificates(refid);
CREATE INDEX IF NOT EXISTS idx_ssh_certs_ca_id ON ssh_certificates(ssh_ca_id);
CREATE INDEX IF NOT EXISTS idx_ssh_certs_cert_type ON ssh_certificates(cert_type);
CREATE INDEX IF NOT EXISTS idx_ssh_certs_serial ON ssh_certificates(serial);
CREATE INDEX IF NOT EXISTS idx_ssh_certs_valid_to ON ssh_certificates(valid_to);
CREATE INDEX IF NOT EXISTS idx_ssh_certs_fingerprint ON ssh_certificates(fingerprint);
CREATE INDEX IF NOT EXISTS idx_ssh_certs_revoked ON ssh_certificates(revoked);
"""


def upgrade(conn):
    """Create SSH CA and SSH certificate tables."""
    conn.executescript(UPGRADE_SQL)
    conn.commit()
    logger.info("Created ssh_cas and ssh_certificates tables")


def downgrade(conn):
    """Drop SSH tables."""
    conn.execute("DROP TABLE IF EXISTS ssh_certificates")
    conn.execute("DROP TABLE IF EXISTS ssh_cas")
    conn.commit()
    logger.info("Dropped ssh_cas and ssh_certificates tables")
