"""
Migration 004: Create webauthn_credentials table
For FIDO2/U2F hardware security keys
"""

def upgrade(db_path):
    """Add webauthn_credentials table"""
    import sqlite3
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='webauthn_credentials'")
        if cursor.fetchone():
            print("⏭️  Table webauthn_credentials already exists")
            return
        
        # Create table
        cursor.execute("""
            CREATE TABLE webauthn_credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                credential_id BLOB UNIQUE NOT NULL,
                public_key BLOB NOT NULL,
                sign_count INTEGER DEFAULT 0 NOT NULL,
                name VARCHAR(128),
                aaguid VARCHAR(36),
                transports TEXT,
                is_backup_eligible BOOLEAN DEFAULT 0,
                is_backup_device BOOLEAN DEFAULT 0,
                user_verified BOOLEAN DEFAULT 0,
                enabled BOOLEAN DEFAULT 1 NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        
        # Create indexes
        cursor.execute("CREATE INDEX idx_webauthn_credential_id ON webauthn_credentials(credential_id)")
        cursor.execute("CREATE INDEX idx_webauthn_user_id ON webauthn_credentials(user_id)")
        
        conn.commit()
        print("✅ Created webauthn_credentials table with indexes")
    
    except Exception as e:
        conn.rollback()
        print(f"❌ Migration 004 failed: {e}")
        raise
    
    finally:
        conn.close()

def downgrade(db_path):
    """Remove webauthn_credentials table"""
    import sqlite3
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("DROP TABLE IF EXISTS webauthn_credentials")
        conn.commit()
        print("✅ Dropped webauthn_credentials table")
    
    except Exception as e:
        conn.rollback()
        print(f"❌ Downgrade 004 failed: {e}")
        raise
    
    finally:
        conn.close()
