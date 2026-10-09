"""The suite never reads the master key of the machine it runs on: rows
encrypted with it would break later tests that switch keys, and a test that
enables encryption would write next to the live key."""
import os
from pathlib import Path

from security import encryption


def test_master_key_path_is_sandboxed():
    assert encryption.MASTER_KEY_PATH != Path('/etc/ucm/master.key')
    assert str(encryption.MASTER_KEY_PATH).startswith(os.environ['DATA_DIR'])


def test_no_key_comes_from_the_environment():
    assert 'KEY_ENCRYPTION_KEY' not in os.environ
    assert 'KEY_ENCRYPTION_KEY_FILE' not in os.environ
