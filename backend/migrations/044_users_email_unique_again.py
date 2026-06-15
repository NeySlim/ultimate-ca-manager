"""Migration 044: restore the UNIQUE constraint on users.email.

Migration 043 dropped it to let an SSO user share an email with a local user.
We reversed that design (#136): instead of allowing duplicate accounts, an SSO
login whose email already belongs to an account is refused, and an admin links
the two explicitly (POST /api/v2/users/<id>/link-sso). So the one-account-per-
email guarantee is restored here.

Idempotent and dual-backend (SQLite + PostgreSQL). On a DB where 043 never ran
(email already unique) this is a no-op.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True


def _upgrade_sqlite(conn):
    has_unique = conn.execute(
        "SELECT 1 FROM sqlite_master "
        "WHERE type='index' AND tbl_name='users' "
        "AND sql IS NULL AND name LIKE 'sqlite_autoindex_users_%'"
    ).fetchone()
    if has_unique:
        logger.info("[044] users.email already UNIQUE, skipping (SQLite)")
        return

    # Guard: a duplicate email would make the rebuild fail. Surface it clearly.
    dup = conn.execute(
        "SELECT email, COUNT(*) c FROM users GROUP BY email HAVING c > 1 LIMIT 1"
    ).fetchone()
    if dup:
        raise RuntimeError(
            f"[044] cannot restore UNIQUE(users.email): duplicate email {dup[0]!r}. "
            "Reconcile duplicate accounts before upgrading."
        )

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
            PRIMARY KEY (id),
            UNIQUE (email)
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
    """)
    conn.commit()
    logger.info("[044] users.email UNIQUE constraint restored (SQLite)")


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    insp = inspect(conn)
    if 'users' not in set(insp.get_table_names()):
        logger.info("[044] users table absent, skipping (fresh PG)")
        return

    already_unique = any(
        uc.get('column_names') == ['email'] for uc in insp.get_unique_constraints('users')
    ) or any(
        ix.get('unique') and ix.get('column_names') == ['email']
        for ix in insp.get_indexes('users')
    )
    if already_unique:
        logger.info("[044] users.email already UNIQUE, skipping (PostgreSQL)")
        return

    dup = conn.execute(text(
        "SELECT email FROM users GROUP BY email HAVING COUNT(*) > 1 LIMIT 1"
    )).fetchone()
    if dup:
        raise RuntimeError(
            f"[044] cannot restore UNIQUE(users.email): duplicate email {dup[0]!r}. "
            "Reconcile duplicate accounts before upgrading."
        )

    # Drop the plain index 043 created, then add the unique constraint.
    conn.execute(text('DROP INDEX IF EXISTS ix_users_email'))
    conn.execute(text('ALTER TABLE users ADD CONSTRAINT users_email_key UNIQUE (email)'))
    logger.info("[044] users.email UNIQUE constraint restored (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """No downgrade — see migration 043 for the inverse operation."""
    pass
