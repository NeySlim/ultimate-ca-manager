"""
Migration 023: Add issuing_ca_id to acme_domains table
Allows per-domain CA selection for ACME certificate signing.
"""


def upgrade(conn):
    """Add issuing_ca_id column to acme_domains"""
    # Check if column already exists
    cursor = conn.execute("PRAGMA table_info(acme_domains)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if 'issuing_ca_id' not in columns:
        conn.execute("""
            ALTER TABLE acme_domains 
            ADD COLUMN issuing_ca_id INTEGER REFERENCES certificate_authorities(id)
        """)
        conn.commit()
        print("  ✓ Added issuing_ca_id column to acme_domains")
    else:
        print("  ✓ issuing_ca_id column already exists")


def downgrade(conn):
    """Remove issuing_ca_id column (SQLite doesn't support DROP COLUMN easily)"""
    pass
