"""
System Security Operations
"""

from . import bp
from flask import request, current_app, Response
from auth.unified import require_auth
from utils.ha import reject_in_ha
from config.settings import Config
from utils.response import success_response, error_response
from utils.trusted_proxy import client_ip
from models import CA, Certificate, db
from services.audit_service import AuditService
from services.database_admin.lock import (
    MigrationBusyError,
    database_migration_lock,
)
from services.database_admin.persistence import update_env_file, env_file_path
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
        from security.encryption import (
            key_encryption, MASTER_KEY_PATH, count_master_key_values,
        )

        from security.dek_rotation import (
            disable_done, disable_grace, grace_end, retained, retiring, rotation_in_progress,
            shown_as_enabled, removes_key_file,
        )

        def stamp(moment):
            return moment.isoformat(timespec='seconds') + 'Z' if moment else None

        encrypted, unencrypted = count_master_key_values()
        # The short grace of a change: enable (after a disable) or rotate waits for its end,
        # known once every live node applied the change (None until then)
        disabled_grace = disable_grace()
        grace = None if disabled_grace else retiring()
        disabled_end = grace_end(disabled_grace) if disabled_grace else None
        grace_until = grace_end(grace) if grace else None
        done = disable_done()
        kept = retained()

        return success_response(data={
            'enabled': shown_as_enabled(),
            # A disable left half-way: values still open, none is encrypted any more
            'disabling': (key_encryption.is_enabled and not key_encryption.is_encrypting
                          and not done),
            'enable_available_after': stamp(disabled_end),
            'enable_waits_for_nodes': bool(disabled_grace) and disabled_end is None,
            # Old DEKs kept for reading only, each dropped after its date and a clean sweep
            'retained_keys': [{'version': r.version, 'retire_after': stamp(r.retire_after)}
                              for r in kept],
            # Outside HA master.key goes with the last DEK a disable kept
            'key_file_kept_for_retained_keys': bool(done and kept and removes_key_file()),
            'key_source': key_encryption.key_source,
            # Fingerprint and version only: neither key ever leaves the server here
            'kek_fingerprint': key_encryption.kek_fingerprint(),
            'dek_version': key_encryption.active_version,
            'rotation_in_progress': rotation_in_progress(),
            'rotation_available': key_encryption.is_encrypting and grace is None,
            'rotation_available_after': stamp(grace_until),
            'rotation_waits_for_nodes': bool(grace) and grace_until is None,
            'key_file_path': str(MASTER_KEY_PATH),
            'key_file_exists': key_encryption.key_file_exists(),
            'encrypted_count': encrypted,
            'unencrypted_count': unencrypted,
            'total_keys': encrypted + unencrypted,
            'key_files_on_disk': sum(1 for _ in Config.PRIVATE_DIR.glob('*.key')),
        })

    except Exception as e:
        logger.error(f"Failed to get encryption status: {e}")
        return error_response("Failed to get encryption status", 500)


def _wait_for_nodes(command):
    """HA: the live nodes load the new DEKs before values are written under them."""
    from security.dek_rotation import wait_for_nodes
    lagging = wait_for_nodes(command)
    if lagging:
        logger.warning(f"Encryption change: node(s) {', '.join(lagging)} did not reload in time")
    return lagging


