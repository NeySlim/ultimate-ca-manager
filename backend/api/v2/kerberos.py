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
# Real keytabs are a handful of KB (a few dozen bytes per key entry); 256KB
# is generous headroom while still catching an obviously-wrong upload early.
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
    return {
        'keytab_valid': inspection['valid'],
        'keytab_principal': inspection['principal'],
        'keytab_error': inspection['error'],
        'keytab_spn_matches': (
            inspection['valid'] and bool(spn) and inspection['principal'] == spn
        ),
    }


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
    return success_response(data={
        'enabled': negotiate_auth.is_enabled(),
        'spn': negotiate_auth.get_spn(),
        'keytab_set': negotiate_auth.KEYTAB_PATH.exists(),
        'library_available': negotiate_auth.is_library_available(),
        'configured': negotiate_auth.is_configured(),
        'reason': negotiate_auth.not_configured_reason(),
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
    """Upload the keytab backing the Kerberos binding's acceptor
    credential. Overwrites any previously uploaded keytab.

    Validated with the same GSSAPI keytab-loading call the real acceptor
    uses (``negotiate_auth.inspect_keytab``) *before* it's persisted -- a
    keytab that doesn't even parse is rejected outright rather than
    silently replacing a working one, closing the gap where the only
    previous feedback was a generic "settings saved" toast with no
    indication the upload was actually usable (issue #229 item 4). A
    keytab that parses but doesn't match the configured SPN is still
    accepted (a keytab can legitimately carry more than one principal, or
    the SPN field might be the one that's wrong) -- surfaced via
    ``keytab_spn_matches`` in the response for the UI to warn on, not a
    hard rejection.
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

    # The default profile holds the keytab; the file every node writes is rebuilt from it
    # and reload_keytab reaches the other nodes (HA)
    from services import cluster_commands, windows_profiles
    user = getattr(g, 'current_user', None)
    profile = windows_profiles.default_for_write(getattr(user, 'username', None), fill=False)
    profile.set_keytab(file_content)
    windows_profiles.fill_realm(profile)
    windows_profiles.publish_keytab(actor=getattr(user, 'username', None))
    cluster_commands.emit(cluster_commands.RELOAD_KEYTAB)
    ok, _err = safe_commit(logger, "Failed to store Kerberos keytab")
    if not ok:
        return _err

    try:
        negotiate_auth.sync_keytab_file(file_content)
    except OSError as e:
        logger.error("Failed to write Kerberos keytab: %s", e)
        return error_response('Failed to save keytab', 500)

    AuditService.log_action(
        action='kerberos_keytab_upload',
        resource_type='kerberos',
        resource_name='Kerberos Keytab',
        details=f"Uploaded a new Kerberos keytab (principal: {inspection['principal']})",
        success=True
    )

    return success_response(message='Keytab uploaded', data=_keytab_status())
