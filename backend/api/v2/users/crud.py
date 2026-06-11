"""
Users CRUD Operations
"""

from . import bp, validate_password_strength
from flask import request, g
import logging

from auth.unified import require_auth
from utils.response import success_response, error_response, created_response
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


def _pending_approvals_count(user_id):
    """Number of pending approval requests owned by this user (blocks hard delete)."""
    try:
        from models import ApprovalRequest
        return ApprovalRequest.query.filter_by(
            requester_id=user_id, status='pending'
        ).count()
    except Exception:
        return 0


def _purge_user_dependencies(user_id):
    """Clean up all FK dependencies before hard-deleting a user.

    Critical pending approvals must be checked by the caller first
    (see _pending_approvals_count). Closed approvals are removed here.
    Returns the number of invalidated sessions for audit detail.
    """
    from models.user import UserSession
    sessions_deleted = UserSession.query.filter_by(user_id=user_id).delete()

    # WebAuthn credentials + challenges
    try:
        from models import WebAuthnCredential, WebAuthnChallenge
        WebAuthnCredential.query.filter_by(user_id=user_id).delete()
        WebAuthnChallenge.query.filter_by(user_id=user_id).delete()
    except Exception as e:
        logger.debug(f"WebAuthn cleanup skipped for user {user_id}: {e}")

    # mTLS auth certificates
    try:
        from models import AuthCertificate
        AuthCertificate.query.filter_by(user_id=user_id).delete()
    except Exception as e:
        logger.debug(f"AuthCertificate cleanup skipped for user {user_id}: {e}")

    # SSO sessions
    try:
        from models import SSOSession
        SSOSession.query.filter_by(user_id=user_id).delete()
    except Exception as e:
        logger.debug(f"SSOSession cleanup skipped for user {user_id}: {e}")

    # API keys
    try:
        from models import APIKey
        APIKey.query.filter_by(user_id=user_id).delete()
    except Exception as e:
        logger.debug(f"APIKey cleanup skipped for user {user_id}: {e}")

    # Group memberships
    try:
        from models import GroupMember
        GroupMember.query.filter_by(user_id=user_id).delete()
    except Exception as e:
        logger.debug(f"GroupMember cleanup skipped for user {user_id}: {e}")

    # Closed approval requests (pending ones block deletion upstream)
    try:
        from models import ApprovalRequest
        ApprovalRequest.query.filter(
            ApprovalRequest.requester_id == user_id,
            ApprovalRequest.status != 'pending',
        ).delete(synchronize_session=False)
    except Exception as e:
        logger.debug(f"ApprovalRequest cleanup skipped for user {user_id}: {e}")

    # HSM providers created_by → NULL (nullable FK, preserve the provider)
    try:
        from models import HsmProvider
        HsmProvider.query.filter_by(created_by=user_id).update(
            {'created_by': None}, synchronize_session=False
        )
    except Exception as e:
        logger.debug(f"HsmProvider cleanup skipped for user {user_id}: {e}")

    return sessions_deleted


@bp.route('/api/v2/users', methods=['GET'])
@require_auth(['read:users'])
def list_users():
    """
    List all users (admin only)

    Query params:
    - role: Filter by role (admin/operator/viewer)
    - active: Filter by active status (true/false)
    - search: Search username, email, full_name
    """
    # SECURITY: Only admins can list all users
    if g.current_user.role != 'admin':
        # Non-admins can only see themselves
        return success_response(data=[g.current_user.to_dict()])

    # Filters (support multi-select: ?role=admin&role=operator)
    role_list = request.args.getlist('role')
    active_str = request.args.get('active')
    search = request.args.get('search', '').strip()

    query = User.query

    if role_list:
        query = query.filter(User.role.in_(role_list))

    if active_str:
        active = active_str.lower() == 'true'
        query = query.filter_by(active=active)

    if search:
        safe_search = search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        search_pattern = f'%{safe_search}%'
        query = query.filter(
            db.or_(
                User.username.ilike(search_pattern),
                User.email.ilike(search_pattern),
                User.full_name.ilike(search_pattern)
            )
        )

    users = query.order_by(User.created_at.desc()).all()

    return success_response(
        data=[user.to_dict() for user in users]
    )


