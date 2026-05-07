"""
Migration 027: Make acme_authorizations.order_id nullable for pre-authz

RFC 8555 §7.4.1 newAuthz endpoint allows a client to create a standalone
authorization (no order yet). Migration 016 added account_id but its
docstring's "make order_id nullable" promise was never implemented because
SQLite has no ALTER COLUMN. This migration recreates the table.
"""


def upgrade(conn):
    cursor = conn.execute("PRAGMA table_info(acme_authorizations)")
    cols = {row[1]: row for row in cursor.fetchall()}
    if 'order_id' not in cols:
        return
    # row layout: cid, name, type, notnull, dflt, pk
    if cols['order_id'][3] == 0:
        # already nullable
        return

    conn.executescript("""
        CREATE TABLE _acme_authorizations_new (
            id INTEGER NOT NULL,
            authorization_id VARCHAR(64) NOT NULL,
            order_id VARCHAR(64),
            identifier TEXT NOT NULL,
            status VARCHAR(20) NOT NULL,
            expires DATETIME NOT NULL,
            wildcard BOOLEAN,
            created_at DATETIME NOT NULL,
            account_id VARCHAR(64),
            PRIMARY KEY (id),
            FOREIGN KEY(order_id) REFERENCES acme_orders (order_id)
        );
        INSERT INTO _acme_authorizations_new
            (id, authorization_id, order_id, identifier, status, expires,
             wildcard, created_at, account_id)
        SELECT id, authorization_id, order_id, identifier, status, expires,
               wildcard, created_at, account_id
        FROM acme_authorizations;
        DROP TABLE acme_authorizations;
        ALTER TABLE _acme_authorizations_new RENAME TO acme_authorizations;
        CREATE UNIQUE INDEX IF NOT EXISTS ix_acme_authorizations_authorization_id
            ON acme_authorizations (authorization_id);
    """)
    conn.commit()


def downgrade(conn):
    """No downgrade — would require deleting standalone authorizations."""
    pass
