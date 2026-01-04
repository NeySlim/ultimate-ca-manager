"""
Migration: Add OPNsense features to Certificate model
Adds SAN fields, OCSP URI, and private key location
"""
import sqlite3
import sys
import os

def migrate():
    """Add new columns to certificates table"""
    db_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'ucm.db')
    
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if columns already exist
    cursor.execute("PRAGMA table_info(certificates)")
    columns = [row[1] for row in cursor.fetchall()]
    
    migrations = []
    
    if 'san_dns' not in columns:
        migrations.append("ALTER TABLE certificates ADD COLUMN san_dns TEXT")
    if 'san_ip' not in columns:
        migrations.append("ALTER TABLE certificates ADD COLUMN san_ip TEXT")
    if 'san_email' not in columns:
        migrations.append("ALTER TABLE certificates ADD COLUMN san_email TEXT")
    if 'san_uri' not in columns:
        migrations.append("ALTER TABLE certificates ADD COLUMN san_uri TEXT")
    if 'ocsp_uri' not in columns:
        migrations.append("ALTER TABLE certificates ADD COLUMN ocsp_uri VARCHAR(255)")
    if 'private_key_location' not in columns:
        migrations.append("ALTER TABLE certificates ADD COLUMN private_key_location VARCHAR(20) DEFAULT 'firewall'")
    
    if not migrations:
        print("✅ All columns already exist - no migration needed")
        conn.close()
        return True
    
    try:
        for sql in migrations:
            print(f"Executing: {sql}")
            cursor.execute(sql)
        
        conn.commit()
        print(f"✅ Successfully added {len(migrations)} new columns")
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
        return False
        
    finally:
        conn.close()

if __name__ == '__main__':
    success = migrate()
    sys.exit(0 if success else 1)
