"""Add Delta CRL support fields"""

def upgrade(conn):
    import sqlite3
    cursor = conn.cursor()
    
    # Add delta CRL fields to crl_metadata
    try:
        cursor.execute("ALTER TABLE crl_metadata ADD COLUMN is_delta BOOLEAN DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE crl_metadata ADD COLUMN base_crl_number INTEGER")
    except sqlite3.OperationalError:
        pass
    
    # Add unique constraint on (ca_id, crl_number) to prevent race conditions
    try:
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS uix_crl_ca_number ON crl_metadata(ca_id, crl_number)")
    except sqlite3.OperationalError:
        pass
    
    # Add delta CRL settings to CA
    try:
        cursor.execute("ALTER TABLE certificate_authorities ADD COLUMN delta_crl_enabled BOOLEAN DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE certificate_authorities ADD COLUMN delta_crl_interval INTEGER DEFAULT 4")
    except sqlite3.OperationalError:
        pass
    
    conn.commit()

def downgrade(conn):
    pass  # SQLite doesn't support DROP COLUMN easily