def _enable_with_configured_kek():
    """A KEK is configured (variable, or HA): encryption restarts under it, nothing is written to disk."""
    from models import EncryptionKey
    from security.encryption import key_encryption, encrypt_all_keys as do_encrypt
    from security.dek_rotation import lock_key_state
    from security.master_key_bootstrap import record_operator_choice
    from security import envelope
    from services.cluster_commands import RELOAD_ENCRYPTION, emit
    lock_key_state()
    # A live node under another KEK would read this one as DEK version 1 once the markers go
    from security.master_key_bootstrap import live_peers_with_another_kek
    strangers = live_peers_with_another_kek()
    if strangers:
        db.session.rollback()
        names = ', '.join(f"{node} (fingerprint {fp})" for node, fp in strangers)
        return error_response(
            f"Encryption not enabled: live node(s) {names} hold another key-encryption key than "
            f"this node's ({key_encryption.kek_fingerprint()}). Configure the same "
            "KEY_ENCRYPTION_KEY on every node, or stop those nodes, then enable again.", 409)
    # Only the disabled marker goes. The DEKs a disable kept for its retention go on opening
    # late values under a new active DEK; any other stored DEK means this KEK cannot open it
    mine = key_encryption.kek_fingerprint()
    keys = EncryptionKey.query.filter(
        EncryptionKey.state.in_((envelope.ACTIVE, envelope.PREVIOUS))).all()
    # retire_after None: defensive, not reached by the normal paths (shown_as_enabled refused it)
    if key_encryption.dek_error or any(r.retire_after is None or r.kek_id != mine for r in keys):
        db.session.rollback()
        return error_response("The stored data-encryption keys do not open with the configured "
                              "key-encryption key; nothing was changed.", 409)
    EncryptionKey.query.filter_by(state=envelope.DISABLED).delete(synchronize_session=False)
    version = 1
    if keys:
        for row in keys:
            row.state = envelope.PREVIOUS
        version = max(r.version for r in keys) + 1
        kek = key_encryption.kek_bytes_for_envelope()
        db.session.add(EncryptionKey(version=version, state=envelope.ACTIVE, kek_id=mine,
                                     wrapped=envelope.wrap(kek, version, envelope.new_dek()),
                                     created_at=utc_now()))
    record_operator_choice(auto=True)
    command = emit(RELOAD_ENCRYPTION, {'version': version})
    db.session.commit()
    key_encryption.reload()
    if not key_encryption.is_enabled:
        return error_response("Failed to initialize encryption with the configured key", 500)
    _wait_for_nodes(command)
    encrypted, skipped, errors = do_encrypt(dry_run=False)
    # As with a new master.key: the plaintext .key mirrors a disable wrote go (#320)
    from security.master_key_bootstrap import purge_plaintext_key_files
    purge = purge_plaintext_key_files()
    AuditService.log_action(
        action='encryption_enabled',
        resource_type='system',
        resource_name='Private Key Encryption',
        details=(f"Encryption enabled with the configured key-encryption key "
                 f"({key_encryption.kek_fingerprint()}). Encrypted {encrypted} keys, "
                 f"{skipped} already encrypted. Removed {purge['removed']} key files; "
                 f"kept {purge['kept_no_db_key']} without a database key."),
        success=not errors)
    return success_response(
        message=f"Encryption enabled. {encrypted} keys encrypted.",
        data={'enabled': True, 'encrypted': encrypted, 'skipped': skipped, 'errors': errors,
              'key_files_removed': purge['removed'], 'key_files_kept': purge['kept_no_db_key'],
              'master_key': None, 'backup_required': False})


@bp.route('/api/v2/system/security/enable-encryption', methods=['POST'])
@require_auth(['admin:system'])
def enable_encryption():
    """
    Enable private key encryption.
    Without a KEK, generates a master key, writes it to master.key in UCM_CONFIG_DIR;
    with one (HA, KEY_ENCRYPTION_KEY), uses it. Encrypts every stored private key.
    """
    try:
        from security.encryption import KeyEncryption, key_encryption
        from security import encryption as _encryption
        from security.master_key_bootstrap import (
            KeyActivationError, activate_new_master_key, ephemeral_key_dir_refusal,
        )
        from utils.ha import ha_enabled
        from security.dek_rotation import RotationError, grace_refusal, retire_if_due, retiring

        grace = retiring()
        if grace and grace.get('disable'):
            # The DEKs of the last disable still open late values: they go first
            try:
                retire_if_due()
            except RotationError as e:
                return error_response(str(e), e.status)
            grace = retiring()
            if grace is not None:
                return error_response(grace_refusal(grace), 409)
        from security.dek_rotation import shown_as_enabled
        # Keys a disable kept for reading leave is_enabled on: the disable still stands
        if shown_as_enabled():
            return error_response("Encryption is already enabled", 400)
        if key_encryption.kek_loaded:
            return _enable_with_configured_kek()
        from security.dek_rotation import retained
        if retained():
            # A new master.key could not open them: a value still under them would be lost
            return error_response(
                "Data-encryption keys kept from the last disable are wrapped by a key-encryption "
                "key that is not configured: restore that master.key (or KEY_ENCRYPTION_KEY) "
                "and enable again.", 409)
        if ha_enabled():
            return error_response(
                "No key-encryption key is configured: set the same KEY_ENCRYPTION_KEY on "
                "every node and restart them.", 409)
        refusal = ephemeral_key_dir_refusal()
        if refusal:
            return error_response(f"Encryption not enabled: {refusal}.", 409)

        try:
            stats = activate_new_master_key(exclusive=False)
        except KeyActivationError:
            return error_response("Failed to initialize encryption after key generation", 500)
        encrypted, skipped, errors = stats['encrypted'], stats['skipped'], stats['errors']
        from security.master_key_bootstrap import record_operator_choice
        record_operator_choice(auto=True)
        db.session.commit()
        purge_stats = stats['purge']

        # Read the freshly-written key so the caller can immediately download
        # a backup. This is the ONLY chance to surface it cleanly: if the
        # operator never backs it up and later loses master.key,
        # every encrypted private key in the DB becomes unrecoverable.
        try:
            from security.encryption import MASTER_KEY_PATH
            master_key_pem = MASTER_KEY_PATH.read_text().strip()
        except Exception:
            master_key_pem = None

        AuditService.log_action(
            action='encryption_enabled',
            resource_type='system',
            resource_name='Private Key Encryption',
            details=(
                f"Encryption enabled. Encrypted {encrypted} keys, {skipped} "
                f"already encrypted. Removed {purge_stats['removed']} key files; "
                f"kept {purge_stats['kept_no_db_key']} without a database key."
            ),
            success=True
        )

        return success_response(
            message=f"Encryption enabled. {encrypted} keys encrypted.",
            data={
                'enabled': True,
                'key_file': str(KeyEncryption.key_file_exists() and _encryption.MASTER_KEY_PATH),
                'encrypted': encrypted,
                'skipped': skipped,
                'errors': errors,
                'key_files_removed': purge_stats['removed'],
                'key_files_kept': purge_stats['kept_no_db_key'],
                'master_key': master_key_pem,
                'backup_required': True,
            }
        )

    except PermissionError:
        from security.encryption import MASTER_KEY_PATH
        conf = MASTER_KEY_PATH.parent
        is_docker = os.path.exists('/.dockerenv')
        hint = (
            f" In Docker, mount a volume to {conf}/ or ensure the container "
            f"runs with write access (e.g. --user root or chown 1000:1000 {conf})."
            if is_docker else
            f" Check that the UCM service user owns {conf}/ "
            f"(sudo mkdir -p {conf} && sudo chown ucm:ucm {conf})."
        )
        return error_response(
            f"Permission denied: cannot write to {MASTER_KEY_PATH}.{hint}", 403
        )
    except Exception as e:
        logger.error(f"Failed to enable encryption: {e}")
        from security.encryption import KeyEncryption, key_encryption
        # A key that loaded may already encrypt values: removing it would lose them
        if not key_encryption.is_enabled:
            KeyEncryption.remove_key_file()
        return error_response("Failed to enable encryption", 500)


