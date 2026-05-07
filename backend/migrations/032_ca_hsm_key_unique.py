"""Migration 032: enforce one-to-one between CA and HSM key.

Closes a TOCTOU race in services/ca/ca_creation.py where two concurrent
CA-create requests could both pass the `CA.query.filter_by(hsm_key_id=...)`
check and end up bound to the same HSM key. Adds a partial unique index
(NULL allowed for local-key CAs).
"""
import logging

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS uq_ca_hsm_key_id
    ON cas(hsm_key_id) WHERE hsm_key_id IS NOT NULL;
"""


def upgrade(conn):
    # No-op if the cas table doesn't exist yet (e.g. fresh install where
    # SQLAlchemy create_all() hasn't run yet — the index is harmless to
    # add later via a future migration, and create_all() won't reproduce it).
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='cas'"
    )
    if not cur.fetchone():
        logger.info("[032] cas table not present yet — skipping (fresh install)")
        return

    # Pre-flight: detect any existing duplicate to avoid a hard failure.
    cur = conn.execute(
        "SELECT hsm_key_id, COUNT(*) FROM cas "
        "WHERE hsm_key_id IS NOT NULL "
        "GROUP BY hsm_key_id HAVING COUNT(*) > 1"
    )
    dupes = cur.fetchall()
    if dupes:
        # Don't auto-resolve — operator must reconcile manually.
        for hsm_key_id, count in dupes:
            logger.error(
                f"[032] HSM key {hsm_key_id} bound to {count} CAs — manual cleanup required"
            )
        raise RuntimeError(
            "Migration 032 aborted: duplicate hsm_key_id found in cas table. "
            "Reconcile manually before retrying."
        )

    conn.executescript(SCHEMA_SQL)
    conn.commit()
    logger.info("[032] Added unique partial index uq_ca_hsm_key_id")


def downgrade(conn):
    conn.execute("DROP INDEX IF EXISTS uq_ca_hsm_key_id")
    conn.commit()
