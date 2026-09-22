"""Migration 093: active health state for the Active Directory connector.

The connector can hold several domain controllers and fails over between
them. Until now a dead DC was discovered only by an enrollment request
paying its full connect timeout before falling through to the next one. A
scheduled probe now binds to each DC on its own, so a DC that is down is
known before a client needs it and is skipped at enrollment time.

``health`` holds the probe's last verdict as JSON (per-DC state, when it
last changed and why), kept on the config row rather than in process memory
because the process that probes is the one holding the scheduler's
singleton lock, while every other worker needs to read the result.

``health_probe_interval`` is the probe period in seconds, per connector.

Dual-backend (SQLite + PostgreSQL).
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

DEFAULT_PROBE_INTERVAL = 120


def _upgrade_sqlite(conn):
    tables = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if 'ad_connector_config' not in tables:
        logger.info("093: no ad_connector_config table, nothing to do (SQLite)")
        return
    cols = {row[1] for row in conn.execute("PRAGMA table_info(ad_connector_config)")}
    changed = False
    if 'health' not in cols:
        conn.execute("ALTER TABLE ad_connector_config ADD COLUMN health TEXT")
        changed = True
    if 'health_probe_interval' not in cols:
        conn.execute(
            "ALTER TABLE ad_connector_config ADD COLUMN "
            f"health_probe_interval INTEGER DEFAULT {DEFAULT_PROBE_INTERVAL}")
        conn.execute(
            "UPDATE ad_connector_config SET health_probe_interval = ? "
            "WHERE health_probe_interval IS NULL", (DEFAULT_PROBE_INTERVAL,))
        changed = True
    if changed:
        conn.commit()
        logger.info("093: added ad_connector_config health columns (SQLite)")


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    # Migrations run before create_all, so on an installation that predates
    # the connector the table is not there yet and its own model will build
    # it with these columns already present.
    if 'ad_connector_config' not in inspect(conn).get_table_names():
        logger.info("093: no ad_connector_config table, nothing to do (PostgreSQL)")
        return
    conn.execute(text(
        "ALTER TABLE ad_connector_config ADD COLUMN IF NOT EXISTS health TEXT"))
    conn.execute(text(
        "ALTER TABLE ad_connector_config ADD COLUMN IF NOT EXISTS "
        f"health_probe_interval INTEGER DEFAULT {DEFAULT_PROBE_INTERVAL}"))
    conn.execute(text(
        "UPDATE ad_connector_config SET health_probe_interval = "
        f"{DEFAULT_PROBE_INTERVAL} WHERE health_probe_interval IS NULL"))
    logger.info("093: ad_connector_config health columns present (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    # Added columns are harmless if left behind, matching nearby migrations.
    pass
