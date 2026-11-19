"""
Microsoft AD CS API routes
CRUD for MS CA connections + CSR signing + request status tracking
"""

import logging
from flask import Blueprint, request, g
from auth.unified import require_auth, has_permission as _has_perm
from services.settings_registry import as_boolean_word
from utils.secret_target import (MASKS, SECRET_TARGET_MESSAGE, changed_targets, keeps_saved_secret,
                                 retarget_error)
from utils.response import success_response, error_response, created_response, no_content_response
from models import db
from models.msca import MicrosoftCA, MSCARequest, basic_password_reaches
from services.msca_service import MicrosoftCAService
from services.msca.connection import saved_credential_retargets
from services.msca.client_keytab import managed_keytab_error
from services.msca.requests import (MSCASignedElsewhere, SIGNED_MEANWHILE_MESSAGE, SUPERSEDED,
                                    SUPERSEDED_MESSAGE, msca_may_write_clause, supersede)
from services.audit import AuditService
from utils.datetime_utils import utc_now
from utils.db_transaction import safe_commit
import fips_mode
from utils import key_algorithms
from utils.key_type import MIN_RSA_BITS
from services.trust_store.constants import KEY_TYPES
from cryptography.hazmat.primitives.asymmetric import rsa

logger = logging.getLogger(__name__)

bp = Blueprint('microsoft_cas', __name__, url_prefix='/api/v2/microsoft-cas')

# --- Limits ----------------------------------------------------------------
# These cap user-supplied PEM/keytab inputs to keep a single CRUD call from
# pushing megabytes of garbage into an encrypted Text column.
MAX_PEM_FIELD_BYTES = 64 * 1024     # 64 KB — enough for cert + chain
MAX_KEYTAB_PATH_LEN = 4096          # filesystem path
MAX_NAME_LEN = 100
MAX_SERVER_LEN = 500
MAX_TEMPLATE_LEN = 200


def _check_size(name: str, value, limit: int):
    """Return error_response() tuple if value exceeds limit, else None."""
    if value is None:
        return None
    if isinstance(value, str) and len(value.encode('utf-8')) > limit:
        return error_response(f"{name} exceeds maximum size ({limit} bytes)", 413)
    return None


def _clean_crl_url(raw):
    """Validate a user-supplied CRL URL. Returns (value_or_None, error_response_or_None)."""
    if not isinstance(raw, str):
        return None, error_response("crl_url must be a string", 400)
    url = raw.strip()
    if not url:
        return None, None
    if len(url) > MAX_SERVER_LEN:
        return None, error_response(f"crl_url too long (max {MAX_SERVER_LEN})", 400)
    if not url.lower().startswith(('http://', 'https://')):
        return None, error_response("crl_url must be an http(s) URL", 400)
    try:
        from utils.ssrf_protection import validate_url_not_cloud_metadata
        validate_url_not_cloud_metadata(url)
    except ValueError as e:
        return None, error_response(f"Invalid crl_url: {e}", 400)
    return url, None


_WINRM_TRANSPORTS = ('kerberos', 'ntlm')


def _winrm_transport_error(data):
    tr = (data.get('winrm_transport') or '').strip().lower()
    if tr not in _WINRM_TRANSPORTS:
        return error_response(f"winrm_transport must be one of {_WINRM_TRANSPORTS}", 400)
    if tr == 'ntlm':
        # Returned, not raised: the callers turn exceptions into a 500
        try:
            fips_mode.refuse('NTLM for the WinRM channel')
        except fips_mode.FipsRestricted as e:
            return error_response(str(e), 400, problem_type=fips_mode.PROBLEM_TYPE)
    return None


def _apply_winrm_fields(msca, data):
    """Apply WinRM admin-channel fields from request data. Returns error_response or None."""
    if 'winrm_enabled' in data:
        msca.winrm_enabled = bool(data['winrm_enabled'])
    if 'winrm_host' in data:
        msca.winrm_host = (data['winrm_host'] or '').strip() or None
    if 'winrm_port' in data:
        try:
            port = int(data['winrm_port'])
        except (TypeError, ValueError):
            return error_response("winrm_port must be an integer", 400)
        if not (1 <= port <= 65535):
            return error_response("winrm_port out of range", 400)
        msca.winrm_port = port
    for key in ('winrm_use_ssl', 'winrm_verify_ssl'):
        if key in data:
            word = as_boolean_word(data[key])
            if word is None:
                return error_response(f"{key} must be a boolean", 400)
            setattr(msca, key, word == 'true')
    if 'winrm_transport' in data:
        err = _winrm_transport_error(data)
        if err:
            return err
        msca.winrm_transport = (data['winrm_transport'] or '').strip().lower()
    if 'winrm_username' in data:
        msca.winrm_username = (data['winrm_username'] or '').strip() or None
    if 'winrm_password' in data:
        password = data['winrm_password']
        if password is not None and not isinstance(password, str):
            return error_response("winrm_password must be a string", 400)
        if (password or '').strip() not in MASKS:
            msca.winrm_password = password or None
    if 'ca_config' in data:
        cfg = (data['ca_config'] or '').strip()
        if cfg and any(c in cfg for c in '"\r\n`$;|&'):
            return error_response("ca_config contains invalid characters", 400)
        msca.ca_config = cfg or None
    return None


_WINRM_OVERRIDE_FIELDS = ('winrm_enabled', 'winrm_host', 'winrm_port', 'winrm_use_ssl',
                          'winrm_verify_ssl', 'winrm_transport', 'winrm_username',
                          'winrm_password', 'ca_config')


# Kerberos credentials a channel test may override: the keytab and the principal it signs in as
_WINRM_KERBEROS_FIELDS = ('kerberos_principal', 'kerberos_keytab_path')

KERBEROS_ADMIN_MESSAGE = ('Setting a Kerberos keytab or principal, or moving a connection or test '
                          'that uses one, requires the admin:system permission')
_CERTSRV_TARGET_FIELDS = ('server', 'use_ssl', 'verify_ssl', 'ca_bundle')


def _text(value):
    return value.strip() if isinstance(value, str) else (value or '')


def _kerberos_forbidden():
    """403 unless the caller holds admin:system: a keytab path names a credential the server reads itself."""
    if _has_perm('admin:system', getattr(g, 'permissions', None) or []):
        return None
    return error_response(KERBEROS_ADMIN_MESSAGE, 403)


def _saved_kerberos(msca):
    return (_text(msca.kerberos_principal), _text(msca.kerberos_keytab_path))


def _kerberos_after(msca, data):
    """(principal, keytab) the connection would hold or use with ``data`` applied, or None off Kerberos."""
    method = data.get('auth_method', msca.auth_method if msca else 'certificate')
    if method != 'kerberos':
        return None
    saved = _saved_kerberos(msca) if msca and msca.auth_method == 'kerberos' else ('', '')
    return tuple(_text(data[field]) if field in data else value
                 for field, value in zip(('kerberos_principal', 'kerberos_keytab_path'), saved))


def _kerberos_save_forbidden(msca, data):
    """A save that sets or changes a keytab or principal, or moves a connection holding one."""
    after = _kerberos_after(msca, data)
    if after is None:
        return None
    saved = _saved_kerberos(msca) if msca and msca.auth_method == 'kerberos' else ('', '')
    moved = msca is not None and any(saved) and (
        changed_targets({k: getattr(msca, k) for k in _CERTSRV_TARGET_FIELDS}, data)
        or changed_targets(_winrm_target_fields(msca), data))
    return _kerberos_forbidden() if after != saved or moved else None


