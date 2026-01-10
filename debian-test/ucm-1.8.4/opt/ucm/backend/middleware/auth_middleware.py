"""
Authentication Middleware
JWT token validation and role-based access control
"""
from functools import wraps
from flask import jsonify
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity, get_jwt
from models import User, db


def init_auth_middleware(jwt):
    """Initialize JWT callbacks"""
    
    @jwt.user_identity_loader
    def user_identity_lookup(user):
        """Convert user object to identity (must be string)"""
        if isinstance(user, User):
            return str(user.id)
        return str(user)
    
    @jwt.user_lookup_loader
    def user_lookup_callback(_jwt_header, jwt_data):
        """Load user from JWT"""
        identity = jwt_data["sub"]
        return User.query.filter_by(id=int(identity)).first()
    
    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        """Handle expired token"""
        return jsonify({
            "error": "token_expired",
            "message": "The token has expired"
        }), 401
    
    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        """Handle invalid token"""
        return jsonify({
            "error": "invalid_token",
            "message": "Signature verification failed"
        }), 401
    
    @jwt.unauthorized_loader
    def missing_token_callback(error):
        """Handle missing token"""
        return jsonify({
            "error": "authorization_required",
            "message": "Request does not contain an access token"
        }), 401


def require_role(*roles):
    """
    Decorator to require specific role(s) for endpoint access
    
    Usage:
        @require_role('admin')
        @require_role('admin', 'operator')
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            claims = get_jwt()
            user_id = get_jwt_identity()
            
            user = User.query.get(int(user_id))
            if not user or not user.active:
                return jsonify({
                    "error": "forbidden",
                    "message": "User account is inactive"
                }), 403
            
            if user.role not in roles:
                return jsonify({
                    "error": "forbidden",
                    "message": f"Requires one of: {', '.join(roles)}"
                }), 403
            
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def admin_required(fn):
    """Shortcut decorator for admin-only endpoints"""
    return require_role('admin')(fn)


def operator_required(fn):
    """Shortcut decorator for operator+ endpoints"""
    return require_role('admin', 'operator')(fn)
