"""
Migration 013: Create ACME Domains table
Maps domains to DNS providers for ACME Proxy functionality.
"""


def upgrade(conn):
    """Create acme_domains table"""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS acme_domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain VARCHAR(255) NOT NULL UNIQUE,
            dns_provider_id INTEGER NOT NULL REFERENCES dns_providers(id),
            is_wildcard_allowed BOOLEAN DEFAULT 1,
            auto_approve BOOLEAN DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME,
            created_by VARCHAR(80)
        )
    """)
    
    # Index for faster lookups
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_acme_domains_domain 
        ON acme_domains(domain)
    """)
    
    conn.commit()
    print("  ✓ Created acme_domains table")


def downgrade(conn):
    """Drop acme_domains table"""
    conn.execute("DROP TABLE IF EXISTS acme_domains")
    conn.commit()
