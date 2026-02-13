"""
Migration 024: Create acme_local_domains table
Maps domains to specific CAs for the Local ACME server.
"""

def upgrade(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS acme_local_domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain VARCHAR(255) NOT NULL UNIQUE,
            issuing_ca_id INTEGER NOT NULL,
            auto_approve BOOLEAN DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_by VARCHAR(80),
            FOREIGN KEY (issuing_ca_id) REFERENCES certificate_authorities(id)
        );
        CREATE INDEX IF NOT EXISTS idx_acme_local_domains_domain ON acme_local_domains(domain);
    """)
    conn.commit()


def downgrade(conn):
    conn.execute("DROP TABLE IF EXISTS acme_local_domains")
    conn.commit()
