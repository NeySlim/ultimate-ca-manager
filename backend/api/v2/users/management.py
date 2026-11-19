"""
Users Management Routes (password reset, toggle, unlock, import)
"""

from . import bp, validate_password_strength
from flask import request, g
import csv
import io
import logging

from auth.unified import refuse_api_key_on_own_account, require_auth
from auth.session_reverify import check_session_password
from auth.session_start import (
    closed_sessions_note, end_sessions_on_commit, keep_own_session, sessions_closed_by,
)
from utils.response import success_response, error_response
from auth.permissions import BUILTIN_ROLES
from utils.db_transaction import safe_commit
from models import db, User, UserSSOIdentity
from models.user import local_email_holder, local_email_taken
from services.audit_service import AuditService

logger = logging.getLogger(__name__)


def _is_last_active_admin(user):
    """True iff this user is the only remaining active admin."""
    if not user or user.role != 'admin' or not user.active:
        return False
    others = User.query.filter(
        User.id != user.id,
        User.role == 'admin',
        User.active.is_(True),
    ).count()
    return others == 0


@bp.route('/api/v2/users/<int:user_id>/reset-password', methods=['POST'])
@require_auth(['write:users'])
def reset_user_password(user_id):
    """
    Reset user password (admin action)

    POST /api/v2/users/{user_id}/reset-password
    {
        "new_password": "NewSecurePass123!"
    }
    """
    refused = refuse_api_key_on_own_account(user_id)
    if refused:
        return refused
    # SECURITY: Only admins can reset other users' passwords
    if g.current_user.role != 'admin' and g.current_user.id != user_id:
        return error_response('Access denied', 403)

    user = db.session.get(User, user_id)
    if not user:
        return error_response('User not found', 404)

    data = request.get_json()

    if not data.get('new_password'):
        return error_response('New password is required', 400)

    # SECURITY: Self-reset must prove knowledge of the current password
    # (otherwise a stolen session = silent password rotation = full takeover)
    if g.current_user.id == user_id:
        current = data.get('current_password') or data.get('old_password')
        if not current:
            return error_response('Current password is required', 400)
        refused = check_session_password(
            user, current, error_response('Current password is required', 400))
        if refused:
            return refused

    # SECURITY: Validate password strength
    is_valid, error_msg = validate_password_strength(data['new_password'])
    if not is_valid:
        return error_response(error_msg, 400)

    # Update password; the user's sessions end with the old one, and so does the count of
    # guesses at it
    user.set_password(data['new_password'])
    user.clear_failed_logins()

    try:
        db.session.commit()
        keep_own_session(user)

        AuditService.log_action(
            action='password_change',
            resource_type='user',
            resource_id=str(user_id),
            resource_name=user.username,
            details=f'Password reset for user: {user.username}',
            success=True
        )

        # Send password changed notification
        try:
            from services.notification_service import NotificationService
            admin_username = g.current_user.username if hasattr(g, 'current_user') else 'admin'
            NotificationService.on_password_changed(user, admin_username)
        except Exception:
            pass  # Non-blocking

        return success_response(
            message=f'Password reset successfully for user {user.username}'
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to reset password: {e}", exc_info=True)
        return error_response('Failed to reset password', 500)


@bp.route('/api/v2/users/<int:user_id>/reset-2fa', methods=['POST'])
@require_auth(['write:users'])
def reset_user_2fa(user_id):
    """
    Clear a user's 2FA — admin break-glass for a locked-out user (#141).

    POST /api/v2/users/{user_id}/reset-2fa

    TOTP and the key-as-second-factor choice are cleared; registered keys stay
    (a lost one is removed with DELETE /api/v2/users/{id}/webauthn/{key}). Under
    enforcement, a user left without a key re-enrols on next login; ``totp_exempt``
    lets them in without 2FA.
    """
    refused = refuse_api_key_on_own_account(user_id)
    if refused:
        return refused
    # SECURITY: only admins may reset another user's 2FA
    if g.current_user.role != 'admin':
        return error_response('Access denied', 403)

    user = db.session.get(User, user_id)
    if not user:
        return error_response('User not found', 404)

    user.totp_confirmed = False
    user.totp_secret = None
    user.backup_codes = None
    user.webauthn_2fa = False
    user.end_sessions()
    ok, _err = safe_commit(logger, "Failed to reset user 2FA")
    if not ok:
        return _err
    keep_own_session(user)

    AuditService.log_action(
        action='mfa_reset',
        resource_type='user',
        resource_id=str(user.id),
        resource_name=user.username,
        details=f'2FA reset by {g.current_user.username} for user: {user.username}',
        success=True,
    )
    return success_response(message=f'2FA reset for user {user.username}')


@bp.route('/api/v2/users/<int:user_id>/toggle', methods=['PATCH'])
@bp.route('/api/v2/users/<int:user_id>/toggle-active', methods=['POST'])
@require_auth(['write:users'])
def toggle_user_status(user_id):
    """
    Toggle user active/inactive status (admin only)

    PATCH /api/v2/users/{user_id}/toggle
    """
    # SECURITY: Only admins can toggle user status
    if g.current_user.role != 'admin':
        return error_response('Insufficient permissions', 403)

    # Prevent toggling yourself
    if g.current_user.id == user_id:
        return error_response('Cannot toggle your own account status', 403)

    user = db.session.get(User, user_id)
    if not user:
        return error_response('User not found', 404)

    # Preserve at least one active admin (toggling the last admin off = lockout)
    if user.active and _is_last_active_admin(user):
        return error_response('Cannot deactivate the last active admin', 409)

    # Toggle status
    user.active = not user.active
    status = 'activated' if user.active else 'deactivated'

    try:
        db.session.commit()
        AuditService.log_action(
            action='user_activate' if user.active else 'user_deactivate',
            resource_type='user',
            resource_id=str(user_id),
            resource_name=user.username,
            details=f'User {user.username} {status}',
            success=True
        )
        return success_response(
            data=user.to_dict(),
            message=f'User {user.username} {status} successfully'
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to toggle user status: {e}", exc_info=True)
        return error_response('Failed to toggle user status', 500)


def _sso_admin_target(user_id):
    """(account, None) for an administrator's change of who opens it, else (None, answer).
    write:users, which the routes require, is reserved to the administrator role."""
    refused = refuse_api_key_on_own_account(user_id)
    if refused:
        return None, refused
    user = db.session.get(User, user_id)
    if not user:
        return None, error_response('User not found', 404)
    return user, None


def _identity_of(user, identity_id):
    return next((row for row in user.sso_identities if row.id == identity_id), None)


def _locked(user_id):
    """The account locked, its sessions ending with the commit: what opens it changes."""
    owner = end_sessions_on_commit(user_id)
    if owner is None:
        db.session.rollback()
    return owner


def _expected_tenant(provider, data, default=None):
    """(tenant, None): the tenant an unbound attachment to ``provider`` may be adopted from, read
    from ``expected_tenant`` in ``data`` else ``default``; it must be one the provider accepts
    now. (None, answer) when it is refused."""
    from services.oidc_id_token import OIDCValidationError, has_tenants, provider_tenants
    value = data.get('expected_tenant', default)
    if value is None:
        return None, None
    if provider is None or not has_tenants(provider):
        return None, error_response('expected_tenant applies only to a provider with accepted '
                                    'tenants', 400)
    try:
        accepted = provider_tenants(provider)
    except OIDCValidationError:
        return None, error_response('The accepted tenants of this provider are not readable', 400)
    tenant = value.strip().lower() if isinstance(value, str) else None
    if tenant not in accepted:
        return None, error_response("expected_tenant must be one of the provider's accepted "
                                    "tenants", 400)
    return tenant, None


def _former_tenant(provider, external_id):
    """The tenant of a bound ``<tid>/<sub>`` identity while ``provider`` still accepts it, else None."""
    from services.oidc_id_token import OIDCValidationError, has_tenants, provider_tenants
    if provider is None or not has_tenants(provider) or not external_id or '/' not in external_id:
        return None
    try:
        accepted = provider_tenants(provider)
    except OIDCValidationError:
        return None
    tid = external_id.split('/', 1)[0].lower()
    return tid if tid in accepted else None


def _tenant_note(row):
    return f', expected tenant {row.expected_tenant}' if row.expected_tenant else ''


@bp.route('/api/v2/users/<int:user_id>/sso-identities', methods=['GET'])
@require_auth(['read:users'])
def list_user_sso_identities(user_id):
    """The providers attached to an account, each bound, pending or orphaned."""
    user = db.session.get(User, user_id)
    if not user:
        return error_response('User not found', 404)
    return success_response(data=[row.to_dict() for row in user.sso_identities])


@bp.route('/api/v2/users/<int:user_id>/sso-identities', methods=['POST'])
@require_auth(['write:users'])
def attach_user_sso_provider(user_id):
    """Attach a provider to any account (admin only); the providers it has keep opening it.
    The attachment is not bound yet: the next sign-in through this provider with the
    account's name, or its verified e-mail (#136), binds its stable identity. An orphan
    the same IdP left on the account is taken back with its identity. The username is kept (#138).

    POST /api/v2/users/{user_id}/sso-identities
    Body: {"provider_id": int, "remove_password": bool (optional, default false),
           "expected_tenant": str (optional; a provider with accepted tenants adopts the
           attachment from this tenant only, none without it)}
    """
    from models.sso import SSOProvider
    from api.v2.sso.account_state import SSO_NO_PASSWORD, attachments_text, own_identity

    user, refused = _sso_admin_target(user_id)
    if refused:
        return refused
    data = request.get_json(silent=True) or {}
    provider_id = data.get('provider_id')
    if not isinstance(provider_id, int) or isinstance(provider_id, bool):
        return error_response('provider_id is required', 400)
    remove_password = data.get('remove_password', False)
    if not isinstance(remove_password, bool):
        return error_response('remove_password must be true or false', 400)
    provider = db.session.get(SSOProvider, provider_id)
    if not provider:
        return error_response('SSO provider not found', 404)
    # Changing one's own password asks for the current one: removing it is another admin's act
    if remove_password and g.current_user.id == user_id:
        return error_response('You cannot remove the local password of your own account', 400)
    expected_tenant, refused = _expected_tenant(provider, data)
    if refused:
        return refused

    # A new provider opens the account: the sessions opened before it end.
    user = _locked(user.id)
    if user is None:
        return error_response('User not found', 404)
    if own_identity(user, provider) is not None:
        db.session.rollback()
        return error_response('This provider is already attached to the account: reset its '
                              'identity instead', 409)
    before = attachments_text(user)
    key = provider.idp_key()
    orphans = [row for row in user.sso_identities
               if key and row.provider_id is None and row.orphan_of == key]
    # An explicit attachment never weakens a binding: the orphan comes back with its identity
    taken_back = next((row for row in orphans if row.external_id), orphans[0] if orphans else None)
    if taken_back is not None:
        taken_back.provider, taken_back.orphan_of = provider, None
        taken_back.expected_tenant = expected_tenant
    else:
        user.sso_identities.append(UserSSOIdentity(provider=provider, expected_tenant=expected_tenant,
                                                   created_by=g.current_user.username))
    identity = taken_back.external_id if taken_back is not None else None
    drop_password = remove_password and user.password_hash != SSO_NO_PASSWORD
    if drop_password:
        # Same state as an account the provider created: no password door opens it.
        from auth.initial_admin import forget_generated
        forget_generated(user)
        user.password_hash = SSO_NO_PASSWORD
        user.password_reset_token = None
        user.password_reset_expires = None
    # An account without a password signs in through its providers only: a change
    # owed would confine its SSO session. One with a password keeps both.
    if user.password_hash == SSO_NO_PASSWORD:
        user.force_password_change = False

    def held_elsewhere():
        # The orphan's identity already opens another account through this provider
        holder = UserSSOIdentity.query.filter(UserSSOIdentity.provider_id == provider_id,
                                              UserSSOIdentity.external_id == identity,
                                              UserSSOIdentity.user_id != user_id).first()
        if identity and holder is not None:
            return error_response('The identity this account keeps from the same IdP already '
                                  'opens another account through this provider', 409)
        return None

    ok, err = safe_commit(logger, f"Failed to attach user {user_id} to SSO",
                          on_conflict=held_elsewhere)
    if not ok:
        return err
    closed = sessions_closed_by(user)
    note = ', taking back its orphan of the same IdP' if taken_back is not None else ''
    note += f', expected tenant {expected_tenant}' if expected_tenant else ''
    note += ', local password removed' if drop_password else ''
    AuditService.log_action(
        action='user_sso_attach',
        resource_type='user',
        resource_id=str(user.id),
        resource_name=user.username,
        details=(f'Attached SSO provider {provider.name!r} to account {user.username!r} '
                 f'(before: {before}{note}, {closed_sessions_note(closed)})'),
        success=True,
    )
    return success_response(
        data=user.to_dict(),
        message=f'Provider {provider.name} attached to the account',
        meta={'other_sessions_closed': closed},
        status=201)


@bp.route('/api/v2/users/<int:user_id>/sso-identities/<int:identity_id>/reset', methods=['POST'])
@require_auth(['write:users'])
def reset_user_sso_identity(user_id, identity_id):
    """Clear the stable identity of one attachment (admin only): the IdP changed it, and
    the next sign-in through that provider with the account's name or its verified e-mail
    binds the new one. Through a provider with accepted tenants, only from the expected tenant:
    the former identity's by default, or ``expected_tenant`` (also settable on an unbound row).

    POST /api/v2/users/{user_id}/sso-identities/{identity_id}/reset
    Body (optional): {"expected_tenant": str | null}
    """
    from api.v2.sso.account_state import bounded, identity_text

    user, refused = _sso_admin_target(user_id)
    if refused:
        return refused
    if _identity_of(user, identity_id) is None:
        return error_response('SSO attachment not found', 404)
    user = _locked(user.id)
    row = _identity_of(user, identity_id) if user is not None else None
    if row is None:
        db.session.rollback()
        return error_response('SSO attachment not found', 404)
    data = request.get_json(silent=True) or {}
    data = data if isinstance(data, dict) else {}
    if row.external_id is None and 'expected_tenant' not in data:
        db.session.rollback()
        return success_response(data=user.to_dict(), message='This attachment is not bound yet',
                                meta={'other_sessions_closed': 0})
    former = row.external_id
    expected, refused = _expected_tenant(row.provider, data, _former_tenant(row.provider, former))
    if refused:
        db.session.rollback()
        return refused
    where = identity_text(row)
    row.bind(None)
    row.expected_tenant = expected
    ok, err = safe_commit(logger, f"Failed to reset the SSO identity of user {user_id}")
    if not ok:
        return err
    closed = sessions_closed_by(user)
    AuditService.log_action(
        action='user_sso_reset',
        resource_type='user',
        resource_id=str(user.id),
        resource_name=user.username,
        details=((f'Reset identity {bounded(former)!r} of account {user.username!r} ' if former
                  else f'Set the expected tenant of an unbound attachment of {user.username!r} ')
                 + f'({where}{_tenant_note(row)}, {closed_sessions_note(closed)})'),
        success=True,
    )
    return success_response(data=user.to_dict(),
                            message='SSO identity reset' if former else 'Expected tenant set',
                            meta={'other_sessions_closed': closed})


@bp.route('/api/v2/users/<int:user_id>/sso-identities/<int:identity_id>', methods=['DELETE'])
@require_auth(['write:users'])
def detach_user_sso_provider(user_id, identity_id):
    """Detach one provider from an account (admin only); the others keep opening it. An
    account without a password whose last attachment goes must set one before it can log in.

    DELETE /api/v2/users/{user_id}/sso-identities/{identity_id}
    """
    from models import user as user_model
    from api.v2.sso.account_state import SSO_NO_PASSWORD, identity_text

    user, refused = _sso_admin_target(user_id)
    if refused:
        return refused
    if _identity_of(user, identity_id) is None:
        return error_response('SSO attachment not found', 404)
    user = _locked(user.id)
    row = _identity_of(user, identity_id) if user is not None else None
    if row is None:
        db.session.rollback()
        return error_response('SSO attachment not found', 404)
    last = len(user.sso_identities) == 1
    # E-mail is unique among local accounts (#136): the last row going makes it one.
    taken = ('Another local account uses this e-mail address: change one of them before '
             'detaching the last provider')
    if last and user_model.local_email_holder(user.email, other_than=user.id) is not None:
        db.session.rollback()
        return error_response(taken, 409)
    uid, email = user.id, user.email
    what = identity_text(row)
    user.sso_identities.remove(row)
    needs_password = last and user.password_hash == SSO_NO_PASSWORD
    if needs_password:
        user.force_password_change = True

    ok, err = safe_commit(logger, f"Failed to detach user {user_id} from SSO",
                          on_conflict=lambda: user_model.local_email_taken(email, uid, taken))
    if not ok:
        return err
    closed = sessions_closed_by(user)
    note = ', now a local account' if last else ''
    note += ' that must set a password' if needs_password else ''
    AuditService.log_action(
        action='user_sso_detach',
        resource_type='user',
        resource_id=str(user.id),
        resource_name=user.username,
        details=(f'Detached {what} from account {user.username!r}'
                 f'{note} ({closed_sessions_note(closed)})'),
        success=True,
    )
    msg = 'Provider detached from the account'
    if needs_password:
        msg += ', set a password for this account'
    return success_response(data=user.to_dict(), message=msg,
                            meta={'other_sessions_closed': closed})


@bp.route('/api/v2/users/<int:user_id>/unlock', methods=['POST'])
@require_auth(['write:users'])
def unlock_user(user_id):
    """
    Unlock a locked user account (admin only)

    POST /api/v2/users/{user_id}/unlock
    """
    if g.current_user.role != 'admin':
        return error_response('Insufficient permissions', 403)

    user = db.session.get(User, user_id)
    if not user:
        return error_response('User not found', 404)

    try:
        # Decided on the stored row: a lock another node wrote after this read is lifted
        if not user.clear_failed_logins():
            db.session.rollback()
            return success_response(data=user.to_dict(), message='Account is not locked')
        db.session.commit()
        AuditService.log_action(
            action='user_unlock',
            resource_type='user',
            resource_id=str(user_id),
            resource_name=user.username,
            details=f'User {user.username} account unlocked by admin',
            success=True
        )
        return success_response(data=user.to_dict(), message=f'User {user.username} unlocked successfully')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to unlock user {user_id}: {e}")
        return error_response('Failed to unlock user', 500)


def _import_conflict(added):
    """The 409 of an import a concurrent creation beat to a username or a local e-mail."""
    for username, email in added:
        if User.query.filter_by(username=username).first() is not None:
            return error_response(f"Username '{username}' already exists", 409)
        taken = local_email_taken(email, message=f"Email '{email}' already exists")
        if taken is not None:
            return taken
    return None


@bp.route('/api/v2/users/import', methods=['POST'])
@require_auth(['write:users'])
def import_users():
    """
    Import users from CSV file (admin only)

    POST /api/v2/users/import
    Content-Type: multipart/form-data

    CSV format:
    username,email,full_name,role,password
    john.doe,john@example.com,John Doe,operator,SecurePass123!
    """
    # SECURITY: Only admins can import users
    if g.current_user.role != 'admin':
        return error_response('Insufficient permissions', 403)

    if 'file' not in request.files:
        return error_response('No file provided', 400)

    file = request.files['file']
    if file.filename == '':
        return error_response('No file selected', 400)

    if not file.filename.endswith('.csv'):
        return error_response('File must be CSV format', 400)

    try:
        # Read CSV — bound the upload size and the number of rows so an
        # admin (or anyone with admin creds) can't DoS the worker by
        # uploading a multi-GB CSV or a 10M-row file. 5 MB / 10 000 rows
        # is enough for any realistic on-prem user-bulk-import while
        # keeping memory + per-row password hashing time bounded.
        MAX_CSV_BYTES = 5 * 1024 * 1024
        MAX_CSV_ROWS = 10_000

        # Honor Content-Length cheaply if present
        cl = request.content_length
        if cl is not None and cl > MAX_CSV_BYTES:
            return error_response(
                f'CSV too large (max {MAX_CSV_BYTES // 1024} KB)', 413
            )

        raw = file.stream.read(MAX_CSV_BYTES + 1)
        if len(raw) > MAX_CSV_BYTES:
            return error_response(
                f'CSV too large (max {MAX_CSV_BYTES // 1024} KB)', 413
            )

        try:
            decoded = raw.decode('utf-8')
        except UnicodeDecodeError:
            return error_response('CSV must be UTF-8 encoded', 400)

        stream = io.StringIO(decoded)
        csv_reader = csv.DictReader(stream)

        imported = 0
        skipped = 0
        errors = []
        added = []

        for row in csv_reader:
            row_num = imported + skipped + 1
            if row_num > MAX_CSV_ROWS:
                errors.append(
                    f"Stopped at row {MAX_CSV_ROWS}: per-import row "
                    "limit reached"
                )
                break

            # Required fields
            if not row.get('username') or not row.get('email') or not row.get('password'):
                skipped += 1
                errors.append(f"Row {row_num}: Missing required fields")
                continue

            # SECURITY: Validate password strength
            is_valid, error_msg = validate_password_strength(row['password'])
            if not is_valid:
                skipped += 1
                errors.append(f"Row {row_num}: {error_msg}")
                continue

            # Check if user exists
            if User.query.filter_by(username=row['username']).first():
                skipped += 1
                errors.append(f"Row {row_num}: Username '{row['username']}' already exists")
                continue

            # E-mail is unique among local accounts only (#136), as for a single creation
            if local_email_holder(row['email']) is not None:
                skipped += 1
                errors.append(f"Row {row_num}: Email '{row['email']}' already exists")
                continue

            # Create user. This used to check against a three-name list
            # that had lost `auditor`, and to rewrite anything outside it to
            # `viewer` without a word -- so a file of auditors came back as
            # viewers, who have no read:audit and cannot read the audit log.
            # Say so instead, as the single-user route next door does.
            role = (row.get('role') or 'viewer').strip() or 'viewer'
            if role not in BUILTIN_ROLES:
                skipped += 1
                errors.append(
                    f"Row {row_num}: Invalid role '{role}'. Must be one of: "
                    + ', '.join(BUILTIN_ROLES))
                continue

            user = User(
                username=row['username'],
                email=row['email'],
                full_name=row.get('full_name', ''),
                role=role,
                active=True
            )
            user.set_password(row['password'])

            db.session.add(user)
            added.append((row['username'], row['email']))
            imported += 1

        ok, _err = safe_commit(logger, "Failed to import users",
                               on_conflict=lambda: _import_conflict(added))
        if not ok:
            return _err

        AuditService.log_action(
            action='user_import',
            resource_type='user',
            resource_name='CSV Import',
            details=f'Imported {imported} users, skipped {skipped}',
            success=True
        )

        return success_response(
            data={
                'imported': imported,
                'skipped': skipped,
                'errors': errors
            },
            message=f'Imported {imported} users, skipped {skipped}'
        )

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to import users: {e}", exc_info=True)
        return error_response('Failed to import users', 500)


# ============================================================================
# Security keys of another user (lost-key recovery)
# ============================================================================

_CONFIRM_LAST_FACTOR = 'last_factor'


def _users_key(user_id, credential_id):
    """(user, credential, None), or an error response in third place."""
    user = db.session.get(User, user_id)
    if not user:
        return None, None, error_response('User not found', 404)
    from models.webauthn import WebAuthnCredential
    credential = db.session.get(WebAuthnCredential, credential_id) if credential_id else None
    if credential_id and (not credential or credential.user_id != user.id):
        return None, None, error_response('Security key not found', 404)
    return user, credential, None


def _refuse_last_factor(user, credential):
    """409 unless confirmed: the account's last factor of required 2FA is going.

    Confirmed, the account is left as after a 2FA reset: under enforcement it
    enrols a factor again at its next login.
    """
    from auth.twofa_enforcement import LAST_FACTOR_REASON, lock_for_factor_change
    _user, refused = lock_for_factor_change(user.id, dropping_key=credential.id)
    if not refused or not credential.enabled or request.args.get('confirm') == _CONFIRM_LAST_FACTOR:
        return None
    db.session.rollback()
    return error_response(
        'This is the last second factor of an account that requires one; confirm with '
        f'?confirm={_CONFIRM_LAST_FACTOR} and the user enrols again at next login',
        409, {'reason': LAST_FACTOR_REASON})


def _audit_key(action, user, credential, verb, closed):
    AuditService.log_action(
        action=action,
        resource_type='user',
        resource_id=str(user.id),
        resource_name=user.username,
        details=(f'Security key "{credential.name}" (id {credential.id}) of {user.username} '
                 f'{verb} by {g.current_user.username} ({closed_sessions_note(closed)})'),
        success=True,
    )


@bp.route('/api/v2/users/<int:user_id>/webauthn', methods=['GET'])
@require_auth(['write:users'])
def list_user_security_keys(user_id):
    """
    List another user's security keys (WebAuthn).

    GET /api/v2/users/{user_id}/webauthn
    """
    user, _none, err = _users_key(user_id, None)
    if err:
        return err
    from services.webauthn_service import WebAuthnService
    return success_response(data=[c.to_dict() for c in WebAuthnService.get_user_credentials(user.id)])


@bp.route('/api/v2/users/<int:user_id>/webauthn/<int:credential_id>', methods=['DELETE'])
@require_auth(['write:users'])
def delete_user_security_key(user_id, credential_id):
    """
    Remove another user's security key, e.g. a lost one.

    DELETE /api/v2/users/{user_id}/webauthn/{credential_id}[?confirm=last_factor]
    """
    refused = refuse_api_key_on_own_account(user_id)
    if refused:
        return refused
    user, credential, err = _users_key(user_id, credential_id)
    if err:
        return err
    refusal = _refuse_last_factor(user, credential)
    if refusal:
        return refusal
    from services.webauthn_service import WebAuthnService
    # The holder's factor changed: their sessions close, as after a password reset
    owner = end_sessions_on_commit(user.id)
    if owner is None:
        db.session.rollback()
        return error_response('User not found', 404)
    ok, message = WebAuthnService.remove_credential(credential)
    if not ok:
        return error_response(message, 500)
    closed = sessions_closed_by(owner)
    _audit_key('webauthn_admin_delete', user, credential, 'removed', closed)
    return success_response(message=f'Security key removed from {user.username}',
                            meta={'other_sessions_closed': closed})


@bp.route('/api/v2/users/<int:user_id>/webauthn/<int:credential_id>', methods=['PATCH'])
@require_auth(['write:users'])
def toggle_user_security_key(user_id, credential_id):
    """
    Enable or disable another user's security key.

    PATCH /api/v2/users/{user_id}/webauthn/{credential_id}[?confirm=last_factor]
    Body: {"enabled": false}
    """
    refused = refuse_api_key_on_own_account(user_id)
    if refused:
        return refused
    data = request.get_json(silent=True)
    enabled = data.get('enabled') if isinstance(data, dict) else None
    if not isinstance(enabled, bool):
        return error_response('enabled must be true or false', 400)
    user, credential, err = _users_key(user_id, credential_id)
    if err:
        return err
    if not enabled:
        refusal = _refuse_last_factor(user, credential)
        if refusal:
            return refusal
    # A key left as it was changes no factor: no session closes, nothing is audited
    if credential.enabled == enabled:
        db.session.rollback()
        return success_response(data=credential.to_dict(), meta={'other_sessions_closed': 0})
    from services.webauthn_service import WebAuthnService
    owner = end_sessions_on_commit(user.id)
    if owner is None:
        db.session.rollback()
        return error_response('User not found', 404)
    ok, message = WebAuthnService.set_credential_enabled(credential, enabled)
    if not ok:
        return error_response(message, 500)
    closed = sessions_closed_by(owner)
    _audit_key('webauthn_admin_enable' if enabled else 'webauthn_admin_disable', user, credential,
               'enabled' if enabled else 'disabled', closed)
    return success_response(data=credential.to_dict(), meta={'other_sessions_closed': closed})
