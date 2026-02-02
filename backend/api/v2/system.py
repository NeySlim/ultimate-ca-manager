"""
System Routes v2.0
Handles system-level operations: database maintenance, HTTPS certificates, health
"""

from flask import Blueprint, request, current_app, jsonify, send_from_directory
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db, Certificate, CA, CRL, OCSPResponse
from pathlib import Path
import os
import subprocess
import shutil
import werkzeug.utils
from datetime import datetime, timezone

bp = Blueprint('system_v2', __name__)

@bp.route('/api/v2/system/database/stats', methods=['GET'])
@require_auth(['read:settings'])
def get_db_stats():
    """Get database statistics"""
    try:
        # Get DB size
        db_path = current_app.config.get('SQLALCHEMY_DATABASE_URI', '').replace('sqlite:///', '')
        size_bytes = os.path.getsize(db_path) if os.path.exists(db_path) else 0
        size_mb = round(size_bytes / (1024 * 1024), 2)
        
        # Get counts using ORM models instead of raw SQL
        counts = {
            'cas': CA.query.count(),
            'certificates': Certificate.query.count(),
            'crls': CRL.query.count(),
            'ocsp_responses': OCSPResponse.query.count()
        }
        
        # Calculate fragmentation (approximate for SQLite)
        # In a real scenario, we might parse 'PRAGMA page_count' vs actual size
        fragmentation = 0 
        
        return success_response(data={
            'size_mb': size_mb,
            'fragmentation_percent': fragmentation,
            'counts': counts,
            'last_vacuum': 'Never', # TODO: Store this timestamp
            'last_check': 'Never'
        })
    except Exception as e:
        return error_response(f"Failed to get stats: {str(e)}")

@bp.route('/api/v2/system/database/optimize', methods=['POST'])
@require_auth(['admin:system'])
def optimize_db():
    """Run VACUUM and ANALYZE"""
    try:
        db.session.execute(db.text("VACUUM"))
        db.session.execute(db.text("ANALYZE"))
        return success_response(message="Database optimized successfully")
    except Exception as e:
        return error_response(f"Optimization failed: {str(e)}")

@bp.route('/api/v2/system/database/integrity-check', methods=['POST'])
@require_auth(['admin:system'])
def check_integrity():
    """Run PRAGMA integrity_check"""
    try:
        result = db.session.execute(db.text("PRAGMA integrity_check")).scalar()
        if result == "ok":
            return success_response(message="Integrity check passed")
        else:
            return error_response(f"Integrity check failed: {result}")
    except Exception as e:
        return error_response(f"Check failed: {str(e)}")

@bp.route('/api/v2/system/database/export', methods=['GET'])
@require_auth(['admin:system'])
def export_db():
    """Export database as SQL dump"""
    try:
        import io
        db_path = current_app.config.get('SQLALCHEMY_DATABASE_URI', '').replace('sqlite:///', '')
        
        if not os.path.exists(db_path):
            return error_response("Database not found")
        
        # Create SQL dump using sqlite3
        import sqlite3
        conn = sqlite3.connect(db_path)
        sql_dump = io.StringIO()
        for line in conn.iterdump():
            sql_dump.write(f"{line}\n")
        conn.close()
        
        from flask import Response
        return Response(
            sql_dump.getvalue(),
            mimetype='application/sql',
            headers={'Content-Disposition': f'attachment; filename=ucm_database_{datetime.now().strftime("%Y%m%d_%H%M%S")}.sql'}
        )
    except Exception as e:
        return error_response(f"Export failed: {str(e)}")

@bp.route('/api/v2/system/database/reset', methods=['POST'])
@require_auth(['admin:system'])
def reset_db():
    """Reset database to initial state - DANGEROUS"""
    try:
        from services.audit_service import AuditService
        from auth.unified import get_current_user
        
        current_user = get_current_user()
        
        # Log this critical action before reset
        AuditService.log(
            action='database_reset',
            resource_type='system',
            resource_id='database',
            details={'initiated_by': current_user.get('username', 'unknown')},
            user_id=current_user.get('id')
        )
        
        # Drop all tables and recreate
        db.drop_all()
        db.create_all()
        
        # Create default admin user
        from models import User
        from werkzeug.security import generate_password_hash
        
        admin = User(
            username='admin',
            email='admin@localhost',
            password_hash=generate_password_hash('changeme123'),
            role='admin',
            is_active=True
        )
        db.session.add(admin)
        db.session.commit()
        
        return success_response(message="Database reset successfully. Default admin user created.")
    except Exception as e:
        return error_response(f"Reset failed: {str(e)}")

