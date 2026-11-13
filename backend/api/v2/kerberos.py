"""
Kerberos/SPNEGO Management Routes v2.0
/api/v2/kerberos/* - shared config for MS-XCEP/MS-WSTEP's Kerberos binding

One SPN + keytab serves both protocols' Kerberos-bound endpoints
(ADPolicyProvider_CEP_Kerberos, ADCertificateService_CES_Kerberos) since
they run on the same host under the same identity — see
services/kerberos/negotiate_auth.py for the actual HTTP Negotiate handshake.
"""
import logging
import os

from flask import Blueprint, g, request

from auth.unified import require_auth
from models import db, SystemConfig
from services.audit_service import AuditService
from services.kerberos import negotiate_auth
from utils.db_transaction import safe_commit
from utils.response import success_response, error_response

logger = logging.getLogger(__name__)

bp = Blueprint('kerberos_v2', __name__)

KEYTAB_EXTENSIONS = {'.keytab', '.kt'}
# Per profile: a keytab is a few dozen bytes per key entry; the composed file has no cap
MAX_KEYTAB_SIZE = 256 * 1024


def _set_config(key, value):
    config = SystemConfig.query.filter_by(key=key).first()
    if config:
        config.value = str(value) if value is not None else None
    else:
        config = SystemConfig(key=key, value=str(value) if value is not None else None)
        db.session.add(config)


def _keytab_status():
    """Re-inspects the persisted keytab on every call rather than caching
    from upload time -- cheap (a single GSSAPI keytab load), and means the
    settings page always reflects the keytab actually on disk, not a stale
    snapshot from whenever it was last uploaded (see issue #229 item 4: no
    persistent way to tell a keytab is valid short of the generic save
    toast at upload time)."""
    inspection = negotiate_auth.inspect_keytab()
    spn = negotiate_auth.get_spn()
    entries = inspection.get('entries') or []
    principals = {e['principal'] for e in entries} or {inspection['principal']}
    return {
        'keytab_valid': inspection['valid'],
        'keytab_principal': inspection['principal'],
        'keytab_error': inspection['error'],
        'keytab_entries': entries,
        'keytab_spn_matches': inspection['valid'] and bool(spn) and spn in principals,
    }


def _foreign_entries(entries, realm):
    """The principals of *entries* that are not ``<service>/<SPN host>@<realm>``: the unnamed
    acceptor takes a ticket for any entry, so a stray one widens what UCM accepts."""
    parsed = negotiate_auth._parse_spn(negotiate_auth.get_spn())
    service, host = parsed if parsed else ('HTTP', None)
    hosts = {e.components[1].lower() for e in entries if len(e.components) == 2}
    if host is None and len(hosts) == 1:
        host = next(iter(hosts))
    return [e.principal for e in entries
            if e.realm != realm or len(e.components) != 2 or e.components[0] != service
            or e.components[1].lower() != (host or '').lower()]


def _realm_problem(realm):
    """(message, status) when *realm* cannot be the default profile's, else None."""
    from services import windows_profiles
    return windows_profiles.realm_problem(realm, windows_profiles.default_profile())


@bp.route('/api/v2/kerberos/config', methods=['GET'])
@require_auth(['read:kerberos'])
def get_kerberos_config():
    """Get Kerberos/SPNEGO configuration; ``reason`` says why it is not configured."""
    from services import windows_profiles
    profile = windows_profiles.default_profile()
    # The default profile's view (A1), as this route has shown it until the profile API replaces it
    reason = negotiate_auth.not_configured_reason() or windows_profiles.kerberos_refusal(profile)
    return success_response(data={
        'enabled': negotiate_auth.is_enabled(),
        'spn': negotiate_auth.get_spn(),
        'keytab_set': negotiate_auth.KEYTAB_PATH.exists(),
        'library_available': negotiate_auth.is_library_available(),
        'configured': reason is None,
        'reason': reason,
        'realm': profile.realm if profile is not None else None,
        **_keytab_status(),
    })


