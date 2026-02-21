"""
Users Management Routes v2.0
/api/v2/users/* - User CRUD operations
"""

from flask import Blueprint, request, jsonify, g
from cryptography import x509 as cx509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from auth.unified import require_auth
from utils.response import success_response, error_response, created_response, no_content_response
from models import db, User, Certificate, CA
from services.audit_service import AuditService
from datetime import datetime
import base64
import csv
import hashlib
import io
import re
import uuid

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
    valid_roles = ['admin', 'operator', 'auditor', 'viewer']
    role = data.get('role', 'viewer')
    if role not in valid_roles:
        return error_response(f'Invalid role. Must be one of: {", ".join(valid_roles)}', 400)
    
    # Validate custom_role_id if provided
    custom_role_id = data.get('custom_role_id')
    if custom_role_id:
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


# ============= User mTLS Certificate Management (Admin) =============

@bp.route('/api/v2/users/<int:user_id>/mtls/certificates', methods=['GET'])
@require_auth(['admin:users'])
def list_user_mtls_certificates(user_id):
    """List mTLS certificates for a specific user (admin only)."""
    from models.auth_certificate import AuthCertificate

    target_user = User.query.get(user_id)
    if not target_user:
        return error_response('User not found', 404)

    certs = AuthCertificate.query.filter_by(user_id=user_id).order_by(AuthCertificate.created_at.desc()).all()
    return success_response(data=[c.to_dict() for c in certs])


