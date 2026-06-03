"""Migration 037: add CA-template pinning table.

Creates ca_template_pins table to support pinning templates to specific CAs.
When a CA has pinned templates, only those templates are shown by default
in the certificate creation form, with a "Show all" toggle available.

Table structure:
- id: primary key
- ca_id: FK to certificate_authorities.id
- template_id: FK to certificate_templates.id
- created_at: timestamp when pin was created
- created_by: username who created the pin
- UNIQUE constraint on (ca_id, template_id) to prevent duplicates

Idempotent and dual-backend (SQLite + PostgreSQL).
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True


def _upgrade_sqlite(conn):
    """Upgrade SQLite database."""
    # Check if table already exists
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='ca_template_pins'"
    )
    if cur.fetchone():
        logger.info("[037] ca_template_pins table already exists, skipping")
        return

    # Create table
    conn.execute("""
        CREATE TABLE ca_template_pins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ca_id INTEGER NOT NULL,
            template_id INTEGER NOT NULL,
            created_at DATETIME NOT NULL,
            created_by VARCHAR(80),
            FOREIGN KEY (ca_id) REFERENCES certificate_authorities(id) ON DELETE CASCADE,
            FOREIGN KEY (template_id) REFERENCES certificate_templates(id) ON DELETE CASCADE,
            UNIQUE(ca_id, template_id)
        )
    """)
    
    # Create indexes for better query performance
    conn.execute("CREATE INDEX idx_ca_template_pins_ca_id ON ca_template_pins(ca_id)")
    conn.execute("CREATE INDEX idx_ca_template_pins_template_id ON ca_template_pins(template_id)")
    
    logger.info("[037] created ca_template_pins table (SQLite)")
    conn.commit()


def _upgrade_pg(conn):
    """Upgrade PostgreSQL database."""
    from sqlalchemy import inspect, text

    insp = inspect(conn)
    if 'ca_template_pins' in set(insp.get_table_names()):
        logger.info("[037] ca_template_pins table already exists, skipping")
        return

    # Create table
    conn.execute(text("""
        CREATE TABLE ca_template_pins (
            id SERIAL PRIMARY KEY,
            ca_id INTEGER NOT NULL,
            template_id INTEGER NOT NULL,
            created_at TIMESTAMP NOT NULL,
            created_by VARCHAR(80),
            FOREIGN KEY (ca_id) REFERENCES certificate_authorities(id) ON DELETE CASCADE,
            FOREIGN KEY (template_id) REFERENCES certificate_templates(id) ON DELETE CASCADE,
            UNIQUE(ca_id, template_id)
        )
    """))
    
    # Create indexes
    conn.execute(text("CREATE INDEX idx_ca_template_pins_ca_id ON ca_template_pins(ca_id)"))
    conn.execute(text("CREATE INDEX idx_ca_template_pins_template_id ON ca_template_pins(template_id)"))
    
    logger.info("[037] created ca_template_pins table (PostgreSQL)")


def upgrade(conn):
    """Main upgrade dispatcher."""
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """Downgrade dispatcher."""
    if isinstance(conn, sqlite3.Connection):
        _downgrade_sqlite(conn)
    else:
        _downgrade_pg(conn)


def _downgrade_sqlite(conn):
    """Drop ca_template_pins table from SQLite."""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='ca_template_pins'"
    )
    if not cur.fetchone():
        logger.info("[037] ca_template_pins table absent, skipping downgrade")
        return

    conn.execute("DROP TABLE ca_template_pins")
    logger.info("[037] dropped ca_template_pins table (SQLite)")
    conn.commit()


def _downgrade_pg(conn):
    """Drop ca_template_pins table from PostgreSQL."""
    from sqlalchemy import inspect, text

    insp = inspect(conn)
    if 'ca_template_pins' not in set(insp.get_table_names()):
        logger.info("[037] ca_template_pins table absent, skipping downgrade")
        return

    conn.execute(text("DROP TABLE ca_template_pins CASCADE"))
    logger.info("[037] dropped ca_template_pins table (PostgreSQL)")
