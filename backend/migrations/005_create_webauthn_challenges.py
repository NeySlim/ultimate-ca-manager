"""
Migration 005: Create webauthn_challenges table
For temporary WebAuthn registration/authentication challenges
"""

def upgrade(db_path):
    """Add webauthn_challenges table"""
    import sqlite3
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='webauthn_challenges'")
        if cursor.fetchone():
            print("⏭️  Table webauthn_challenges already exists")
            return
        
        cursor.execute("""
            CREATE TABLE webauthn_challenges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                challenge VARCHAR(128) UNIQUE NOT NULL,
                challenge_type VARCHAR(20) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                used BOOLEAN DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        cursor.execute("CREATE INDEX idx_webauthn_challenge ON webauthn_challenges(challenge)")
        
        conn.commit()
        print("✅ Created webauthn_challenges table")
    
    except Exception as e:
        conn.rollback()
        print(f"❌ Migration 005 failed: {e}")
        raise
    finally:
        conn.close()

def downgrade(db_path):
    import sqlite3
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS webauthn_challenges")
    conn.commit()
    conn.close()
    print("✅ Dropped webauthn_challenges table")