def _kerberos_test_forbidden(msca, data):
    """A test that uses a keytab or principal other than the saved ones, or toward another target."""
    after = _kerberos_after(msca, data)
    if not after or not any(after):
        return None
    if msca is not None and after == _saved_kerberos(msca) and not changed_targets(
            {k: getattr(msca, k) for k in _CERTSRV_TARGET_FIELDS + ('auth_method',)}, data):
        return None
    return _kerberos_forbidden()


def _winrm_channel(cfg):
    """Where and as whom the channel signs in, as _build_session derives it."""
    use_ssl = bool(cfg.winrm_use_ssl)
    transport = (cfg.winrm_transport or 'kerberos').lower()
    account = cfg.winrm_username or (cfg.username if cfg.auth_method == 'basic' else None)
    if transport == 'kerberos':
        account = account or cfg.kerberos_principal
    return {'winrm_host': (cfg.winrm_host or cfg.server or '').strip().lower(),
            'winrm_port': cfg.winrm_port or (5986 if use_ssl else 5985),
            'winrm_use_ssl': use_ssl, 'winrm_verify_ssl': bool(cfg.winrm_verify_ssl),
            'winrm_transport': transport, 'winrm_username': (account or '').strip() or None}


def _transient_winrm_config(msca, overrides):
    """Build a transient config for the admin-channel test: saved connection
    values + unsaved form overrides. Plain attributes (no ORM, no encryption
    setters) — the object is NEVER persisted. Returns (config, error) where
    error is an error_response tuple on invalid override values.
    """
    from types import SimpleNamespace

    cfg = SimpleNamespace(
        name=msca.name,
        server=msca.server,
        auth_method=msca.auth_method,
        username=msca.username,
        password=msca.password,
        kerberos_principal=msca.kerberos_principal,
        kerberos_keytab_path=msca.kerberos_keytab_path,
        winrm_enabled=bool(msca.winrm_enabled),
        winrm_host=msca.winrm_host,
        winrm_port=msca.winrm_port,
        winrm_use_ssl=bool(msca.winrm_use_ssl),
        winrm_verify_ssl=bool(msca.winrm_verify_ssl),
        winrm_transport=msca.winrm_transport or 'kerberos',
        winrm_username=msca.winrm_username,
        winrm_password=msca.winrm_password,
        ca_config=msca.ca_config,
    )

    if not isinstance(overrides, dict):
        return None, error_response("Request body must be a JSON object", 400)
    data = {k: v for k, v in overrides.items() if k in _WINRM_OVERRIDE_FIELDS + _WINRM_KERBEROS_FIELDS}
    # Empty or masked password means "use the saved one".
    if not data.get('winrm_password') or str(data['winrm_password']).strip() in MASKS:
        data.pop('winrm_password', None)
    for field in _WINRM_KERBEROS_FIELDS:
        if field in data and data[field] is not None and not isinstance(data[field], str):
            return None, error_response(f"{field} must be a string", 400)
    err = _check_size('kerberos_keytab_path', data.get('kerberos_keytab_path'), MAX_KEYTAB_PATH_LEN) \
        or _keytab_error(data)
    if err:
        return None, err
    saved_channel = _winrm_channel(cfg)
    err = _apply_winrm_fields(cfg, data)
    if err:
        return None, err
    for field in _WINRM_KERBEROS_FIELDS:
        if field in data:
            setattr(cfg, field, (data[field] or '').strip() or None)
    # The saved NTLM password does not follow a moved channel; Kerberos is the route's admin:system
    changed = sorted(k for k, v in _winrm_channel(cfg).items() if saved_channel[k] != v)
    if changed and cfg.winrm_transport != 'kerberos' and 'winrm_password' not in data:
        return None, error_response(SECRET_TARGET_MESSAGE, 400,
                                    details={'code': 'secret_required_for_target', 'fields': changed})

    # Mirror MicrosoftCA.winrm_effective_* on the transient object.
    cfg.winrm_effective_host = cfg.winrm_host or cfg.server
    cfg.winrm_effective_username = cfg.winrm_username or (
        cfg.username if cfg.auth_method == 'basic' else None)
    cfg.winrm_effective_password = cfg.winrm_password or (
        cfg.password if cfg.auth_method == 'basic'
        and basic_password_reaches(cfg.winrm_host, cfg.server) else None)
    return cfg, None


def _actor():
    """Current username for audit/attribution, or 'system'."""
    try:
        if hasattr(g, 'current_user') and g.current_user:
            return g.current_user.username
    except Exception:
        pass
    return 'system'


def _audit(action: str, msca, details: str, success: bool = True):
    try:
        AuditService.log_action(
            action=action,
            resource_type='microsoft_ca',
            resource_id=getattr(msca, 'id', None),
            resource_name=getattr(msca, 'name', None),
            details=details,
            success=success,
        )
    except Exception as e:
        logger.error(f"MSCA audit log failed: {e}")


# --- CRUD Endpoints ---

@bp.route('', methods=['GET'])
@require_auth(['read:settings'])
def list_connections():
    """List all Microsoft CA connections"""
    connections = MicrosoftCA.query.order_by(MicrosoftCA.name).all()
    return success_response(data=[c.to_dict() for c in connections])


@bp.route('/enabled', methods=['GET'])
@require_auth(['read:certificates'])
def list_enabled_connections():
    """List enabled MS CA connections (for sign modal dropdown)"""
    connections = MicrosoftCAService.get_enabled_connections()
    return success_response(data=connections)


@bp.route('', methods=['POST'])
@require_auth(['write:settings'])
def create_connection():
    """Create a new Microsoft CA connection"""
    data = request.get_json()
    if not data:
        return error_response("Request body required", 400)

    name = data.get('name', '').strip()
    server = data.get('server', '').strip()
    auth_method = data.get('auth_method', 'certificate')

    if not name:
        return error_response("Name is required", 400)
    if len(name) > MAX_NAME_LEN:
        return error_response(f"Name too long (max {MAX_NAME_LEN})", 400)
    if not server:
        return error_response("Server hostname is required", 400)
    if len(server) > MAX_SERVER_LEN:
        return error_response(f"Server too long (max {MAX_SERVER_LEN})", 400)
    if auth_method not in ('certificate', 'kerberos', 'basic'):
        return error_response("Invalid auth method", 400)
    err = _kerberos_save_forbidden(None, data) or _keytab_error(data)
    if err:
        return err

    # Cap PEM/keytab inputs early so we don't ingest megabytes into the DB.
    for field, limit in (
        ('client_cert_pem', MAX_PEM_FIELD_BYTES),
        ('client_key_pem', MAX_PEM_FIELD_BYTES),
        ('ca_bundle', MAX_PEM_FIELD_BYTES),
        ('kerberos_keytab_path', MAX_KEYTAB_PATH_LEN),
        ('default_template', MAX_TEMPLATE_LEN),
    ):
        err = _check_size(field, data.get(field), limit)
        if err:
            return err

    if MicrosoftCA.query.filter_by(name=name).first():
        return error_response(f"Connection '{name}' already exists", 409)

    try:
        msca = MicrosoftCA(
            name=name,
            server=server,
            ca_name=data.get('ca_name', '').strip() or None,
            auth_method=auth_method,
            use_ssl=data.get('use_ssl', True),
            verify_ssl=data.get('verify_ssl', True),
            ca_bundle=data.get('ca_bundle', '').strip() or None,
            default_template=data.get('default_template', 'WebServer').strip(),
            enabled=data.get('enabled', True),
            created_by=g.current_user.username if hasattr(g, 'current_user') else None,
        )

        # Auth-specific fields
        if auth_method == 'basic':
            msca.username = data.get('username', '').strip()
            msca.password = data.get('password', '')
        elif auth_method == 'certificate':
            msca.client_cert_pem = data.get('client_cert_pem', '').strip() or None
            msca.client_key_pem = data.get('client_key_pem', '').strip() or None
        elif auth_method == 'kerberos':
            msca.kerberos_principal = data.get('kerberos_principal', '').strip() or None
            msca.kerberos_keytab_path = data.get('kerberos_keytab_path', '').strip() or None

        # CRL revocation sync (#185)
        msca.crl_sync_enabled = bool(data.get('crl_sync_enabled', False))
        if 'crl_url' in data:
            url, err = _clean_crl_url(data['crl_url'])
            if err:
                return err
            msca.crl_url = url

        # WinRM admin channel (#185 phase A)
        err = _apply_winrm_fields(msca, data)
        if err:
            return err
        msca.inventory_sync_enabled = bool(data.get('inventory_sync_enabled', False))

        db.session.add(msca)
        ok, err = safe_commit(logger, "Failed to create connection")
        if not ok:
            _audit('msca.create', None, f"name={name} error=commit failed", success=False)
            return err

        _audit('msca.create', msca,
               f"auth={auth_method} server={server} ssl={msca.use_ssl}/verify={msca.verify_ssl}")
        logger.info(f"Microsoft CA connection created: {name} ({auth_method})")
        return created_response(data=msca.to_dict(), message="Microsoft CA connection created")

    except Exception as e:
        logger.error(f"Failed to create MS CA connection: {e}")
        # Before the audit, for the reason `update_connection` has above: the
        # row is already staged by then, and `_audit` commits the session it
        # is handed, so recording the refusal was what saved the connection
        # the refusal was about, credentials included.
        db.session.rollback()
        _audit('msca.create', None, f"name={name} error={e}", success=False)
        return error_response("Failed to create connection", 500)


