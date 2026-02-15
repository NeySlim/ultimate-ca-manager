"""
Migration 029: Add email_text_template column to smtp_config
Stores custom plain text template for email notifications
"""

def upgrade(conn):
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(smtp_config)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if 'email_text_template' not in columns:
        cursor.execute("ALTER TABLE smtp_config ADD COLUMN email_text_template TEXT DEFAULT NULL")
    
    conn.commit()


def downgrade(conn):
    pass
