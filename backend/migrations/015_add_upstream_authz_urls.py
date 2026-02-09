"""
Migration 015: Add upstream_authz_urls to acme_client_orders

Stores the upstream authorization URLs for matching challenges to orders.
This fixes a race condition where concurrent orders could be confused.
"""

MIGRATION_SQL = """
ALTER TABLE acme_client_orders ADD COLUMN upstream_authz_urls TEXT;
"""

def upgrade(conn):
    """Add upstream_authz_urls column"""
    cursor = conn.cursor()
    
    # Check if column already exists
    cursor.execute("PRAGMA table_info(acme_client_orders)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if 'upstream_authz_urls' not in columns:
        cursor.execute("ALTER TABLE acme_client_orders ADD COLUMN upstream_authz_urls TEXT")
        conn.commit()
        print("  Added upstream_authz_urls column to acme_client_orders")
    else:
        print("  upstream_authz_urls column already exists")

def downgrade(conn):
    """SQLite doesn't support DROP COLUMN easily, so we skip"""
    print("  Downgrade not supported for this migration")
