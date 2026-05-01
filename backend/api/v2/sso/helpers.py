from . import bp, VALID_ROLES
from models import db, User
from utils.datetime_utils import utc_now
from datetime import timedelta
import tempfile
import os
import json
import logging

logger = logging.getLogger(__name__)

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

    return None


def _encrypt_ldap_password(password: str) -> str:
    """Encrypt LDAP bind password if encryption is available."""
    if not password:
        return password
    try:
        from security.encryption import key_encryption
        if key_encryption.is_enabled:
            return key_encryption.encrypt_string(password)
    except ImportError:
        pass
    return password


def _decrypt_ldap_password(provider) -> str:
    """Decrypt LDAP bind password from provider config."""
    password = provider.ldap_bind_password
    if not password:
        return password
    try:
        from security.encryption import key_encryption
        if key_encryption.is_enabled:
            return key_encryption.decrypt_string(password)
    except ImportError:
        pass
    return password


def _parse_json_field(value):
    """Parse a JSON field that may be a string, double-encoded string, or dict/list."""
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, str):
                parsed = json.loads(parsed)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


# LDAP brute-force protection (reuses User model's lockout fields)
# Settings read from DB config via _get_lockout_settings in auth.py


def _get_ldap_lockout_settings():
    """Read lockout settings from DB config, fallback to defaults"""
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
        db.session.commit()
    return False


def _record_ldap_failed_attempt(username):
    """Record a failed LDAP login attempt."""
    user = User.query.filter_by(username=username).first()
    if not user:
        return
    max_attempts, lockout_seconds = _get_ldap_lockout_settings()
    user.failed_logins = (user.failed_logins or 0) + 1
    if user.failed_logins >= max_attempts:
        user.locked_until = utc_now() + timedelta(seconds=lockout_seconds)
        logger.warning(f"LDAP account locked for {username} after {max_attempts} failed attempts")
    db.session.commit()


def _clear_ldap_failed_attempts(username):
    """Clear failed attempt counters on successful login."""
    user = User.query.filter_by(username=username).first()
    if user and (user.failed_logins or user.locked_until):
        user.failed_logins = 0
        user.locked_until = None
        db.session.commit()


def _resolve_role_from_mapping(provider, external_data):
    """Try to resolve a role from the configured role_mapping.

    Returns the mapped UCM role (str) when one of the user's external
    groups matches an entry in ``provider.role_mapping``. Returns ``None``
    when no mapping is configured or no group matches — the caller is
    then responsible for deciding whether to fall back to ``default_role``
    (creation only) or to keep the stored role (existing user, see #81).
    """
    role_mapping = _parse_json_field(provider.role_mapping)
    if not role_mapping:
        return None
    external_roles = external_data.get('roles', external_data.get('groups', []))
    if isinstance(external_roles, str):
        external_roles = [external_roles]
    logger.info(f"Role resolution: mapping={role_mapping}, external_groups={external_roles}")
    for ext_role, ucm_role in role_mapping.items():
        if ext_role in external_roles:
            resolved = ucm_role if ucm_role in VALID_ROLES else 'viewer'
            logger.info(f"Role resolved via mapping: {ext_role} -> {resolved}")
            return resolved
    return None


def _resolve_role(provider, external_data):
    """Resolve user role for **user creation** — uses role_mapping then
    falls back to ``default_role``. Do NOT use this on existing users:
    that behaviour caused #81 (UI role overwritten on every SSO login).
    For existing users, use :func:`_resolve_role_from_mapping` and check
    ``provider.sync_role_on_login``.
    """
    mapped = _resolve_role_from_mapping(provider, external_data)
    if mapped is not None:
        return mapped
    fallback = provider.default_role if provider.default_role in VALID_ROLES else 'viewer'
    logger.info(f"Role resolved via default_role: {fallback}")
    return fallback
