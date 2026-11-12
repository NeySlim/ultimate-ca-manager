"""Migration 155: Windows enrollment profiles, and the 2.x configuration as the default one.

Creates windows_enrollment_profiles and windows_profile_templates, names the AD connector
rows, adds certificates.windows_profile_id. The 2.x XCEP/WSTEP settings become the default
profile (services.windows_profiles.legacy, shared with the restore of a 2.x archive) and
are deleted in the same transaction; the WSTEP certificates are attached to it. XCEP without
a CA of its own is switched off, as it served no policy (legacy.switches_from_2x).
The keytab is read for its realm only; it is stored in the profile at startup.
Idempotent, dual-backend (SQLite + PostgreSQL).
"""
import logging
import sqlite3
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
pg_compatible = True

PROFILES = 'windows_enrollment_profiles'
LINKS = 'windows_profile_templates'
CONNECTORS = 'ad_connector_config'
CERTS = 'certificates'
SETTINGS = 'system_config'

_PROFILE_COLUMNS = (
    "name VARCHAR(100) NOT NULL UNIQUE, realm VARCHAR(255) UNIQUE, "
    "is_default BOOLEAN NOT NULL DEFAULT {false}, enabled BOOLEAN NOT NULL DEFAULT {true}, "
    f"connector_id INTEGER REFERENCES {CONNECTORS}(id) ON DELETE SET NULL, "
    "issuing_ca_refid VARCHAR(36), policy_ca_refid VARCHAR(36), "
    "validity_days INTEGER NOT NULL DEFAULT 365, xcep_username TEXT, xcep_password TEXT, "
    "wstep_username TEXT, wstep_password TEXT, allowed_ad_group VARCHAR(255), "
    "pinned_subject_fields TEXT, keytab TEXT, created_at {ts}, created_by VARCHAR(80), "
    "updated_at {ts}, updated_by VARCHAR(80)")
_LINK_COLUMNS = (
    f"profile_id INTEGER NOT NULL REFERENCES {PROFILES}(id) ON DELETE CASCADE, "
    "template_id INTEGER NOT NULL REFERENCES certificate_templates(id), "
    "CONSTRAINT uq_windows_profile_templates UNIQUE (profile_id, template_id)")
_SQLITE_DDL = (
    f"CREATE TABLE IF NOT EXISTS {PROFILES} (id INTEGER PRIMARY KEY AUTOINCREMENT, "
    + _PROFILE_COLUMNS.format(false='0', true='1', ts='DATETIME') + ")",
    f"CREATE TABLE IF NOT EXISTS {LINKS} (id INTEGER PRIMARY KEY AUTOINCREMENT, {_LINK_COLUMNS})",
)
_PG_DDL = (
    f"CREATE TABLE IF NOT EXISTS {PROFILES} (id SERIAL PRIMARY KEY, "
    + _PROFILE_COLUMNS.format(false='FALSE', true='TRUE', ts='TIMESTAMP') + ")",
    f"CREATE TABLE IF NOT EXISTS {LINKS} (id SERIAL PRIMARY KEY, {_LINK_COLUMNS})",
)
_INDEXES = (
    f"CREATE UNIQUE INDEX IF NOT EXISTS uq_windows_enrollment_profiles_default ON {PROFILES} (is_default) "
    "WHERE is_default",
    f"CREATE INDEX IF NOT EXISTS ix_{PROFILES}_issuing_ca_refid ON {PROFILES} (issuing_ca_refid)",
    f"CREATE INDEX IF NOT EXISTS ix_{PROFILES}_policy_ca_refid ON {PROFILES} (policy_ca_refid)",
    f"CREATE INDEX IF NOT EXISTS ix_{LINKS}_profile_id ON {LINKS} (profile_id)",
    f"CREATE INDEX IF NOT EXISTS ix_{LINKS}_template_id ON {LINKS} (template_id)",
)
_CONNECTOR_NAME_INDEX = f"CREATE UNIQUE INDEX IF NOT EXISTS uq_{CONNECTORS}_name ON {CONNECTORS} (name)"
_CERT_INDEX = f"CREATE INDEX IF NOT EXISTS ix_{CERTS}_windows_profile_id ON {CERTS} (windows_profile_id)"
_INSERT_FIELDS = ('name', 'realm', 'is_default', 'enabled', 'connector_id', 'issuing_ca_refid',
                  'policy_ca_refid', 'validity_days', 'xcep_username', 'xcep_password',
                  'wstep_username', 'wstep_password', 'created_at', 'created_by')


