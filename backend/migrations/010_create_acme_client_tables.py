"""
Migration 010: Create ACME Client tables for Let's Encrypt integration
Creates dns_providers and acme_client_orders tables for the ACME client feature.
Uses CREATE TABLE IF NOT EXISTS to be idempotent.
"""


MIGRATION_SQL = """
-- DNS Providers for automatic DNS-01 challenge validation
CREATE TABLE IF NOT EXISTS dns_providers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL,
    provider_type VARCHAR(50) NOT NULL DEFAULT 'manual',
    credentials TEXT,
    is_default BOOLEAN DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME,
    created_by VARCHAR(80)
);

-- ACME Client Orders for Let's Encrypt certificate requests
CREATE TABLE IF NOT EXISTS acme_client_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domains TEXT NOT NULL,
    email VARCHAR(255) NOT NULL,
    environment VARCHAR(20) NOT NULL DEFAULT 'staging',
    challenge_type VARCHAR(20) NOT NULL DEFAULT 'dns-01',
    dns_provider_id INTEGER REFERENCES dns_providers(id),
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    order_url TEXT,
    finalize_url TEXT,
    certificate_url TEXT,
    challenges_data TEXT,
    error_message TEXT,
    certificate_id INTEGER REFERENCES certificates(id),
    auto_renew BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME,
    expires_at DATETIME,
    created_by VARCHAR(80)
);

-- Index for faster lookups
CREATE INDEX IF NOT EXISTS idx_acme_client_orders_status ON acme_client_orders(status);
CREATE INDEX IF NOT EXISTS idx_acme_client_orders_environment ON acme_client_orders(environment);
"""


def upgrade(conn):
    """Create ACME client tables"""
    conn.executescript(MIGRATION_SQL)
    conn.commit()


def downgrade(conn):
    """Drop ACME client tables (dangerous!)"""
    conn.execute("DROP TABLE IF EXISTS acme_client_orders")
    conn.execute("DROP TABLE IF EXISTS dns_providers")
    conn.commit()