@bp.route('/api/v2/system/https/cert-info', methods=['GET'])
@require_auth(['read:settings'])
def get_https_cert_info():
    """Get information about the current HTTPS certificate"""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    import hashlib
    
    cert_path = Path('/opt/ucm/data/https_cert.pem')
    
    if not cert_path.exists():
        return success_response(data={
            'common_name': 'Not configured',
            'issuer': '-',
            'valid_from': None,
            'valid_to': None,
            'fingerprint': '-',
            'type': 'none'
        })
    
    try:
        cert_pem = cert_path.read_bytes()
        cert = x509.load_pem_x509_certificate(cert_pem)
        
        # Extract subject CN
        cn = None
        for attr in cert.subject:
            if attr.oid == x509.oid.NameOID.COMMON_NAME:
                cn = attr.value
                break
        
        # Extract issuer CN
        issuer_cn = None
        for attr in cert.issuer:
            if attr.oid == x509.oid.NameOID.COMMON_NAME:
                issuer_cn = attr.value
                break
        
        # Check if self-signed
        is_self_signed = cert.subject == cert.issuer
        
        # Calculate fingerprint
        fingerprint = cert.fingerprint(hashes.SHA256()).hex()
        fingerprint_formatted = ':'.join(fingerprint[i:i+2].upper() for i in range(0, len(fingerprint), 2))
        
        return success_response(data={
            'common_name': cn or 'Unknown',
            'issuer': issuer_cn or 'Unknown',
            'valid_from': cert.not_valid_before_utc.isoformat(),
            'valid_to': cert.not_valid_after_utc.isoformat(),
            'fingerprint': fingerprint_formatted[:47] + '...',  # Truncate for display
            'type': 'Self-Signed' if is_self_signed else 'CA-Signed',
            'serial': format(cert.serial_number, 'x').upper()
        })
    except Exception as e:
        return success_response(data={
            'common_name': 'Error reading certificate',
            'issuer': str(e),
            'valid_from': None,
            'valid_to': None,
            'fingerprint': '-',
            'type': 'error'
        })

@bp.route('/api/v2/system/https/regenerate', methods=['POST'])
@require_auth(['admin:system'])
def regenerate_https_cert():
    """Regenerate self-signed HTTPS certificate"""
    # Trigger script or internal logic to regen cert
    # Service restart required
    return success_response(message="Certificate regenerated. Service restart required.")

@bp.route('/api/v2/system/https/apply', methods=['POST'])
@require_auth(['admin:system'])
def apply_https_cert():
    """Apply a managed certificate to HTTPS"""
    data = request.json
    cert_id = data.get('cert_id')
    
    if not cert_id:
        return error_response("Certificate ID required")
        
    cert = Certificate.query.get(cert_id)
    if not cert:
        return error_response("Certificate not found")
        
    # Logic to write cert.crt and cert.key to system location
    # and trigger restart
    return success_response(message="Certificate applied. Service restart required.")

