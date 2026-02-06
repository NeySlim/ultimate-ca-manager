"""
Migration 008: Add missing columns to certificate_templates
Aligns existing table with the CertificateTemplate model.
"""


def upgrade(conn):
    """Add missing columns to certificate_templates"""
    cursor = conn.execute("PRAGMA table_info(certificate_templates)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    
    # Columns needed by the model
    columns_to_add = [
        ("template_type", "VARCHAR(50) NOT NULL DEFAULT 'custom'"),
        ("digest", "VARCHAR(20) DEFAULT 'sha256'"),
        ("dn_template", "TEXT"),
        ("extensions_template", "TEXT DEFAULT '{}'"),
        ("is_system", "BOOLEAN DEFAULT 0"),
        ("is_active", "BOOLEAN DEFAULT 1"),
        ("created_by", "VARCHAR(80)"),
        ("updated_by", "VARCHAR(80)"),
    ]
    
    for col_name, col_def in columns_to_add:
        if col_name not in existing_columns:
            try:
                conn.execute(f"ALTER TABLE certificate_templates ADD COLUMN {col_name} {col_def}")
                print(f"    Added column: {col_name}")
            except Exception as e:
                if "duplicate column" not in str(e).lower():
                    # Ignore if column already exists
                    pass
    
    conn.commit()


def downgrade(conn):
    """SQLite doesn't support DROP COLUMN easily"""
    pass
