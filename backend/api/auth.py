"""
Authentication API
Login, logout, token refresh, user management
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity, get_jwt
)
from datetime import datetime
from models import db, User, AuditLog
from middleware.auth_middleware import admin_required

auth_bp = Blueprint('auth', __name__)


def log_audit(action, username, details=None, success=True):
    """Helper to log authentication events"""
    log = AuditLog(
        username=username,
        action=action,
        resource_type='auth',
        details=details,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        success=success
    )
    db.session.add(log)
    db.session.commit()


@auth_bp.route('/login', methods=['POST'])
def login():
    """
    User login
    ---
    POST /api/v1/auth/login
    {
        "username": "admin",
        "password": "password"
    }
    """
    data = request.get_json()
    
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({"error": "Username and password required"}), 400
    
    user = User.query.filter_by(username=data['username']).first()
    
    if not user or not user.check_password(data['password']):
        log_audit('login_failed', data['username'], 
                 details='Invalid credentials', success=False)
        return jsonify({"error": "Invalid username or password"}), 401
    
    if not user.active:
        log_audit('login_failed', data['username'], 
                 details='Account inactive', success=False)
        return jsonify({"error": "Account is inactive"}), 403
    
    # Update last login
    user.last_login = datetime.utcnow()
    db.session.commit()
    
    # Create tokens
    access_token = create_access_token(identity=user)
    refresh_token = create_refresh_token(identity=user)
    
    log_audit('login_success', user.username, details='User logged in')
    
    return jsonify({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": user.to_dict()
    }), 200


@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """
    Refresh access token
    ---
    POST /api/v1/auth/refresh
    Headers: Authorization: Bearer <refresh_token>
    """
    identity = get_jwt_identity()
    user = User.query.get(identity)
    
    if not user or not user.active:
        return jsonify({"error": "Invalid user"}), 401
    
    access_token = create_access_token(identity=user)
    
    return jsonify({
        "access_token": access_token
    }), 200


@auth_bp.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    """
    Logout (client-side token removal)
    ---
    POST /api/v1/auth/logout
    """
    identity = get_jwt_identity()
    user = User.query.get(identity)
    
    if user:
        log_audit('logout', user.username, details='User logged out')
    
    return jsonify({"message": "Logged out successfully"}), 200


@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def get_current_user():
    """
    Get current user info
    ---
    GET /api/v1/auth/me
    """
    identity = get_jwt_identity()
    user = User.query.get(identity)
    
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    return jsonify(user.to_dict()), 200


@auth_bp.route('/change-password', methods=['POST'])
@jwt_required()
def change_password():
    """
    Change current user's password
    ---
    POST /api/v1/auth/change-password
    {
        "current_password": "old",
        "new_password": "new"
    }
    """
    data = request.get_json()
    identity = get_jwt_identity()
    user = User.query.get(identity)
    
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    if not user.check_password(data.get('current_password', '')):
        log_audit('password_change_failed', user.username, 
                 details='Invalid current password', success=False)
        return jsonify({"error": "Current password is incorrect"}), 401
    
    if not data.get('new_password') or len(data['new_password']) < 8:
        return jsonify({"error": "New password must be at least 8 characters"}), 400
    
    user.set_password(data['new_password'])
    db.session.commit()
    
    log_audit('password_changed', user.username, details='Password changed successfully')
    
    return jsonify({"message": "Password changed successfully"}), 200


# Admin-only user management endpoints

@auth_bp.route('/users', methods=['GET'])
@jwt_required()
@admin_required
def list_users():
    """
    List all users (admin only)
    ---
    GET /api/v1/auth/users
    """
    users = User.query.all()
    return jsonify([user.to_dict() for user in users]), 200


@auth_bp.route('/users', methods=['POST'])
@jwt_required()
@admin_required
def create_user():
    """
    Create new user (admin only)
    ---
    POST /api/v1/auth/users
    {
        "username": "newuser",
        "email": "user@example.com",
        "password": "password",
        "role": "viewer"
    }
    """
    data = request.get_json()
    identity = get_jwt_identity()
    admin = User.query.get(identity)
    
    # Validation
    if not all(k in data for k in ['username', 'email', 'password', 'role']):
        return jsonify({"error": "Missing required fields"}), 400
    
    if data['role'] not in ['admin', 'operator', 'viewer']:
        return jsonify({"error": "Invalid role"}), 400
    
    if User.query.filter_by(username=data['username']).first():
        return jsonify({"error": "Username already exists"}), 409
    
    if User.query.filter_by(email=data['email']).first():
        return jsonify({"error": "Email already exists"}), 409
    
    # Create user
    user = User(
        username=data['username'],
        email=data['email'],
        role=data['role'],
        active=True
    )
    user.set_password(data['password'])
    
    db.session.add(user)
    db.session.commit()
    
    log_audit('user_created', admin.username, 
             details=f'Created user: {user.username}')
    
    return jsonify(user.to_dict()), 201


@auth_bp.route('/users/<int:user_id>', methods=['PUT'])
@jwt_required()
@admin_required
def update_user(user_id):
    """
    Update user (admin only)
    ---
    PUT /api/v1/auth/users/<id>
    """
    user = User.query.get_or_404(user_id)
    data = request.get_json()
    identity = get_jwt_identity()
    admin = User.query.get(identity)
    
    # Update fields
    if 'email' in data:
        user.email = data['email']
    if 'role' in data and data['role'] in ['admin', 'operator', 'viewer']:
        user.role = data['role']
    if 'active' in data:
        user.active = bool(data['active'])
    if 'password' in data:
        user.set_password(data['password'])
    
    db.session.commit()
    
    log_audit('user_updated', admin.username, 
             details=f'Updated user: {user.username}')
    
    return jsonify(user.to_dict()), 200


@auth_bp.route('/users/<int:user_id>', methods=['DELETE'])
@jwt_required()
@admin_required
def delete_user(user_id):
    """
    Delete user (admin only)
    ---
    DELETE /api/v1/auth/users/<id>
    """
    user = User.query.get_or_404(user_id)
    identity = get_jwt_identity()
    admin = User.query.get(identity)
    
    # Prevent self-deletion
    if user.id == admin.id:
        return jsonify({"error": "Cannot delete your own account"}), 400
    
    username = user.username
    db.session.delete(user)
    db.session.commit()
    
    log_audit('user_deleted', admin.username, 
             details=f'Deleted user: {username}')
    
    return jsonify({"message": "User deleted successfully"}), 200
