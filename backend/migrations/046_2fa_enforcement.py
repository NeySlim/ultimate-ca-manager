"""Migration 046: 2FA enforcement (#141).

Wires the previously inert "Enforce Two-Factor Authentication" toggle:

  * users.totp_exempt            — per-user opt-out from forced enrolment.
                                   Set on the initial admin (smallest-id local
                                   admin) so enabling global enforcement can
                                   never lock out the bootstrap account.
  * pro_sso_providers.enforce_2fa — per-provider toggle. The global setting
                                   gates LOCAL users; each SSO provider carries
                                   its own independent toggle.

Dual-backend (SQLite + PostgreSQL).
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

# Smallest-id local admin = the account created at bootstrap (app.py).
_EXEMPT_INITIAL_ADMIN_SQLITE = (
    "UPDATE users SET totp_exempt = 1 "
    "WHERE id = (SELECT MIN(id) FROM users WHERE role='admin' AND auth_source='local')"
)
_EXEMPT_INITIAL_ADMIN_PG = (
    "UPDATE users SET totp_exempt = TRUE "
    "WHERE id = (SELECT MIN(id) FROM users WHERE role='admin' AND auth_source='local')"
)


def _upgrade_sqlite(conn):
    ucols = {r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
    if 'totp_exempt' not in ucols:
        conn.execute("ALTER TABLE users ADD COLUMN totp_exempt BOOLEAN DEFAULT 0")
        # Only exempt the initial admin when the column is first created, so a
        # re-run never silently re-exempts an admin who opted back in.
        conn.execute(_EXEMPT_INITIAL_ADMIN_SQLITE)
        logger.info("[046] users.totp_exempt added + initial admin exempted (SQLite)")

    pcols = {r[1] for r in conn.execute("PRAGMA table_info(pro_sso_providers)").fetchall()}
    if 'enforce_2fa' not in pcols:
        conn.execute("ALTER TABLE pro_sso_providers ADD COLUMN enforce_2fa BOOLEAN DEFAULT 0")
        logger.info("[046] pro_sso_providers.enforce_2fa added (SQLite)")

    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import inspect, text

    insp = inspect(conn)
    tables = set(insp.get_table_names())

    if 'users' in tables:
        ucols = {c['name'] for c in insp.get_columns('users')}
        if 'totp_exempt' not in ucols:
            conn.execute(text("ALTER TABLE users ADD COLUMN totp_exempt BOOLEAN DEFAULT FALSE"))
            conn.execute(text(_EXEMPT_INITIAL_ADMIN_PG))
            logger.info("[046] users.totp_exempt added + initial admin exempted (PostgreSQL)")

    if 'pro_sso_providers' in tables:
        pcols = {c['name'] for c in insp.get_columns('pro_sso_providers')}
        if 'enforce_2fa' not in pcols:
            conn.execute(text("ALTER TABLE pro_sso_providers ADD COLUMN enforce_2fa BOOLEAN DEFAULT FALSE"))
            logger.info("[046] pro_sso_providers.enforce_2fa added (PostgreSQL)")


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """No downgrade — dropping the columns would re-expose the lockout bug."""
    pass
