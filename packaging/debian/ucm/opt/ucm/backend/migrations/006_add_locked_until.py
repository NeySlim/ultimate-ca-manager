"""
Migration: Add locked_until column to users table for persistent account lockout
"""

MIGRATION_SQL = """
-- Add locked_until column if not exists (SQLite workaround)
-- Check if column exists first by querying pragma
-- This uses CREATE TABLE IF NOT EXISTS pattern instead

-- For SQLite, we check if column exists and add if not
-- This is handled by the migration runner which catches "duplicate column" errors
ALTER TABLE users ADD COLUMN locked_until DATETIME;
"""

def upgrade(db_path):
    """Add locked_until column to users table"""
    import sqlite3
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'locked_until' in columns:
            print("✓ Column locked_until already exists")
            return
        
        cursor.execute("ALTER TABLE users ADD COLUMN locked_until DATETIME")
        conn.commit()
        print("✓ Added locked_until column to users table")
        
    except Exception as e:
        if "duplicate column" in str(e).lower():
            print("✓ Column locked_until already exists")
        else:
            raise
    finally:
        conn.close()

def downgrade(db_path):
    """Remove locked_until column (SQLite doesn't support DROP COLUMN easily)"""
    print("Note: SQLite doesn't support DROP COLUMN. Column will remain but be unused.")
