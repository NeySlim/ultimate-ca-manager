from . import bp, VALID_ROLES
from models import db, User
from utils.datetime_utils import utc_now
from datetime import timedelta
import tempfile
import os
import json
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# Shared lockout helpers (used by auth.py, auth_methods.py, sso/*)
# ============================================================================

def _get_lockout_settings():
    """Read lockout settings from DB config, fallback to defaults.
    
    Returns:
        tuple: (max_attempts, lockout_seconds)
    """
    from models import SystemConfig
    try:
        max_cfg = SystemConfig.query.filter_by(key='max_login_attempts').first()
        dur_cfg = SystemConfig.query.filter_by(key='lockout_duration').first()
        max_attempts = int(max_cfg.value) if max_cfg and max_cfg.value else 5
        lockout_seconds = int(dur_cfg.value) if dur_cfg and dur_cfg.value else 900
    except Exception:
        max_attempts = 5
        lockout_seconds = 900
    return max_attempts, lockout_seconds

def _get_ssl_verify(provider, protocol):
    """Get SSL verification parameter for requests library.

    Returns:
        False if verify_ssl is disabled
        str (temp file path) if ca_bundle PEM is configured
        True otherwise (use default certifi bundle)
    """
    verify_ssl = getattr(provider, f'{protocol}_verify_ssl', None)
    if verify_ssl is False or verify_ssl == 0:
        return False

    ca_bundle = getattr(provider, f'{protocol}_ca_bundle', None)
    if ca_bundle:
        fd, path = tempfile.mkstemp(suffix='.pem', prefix='ucm_sso_ca_')
        try:
            os.write(fd, ca_bundle.encode('utf-8') if isinstance(ca_bundle, str) else ca_bundle)
        finally:
            os.close(fd)
        return path

    return True


def _cleanup_ssl_verify(verify_param):
    """Clean up temp CA bundle file if one was created."""
    if isinstance(verify_param, str) and verify_param.startswith(tempfile.gettempdir()):
        try:
            os.unlink(verify_param)
        except OSError:
            pass


def _build_ldap_tls(provider):
    """Build ldap3 Tls object based on provider SSL settings."""
    import ssl
    verify_ssl = provider.ldap_verify_ssl if provider.ldap_verify_ssl is not None else True

    if not provider.ldap_use_ssl and not verify_ssl:
        return None

    if not verify_ssl:
        return __import__('ldap3').Tls(validate=ssl.CERT_NONE)

    ca_bundle = provider.ldap_ca_bundle
    if ca_bundle:
        fd, ca_path = tempfile.mkstemp(suffix='.pem', prefix='ucm_ldap_ca_')
        try:
            os.write(fd, ca_bundle.encode('utf-8') if isinstance(ca_bundle, str) else ca_bundle)
        finally:
            os.close(fd)
        return __import__('ldap3').Tls(ca_certs_file=ca_path, validate=ssl.CERT_REQUIRED)

    # verify requested but no explicit CA bundle: validate against the system trust store
    # (CERT_REQUIRED) rather than returning None, which would leave ldap3 on its default
    # unvalidated TLS — i.e. a "verify SSL" setting that silently doesn't verify.
    return __import__('ldap3').Tls(validate=ssl.CERT_REQUIRED)


def _encrypt_ldap_password(password: str) -> str:
    """Encrypt LDAP bind password if encryption is available."""
    if not password:
        return password
    from security.encryption import key_encryption
    if key_encryption.is_enabled:
        return key_encryption.encrypt_string(password)
    return password


def _decrypt_ldap_password(provider) -> str:
    """Decrypt LDAP bind password from provider config."""
    password = provider.ldap_bind_password
    if not password:
        return password
    from security.encryption import key_encryption
    if key_encryption.is_enabled:
        return key_encryption.decrypt_string(password)
    return password


def _parse_group_list(value):
    """Parse a group list field: JSON array, dict (legacy), or comma-separated string."""
    if not value:
        return []
    if isinstance(value, dict):
        return [str(g).strip() for g in value.keys() if str(g).strip()]
    if isinstance(value, list):
        return [str(g).strip() for g in value if str(g).strip()]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, (list, dict)):
                return _parse_group_list(parsed)
        except (json.JSONDecodeError, TypeError):
            pass
        return [g.strip() for g in value.split(',') if g.strip()]
    return []


