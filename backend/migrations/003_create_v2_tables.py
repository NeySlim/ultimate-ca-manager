"""
Migration 003: Create all v2.0 tables
Creates tables that may be missing when upgrading from v1.8.x
Uses CREATE TABLE IF NOT EXISTS to be idempotent.
"""


MIGRATION_SQL = """
-- Groups system
CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(80) NOT NULL UNIQUE,
    description TEXT,
    permissions TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS group_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(group_id, user_id)
);

-- User sessions
CREATE TABLE IF NOT EXISTS user_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id VARCHAR(255) NOT NULL UNIQUE,
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_active DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME
);

-- Approval workflow
CREATE TABLE IF NOT EXISTS approval_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_type VARCHAR(50) NOT NULL,
    requester_id INTEGER REFERENCES users(id),
    target_id INTEGER,
    target_type VARCHAR(50),
    status VARCHAR(20) DEFAULT 'pending',
    data TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    reviewed_at DATETIME,
    reviewer_id INTEGER REFERENCES users(id),
    review_comment TEXT
);

-- Certificate templates (aligned with CertificateTemplate model)
CREATE TABLE IF NOT EXISTS certificate_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    template_type VARCHAR(50) NOT NULL DEFAULT 'custom',
    key_type VARCHAR(20) DEFAULT 'RSA-2048',
    validity_days INTEGER DEFAULT 397,
    digest VARCHAR(20) DEFAULT 'sha256',
    dn_template TEXT,
    extensions_template TEXT NOT NULL DEFAULT '{}',
    is_system BOOLEAN DEFAULT 0,
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(80),
    updated_at DATETIME,
    updated_by VARCHAR(80)
);

-- Certificate policies  
CREATE TABLE IF NOT EXISTS certificate_policies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    oid VARCHAR(50),
    cps_uri VARCHAR(500),
    user_notice TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Trusted certificates (for chain building)
CREATE TABLE IF NOT EXISTS trusted_certificates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(255),
    certificate_pem TEXT NOT NULL,
    subject TEXT,
    issuer TEXT,
    serial_number VARCHAR(100),
    not_before DATETIME,
    not_after DATETIME,
    fingerprint_sha256 VARCHAR(64) UNIQUE,
    source VARCHAR(50),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- API Keys (if not created by migration 001)
CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL,
    key_hash VARCHAR(255) NOT NULL,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    permissions TEXT,
    expires_at DATETIME,
    last_used DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    active BOOLEAN DEFAULT 1
);
"""


def upgrade(conn):
    """Create all v2.0 tables"""
    conn.executescript(MIGRATION_SQL)
    conn.commit()


def downgrade(conn):
    """Drop v2.0 specific tables (dangerous!)"""
    pass
