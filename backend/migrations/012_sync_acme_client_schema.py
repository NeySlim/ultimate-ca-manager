"""
Migration 012: Sync ACME Client schema with models
Adds missing columns to dns_providers and acme_client_orders tables.
"""


def upgrade(conn):
    """Add missing columns to ACME client tables"""
    
    # Add missing columns to dns_providers
    columns_to_add_dns = [
        ("zones", "TEXT"),
        ("enabled", "BOOLEAN DEFAULT 1"),
    ]
    
    for col_name, col_type in columns_to_add_dns:
        try:
            conn.execute(f"ALTER TABLE dns_providers ADD COLUMN {col_name} {col_type}")
            print(f"  ✓ Added dns_providers.{col_name}")
        except Exception as e:
            if "duplicate column" in str(e).lower():
                print(f"  ⏭️  dns_providers.{col_name} already exists")
            else:
                raise
    
    # Add missing columns to acme_client_orders
    columns_to_add_orders = [
        ("account_url", "VARCHAR(500)"),
        ("last_renewal_at", "DATETIME"),
        ("renewal_failures", "INTEGER DEFAULT 0"),
        ("last_error_at", "DATETIME"),
    ]
    
    for col_name, col_type in columns_to_add_orders:
        try:
            conn.execute(f"ALTER TABLE acme_client_orders ADD COLUMN {col_name} {col_type}")
            print(f"  ✓ Added acme_client_orders.{col_name}")
        except Exception as e:
            if "duplicate column" in str(e).lower():
                print(f"  ⏭️  acme_client_orders.{col_name} already exists")
            else:
                raise
    
    # Rename auto_renew to renewal_enabled if needed (SQLite doesn't support RENAME COLUMN before 3.25)
    # We'll just add both and keep auto_renew as alias
    try:
        conn.execute("ALTER TABLE acme_client_orders ADD COLUMN renewal_enabled BOOLEAN DEFAULT 1")
        # Copy existing values
        conn.execute("UPDATE acme_client_orders SET renewal_enabled = auto_renew WHERE renewal_enabled IS NULL")
        print("  ✓ Added acme_client_orders.renewal_enabled (synced from auto_renew)")
    except Exception as e:
        if "duplicate column" in str(e).lower():
            print("  ⏭️  acme_client_orders.renewal_enabled already exists")
        else:
            raise
    
    conn.commit()


def downgrade(conn):
    """Cannot remove columns in SQLite"""
    pass
