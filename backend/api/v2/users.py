"""
Users Management Routes v2.0
/api/v2/users/* - User CRUD operations
"""

from flask import Blueprint, request, jsonify, g
from auth.unified import require_auth
from utils.response import success_response, error_response, created_response, no_content_response
from models import db, User
from datetime import datetime
import csv
import io

bp = Blueprint('users_v2', __name__)


@bp.route('/api/v2/roles', methods=['GET'])
@require_auth()
def list_roles():
    """List available roles"""
    roles = [
        {'id': 'admin', 'name': 'Administrator', 'description': 'Full system access'},
        {'id': 'operator', 'name': 'Operator', 'description': 'Can manage certificates and CAs'},
        {'id': 'viewer', 'name': 'Viewer', 'description': 'Read-only access'}
    ]
    return success_response(data=roles)


@bp.route('/api/v2/users', methods=['GET'])
@require_auth()
def list_users():
    """
    List all users
    
    Query params:
    - role: Filter by role (admin/operator/viewer)
    - active: Filter by active status (true/false)
    - search: Search username, email, full_name
    """
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
@require_auth()
def create_user():
    """
    Create new user
    
    POST /api/v2/users
    {
        "username": "john.doe",
        "email": "john@example.com",
        "password": "securepass123",
        "full_name": "John Doe",
        "role": "operator",
        "permissions": {...}
    }
    """
    data = request.get_json()
    
    # Required fields
    if not data.get('username'):
        return error_response('Username is required', 400)
    if not data.get('email'):
        return error_response('Email is required', 400)
    if not data.get('password'):
        return error_response('Password is required', 400)
    
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
        
        return created_response(
            data=user.to_dict(),
            message=f'User {user.username} created successfully'
        )
    except Exception as e:
        db.session.rollback()
        return error_response(f'Failed to create user: {str(e)}', 500)


@bp.route('/api/v2/users/<int:user_id>', methods=['GET'])
@require_auth()
def get_user(user_id):
    """Get user by ID"""
    user = User.query.get(user_id)
    if not user:
        return error_response('User not found', 404)
    return success_response(data=user.to_dict())


@bp.route('/api/v2/users/<int:user_id>', methods=['PUT'])
@require_auth()
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
    
    if 'role' in data:
        valid_roles = ['admin', 'operator', 'viewer']
        if data['role'] not in valid_roles:
            return error_response(f'Invalid role. Must be one of: {", ".join(valid_roles)}', 400)
        user.role = data['role']
    
    if 'active' in data:
        user.active = bool(data['active'])
    
    # Update password if provided
    if 'password' in data and data['password']:
        user.set_password(data['password'])
    
    try:
        db.session.commit()
        return success_response(
            data=user.to_dict(),
            message=f'User {user.username} updated successfully'
        )
    except Exception as e:
        db.session.rollback()
        return error_response(f'Failed to update user: {str(e)}', 500)


@bp.route('/api/v2/users/<int:user_id>', methods=['DELETE'])
@require_auth()
def delete_user(user_id):
    """
    Delete user (soft delete - set active=False)
    
    DELETE /api/v2/users/{user_id}
    """
    # Prevent deleting yourself
    if g.current_user.id == user_id:
        return error_response('Cannot delete your own account', 403)
    
    user = User.query.get(user_id)
    if not user:
        return error_response('User not found', 404)
    
    # Soft delete
    user.active = False
    
    try:
        db.session.commit()
        return no_content_response(
            message=f'User {user.username} deactivated successfully'
        )
    except Exception as e:
        db.session.rollback()
        return error_response(f'Failed to delete user: {str(e)}', 500)


@bp.route('/api/v2/users/<int:user_id>/reset-password', methods=['POST'])
@require_auth()
def reset_user_password(user_id):
    """
    Reset user password (admin action)
    
    POST /api/v2/users/{user_id}/reset-password
    {
        "new_password": "newsecurepass123"
    }
    """
    user = User.query.get(user_id)
    if not user:
        return error_response('User not found', 404)
    
    data = request.get_json()
    
    if not data.get('new_password'):
        return error_response('New password is required', 400)
    
    # Update password
    user.set_password(data['new_password'])
    
    try:
        db.session.commit()
        return success_response(
            message=f'Password reset successfully for user {user.username}'
        )
    except Exception as e:
        db.session.rollback()
        return error_response(f'Failed to reset password: {str(e)}', 500)


@bp.route('/api/v2/users/<int:user_id>/toggle', methods=['PATCH'])
@require_auth()
def toggle_user_status(user_id):
    """
    Toggle user active/inactive status
    
    PATCH /api/v2/users/{user_id}/toggle
    """
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
        return success_response(
            data=user.to_dict(),
            message=f'User {user.username} {status} successfully'
        )
    except Exception as e:
        db.session.rollback()
        return error_response(f'Failed to toggle user status: {str(e)}', 500)


@bp.route('/api/v2/users/import', methods=['POST'])
@require_auth()
def import_users():
    """
    Import users from CSV file
    
    POST /api/v2/users/import
    Content-Type: multipart/form-data
    
    CSV format:
    username,email,full_name,role,password
    john.doe,john@example.com,John Doe,operator,pass123
    """
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
            # Required fields
            if not row.get('username') or not row.get('email') or not row.get('password'):
                skipped += 1
                errors.append(f"Row {imported + skipped + 1}: Missing required fields")
                continue
            
            # Check if user exists
            if User.query.filter_by(username=row['username']).first():
                skipped += 1
                errors.append(f"Row {imported + skipped + 1}: Username '{row['username']}' already exists")
                continue
            
            if User.query.filter_by(email=row['email']).first():
                skipped += 1
                errors.append(f"Row {imported + skipped + 1}: Email '{row['email']}' already exists")
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
        return error_response(f'Failed to import users: {str(e)}', 500)
