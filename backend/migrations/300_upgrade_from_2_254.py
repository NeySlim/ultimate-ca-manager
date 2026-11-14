"""Migration 300: a database last started by UCM 2.254 becomes a 3.0 database.

The runner only applies it to a database whose registry holds every name 2.254 records
(``_from_2_254.PIVOT_NAMES``). Its steps run in order; each is idempotent, so a start after
an interruption runs them all again and ends in the same state. PostgreSQL runs the whole
migration in one transaction, SQLite commits step by step.
"""
import logging

from migrations._from_2_254 import STEPS, step

logger = logging.getLogger(__name__)
pg_compatible = True


def upgrade(conn):
    for name in STEPS:
        try:
            step(name).upgrade(conn)
        except Exception as exc:
            raise RuntimeError(f"upgrade step {name} failed: {exc}") from exc
        logger.info("[300] step %s done", name)


def downgrade(conn):
    """No downgrade: 2.254 restores a backup taken before the upgrade."""
