"""
Migration 024: Track authentication source on ``users``

Adds two columns so the UI can distinguish locally-managed accounts from
those provisioned through an SSO provider:

* ``auth_source``     — ``'local' | 'ldap' | 'oauth2' | 'saml'``
* ``sso_provider_id`` — FK to ``pro_sso_providers.id`` (nullable)

Existing rows are backfilled by inspecting the password hash sentinel
written by ``_get_or_create_sso_user`` (``'!SSO_NO_PASSWORD!'``). Such
users are flagged as ``auth_source='ldap'`` when a single LDAP provider
exists, otherwise left as ``local`` and resolved on next login.

Multi-backend convention (v2.128+): runs on both SQLite and PostgreSQL.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

SSO_PASSWORD_SENTINEL = '!SSO_NO_PASSWORD!'


def _column_exists_sqlite(conn, table, column):
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def _upgrade_sqlite(conn):
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
    )
    if not cur.fetchone():
        logger.info("Migration 024: users table absent, skipping")
        return

    if not _column_exists_sqlite(conn, 'users', 'auth_source'):
        conn.execute(
            "ALTER TABLE users ADD COLUMN auth_source VARCHAR(20) "
            "NOT NULL DEFAULT 'local'"
        )
        logger.info("Migration 024: added users.auth_source")

    if not _column_exists_sqlite(conn, 'users', 'sso_provider_id'):
        conn.execute("ALTER TABLE users ADD COLUMN sso_provider_id INTEGER")
        logger.info("Migration 024: added users.sso_provider_id")

    # Backfill SSO-provisioned users (sentinel hash → unknown SSO source).
    sso_count = conn.execute(
        "SELECT COUNT(*) FROM users WHERE password_hash = ? AND auth_source = 'local'",
        (SSO_PASSWORD_SENTINEL,),
    ).fetchone()[0]

    if sso_count:
        # Try to resolve the originating provider when the SSO sessions
        # table has a record for them; otherwise fall back to the only
        # enabled provider, if any.
        try:
            providers = conn.execute(
                "SELECT id, provider_type FROM pro_sso_providers WHERE enabled = 1"
            ).fetchall()
        except sqlite3.OperationalError:
            providers = []

        sole_provider = providers[0] if len(providers) == 1 else None

        try:
            session_rows = conn.execute(
                "SELECT user_id, MAX(provider_id) FROM pro_sso_sessions GROUP BY user_id"
            ).fetchall()
        except sqlite3.OperationalError:
            session_rows = []

        session_map = {row[0]: row[1] for row in session_rows if row[1] is not None}
        provider_types = {pid: ptype for pid, ptype in providers} if providers else {}

        sso_users = conn.execute(
            "SELECT id FROM users WHERE password_hash = ?",
            (SSO_PASSWORD_SENTINEL,),
        ).fetchall()

        for (uid,) in sso_users:
            pid = session_map.get(uid) or (sole_provider[0] if sole_provider else None)
            ptype = provider_types.get(pid) if pid else None
            source = ptype if ptype in ('ldap', 'oauth2', 'saml') else 'local'
            conn.execute(
                "UPDATE users SET auth_source = ?, sso_provider_id = ? WHERE id = ?",
                (source, pid, uid),
            )
        logger.info(
            f"Migration 024: backfilled auth_source for {sso_count} SSO user(s)"
        )

    conn.commit()


def _upgrade_pg(conn):
    # Runner passes a Connection (already in transaction) — issue #111.
    from sqlalchemy import inspect, text

    insp = inspect(conn)
    if 'users' not in set(insp.get_table_names()):
        logger.info("Migration 024: users table absent, skipping")
        return

    cols = {c['name'] for c in insp.get_columns('users')}
    if 'auth_source' not in cols:
        conn.execute(text(
            "ALTER TABLE users ADD COLUMN auth_source VARCHAR(20) "
            "NOT NULL DEFAULT 'local'"
        ))
        logger.info("Migration 024: added users.auth_source")

    if 'sso_provider_id' not in cols:
        conn.execute(text(
            "ALTER TABLE users ADD COLUMN sso_provider_id INTEGER "
            "REFERENCES pro_sso_providers(id) ON DELETE SET NULL"
        ))
        logger.info("Migration 024: added users.sso_provider_id")

    # Backfill SSO-provisioned users
    providers = conn.execute(text(
        "SELECT id, provider_type FROM pro_sso_providers WHERE enabled = TRUE"
    )).fetchall()
    sole_provider = providers[0] if len(providers) == 1 else None
    provider_types = {row[0]: row[1] for row in providers}

    try:
        session_rows = conn.execute(text(
            "SELECT user_id, MAX(provider_id) FROM pro_sso_sessions GROUP BY user_id"
        )).fetchall()
    except Exception:
        session_rows = []
    session_map = {row[0]: row[1] for row in session_rows if row[1] is not None}

    sso_users = conn.execute(text(
        "SELECT id FROM users WHERE password_hash = :h AND auth_source = 'local'"
    ), {"h": SSO_PASSWORD_SENTINEL}).fetchall()

    for (uid,) in sso_users:
        pid = session_map.get(uid) or (sole_provider[0] if sole_provider else None)
        ptype = provider_types.get(pid) if pid else None
        source = ptype if ptype in ('ldap', 'oauth2', 'saml') else 'local'
        conn.execute(text(
            "UPDATE users SET auth_source = :s, sso_provider_id = :p WHERE id = :u"
        ), {"s": source, "p": pid, "u": uid})

    if sso_users:
        logger.info(
            f"Migration 024: backfilled auth_source for {len(sso_users)} SSO user(s)"
        )


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    """SQLite cannot DROP COLUMN cleanly; left as no-op."""
    pass