@bp.route('/<int:msca_id>', methods=['GET'])
@require_auth(['read:settings'])
def get_connection(msca_id):
    """Get Microsoft CA connection details"""
    msca = db.session.get(MicrosoftCA, msca_id)
    if not msca:
        return error_response("Connection not found", 404)
    return success_response(data=msca.to_dict())


def _keytab_error(data):
    """400 when the body names a file UCM manages as the client keytab."""
    value = data.get('kerberos_keytab_path') if isinstance(data, dict) else None
    reason = managed_keytab_error(value) if isinstance(value, str) else None
    return error_response(reason, 400) if reason else None


_WINRM_TARGET_FIELDS = ('winrm_host', 'winrm_port', 'winrm_use_ssl', 'winrm_verify_ssl',
                        'winrm_transport', 'winrm_username')


def _winrm_target_fields(msca):
    current = {k: getattr(msca, k) for k in _WINRM_TARGET_FIELDS}
    # Same defaults as to_dict, so a form sent back unchanged compares equal
    current.update(winrm_port=msca.winrm_port or 5986,
                   winrm_transport=msca.winrm_transport or 'kerberos')
    if not msca.winrm_host:
        current['server'] = msca.server  # WinRM falls back to the server
    return current


def _msca_retarget_error(msca, data):
    """Saved passwords and client keys stay with their saved target; Kerberos is a permission instead.
    Stored tokens are read: a password this node cannot open is kept all the same."""
    current = _winrm_target_fields(msca)
    winrm_err = retarget_error(current, data, keeps_saved_secret(
        data, 'winrm_password', msca._winrm_password, blank_clears=True))
    if winrm_err:
        return winrm_err
    # The saved password or client key stays with the saved certsrv target, whatever the channel
    fields = saved_credential_retargets(msca, data)
    if fields:
        return error_response(SECRET_TARGET_MESSAGE, 400,
                              details={'code': 'secret_required_for_target', 'fields': fields})
    if msca.auth_method != 'basic' or data.get('auth_method', 'basic') != 'basic':
        return None
    if not keeps_saved_secret(data, 'password', msca._password, blank_clears=True):
        return None
    # Clearing the WinRM password hands its channel to the connection password
    cleared = 'winrm_password' in data and not str(data['winrm_password'] or '').strip()
    if cleared and msca._winrm_password and basic_password_reaches(
            data.get('winrm_host', msca.winrm_host), data.get('server', msca.server)):
        return retarget_error({'winrm_password': 'saved'}, {'winrm_password': 'cleared'}, True)
    current = {k: getattr(msca, k) for k in ('server', 'use_ssl', 'verify_ssl', 'ca_bundle', 'username')}
    winrm_typed = str(data.get('winrm_password') or '').strip() not in ('', *MASKS)
    if not msca._winrm_password and not winrm_typed:
        # The basic password doubles as the WinRM one
        current.update(_winrm_target_fields(msca))
    return retarget_error(current, data, True)


@bp.route('/<int:msca_id>', methods=['PUT'])
@require_auth(['write:settings'])
def update_connection(msca_id):
    """Update a Microsoft CA connection"""
    msca = db.session.get(MicrosoftCA, msca_id)
    if not msca:
        return error_response("Connection not found", 404)

    data = request.get_json()
    if not data:
        return error_response("Request body required", 400)
    # A transport refused outright is the answer, before any question of secrets
    err = _kerberos_save_forbidden(msca, data) \
        or (_winrm_transport_error(data) if 'winrm_transport' in data else None) \
        or _keytab_error(data) or _msca_retarget_error(msca, data)
    if err:
        return err

    try:
        # Cap PEM/keytab inputs.
        for field, limit in (
            ('client_cert_pem', MAX_PEM_FIELD_BYTES),
            ('client_key_pem', MAX_PEM_FIELD_BYTES),
            ('ca_bundle', MAX_PEM_FIELD_BYTES),
            ('kerberos_keytab_path', MAX_KEYTAB_PATH_LEN),
            ('default_template', MAX_TEMPLATE_LEN),
            ('name', MAX_NAME_LEN),
            ('server', MAX_SERVER_LEN),
        ):
            err = _check_size(field, data.get(field), limit)
            if err:
                return err

        # Update common fields
        if 'name' in data:
            new_name = data['name'].strip()
            existing = MicrosoftCA.query.filter_by(name=new_name).first()
            if existing and existing.id != msca_id:
                return error_response(f"Connection '{new_name}' already exists", 409)
            msca.name = new_name

        if 'server' in data:
            msca.server = data['server'].strip()
        if 'ca_name' in data:
            msca.ca_name = data['ca_name'].strip() or None
        if 'use_ssl' in data:
            msca.use_ssl = data['use_ssl']
        if 'verify_ssl' in data:
            msca.verify_ssl = data['verify_ssl']
        if 'ca_bundle' in data:
            msca.ca_bundle = data['ca_bundle'].strip() or None
        if 'default_template' in data:
            msca.default_template = data['default_template'].strip()
        if 'enabled' in data:
            msca.enabled = data['enabled']
        if 'crl_sync_enabled' in data:
            msca.crl_sync_enabled = bool(data['crl_sync_enabled'])
        if 'crl_url' in data:
            url, err = _clean_crl_url(data['crl_url'])
            if err:
                return err
            msca.crl_url = url

        # WinRM admin channel (#185 phase A)
        err = _apply_winrm_fields(msca, data)
        if err:
            return err
        if 'inventory_sync_enabled' in data:
            msca.inventory_sync_enabled = bool(data['inventory_sync_enabled'])

        # Auth method change: clear ALL stale credentials for the old method
        # so a basic→certificate switch doesn't leave the old encrypted password
        # sitting in the row (and accidentally being considered active again on a
        # later switch back).
        if 'auth_method' in data:
            new_method = data['auth_method']
            if new_method not in ('certificate', 'kerberos', 'basic'):
                return error_response("Invalid auth method", 400)
            if new_method != msca.auth_method:
                msca.username = None
                msca.password = None
                msca.client_cert_pem = None
                msca.client_key_pem = None
                msca.kerberos_principal = None
                msca.kerberos_keytab_path = None
            msca.auth_method = new_method

        # Auth-specific fields
        auth = data.get('auth_method', msca.auth_method)
        if auth == 'basic':
            if 'username' in data:
                msca.username = data['username'].strip()
            if 'password' in data and str(data['password'] or '').strip() not in MASKS:
                msca.password = data['password']
        elif auth == 'certificate':
            if 'client_cert_pem' in data:
                msca.client_cert_pem = data['client_cert_pem'].strip() or None
            if 'client_key_pem' in data and str(data['client_key_pem'] or '').strip() not in MASKS:
                msca.client_key_pem = data['client_key_pem'].strip() or None
        elif auth == 'kerberos':
            if 'kerberos_principal' in data:
                msca.kerberos_principal = data['kerberos_principal'].strip() or None
            if 'kerberos_keytab_path' in data:
                msca.kerberos_keytab_path = data['kerberos_keytab_path'].strip() or None

        ok, err = safe_commit(logger, "Failed to update connection")
        if not ok:
            _audit('msca.update', msca, "error=commit failed", success=False)
            return err
        _audit('msca.update', msca, f"fields={sorted(data.keys())}")
        logger.info(f"Microsoft CA connection updated: {msca.name}")
        return success_response(data=msca.to_dict(), message="Connection updated")

    except Exception as e:
        logger.error(f"Failed to update MS CA connection: {e}")
        # Before the audit, not after. The fields above are applied to the
        # row one by one with no commit between them, so a value of the wrong
        # type part way down leaves the earlier ones staged. `log_action`
        # commits the session it is given, so auditing the refusal was what
        # saved them: a request carrying a new name and a new password and
        # one unusable field was answered 500 and kept the name and the
        # password.
        db.session.rollback()
        _audit('msca.update', msca, f"error={e}", success=False)
        return error_response("Failed to update connection", 500)


