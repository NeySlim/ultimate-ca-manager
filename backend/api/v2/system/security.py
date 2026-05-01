"""
System Security Operations
"""

from . import bp
from flask import request, current_app
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import CA, Certificate, db
from services.audit_service import AuditService
from pathlib import Path
import os
import shutil
import secrets as py_secrets
from datetime import datetime, timezone
import logging
from utils.datetime_utils import utc_now
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization

logger = logging.getLogger(__name__)


# ============================================================================
# Encryption Management
# ============================================================================

@bp.route('/api/v2/system/security/encryption-status', methods=['GET'])
@require_auth(['admin:system'])
def get_encryption_status():
    """Get private key encryption status"""
    try:
        from security.encryption import key_encryption, MASTER_KEY_PATH
        
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
            'key_source': key_encryption.key_source,
            'key_file_path': str(MASTER_KEY_PATH),
            'key_file_exists': key_encryption.key_file_exists(),
            'encrypted_count': encrypted,
            'unencrypted_count': unencrypted,
            'total_keys': encrypted + unencrypted
        })
        
    except Exception as e:
        logger.error(f"Failed to get encryption status: {e}")
        return error_response("Failed to get encryption status", 500)


@bp.route('/api/v2/system/security/enable-encryption', methods=['POST'])
@require_auth(['admin:system'])
def enable_encryption():
    """
    Enable private key encryption.
    Generates a master key, writes it to /etc/ucm/master.key,
    and encrypts all existing private keys in the database.
    """
    try:
        from security.encryption import (
            KeyEncryption, key_encryption, encrypt_all_keys as do_encrypt
        )
        
        if key_encryption.is_enabled:
            return error_response("Encryption is already enabled", 400)
        
        # Generate key and write to file
        key = KeyEncryption.generate_key()
        KeyEncryption.write_key_file(key)
        
        # Reload singleton to pick up the new key
        key_encryption.reload()
        
        if not key_encryption.is_enabled:
            KeyEncryption.remove_key_file()
            return error_response("Failed to initialize encryption after key generation", 500)
        
        # Encrypt all existing keys
        encrypted, skipped, errors = do_encrypt(dry_run=False)
        
        AuditService.log_action(
            action='encryption_enabled',
            resource_type='system',
            resource_name='Private Key Encryption',
            details=f'Encryption enabled. Encrypted {encrypted} keys, {skipped} already encrypted.',
            success=True
        )
        
        return success_response(
            message=f"Encryption enabled. {encrypted} keys encrypted.",
            data={
                'enabled': True,
                'key_file': str(KeyEncryption.key_file_exists() and '/etc/ucm/master.key'),
                'encrypted': encrypted,
                'skipped': skipped,
                'errors': errors
            }
        )
        
    except PermissionError:
        is_docker = os.path.exists('/.dockerenv')
        hint = (
            " In Docker, mount a volume to /etc/ucm/ or ensure the container "
            "runs with write access (e.g. --user root or chown 1000:1000 /etc/ucm)."
            if is_docker else
            " Check that the UCM service user owns /etc/ucm/ "
            "(sudo mkdir -p /etc/ucm && sudo chown ucm:ucm /etc/ucm)."
        )
        return error_response(
            f"Permission denied: cannot write to /etc/ucm/master.key.{hint}", 403
        )
    except Exception as e:
        logger.error(f"Failed to enable encryption: {e}")
        KeyEncryption.remove_key_file()
        return error_response("Failed to enable encryption", 500)


