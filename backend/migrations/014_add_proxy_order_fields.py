"""
Migration 014: Add proxy order fields to acme_client_orders
Adds fields for tracking proxy orders and DNS records created
"""

def upgrade(db_connection, logger=None):
    cursor = db_connection.cursor()
    
    # Check if columns exist
    cursor.execute("PRAGMA table_info(acme_client_orders)")
    columns = [row[1] for row in cursor.fetchall()]
    
    # Add is_proxy_order column
    if 'is_proxy_order' not in columns:
        cursor.execute("ALTER TABLE acme_client_orders ADD COLUMN is_proxy_order BOOLEAN DEFAULT 0")
        if logger:
            logger.info("Added is_proxy_order column")
    
    # Add dns_records_created column (JSON array of record IDs)
    if 'dns_records_created' not in columns:
        cursor.execute("ALTER TABLE acme_client_orders ADD COLUMN dns_records_created TEXT")
        if logger:
            logger.info("Added dns_records_created column")
    
    # Add client_jwk_thumbprint column (for identifying the ACME client)
    if 'client_jwk_thumbprint' not in columns:
        cursor.execute("ALTER TABLE acme_client_orders ADD COLUMN client_jwk_thumbprint VARCHAR(64)")
        if logger:
            logger.info("Added client_jwk_thumbprint column")
    
    # Add upstream_order_url column (the real LE order URL)
    if 'upstream_order_url' not in columns:
        cursor.execute("ALTER TABLE acme_client_orders ADD COLUMN upstream_order_url TEXT")
        if logger:
            logger.info("Added upstream_order_url column")
    
    db_connection.commit()
    return True


def downgrade(db_connection, logger=None):
    # SQLite doesn't support DROP COLUMN easily, skip
    return True