@bp.route('/<int:msca_id>', methods=['DELETE'])
@require_auth(['delete:settings'])
def delete_connection(msca_id):
    """Delete a Microsoft CA connection"""
    msca = db.session.get(MicrosoftCA, msca_id)
    if not msca:
        return error_response("Connection not found", 404)

    pending = MSCARequest.query.filter_by(msca_id=msca_id, status='pending').count()
    if pending > 0:
        return error_response(
            f"Cannot delete: {pending} pending request(s). Resolve them first.", 409
        )

    try:
        name = msca.name
        snapshot_id = msca.id
        snapshot = type('S', (), {'id': snapshot_id, 'name': name})()
        db.session.delete(msca)
        db.session.commit()
        _audit('msca.delete', snapshot, "")
        logger.info(f"Microsoft CA connection deleted: {name}")
        return no_content_response()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to delete MS CA connection: {e}")
        _audit('msca.delete', msca, f"error={e}", success=False)
        return error_response("Failed to delete connection", 500)


# --- Connection Testing ---

@bp.route('/test', methods=['POST'])
@require_auth(['write:settings'])
def test_connection_inline():
    """Test connectivity using provided connection data (before save)"""
    data = request.get_json()
    if not data or not data.get('server'):
        return error_response("Server hostname is required", 400)
    # An unsaved connection has no saved target: any keytab or principal needs admin:system
    err = _kerberos_test_forbidden(None, {'auth_method': 'basic', **data}) or _keytab_error(data)
    if err:
        return err
    result = MicrosoftCAService.test_connection_inline(data)
    if result.get('success'):
        return success_response(data=result, message="Connection successful")
    return error_response(result.get('error', 'Connection test failed'), 400)


_TEST_STRING_FIELDS = ('server', 'ca_name', 'username', 'password', 'client_cert_pem',
                       'client_key_pem', 'kerberos_principal', 'kerberos_keytab_path', 'ca_bundle')


def _test_overrides(msca, data):
    """(form values, error): the body of a test, held to the rules of a save."""
    if not isinstance(data, dict):
        return None, error_response("Request body must be a JSON object", 400)
    for field in _TEST_STRING_FIELDS:
        if field in data and not isinstance(data[field], str):
            return None, error_response(f"{field} must be a string", 400)
    for field in ('use_ssl', 'verify_ssl'):
        if field in data and not isinstance(data[field], bool):
            return None, error_response(f"{field} must be a boolean", 400)
    if 'server' in data and not data['server'].strip():
        return None, error_response("Server hostname is required", 400)
    if data.get('auth_method', msca.auth_method) not in ('certificate', 'kerberos', 'basic'):
        return None, error_response("Invalid auth method", 400)
    err = _kerberos_test_forbidden(msca, data) or _keytab_error(data)
    if err:
        return None, err
    for field, limit in (('client_cert_pem', MAX_PEM_FIELD_BYTES), ('client_key_pem', MAX_PEM_FIELD_BYTES),
                         ('ca_bundle', MAX_PEM_FIELD_BYTES), ('kerberos_keytab_path', MAX_KEYTAB_PATH_LEN),
                         ('server', MAX_SERVER_LEN)):
        err = _check_size(field, data.get(field), limit)
        if err:
            return None, err
    # A saved password or client key never follows a changed target (as on save), a new method included
    err = _msca_retarget_error(msca, data)
    if err:
        return None, err
    return {**data, **({'server': data['server'].strip()} if 'server' in data else {})}, None


@bp.route('/<int:msca_id>/test', methods=['POST'])
@require_auth(['write:settings'])
def test_connection(msca_id):
    """Test connectivity to Microsoft CA; a JSON body tests the form's values instead, saving nothing"""
    data = request.get_json(silent=True)
    overrides = None
    if data:
        msca = db.session.get(MicrosoftCA, msca_id)
        if not msca:
            return error_response("Connection not found", 404)
        overrides, err = _test_overrides(msca, data)
        if err:
            return err
    result = MicrosoftCAService.test_connection(msca_id, overrides)
    if result.get('success'):
        return success_response(data=result, message="Connection successful")
    return error_response(result.get('error', 'Connection test failed'), 400)


@bp.route('/<int:msca_id>/sync-crl', methods=['POST'])
@require_auth(['write:certificates'])
def sync_crl(msca_id):
    """Fetch the CA's CRL and revoke matching UCM certificates (one-way CA → UCM)"""
    msca = db.session.get(MicrosoftCA, msca_id)
    if not msca:
        return error_response("Connection not found", 404)
    if not msca.enabled:
        return error_response("Microsoft CA connection is disabled", 400)

    username = None
    try:
        username = g.current_user.username if hasattr(g, 'current_user') and g.current_user else None
    except Exception:
        pass

    try:
        summary = MicrosoftCAService.sync_crl(msca_id, username=username or 'system')
        _audit('msca.crl_sync_manual', msca,
               f"revoked={summary['revoked']} checked={summary['checked']}")
        return success_response(
            data=summary,
            message=f"CRL sync complete: {summary['revoked']} certificate(s) revoked"
        )
    except ValueError as e:
        _audit('msca.crl_sync_manual', msca, f"error={e}", success=False)
        return error_response(str(e), 400)
    except Exception as e:
        logger.error(f"CRL sync failed for MS CA '{msca.name}': {e}", exc_info=True)
        _audit('msca.crl_sync_manual', msca, f"error={e}", success=False)
        return error_response("CRL sync failed", 500)


# --- WinRM admin channel (#185 phase A) ---

