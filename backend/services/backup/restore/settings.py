"""Settings that are stored encrypted, put back with the target's key.

The archive carries them in the clear, protected by the archive itself, which
is what makes it restorable on an installation whose database key is not the
source's. Writing them back means encrypting them again here, and marking the
row as holding a secret so the next export knows it does.
"""
import logging
from typing import Any, Dict, Iterable

from models import SystemConfig, db

logger = logging.getLogger(__name__)


def restore_encrypted_settings(configuration: Dict[str, Any],
                               keys: Iterable[str]) -> int:
    """Re-encrypt the settings the archive marked as secret. Returns a count."""
    from fnmatch import fnmatchcase
    from security.encryption import MASTER_KEY_CONFIG_KEYS, encrypt_text
    from utils.encryption import encrypt_if_needed

    settings = configuration.get('settings') or {}
    restored = 0
    for key in keys or ():
        if key not in settings:
            continue
        value = settings[key]
        if value is None:
            continue
        row = SystemConfig.query.filter_by(key=key).first()
        if row is None:
            row = SystemConfig(key=key)
            db.session.add(row)
        # Written back under the layer its readers decrypt
        if any(fnmatchcase(key, pattern) for pattern in MASTER_KEY_CONFIG_KEYS):
            row.value = encrypt_text(str(value))
        else:
            row.value = encrypt_if_needed(str(value))
        row.encrypted = True
        restored += 1

    if restored:
        db.session.flush()
    return restored