def _keytab_on_disk():
    """The keytab a 2.x node kept in DATA_DIR, None when absent or unreadable."""
    try:
        from config.settings import DATA_DIR
        return (DATA_DIR / 'kerberos.keytab').read_bytes()
    except (OSError, ImportError):
        return None


def _profile(settings, connector, keytab):
    from services.windows_profiles.legacy import profile_from_2x
    profile = profile_from_2x(settings, connector, keytab)
    if profile is not None:
        profile.update(created_at=datetime.now(timezone.utc).replace(tzinfo=None), created_by='system')
    return profile


def _settings_keys():
    from services.windows_profiles.legacy import MIGRATED_KEYS
    return MIGRATED_KEYS, MIGRATED_KEYS + ('kerberos_spn', 'kerberos_enabled', 'xcep_enabled')


def _switches(settings):
    from services.windows_profiles.legacy import switches_from_2x
    return switches_from_2x(settings)


def _connector_names(rows):
    from services.windows_profiles.legacy import connector_names
    return connector_names(rows)


def upgrade_sqlite(conn, keytab=None):
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    for ddl in _SQLITE_DDL + _INDEXES:
        conn.execute(ddl)
    if CONNECTORS in tables:
        columns = {r[1] for r in conn.execute(f"PRAGMA table_info({CONNECTORS})")}
        if 'name' not in columns:
            conn.execute(f"ALTER TABLE {CONNECTORS} ADD COLUMN name VARCHAR(100)")
        if 'domain_sid' not in columns:
            conn.execute(f"ALTER TABLE {CONNECTORS} ADD COLUMN domain_sid VARCHAR(255)")
        for row_id, name in _connector_names(conn.execute(f"SELECT id, name FROM {CONNECTORS}").fetchall()):
            conn.execute(f"UPDATE {CONNECTORS} SET name = ? WHERE id = ?", (name, row_id))
        conn.execute(_CONNECTOR_NAME_INDEX)
    if CERTS in tables:
        if 'windows_profile_id' not in {r[1] for r in conn.execute(f"PRAGMA table_info({CERTS})")}:
            conn.execute(f"ALTER TABLE {CERTS} ADD COLUMN windows_profile_id INTEGER")
        conn.execute(_CERT_INDEX)
    if SETTINGS in tables:
        migrated, read = _settings_keys()
        marks = ','.join('?' * len(read))
        settings = dict(conn.execute(f"SELECT key, value FROM {SETTINGS} WHERE key IN ({marks})", read))
        default = conn.execute(f"SELECT id FROM {PROFILES} WHERE is_default").fetchone()
        if default is None:
            connector = None
            if CONNECTORS in tables:
                row = conn.execute(f"SELECT id, enabled, base_dn FROM {CONNECTORS} ORDER BY id LIMIT 1").fetchone()
                connector = {'id': row[0], 'enabled': bool(row[1]), 'base_dn': row[2]} if row else None
            profile = _profile(settings, connector, keytab if keytab is not None else _keytab_on_disk())
            if profile is not None:
                values = [profile[f] for f in _INSERT_FIELDS]
                values[_INSERT_FIELDS.index('created_at')] = profile['created_at'].isoformat(' ')
                conn.execute(f"INSERT INTO {PROFILES} ({', '.join(_INSERT_FIELDS)}) VALUES "
                             f"({','.join('?' * len(values))})", values)
                default = conn.execute(f"SELECT id FROM {PROFILES} WHERE is_default").fetchone()
                logger.info("[155] default Windows enrollment profile created (realm %s)", profile['realm'])
            for key, value in _switches(settings).items():
                conn.execute(f"UPDATE {SETTINGS} SET value = ? WHERE key = ?", (value, key))
        if default is not None and CERTS in tables:
            conn.execute(f"UPDATE {CERTS} SET windows_profile_id = ? "
                         "WHERE source = 'wstep' AND windows_profile_id IS NULL", (default[0],))
        conn.execute(f"DELETE FROM {SETTINGS} WHERE key IN ({','.join('?' * len(migrated))})", migrated)
    conn.commit()