@bp.route('/<int:msca_id>/admin-channel/test', methods=['POST'])
@require_auth(['admin:system'])
def test_admin_channel(msca_id):
    """Test the WinRM admin channel (connect + CA service/ping).

    Accepts an optional JSON body of unsaved winrm_*/ca_config form values so
    the test reflects what the operator is about to save, not the stored row.
    """
    from services.msca_service import MSCAAdminChannelError

    msca = db.session.get(MicrosoftCA, msca_id)
    if not msca:
        return error_response("Connection not found", 404)

    overrides = request.get_json(silent=True) or {}
    cfg, err = _transient_winrm_config(msca, overrides)
    if err:
        return err
    if not cfg.winrm_enabled:
        return error_response("WinRM admin channel is not enabled on this connection", 400)

    try:
        result = MicrosoftCAService.test_admin_channel_config(cfg)
        _audit('msca.admin_channel_test', msca,
               f"transport={cfg.winrm_transport} certsvc={result.get('certsvc_status')}")
        return success_response(data=result, message="Admin channel reachable")
    except MSCAAdminChannelError as e:
        _audit('msca.admin_channel_test', msca, f"error={e}", success=False)
        return error_response(str(e), 400)
    except Exception as e:
        logger.error(f"Admin channel test failed for MS CA '{msca.name}': {e}", exc_info=True)
        _audit('msca.admin_channel_test', msca, f"error={e}", success=False)
        return error_response("Admin channel test failed", 500)


@bp.route('/<int:msca_id>/publish-crl', methods=['POST'])
@require_auth(['admin:system'])
def publish_crl(msca_id):
    """Force the Windows CA to publish a fresh CRL via the admin channel."""
    from services.msca_service import MSCAAdminChannelError

    msca = db.session.get(MicrosoftCA, msca_id)
    if not msca:
        return error_response("Connection not found", 404)
    if not MicrosoftCAService.admin_channel_available(msca):
        return error_response("WinRM admin channel is not configured", 400)

    try:
        result = MicrosoftCAService.publish_crl(msca_id)
        _audit('msca.publish_crl', msca, "CRL published on CA")
        return success_response(data=result, message="CRL published on the Microsoft CA")
    except MSCAAdminChannelError as e:
        _audit('msca.publish_crl', msca, f"error={e}", success=False)
        return error_response(str(e), 400)
    except Exception as e:
        logger.error(f"Publish CRL failed for MS CA '{msca.name}': {e}", exc_info=True)
        _audit('msca.publish_crl', msca, f"error={e}", success=False)
        return error_response("Publish CRL failed", 500)


# --- CA inventory sync (#185 phase B) ---

@bp.route('/<int:msca_id>/inventory-sync', methods=['POST'])
@require_auth(['admin:system'])
def inventory_sync(msca_id):
    """Import certs issued directly on the CA that UCM doesn't know yet."""
    from services.msca_service import MSCAAdminChannelError

    msca = db.session.get(MicrosoftCA, msca_id)
    if not msca:
        return error_response("Connection not found", 404)
    if not MicrosoftCAService.admin_channel_available(msca):
        return error_response("WinRM admin channel is not configured", 400)

    full = bool((request.get_json(silent=True) or {}).get('full', False))
    try:
        summary = MicrosoftCAService.inventory_sync(msca_id, username=_actor(), full=full)
        _audit('msca.inventory_sync', msca,
               f"imported={summary['imported']} completed={summary['completed']} "
               f"denied={summary['denied']} skipped={summary['skipped']} "
               f"failed={summary['failed']} full={full}")
        return success_response(
            data=summary,
            message=(f"Inventory sync complete: {summary['imported']} certificate(s) imported, "
                    f"{summary['completed']} pending request(s) completed")
        )
    except MSCAAdminChannelError as e:
        _audit('msca.inventory_sync', msca, f"error={e}", success=False)
        return error_response(str(e), 400)
    except Exception as e:
        logger.error(f"Inventory sync failed for MS CA '{msca.name}': {e}", exc_info=True)
        _audit('msca.inventory_sync', msca, f"error={e}", success=False)
        return error_response("Inventory sync failed", 500)


@bp.route('/<int:msca_id>/reconciliation', methods=['GET'])
@require_auth(['read:certificates'])
def inventory_reconciliation(msca_id):
    """Compare the CA's issued certs with UCM's known set (read-only)."""
    from services.msca_service import MSCAAdminChannelError

    msca = db.session.get(MicrosoftCA, msca_id)
    if not msca:
        return error_response("Connection not found", 404)
    if not MicrosoftCAService.admin_channel_available(msca):
        return error_response("WinRM admin channel is not configured", 400)

    try:
        result = MicrosoftCAService.reconcile_inventory(msca_id)
        return success_response(data=result)
    except MSCAAdminChannelError as e:
        return error_response(str(e), 400)
    except Exception as e:
        logger.error(f"Reconciliation failed for MS CA '{msca.name}': {e}", exc_info=True)
        return error_response("Reconciliation failed", 500)


# --- CA control: pending requests + health (#185 phase C) ---

@bp.route('/<int:msca_id>/ca/health', methods=['GET'])
@require_auth(['read:certificates'])
def ca_health(msca_id):
    """CA health snapshot (service, CA cert, CRL, pending count)."""
    from services.msca_service import MSCAAdminChannelError

    msca = db.session.get(MicrosoftCA, msca_id)
    if not msca:
        return error_response("Connection not found", 404)
    if not MicrosoftCAService.admin_channel_available(msca):
        return error_response("WinRM admin channel is not configured", 400)
    try:
        return success_response(data=MicrosoftCAService.ca_health(msca_id))
    except MSCAAdminChannelError as e:
        return error_response(str(e), 400)
    except Exception as e:
        logger.error(f"CA health failed for MS CA '{msca.name}': {e}", exc_info=True)
        return error_response("CA health check failed", 500)


@bp.route('/<int:msca_id>/ca/pending', methods=['GET'])
@require_auth(['read:certificates'])
def list_pending_ca_requests(msca_id):
    """List requests awaiting CA manager approval."""
    from services.msca_service import MSCAAdminChannelError

    msca = db.session.get(MicrosoftCA, msca_id)
    if not msca:
        return error_response("Connection not found", 404)
    if not MicrosoftCAService.admin_channel_available(msca):
        return error_response("WinRM admin channel is not configured", 400)
    try:
        return success_response(data=MicrosoftCAService.list_pending_requests(msca_id))
    except MSCAAdminChannelError as e:
        return error_response(str(e), 400)
    except Exception as e:
        logger.error(f"List pending failed for MS CA '{msca.name}': {e}", exc_info=True)
        return error_response("Failed to list pending requests", 500)


@bp.route('/<int:msca_id>/ca/pending/<int:request_id>/approve', methods=['POST'])
@require_auth(['admin:system'])
def approve_ca_request(msca_id, request_id):
    """Approve (resubmit) a pending CA request and import the issued cert."""
    from services.msca_service import MSCAAdminChannelError

    msca = db.session.get(MicrosoftCA, msca_id)
    if not msca:
        return error_response("Connection not found", 404)
    if not MicrosoftCAService.admin_channel_available(msca):
        return error_response("WinRM admin channel is not configured", 400)
    try:
        result = MicrosoftCAService.approve_request(msca_id, request_id)
        _audit('msca.approve_request', msca,
               f"request_id={request_id} imported_cert_id={result.get('imported_cert_id')}")
        return success_response(data=result, message="Request approved")
    except MSCAAdminChannelError as e:
        _audit('msca.approve_request', msca, f"request_id={request_id} error={e}", success=False)
        return error_response(str(e), 400)
    except Exception as e:
        logger.error(f"Approve request failed for MS CA '{msca.name}': {e}", exc_info=True)
        _audit('msca.approve_request', msca, f"request_id={request_id} error={e}", success=False)
        return error_response("Failed to approve request", 500)