@bp.route('/api/v2/system/security/master-key/download', methods=['GET'])
@require_auth(['admin:system'])
def download_master_key():
    """
    Download the current master key file as plain text.

    SECURITY:
    - admin:system only
    - audited (every download logged with IP)
    - returned as application/octet-stream attachment named ucm-master.key
    - never cached (no-store)

    Use case: operator just enabled encryption (or wants to back up an
    existing key). Without this file, ALL encrypted private keys in the DB
    are unrecoverable after a host migration / Docker container recreate.
    """
    try:
        from security.encryption import key_encryption, MASTER_KEY_PATH

        if not key_encryption.is_enabled:
            return error_response("Encryption is not enabled, no master key to download", 400)

        if key_encryption.key_source != 'file' or not MASTER_KEY_PATH.exists():
            return error_response(
                "Master key is not stored as a file (likely loaded from "
                "KEY_ENCRYPTION_KEY env var), backup must be done manually.",
                409
            )

        try:
            key_bytes = MASTER_KEY_PATH.read_bytes()
        except PermissionError:
            return error_response(
                f"Permission denied reading {MASTER_KEY_PATH}. "
                "Check that the UCM service user owns it.", 403
            )

        AuditService.log_action(
            action='master_key_downloaded',
            resource_type='system',
            resource_name='Master Key',
            details=f'Master key downloaded for backup from {client_ip()}',
            success=True,
        )

        return Response(
            key_bytes,
            mimetype='application/octet-stream',
            headers={
                'Content-Disposition': 'attachment; filename="ucm-master.key"',
                'Cache-Control': 'no-store, no-cache, must-revalidate, private',
                'Pragma': 'no-cache',
                'X-Content-Type-Options': 'nosniff',
            }
        )
    except Exception as e:
        logger.error(f"Failed to download master key: {e}")
        return error_response("Failed to download master key", 500)


def _env_kek_fingerprint():
    import base64
    from security.envelope import kek_id
    value = os.getenv('KEY_ENCRYPTION_KEY', '').strip()
    if not value:
        return None
    try:
        return kek_id(base64.urlsafe_b64decode(value.encode()))
    except Exception:
        return None


