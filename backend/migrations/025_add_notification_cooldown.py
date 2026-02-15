"""Add cooldown_hours column to notification_config"""


def upgrade(conn):
    # Check if column already exists
    cursor = conn.execute("PRAGMA table_info(notification_config)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'cooldown_hours' not in columns:
        conn.execute("ALTER TABLE notification_config ADD COLUMN cooldown_hours INTEGER DEFAULT 24")
        conn.commit()


def downgrade(conn):
    pass  # SQLite doesn't support DROP COLUMN easily
