"""Migration 105: delete the legacy ``ldap_*`` settings.

LDAP sign-in lives in the SSO providers; these global keys have no reader and
one of them is a bind password that would otherwise linger in backups.
"""
import sqlite3

pg_compatible = True

# Exact keys only: a pattern would also catch unrelated ``ldap*`` settings.
LEGACY_LDAP_KEYS = (
    'ldap_server',
    'ldap_port',
    'ldap_use_ssl',
    'ldap_use_starttls',
    'ldap_base_dn',
    'ldap_bind_dn',
    'ldap_bind_password',
    'ldap_user_filter',
    'ldap_username_attribute',
    'ldap_email_attribute',
    'ldap_display_name_attribute',
    'ldap_group_filter',
    'ldap_group_attribute',
    'ldap_sync_enabled',
    'ldap_sync_interval',
    'ldap_default_role',
    'ldap_enabled',
    'ldap_timeout',
    'ldap_verify_ssl',
    'ldap_ca_cert',
)


def _upgrade_sqlite(conn):
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' "
                    "AND name = 'system_config'").fetchone() is None:
        return
    conn.executemany("DELETE FROM system_config WHERE key = ?", [(k,) for k in LEGACY_LDAP_KEYS])
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import bindparam, inspect, text

    if 'system_config' not in inspect(conn).get_table_names():
        return
    conn.execute(text("DELETE FROM system_config WHERE key IN :keys").bindparams(
        bindparam('keys', expanding=True)), {'keys': list(LEGACY_LDAP_KEYS)})


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    # A deleted value cannot be restored; nothing reads these keys.
    pass
