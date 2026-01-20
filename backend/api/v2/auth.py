"""
Authentication Routes v2.0
/api/auth/* - Login, Logout, Verify

Supports:
- Session cookies (web UI)
- JWT tokens (external APIs)
"""

from flask import Blueprint, request, jsonify, session, current_app
from auth.unified import AuthManager, require_auth
from utils.response import success_response, error_response
from models import User, db
import hashlib

bp = Blueprint('auth_v2', __name__)


@bp.route('/api/auth/login', methods=['POST'])
def login():
    """
    Login endpoint
    Supports 2 modes based on Accept header:
    - Default: Returns session cookie
    - Accept: application/jwt → Returns JWT token
    
    POST /api/auth/login
    Body: {"username": "admin", "password": "xxx"}
    """
    data = request.json
    
    if not data or not data.get('username') or not data.get('password'):
        return error_response('Username and password required', 400)
    
    username = data['username']
    password = data['password']
    
    # Find user
    user = User.query.filter_by(username=username).first()
    
    if not user or not user.active:
        return error_response('Invalid credentials', 401)
    
    # Verify password (assumes User has check_password method)
    if not user.check_password(password):
        return error_response('Invalid credentials', 401)
    
    # Check if JWT requested
    accept_header = request.headers.get('Accept', '')
    wants_jwt = 'application/jwt' in accept_header
    
    if wants_jwt:
        # Return JWT token
        auth_manager = AuthManager()
        token_info = auth_manager.create_jwt(user.id)
        
        return success_response(
            data={
                'token': token_info['token'],
                'expires_in': token_info['expires_in'],
                'expires_at': token_info['expires_at'],
                'user': {
                    'id': user.id,
                    'username': user.username
                }
            },
            message='Login successful'
        )
    
    else:
        # Create session cookie
        session.clear()
        session['user_id'] = user.id
        session['username'] = user.username
        session.permanent = True
        
        # DEBUG: Log session info
        current_app.logger.info(f"🔍 Session created for user {user.username}")
        current_app.logger.info(f"🔍 Session ID: {session.get('_id', 'NO ID')}")
        current_app.logger.info(f"🔍 Session user_id: {session.get('user_id')}")
        current_app.logger.info(f"🔍 Session file dir: {current_app.config.get('SESSION_FILE_DIR')}")
        
        return success_response(
            data={
                'user': {
                    'id': user.id,
                    'username': user.username
                }
            },
            message='Login successful'
        )


@bp.route('/api/auth/logout', methods=['POST'])
@require_auth()
def logout():
    """
    Logout endpoint
    Clears session (for session-based auth)
    """
    session.clear()
    
    return success_response(message='Logout successful')


@bp.route('/api/auth/verify', methods=['GET'])
def verify():
    """
    Verify current authentication
    Returns user info and auth method
    
    Useful for:
    - Checking if token is still valid
    - Getting current user info
    - Determining auth method used
    """
    from flask import g
    from auth.unified import verify_request_auth
    
    # Manually verify auth to handle unauthenticated state gracefully
    auth_result = verify_request_auth()
    
    if not auth_result:
        # Check for mTLS certificate error in request context (set by middleware)
        cert_error = getattr(g, 'cert_error', None)
        
        return jsonify({
            'status': 'success',
            'data': {
                'authenticated': False,
                'cert_error': cert_error
            }
        }), 200
    
    # If authenticated
    return success_response(
        data={
            'authenticated': True,
            'user_id': g.user_id,
            'auth_method': g.auth_method,
            'permissions': g.permissions,
            'user': {
                'id': g.current_user.id,
                'username': g.current_user.username
            }
        }
    )


@bp.route('/api/auth/refresh', methods=['POST'])
@require_auth()
def refresh_token():
    """
    Refresh JWT token
    Only works with JWT auth (not session or API key)
    """
    from flask import g
    
    if g.auth_method != 'jwt':
        return error_response(
            'Refresh only available for JWT tokens',
            400,
            {'current_method': g.auth_method}
        )
    
    # Create new token
    auth_manager = AuthManager()
    token_info = auth_manager.create_jwt(g.user_id)
    
    return success_response(
        data={
            'token': token_info['token'],
            'expires_in': token_info['expires_in'],
            'expires_at': token_info['expires_at']
        },
        message='Token refreshed'
    )