@bp.route('/api/v2/system/security/disable-encryption', methods=['POST'])
@require_auth(['admin:system'])
def disable_encryption():
    """
    Disable private key encryption.
    Decrypts all keys in database; the DEKs are kept for reading through their retention, then
    dropped with a master.key file outside HA. A KEK that stays configured (variable, HA) is
    kept, unused.
    """
    try:
        from security.encryption import (
            key_encryption, key_encryption_required,
            decrypt_all_keys as do_decrypt
        )

        # Refuse BEFORE any destructive step. Under the require flag,
        # decrypting the database and removing the key file would end in
        # reload() raising after the damage is done — leaving keys in
        # plaintext AND a service that refuses its next startup.
        if key_encryption_required():
            logger.warning(
                "Disable-encryption refused: UCM_REQUIRE_KEY_ENCRYPTION is set"
            )
            return error_response(
                "Private-key encryption is enforced on this deployment "
                "(UCM_REQUIRE_KEY_ENCRYPTION is set). Disabling it would "
                "store private keys in plaintext and the service would "
                "refuse its next startup. Unset UCM_REQUIRE_KEY_ENCRYPTION "
                "and restart UCM first if you really intend to disable "
                "encryption.", 409
            )

        from security.dek_rotation import (
            RotationError, begin_disable, finish_disable, grace_end, retained, retire_if_due,
            retiring, settle,
        )
        from utils.ha import ha_enabled

        # Phase 1, under the lock: nothing new is encrypted, every DEK still opens what it did
        try:
            if retiring() is not None:
                retire_if_due()  # a grace that is over no longer holds the disable
            command = begin_disable()
        except RotationError as e:
            return error_response(str(e), e.status)
        settle()
        _wait_for_nodes(command)

        decrypted, skipped, errors = do_decrypt(dry_run=False)

        if errors:
            return error_response(
                f"Failed to decrypt some keys: {', '.join(errors[:3])}. "
                "Encryption NOT disabled to prevent data loss.", 500
            )

        # A master.key file outside HA is removed with the DEKs; the KEK that stays configured
        # (this one, or the variable the next reload falls back to) is marked unused
        remove_file = key_encryption.key_source == 'file' and not ha_enabled()
        kept_kek = key_encryption.kek_fingerprint() if not remove_file else _env_kek_fingerprint()
        # Phase 2: only if no value is encrypted any more; the DEKs stay for their retention
        try:
            finish_disable(kept_kek)
        except RotationError as e:
            return error_response(str(e), e.status)
        try:
            dropped = retire_if_due()
        except RotationError as e:
            logger.error(f"🔑 Data-encryption keys kept after the disable: {e}")
            dropped = 0

        # Reload singleton
        key_encryption.reload()
        grace = retiring()
        enable_after = grace_end(grace) if grace else None
        kept_until = max((r.retire_after for r in retained()), default=None)

        from services.file_regen_service import regenerate_all_files
        regeneration_stats = regenerate_all_files()
        key_files_written = (
            regeneration_stats['ca_keys'] + regeneration_stats['cert_keys']
        )

        AuditService.log_action(
            action='encryption_disabled',
            resource_type='system',
            resource_name='Private Key Encryption',
            details=(
                f"Encryption disabled. Decrypted {decrypted} keys and wrote "
                f"{key_files_written} key files."
            ),
            success=True
        )

        return success_response(
            message=f"Encryption disabled. {decrypted} keys decrypted.",
            data={
                'enabled': False,
                'decrypted': decrypted,
                'skipped': skipped,
                'key_files_written': key_files_written,
                'keys_kept_until': (None if dropped or not kept_until
                                    else kept_until.isoformat(timespec='seconds') + 'Z'),
                'enable_available_after': (enable_after.isoformat(timespec='seconds') + 'Z'
                                           if enable_after else None),
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


@bp.route('/api/v2/system/security/rotate-encryption-key', methods=['POST'])
@require_auth(['admin:system'])
def rotate_encryption_key():
    """New data-encryption key, every stored value rewritten under it; resumes an unfinished one.

    The KEK (master.key, KEY_ENCRYPTION_KEY) is unchanged: it only changes by hand.
    """
    from security.encryption import key_encryption
    from security import dek_rotation
    if not key_encryption.is_enabled:
        return error_response("Encryption is not enabled", 400)
    try:
        result = dek_rotation.rotate()
    except dek_rotation.RotationError as e:
        db.session.rollback()
        return error_response(str(e), e.status)
    except Exception as e:
        db.session.rollback()
        logger.error(f"DEK rotation failed: {type(e).__name__}: {e}")
        AuditService.log_action(
            action='encryption_key_rotated', resource_type='system',
            resource_name='Data Encryption Key',
            details=f"DEK rotation interrupted ({type(e).__name__}); run it again to resume",
            success=False)
        return error_response("Key rotation interrupted: run it again to resume", 500)
    done = result['state'] == 'done'
    AuditService.log_action(
        action='encryption_key_rotated', resource_type='system',
        resource_name='Data Encryption Key',
        details=(f"DEK rotated to version {result['version']}: {result['rewritten']} values "
                 f"rewritten, {result['dropped']} previous key(s) dropped" if done else
                 f"DEK rotation to version {result['version']} started, waiting for node(s) "
                 f"{', '.join(result['waiting_for'])}"),
        success=True)
    if done:
        return success_response(message=f"Data-encryption key rotated to version {result['version']}",
                                data=result)
    return success_response(
        message="Rotation started: some nodes have not loaded the new key yet, run it again "
                "to finish", data=result, status=202)


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
                f'2. Write it to {MASTER_KEY_PATH} on the server\n'
                f'3. Set permissions: chmod 600 {MASTER_KEY_PATH}\n'
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

        from utils.ha import ha_enabled
        if ha_enabled():
            return _update_stored_rate_limits(data)

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


def _update_stored_rate_limits(data):
    """HA: the change is stored and its command emitted in one transaction, then applied here."""
    import json
    from models import SystemConfig
    from security.rate_limiter import STORED_KEY, RateLimitConfig
    from services.cluster_commands import RELOAD_RATE_LIMITS, emit
    row = SystemConfig.query.filter_by(key=STORED_KEY).with_for_update().first()
    stored = RateLimitConfig.merge_stored(json.loads(row.value) if row and row.value else None, data)
    if row is None:
        row = SystemConfig(key=STORED_KEY)
        db.session.add(row)
    row.value = json.dumps(stored, sort_keys=True)
    emit(RELOAD_RATE_LIMITS, stored)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Rate limit config not saved: {type(e).__name__}: {e}")
        return error_response("Failed to update config", 500)
    RateLimitConfig.compose(stored)
    return success_response(message="Rate limit config updated", data=RateLimitConfig.get_config())


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
@reject_in_ha()
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
        env_path = env_file_path()

        if not env_path.exists():
            return error_response(f"Environment file not found: {env_path}", 500)

        def _replace_secret(existing: str) -> str:
            """Swap SECRET_KEY and drop the old JWT keys, keep everything else."""
            lines = []
            key_found = False
            for line in existing.splitlines():
                stripped = line.strip()
                if stripped.startswith('SECRET_KEY='):
                    lines.append(f'SECRET_KEY={new_secret}')
                    key_found = True
                elif stripped.startswith('JWT_SECRET_KEY'):
                    continue  # Remove old JWT keys
                else:
                    lines.append(line)
            if not key_found:
                lines.append(f'SECRET_KEY={new_secret}')
            return '\n'.join(lines) + '\n'

        try:
            # The same file the backend switch writes, through the same
            # writer: a truncating write here would destroy the DATABASE_URL
            # a migration has just verified, and a plain read-then-write can
            # interleave with one. The migration lock covers the second half.
            with database_migration_lock(purpose='rotating the session secret'):
                ok, message, _backup = update_env_file(
                    env_path, _replace_secret,
                    verify=lambda observed: f'SECRET_KEY={new_secret}' in observed,
                    what='SECRET_KEY',
                )
                if not ok:
                    return error_response(message, 500)

                # Log the rotation
                AuditService.log_action(
                    action='secrets_rotated',
                    resource_type='security',
                    details='Session secret key rotated',
                    success=True
                )

                # Restart service
                from utils.service_manager import restart_service as do_restart
                do_restart()

            return success_response(
                data={
                    'rotated': True,
                    'note': 'Service is restarting. All users will need to log in again.'
                },
                message='Session secret rotated successfully. Service restarting.'
            )
        except MigrationBusyError as busy:
            return error_response(str(busy), 409)

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
                    f'1. Edit {env_file_path()}',
                    f'2. Set SECRET_KEY={new_secret}',
                    '3. Restart UCM: systemctl restart ucm'
                ]
            },
            message='New secret generated. Follow instructions to complete rotation.'
        )


# ============ Security Status ============

def _key_file_exists():
    from security.encryption import KeyEncryption
    return KeyEncryption.key_file_exists()


@bp.route('/api/v2/system/security/secrets-status', methods=['GET'])
@require_auth(['admin:system'])
def secrets_status():
    """Get status of secret keys (without revealing them)"""
    from config.settings import Config

    session_configured = bool(os.getenv('SECRET_KEY')) and Config.SECRET_KEY != "INSTALL_TIME_PLACEHOLDER"
    encryption_configured = bool(os.getenv('KEY_ENCRYPTION_KEY')) or _key_file_exists()

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