def _parse_json_field(value):
    """Parse a JSON field that may be a string, double-encoded string, or dict/list."""
    if not value:
        return {}
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, str):
                parsed = json.loads(parsed)
            return parsed if isinstance(parsed, (dict, list)) else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


# LDAP brute-force protection (reuses User model's lockout fields)
# Settings read from DB config via _get_lockout_settings above


def _get_ldap_lockout_settings():
    """Read lockout settings from DB config, fallback to defaults.
    Uses shared function from helpers.
    """
    return _get_lockout_settings()


def _check_ldap_lockout(username):
    """Check if account is locked due to failed LDAP attempts."""
    user = User.query.filter_by(username=username).first()
    if not user:
        return False
    if user.locked_until:
        if utc_now() < user.locked_until:
            return True
        user.locked_until = None
        user.failed_logins = 0
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to clear LDAP lockout: {e}")
    return False


def notify_account_locked(username):
    """Send the account_locked security alert; never fails the login."""
    try:
        from services.notification_service import NotificationService
        from utils.trusted_proxy import client_ip
        NotificationService.on_security_alert(
            alert_type='account_locked',
            username=username,
            ip_address=client_ip() or 'unknown',
        )
    except Exception as e:
        logger.warning(f"Failed to send account_locked alert for {username}: {e}")


def _record_ldap_failed_attempt(username):
    """Record a failed LDAP login attempt."""
    user = User.query.filter_by(username=username).first()
    if not user:
        return
    max_attempts, lockout_seconds = _get_ldap_lockout_settings()
    user.failed_logins = (user.failed_logins or 0) + 1
    locked = user.failed_logins >= max_attempts
    if locked:
        user.locked_until = utc_now() + timedelta(seconds=lockout_seconds)
        logger.warning(f"LDAP account locked for {username} after {max_attempts} failed attempts")
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to record LDAP failed attempt for {username}: {e}")
        return
    if locked:
        notify_account_locked(username)


def _clear_ldap_failed_attempts(username):
    """Clear failed attempt counters on successful login."""
    user = User.query.filter_by(username=username).first()
    if user and (user.failed_logins or user.locked_until):
        user.failed_logins = 0
        user.locked_until = None
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to clear LDAP failed attempts for {username}: {e}")


# SAML attributes read for group membership when the provider's attribute
# mapping names none: the plain name, and the claim URIs Microsoft Entra ID
# (groups, app roles) and AD FS send by default.
_SAML_GROUP_ATTRIBUTES = (
    'groups',
    'http://schemas.microsoft.com/ws/2008/06/identity/claims/groups',
    'http://schemas.microsoft.com/ws/2008/06/identity/claims/role',
    'http://schemas.xmlsoap.org/claims/Group',
)
# Sent by Entra ID in place of the groups claim when the user has too many groups.
_ENTRA_GROUPS_OVERAGE = 'http://schemas.microsoft.com/claims/groups.link'
# UCM fields an attribute mapping row can target.
_MAPPING_FIELDS = ('username', 'email', 'fullname', 'groups')


def mapped_attributes(attr_mapping, field):
    """SSO attributes the mapping assigns to the UCM ``field``.

    The form stores ``{SSO attribute: UCM field}``; the legacy shape
    ``{UCM field: SSO attribute}`` is accepted when no row targets ``field``
    and the value is not itself a UCM field name. Malformed entries are ignored.
    """
    if not isinstance(attr_mapping, dict):
        return ()
    names = {}
    for key, val in attr_mapping.items():
        if (isinstance(key, str) and key.strip() and isinstance(val, str)
                and val.strip() == field):
            names[key.strip()] = None
    if names:
        return tuple(names)
    legacy = attr_mapping.get(field)
    if isinstance(legacy, str) and legacy.strip() and legacy.strip() not in _MAPPING_FIELDS:
        return (legacy.strip(),)
    return ()


def mapped_attribute(attr_mapping, field, default):
    """First SSO attribute mapped to ``field``, else ``default``."""
    names = mapped_attributes(attr_mapping, field)
    return names[0] if names else default


def _saml_group_attribute_names(attr_mapping):
    """SAML attributes mapped to ``groups``; empty when none is configured."""
    return mapped_attributes(attr_mapping, 'groups')


