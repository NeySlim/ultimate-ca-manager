"""
Migration 009: Add password reset and force change fields

Adds:
- force_password_change: Boolean to force password change on next login
- password_reset_token: Token for forgot password flow
- password_reset_expires: Token expiry timestamp
"""

def upgrade(conn):
    """Add password management columns to users table"""
    cursor = conn.cursor()
    
    # Check existing columns
    cursor.execute("PRAGMA table_info(users)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    
    columns_to_add = {
        'force_password_change': 'BOOLEAN DEFAULT 0',
        'password_reset_token': 'VARCHAR(128)',
        'password_reset_expires': 'DATETIME',
    }
    
    for col_name, col_def in columns_to_add.items():
        if col_name not in existing_columns:
            try:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}")
                print(f"  ✓ Added column: {col_name}")
            except Exception as e:
                print(f"  - Column {col_name} may already exist: {e}")
    
    conn.commit()


def downgrade(conn):
    """SQLite doesn't support DROP COLUMN easily - skip"""
    pass
