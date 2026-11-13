"""Corrections of the 2.x migrations that a restore replays on the rows an older archive wrote.

Each section carries the rule of the migration it comes from, so a restore does not read
a migration file. The functions are pure: they take the values and return the repaired ones.
"""
import base64
import json
import logging

from cryptography import x509
from cryptography.hazmat.primitives import serialization

logger = logging.getLogger(__name__)


# -- 101: the legacy acme_eab_keys blob ------------------------------------------------------
LABEL = 'Imported legacy EAB key'


KID_LENGTH = 255


def eab_entries(raw):
    """``(importable pairs, leftover blob or None)``; the blob is left whole when unreadable."""
    try:
        blob = json.loads(raw or '{}')
    except (TypeError, ValueError):
        blob = None
    if not isinstance(blob, dict):
        logger.warning("[101] acme_eab_keys is not a JSON object; left in place")
        return [], raw
    entries, leftover = [], {}
    for kid, key in blob.items():
        if isinstance(kid, str) and isinstance(key, str) and kid and key and len(kid) <= KID_LENGTH:
            entries.append((kid, key))
        else:
            leftover[kid] = key
    if leftover:
        logger.warning("[101] %d legacy EAB entr(ies) not importable; left in acme_eab_keys", len(leftover))
    return entries, (json.dumps(leftover) if leftover else None)


def encrypt(value):
    from utils.encryption import encrypt_if_needed
    return encrypt_if_needed(value)


# -- 102: dead settings, dead policy rule keys, built-in template SAN types -------------------
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


def system_name(config):
    """``site_name`` carried over to ``system_name``, which the settings page
    showed in its place, when no system name is stored."""
    site = (config.get('site_name') or '').strip()
    if site and not (config.get('system_name') or '').strip() and site != 'UCM':
        return {'system_name': site}
    return {}


def legacy_schedules(config):
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


def cleaned_rules(text):
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


# Built-in template name: (seeded SAN types, widened SAN types)
SYSTEM_SAN_TYPES = {
    'VPN Client': (['email'], ['dns', 'email', 'upn']),
    'Client Authentication': (['email'], ['dns', 'email', 'upn']),
    'Client Certificate': (['email'], ['dns', 'email', 'upn']),
    'Smartcard Logon': (['upn'], ['upn', 'email']),
}


def widened_system_extensions(name, is_system, value):
    """The built-in template's extensions with the widened SAN types, or None."""
    if not is_system or name not in SYSTEM_SAN_TYPES:
        return None
    try:
        ext = json.loads(value or '{}')
    except (TypeError, ValueError):
        return None
    old, new = SYSTEM_SAN_TYPES[name]
    if not isinstance(ext, dict) or ext.get('san_types') != old:
        return None
    return json.dumps({**ext, 'san_types': new})


# -- 104: group permissions as lists --------------------------------------------------------
ADMIN_GROUP_SEEDED = 'Full system administrators with all permissions'
ADMIN_GROUP_NOW = 'Membership grants no rights: assign the Administrator role for full access'


def grantable_scopes():
    """The scopes a group may grant, or None to fall back on the structural filter."""
    try:
        from auth.permissions import GROUP_GRANTABLE_PERMISSIONS
        return set(GROUP_GRANTABLE_PERMISSIONS)
    except ImportError as e:
        logger.warning("Migration 104: %s; keeping only scoped, non-admin permissions", e)
        return None


def grantable_list(value, grantable=None):
    """*value* (list, JSON text, or JSON text of JSON text) as a list of the
    scopes a group may hold, or None when it is not a list."""
    for _ in range(3):
        if not isinstance(value, str):
            break
        try:
            value = json.loads(value)
        except ValueError:
            return None
    if not isinstance(value, list):
        return None
    return [p for p in value
            if isinstance(p, str) and ':' in p and '*' not in p and not p.startswith('admin:')
            and (grantable is None or p in grantable)]


# -- 105: the legacy ldap_* settings ----------------------------------------------------------

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


# -- 121: renewal schedule of ACME client orders ----------------------------------------------
REISSUE = """
    UPDATE acme_client_orders SET status = 'issued'
    WHERE status = 'valid'
      AND COALESCE(is_proxy_order, FALSE) = FALSE
      AND EXISTS (
          SELECT 1 FROM certificates
          WHERE certificates.id = acme_client_orders.certificate_id
            AND certificates.valid_to > CURRENT_TIMESTAMP
            AND COALESCE(certificates.revoked, FALSE) = FALSE
      )
      AND NOT EXISTS (
          SELECT 1 FROM acme_client_orders newer
          WHERE newer.id > acme_client_orders.id
            AND newer.status = 'issued'
            AND newer.domains = acme_client_orders.domains
            AND newer.environment = acme_client_orders.environment
            AND newer.certificate_id <> acme_client_orders.certificate_id
      )
"""

