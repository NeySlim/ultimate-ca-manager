"""
Migration 028: Add email_template column to smtp_config
Stores custom HTML template for all email notifications
"""

def upgrade(conn):
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(smtp_config)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if 'email_template' not in columns:
        cursor.execute("ALTER TABLE smtp_config ADD COLUMN email_template TEXT DEFAULT NULL")
    
    conn.commit()


def downgrade(conn):
    pass  # SQLite doesn't support DROP COLUMN easily
