"""
Add saml_sp_cert_source column to pro_sso_providers.
Allows selecting which certificate to include in SAML SP metadata:
- 'https' (default): use UCM's HTTPS certificate
- numeric ID: use a specific certificate from the certificates table
"""


def upgrade(conn):
    # Check if column already exists
    cursor = conn.execute("PRAGMA table_info(pro_sso_providers)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'saml_sp_cert_source' not in columns:
        conn.execute(
            "ALTER TABLE pro_sso_providers ADD COLUMN saml_sp_cert_source VARCHAR(50) DEFAULT 'https'"
        )
        conn.commit()


def downgrade(conn):
    pass  # SQLite doesn't support DROP COLUMN easily
