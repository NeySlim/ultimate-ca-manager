"""
Migration: Add hash chain columns to audit_logs for tamper detection
"""

def upgrade(db_path):
    """Add prev_hash and entry_hash columns to audit_logs"""
    import sqlite3
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check existing columns
        cursor.execute("PRAGMA table_info(audit_logs)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'prev_hash' not in columns:
            cursor.execute("ALTER TABLE audit_logs ADD COLUMN prev_hash VARCHAR(64)")
            print("✓ Added prev_hash column")
        else:
            print("✓ prev_hash already exists")
        
        if 'entry_hash' not in columns:
            cursor.execute("ALTER TABLE audit_logs ADD COLUMN entry_hash VARCHAR(64)")
            print("✓ Added entry_hash column")
        else:
            print("✓ entry_hash already exists")
        
        conn.commit()
        
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()

def downgrade(db_path):
    print("Note: SQLite doesn't support DROP COLUMN. Columns will remain.")
