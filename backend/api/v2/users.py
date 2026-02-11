"""
Users Management Routes v2.0
/api/v2/users/* - User CRUD operations
"""

from flask import Blueprint, request, jsonify, g
from auth.unified import require_auth
from utils.response import success_response, error_response, created_response, no_content_response
from models import db, User
from services.audit_service import AuditService
from datetime import datetime
import csv
import io
import re

# Import password policy
try:
    from security.password_policy import validate_password, get_password_strength, get_policy_requirements
    HAS_PASSWORD_POLICY = True
except ImportError:
    HAS_PASSWORD_POLICY = False

bp = Blueprint('users_v2', __name__)


# Legacy password validation (fallback if security module not available)
MIN_PASSWORD_LENGTH = 8
PASSWORD_REQUIREMENTS = """Password must:
- Be at least 8 characters long
- Contain at least one uppercase letter
- Contain at least one lowercase letter
- Contain at least one number
- Contain at least one special character (!@#$%^&*(),.?":{}|<>)"""


def validate_password_strength(password, username=None):
    """
    SECURITY: Validate password meets security requirements
    Returns (is_valid, error_message)
    """
    # Use new security module if available
    if HAS_PASSWORD_POLICY:
        is_valid, errors = validate_password(password, username=username)
        if not is_valid:
            return False, errors[0] if errors else "Invalid password"
        return True, None
    
    # Legacy validation
    if len(password) < MIN_PASSWORD_LENGTH:
        return False, f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r'\d', password):
        return False, "Password must contain at least one number"
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "Password must contain at least one special character"
    return True, None


# Roles endpoint moved to api/v2/roles.py


@bp.route('/api/v2/users/password-policy', methods=['GET'])
def get_password_policy():
    """
    Get password policy requirements
    
    GET /api/v2/users/password-policy
    
    Returns password requirements for UI display
    """
    if HAS_PASSWORD_POLICY:
        requirements = get_policy_requirements()
    else:
        requirements = {
            'min_length': MIN_PASSWORD_LENGTH,
            'max_length': 128,
            'rules': PASSWORD_REQUIREMENTS.split('\n')[1:]  # Skip header
        }
    
    return success_response(data=requirements)


@bp.route('/api/v2/users/password-strength', methods=['POST'])
def check_password_strength():
    """
    Check password strength (no auth required - used during registration/password change)
    
    POST /api/v2/users/password-strength
    {"password": "test123"}
    
    Returns strength score and feedback
    """
    data = request.get_json() or {}
    password = data.get('password', '')
    
    if HAS_PASSWORD_POLICY:
        result = get_password_strength(password)
    else:
        # Basic fallback
        length = len(password)
        score = min(100, length * 10)
        level = 'weak' if score < 40 else 'fair' if score < 60 else 'good' if score < 80 else 'strong'
        result = {'score': score, 'level': level, 'feedback': []}
    
    return success_response(data=result)


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
    
    # Filters
    role = request.args.get('role')
    active_str = request.args.get('active')
    search = request.args.get('search', '').strip()
    
    query = User.query
    
    if role:
        query = query.filter_by(role=role)
    
    if active_str:
        active = active_str.lower() == 'true'
        query = query.filter_by(active=active)
    
    if search:
        search_pattern = f'%{search}%'
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
    
    # Validate role
    valid_roles = ['admin', 'operator', 'viewer']
    role = data.get('role', 'viewer')
    if role not in valid_roles:
        return error_response(f'Invalid role. Must be one of: {", ".join(valid_roles)}', 400)
    
    # Create user
    user = User(
        username=data['username'],
        email=data['email'],
        full_name=data.get('full_name', ''),
        role=role,
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
        valid_roles = ['admin', 'operator', 'viewer']
        if data['role'] not in valid_roles:
            return error_response(f'Invalid role. Must be one of: {", ".join(valid_roles)}', 400)
        user.role = data['role']
    
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
        return success_response(
            message=f'User {username} deactivated successfully'
        )
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
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
            results['failed'].append({'id': user_id, 'error': str(e)})

    AuditService.log_action(
        action='users_bulk_deactivated',
        resource_type='user',
        resource_id=','.join(str(i) for i in results['success']),
        resource_name=f'{len(results["success"])} users',
        details=f'Bulk deactivated {len(results["success"])} users',
        success=True
    )

    return success_response(data=results, message=f'{len(results["success"])} users deactivated')


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
        return error_response('Failed to toggle user status', 500)


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
        # Read CSV
        stream = io.StringIO(file.stream.read().decode('utf-8'))
        csv_reader = csv.DictReader(stream)
        
        imported = 0
        skipped = 0
        errors = []
        
        for row in csv_reader:
            row_num = imported + skipped + 1
            
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
        
        db.session.commit()
        
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
        return error_response('Failed to import users', 500)
