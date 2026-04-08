"""
Migration 017: Remove Certificate Authority template

CA certificates should be created from the CAs page, not via templates
in the Certificates page. This removes the misleading CA template.
"""
import logging

logger = logging.getLogger(__name__)


def upgrade(conn):
    """Remove the CA template."""
    cursor = conn.execute(
        "DELETE FROM certificate_templates WHERE template_type = 'ca' AND is_system = 1"
    )
    logger.info(f"Removed {cursor.rowcount} CA template(s)")
    conn.commit()


def downgrade(conn):
    """Re-add CA template (no-op, will be re-seeded on next startup if needed)."""
    pass
