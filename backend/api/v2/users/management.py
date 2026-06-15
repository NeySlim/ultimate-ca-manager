"""
Users Management Routes (password reset, toggle, unlock, import)
"""

from . import bp, validate_password_strength
from flask import request, g
import csv
import io
import logging

from auth.unified import require_auth
from utils.response import success_response, error_response
from utils.db_transaction import safe_commit
from models import db, User
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
    # SECURITY: Only admins can reset other users' passwords
    if g.current_user.role != 'admin' and g.current_user.id != user_id:
        return error_response('Access denied', 403)

    user = User.query.get(user_id)
    if not user:
        return error_response('User not found', 404)

    data = request.get_json()

    if not data.get('new_password'):
        return error_response('New password is required', 400)

    # SECURITY: Self-reset must prove knowledge of the current password
    # (otherwise a stolen session = silent password rotation = full takeover)
    if g.current_user.id == user_id:
        current = data.get('current_password') or data.get('old_password')
        if not current or not user.check_password(current):
            return error_response('Current password is required', 400)

    # SECURITY: Validate password strength
    is_valid, error_msg = validate_password_strength(data['new_password'])
    if not is_valid:
        return error_response(error_msg, 400)

    # Update password
    user.set_password(data['new_password'])

    try:
        db.session.commit()

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

    user = User.query.get(user_id)
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


SSO_NO_PASSWORD = '!SSO_NO_PASSWORD!'


@bp.route('/api/v2/users/<int:user_id>/link-sso', methods=['POST'])
@require_auth(['write:users'])
def link_user_sso(user_id):
    """Link an existing local account to an SSO provider (admin only).

    The recommended way to resolve an email collision between a local user and
    an SSO identity (#136): instead of creating a duplicate or silently merging
    on email, an admin deliberately links the two. After linking, an SSO login
    matching the (optionally updated) username adopts this account.

    POST /api/v2/users/{user_id}/link-sso
    Body: {"provider_id": int, "sso_username": str?}
    """
    if g.current_user.role != 'admin':
        return error_response('Insufficient permissions', 403)

    from models.sso import SSOProvider

    user = User.query.get(user_id)
    if not user:
        return error_response('User not found', 404)
    if (user.auth_source or 'local') != 'local' or user.sso_provider_id:
        return error_response('User is already linked to single sign-on', 400)

    data = request.get_json(silent=True) or {}
    provider_id = data.get('provider_id')
    if not provider_id:
        return error_response('provider_id is required', 400)
    provider = SSOProvider.query.get(provider_id)
    if not provider:
        return error_response('SSO provider not found', 404)

    # The username the IdP will send; defaults to the current one.
    new_username = (data.get('sso_username') or user.username).strip()
    if not new_username:
        return error_response('sso_username cannot be empty', 400)
    if new_username != user.username:
        clash = User.query.filter(
            User.username == new_username, User.id != user.id
        ).first()
        if clash:
            return error_response('That username is already taken', 409)

    old_username = user.username
    user.username = new_username
    user.auth_source = provider.provider_type
    user.sso_provider_id = provider.id

    ok, err = safe_commit(logger, f"Failed to link user {user_id} to SSO")
    if not ok:
        return err
    AuditService.log_action(
        action='user_link_sso',
        resource_type='user',
        resource_id=str(user.id),
        resource_name=user.username,
        details=(f'Linked account {old_username!r} to SSO provider '
                 f'{provider.name!r} (username now {new_username!r})'),
        success=True,
    )
    return success_response(
        data=user.to_dict(),
        message=f'Account linked to {provider.name}')


@bp.route('/api/v2/users/<int:user_id>/unlink-sso', methods=['POST'])
@require_auth(['write:users'])
def unlink_user_sso(user_id):
    """Convert an SSO-linked account back to a local account (admin only).

    POST /api/v2/users/{user_id}/unlink-sso
    """
    if g.current_user.role != 'admin':
        return error_response('Insufficient permissions', 403)

    user = User.query.get(user_id)
    if not user:
        return error_response('User not found', 404)
    if (user.auth_source or 'local') == 'local' and not user.sso_provider_id:
        return error_response('User is not linked to single sign-on', 400)

    user.auth_source = 'local'
    user.sso_provider_id = None
    # An account that never had a local password must set one before it can log in.
    needs_password = user.password_hash == SSO_NO_PASSWORD
    if needs_password:
        user.force_password_change = True

    ok, err = safe_commit(logger, f"Failed to unlink user {user_id} from SSO")
    if not ok:
        return err
    AuditService.log_action(
        action='user_unlink_sso',
        resource_type='user',
        resource_id=str(user.id),
        resource_name=user.username,
        details=f'Unlinked account {user.username!r} from single sign-on',
        success=True,
    )
    msg = f'Account {user.username} converted to local'
    if needs_password:
        msg += ' — set a password for this account'
    return success_response(data=user.to_dict(), message=msg)


@bp.route('/api/v2/users/<int:user_id>/unlock', methods=['POST'])
@require_auth(['write:users'])
def unlock_user(user_id):
    """
    Unlock a locked user account (admin only)

    POST /api/v2/users/{user_id}/unlock
    """
    if g.current_user.role != 'admin':
        return error_response('Insufficient permissions', 403)

    user = User.query.get(user_id)
    if not user:
        return error_response('User not found', 404)

    if not user.locked_until and not user.failed_logins:
        return success_response(data=user.to_dict(), message='Account is not locked')

    try:
        user.failed_logins = 0
        user.locked_until = None
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

            if User.query.filter_by(email=row['email']).first():
                skipped += 1
                errors.append(f"Row {row_num}: Email '{row['email']}' already exists")
                continue

            # Create user
            role = row.get('role', 'viewer')
            if role not in ['admin', 'operator', 'viewer']:
                role = 'viewer'

            user = User(
                username=row['username'],
                email=row['email'],
                full_name=row.get('full_name', ''),
                role=role,
                active=True
            )
            user.set_password(row['password'])

            db.session.add(user)
            imported += 1

        ok, _err = safe_commit(logger, "Failed to import users")
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