@bp.route('/<int:msca_id>/ca/pending/<int:request_id>/deny', methods=['POST'])
@require_auth(['admin:system'])
def deny_ca_request(msca_id, request_id):
    """Deny a pending CA request."""
    from services.msca_service import MSCAAdminChannelError

    msca = db.session.get(MicrosoftCA, msca_id)
    if not msca:
        return error_response("Connection not found", 404)
    if not MicrosoftCAService.admin_channel_available(msca):
        return error_response("WinRM admin channel is not configured", 400)
    try:
        result = MicrosoftCAService.deny_request(msca_id, request_id)
        _audit('msca.deny_request', msca, f"request_id={request_id}")
        return success_response(data=result, message="Request denied")
    except MSCAAdminChannelError as e:
        _audit('msca.deny_request', msca, f"request_id={request_id} error={e}", success=False)
        return error_response(str(e), 400)
    except Exception as e:
        logger.error(f"Deny request failed for MS CA '{msca.name}': {e}", exc_info=True)
        _audit('msca.deny_request', msca, f"request_id={request_id} error={e}", success=False)
        return error_response("Failed to deny request", 500)


# --- Templates ---

@bp.route('/<int:msca_id>/templates', methods=['GET'])
@require_auth(['read:certificates'])
def list_templates(msca_id):
    """List available certificate templates from MS CA"""
    msca = db.session.get(MicrosoftCA, msca_id)
    if not msca:
        return error_response("Connection not found", 404)

    try:
        templates = MicrosoftCAService.list_templates(msca_id)
        return success_response(data=templates)
    except Exception as e:
        logger.error(f"Failed to list templates: {e}")
        return error_response("Failed to retrieve templates", 500)


# --- CSR Signing ---

@bp.route('/<int:msca_id>/sign/<int:csr_id>', methods=['POST'])
@require_auth(['write:certificates'])
def sign_csr(msca_id, csr_id):
    """Submit a CSR to Microsoft CA for signing"""
    from models import Certificate

    msca = db.session.get(MicrosoftCA, msca_id)
    if not msca:
        return error_response("Microsoft CA connection not found", 404)
    if not msca.enabled:
        return error_response("Microsoft CA connection is disabled", 400)

    data = request.get_json() or {}
    template = (data.get('template') or msca.default_template or '').strip()

    if not template:
        return error_response("Certificate template is required", 400)
    if len(template) > MAX_TEMPLATE_LEN:
        return error_response(f"Template name too long (max {MAX_TEMPLATE_LEN})", 400)

    csr = db.session.get(Certificate, csr_id)
    if not csr or not csr.csr:
        return error_response("CSR not found", 404)
    if csr.crt:
        # Same rule as the local Sign CSR action: the row already holds a
        # certificate, overwriting it would drop that certificate from the
        # inventory (and from revocation) while a second one lives on
        return error_response("CSR already signed", 400)

    # EOBO (Enroll On Behalf Of): the requester is impersonating another
    # principal. This bypasses the normal "user signs their own CSR" boundary,
    # so require an elevated permission. The MS CA enrollment-agent cert still
    # has to allow EOBO server-side, but we don't want any operator with
    # write:certificates to be able to issue certs as arbitrary UPNs.
    enrollee_name = (data.get('enrollee_name') or '').strip() or None
    enrollee_upn = (data.get('enrollee_upn') or '').strip() or None
    if enrollee_name or enrollee_upn:
        user_perms = getattr(g, 'permissions', []) or []
        if '*' not in user_perms and not _has_perm('admin:system', user_perms):
            return error_response(
                "EOBO (enroll-on-behalf) requires admin:system permission", 403
            )

    # Get CSR PEM
    try:
        import base64
        csr_pem = base64.b64decode(csr.csr).decode('utf-8')
    except Exception:
        csr_pem = csr.csr

    if not csr_pem:
        return error_response("CSR data is empty", 400)

    if isinstance(csr_pem, bytes):
        csr_pem = csr_pem.decode('utf-8', errors='replace')

    # Proof-of-Possession: verify the CSR self-signature before sending it
    # upstream. Same defense as SCEP/EST — we don't want UCM to be a relay
    # for unsigned/forged CSRs.
    try:
        from cryptography import x509 as _x509
        _csr_obj = _x509.load_pem_x509_csr(csr_pem.encode('utf-8'))
        from utils.key_type import unsignable_csr_key
        _unsignable = unsignable_csr_key(_csr_obj)
        if _unsignable:
            return error_response(_unsignable, 400)
        if not _csr_obj.is_signature_valid:
            from utils.csr_diagnostics import weak_csr_hash_error
            return error_response(weak_csr_hash_error(_csr_obj) or "CSR signature is invalid", 400)
    except ValueError as e:
        return error_response(f"Invalid CSR: {e}", 400)
    except Exception as e:
        logger.error(f"CSR POP check failed for csr_id={csr_id}: {e}")
        return error_response("Failed to validate CSR", 400)

    username = None
    try:
        username = g.current_user.username if hasattr(g, 'current_user') and g.current_user else None
    except Exception:
        pass

    try:
        result = MicrosoftCAService.submit_csr(
            msca_id=msca_id,
            csr_pem=csr_pem,
            template=template,
            csr_id=csr_id,
            submitted_by=username,
            enrollee_name=enrollee_name,
            enrollee_upn=enrollee_upn,
        )

        if result['status'] == 'issued':
            # Import the signed cert into UCM. If import fails the upstream MS CA
            # has already issued the cert — surface that explicitly so the
            # operator knows the cert exists and needs manual reconciliation
            # (don't pretend the whole call succeeded).
            try:
                _import_signed_cert(csr, result.get('cert_pem'), msca, template, result['request_id'])
            except MSCASignedElsewhere:
                # Signed by a local CA or an import meanwhile: closed as complete_request does
                db.session.rollback()
                supersede([result['request_id']], states=('issued',))
                _audit('msca.sign', msca,
                       f"template={template} csr_id={csr_id} eobo={bool(enrollee_name or enrollee_upn)} "
                       f"status=superseded", success=False)
                return error_response(SIGNED_MEANWHILE_MESSAGE, 409)
            except Exception as imp_err:
                logger.error(
                    f"MS CA issued cert but UCM import failed (msca={msca.name}, "
                    f"csr_id={csr_id}, ms_request_id={result.get('request_id')}): {imp_err}",
                    exc_info=True,
                )
                # Before the audit. `_import_signed_cert` rewrites the CSR row
                # column by column and commits at the end, so a failure part
                # way through leaves the row half rewritten in the session,
                # and `_audit` commits what it is given: recording this
                # refusal was what saved a record carrying the new
                # certificate's subject over the old one's, on a call the
                # operator is told to reconcile by hand.
                db.session.rollback()
                _audit('msca.sign', msca,
                       f"template={template} csr_id={csr_id} eobo={bool(enrollee_name or enrollee_upn)} "
                       f"status=issued_import_failed error={imp_err}",
                       success=False)
                return error_response(
                    "Certificate was issued by MS CA but failed to import into UCM. "
                    f"Check logs for ms_request_id={result.get('request_id')}.",
                    500,
                )
            _audit('msca.sign', msca,
                   f"template={template} csr_id={csr_id} eobo={bool(enrollee_name or enrollee_upn)} status=issued")
            return success_response(data=result, message="Certificate issued by Microsoft CA")

        elif result['status'] == 'pending':
            _audit('msca.sign', msca,
                   f"template={template} csr_id={csr_id} eobo={bool(enrollee_name or enrollee_upn)} status=pending")
            return success_response(data=result, message="Request pending approval")

        return success_response(data=result)

    except ValueError as e:
        logger.error(f"Validation error signing CSR via MS CA: {e}", exc_info=True)
        _audit('msca.sign', msca, f"template={template} csr_id={csr_id} error={e}", success=False)
        return error_response(str(e), 400)
    except Exception as e:
        logger.error(f"Failed to sign CSR via MS CA: {e}", exc_info=True)
        _audit('msca.sign', msca, f"template={template} csr_id={csr_id} error={e}", success=False)
        return error_response("Failed to submit CSR to Microsoft CA", 500)


