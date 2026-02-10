"""
System Routes v2.0
Handles system-level operations: database maintenance, HTTPS certificates, health
"""

from flask import Blueprint, request, current_app, jsonify, send_from_directory
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db, Certificate, CA, CRL, OCSPResponse
from services.audit_service import AuditService
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
        AuditService.log_action(
            action='system_optimize',
            resource_type='system',
            resource_name='Database',
            details='Database optimized (VACUUM + ANALYZE)',
            success=True
        )
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
        db.session.rollback()
        return error_response(f"Reset failed: {str(e)}")

@bp.route('/api/v2/system/https/cert-info', methods=['GET'])
@require_auth(['read:settings'])
def get_https_cert_info():
    """Get information about the current HTTPS certificate"""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    import hashlib
    
    data_dir = os.environ.get('DATA_DIR', '/opt/ucm/data')
    cert_path = Path(os.environ.get('HTTPS_CERT_PATH', f'{data_dir}/https_cert.pem'))
    
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
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from datetime import timedelta
    import signal
    
    data = request.json or {}
    common_name = data.get('common_name', 'localhost')
    validity_days = data.get('validity_days', 365)
    
    try:
        # Generate private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )
        
        # Build certificate
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "NL"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Ultimate CA Manager"),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ])
        
        now = datetime.now(timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + timedelta(days=validity_days))
            .add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName(common_name),
                    x509.DNSName("localhost"),
                ]),
                critical=False,
            )
            .sign(private_key, hashes.SHA256())
        )
        
        # Get cert paths dynamically - same logic as gunicorn.conf.py
        data_dir = os.environ.get('DATA_DIR', '/opt/ucm/data')
        cert_path = Path(os.environ.get('HTTPS_CERT_PATH', f'{data_dir}/https_cert.pem'))
        key_path = Path(os.environ.get('HTTPS_KEY_PATH', f'{data_dir}/https_key.pem'))
        
        # Backup existing
        if cert_path.exists():
            backup_suffix = datetime.now().strftime('%Y%m%d_%H%M%S')
            shutil.copy(cert_path, f"{cert_path}.backup-{backup_suffix}")
        if key_path.exists():
            shutil.copy(key_path, f"{key_path}.backup-{backup_suffix}")
        
        # Write new cert and key
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))
        os.chmod(key_path, 0o600)
        
        # Set ownership
        import pwd
        try:
            ucm_user = pwd.getpwnam('ucm')
            os.chown(cert_path, ucm_user.pw_uid, ucm_user.pw_gid)
            os.chown(key_path, ucm_user.pw_uid, ucm_user.pw_gid)
        except KeyError:
            pass
        
        current_app.logger.info(f"Regenerated HTTPS certificate for {common_name}")
        
        AuditService.log_action(
            action='https_regenerate',
            resource_type='system',
            resource_name='HTTPS Certificate',
            details=f'Regenerated self-signed HTTPS certificate for {common_name}',
            success=True
        )
        
        # Restart service - method depends on environment
        is_docker = os.environ.get('UCM_DOCKER', '').lower() in ('1', 'true')
        
        if is_docker:
            # In Docker, SIGTERM to gunicorn master - Docker will auto-restart
            try:
                os.kill(os.getppid(), signal.SIGTERM)
            except Exception as e:
                current_app.logger.warning(f"Failed to send restart signal: {e}")
            return success_response(message="Certificate regenerated. Container restarting...")
        else:
            subprocess.Popen(['sudo', '/usr/bin/systemctl', 'restart', 'ucm'],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
            return success_response(message="Certificate regenerated. Service restarting...")
        
    except Exception as e:
        current_app.logger.error(f"Failed to regenerate HTTPS cert: {e}")
        return error_response(f"Failed to regenerate certificate: {str(e)}", 500)

@bp.route('/api/v2/system/https/apply', methods=['POST'])
@require_auth(['admin:system'])
def apply_https_cert():
    """Apply a managed certificate to HTTPS"""
    import base64
    import signal
    
    data = request.json
    cert_id = data.get('cert_id')
    
    if not cert_id:
        return error_response("Certificate ID required", 400)
        
    cert = Certificate.query.get(cert_id)
    if not cert:
        return error_response("Certificate not found", 404)
    
    # Verify cert has private key
    if not cert.prv:
        return error_response("Certificate has no private key - cannot use for HTTPS", 400)
    
    try:
        # Get cert paths dynamically - same logic as gunicorn.conf.py
        data_dir = os.environ.get('DATA_DIR', '/opt/ucm/data')
        cert_path = Path(os.environ.get('HTTPS_CERT_PATH', f'{data_dir}/https_cert.pem'))
        key_path = Path(os.environ.get('HTTPS_KEY_PATH', f'{data_dir}/https_key.pem'))
        
        # Backup existing certs
        if cert_path.exists():
            backup_suffix = datetime.now().strftime('%Y%m%d_%H%M%S')
            shutil.copy(cert_path, f"{cert_path}.backup-{backup_suffix}")
        if key_path.exists():
            shutil.copy(key_path, f"{key_path}.backup-{backup_suffix}")
        
        # Decode cert/key - they may be base64 encoded or raw PEM
        cert_data = cert.crt
        key_data = cert.prv
        
        # Check if base64 encoded (doesn't start with -----BEGIN)
        if not cert_data.startswith('-----BEGIN'):
            try:
                cert_data = base64.b64decode(cert_data).decode('utf-8')
            except Exception:
                pass  # Already decoded or different format
        
        if not key_data.startswith('-----BEGIN'):
            try:
                key_data = base64.b64decode(key_data).decode('utf-8')
            except Exception:
                pass
        
        # Write new certificate
        cert_path.write_text(cert_data)
        
        # Write private key with restricted permissions
        key_path.write_text(key_data)
        os.chmod(key_path, 0o600)
        
        # Set ownership to ucm user (if exists)
        import pwd
        try:
            ucm_user = pwd.getpwnam('ucm')
            os.chown(cert_path, ucm_user.pw_uid, ucm_user.pw_gid)
            os.chown(key_path, ucm_user.pw_uid, ucm_user.pw_gid)
        except KeyError:
            pass  # ucm user doesn't exist, skip chown
        
        current_app.logger.info(f"Applied certificate {cert.refid} as HTTPS cert")
        
        AuditService.log_action(
            action='https_apply',
            resource_type='system',
            resource_id=str(cert_id),
            resource_name=cert.descr or cert.refid,
            details=f'Applied certificate {cert.refid} as HTTPS certificate',
            success=True
        )
        
        # Restart service - method depends on environment
        is_docker = os.environ.get('UCM_DOCKER', '').lower() in ('1', 'true')
        
        if is_docker:
            # In Docker, we need to restart the container for SSL cert changes
            # SIGHUP doesn't reload SSL certs in gunicorn
            # Send SIGTERM to master - Docker will auto-restart the container
            try:
                import sys
                # Kill gunicorn master (parent of worker) - Docker restart policy will restart
                os.kill(os.getppid(), signal.SIGTERM)
            except Exception as e:
                current_app.logger.warning(f"Failed to send restart signal: {e}")
            return success_response(message="Certificate applied. Container restarting...")
        else:
            # On systemd systems, restart the service
            # Use subprocess.run for better error handling
            try:
                result = subprocess.run(
                    ['sudo', '/usr/bin/systemctl', 'restart', 'ucm'],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if result.returncode != 0:
                    current_app.logger.error(f"Service restart failed: {result.stderr}")
                    # Still return success for cert apply, but warn about restart
                    return success_response(
                        message="Certificate applied but service restart failed. Please restart manually: sudo systemctl restart ucm",
                        data={'restart_failed': True, 'error': result.stderr}
                    )
            except subprocess.TimeoutExpired:
                current_app.logger.warning("Service restart timed out - this is expected as the process restarts")
            except Exception as e:
                current_app.logger.error(f"Service restart error: {e}")
                return success_response(
                    message="Certificate applied but service restart failed. Please restart manually: sudo systemctl restart ucm",
                    data={'restart_failed': True, 'error': str(e)}
                )
            
            return success_response(message="Certificate applied. Service restarting...")
        
    except Exception as e:
        current_app.logger.error(f"Failed to apply HTTPS cert: {e}")
        return error_response(f"Failed to apply certificate: {str(e)}", 500)

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
        
        AuditService.log_action(
            action='system_backup',
            resource_type='system',
            resource_name=filename,
            details=f'Created backup: {filename}',
            success=True
        )
        
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
        AuditService.log_action(
            action='backup_delete',
            resource_type='system',
            resource_name=filename,
            details=f'Deleted backup: {filename}',
            success=True
        )
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
        
        AuditService.log_action(
            action='system_restore',
            resource_type='system',
            resource_name='Backup Restore',
            details='Restored from backup file',
            success=True
        )
        
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
        
        if not dry_run:
            AuditService.log_action(
                action='system_encrypt',
                resource_type='system',
                resource_name='Private Keys',
                details=f'Encrypted {encrypted} private keys, skipped {skipped}',
                success=True
            )
        
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


@bp.route('/api/v2/system/security/rotate-secrets', methods=['POST'])
@require_auth(['admin:system'])
def rotate_secrets():
    """
    Rotate JWT secret key with automatic .env update.
    
    Process:
    1. Backup current .env file
    2. Current JWT_SECRET_KEY becomes JWT_SECRET_KEY_PREVIOUS
    3. New key is generated and set as JWT_SECRET_KEY
    4. Service restart (SIGHUP for graceful reload)
    5. Tokens signed with old key remain valid during transition period
    
    Body:
        new_secret: Optional - provide your own secret (32+ chars)
        auto_apply: bool - automatically update .env and restart (default: true)
        
    Returns:
        Success message or manual instructions if auto_apply=false
    """
    import secrets as py_secrets
    import shutil
    from datetime import datetime
    
    data = request.get_json() or {}
    new_secret = data.get('new_secret')
    auto_apply = data.get('auto_apply', True)
    
    # Generate new secret if not provided
    if not new_secret:
        new_secret = py_secrets.token_urlsafe(32)
    elif len(new_secret) < 32:
        return error_response("Secret must be at least 32 characters", 400)
    
    # Get current secret
    current_secret = os.getenv('JWT_SECRET_KEY', '')
    
    if auto_apply:
        # Determine .env path based on environment
        is_docker = os.environ.get('UCM_DOCKER', '').lower() in ('1', 'true')
        if is_docker:
            env_path = Path('/app/backend/.env')
            if not env_path.exists():
                env_path = Path('/app/.env')
        else:
            env_path = Path('/etc/ucm/ucm.env')
        
        if not env_path.exists():
            return error_response(f"Environment file not found: {env_path}", 500)
        
        try:
            # Backup current .env
            backup_path = env_path.with_suffix(f'.env.backup-{datetime.now().strftime("%Y%m%d_%H%M%S")}')
            shutil.copy(env_path, backup_path)
            
            # Read current .env
            env_content = env_path.read_text()
            lines = env_content.splitlines()
            new_lines = []
            jwt_key_found = False
            jwt_prev_found = False
            
            for line in lines:
                stripped = line.strip()
                
                # Update JWT_SECRET_KEY
                if stripped.startswith('JWT_SECRET_KEY=') and not stripped.startswith('JWT_SECRET_KEY_PREVIOUS'):
                    new_lines.append(f'JWT_SECRET_KEY={new_secret}')
                    jwt_key_found = True
                # Update or skip JWT_SECRET_KEY_PREVIOUS (we'll add it after)
                elif stripped.startswith('JWT_SECRET_KEY_PREVIOUS='):
                    jwt_prev_found = True
                    # Update with current secret
                    if current_secret:
                        new_lines.append(f'JWT_SECRET_KEY_PREVIOUS={current_secret}')
                else:
                    new_lines.append(line)
            
            # Add JWT_SECRET_KEY if not found
            if not jwt_key_found:
                new_lines.append(f'JWT_SECRET_KEY={new_secret}')
            
            # Add JWT_SECRET_KEY_PREVIOUS if not found and we have a current secret
            if not jwt_prev_found and current_secret:
                new_lines.append(f'JWT_SECRET_KEY_PREVIOUS={current_secret}')
            
            # Write updated .env
            env_path.write_text('\n'.join(new_lines) + '\n')
            
            # Save rotation timestamp to data file
            import json
            rotation_file = Path('/opt/ucm/data/jwt_rotation.json')
            rotation_file.parent.mkdir(parents=True, exist_ok=True)
            rotation_file.write_text(json.dumps({
                'rotated_at': datetime.now().isoformat(),
                'previous_expires_hours': 24
            }))
            
            # Log the rotation
            from services.audit_service import AuditService
            AuditService.log_action(
                action='secrets_rotated',
                resource_type='security',
                details=f'JWT secret key rotated automatically. Backup: {backup_path.name}',
                success=True
            )
            
            # Signal service to reload (graceful restart)
            import signal
            if is_docker:
                # In Docker, SIGTERM triggers container restart
                os.kill(os.getppid(), signal.SIGTERM)
            else:
                # In systemd, use SIGHUP for graceful reload or restart service
                try:
                    import subprocess
                    subprocess.run(['systemctl', 'restart', 'ucm'], check=True, timeout=30)
                except Exception:
                    # Fallback to SIGHUP
                    os.kill(os.getppid(), signal.SIGHUP)
            
            return success_response(
                data={
                    'rotated': True,
                    'backup': str(backup_path),
                    'previous_expires_in': '24 hours',
                    'note': 'Service is restarting. You will need to log in again. Old tokens remain valid for 24 hours.'
                },
                message='JWT secret rotated successfully. Service restarting.'
            )
            
        except Exception as e:
            current_app.logger.error(f"Failed to rotate secrets: {e}")
            return error_response(f"Failed to rotate secrets: {str(e)}", 500)
    
    else:
        # Manual mode - return instructions
        from services.audit_service import AuditService
        AuditService.log_action(
            action='secrets_rotation_initiated',
            resource_type='security',
            details='JWT secret key generated (manual apply required)',
            success=True
        )
        
        return success_response(
            data={
                'new_secret': new_secret,
                'previous_secret': current_secret[:8] + '...' if current_secret else None,
                'instructions': [
                    '1. Edit /etc/ucm/ucm.env',
                    '2. Set JWT_SECRET_KEY_PREVIOUS to your current JWT_SECRET_KEY value',
                    f'3. Set JWT_SECRET_KEY={new_secret}',
                    '4. Restart UCM: systemctl restart ucm',
                    '5. After 1 hour (token expiry), remove JWT_SECRET_KEY_PREVIOUS'
                ]
            },
            message='New secret generated. Follow instructions to complete rotation.'
        )


@bp.route('/api/v2/system/security/secrets-status', methods=['GET'])
@require_auth(['admin:system'])
def secrets_status():
    """Get status of secret keys (without revealing them)"""
    from config.settings import Config
    import json
    from datetime import datetime, timedelta
    
    jwt_configured = bool(os.getenv('JWT_SECRET_KEY')) and Config.JWT_SECRET_KEY != "INSTALL_TIME_PLACEHOLDER"
    jwt_previous = bool(os.getenv('JWT_SECRET_KEY_PREVIOUS'))
    session_configured = bool(os.getenv('SECRET_KEY')) and Config.SECRET_KEY != "INSTALL_TIME_PLACEHOLDER"
    encryption_configured = bool(os.getenv('KEY_ENCRYPTION_KEY'))
    
    # Check rotation timestamp from data file
    rotation_info = {}
    rotation_file = Path('/opt/ucm/data/jwt_rotation.json')
    if rotation_file.exists():
        try:
            rotation_info = json.loads(rotation_file.read_text())
        except Exception:
            pass
    
    rotated_at = rotation_info.get('rotated_at')
    expires_previous = None
    if rotated_at and jwt_previous:
        rotated_dt = datetime.fromisoformat(rotated_at)
        # Previous key expires 24 hours after rotation
        expires_dt = rotated_dt + timedelta(hours=24)
        expires_previous = expires_dt.isoformat()
    
    return success_response(data={
        'jwt_secret': {
            'configured': jwt_configured,
            'has_previous': jwt_previous,
            'rotated_at': rotated_at,
            'previous_expires_at': expires_previous,
            'rotation_in_progress': False
        },
        'session_secret': {
            'configured': session_configured
        },
        'encryption_key': {
            'configured': encryption_configured
        }
    })


@bp.route('/api/v2/system/security/anomalies', methods=['GET'])
@require_auth(['admin:system'])
def get_security_anomalies():
    """Get recent security anomalies"""
    try:
        from security.anomaly_detection import get_anomaly_detector
        
        hours = request.args.get('hours', 24, type=int)
        anomalies = get_anomaly_detector().get_recent_anomalies(hours)
        
        return success_response(
            data={
                'anomalies': anomalies,
                'period_hours': hours,
                'total': len(anomalies)
            }
        )
    except Exception as e:
        return error_response(f"Failed to get anomalies: {str(e)}", 500)


# ============================================================================
# UPDATE MANAGEMENT
# ============================================================================

@bp.route('/api/v2/system/updates/check', methods=['GET'])
@require_auth(['admin:system'])
def check_updates():
    """Check for available updates"""
    try:
        import os
        from services.updates import check_for_updates
        
        include_prereleases = request.args.get('include_prereleases', 'false').lower() == 'true'
        result = check_for_updates(include_prereleases=include_prereleases)
        result['can_auto_update'] = os.getenv('UCM_DOCKER') != '1'
        
        return success_response(data=result)
    except Exception as e:
        return error_response(f"Failed to check for updates: {str(e)}", 500)


@bp.route('/api/v2/system/updates/install', methods=['POST'])
@require_auth(['admin:system'])
def install_update():
    """Download and install an update"""
    import os
    if os.getenv('UCM_DOCKER') == '1':
        return error_response("Auto-update is not available in Docker. Pull the new image instead: docker pull ghcr.io/neyslim/ultimate-ca-manager:latest", 400)
    
    try:
        from services.updates import check_for_updates, download_update, install_update as do_install
        
        # Get update info
        include_prereleases = request.json.get('include_prereleases', False)
        update_info = check_for_updates(include_prereleases=include_prereleases)
        
        if not update_info.get('update_available'):
            return error_response("No update available", 400)
        
        if not update_info.get('download_url'):
            return error_response("No download URL available for this platform", 400)
        
        # Download
        package_path = download_update(
            update_info['download_url'],
            update_info['package_name']
        )
        
        # Install (this will restart the service)
        do_install(package_path)
        
        # Log the update
        from services.audit_service import AuditService
        AuditService.log_action(
            action='settings_update',
            resource_type='system',
            resource_id='ucm',
            resource_name='UCM Update',
            details=f"Updated from {update_info['current_version']} to {update_info['latest_version']}"
        )
        
        return success_response(
            message=f"Update to {update_info['latest_version']} initiated. Service will restart shortly."
        )
    except Exception as e:
        return error_response(f"Update failed: {str(e)}", 500)


@bp.route('/api/v2/system/updates/version', methods=['GET'])
def get_version():
    """Get current version info (public endpoint)"""
    from services.updates import get_current_version, get_edition
    
    return success_response(data={
        'version': get_current_version(),
        'edition': get_edition()
    })
