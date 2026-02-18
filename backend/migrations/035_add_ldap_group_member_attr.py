"""Add ldap_group_member_attr column to SSO providers for AD memberOf support"""


def upgrade(conn):
    # Check if column already exists
    cursor = conn.execute("PRAGMA table_info(pro_sso_providers)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if 'ldap_group_member_attr' not in columns:
        conn.execute(
            "ALTER TABLE pro_sso_providers ADD COLUMN ldap_group_member_attr VARCHAR(100) DEFAULT 'member'"
        )
        conn.commit()


def downgrade(conn):
    pass  # SQLite doesn't support DROP COLUMN easily
