"""Add missing columns to trusted_certificates table"""

def upgrade(conn):
    cursor = conn.execute("PRAGMA table_info(trusted_certificates)")
    columns = [row[1] for row in cursor.fetchall()]
    
    additions = {
        'description': "ALTER TABLE trusted_certificates ADD COLUMN description TEXT",
        'fingerprint_sha1': "ALTER TABLE trusted_certificates ADD COLUMN fingerprint_sha1 VARCHAR(40)",
        'purpose': "ALTER TABLE trusted_certificates ADD COLUMN purpose VARCHAR(100)",
        'added_by': "ALTER TABLE trusted_certificates ADD COLUMN added_by VARCHAR(80)",
        'added_at': "ALTER TABLE trusted_certificates ADD COLUMN added_at DATETIME DEFAULT CURRENT_TIMESTAMP",
        'notes': "ALTER TABLE trusted_certificates ADD COLUMN notes TEXT",
    }
    
    for col, sql in additions.items():
        if col not in columns:
            conn.execute(sql)
    
    # Backfill added_at from created_at if it exists
    if 'created_at' in columns:
        conn.execute("UPDATE trusted_certificates SET added_at = created_at WHERE added_at IS NULL")
    
    conn.commit()

def downgrade(conn):
    pass