@bp.route('/api/v2/users', methods=['POST'])
@require_auth(['write:users'])
def create_user():
    """
    Create new user (admin only)

    POST /api/v2/users
    {
        "username": "john.doe",
        "email": "john@example.com",
        "password": "SecurePass123!",
        "full_name": "John Doe",
        "role": "operator",
        "permissions": {...}
    }
    """
    # SECURITY: Only admins can create users
    if g.current_user.role != 'admin':
        return error_response('Insufficient permissions', 403)

    data = request.get_json()

    # Required fields
    if not data.get('username'):
        return error_response('Username is required', 400)
    if not data.get('email'):
        return error_response('Email is required', 400)
    if not data.get('password'):
        return error_response('Password is required', 400)

    # SECURITY: Validate password strength with username check
    is_valid, error_msg = validate_password_strength(data['password'], username=data['username'])
    if not is_valid:
        return error_response(error_msg, 400)

    # Check if user exists
    if User.query.filter_by(username=data['username']).first():
        return error_response('Username already exists', 409)

    if User.query.filter_by(email=data['email']).first():
        return error_response('Email already exists', 409)

    # Validate role — only admins can assign non-viewer roles
    valid_roles = ['admin', 'operator', 'auditor', 'viewer']
    role = data.get('role', 'viewer')
    if role not in valid_roles:
        return error_response(f'Invalid role. Must be one of: {", ".join(valid_roles)}', 400)
    if role != 'viewer' and g.current_user.role != 'admin':
        return error_response('Only admins can assign elevated roles', 403)

    # Validate custom_role_id if provided — admin only
    custom_role_id = data.get('custom_role_id')
    if custom_role_id:
        if g.current_user.role != 'admin':
            return error_response('Only admins can assign custom roles', 403)
        try:
            from models.rbac import CustomRole
            if not CustomRole.query.get(int(custom_role_id)):
                return error_response('Custom role not found', 404)
            custom_role_id = int(custom_role_id)
        except (ValueError, ImportError):
            custom_role_id = None

    # Create user
    user = User(
        username=data['username'],
        email=data['email'],
        full_name=data.get('full_name', ''),
        role=role,
        custom_role_id=custom_role_id,
        active=data.get('active', True)
    )
    user.set_password(data['password'])

    db.session.add(user)
    if not safe_commit(logger, "Failed to create user"):
        return error_response('Failed to create user', 500)

    AuditService.log_action(
        action='user_create',
        resource_type='user',
        resource_id=str(user.id),
        resource_name=user.username,
        details=f'Created user: {user.username} (role: {role})',
        success=True
    )

    try:
        from websocket.emitters import on_user_created
        on_user_created(user.id, user.username, g.current_user.username)
    except Exception:
        pass

    return created_response(
        data=user.to_dict(),
        message=f'User {user.username} created successfully'
    )


@bp.route('/api/v2/users/<int:user_id>', methods=['GET'])
@require_auth(['read:users'])
def get_user(user_id):
    """Get user by ID"""
    # SECURITY: Non-admins can only view themselves
    if g.current_user.role != 'admin' and g.current_user.id != user_id:
        return error_response('Access denied', 403)

    user = User.query.get(user_id)
    if not user:
        return error_response('User not found', 404)
    return success_response(data=user.to_dict())


