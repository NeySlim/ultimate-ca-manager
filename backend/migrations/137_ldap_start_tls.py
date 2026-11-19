"""Migration 137: LDAP providers can run StartTLS before binding.

``pro_sso_providers.ldap_start_tls``: off for every existing provider, so a
directory reached in plain LDAP keeps working as before. A NULL or unknown
``default_role`` meant viewer until now; it becomes viewer explicitly, since an
empty default role now refuses unmapped users.

``users.sso_orphan_of`` keeps the IdP of a deleted provider on its users. A user
still pointing at a deleted provider (SQLite never applied ON DELETE SET NULL) is
unlinked, so a new provider that reuses the id does not inherit it.

Older releases bound the external id of a same-named identity onto local
accounts; that id is dropped, so Link to SSO binds the first sign-in instead.
SSO accounts from before migration 024 (no password) keep theirs.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

TABLE = 'pro_sso_providers'
COLUMN = 'ldap_start_tls'
ROLES = "('admin', 'operator', 'auditor', 'viewer')"
NORMALISE_ROLE = (f"UPDATE {TABLE} SET default_role = 'viewer' "
                  f"WHERE default_role IS NULL OR default_role NOT IN {ROLES}")
USERS = 'users'
ORPHAN = 'sso_orphan_of'
UNLINK_DANGLING = (f"UPDATE {USERS} SET sso_provider_id = NULL WHERE sso_provider_id IS NOT NULL "
                   f"AND sso_provider_id NOT IN (SELECT id FROM {TABLE})")
STALE_ID_COLUMNS = {'sso_external_id', 'sso_provider_id', 'auth_source', 'password_hash'}
DROP_STALE_IDS = (f"UPDATE {USERS} SET sso_external_id = NULL WHERE sso_external_id IS NOT NULL "
                  "AND sso_provider_id IS NULL AND (auth_source IS NULL OR auth_source = 'local') "
                  "AND (password_hash IS NULL OR password_hash <> '!SSO_NO_PASSWORD!')")


def _upgrade_sqlite(conn):
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (TABLE,)).fetchone() is None:
        return
    present = {row[1] for row in conn.execute(f"PRAGMA table_info({TABLE})")}
    if COLUMN not in present:  # first run only: a later empty default role is a choice
        conn.execute(f"ALTER TABLE {TABLE} ADD COLUMN {COLUMN} BOOLEAN NOT NULL DEFAULT 0")
        if 'default_role' in present:
            conn.execute(NORMALISE_ROLE)
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (USERS,)).fetchone() is not None:
        ucols = {row[1] for row in conn.execute(f"PRAGMA table_info({USERS})")}
        if ORPHAN not in ucols:
            conn.execute(f"ALTER TABLE {USERS} ADD COLUMN {ORPHAN} VARCHAR(600)")
        if 'sso_provider_id' in ucols:
            conn.execute(UNLINK_DANGLING)
        if STALE_ID_COLUMNS <= ucols:
            conn.execute(DROP_STALE_IDS)
    conn.commit()
    logger.info("[137] ldap_start_tls, users.sso_orphan_of (SQLite)")


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    inspector = inspect(conn)
    tables = set(inspector.get_table_names())
    if TABLE not in tables:
        return
    present = {c['name'] for c in inspector.get_columns(TABLE)}
    if COLUMN not in present:  # first run only: a later empty default role is a choice
        conn.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN {COLUMN} BOOLEAN NOT NULL DEFAULT FALSE"))
        if 'default_role' in present:
            conn.execute(text(NORMALISE_ROLE))
    if USERS in tables:
        ucols = {c['name'] for c in inspector.get_columns(USERS)}
        if ORPHAN not in ucols:
            conn.execute(text(f"ALTER TABLE {USERS} ADD COLUMN {ORPHAN} VARCHAR(600)"))
        if 'sso_provider_id' in ucols:
            conn.execute(text(UNLINK_DANGLING))
        if STALE_ID_COLUMNS <= ucols:
            conn.execute(text(DROP_STALE_IDS))
    logger.info("[137] ldap_start_tls, users.sso_orphan_of (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """No downgrade: the columns are harmless when unused."""
    pass
