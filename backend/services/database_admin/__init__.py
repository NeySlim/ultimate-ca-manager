"""
Database Admin service package.
Manages database backend status, testing, switching, and data migration
between SQLite and PostgreSQL.
"""

from .helpers import (
    UCM_ENV_PATH, BACKUP_DIR,
    _redact_uri, _short_err, _human_size, _backup_current_db,
    _reset_pg_sequences, _normalize_row, _force_register_all_models,
    _detect_json_columns, _detect_boolean_columns,
    _try_disable_fks, _try_reenable_fks, _topo_sort_tables,
)
from .status import MIN_POSTGRES_MAJOR, get_status, test_connection
from .persistence import persist_database_url
from .migration import BOOTSTRAP_AUTH_TABLES, bootstrap_auth_to_target, migrate_data

__all__ = [
    'UCM_ENV_PATH', 'BACKUP_DIR',
    '_redact_uri', '_short_err', '_human_size', '_backup_current_db',
    '_reset_pg_sequences', '_normalize_row', '_force_register_all_models',
    '_detect_json_columns', '_detect_boolean_columns',
    '_try_disable_fks', '_try_reenable_fks', '_topo_sort_tables',
    'MIN_POSTGRES_MAJOR', 'get_status', 'test_connection',
    'persist_database_url',
    'BOOTSTRAP_AUTH_TABLES', 'bootstrap_auth_to_target', 'migrate_data',
]