@bp.route('/api/v2/kerberos/config', methods=['PATCH'])
@require_auth(['write:kerberos'])
def update_kerberos_config():
    """Update Kerberos/SPNEGO configuration (enabled flag, SPN, realm of the default profile)."""
    data = request.json or {}
    if 'realm' in data:
        problem = _realm_problem(data['realm'])
        if problem:
            return error_response(problem[0], problem[1])

    if 'enabled' in data:
        _set_config('kerberos_enabled', 'true' if data['enabled'] else 'false')
    if 'spn' in data:
        _set_config('kerberos_spn', data['spn'] or '')
        from services import windows_profiles
        profile = windows_profiles.default_profile()
        if profile is not None:
            db.session.flush()
            windows_profiles.fill_realm(profile)
    if 'realm' in data:
        from services import windows_profiles
        windows_profiles.default_for_write(getattr(getattr(g, 'current_user', None), 'username', None)
                                           ).realm = data['realm']

    ok, _err = safe_commit(logger, "Failed to update Kerberos configuration")
    if not ok:
        return _err

    AuditService.log_action(
        action='kerberos_config_update',
        resource_type='kerberos',
        resource_name='Kerberos Configuration',
        details='Updated Kerberos/SPNEGO configuration',
        success=True
    )

    return success_response(message='Kerberos configuration saved')


@bp.route('/api/v2/kerberos/keytab', methods=['POST'])
@require_auth(['write:kerberos'])
def upload_kerberos_keytab():
    """Upload the keytab of a Windows enrollment profile (form field ``profile_id``, else the
    default profile), replacing the one it held. Loaded with GSSAPI before it is stored; every
    entry must be ``<SPN service>/<SPN host>@<realm of the profile>``, else 400. The acceptor
    reads the file composed from the keytabs of every profile, enabled or not.
    """
    if 'file' not in request.files:
        return error_response('No file provided', 400)

    from utils.file_validation import validate_upload
    try:
        file_content, _safe_filename = validate_upload(
            request.files['file'], KEYTAB_EXTENSIONS, max_size=MAX_KEYTAB_SIZE,
        )
    except ValueError as e:
        return error_response(str(e), 400)

    import tempfile
    fd, tmp_path = tempfile.mkstemp(prefix='.kerberos-keytab-check-')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(file_content)
        inspection = negotiate_auth.inspect_keytab(tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    if not inspection['valid']:
        return error_response(
            f"Keytab is not a valid krb5 keytab: {inspection['error']}", 400
        )
    from services.kerberos.keytab_format import read_entries
    entries = read_entries(file_content)
    if not entries:
        return error_response('Keytab holds no entry', 400)

    # The profile holds the keytab; the file every node writes is composed from the profiles
    # and reload_keytab reaches the other nodes (HA)
    from models import WindowsEnrollmentProfile
    from services import cluster_commands, windows_profiles
    user = getattr(g, 'current_user', None)
    profile_id = request.form.get('profile_id')
    if profile_id:
        # A13: profiles are written with write:xcep, whichever route carries the keytab
        from auth.unified import has_permission
        if not has_permission('write:xcep', getattr(g, 'permissions', None) or []):
            return error_response('Insufficient permissions', 403)
        profile = (db.session.get(WindowsEnrollmentProfile, int(profile_id))
                   if profile_id.isdigit() else None)
        if profile is None:
            return error_response('Windows enrollment profile not found', 404)
        profile.updated_by = getattr(user, 'username', None)
    else:
        profile = windows_profiles.default_for_write(getattr(user, 'username', None), fill=False)
    profile.set_keytab(file_content)
    windows_profiles.fill_realm(profile)
    if profile.realm is None:
        db.session.rollback()
        return error_response('the profile has no realm: set it, then upload its keytab', 400)
    foreign = _foreign_entries(entries, profile.realm)
    if foreign:
        db.session.rollback()
        return error_response(f"Keytab entries outside HTTP/<host>@{profile.realm}: "
                              f"{', '.join(sorted(set(foreign)))}", 400)
    try:
        windows_profiles.publish_keytab(actor=getattr(user, 'username', None))
    except ValueError as e:
        db.session.rollback()
        return error_response(f'Keytab not composed: {e}', 409)
    cluster_commands.emit(cluster_commands.RELOAD_KEYTAB)
    ok, _err = safe_commit(logger, "Failed to store Kerberos keytab")
    if not ok:
        return _err

    try:
        negotiate_auth.write_stored_keytab()
    except (OSError, ValueError) as e:
        logger.error("Failed to write Kerberos keytab: %s", e)
        return error_response('Failed to save keytab', 500)

    AuditService.log_action(
        action='kerberos_keytab_upload',
        resource_type='kerberos',
        resource_name=f'Kerberos Keytab ({profile.name})',
        details=f"Uploaded a Kerberos keytab for profile {profile.name} (principals: "
                f"{', '.join(sorted({e.principal for e in entries}))})",
        success=True
    )

    return success_response(message='Keytab uploaded', data=_keytab_status())