@bp.route('/<int:msca_id>/requests/<int:request_id>', methods=['GET'])
@require_auth(['write:certificates'])
def check_request_status(msca_id, request_id):
    """Check a pending signing request; an issued certificate is imported (as signing does)."""
    from services.msca.requests import MSCAImportError
    try:
        result = MicrosoftCAService.check_request(msca_id, request_id)
        if result.get('status') == SUPERSEDED:
            return success_response(data=result, message=SUPERSEDED_MESSAGE)
        return success_response(data=result)
    except MSCAImportError as e:
        logger.error(f"MS CA request {request_id} issued but UCM import failed: {e}")
        return error_response(
            "Certificate was issued by MS CA but failed to import into UCM.", 500)
    except ValueError as e:
        logger.error(f"Request not found or invalid: {e}")
        return error_response("Request not found", 404)
    except Exception as e:
        logger.error(f"Failed to check request status: {e}")
        return error_response("Failed to check request status", 500)


@bp.route('/requests/pending', methods=['GET'])
@require_auth(['read:certificates'])
def list_pending_requests():
    """List all pending MS CA requests"""
    msca_id = request.args.get('msca_id', type=int)
    requests_list = MicrosoftCAService.get_pending_requests(msca_id)
    return success_response(data=requests_list)


# --- Helper ---

def _import_signed_cert(csr, cert_pem, msca, template, msca_request_id, announce=True):
    """Import a signed certificate from MS CA into UCM's certificate store.

    Raises on failure. Callers MUST handle the exception so that an MS-CA-issued
    certificate that we couldn't persist is surfaced to the operator instead of
    being silently swallowed (orphan: MS CA has it, UCM doesn't).
    With *announce*, the commit is followed by certificate.issued, or
    certificate.renewed when the row held another certificate.
    """
    from models import Certificate
    from services.import_service import stored_certificate_serial
    import base64
    import uuid
    import json

    from cryptography import x509 as cx509
    from cryptography.hazmat.primitives.serialization import Encoding

    if not cert_pem:
        raise ValueError("No certificate data to import")

    # Ensure string
    if isinstance(cert_pem, bytes):
        cert_pem = cert_pem.decode('utf-8', errors='replace')

    cert_obj = None

    try:
        # Case 1: Full PEM with headers
        if '-----BEGIN CERTIFICATE-----' in cert_pem:
            cert_obj = cx509.load_pem_x509_certificate(cert_pem.encode('utf-8'))
        else:
            # Case 2: Base64-encoded DER (certsrv b64 format) — may lack padding
            clean_b64 = cert_pem.replace('\r', '').replace('\n', '').replace(' ', '')
            padding = 4 - len(clean_b64) % 4
            if padding != 4:
                clean_b64 += '=' * padding
            try:
                cert_der = base64.b64decode(clean_b64)
                cert_obj = cx509.load_der_x509_certificate(cert_der)
            except Exception:
                pem_wrapped = (
                    '-----BEGIN CERTIFICATE-----\n'
                    + cert_pem.strip()
                    + '\n-----END CERTIFICATE-----\n'
                )
                cert_obj = cx509.load_pem_x509_certificate(pem_wrapped.encode('utf-8'))
    except Exception as parse_err:
        raise ValueError(f"MS CA returned an unparseable certificate: {parse_err}")

    try:
        # Extract subject fields
        subject = cert_obj.subject
        cn_attrs = subject.get_attributes_for_oid(cx509.oid.NameOID.COMMON_NAME)
        cn = cn_attrs[0].value if cn_attrs else 'Unknown'

        # Extract SANs
        san_dns, san_ip, san_email, san_uri = [], [], [], []
        try:
            san_ext = cert_obj.extensions.get_extension_for_class(cx509.SubjectAlternativeName)
            san_dns = [str(n) for n in san_ext.value.get_values_for_type(cx509.DNSName)]
            san_ip = [str(n) for n in san_ext.value.get_values_for_type(cx509.IPAddress)]
            san_email = [str(n) for n in san_ext.value.get_values_for_type(cx509.RFC822Name)]
            san_uri = [str(n) for n in san_ext.value.get_values_for_type(cx509.UniformResourceIdentifier)]
        except cx509.ExtensionNotFound:
            pass

        # Store as base64-encoded PEM (UCM standard format)
        cert_pem_bytes = cert_obj.public_bytes(encoding=Encoding.PEM)
        cert_pem_b64 = base64.b64encode(cert_pem_bytes).decode('utf-8')

        # Validity dates: cert_obj exposes tz-aware UTC datetimes; UCM stores
        # naive UTC everywhere, so strip tzinfo here.
        valid_from = cert_obj.not_valid_before_utc.replace(tzinfo=None)
        valid_to = cert_obj.not_valid_after_utc.replace(tzinfo=None)

        # If a CSR record exists, UPDATE it in-place into a full certificate.
        # This avoids creating a duplicate Certificate row (one CSR + one cert).
        # The CSR's id is reused so existing references (links, audit) stay valid.
        # aki/ski come from the crt listener, in the form CA lookups match
        old_serial = stored_certificate_serial(csr) if csr is not None else None
        if csr is not None:
            # Atomic with the write: a certificate another source stored on this row stays
            if Certificate.query.filter(Certificate.id == csr.id, msca_may_write_clause()).update(
                    {Certificate.crt: cert_pem_b64}, synchronize_session=False) != 1:
                raise MSCASignedElsewhere(f"CSR id={csr.id} already holds a certificate from another source")
            csr.crt = cert_pem_b64
            csr.descr = csr.descr or f"MSCA: {cn} ({template})"
            csr.cert_type = csr.cert_type or 'server'
            csr.subject = cert_obj.subject.rfc4514_string()
            csr.subject_cn = cn
            csr.issuer = cert_obj.issuer.rfc4514_string()
            csr.serial_number = cert_obj.serial_number
            csr.valid_from = valid_from
            csr.valid_to = valid_to
            # Refresh SANs from issued cert (MS CA may have added/changed entries)
            csr.san_dns = json.dumps(san_dns) if san_dns else None
            csr.san_ip = json.dumps(san_ip) if san_ip else None
            csr.san_email = json.dumps(san_email) if san_email else None
            csr.san_uri = json.dumps(san_uri) if san_uri else None
            csr.source = 'msca'
            csr.imported_from = f"msca:{msca.name}"
            # A freshly issued cert is not revoked — matters on renewal, where
            # the row being updated in place may carry flags from the old cert.
            csr.revoked = False
            csr.revoked_at = None
            csr.revoke_reason = None
            cert = csr  # for downstream MSCARequest link
        else:
            # Fallback: no CSR record — create a new Certificate row
            cert = Certificate(
                refid=str(uuid.uuid4())[:8],
                descr=f"MSCA: {cn} ({template})",
                crt=cert_pem_b64,
                cert_type='server',
                subject=cert_obj.subject.rfc4514_string(),
                subject_cn=cn,
                issuer=cert_obj.issuer.rfc4514_string(),
                serial_number=cert_obj.serial_number,
                valid_from=valid_from,
                valid_to=valid_to,
                san_dns=json.dumps(san_dns) if san_dns else None,
                san_ip=json.dumps(san_ip) if san_ip else None,
                san_email=json.dumps(san_email) if san_email else None,
                san_uri=json.dumps(san_uri) if san_uri else None,
                source='msca',
                imported_from=f"msca:{msca.name}",
                created_by='system',
            )
            db.session.add(cert)
        db.session.flush()

        # Link the MSCA request to the cert (same id as CSR when csr is not None)
        msca_req = db.session.get(MSCARequest, msca_request_id)
        if msca_req:
            msca_req.cert_id = cert.id
            msca_req.status = 'issued'
            msca_req.issued_at = utc_now()

        ok, err = safe_commit(logger, "Failed to import MS CA signed certificate")
        if not ok:
            raise RuntimeError('Failed to import MS CA signed certificate')
        logger.info(f"Imported MS CA signed certificate: {cn} (id={cert.id})")
        if csr is not None:
            # A request queued for approval and signed through the Microsoft
            # CA meanwhile is closed as approved by that action
            from services.approval_gate import resolve_moot_requests
            actor = getattr(getattr(g, 'current_user', None), 'username', None) or 'system'
            resolve_moot_requests('csr', 'csr_id', csr.id, outcome='approved', username=actor,
                                  certificate_id=cert.id, reason='Signed by the Microsoft CA')
        if announce:
            from services.webhook_service import emit_cert_stored
            actor = getattr(getattr(g, 'current_user', None), 'username', None) or 'system'
            emit_cert_stored(cert.to_dict(), old_serial, cert_obj.serial_number,
                             ca_refid=cert.caref, actor=actor)

    except MSCASignedElsewhere:
        raise
    except Exception as e:
        logger.error(f"Failed to import MS CA signed certificate: {e}", exc_info=True)
        raise


