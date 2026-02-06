"""
Migration 002: Upgrade users table from v1.8.x to v2.0
Adds TOTP/MFA columns and login tracking.
"""


def upgrade(conn):
    """Add missing columns to users table for v2.0"""
    # Get current columns
    cursor = conn.execute("PRAGMA table_info(users)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    
    # Columns to add with their definitions
    new_columns = [
        ("totp_secret", "TEXT"),
        ("totp_confirmed", "INTEGER DEFAULT 0"),
        ("backup_codes", "TEXT"),
        ("login_count", "INTEGER DEFAULT 0"),
        ("failed_logins", "INTEGER DEFAULT 0"),
        ("locked_until", "DATETIME"),
    ]
    
    for col_name, col_def in new_columns:
        if col_name not in existing_columns:
            try:
                conn.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}")
                print(f"    Added column: {col_name}")
            except Exception as e:
                if "duplicate column" not in str(e).lower():
                    raise
    
    conn.commit()


def downgrade(conn):
    """SQLite doesn't support DROP COLUMN easily, skip"""
    pass
