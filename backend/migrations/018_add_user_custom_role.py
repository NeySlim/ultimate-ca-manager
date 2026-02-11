"""
Migration 018: Add custom_role_id to users table
Links users to RBAC custom roles and enables group permission cascading
"""

def upgrade(conn):
    cursor = conn.cursor()
    
    # Check if custom_role_id already exists
    cursor.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if 'custom_role_id' not in columns:
        cursor.execute("""
            ALTER TABLE users ADD COLUMN custom_role_id INTEGER 
            REFERENCES pro_custom_roles(id) ON DELETE SET NULL
        """)
    
    conn.commit()


def downgrade(conn):
    # SQLite doesn't support DROP COLUMN before 3.35.0
    # For safety, we just leave the column
    pass
