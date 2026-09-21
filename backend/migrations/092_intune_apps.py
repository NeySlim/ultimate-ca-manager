"""Migration 092: one Intune app registration, shared by SCEP profiles.

The Entra tenant, client id and secret lived on each SCEP profile (076). They
move to `intune_apps`, one row per distinct (tenant, client, secret), and the
profile keeps a foreign key to it. Profiles that carried the same credentials
share one row; a different secret for the same tenant and client keeps a row
of its own (Entra allows several secrets during a rotation) and is reported,
for the operator to merge by hand. Nothing is discarded. Then the frozen
profile columns are cleared: a secret must have one home. Idempotent, dual
backend.
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)
pg_compatible = True

_TABLE_SQLITE = """
    CREATE TABLE IF NOT EXISTS intune_apps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name VARCHAR(100) NOT NULL UNIQUE,
        tenant_id VARCHAR(255) NOT NULL,
        client_id VARCHAR(255) NOT NULL,
        client_secret TEXT NOT NULL,
        last_test_at DATETIME,
        last_test_result VARCHAR(255),
        created_at DATETIME,
        created_by VARCHAR(80),
        updated_at DATETIME,
        updated_by VARCHAR(80)
    )
"""

_TABLE_PG = """
    CREATE TABLE IF NOT EXISTS intune_apps (
        id SERIAL PRIMARY KEY,
        name VARCHAR(100) NOT NULL UNIQUE,
        tenant_id VARCHAR(255) NOT NULL,
        client_id VARCHAR(255) NOT NULL,
        client_secret TEXT NOT NULL,
        last_test_at TIMESTAMP,
        last_test_result VARCHAR(255),
        created_at TIMESTAMP,
        created_by VARCHAR(80),
        updated_at TIMESTAMP,
        updated_by VARCHAR(80)
    )
"""

# Profiles that carry credentials of their own, oldest first so the app takes
# the name of the profile that configured it first.
_LEGACY_ROWS = """
    SELECT id, name, intune_tenant_id, intune_client_id, intune_client_secret,
           intune_last_test_at, intune_last_test_result
      FROM scep_profiles
     WHERE intune_app_id IS NULL
       AND intune_tenant_id IS NOT NULL AND intune_tenant_id <> ''
       AND intune_client_id IS NOT NULL AND intune_client_id <> ''
       AND intune_client_secret IS NOT NULL AND intune_client_secret <> ''
     ORDER BY id
"""


def _unique_name(taken, wanted):
    name = wanted[:100]
    n = 2
    while name in taken:
        suffix = f' ({n})'
        name = wanted[:100 - len(suffix)] + suffix
        n += 1
    taken.add(name)
    return name


def _plain(secret):
    """The secret as entered, so two encryptions of one value compare equal;
    the ciphertext itself when it cannot be opened here (a missing key makes
    two rows distinct, never merged)."""
    try:
        from utils.encryption import decrypt_value, is_encrypted
        if is_encrypted(secret):
            return decrypt_value(secret) or secret
    except Exception:
        pass
    return secret


def _carry_over(rows, existing_apps, insert_app, bind_profile, clear_profile):
    """Give every legacy profile an app, one per distinct (tenant, client, secret)."""
    by_key = {(tenant, client, _plain(secret)): app_id
              for app_id, tenant, client, _name, secret in existing_apps}
    taken = {name for _id, _tenant, _client, name, _secret in existing_apps}
    for pid, pname, tenant, client, secret, tested_at, tested in rows:
        key = (tenant, client, _plain(secret))
        app_id = by_key.get(key)
        if app_id is None:
            if any(k[:2] == key[:2] for k in by_key):
                logger.warning(
                    "Migration 092: SCEP profile %r uses tenant %s / client %s with a "
                    "secret that differs from another profile's; a separate app "
                    "registration is created, merge them by hand under SCEP > Intune app registrations",
                    pname, tenant, client)
            app_id = insert_app(_unique_name(taken, pname), tenant, client, secret,
                                tested_at, tested)
            by_key[key] = app_id
        bind_profile(pid, app_id)
        clear_profile(pid)


def _upgrade_sqlite(conn):
    conn.execute(_TABLE_SQLITE)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(scep_profiles)")}
    if 'intune_app_id' not in columns:
        conn.execute(
            "ALTER TABLE scep_profiles ADD COLUMN intune_app_id INTEGER "
            "REFERENCES intune_apps(id)")
    existing = [(r[0], r[1], r[2], r[3], r[4]) for r in conn.execute(
        "SELECT id, tenant_id, client_id, name, client_secret FROM intune_apps")]
    rows = conn.execute(_LEGACY_ROWS).fetchall()

    def insert_app(name, tenant, client, secret, tested_at, tested):
        cur = conn.execute(
            "INSERT INTO intune_apps (name, tenant_id, client_id, client_secret, "
            "last_test_at, last_test_result, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (name, tenant, client, secret, tested_at, tested))
        return cur.lastrowid

    def bind_profile(pid, app_id):
        conn.execute("UPDATE scep_profiles SET intune_app_id = ? WHERE id = ?", (app_id, pid))

    def clear_profile(pid):
        conn.execute(
            "UPDATE scep_profiles SET intune_tenant_id = NULL, intune_client_id = NULL, "
            "intune_client_secret = NULL WHERE id = ?", (pid,))

    _carry_over(rows, existing, insert_app, bind_profile, clear_profile)
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import text

    conn.execute(text(_TABLE_PG))
    conn.execute(text(
        "ALTER TABLE scep_profiles ADD COLUMN IF NOT EXISTS intune_app_id INTEGER "
        "REFERENCES intune_apps(id)"))
    existing = [(r[0], r[1], r[2], r[3], r[4]) for r in conn.execute(text(
        "SELECT id, tenant_id, client_id, name, client_secret FROM intune_apps")).fetchall()]
    rows = conn.execute(text(_LEGACY_ROWS)).fetchall()

    def insert_app(name, tenant, client, secret, tested_at, tested):
        return conn.execute(text(
            "INSERT INTO intune_apps (name, tenant_id, client_id, client_secret, "
            "last_test_at, last_test_result, created_at) "
            "VALUES (:name, :tenant, :client, :secret, :tested_at, :tested, NOW()) "
            "RETURNING id"),
            {'name': name, 'tenant': tenant, 'client': client, 'secret': secret,
             'tested_at': tested_at, 'tested': tested}).scalar()

    def bind_profile(pid, app_id):
        conn.execute(text("UPDATE scep_profiles SET intune_app_id = :app WHERE id = :pid"),
                     {'app': app_id, 'pid': pid})

    def clear_profile(pid):
        conn.execute(text(
            "UPDATE scep_profiles SET intune_tenant_id = NULL, intune_client_id = NULL, "
            "intune_client_secret = NULL WHERE id = :pid"), {'pid': pid})

    _carry_over(rows, existing, insert_app, bind_profile, clear_profile)


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    # The frozen profile columns stay; an older version ignores intune_apps.
    pass