def oidc_identity(userinfo, attr_mapping):
    """(username, email, fullname) from OIDC userinfo through the attribute mapping."""
    userinfo = userinfo if isinstance(userinfo, dict) else {}

    def get(field, default):
        value = userinfo.get(mapped_attribute(attr_mapping, field, default))
        return value if isinstance(value, str) else ''

    email = get('email', 'email')
    username = get('username', 'preferred_username') or (userinfo.get('email') or '').split('@')[0]
    return username, email, get('fullname', 'name')


def saml_identity(attrs, name_id, attr_mapping):
    """(username, email, fullname) from SAML attributes through the attribute mapping."""
    attrs = attrs if isinstance(attrs, dict) else {}

    def get(field, default):
        values = attrs.get(mapped_attribute(attr_mapping, field, default))
        if isinstance(values, (list, tuple)):
            values = values[0] if values else None
        return values.strip() if isinstance(values, str) else ''

    return get('username', 'username') or (name_id or '').strip(), \
        get('email', 'email'), get('fullname', 'name')


def _extract_saml_groups(attrs, attr_mapping=None):
    """Group / role values from a validated SAML assertion, for role mapping.

    ``attrs`` is the ``{name: [values]}`` dict from the SAML library. When the
    attribute mapping assigns attributes to ``groups``, only those are read and
    the defaults in ``_SAML_GROUP_ATTRIBUTES`` are not. Returns the non-empty
    values, de-duplicated in assertion order, for the top-level ``groups`` key
    that ``_resolve_role_from_mapping`` reads.
    """
    attrs = attrs if isinstance(attrs, dict) else {}
    configured = _saml_group_attribute_names(attr_mapping)
    groups = {}  # insertion-ordered set
    sources = []
    for name in configured or _SAML_GROUP_ATTRIBUTES:
        values = attrs.get(name)
        if values is None:
            continue
        if isinstance(values, str):
            values = [values]
        before = len(groups)
        for value in values:
            value = str(value).strip() if value is not None else ''
            if value:
                groups[value] = None
        if len(groups) > before:
            sources.append(name)

    if sources:
        logger.info(f"SAML groups read from {', '.join(sources)} ({len(groups)} value(s))")
    elif configured:
        logger.info(f"SAML group attribute {', '.join(configured)} not in the assertion")
    if not groups and _ENTRA_GROUPS_OVERAGE in attrs:
        logger.warning(
            "SAML assertion has no groups: Entra ID sent groups.link because the user "
            "has too many groups. Emit only the groups assigned to the application, "
            "or app roles, so role mapping can match.")
    return list(groups)


# Highest privilege first — multi-match resolution picks the greatest (#221).
_ROLE_PRIVILEGE = {'admin': 3, 'operator': 2, 'auditor': 1, 'viewer': 0}


def _find_custom_role(name):
    """The custom role called ``name`` (names are unique, case-insensitively), or None."""
    from models.rbac import CustomRole
    if not isinstance(name, str) or not name.strip():
        return None
    return CustomRole.query.filter(
        db.func.lower(CustomRole.name) == name.strip().lower()).first()


def _split_mapping_value(value):
    """``(base_role, custom_role_name)`` of a role_mapping value; either may be None.

    A string is a base role; an object carries ``role`` and/or ``custom_role``.
    """
    if isinstance(value, dict):
        return value.get('role') or None, value.get('custom_role') or None
    return (value or None), None


def mapped_custom_role_names(role_mapping):
    """Custom role names a role_mapping refers to."""
    return {name for name in (_split_mapping_value(v)[1] for v in (role_mapping or {}).values())
            if isinstance(name, str)}


