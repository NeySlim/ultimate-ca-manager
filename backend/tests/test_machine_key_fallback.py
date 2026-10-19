"""The machine-id fallback key survives a restart when /etc/machine-id is empty."""
import pytest

import utils.encryption as enc


@pytest.fixture
def fallback(monkeypatch, tmp_path):
    monkeypatch.delenv('UCM_DB_ENCRYPTION_KEY', raising=False)
    monkeypatch.setattr(enc, '_require_db_encryption_key', lambda: False)
    etc_id = tmp_path / 'machine-id'
    key_path = tmp_path / 'data' / '.machine-key'
    monkeypatch.setattr(enc, 'MACHINE_KEY_PATH', str(key_path))
    monkeypatch.setattr(enc, 'MACHINE_ID_PATHS',
                        (str(etc_id), str(tmp_path / 'absent'), str(key_path)))
    return etc_id, key_path


def test_empty_machine_id_reuses_the_persisted_key(fallback):
    etc_id, key_path = fallback
    etc_id.write_text('\n')
    first = enc._get_encryption_key()
    assert key_path.read_text()
    assert enc._get_encryption_key() == first  # a second start derives the same key


def test_a_secret_written_before_a_restart_reads_back(fallback):
    from cryptography.fernet import Fernet
    etc_id, _ = fallback
    etc_id.write_text('')
    token = Fernet(enc._get_encryption_key()).encrypt(b'smtp-password')
    assert Fernet(enc._get_encryption_key()).decrypt(token) == b'smtp-password'


def test_a_real_machine_id_still_wins(fallback):
    etc_id, key_path = fallback
    etc_id.write_text('0123456789abcdef0123456789abcdef\n')
    key_path.parent.mkdir()
    key_path.write_text('other')
    import base64
    import hashlib
    expected = base64.urlsafe_b64encode(hashlib.pbkdf2_hmac(
        'sha256', b'0123456789abcdef0123456789abcdef', b'ucm-encryption-salt', 100000, dklen=32))
    assert enc._get_encryption_key() == expected
