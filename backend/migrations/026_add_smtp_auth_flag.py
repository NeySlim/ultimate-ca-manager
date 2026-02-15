"""Add smtp_auth column to smtp_config table"""

def upgrade(conn):
    cursor = conn.execute("PRAGMA table_info(smtp_config)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'smtp_auth' not in columns:
        conn.execute("ALTER TABLE smtp_config ADD COLUMN smtp_auth BOOLEAN DEFAULT 1")
        conn.commit()

def downgrade(conn):
    pass  # SQLite doesn't support DROP COLUMN easily
