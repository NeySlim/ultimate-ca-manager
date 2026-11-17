"""SQLite planner statistics kept current (SQLite never re-analyzes on its own); PostgreSQL has autovacuum."""
import logging

from models import db

logger = logging.getLogger(__name__)

# Rows examined per index (sqlite.org recommends 100 to 1000): ANALYZE holds the write lock briefly at any size
ANALYSIS_LIMIT = 1000
# PRAGMA optimize: every table's size checked, not only those this connection planned with (0x10000), then ANALYZE (0x02)
_ALL_TABLES = 0x10002


def refresh_statistics(full=False):
    """ANALYZE every table (`full`) or only the tables PRAGMA optimize finds grown or shrunk
    tenfold or without statistics, bounded by ANALYSIS_LIMIT. False on another engine."""
    if db.engine.dialect.name != 'sqlite':
        return False
    conn = db.session.connection()
    previous = int(conn.exec_driver_sql('PRAGMA analysis_limit').scalar() or 0)
    conn.exec_driver_sql(f'PRAGMA analysis_limit = {ANALYSIS_LIMIT}')
    try:
        conn.exec_driver_sql('ANALYZE' if full else f'PRAGMA optimize = {_ALL_TABLES:#x}')
    finally:
        conn.exec_driver_sql(f'PRAGMA analysis_limit = {previous}')
    db.session.commit()
    return True


def scheduled_refresh():
    refresh_statistics()