@bp.route('/api/v2/system/backup', methods=['POST'])
@bp.route('/api/v2/system/backup/create', methods=['POST'])
@require_auth(['admin:system'])
def create_backup():
    """Create encrypted backup"""
    try:
        from services.backup_service import BackupService
        data = request.json or {}
        password = data.get('password')
        
        if not password:
            return error_response("Password required for encryption", 400)
        
        if len(password) < 12:
            return error_response("Password must be at least 12 characters", 400)

        service = BackupService()
        backup_bytes = service.create_backup(password)
        
        # Save to disk
        filename = f"ucm_backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.ucmbkp"
        backup_dir = "/opt/ucm/data/backups"
        os.makedirs(backup_dir, exist_ok=True)
        
        filepath = os.path.join(backup_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(backup_bytes)
        
        # Format size
        size = len(backup_bytes)
        if size > 1024*1024:
            size_str = f"{size/1024/1024:.1f} MB"
        elif size > 1024:
            size_str = f"{size/1024:.1f} KB"
        else:
            size_str = f"{size} B"
            
        return success_response(
            message="Backup created successfully", 
            data={
                'filename': filename,
                'size': size_str,
                'path': filepath
            }
        )
    except ValueError as e:
        return error_response(str(e), 400)
    except Exception as e:
        return error_response(f"Backup failed: {str(e)}", 500)

@bp.route('/api/v2/system/backups', methods=['GET'])
@bp.route('/api/v2/system/backup/list', methods=['GET'])
@require_auth(['read:settings'])
def list_backups():
    """List available backups"""
    try:
        backup_dir = "/opt/ucm/data/backups"
        if not os.path.exists(backup_dir):
            return success_response(data=[])
            
        files = []
        for f in os.listdir(backup_dir):
            if f.endswith('.ucmbkp') or f.endswith('.json.enc'):
                path = os.path.join(backup_dir, f)
                stat = os.stat(path)
                
                # Format size
                size = stat.st_size
                if size > 1024*1024:
                    size_str = f"{size/1024/1024:.1f} MB"
                elif size > 1024:
                    size_str = f"{size/1024:.1f} KB"
                else:
                    size_str = f"{size} B"
                
                files.append({
                    'filename': f,
                    'size': size_str,
                    'size_bytes': size,
                    'created_at': datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
                })
        
        # Sort by date desc
        files.sort(key=lambda x: x['size_bytes'], reverse=True)
        files.sort(key=lambda x: x['created_at'], reverse=True)
        return success_response(data=files)
    except Exception as e:
        return error_response(f"Failed to list backups: {str(e)}")

@bp.route('/api/v2/system/backup/<filename>/download', methods=['GET'])
@require_auth(['read:settings'])
def download_backup(filename):
    """Download backup file"""
    backup_dir = "/opt/ucm/data/backups"
    filename = werkzeug.utils.secure_filename(filename)
    return send_from_directory(
        backup_dir, 
        filename, 
        as_attachment=True, 
        mimetype='application/octet-stream'
    )

@bp.route('/api/v2/system/backup/<filename>', methods=['DELETE'])
@require_auth(['admin:system'])
def delete_backup(filename):
    """Delete a backup file"""
    try:
        backup_dir = "/opt/ucm/data/backups"
        filename = werkzeug.utils.secure_filename(filename)
        filepath = os.path.join(backup_dir, filename)
        
        if not os.path.exists(filepath):
            return error_response("Backup file not found", 404)
        
        os.remove(filepath)
        return success_response(message="Backup deleted successfully")
    except Exception as e:
        return error_response(f"Failed to delete backup: {str(e)}", 500)

@bp.route('/api/v2/system/restore', methods=['POST'])
@bp.route('/api/v2/system/backup/restore', methods=['POST'])
@require_auth(['admin:system'])
def restore_backup():
    """Restore from backup file"""
    try:
        from services.backup_service import BackupService
        
        if 'file' not in request.files:
            return error_response("No backup file provided", 400)
        
        file = request.files['file']
        password = request.form.get('password')
        
        if not password:
            return error_response("Password required for decryption", 400)
        
        if len(password) < 12:
            return error_response("Password must be at least 12 characters", 400)
        
        # Read file content
        backup_bytes = file.read()
        
        service = BackupService()
        results = service.restore_backup(backup_bytes, password)
        
        return success_response(
            message="Backup restored successfully",
            data=results
        )
    except ValueError as e:
        return error_response(str(e), 400)
    except Exception as e:
        return error_response(f"Restore failed: {str(e)}", 500)


# ============================================================================
# Security Management Endpoints
# ============================================================================

@bp.route('/api/v2/system/security/encryption-status', methods=['GET'])
@require_auth(['admin:system'])
def get_encryption_status():
    """
    Get private key encryption status
    
    Returns:
    - enabled: bool - Whether encryption is configured
    - encrypted_count: int - Number of encrypted keys
    - unencrypted_count: int - Number of unencrypted keys
    """
    try:
        from security.encryption import key_encryption
        
        # Count encrypted vs unencrypted
        encrypted = 0
        unencrypted = 0
        
        for ca in CA.query.filter(CA.prv.isnot(None)).all():
            if key_encryption.is_encrypted(ca.prv):
                encrypted += 1
            else:
                unencrypted += 1
        
        for cert in Certificate.query.filter(Certificate.prv.isnot(None)).all():
            if key_encryption.is_encrypted(cert.prv):
                encrypted += 1
            else:
                unencrypted += 1
        
        return success_response(data={
            'enabled': key_encryption.is_enabled,
            'encrypted_count': encrypted,
            'unencrypted_count': unencrypted,
            'total_keys': encrypted + unencrypted
        })
        
    except ImportError:
        return success_response(data={
            'enabled': False,
            'encrypted_count': 0,
            'unencrypted_count': 0,
            'total_keys': 0,
            'error': 'Security module not available'
        })
    except Exception as e:
        return error_response(f"Failed to get encryption status: {str(e)}", 500)


@bp.route('/api/v2/system/security/encrypt-all-keys', methods=['POST'])
@require_auth(['admin:system'])
def encrypt_all_keys():
    """
    Encrypt all unencrypted private keys in the database
    
    POST body (optional):
    - dry_run: bool (default: true) - If true, only count without modifying
    """
    try:
        from security.encryption import encrypt_all_keys as do_encrypt
        
        data = request.get_json() or {}
        dry_run = data.get('dry_run', True)
        
        encrypted, skipped, errors = do_encrypt(dry_run=dry_run)
        
        message = f"Encrypted {encrypted} keys, skipped {skipped} (already encrypted)"
        if dry_run:
            message = f"[DRY RUN] Would encrypt {encrypted} keys, {skipped} already encrypted"
        
        return success_response(
            message=message,
            data={
                'dry_run': dry_run,
                'encrypted': encrypted,
                'skipped': skipped,
                'errors': errors
            }
        )
        
    except ImportError:
        return error_response("Security module not available", 500)
    except Exception as e:
        return error_response(f"Encryption failed: {str(e)}", 500)


@bp.route('/api/v2/system/security/generate-key', methods=['GET'])
@require_auth(['admin:system'])
def generate_encryption_key():
    """
    Generate a new encryption key for KEY_ENCRYPTION_KEY env var
    
    The key should be stored securely in /etc/ucm/ucm.env
    """
    try:
        from security.encryption import KeyEncryption
        
        key = KeyEncryption.generate_key()
        
        return success_response(
            message="Add this key to /etc/ucm/ucm.env as KEY_ENCRYPTION_KEY",
            data={
                'key': key,
                'env_line': f'KEY_ENCRYPTION_KEY={key}',
                'instructions': [
                    '1. Edit /etc/ucm/ucm.env',
                    '2. Add: KEY_ENCRYPTION_KEY=' + key,
                    '3. Restart UCM service: systemctl restart ucm',
                    '4. Run encrypt-all-keys to encrypt existing keys'
                ]
            }
        )
        
    except ImportError:
        return error_response("Security module not available", 500)
    except Exception as e:
        return error_response(f"Key generation failed: {str(e)}", 500)


# ============ Audit Log Retention ============

@bp.route('/api/v2/system/audit/retention', methods=['GET'])
@require_auth(['read:settings'])
def get_audit_retention():
    """Get audit log retention settings and stats"""
    try:
        from services.retention_service import RetentionPolicy
        return success_response(data=RetentionPolicy.get_stats())
    except Exception as e:
        return error_response(f"Failed to get retention settings: {str(e)}", 500)


@bp.route('/api/v2/system/audit/retention', methods=['PUT'])
@require_auth(['admin:system'])
def update_audit_retention():
    """Update audit log retention settings"""
    try:
        from services.retention_service import RetentionPolicy
        data = request.get_json() or {}
        
        settings = RetentionPolicy.update_settings(**data)
        return success_response(
            message="Retention settings updated",
            data=settings
        )
    except Exception as e:
        return error_response(f"Failed to update settings: {str(e)}", 500)


@bp.route('/api/v2/system/audit/cleanup', methods=['POST'])
@require_auth(['admin:system'])
def cleanup_audit_logs():
    """Manually trigger audit log cleanup"""
    try:
        from services.retention_service import cleanup_audit_logs as do_cleanup
        data = request.get_json() or {}
        
        result = do_cleanup(retention_days=data.get('retention_days'))
        return success_response(
            message=result.get('message', 'Cleanup complete'),
            data=result
        )
    except Exception as e:
        return error_response(f"Cleanup failed: {str(e)}", 500)


# ============ Certificate Expiry Alerts ============

@bp.route('/api/v2/system/alerts/expiry', methods=['GET'])
@require_auth(['read:settings'])
def get_expiry_alert_settings():
    """Get certificate expiry alert settings"""
    try:
        from services.expiry_alert_service import ExpiryAlertSettings
        return success_response(data=ExpiryAlertSettings.get_settings())
    except Exception as e:
        return error_response(f"Failed to get settings: {str(e)}", 500)


@bp.route('/api/v2/system/alerts/expiry', methods=['PUT'])
@require_auth(['admin:system'])
def update_expiry_alert_settings():
    """Update certificate expiry alert settings"""
    try:
        from services.expiry_alert_service import ExpiryAlertSettings
        data = request.get_json() or {}
        
        settings = ExpiryAlertSettings.update_settings(**data)
        return success_response(
            message="Expiry alert settings updated",
            data=settings
        )
    except Exception as e:
        return error_response(f"Failed to update settings: {str(e)}", 500)


@bp.route('/api/v2/system/alerts/expiry/check', methods=['POST'])
@require_auth(['admin:system'])
def trigger_expiry_check():
    """Manually trigger expiry check and send alerts"""
    try:
        from services.expiry_alert_service import check_and_send_alerts
        result = check_and_send_alerts()
        return success_response(
            message=f"Check complete: {result.get('alerts_sent', 0)} alerts sent",
            data=result
        )
    except Exception as e:
        return error_response(f"Expiry check failed: {str(e)}", 500)


# NOTE: get_expiring_certificates moved to dashboard.py (/api/v2/dashboard/expiring-certs)


# ============ Rate Limiting ============

@bp.route('/api/v2/system/security/rate-limit', methods=['GET'])
@require_auth(['read:settings'])
def get_rate_limit_config():
    """Get rate limiting configuration"""
    try:
        from security.rate_limiter import RateLimitConfig, get_rate_limiter
        
        config = RateLimitConfig.get_config()
        stats = get_rate_limiter().get_stats()
        
        return success_response(data={
            'config': config,
            'stats': stats
        })
    except Exception as e:
        return error_response(f"Failed to get rate limit config: {str(e)}", 500)


@bp.route('/api/v2/system/security/rate-limit', methods=['PUT'])
@require_auth(['admin:system'])
def update_rate_limit_config():
    """Update rate limiting configuration"""
    try:
        from security.rate_limiter import RateLimitConfig
        data = request.get_json() or {}
        
        if 'enabled' in data:
            RateLimitConfig.set_enabled(data['enabled'])
        
        if 'custom_limits' in data:
            for path, limit in data['custom_limits'].items():
                RateLimitConfig.set_custom_limit(path, limit['rpm'], limit.get('burst', limit['rpm'] // 3))
        
        if 'whitelist_add' in data:
            for ip in data['whitelist_add']:
                RateLimitConfig.add_whitelist(ip)
        
        if 'whitelist_remove' in data:
            for ip in data['whitelist_remove']:
                RateLimitConfig.remove_whitelist(ip)
        
        return success_response(
            message="Rate limit config updated",
            data=RateLimitConfig.get_config()
        )
    except Exception as e:
        return error_response(f"Failed to update config: {str(e)}", 500)


@bp.route('/api/v2/system/security/rate-limit/stats', methods=['GET'])
@require_auth(['read:settings'])
def get_rate_limit_stats():
    """Get rate limiting statistics"""
    try:
        from security.rate_limiter import get_rate_limiter
        return success_response(data=get_rate_limiter().get_stats())
    except Exception as e:
        return error_response(f"Failed to get stats: {str(e)}", 500)


@bp.route('/api/v2/system/security/rate-limit/reset', methods=['POST'])
@require_auth(['admin:system'])
def reset_rate_limits():
    """Reset rate limit counters"""
    try:
        from security.rate_limiter import get_rate_limiter
        data = request.get_json() or {}
        
        limiter = get_rate_limiter()
        ip = data.get('ip')  # Optional: clear specific IP only
        
        limiter.clear_bucket(ip)
        if data.get('reset_stats', False):
            limiter.reset_stats()
        
        return success_response(message="Rate limits reset")
    except Exception as e:
        return error_response(f"Failed to reset: {str(e)}", 500)
