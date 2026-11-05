"""Settings that are stored encrypted, put back with the target's key.

The archive carries them in the clear, protected by the archive itself, which
is what makes it restorable on an installation whose database key is not the
source's. Writing them back means encrypting them again here, and marking the
row as holding a secret so the next export knows it does.
"""
import logging
from typing import Any, Dict, Iterable

from models import SystemConfig, db

from .. import installation

logger = logging.getLogger(__name__)


def store_setting(key: str, value: Any, *, encrypted: bool = False) -> None:
    """Write one setting; a secret one under the layer its readers decrypt."""
    from fnmatch import fnmatchcase
    from security.encryption import MASTER_KEY_CONFIG_KEYS, encrypt_text
    from utils.encryption import encrypt_if_needed

    row = SystemConfig.query.filter_by(key=key).first()
    if row is None:
        row = SystemConfig(key=key)
        db.session.add(row)
    if not encrypted or value in (None, ''):
        row.value = value
        return
    if any(fnmatchcase(key, pattern) for pattern in MASTER_KEY_CONFIG_KEYS):
        row.value = encrypt_text(str(value))
    else:
        row.value = encrypt_if_needed(str(value))
    row.encrypted = True


def restore_encrypted_settings(configuration: Dict[str, Any],
                               keys: Iterable[str], skip: Iterable[str] = ()) -> int:
    """Re-encrypt the settings the archive marked as secret. Returns a count."""
    settings = configuration.get('settings') or {}
    skip = set(skip)
    restored = 0
    for key in keys or ():
        if key not in settings or key == installation.CONFIG_KEY or key in skip:
            continue    # the installation keeps its own identifier; a renumbered one comes later
        value = settings[key]
        if value is None:
            continue
        store_setting(key, value, encrypted=True)
        restored += 1

    if restored:
        db.session.flush()
    return restored