@bp.route('/api/v2/users/<int:user_id>', methods=['PUT'])
@require_auth(['write:users'])
def update_user(user_id):
    """
    Update existing user

    PUT /api/v2/users/{user_id}
    {
        "email": "newemail@example.com",
        "full_name": "John Doe Updated",
        "role": "admin",
        "active": true
    }
    """
    # SECURITY: Non-admins can only update themselves (limited fields)
    if g.current_user.role != 'admin' and g.current_user.id != user_id:
        return error_response('Access denied', 403)

    user = User.query.get(user_id)
    if not user:
        return error_response('User not found', 404)

    data = request.get_json()

    # Update fields
    if 'email' in data:
        # Check if email already used by another user
        existing = User.query.filter(User.email == data['email'], User.id != user_id).first()
        if existing:
            return error_response('Email already in use', 409)
        user.email = data['email']

    if 'full_name' in data:
        user.full_name = data['full_name']

    # SECURITY: Only admins can change roles
    if 'role' in data:
        if g.current_user.role != 'admin':
            return error_response('Only admins can change roles', 403)
        valid_roles = ['admin', 'operator', 'auditor', 'viewer']
        if data['role'] not in valid_roles:
            return error_response(f'Invalid role. Must be one of: {", ".join(valid_roles)}', 400)
        # Block self-demotion away from admin (operator-level lockout risk)
        if g.current_user.id == user_id and user.role == 'admin' and data['role'] != 'admin':
            return error_response('Cannot demote your own admin account', 403)
        # Preserve at least one active admin
        if user.role == 'admin' and data['role'] != 'admin' and _is_last_active_admin(user):
            return error_response('Cannot demote the last active admin', 409)
        user.role = data['role']

    # SECURITY: Only admins can assign custom roles
    if 'custom_role_id' in data:
        if g.current_user.role != 'admin':
            return error_response('Only admins can assign custom roles', 403)
        if data['custom_role_id']:
            try:
                from models.rbac import CustomRole
                if not CustomRole.query.get(int(data['custom_role_id'])):
                    return error_response('Custom role not found', 404)
                user.custom_role_id = int(data['custom_role_id'])
            except (ValueError, ImportError):
                return error_response('Invalid custom role ID', 400)
        else:
            user.custom_role_id = None

    # SECURITY: Only admins can change active status
    if 'active' in data:
        if g.current_user.role != 'admin':
            return error_response('Only admins can change active status', 403)
        new_active = bool(data['active'])
        # Block self-disable (lockout risk)
        if g.current_user.id == user_id and not new_active:
            return error_response('Cannot disable your own account', 403)
        # Preserve at least one active admin
        if not new_active and _is_last_active_admin(user):
            return error_response('Cannot disable the last active admin', 409)
        user.active = new_active

    # Update password if provided
    if 'password' in data and data['password']:
        # SECURITY: Validate password strength
        is_valid, error_msg = validate_password_strength(data['password'])
        if not is_valid:
            return error_response(error_msg, 400)
        # SECURITY: Self-password change requires current-password proof
        # (defends against stolen-cookie / XSS account takeover)
        if g.current_user.id == user_id:
            current = data.get('current_password') or data.get('old_password')
            if not current or not user.check_password(current):
                return error_response('Current password is required', 400)
        user.set_password(data['password'])

    try:
        db.session.commit()
        AuditService.log_action(
            action='user_update',
            resource_type='user',
            resource_id=str(user_id),
            resource_name=user.username,
            details=f'Updated user: {user.username}',
            success=True
        )
        return success_response(
            data=user.to_dict(),
            message=f'User {user.username} updated successfully'
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to update user: {e}", exc_info=True)
        return error_response('Failed to update user', 500)


@bp.route('/api/v2/users/<int:user_id>', methods=['DELETE'])
@require_auth(['delete:users'])
def delete_user(user_id):
    """
    Permanently delete a user and clean up FK dependencies.
    Admin only. Use the activate/deactivate toggle for soft state.

    DELETE /api/v2/users/{user_id}
    """
    # SECURITY: Only admins can delete users
    if g.current_user.role != 'admin':
        return error_response('Insufficient permissions', 403)

    # Prevent deleting yourself
    if g.current_user.id == user_id:
        return error_response('Cannot delete your own account', 403)

    user = db.session.get(User, user_id)
    if not user:
        return error_response('User not found', 404)

    # Preserve at least one active admin (deleting last admin = lockout)
    if _is_last_active_admin(user):
        return error_response('Cannot delete the last active admin', 409)

    # Block if the user still owns pending approval requests
    pending = _pending_approvals_count(user_id)
    if pending > 0:
        return error_response(
            f'Cannot delete: user has {pending} pending approval request(s). '
            'Resolve them first.', 409
        )

    username = user.username
    try:
        sessions_deleted = _purge_user_dependencies(user_id)
        db.session.delete(user)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to delete user {user_id}: {e}", exc_info=True)
        return error_response('Failed to delete user', 500)

    if sessions_deleted > 0:
        logger.info(f"Invalidated {sessions_deleted} sessions for deleted user {username}")

    AuditService.log_action(
        action='user_delete',
        resource_type='user',
        resource_id=str(user_id),
        resource_name=username,
        details=f'Deleted user: {username} ({sessions_deleted} sessions invalidated)',
        success=True
    )

    try:
        from websocket.emitters import on_user_deleted
        on_user_deleted(user_id, username, g.current_user.username)
    except Exception:
        pass

    return success_response(
        message=f'User {username} deleted successfully'
    )


# ============================================================
# Bulk Operations
# ============================================================

@bp.route('/api/v2/users/bulk/delete', methods=['POST'])
@require_auth(['delete:users'])
def bulk_delete_users():
    """Bulk deactivate users (soft delete)"""
    if g.current_user.role != 'admin':
        return error_response('Insufficient permissions', 403)

    data = request.get_json()
    if not data or not data.get('ids'):
        return error_response('ids array required', 400)

    ids = data['ids']
    results = {'success': [], 'failed': []}
    total_sessions_invalidated = 0

    for user_id in ids:
        if g.current_user.id == user_id:
            results['failed'].append({'id': user_id, 'error': 'Cannot delete your own account'})
            continue
        user = db.session.get(User, user_id)
        if not user:
            results['failed'].append({'id': user_id, 'error': 'Not found'})
            continue
        if _is_last_active_admin(user):
            results['failed'].append({'id': user_id, 'error': 'Cannot delete the last active admin'})
            continue
        if _pending_approvals_count(user_id) > 0:
            results['failed'].append({'id': user_id, 'error': 'User has pending approval requests'})
            continue

        try:
            sessions_deleted = _purge_user_dependencies(user_id)
            db.session.delete(user)
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to delete user {user_id}: {e}", exc_info=True)
            results['failed'].append({'id': user_id, 'error': 'Deletion failed'})
            continue
        if not safe_commit(logger, f"Delete user {user_id}"):
            results['failed'].append({'id': user_id, 'error': 'Deletion failed'})
            continue
        total_sessions_invalidated += sessions_deleted
        results['success'].append(user_id)

    AuditService.log_action(
        action='users_bulk_deleted',
        resource_type='user',
        resource_id=','.join(str(i) for i in results['success']),
        resource_name=f'{len(results["success"])} users',
        details=f'Bulk deleted {len(results["success"])} users ({total_sessions_invalidated} sessions invalidated)',
        success=True
    )

    return success_response(data=results, message=f'{len(results["success"])} users deleted')
