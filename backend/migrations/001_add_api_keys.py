"""
Database Migration: Add API Keys table
Date: 2026-01-18
"""

import sqlite3
import sys
import os

MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    key_hash VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    permissions TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    last_used_at TIMESTAMP,
    is_active BOOLEAN DEFAULT 1,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_active ON api_keys(is_active);
"""

ROLLBACK_SQL = """
DROP INDEX IF EXISTS idx_api_keys_active;
DROP INDEX IF EXISTS idx_api_keys_user;
DROP INDEX IF EXISTS idx_api_keys_hash;
DROP TABLE IF EXISTS api_keys;
"""

def run_migration(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.executescript(MIGRATION_SQL)
        conn.commit()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='api_keys'")
        if cursor.fetchone():
            print("✅ Migration successful - Table api_keys created")
            return True
        return False
    except Exception as e:
        print(f"❌ Migration error: {e}")
        return False
    finally:
        conn.close()

if __name__ == '__main__':
    db_path = '/opt/ucm/backend/data/ucm.db'
    if os.path.exists('/root/ucm-src/backend/data/ucm.db'):
        db_path = '/root/ucm-src/backend/data/ucm.db'
    run_migration(db_path)