@bp.route('/api/v2/system/security/disable-encryption', methods=['POST'])
@require_auth(['admin:system'])
def disable_encryption():
    """
    Disable private key encryption.
    Decrypts all keys in database, then removes the master key file.
    """
    try:
        from security.encryption import (
            KeyEncryption, key_encryption, decrypt_all_keys as do_decrypt
        )
        
        if not key_encryption.is_enabled:
            return error_response("Encryption is not enabled", 400)
        
        # Decrypt all keys first (while we still have the key)
        decrypted, skipped, errors = do_decrypt(dry_run=False)
        
        if errors:
            return error_response(
                f"Failed to decrypt some keys: {', '.join(errors[:3])}. "
                "Encryption NOT disabled to prevent data loss.", 500
            )
        
        # Remove key file
        KeyEncryption.remove_key_file()
        
        # Reload singleton
        key_encryption.reload()
        
        AuditService.log_action(
            action='encryption_disabled',
            resource_type='system',
            resource_name='Private Key Encryption',
            details=f'Encryption disabled. Decrypted {decrypted} keys.',
            success=True
        )
        
        return success_response(
            message=f"Encryption disabled. {decrypted} keys decrypted.",
            data={
                'enabled': False,
                'decrypted': decrypted,
                'skipped': skipped
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to disable encryption: {e}")
        return error_response("Failed to disable encryption", 500)


@bp.route('/api/v2/system/security/encrypt-all-keys', methods=['POST'])
@require_auth(['admin:system'])
def encrypt_all_keys():
    """Encrypt all unencrypted private keys in the database"""
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
        
    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        return error_response("Encryption failed", 500)


@bp.route('/api/v2/system/security/generate-key', methods=['GET'])
@require_auth(['admin:system'])
def generate_encryption_key():
    """
    Generate a new encryption key.
    Returns the key as plaintext - the user must save it securely.
    """
    try:
        from security.encryption import KeyEncryption, MASTER_KEY_PATH
        key = KeyEncryption.generate_key()
        
        return success_response(data={
            'key': key,
            'key_file_path': str(MASTER_KEY_PATH),
            'instructions': (
                '1. Save this key to a secure location\n'
                '2. Write it to /etc/ucm/master.key on the server\n'
                '3. Set permissions: chmod 600 /etc/ucm/master.key\n'
                '4. Restart UCM service'
            )
        })
    except Exception as e:
        logger.error(f"Failed to generate key: {e}")
        return error_response("Failed to generate key", 500)


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
        logger.error(f"Failed to get rate limit config: {e}")
        return error_response("Failed to get rate limit config", 500)


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
        logger.error(f"Failed to update rate limit config: {e}")
        return error_response("Failed to update config", 500)


@bp.route('/api/v2/system/security/rate-limit/stats', methods=['GET'])
@require_auth(['read:settings'])
def get_rate_limit_stats():
    """Get rate limiting statistics"""
    try:
        from security.rate_limiter import get_rate_limiter
        return success_response(data=get_rate_limiter().get_stats())
    except Exception as e:
        logger.error(f"Failed to get rate limit stats: {e}")
        return error_response("Failed to get stats", 500)


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
        logger.error(f"Failed to reset rate limits: {e}")
        return error_response("Failed to reset", 500)


# ============ Secrets Rotation ============

@bp.route('/api/v2/system/security/rotate-secrets', methods=['POST'])
@require_auth(['admin:system'])
def rotate_secrets():
    """
    Rotate session secret key with automatic .env update.
    
    Process:
    1. Backup current .env file
    2. Generate new SECRET_KEY
    3. Service restart
    4. All active sessions are invalidated (users must re-login)
    """
    data = request.get_json() or {}
    new_secret = data.get('new_secret')
    auto_apply = data.get('auto_apply', True)
    
    # Generate new secret if not provided
    if not new_secret:
        new_secret = py_secrets.token_urlsafe(32)
    elif len(new_secret) < 32:
        return error_response("Secret must be at least 32 characters", 400)
    
    if auto_apply:
        # Determine .env path based on environment
        is_docker = os.environ.get('UCM_DOCKER', '').lower() in ('1', 'true')
        if is_docker:
            env_path = Path('/opt/ucm/.env')
            if not env_path.exists():
                # Fallback for older Docker images
                env_path = Path('/app/.env')
                if not env_path.exists():
                    env_path = Path('/app/backend/.env')
        else:
            env_path = Path('/etc/ucm/ucm.env')
        
        if not env_path.exists():
            return error_response(f"Environment file not found: {env_path}", 500)
        
        try:
            # Backup current .env
            backup_path = env_path.with_suffix(f'.env.backup-{utc_now().strftime("%Y%m%d_%H%M%S")}')
            shutil.copy(env_path, backup_path)
            
            # Read and update .env
            env_content = env_path.read_text()
            lines = env_content.splitlines()
            new_lines = []
            key_found = False
            
            for line in lines:
                stripped = line.strip()
                if stripped.startswith('SECRET_KEY='):
                    new_lines.append(f'SECRET_KEY={new_secret}')
                    key_found = True
                elif stripped.startswith('JWT_SECRET_KEY'):
                    continue  # Remove old JWT keys
                else:
                    new_lines.append(line)
            
            if not key_found:
                new_lines.append(f'SECRET_KEY={new_secret}')
            
            env_path.write_text('\n'.join(new_lines) + '\n')
            
            # Log the rotation
            AuditService.log_action(
                action='secrets_rotated',
                resource_type='security',
                details=f'Session secret key rotated. Backup: {backup_path.name}',
                success=True
            )
            
            # Restart service
            from utils.service_manager import restart_service as do_restart
            do_restart()
            
            return success_response(
                data={
                    'rotated': True,
                    'backup': str(backup_path),
                    'note': 'Service is restarting. All users will need to log in again.'
                },
                message='Session secret rotated successfully. Service restarting.'
            )
            
        except Exception as e:
            current_app.logger.error(f"Failed to rotate secrets: {e}")
            return error_response("Failed to rotate secrets", 500)
    
    else:
        AuditService.log_action(
            action='secrets_rotation_initiated',
            resource_type='security',
            details='Session secret key generated (manual apply required)',
            success=True
        )
        
        return success_response(
            data={
                'new_secret': new_secret,
                'instructions': [
                    '1. Edit /etc/ucm/ucm.env',
                    f'2. Set SECRET_KEY={new_secret}',
                    '3. Restart UCM: systemctl restart ucm'
                ]
            },
            message='New secret generated. Follow instructions to complete rotation.'
        )


# ============ Security Status ============

@bp.route('/api/v2/system/security/secrets-status', methods=['GET'])
@require_auth(['admin:system'])
def secrets_status():
    """Get status of secret keys (without revealing them)"""
    from config.settings import Config
    
    session_configured = bool(os.getenv('SECRET_KEY')) and Config.SECRET_KEY != "INSTALL_TIME_PLACEHOLDER"
    encryption_configured = bool(os.getenv('KEY_ENCRYPTION_KEY')) or os.path.exists('/etc/ucm/master.key')
    
    return success_response(data={
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
        logger.error(f"Failed to get anomalies: {e}")
        return error_response("Failed to get anomalies", 500)
