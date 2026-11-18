from . import bp, VALID_ROLES
from models import db, User
from utils.datetime_utils import utc_now
from datetime import timedelta
import tempfile
import os
import json
import logging
from .diagnostics import (
    MAX_NAMES, NAME_LENGTH, GroupSource, claim_candidates, saml_candidates, shown_list,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Shared lockout helpers (used by auth.py, auth_methods.py, sso/*)
# ============================================================================

# The settings screen's minimum: under it every login locks at its first failure
MIN_LOGIN_ATTEMPTS = 3


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
    return max(max_attempts, MIN_LOGIN_ATTEMPTS), lockout_seconds

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

    if not (provider.ldap_use_ssl or getattr(provider, 'ldap_start_tls', False)) and not verify_ssl:
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


def ldap_auto_bind(provider):
    """ldap3 auto_bind mode: StartTLS before the bind when chosen, so neither
    password crosses in clear (RFC 4513 §3, §5.1.3). LDAPS needs none."""
    import ldap3
    if getattr(provider, 'ldap_start_tls', False) and not provider.ldap_use_ssl:
        return ldap3.AUTO_BIND_TLS_BEFORE_BIND
    return ldap3.AUTO_BIND_NO_TLS


def ldap_bind(conn, provider):
    """Bind ``conn`` (not yet bound), after StartTLS when chosen. False if refused;
    a StartTLS or certificate failure raises before any bind is sent."""
    import ldap3
    from ldap3.core.exceptions import LDAPStartTLSError
    if ldap_auto_bind(provider) == ldap3.AUTO_BIND_TLS_BEFORE_BIND:
        conn.open(read_server_info=False)
        if not conn.start_tls(read_server_info=False):
            raise LDAPStartTLSError('StartTLS refused by the directory')
    return conn.bind()


def _encrypt_ldap_password(password: str) -> str:
    """Encrypt LDAP bind password if encryption is available."""
    if not password:
        return password
    from security.encryption import key_encryption
    if key_encryption.is_enabled:
        return key_encryption.encrypt_string(password)
    return password


def _decrypt_ldap_password(provider) -> str:
    """Decrypt LDAP bind password from provider config. A stored token this node's key
    does not open raises SecretUnreadable: ldap3 would bind anonymously without it."""
    from utils.encryption import decrypt_required
    if hasattr(provider, '_ldap_bind_password'):
        password = decrypt_required(provider._ldap_bind_password,
                                    f'SSO provider {provider.id} LDAP bind password')
    else:
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


def announce_account_locked(subject, username, max_attempts):
    """Log and alert a lock; called by the one attempt that armed it."""
    logger.warning(f"{subject} locked after {max_attempts} failed attempts")
    notify_account_locked(username)


def _reserve_ldap_attempt(user):
    """Count one LDAP attempt before the bind, on the local account the entry resolves to.

    Returns (account, rank, armed) as ``User.reserve_login_attempt``: account None when
    there is none (nothing is counted). Raises, rolled back, when the count fails."""
    if not user:
        return None, None, None
    max_attempts, lockout_seconds = _get_ldap_lockout_settings()
    try:
        rank, armed = user.reserve_login_attempt(max_attempts, lockout_seconds)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return user, rank, armed


def _ldap_attempt_failed(user, armed):
    """A refused or failed bind: the one attempt that armed the lock reports it."""
    if user is not None and armed:
        announce_account_locked(f'LDAP account {user.username}', user.username,
                                _get_ldap_lockout_settings()[0])


def _release_ldap_attempt(user, armed):
    """The bind proved the password but no session opens: the attempt that armed the lock
    lifts it and is not counted; any other stays counted (``User.release_login_attempt``)."""
    if user is None:
        return
    try:
        user.release_login_attempt(armed)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to release LDAP attempt for {user.username}: {e}")


def _clear_ldap_failed_attempts(user):
    """Clear the stored count and lock of the account a successful bind opens; False,
    rolled back, when that fails: no session opens, as at the password door."""
    if user is None:
        return True
    try:
        user.clear_failed_logins()
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to update login stats for {user.username}: {e}", exc_info=True)
        return False
    return True


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


def mapped_attributes(attr_mapping, field, available=None):
    """SSO attributes the mapping assigns to the UCM ``field``.

    The form stores ``{SSO attribute: UCM field}``; the legacy ``{UCM field: SSO
    attribute}`` is still read. A row whose two sides are both UCM field names is
    read the form's way when it involves ``groups``, or when its key is among the
    ``available`` attributes and its value is not; else the legacy way, the only
    one that ever logged anyone in.
    """
    if not isinstance(attr_mapping, dict):
        return ()
    available = set(available or ())
    form, legacy = {}, {}
    for key, val in attr_mapping.items():
        if not (isinstance(key, str) and isinstance(val, str) and key.strip() and val.strip()):
            continue
        key, val = key.strip(), val.strip()
        key_is_field, val_is_field = key in _MAPPING_FIELDS, val in _MAPPING_FIELDS
        if key_is_field and val_is_field:
            # `groups` has no legacy history: such a row is always the form's.
            as_form = 'groups' in (key, val) or (key in available and val not in available)
        elif val_is_field or key_is_field:
            as_form = val_is_field
        else:
            continue
        if as_form and val == field:
            form[key] = None
        elif not as_form and key == field:
            legacy[val] = None
    return tuple(form) or tuple(legacy)


def mapped_attribute(attr_mapping, field, default, available=None):
    """First SSO attribute mapped to ``field``, else ``default``."""
    names = mapped_attributes(attr_mapping, field, available)
    return names[0] if names else default


def _saml_group_attribute_names(attr_mapping, available=None):
    """SAML attributes mapped to ``groups``; empty when none is configured."""
    return mapped_attributes(attr_mapping, 'groups', available)


def oidc_identity(userinfo, attr_mapping):
    """(username, email, fullname) from OIDC userinfo through the attribute mapping."""
    userinfo = userinfo if isinstance(userinfo, dict) else {}

    def get(field, default):
        value = userinfo.get(mapped_attribute(attr_mapping, field, default, userinfo))
        return value if isinstance(value, str) else ''

    email = get('email', 'email')
    username = get('username', 'preferred_username') or (userinfo.get('email') or '').split('@')[0]
    return username, email, get('fullname', 'name')


def oidc_stable_id(userinfo):
    """The account's stable id in UserInfo: ``sub``, else (GitHub, not an OIDC provider) the
    numeric ``id``; never ``login`` nor the e-mail, which can pass to another person."""
    userinfo = userinfo if isinstance(userinfo, dict) else {}
    value = userinfo.get('sub')
    if value is None:
        value = userinfo.get('id')
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            return None
    value = str(value).strip()
    return value or None


def saml_identity(attrs, name_id, attr_mapping):
    """(username, email, fullname) from SAML attributes through the attribute mapping."""
    attrs = attrs if isinstance(attrs, dict) else {}

    def get(field, default):
        values = attrs.get(mapped_attribute(attr_mapping, field, default, attrs))
        if isinstance(values, (list, tuple)):
            values = values[0] if values else None
        return values.strip() if isinstance(values, str) else ''

    return get('username', 'username') or (name_id or '').strip(), \
        get('email', 'email'), get('fullname', 'name')


def _extract_saml_groups(attrs, attr_mapping=None):
    """Group / role values from a validated SAML assertion, for role mapping."""
    return saml_groups(attrs, attr_mapping)[0]


def saml_groups(attrs, attr_mapping=None, friendly_names=None):
    """``(values, GroupSource)`` of a validated SAML assertion, for role mapping.

    ``attrs`` is the ``{name: [values]}`` dict from the SAML library. When the
    attribute mapping assigns attributes to ``groups``, only those are read and
    the defaults in ``_SAML_GROUP_ATTRIBUTES`` are not. Attributes are read by Name
    only, never by FriendlyName (SAML Core 2.0 §2.7.3.1), which ``friendly_names``
    gives for the refusal diagnosis alone. Values are the non-empty ones,
    de-duplicated in assertion order, for the top-level ``groups`` key.
    """
    attrs = attrs if isinstance(attrs, dict) else {}
    configured = _saml_group_attribute_names(attr_mapping, attrs)
    looked_for = configured or _SAML_GROUP_ATTRIBUTES
    groups = {}  # insertion-ordered set
    sources = []
    for name in looked_for:
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
    names = sources or looked_for
    label = (f"SAML attribute{'s' if len(names) > 1 else ''} "
             f"{shown_list(names, MAX_NAMES, NAME_LENGTH)}")
    candidates = None if groups else saml_candidates(attrs, friendly_names, exclude=looked_for)
    return list(groups), GroupSource(label, candidates, 'attributes')


# Highest privilege first — multi-match resolution picks the greatest (#221).
_ROLE_PRIVILEGE = {'admin': 3, 'operator': 2, 'auditor': 1, 'viewer': 0}


def _find_custom_role(name):
    """The non-system custom role called ``name`` (names are unique, case-insensitively)."""
    from models.rbac import CustomRole
    if not isinstance(name, str) or not name.strip():
        return None
    return CustomRole.query.filter(
        db.func.lower(CustomRole.name) == name.strip().lower(),
        CustomRole.is_system.isnot(True)).first()


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


def validate_role_mapping(value, provider_type=None):
    """Check a role_mapping at save time. Returns ``(normalized_dict, error)``.

    Rows with no key and no value (blank editor rows) are dropped; a key is
    saved without its edge spaces. Two keys the provider compares equal are refused.
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
    cleaned, seen = {}, set()
    match_key = _group_match_key_of(provider_type)
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
        name = group.strip()
        if match_key(name) in seen:
            return None, f"role_mapping has two entries for the external group '{name}'"
        seen.add(match_key(name))
        cleaned[name] = entry
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


def _mapping_rules(provider):
    """The provider's role_mapping as a dict; empty when it has no rule."""
    rules = _parse_json_field(provider.role_mapping)
    return rules if isinstance(rules, dict) else {}


def _external_groups(external_data):
    """Values of ``roles`` and ``groups`` together, de-duplicated: an IdP may
    send app roles and groups side by side, and an empty one hides nothing."""
    data = external_data if isinstance(external_data, dict) else {}
    values = {}  # insertion-ordered set
    for key in ('roles', 'groups'):
        found = data.get(key)
        if isinstance(found, str):
            found = [found]
        if isinstance(found, (list, tuple, set)):
            values.update((v, None) for v in found if isinstance(v, str))
    return list(values)


def _entra_oidc_groups_overage(id_claims):
    """Whether Entra ID left ``groups`` out of the ID token for too many groups."""
    names = id_claims.get('_claim_names')
    return (isinstance(names, dict) and 'groups' in names) or id_claims.get('hasgroups') is True


def _claim_lookup(data, name):
    """The value of claim ``name``: the claim of that exact name, else a dotted path
    through nested objects (a key may itself hold dots); ``_MISSING`` when neither."""
    if not isinstance(data, dict):
        return _MISSING
    if name in data:
        return data[name]
    dots = [i for i, ch in enumerate(name) if ch == '.']
    for i in reversed(dots):  # the longest key first
        inner = data.get(name[:i])
        if isinstance(inner, dict):
            found = _claim_lookup(inner, name[i + 1:])
            if found is not _MISSING:
                return found
    return _MISSING


_MISSING = object()


def claim_groups(data, name):
    """Groups of the claim an attribute mapping row assigns to ``groups``: a string
    or a list of strings; any other value gives none."""
    value = _claim_lookup(data, name)
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return list(value)
    return []


def oidc_groups(userinfo, id_claims, token_unused=None, attr_mapping=None):
    """``(values, GroupSource)`` of an OIDC login: those of its UserInfo response and of
    the ID token bound to it (``None`` when none is, ``token_unused`` saying why).
    Claims the attribute mapping assigns to ``groups`` replace ``roles`` and ``groups``."""
    id_claims = id_claims if isinstance(id_claims, dict) else {}
    userinfo = userinfo if isinstance(userinfo, dict) else {}
    configured = mapped_attributes(attr_mapping, 'groups', set(userinfo) | set(id_claims))
    sources = [('UserInfo', userinfo)]
    if token_unused is None:
        sources.insert(0, ('ID token', id_claims))
    merged, counts = {}, []
    for label, data in sources:
        if configured:
            values = [v for name in configured for v in claim_groups(data, name)]
        else:
            values = _external_groups(data)
        counts.append(f"{label} ({len(values)} value(s))")
        merged.update((v, None) for v in values)
    unused = f"; ID token not used: {token_unused}" if token_unused is not None else ''
    claims = f" claim {', '.join(configured)}" if configured else ''
    logger.info(f"OIDC groups read from {', '.join(counts)}{claims}{unused}")
    if _entra_oidc_groups_overage(id_claims):
        logger.warning(
            "OIDC ID token has no groups claim: Entra ID left it out because the user "
            "has too many groups. Emit only the groups assigned to the application, "
            "or app roles, so role mapping can match.")
    names = configured or ('roles', 'groups')
    where = ' and '.join(('the ID token' if label == 'ID token' else label) for label, _ in sources)
    label = (f"{where}, claim{'s' if len(names) > 1 else ''} "
             f"{shown_list(names, MAX_NAMES, NAME_LENGTH)}")
    if token_unused is not None:
        label += f" (ID token not used: {token_unused})"
    candidates = None if merged else claim_candidates(*(data for _, data in sources), exclude=names)
    return list(merged), GroupSource(label, candidates, 'claims')


def oidc_external_groups(userinfo, id_claims, token_unused=None, attr_mapping=None):
    """Group values of an OIDC login (see :func:`oidc_groups`)."""
    return oidc_groups(userinfo, id_claims, token_unused, attr_mapping)[0]


def _group_match_key_of(provider_type):
    if provider_type == 'ldap':
        # str.split() takes every separator RFC 4518 §2.2 maps to SPACE
        return lambda name: ' '.join(str(name).split()).casefold()
    return lambda name: name


def group_match_key(provider):
    """How a rule key and a group name compare. LDAP: close to what cn does, caseIgnoreMatch
    (RFC 4519 §2.3; RFC 4517 §4.2.11 with RFC 4518 §2.6.1): case, edge spaces and the
    length of inner space runs ignored. OIDC and SAML groups are opaque identifiers: exact."""
    return _group_match_key_of(getattr(provider, 'provider_type', None))


def _external_group_keys(provider, external_data):
    key = group_match_key(provider)
    return [key(g) for g in _external_groups(external_data)]


def sso_admission(provider, external_data):
    """Whether a login may proceed. With mapping rules, only a user one of them
    matches; without rules, every user gets the default role, and no default
    role admits nobody (no implicit role)."""
    rules = _mapping_rules(provider)
    if rules:
        key = group_match_key(provider)
        groups = _external_group_keys(provider, external_data)
        return any(key(rule) in groups for rule in rules)
    return provider.default_role in VALID_ROLES


def _resolve_mapped_roles(provider, external_data):
    """``(base_role, custom_role)`` the role_mapping gives, either may be None.

    Base role: the highest-privilege one among matching entries (admin >
    operator > auditor > viewer, #221). Custom role: the first matching entry,
    in mapping order, that names one. An invalid base role counts as viewer
    (as before) and an unknown custom role is ignored, both with a warning.
    """
    role_mapping = _mapping_rules(provider)
    if not role_mapping:
        return None, None
    external_roles = _external_groups(external_data)
    logger.info(f"Role resolution: {len(role_mapping)} rule(s), external groups "
                f"({len(external_roles)}): {shown_list(external_roles)}")
    key = group_match_key(provider)
    external_keys = _external_group_keys(provider, external_data)
    bases, customs = [], []
    for ext_role, value in role_mapping.items():
        if key(ext_role) not in external_keys:
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
