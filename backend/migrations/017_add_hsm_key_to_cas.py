"""
Migration 017: Add HSM key reference to Certificate Authorities

Adds hsm_key_id foreign key to certificate_authorities table,
allowing CAs to use HSM-backed private keys for signing.
"""


def upgrade(conn):
    """Add hsm_key_id column to certificate_authorities table"""
    
    # Check if column already exists
    cursor = conn.execute("PRAGMA table_info(certificate_authorities)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if 'hsm_key_id' not in columns:
        conn.execute("""
            ALTER TABLE certificate_authorities
            ADD COLUMN hsm_key_id INTEGER REFERENCES hsm_keys(id)
        """)
        print("  ✓ Added hsm_key_id to certificate_authorities")
    else:
        print("  ✓ hsm_key_id already exists (skipped)")
    
    conn.commit()


def downgrade(conn):
    """Remove hsm_key_id column - SQLite doesn't support DROP COLUMN easily"""
    # SQLite < 3.35 doesn't support DROP COLUMN
    # For older versions, would need to recreate table
    print("  ⚠ DROP COLUMN not supported in older SQLite - manual intervention needed")
    conn.commit()