DROP_LEFTOVERS = """
    DELETE FROM acme_client_orders
    WHERE status = 'issued'
      AND COALESCE(is_proxy_order, FALSE) = FALSE
      AND EXISTS (
          SELECT 1 FROM acme_client_orders older
          WHERE older.id < acme_client_orders.id
            AND older.certificate_id = acme_client_orders.certificate_id
            AND older.order_url = acme_client_orders.order_url
            AND older.renewal_enabled = TRUE
            AND older.status = 'issued'
            AND older.last_renewal_at IS NOT NULL
      )
"""


# -- 150: the highest user id the database still names -----------------------------------------
TABLE = 'users'
# Columns that keep a user id after the account is gone, or until it is purged
REFERENCES = (
    ('user_sessions', 'user_id'), ('api_keys', 'user_id'), ('auth_certificates', 'user_id'),
    ('webauthn_credentials', 'user_id'), ('webauthn_challenges', 'user_id'),
    ('group_members', 'user_id'), ('pro_sso_sessions', 'user_id'),
    ('approval_requests', 'requester_id'), ('hsm_providers', 'created_by'),
    ('acme_eab_credentials', 'created_by_user_id'), ('acme_eab_credentials', 'revoked_by_user_id'),
    ('acme_dns_update_keys', 'created_by_user_id'),
)


def _ids_in_approvals(rows):
    """User ids named in the JSON approval lists of ``approval_requests``."""
    for (approvals,) in rows:
        try:
            entries = json.loads(approvals) if approvals else []
        except (TypeError, ValueError):
            continue
        for entry in entries if isinstance(entries, list) else []:
            value = entry.get('user_id') if isinstance(entry, dict) else None
            if isinstance(value, int) and not isinstance(value, bool):
                yield value


# Above the int4 range PostgreSQL's users sequence cannot take it: not an id it handed out
_MAX_ID = 2 ** 31 - 1


def _ids_in_audit(rows):
    """User ids in ``audit_logs.resource_id``: one id, or a comma list for a bulk delete."""
    for (value,) in rows:
        for part in (value or '').split(','):
            part = part.strip()
            if part.isascii() and part.isdigit() and int(part) <= _MAX_ID:
                yield int(part)


def highest_named(scalar, rows, has_column):
    """The highest user id the database still names anywhere (0 if none)."""
    highest = scalar(f"SELECT MAX(id) FROM {TABLE}") or 0
    for table, column in REFERENCES:
        if has_column(table, column):
            highest = max(highest, scalar(f"SELECT MAX({column}) FROM {table}") or 0)
    if has_column('approval_requests', 'approvals'):
        highest = max([highest, *_ids_in_approvals(rows("SELECT approvals FROM approval_requests"))])
    if has_column('audit_logs', 'resource_id') and has_column('audit_logs', 'resource_type'):
        highest = max([highest, *_ids_in_audit(rows(
            "SELECT resource_id FROM audit_logs WHERE resource_type = 'user'"))])
    return int(highest)


# -- 154: suspension records left behind a lifted hold ----------------------------------------
def ca_key(crt):
    """(subject, public key) of a stored CA certificate, None when unreadable."""
    try:
        cert = x509.load_pem_x509_certificate(base64.b64decode(crt))
        return cert.subject.public_bytes(), cert.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    except Exception:
        return None


def leftovers(candidates, ca_crt) -> list:
    """Ids of the ``(record id, record caref, row caref)`` candidates under the row's CA
    or a record of its subject and key; ``ca_crt(refid)`` reads a CA's certificate."""
    keys, ids = {}, []

    def key(refid):
        if refid not in keys:
            crt = ca_crt(refid)
            keys[refid] = ca_key(crt) if crt else None
        return keys[refid]
    for record_id, record_caref, row_caref in candidates:
        if record_caref is None or row_caref is None:
            continue
        if record_caref == row_caref or (key(row_caref) is not None and key(record_caref) == key(row_caref)):
            ids.append(record_id)
    return ids