def validate_role_mapping(value):
    """Check a role_mapping at save time. Returns ``(normalized_dict, error)``.

    Rows with no key and no value (blank editor rows) are dropped.
    """
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return None, "role_mapping is not valid JSON"
    if value is None:
        return {}, None
    if not isinstance(value, dict):
        return None, "role_mapping must be an object mapping external groups to roles"
    cleaned = {}
    for group, entry in value.items():
        blank = entry in (None, '', {}) or (isinstance(entry, dict) and not any(entry.values()))
        if not isinstance(group, str) or not group.strip():
            if blank:
                continue
            return None, "role_mapping has an entry without an external group name"
        if isinstance(entry, dict):
            if set(entry) - {'role', 'custom_role'}:
                return None, f"role_mapping entry '{group}' has unknown keys (allowed: role, custom_role)"
        elif not isinstance(entry, str):
            return None, f"role_mapping entry '{group}' must be a role name or an object"
        role, custom = _split_mapping_value(entry)
        if role is not None and (not isinstance(role, str) or role not in VALID_ROLES):
            return None, (f"role_mapping entry '{group}': invalid role '{role}'. "
                          f"Must be one of: {', '.join(sorted(VALID_ROLES))}")
        if custom is not None:
            if not isinstance(custom, str) or _find_custom_role(custom) is None:
                return None, f"role_mapping entry '{group}': custom role '{custom}' does not exist"
        if role is None and custom is None:
            return None, f"role_mapping entry '{group}' needs a role or a custom role"
        cleaned[group] = entry
    return cleaned, None


def providers_using_custom_role(name):
    """Names of the SSO providers whose role_mapping cites the custom role ``name``."""
    from models.sso import SSOProvider
    wanted = (name or '').strip().lower()
    users = []
    for provider in SSOProvider.query.all():
        cited = mapped_custom_role_names(_parse_json_field(provider.role_mapping))
        if any(c.strip().lower() == wanted for c in cited):
            users.append(provider.name)
    return users


def _resolve_mapped_roles(provider, external_data):
    """``(base_role, custom_role)`` the role_mapping gives, either may be None.

    Base role: the highest-privilege one among matching entries (admin >
    operator > auditor > viewer, #221). Custom role: the first matching entry,
    in mapping order, that names one. An invalid base role counts as viewer
    (as before) and an unknown custom role is ignored, both with a warning.
    """
    role_mapping = _parse_json_field(provider.role_mapping)
    if not role_mapping or not isinstance(role_mapping, dict):
        return None, None
    external_roles = external_data.get('roles', external_data.get('groups', []))
    if isinstance(external_roles, str):
        external_roles = [external_roles]
    logger.info(f"Role resolution: mapping={role_mapping}, external_groups={external_roles}")
    bases, customs = [], []
    for ext_role, value in role_mapping.items():
        if ext_role not in external_roles:
            continue
        base, custom_name = _split_mapping_value(value)
        if base is not None:
            if isinstance(base, str) and base in VALID_ROLES:
                bases.append((base, ext_role))
            else:
                logger.warning(f"Role mapping for '{ext_role}': invalid role {base!r}, using viewer")
                bases.append(('viewer', ext_role))
        if custom_name is not None:
            custom = _find_custom_role(custom_name)
            if custom is not None:
                customs.append((custom, ext_role))
            else:
                logger.warning(f"Role mapping for '{ext_role}': ignoring unknown custom role {custom_name!r}")
    resolved = custom = None
    if bases:
        resolved, ext_role = max(bases, key=lambda m: _ROLE_PRIVILEGE[m[0]])
        logger.info(f"Role resolved via mapping: {ext_role} -> {resolved} (highest privilege of {len(bases)} match(es))")
    if customs:
        custom = customs[0][0]
        if len({c.id for c, _ in customs}) > 1:
            logger.warning(f"Role mapping: several custom roles match, using '{custom.name}' "
                           f"(first in mapping order)")
    return resolved, custom


def _resolve_role_from_mapping(provider, external_data):
    """Base role from the role_mapping, or ``None`` when none applies.

    ``None`` means the caller decides: ``default_role`` at creation, the stored
    role for an existing user (#81).
    """
    return _resolve_mapped_roles(provider, external_data)[0]


def _resolve_role(provider, external_data, mapped=None):
    """Resolve user role for **user creation** — uses role_mapping then
    falls back to ``default_role``. Do NOT use this on existing users:
    that behaviour caused #81 (UI role overwritten on every SSO login).
    For existing users, use :func:`_resolve_role_from_mapping` and check
    ``provider.sync_role_on_login``. ``mapped`` is an already resolved base role.
    """
    if mapped is None:
        mapped = _resolve_role_from_mapping(provider, external_data)
    if mapped is not None:
        return mapped
    fallback = provider.default_role if provider.default_role in VALID_ROLES else 'viewer'
    logger.info(f"Role resolved via default_role: {fallback}")
    return fallback
