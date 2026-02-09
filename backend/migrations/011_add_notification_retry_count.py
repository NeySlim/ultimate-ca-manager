"""
Migration: Add retry_count column to notification_log table
"""

def upgrade(db_path):
    """Add retry_count column to notification_log"""
    import sqlite3
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='notification_log'")
        if not cursor.fetchone():
            print("✓ notification_log table doesn't exist yet, skipping")
            return
        
        # Check existing columns
        cursor.execute("PRAGMA table_info(notification_log)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'retry_count' not in columns:
            cursor.execute("ALTER TABLE notification_log ADD COLUMN retry_count INTEGER DEFAULT 0")
            print("✓ Added retry_count column to notification_log")
        else:
            print("✓ retry_count already exists")
        
        conn.commit()
        
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()

def downgrade(db_path):
    print("Note: SQLite doesn't support DROP COLUMN. Column will remain.")
