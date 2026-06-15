"""Migration 043: drop the global UNIQUE constraint on users.email.

An SSO (LDAP/OAuth2/SAML) login may legitimately resolve to an email that a
local user already owns. The previous ``UNIQUE (email)`` constraint turned that
into a ``sqlite3.IntegrityError``/``UniqueViolation`` during SSO user creation,
surfacing as an Internal Server Error (see #136).

Uniqueness for locally-managed users stays enforced at the application layer
(api/v2/users/crud.py). This migration only removes the DB-level constraint and
replaces it with a plain (non-unique) index for lookups.

SQLite has no ``ALTER TABLE ... DROP CONSTRAINT``, so the table is rebuilt.
Dual-backend (SQLite + PostgreSQL).
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True


def _upgrade_sqlite(conn):
    # The column-level UNIQUE is materialised as an auto-index that cannot be
    # dropped directly, so detect it and rebuild the table without it.
    has_unique = conn.execute(
        "SELECT 1 FROM sqlite_master "
        "WHERE type='index' AND tbl_name='users' "
        "AND sql IS NULL AND name LIKE 'sqlite_autoindex_users_%'"
    ).fetchone()
    if not has_unique:
        logger.info("[043] users.email already non-unique, skipping (SQLite)")
        return

    conn.executescript("""
        CREATE TABLE _users_new (
            id INTEGER NOT NULL,
            username VARCHAR(80) NOT NULL,
            email VARCHAR(120) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            full_name VARCHAR(255),
            role VARCHAR(20) NOT NULL,
            active BOOLEAN,
            mfa_enabled BOOLEAN,
            created_at DATETIME,
            last_login DATETIME,
            totp_secret TEXT,
            totp_confirmed INTEGER DEFAULT 0,
            backup_codes TEXT,
            login_count INTEGER DEFAULT 0,
            failed_logins INTEGER DEFAULT 0,
            locked_until DATETIME,
            force_password_change BOOLEAN DEFAULT 0,
            password_reset_token VARCHAR(128),
            password_reset_expires DATETIME,
            custom_role_id INTEGER REFERENCES pro_custom_roles(id) ON DELETE SET NULL,
            preferences TEXT,
            auth_source VARCHAR(20) NOT NULL DEFAULT 'local',
            sso_provider_id INTEGER,
            PRIMARY KEY (id)
        );
        INSERT INTO _users_new
            SELECT id, username, email, password_hash, full_name, role, active,
                   mfa_enabled, created_at, last_login, totp_secret,
                   totp_confirmed, backup_codes, login_count, failed_logins,
                   locked_until, force_password_change, password_reset_token,
                   password_reset_expires, custom_role_id, preferences,
                   auth_source, sso_provider_id
            FROM users;
        DROP TABLE users;
        ALTER TABLE _users_new RENAME TO users;
        CREATE UNIQUE INDEX ix_users_username ON users (username);
        CREATE INDEX ix_users_email ON users (email);
    """)
    conn.commit()
    logger.info("[043] users.email UNIQUE constraint dropped (SQLite)")


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    insp = inspect(conn)
    if 'users' not in set(insp.get_table_names()):
        logger.info("[043] users table absent, skipping (fresh PG)")
        return

    # Drop every unique constraint/index covering exactly (email).
    dropped = False
    for uc in insp.get_unique_constraints('users'):
        if uc.get('column_names') == ['email'] and uc.get('name'):
            conn.execute(text(
                f'ALTER TABLE users DROP CONSTRAINT IF EXISTS "{uc["name"]}"'
            ))
            dropped = True
    for ix in insp.get_indexes('users'):
        if ix.get('unique') and ix.get('column_names') == ['email'] and ix.get('name'):
            conn.execute(text(f'DROP INDEX IF EXISTS "{ix["name"]}"'))
            dropped = True

    # Replace with a plain index for email lookups (idempotent).
    conn.execute(text('CREATE INDEX IF NOT EXISTS ix_users_email ON users (email)'))

    if dropped:
        logger.info("[043] users.email UNIQUE constraint dropped (PostgreSQL)")
    else:
        logger.info("[043] users.email already non-unique, skipping (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """No downgrade — duplicate emails may exist once SSO has used them."""
    pass
