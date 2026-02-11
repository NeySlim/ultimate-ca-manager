"""Add updated_at column to groups table"""

def upgrade(conn):
    cursor = conn.execute("PRAGMA table_info(groups)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'updated_at' not in columns:
        conn.execute("ALTER TABLE groups ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP")
        conn.execute("UPDATE groups SET updated_at = created_at WHERE updated_at IS NULL")
        conn.commit()

def downgrade(conn):
    pass  # SQLite cannot drop columns
