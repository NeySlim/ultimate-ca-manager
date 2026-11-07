"""Master key at first start, so a new installation stores no private key in the clear.

A key is created only where none was ever configured and nothing in the database
is encrypted: a missing key beside encrypted rows is a lost key (safe mode).
"""
import logging
import os
import re
from pathlib import Path

from security import encryption as _encryption

logger = logging.getLogger(__name__)

# Docker and Podman name an anonymous volume after 64 hex digits
_ANONYMOUS_VOLUME = re.compile(r'/volumes/[0-9a-f]{64}/_data/?$')
_MEMORY_FILESYSTEMS = {'tmpfs', 'ramfs'}


def in_container() -> bool:
    return (os.getenv('UCM_DOCKER') == '1' or os.path.exists('/.dockerenv')
            or os.path.exists('/run/.containerenv'))


def _read_mountinfo() -> str:
    return Path('/proc/self/mountinfo').read_text()


def _unescape(field: str) -> str:
    return re.sub(r'\\([0-7]{3})', lambda m: chr(int(m.group(1), 8)), field)


def container_dir_is_persistent(directory, mountinfo: str = None):
    """(persistent, reason) for `directory` in a container: it must be a volume of
    its own that outlives the container, not an anonymous volume, memory or an emptyDir."""
    target = str(directory).rstrip('/') or '/'
    if mountinfo is None:
        try:
            mountinfo = _read_mountinfo()
        except OSError as e:
            return False, f'the mount table is unreadable ({e})'
    found = None
    for line in mountinfo.splitlines():
        left, sep, right = line.partition(' - ')
        fields = left.split()
        if not sep or len(fields) < 5:
            continue
        root, point = _unescape(fields[3]), _unescape(fields[4])
        if target == point or target.startswith(point.rstrip('/') + '/'):
            # The longest mount point holds the path; the last mounted one wins
            if found is None or len(point) >= len(found[1]):
                found = (root, point, (right.split() or [''])[0])
    if found is None or found[1] != target:
        return False, f'{target} is not a volume of its own'
    root, _, fstype = found
    if fstype in _MEMORY_FILESYSTEMS:
        return False, f'{target} is held in memory ({fstype})'
    if _ANONYMOUS_VOLUME.search(root):
        return False, f'{target} is an anonymous volume'
    if 'kubernetes.io~empty-dir' in root:
        return False, f'{target} is an emptyDir volume'
    return True, ''


class KeyActivationError(RuntimeError):
    """The new key file was written but does not load; it has been removed."""


def activate_new_master_key(exclusive: bool) -> dict:
    """Write a new master key, load it, encrypt what is stored without it.

    The key file is removed only when it failed to load: once a value is
    encrypted under it, removing it would lose that value.
    """
    KeyEncryption = _encryption.KeyEncryption
    key_encryption = _encryption.key_encryption
    KeyEncryption.write_key_file(KeyEncryption.generate_key(), exclusive=exclusive)
    key_encryption.reload()
    if not key_encryption.is_enabled:
        KeyEncryption.remove_key_file()
        raise KeyActivationError('Failed to initialize encryption after key generation')

    encrypted, skipped, errors = _encryption.encrypt_all_keys(dry_run=False)
    from services.file_regen_service import purge_private_key_files
    purge = purge_private_key_files()
    return {'encrypted': encrypted, 'skipped': skipped, 'errors': errors, 'purge': purge}


def bootstrap_master_key(app) -> str:
    """Create the master key when the installation never had one; returns what was done."""
    key_encryption = _encryption.key_encryption
    path = _encryption.MASTER_KEY_PATH
    if key_encryption.is_enabled:
        return 'present'
    if not app.config.get('AUTO_MASTER_KEY'):
        return 'disabled'
    # A key that exists but does not load is reported, never replaced
    if path.exists() or os.getenv('KEY_ENCRYPTION_KEY'):
        return 'configured'
    if _encryption.has_encrypted_keys_in_db():
        return 'lost'
    if in_container():
        persistent, reason = container_dir_is_persistent(path.parent)
        if not persistent:
            logger.error(
                "🔓 No master key created: %s, so it would be lost with the container. "
                "Mount %s on a named volume or a host directory, or set KEY_ENCRYPTION_KEY; "
                "private keys stay unencrypted until then.", reason, path.parent)
            return 'ephemeral'
    try:
        stats = activate_new_master_key(exclusive=True)
    except FileExistsError:
        # Another process of this start created it first
        key_encryption.reload()
        return 'present' if key_encryption.is_enabled else 'configured'
    except (OSError, KeyActivationError) as e:
        logger.error("🔓 Could not create the master key %s: %s; private keys stay unencrypted",
                     path, e)
        return 'unwritable'

    logger.warning(
        "🔑 Master key created at %s; %d keys and secrets encrypted. Back this file up: "
        "without it a copy of the database cannot be decrypted.", path, stats['encrypted'])
    from services.audit_service import AuditService
    AuditService.log_action(
        action='encryption_enabled',
        resource_type='system',
        resource_name='Private Key Encryption',
        details=(f"Master key created at first start. Encrypted {stats['encrypted']} keys, "
                 f"{len(stats['errors'])} errors. Removed {stats['purge']['removed']} key files."),
        success=not stats['errors'],
    )
    return 'generated'


def check_master_key_at_start(app) -> None:
    """Load the master key, create it on a new installation, and enter safe mode
    when encrypted keys are found without it. Runs inside an app context."""
    key_encryption = _encryption.key_encryption
    key_encryption.reload()
    outcome = bootstrap_master_key(app)
    has_enc = _encryption.has_encrypted_keys_in_db()
    app.logger.info(
        f"🔐 Encryption check: enabled={key_encryption.is_enabled}, has_encrypted_keys={has_enc}, "
        f"key_source={key_encryption.key_source}, first_start={outcome}")
    app.config['SAFE_MODE'] = not key_encryption.is_enabled and has_enc
    if app.config['SAFE_MODE']:
        app.logger.error(
            "🔒 SAFE MODE: Encrypted private keys found but no encryption key available. "
            f"Place your master.key file at {_encryption.MASTER_KEY_PATH} and restart UCM.")