def upgrade_pg(conn, keytab=None):
    from sqlalchemy import bindparam, inspect, text
    tables = set(inspect(conn).get_table_names())
    for ddl in _PG_DDL + _INDEXES:
        conn.execute(text(ddl))
    if CONNECTORS in tables:
        conn.execute(text(f"ALTER TABLE {CONNECTORS} ADD COLUMN IF NOT EXISTS name VARCHAR(100)"))
        conn.execute(text(f"ALTER TABLE {CONNECTORS} ADD COLUMN IF NOT EXISTS domain_sid VARCHAR(255)"))
        for row_id, name in _connector_names(conn.execute(text(f"SELECT id, name FROM {CONNECTORS}")).fetchall()):
            conn.execute(text(f"UPDATE {CONNECTORS} SET name = :n WHERE id = :i"), {'n': name, 'i': row_id})
        conn.execute(text(f"ALTER TABLE {CONNECTORS} ALTER COLUMN name SET NOT NULL"))
        conn.execute(text(_CONNECTOR_NAME_INDEX))
    if CERTS in tables:
        conn.execute(text(f"ALTER TABLE {CERTS} ADD COLUMN IF NOT EXISTS windows_profile_id INTEGER"))
        conn.execute(text(_CERT_INDEX))
    if SETTINGS in tables:
        migrated, read = _settings_keys()
        settings = dict(conn.execute(text(f"SELECT key, value FROM {SETTINGS} WHERE key IN :keys")
                                     .bindparams(bindparam('keys', expanding=True)), {'keys': list(read)}).fetchall())
        default = conn.execute(text(f"SELECT id FROM {PROFILES} WHERE is_default")).fetchone()
        if default is None:
            connector = None
            if CONNECTORS in tables:
                row = conn.execute(text(f"SELECT id, enabled, base_dn FROM {CONNECTORS} ORDER BY id LIMIT 1")).fetchone()
                connector = {'id': row[0], 'enabled': bool(row[1]), 'base_dn': row[2]} if row else None
            profile = _profile(settings, connector, keytab if keytab is not None else _keytab_on_disk())
            if profile is not None:
                conn.execute(text(f"INSERT INTO {PROFILES} ({', '.join(_INSERT_FIELDS)}) VALUES "
                                  f"({', '.join(':' + f for f in _INSERT_FIELDS)})"),
                             {f: profile[f] for f in _INSERT_FIELDS})
                default = conn.execute(text(f"SELECT id FROM {PROFILES} WHERE is_default")).fetchone()
                logger.info("[155] default Windows enrollment profile created (realm %s)", profile['realm'])
            for key, value in _switches(settings).items():
                conn.execute(text(f"UPDATE {SETTINGS} SET value = :v WHERE key = :k"), {'v': value, 'k': key})
        if default is not None and CERTS in tables:
            conn.execute(text(f"UPDATE {CERTS} SET windows_profile_id = :p "
                              "WHERE source = 'wstep' AND windows_profile_id IS NULL"), {'p': default[0]})
        conn.execute(text(f"DELETE FROM {SETTINGS} WHERE key IN :keys")
                     .bindparams(bindparam('keys', expanding=True)), {'keys': list(migrated)})


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        upgrade_sqlite(conn)
    else:
        upgrade_pg(conn)


def downgrade(conn):
    """No downgrade: the settings it replaced are gone, the profile is their only copy."""
    pass
