"""
Migration 021: Add missing columns to group_members table
- role: member role within group (member/admin)
- joined_at: when user joined the group
"""

def upgrade(conn):
    cursor = conn.execute("PRAGMA table_info(group_members)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if 'role' not in columns:
        conn.execute("ALTER TABLE group_members ADD COLUMN role VARCHAR(20) DEFAULT 'member'")
    
    if 'joined_at' not in columns:
        conn.execute("ALTER TABLE group_members ADD COLUMN joined_at DATETIME DEFAULT CURRENT_TIMESTAMP")
    
    conn.commit()


def downgrade(conn):
    pass  # SQLite doesn't support DROP COLUMN easily
