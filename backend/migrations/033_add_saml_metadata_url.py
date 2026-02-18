"""Add saml_metadata_url column to SSO providers"""

def upgrade(conn):
    # Check if column already exists
    cursor = conn.execute("PRAGMA table_info(pro_sso_providers)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'saml_metadata_url' not in columns:
        conn.execute("ALTER TABLE pro_sso_providers ADD COLUMN saml_metadata_url VARCHAR(500)")
        conn.commit()


def downgrade(conn):
    pass  # SQLite doesn't support DROP COLUMN easily
