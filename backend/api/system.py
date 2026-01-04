"""
System Configuration API
Web-based configuration for HTTPS, SCEP, and all system settings
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import db, User, SystemConfig, AuditLog
from middleware.auth_middleware import admin_required
from config.https_manager import HTTPSManager
from pathlib import Path
import json

system_bp = Blueprint('system', __name__)


def log_audit(action, username, details=None):
    """Helper to log system config changes"""
    log = AuditLog(
        username=username,
        action=action,
        resource_type='system',
        details=details,
        ip_address=request.remote_addr
    )
    db.session.add(log)
    db.session.commit()


@system_bp.route('/config', methods=['GET'])
@jwt_required()
def get_config():
    """
    Get all system configuration
    ---
    GET /api/v1/system/config
    """
    configs = SystemConfig.query.all()
    return jsonify([c.to_dict() for c in configs]), 200


@system_bp.route('/config/<key>', methods=['GET'])
@jwt_required()
def get_config_key(key):
    """
    Get specific configuration value
    ---
    GET /api/v1/system/config/<key>
    """
    config = SystemConfig.query.filter_by(key=key).first_or_404()
    return jsonify(config.to_dict()), 200


@system_bp.route('/config', methods=['POST'])
@jwt_required()
@admin_required
def set_config():
    """
    Set system configuration (admin only)
    ---
    POST /api/v1/system/config
    {
        "key": "scep.enabled",
        "value": "true",
        "encrypted": false,
        "description": "Enable SCEP server"
    }
    """
    data = request.get_json()
    identity = get_jwt_identity()
    admin = User.query.get(identity)
    
    if not data.get('key'):
        return jsonify({"error": "Key is required"}), 400
    
    config = SystemConfig.query.filter_by(key=data['key']).first()
    
    if config:
        # Update existing
        config.value = data.get('value')
        if 'encrypted' in data:
            config.encrypted = data['encrypted']
        if 'description' in data:
            config.description = data['description']
        config.updated_by = admin.username
    else:
        # Create new
        config = SystemConfig(
            key=data['key'],
            value=data.get('value'),
            encrypted=data.get('encrypted', False),
            description=data.get('description'),
            updated_by=admin.username
        )
        db.session.add(config)
    
    db.session.commit()
    
    log_audit('config_updated', admin.username, 
             details=f'Updated config: {data["key"]}')
    
    return jsonify(config.to_dict()), 200


@system_bp.route('/https/certificate', methods=['GET'])
@jwt_required()
def get_https_cert_info():
    """
    Get HTTPS certificate information
    ---
    GET /api/v1/system/https/certificate
    """
    from flask import current_app
    cert_path = Path(current_app.config['HTTPS_CERT_PATH'])
    
    if not cert_path.exists():
        return jsonify({"error": "Certificate not found"}), 404
    
    info = HTTPSManager.get_cert_info(cert_path)
    if not info:
        return jsonify({"error": "Failed to read certificate"}), 500
    
    return jsonify(info), 200


@system_bp.route('/https/certificate', methods=['POST'])
@jwt_required()
@admin_required
def regenerate_https_cert():
    """
    Regenerate HTTPS certificate (admin only)
    ---
    POST /api/v1/system/https/certificate
    {
        "common_name": "ucm.example.com",
        "organization": "My Company",
        "validity_days": 825
    }
    """
    from flask import current_app
    data = request.get_json() or {}
    identity = get_jwt_identity()
    admin = User.query.get(identity)
    
    cert_path = Path(current_app.config['HTTPS_CERT_PATH'])
    key_path = Path(current_app.config['HTTPS_KEY_PATH'])
    
    try:
        HTTPSManager.generate_self_signed_cert(
            cert_path,
            key_path,
            common_name=data.get('common_name'),
            organization=data.get('organization', 'Ultimate CA Manager'),
            validity_days=int(data.get('validity_days', 825))
        )
        
        log_audit('https_cert_regenerated', admin.username,
                 details=f'CN: {data.get("common_name", "auto")}')
        
        info = HTTPSManager.get_cert_info(cert_path)
        
        return jsonify({
            "message": "HTTPS certificate regenerated. Server restart required.",
            "certificate": info
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@system_bp.route('/https/certificate', methods=['PUT'])
@jwt_required()
@admin_required
def upload_https_cert():
    """
    Upload custom HTTPS certificate (admin only)
    ---
    PUT /api/v1/system/https/certificate
    {
        "certificate": "-----BEGIN CERTIFICATE-----...",
        "private_key": "-----BEGIN PRIVATE KEY-----..."
    }
    """
    from flask import current_app
    data = request.get_json()
    identity = get_jwt_identity()
    admin = User.query.get(identity)
    
    if not data.get('certificate') or not data.get('private_key'):
        return jsonify({"error": "Certificate and private key required"}), 400
    
    cert_path = Path(current_app.config['HTTPS_CERT_PATH'])
    key_path = Path(current_app.config['HTTPS_KEY_PATH'])
    
    try:
        # Validate certificate before saving
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend
        
        cert_obj = x509.load_pem_x509_certificate(
            data['certificate'].encode(), default_backend()
        )
        
        key_obj = serialization.load_pem_private_key(
            data['private_key'].encode(), password=None, backend=default_backend()
        )
        
        # Save files
        with open(cert_path, 'w') as f:
            f.write(data['certificate'])
        
        with open(key_path, 'w') as f:
            f.write(data['private_key'])
        key_path.chmod(0o600)
        
        log_audit('https_cert_uploaded', admin.username,
                 details='Custom HTTPS certificate uploaded')
        
        info = HTTPSManager.get_cert_info(cert_path)
        
        return jsonify({
            "message": "HTTPS certificate uploaded. Server restart required.",
            "certificate": info
        }), 200
        
    except Exception as e:
        return jsonify({"error": f"Invalid certificate or key: {str(e)}"}), 400


@system_bp.route('/scep/config', methods=['GET'])
@jwt_required()
def get_scep_config():
    """
    Get SCEP configuration
    ---
    GET /api/v1/system/scep/config
    """
    from flask import current_app
    
    config = {
        "enabled": current_app.config.get('SCEP_ENABLED', False),
        "ca_id": current_app.config.get('SCEP_CA_ID'),
        "auto_approve": current_app.config.get('SCEP_AUTO_APPROVE', False),
        "cert_lifetime": current_app.config.get('SCEP_CERT_LIFETIME', 365),
        "key_size": current_app.config.get('SCEP_KEY_SIZE', 2048),
        "renewal_days": current_app.config.get('SCEP_RENEWAL_DAYS', 30),
        "endpoint_url": f"https://{request.host}/scep/pkiclient.exe"
    }
    
    return jsonify(config), 200


@system_bp.route('/scep/config', methods=['POST'])
@jwt_required()
@admin_required
def update_scep_config():
    """
    Update SCEP configuration (admin only)
    ---
    POST /api/v1/system/scep/config
    {
        "enabled": true,
        "ca_id": 1,
        "challenge_password": "secret",
        "auto_approve": false,
        "cert_lifetime": 365
    }
    """
    data = request.get_json()
    identity = get_jwt_identity()
    admin = User.query.get(identity)
    
    # Update config in database
    config_updates = {
        'scep.enabled': str(data.get('enabled', False)),
        'scep.ca_id': str(data.get('ca_id', '')),
        'scep.auto_approve': str(data.get('auto_approve', False)),
        'scep.cert_lifetime': str(data.get('cert_lifetime', 365)),
        'scep.key_size': str(data.get('key_size', 2048)),
        'scep.renewal_days': str(data.get('renewal_days', 30)),
    }
    
    if 'challenge_password' in data:
        config_updates['scep.challenge_password'] = data['challenge_password']
    
    for key, value in config_updates.items():
        config = SystemConfig.query.filter_by(key=key).first()
        if config:
            config.value = value
            config.updated_by = admin.username
        else:
            config = SystemConfig(
                key=key,
                value=value,
                encrypted=(key == 'scep.challenge_password'),
                updated_by=admin.username
            )
            db.session.add(config)
    
    db.session.commit()
    
    log_audit('scep_config_updated', admin.username,
             details='SCEP configuration updated')
    
    return jsonify({"message": "SCEP configuration updated"}), 200


@system_bp.route('/info', methods=['GET'])
def get_system_info():
    """
    Get system information (public)
    ---
    GET /api/v1/system/info
    """
    from flask import current_app
    
    info = {
        "app_name": current_app.config.get('APP_NAME'),
        "version": current_app.config.get('APP_VERSION'),
        "https_enabled": True,
        "scep_enabled": current_app.config.get('SCEP_ENABLED', False),
    }
    
    return jsonify(info), 200


@system_bp.route('/stats', methods=['GET'])
@jwt_required()
def get_stats():
    """
    Get database statistics
    ---
    GET /api/v1/system/stats
    """
    from models import CA, Certificate
    
    stats = {
        'cas': CA.query.count(),
        'certificates': Certificate.query.count(),
        'users': User.query.count()
    }
    
    return jsonify(stats), 200


@system_bp.route('/config', methods=['PUT'])
@jwt_required()
@admin_required
def update_config_bulk():
    """
    Bulk update system configuration
    ---
    PUT /api/v1/system/config
    {
        "default_cert_validity": 730,
        "session_timeout": 120,
        "enable_audit_log": true,
        "enable_rate_limit": true,
        "scep_auto_approve": false
    }
    """
    data = request.get_json()
    identity = get_jwt_identity()
    admin = User.query.get(identity)
    
    # Map frontend keys to backend config keys
    config_mapping = {
        'default_cert_validity': 'system.default_cert_validity',
        'session_timeout': 'system.session_timeout',
        'enable_audit_log': 'system.enable_audit_log',
        'enable_rate_limit': 'system.enable_rate_limit',
        'scep_auto_approve': 'scep.auto_approve'
    }
    
    for frontend_key, backend_key in config_mapping.items():
        if frontend_key in data:
            value = str(data[frontend_key])
            config = SystemConfig.query.filter_by(key=backend_key).first()
            
            if config:
                config.value = value
                config.updated_by = admin.username
            else:
                config = SystemConfig(
                    key=backend_key,
                    value=value,
                    encrypted=False,
                    updated_by=admin.username
                )
                db.session.add(config)
    
    db.session.commit()
    
    log_audit('config_bulk_updated', admin.username,
             details='Bulk system configuration update')
    
    return jsonify({"message": "Configuration updated successfully"}), 200
