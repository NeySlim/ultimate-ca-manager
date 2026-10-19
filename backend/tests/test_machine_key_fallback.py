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


def test_new_key_is_private(fallback):
    etc_id, key_path = fallback
    etc_id.write_text('')
    enc._get_encryption_key()
    assert (key_path.stat().st_mode & 0o777) == 0o600


def test_losing_the_first_start_race_reads_the_winners_key(fallback):
    _, key_path = fallback
    key_path.parent.mkdir()
    key_path.write_text('winner')
    assert enc._create_machine_key() == 'winner'
    assert key_path.read_text() == 'winner'


def test_concurrent_first_starts_agree_on_one_key(fallback):
    import threading
    _, key_path = fallback
    barrier = threading.Barrier(8)
    results = []

    def start():
        barrier.wait()
        results.append(enc._create_machine_key())

    threads = [threading.Thread(target=start) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert set(results) == {key_path.read_text()}
    assert [p.name for p in key_path.parent.iterdir()] == ['.machine-key']


def test_without_hard_links_the_key_is_still_written_once(fallback, monkeypatch):
    _, key_path = fallback

    def no_link(*_a):
        raise PermissionError('no hard links here')

    monkeypatch.setattr(enc.os, 'link', no_link)
    first = enc._create_machine_key()
    assert key_path.read_text() == first
    assert (key_path.stat().st_mode & 0o777) == 0o600
    assert enc._create_machine_key() == first
