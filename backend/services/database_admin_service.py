"""Backward-compatible shim — use services.database_admin directly."""
from services.database_admin import *  # noqa: F401,F403
from services.database_admin import (  # noqa: F401
    UCM_ENV_PATH, BACKUP_DIR, MIN_POSTGRES_MAJOR,
    get_status, test_connection, persist_database_url,
    persist_database_url_with_backup, restore_previous_database_url,
    database_migration_lock, MigrationBusyError,
    BOOTSTRAP_AUTH_TABLES, bootstrap_auth_to_target, migrate_data, start_refusal,
    _redact_uri, _short_err, _human_size, _backup_current_db,
    _reset_pg_sequences, _normalize_row, _force_register_all_models,
    _detect_json_columns, _detect_boolean_columns,
    _try_disable_fks, _try_reenable_fks, _topo_sort_tables,
)
