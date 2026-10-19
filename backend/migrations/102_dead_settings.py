"""Migration 102: delete settings that nothing reads any more.

Each key below lost its reader or its screen in the same release; leaving the
row would only keep a stale value (some of them secrets) in backups. Policy
rules lose the JSON keys no evaluation ever read, and
discovery profiles gain the notification address their form always sent, and
discovered certificates the fingerprint whose expiry was last reported.
"""
import json
import sqlite3

pg_compatible = True

DEAD_KEYS = (
    'admin_bypass_password_policy',
    'acme.proxy_enabled',
    'acme.proxy.eab_kid',
    'acme.proxy.eab_hmac_key',
    'acme.proxy.account_url',
    'acme.proxy.account_key',
    'report_expiry_enabled',
    'report_expiry_recipients',
    'report_compliance_enabled',
    'report_compliance_recipients',
    'scep_url',
    'scep_ca_ident',
    'site_name',
    'app.initialized',
    'https.enabled',
)

# Legacy report switches nothing ran: (prefix, schedule key, frequency).
LEGACY_REPORTS = (
    ('report_expiry', 'report_schedule_expiring_certificates', 'daily'),
    ('report_compliance', 'report_schedule_compliance_status', 'weekly'),
)


def _system_name(config):
    """``site_name`` carried over to ``system_name``, which the settings page
    showed in its place, when no system name is stored."""
    site = (config.get('site_name') or '').strip()
    if site and not (config.get('system_name') or '').strip() and site != 'UCM':
        return {'system_name': site}
    return {}


def _legacy_schedules(config):
    """``{schedule key: JSON}`` for each legacy report switched on with
    recipients and not already scheduled, from ``{key: value}`` *config*."""
    out = {}
    for prefix, schedule_key, frequency in LEGACY_REPORTS:
        if config.get(f'{prefix}_enabled') != 'true' or schedule_key in config:
            continue
        try:
            recipients = json.loads(config.get(f'{prefix}_recipients') or '[]')
        except (TypeError, ValueError):
            continue
        if not isinstance(recipients, list) or not recipients:
            continue
        out[schedule_key] = json.dumps({
            'enabled': True, 'frequency': frequency, 'time': '08:00', 'day_of_week': 1,
            'day_of_month': 1, 'recipients': recipients, 'format': 'csv'})
    return out


DEAD_RULE_KEYS = ('required_extensions', 'forbidden_extensions')
DEAD_SAN_RULE_KEYS = ('require_approval_for_external',)


def _cleaned_rules(text):
    """The rules without the dead keys, or None when nothing changes."""
    try:
        rules = json.loads(text or '{}')
    except (TypeError, ValueError):
        return None
    if not isinstance(rules, dict):
        return None
    cleaned = {k: v for k, v in rules.items() if k not in DEAD_RULE_KEYS}
    san = cleaned.get('san_restrictions')
    if isinstance(san, dict):
        cleaned['san_restrictions'] = {k: v for k, v in san.items() if k not in DEAD_SAN_RULE_KEYS}
    return None if cleaned == rules else json.dumps(cleaned)


# (table, column, cleaner)
JSON_COLUMNS = (
    ('certificate_policies', 'rules', _cleaned_rules),
)


def _upgrade_sqlite(conn):
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'system_config' in tables:
        config = dict(conn.execute("SELECT key, value FROM system_config").fetchall())
        if _system_name(config):
            conn.execute("DELETE FROM system_config WHERE key = 'system_name' AND "
                         "(value IS NULL OR TRIM(value) = '')")
        for key, value in {**_legacy_schedules(config), **_system_name(config)}.items():
            conn.execute("INSERT INTO system_config (key, value) VALUES (?, ?)", (key, value))
        conn.executemany("DELETE FROM system_config WHERE key = ?", [(k,) for k in DEAD_KEYS])
    if 'discovery_scan_profiles' in tables:
        columns = {r[1] for r in conn.execute("PRAGMA table_info(discovery_scan_profiles)")}
        if 'notify_email' not in columns:
            conn.execute("ALTER TABLE discovery_scan_profiles ADD COLUMN notify_email VARCHAR(255)")
    if 'discovered_certificates' in tables:
        columns = {r[1] for r in conn.execute("PRAGMA table_info(discovered_certificates)")}
        if 'expiry_notified_fingerprint' not in columns:
            conn.execute("ALTER TABLE discovered_certificates ADD COLUMN expiry_notified_fingerprint VARCHAR(64)")
    for table, column, clean in JSON_COLUMNS:
        if table not in tables:
            continue
        for rid, value in conn.execute(f"SELECT id, {column} FROM {table}").fetchall():
            cleaned = clean(value)
            if cleaned is not None:
                conn.execute(f"UPDATE {table} SET {column} = ? WHERE id = ?", (cleaned, rid))
    conn.commit()


def _upgrade_pg(conn):
    from sqlalchemy import bindparam, inspect, text

    tables = set(inspect(conn).get_table_names())
    if 'system_config' in tables:
        config = dict(conn.execute(text("SELECT key, value FROM system_config")).fetchall())
        if _system_name(config):
            conn.execute(text("DELETE FROM system_config WHERE key = 'system_name' AND "
                              "(value IS NULL OR TRIM(value) = '')"))
        for key, value in {**_legacy_schedules(config), **_system_name(config)}.items():
            conn.execute(text("INSERT INTO system_config (key, value) VALUES (:k, :v)"),
                         {'k': key, 'v': value})
        conn.execute(text("DELETE FROM system_config WHERE key IN :keys").bindparams(
            bindparam('keys', expanding=True)), {'keys': list(DEAD_KEYS)})
    if 'discovery_scan_profiles' in tables:
        conn.execute(text("ALTER TABLE discovery_scan_profiles "
                          "ADD COLUMN IF NOT EXISTS notify_email VARCHAR(255)"))
    if 'discovered_certificates' in tables:
        conn.execute(text("ALTER TABLE discovered_certificates "
                          "ADD COLUMN IF NOT EXISTS expiry_notified_fingerprint VARCHAR(64)"))
    for table, column, clean in JSON_COLUMNS:
        if table not in tables:
            continue
        for rid, value in conn.execute(text(f"SELECT id, {column} FROM {table}")).fetchall():
            cleaned = clean(value)
            if cleaned is not None:
                conn.execute(text(f"UPDATE {table} SET {column} = :v WHERE id = :i"),
                             {'v': cleaned, 'i': rid})


def upgrade(conn):
    if isinstance(conn, sqlite3.Connection):
        _upgrade_sqlite(conn)
    else:
        _upgrade_pg(conn)


def downgrade(conn):
    # Older versions fall back to their defaults for a missing key.
    pass