@bp.route('/api/v2/users/<int:user_id>/mtls/certificates', methods=['POST'])
@require_auth(['admin:users'])
def create_user_mtls_certificate(user_id):
    """Generate or import an mTLS certificate for a user (admin only)."""
    from models import Certificate, CA, SystemConfig
    from models.auth_certificate import AuthCertificate
    from services.cert_service import CertificateService

    target_user = User.query.get(user_id)
    if not target_user:
        return error_response('User not found', 404)

    data = request.get_json() or {}
    mode = data.get('mode', 'generate')  # 'generate' or 'import'

    if mode == 'import':
        pem_text = data.get('pem', '').strip()
        name = data.get('name', '').strip()
        if not pem_text:
            return error_response('PEM certificate data is required', 400)

        try:
            if not pem_text.startswith('-----BEGIN'):
                try:
                    pem_text = base64.b64decode(pem_text).decode('utf-8')
                except Exception:
                    return error_response('Invalid certificate format', 400)
            pem_bytes = pem_text.encode('utf-8')
            cert_obj = cx509.load_pem_x509_certificate(pem_bytes, default_backend())
        except Exception as e:
            return error_response('Invalid PEM certificate data', 400)

        serial = str(cert_obj.serial_number)
        subject_dn = cert_obj.subject.rfc4514_string()
        issuer_dn = cert_obj.issuer.rfc4514_string()
        fingerprint = hashlib.sha256(cert_obj.public_bytes(serialization.Encoding.DER)).hexdigest().upper()
        valid_from = cert_obj.not_valid_before_utc if hasattr(cert_obj, 'not_valid_before_utc') else cert_obj.not_valid_before
        valid_until = cert_obj.not_valid_after_utc if hasattr(cert_obj, 'not_valid_after_utc') else cert_obj.not_valid_after

        existing = AuthCertificate.query.filter_by(cert_serial=serial).first()
        if existing:
            return error_response('This certificate is already enrolled', 409)

        cn = ''
        for attr in cert_obj.subject:
            if attr.oid == cx509.oid.NameOID.COMMON_NAME:
                cn = attr.value
                break

        cert_name = name or cn or f"Imported {serial[:8]}"

        # Create Certificate record if not exists
        existing_cert = Certificate.query.filter_by(serial_number=serial).first()
        if not existing_cert:
            issuer_ca = CA.query.filter(CA.subject == issuer_dn).first()
            existing_cert = Certificate(
                refid=str(uuid.uuid4()),
                descr=cert_name,
                caref=issuer_ca.refid if issuer_ca else None,
                crt=base64.b64encode(pem_bytes).decode('utf-8'),
                cert_type='usr_cert',
                subject=subject_dn,
                subject_cn=cn,
                issuer=issuer_dn,
                serial_number=serial,
                valid_from=valid_from,
                valid_to=valid_until,
                created_by=target_user.username,
            )
            db.session.add(existing_cert)
            db.session.flush()

        auth_cert = AuthCertificate(
            user_id=user_id,
            cert_serial=serial,
            cert_subject=subject_dn,
            cert_issuer=issuer_dn,
            cert_fingerprint=fingerprint,
            cert_pem=pem_bytes,
            name=cert_name,
            valid_from=valid_from,
            valid_until=valid_until,
            enabled=True,
        )
        db.session.add(auth_cert)
        db.session.commit()

        AuditService.log_action(
            action='admin_mtls_import',
            resource_type='certificate',
            resource_name=auth_cert.name,
            details=f'Admin imported mTLS cert for user {target_user.username}',
            success=True,
        )
        return created_response(data=auth_cert.to_dict(), message='Certificate imported')

    else:
        # Generate mode
        name = data.get('name', '').strip() or f"{target_user.username}@mtls"
        ca_id = data.get('ca_id')
        validity_days = data.get('validity_days', 365)

        # Find CA
        ca = None
        if ca_id:
            ca = CA.query.filter((CA.refid == ca_id) | (CA.id == ca_id)).first()
        if not ca:
            config = SystemConfig.query.filter_by(key='mtls_trusted_ca').first()
            if config:
                ca = CA.query.filter_by(refid=config.value).first()
        if not ca:
            return error_response('No CA available for mTLS certificate generation', 400)

        try:
            result = CertificateService.create_user_certificate(
                ca_refid=ca.refid,
                common_name=name,
                validity_days=int(validity_days),
                key_type='RSA',
                key_size=2048,
                username=target_user.username,
            )

            cert_pem = base64.b64decode(result.crt) if result.crt else b''
            cert_obj = cx509.load_pem_x509_certificate(cert_pem, default_backend())
            serial = str(cert_obj.serial_number)
            subject_dn = cert_obj.subject.rfc4514_string()
            issuer_dn = cert_obj.issuer.rfc4514_string()
            fingerprint = hashlib.sha256(cert_obj.public_bytes(serialization.Encoding.DER)).hexdigest().upper()
            valid_from = cert_obj.not_valid_before_utc if hasattr(cert_obj, 'not_valid_before_utc') else cert_obj.not_valid_before
            valid_until = cert_obj.not_valid_after_utc if hasattr(cert_obj, 'not_valid_after_utc') else cert_obj.not_valid_after

            auth_cert = AuthCertificate(
                user_id=user_id,
                cert_serial=serial,
                cert_subject=subject_dn,
                cert_issuer=issuer_dn,
                cert_fingerprint=fingerprint,
                cert_pem=cert_pem,
                name=name,
                valid_from=valid_from,
                valid_until=valid_until,
                enabled=True,
            )
            db.session.add(auth_cert)
            db.session.commit()

            key_pem = base64.b64decode(result.prv).decode('utf-8') if result.prv else ''

            AuditService.log_action(
                action='admin_mtls_generate',
                resource_type='certificate',
                resource_name=name,
                details=f'Admin generated mTLS cert for user {target_user.username}',
                success=True,
            )

            resp = auth_cert.to_dict()
            resp['certificate'] = cert_pem.decode('utf-8')
            resp['private_key'] = key_pem
            resp['cert_id'] = result.id
            return created_response(data=resp, message='Certificate generated')

        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to generate mTLS cert for user {user_id}: {e}")
            return error_response('Failed to generate certificate', 500)


@bp.route('/api/v2/users/<int:user_id>/mtls/certificates/<int:cert_id>', methods=['DELETE'])
@require_auth(['admin:users'])
def delete_user_mtls_certificate(user_id, cert_id):
    """Delete an mTLS certificate for a user (admin only)."""
    from models.auth_certificate import AuthCertificate

    target_user = User.query.get(user_id)
    if not target_user:
        return error_response('User not found', 404)

    auth_cert = AuthCertificate.query.get(cert_id)
    if not auth_cert or auth_cert.user_id != user_id:
        return error_response('Certificate not found', 404)

    cert_name = auth_cert.name or f'Certificate #{cert_id}'
    db.session.delete(auth_cert)
    db.session.commit()

    AuditService.log_action(
        action='admin_mtls_delete',
        resource_type='certificate',
        resource_id=str(cert_id),
        resource_name=cert_name,
        details=f'Admin deleted mTLS cert {cert_name} for user {target_user.username}',
        success=True,
    )

    return no_content_response()
