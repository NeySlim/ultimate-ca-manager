"""
Users CRUD Operations
"""

from . import bp, validate_password_strength
from flask import request, g
import logging

from auth.unified import require_auth
from utils.response import success_response, error_response, created_response
from models import db, User
from services.audit_service import AuditService

logger = logging.getLogger(__name__)


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

    try:
        db.session.add(user)
        db.session.commit()

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
    except Exception as e:
        db.session.rollback()
        return error_response('Failed to create user', 500)


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
        user.active = bool(data['active'])

    # Update password if provided
    if 'password' in data and data['password']:
        # SECURITY: Validate password strength
        is_valid, error_msg = validate_password_strength(data['password'])
        if not is_valid:
            return error_response(error_msg, 400)
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
        return error_response('Failed to update user', 500)


@bp.route('/api/v2/users/<int:user_id>', methods=['DELETE'])
@require_auth(['delete:users'])
def delete_user(user_id):
    """
    Delete user (soft delete - set active=False)
    Admin only.

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

    # Soft delete
    username = user.username
    user.active = False

    try:
        db.session.commit()
        AuditService.log_action(
            action='user_deactivate',
            resource_type='user',
            resource_id=str(user_id),
            resource_name=username,
            details=f'Deactivated user: {username}',
            success=True
        )

        try:
            from websocket.emitters import on_user_deleted
            on_user_deleted(user_id, username, g.current_user.username)
        except Exception:
            pass

        return success_response(
            message=f'User {username} deactivated successfully'
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to delete user: {e}", exc_info=True)
        return error_response('Failed to delete user', 500)


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

    for user_id in ids:
        try:
            if g.current_user.id == user_id:
                results['failed'].append({'id': user_id, 'error': 'Cannot delete your own account'})
                continue
            user = db.session.get(User, user_id)
            if not user:
                results['failed'].append({'id': user_id, 'error': 'Not found'})
                continue
            user.active = False
            db.session.commit()
            results['success'].append(user_id)
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to delete user {user_id}: {e}")
            results['failed'].append({'id': user_id, 'error': 'Deletion failed'})

    AuditService.log_action(
        action='users_bulk_deactivated',
        resource_type='user',
        resource_id=','.join(str(i) for i in results['success']),
        resource_name=f'{len(results["success"])} users',
        details=f'Bulk deactivated {len(results["success"])} users',
        success=True
    )

    return success_response(data=results, message=f'{len(results["success"])} users deactivated')
