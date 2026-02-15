"""Add smtp_content_type column to smtp_config table"""

def upgrade(conn):
    cursor = conn.execute("PRAGMA table_info(smtp_config)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'smtp_content_type' not in columns:
        conn.execute("ALTER TABLE smtp_config ADD COLUMN smtp_content_type VARCHAR(10) DEFAULT 'html'")
        conn.commit()

def downgrade(conn):
    pass