def _rekey_key_type(public_key):
    """TrustStore key type reproducing *public_key* (every registry key TrustStore
    generates, same size, curve or level, plus the larger RSA sizes); ValueError otherwise."""
    label = key_algorithms.label_for_public_key(public_key)
    alg = key_algorithms.get(label) if label else None
    if (alg is None and isinstance(public_key, rsa.RSAPublicKey)
            and public_key.key_size >= MIN_RSA_BITS and str(public_key.key_size) in KEY_TYPES):
        return str(public_key.key_size)
    if alg is None or alg.trust_store_id not in KEY_TYPES:
        supported = ', '.join(a.display for a in key_algorithms.algorithms()
                              if a.trust_store_id in KEY_TYPES)
        raise ValueError(
            f'Cannot rekey for renewal: the original key is not one UCM can reproduce '
            f'(supported: {supported})')
    return alg.trust_store_id


def _generate_rekey_csr(cert):
    """Generate a new key pair + CSR (same subject and SANs) for an imported
    MS CA certificate that has no CSR/private key in UCM (AD CS never exports
    private keys). Stores the CSR and the encrypted key on the cert row and
    returns the CSR PEM string. Raises ValueError on unusable cert data.
    """
    import base64
    import json

    from cryptography import x509 as cx509
    from services.trust_store.csr_operations_mixin import CSROperationsMixin
    from utils.key_codec import store_pem_bytes

    if not cert.crt:
        raise ValueError("Certificate data not available")
    try:
        orig = cx509.load_pem_x509_certificate(base64.b64decode(cert.crt))
    except Exception:
        raise ValueError("Stored certificate is unreadable; cannot rekey for renewal")

    key_type = _rekey_key_type(orig.public_key())

    def _san(col):
        try:
            return json.loads(col) if col else []
        except Exception:
            return []

    csr_pem_bytes, key_pem_bytes = CSROperationsMixin.generate_csr(
        subject=orig.subject,
        key_type=key_type,
        san_dns=_san(cert.san_dns),
        san_ip=_san(cert.san_ip),
        san_email=_san(cert.san_email),
        san_uri=_san(cert.san_uri),
        san_upn=cert.san_upn_list,
    )
    cert.csr = base64.b64encode(csr_pem_bytes).decode('utf-8')
    cert.prv = store_pem_bytes(key_pem_bytes)
    return csr_pem_bytes.decode('utf-8')


def renew_via_msca(cert, username=None):
    """Renew an MS-CA-issued certificate by resubmitting its original CSR
    (same key, same subject/SANs) to the connection and template that issued
    it. Imported certs without a CSR/key are renewed by rekey: a fresh key
    pair + CSR with the same subject/SANs is generated and stored on the cert.

    Returns the submit_csr result dict: status 'issued' (cert updated in place)
    or 'pending' (imported later by the request-status poll).
    Raises ValueError for unrenewable certs, PermissionError for EOBO certs
    renewed without admin:system.
    """
    import base64

    # Recover the connection + template from the original signing request;
    # fall back to imported_from ("msca:<name>") if the request row is gone
    # (e.g. partial restore).
    req = (MSCARequest.query
           .filter((MSCARequest.cert_id == cert.id) | (MSCARequest.csr_id == cert.id))
           .filter(MSCARequest.status == 'issued')
           .order_by(MSCARequest.id.desc())
           .first())

    msca = db.session.get(MicrosoftCA, req.msca_id) if req else None
    if not msca and cert.imported_from and cert.imported_from.startswith('msca:'):
        msca = MicrosoftCA.query.filter_by(name=cert.imported_from[len('msca:'):]).first()
    if not msca:
        raise ValueError("The Microsoft CA connection that issued this certificate no longer exists")
    if not msca.enabled:
        raise ValueError("Microsoft CA connection is disabled")

    # Inventory-imported requests carry template 'unknown' — not submittable.
    template = (req.template if req else None) or msca.default_template
    if not template or template == 'unknown':
        template = msca.default_template
    if not template:
        raise ValueError("Original certificate template unknown; sign a new CSR via the Microsoft CA instead")

    # EOBO renewals re-issue a cert for another principal — same elevated
    # permission as the initial EOBO signing.
    enrollee_name = req.enrollee_name if req else None
    enrollee_upn = req.enrollee_upn if req else None
    if enrollee_name or enrollee_upn:
        user_perms = getattr(g, 'permissions', []) or []
        if '*' not in user_perms and not _has_perm('admin:system', user_perms):
            raise PermissionError("Renewing an EOBO-issued certificate requires admin:system permission")

    rekey_previous = None
    if cert.csr:
        try:
            csr_pem = base64.b64decode(cert.csr).decode('utf-8')
        except Exception:
            csr_pem = cert.csr
    else:
        # Imported cert (e.g. inventory sync) with no CSR/key in UCM — renew
        # by REKEY: fresh key pair + CSR with the same subject and SANs.
        # Persist both BEFORE submission so a 'pending' approval can still be
        # finalized by the request-status poll.
        rekey_previous = (cert.csr, cert.prv)
        csr_pem = _generate_rekey_csr(cert)
        ok, _resp = safe_commit(logger, "Failed to persist renewal key material")
        if not ok:
            raise ValueError("Failed to persist renewal key material")

    def _rollback_rekey():
        """A failed submission must not leave the active cert paired with a
        key/CSR that never got signed — the row would lose its 'No Key' badge
        and a PKCS12 export would bundle the wrong private key."""
        if rekey_previous is None:
            return
        cert.csr, cert.prv = rekey_previous
        safe_commit(logger, "Failed to roll back rekey material")

    try:
        result = MicrosoftCAService.submit_csr(
            msca_id=msca.id,
            csr_pem=csr_pem,
            template=template,
            csr_id=cert.id,
            submitted_by=username,
            enrollee_name=enrollee_name,
            enrollee_upn=enrollee_upn,
        )
    except Exception:
        _rollback_rekey()
        raise

    if result['status'] == 'issued':
        _import_signed_cert(cert, result.get('cert_pem'), msca, template, result['request_id'])
    elif result['status'] != 'pending':
        # denied/failed: the submission is terminal, restore the row
        _rollback_rekey()

    _audit('msca.renew', msca, f"cert_id={cert.id} template={template} status={result['status']}")
    return result
