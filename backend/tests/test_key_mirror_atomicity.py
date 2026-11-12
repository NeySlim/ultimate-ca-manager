"""A key mirror is replaced whole, or the previous one stays.

`mirror_private_key` opened the destination with O_TRUNC and wrote into it.
The truncation happens first, so a failure partway -- a full disk, a
read-only mount, a process killed -- left the file empty or half written
while the caller went on to report a success. The mirror exists so that
tools can read a key off disk; half of one is a key nothing can read, and
the previous one is gone.
"""
import errno
import os
import stat
from pathlib import Path

import pytest

from services.file_regen_service import mirror_private_key

KEY = b'-----BEGIN PRIVATE KEY-----\nrestored\n-----END PRIVATE KEY-----\n'
PREVIOUS = b'-----BEGIN PRIVATE KEY-----\nprevious\n-----END PRIVATE KEY-----\n'


@pytest.fixture
def mirrors_enabled(monkeypatch):
    """Mirroring only happens while new values are stored in the clear."""
    from security import encryption

    monkeypatch.setattr(
        type(encryption.key_encryption), 'is_encrypting',
        property(lambda self: False))


def _mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


class TestTheMirrorIsWrittenWhole:
    def test_a_new_mirror_is_written_private(self, tmp_path, mirrors_enabled):
        destination = tmp_path / 'keys' / 'ca-1.key'

        assert mirror_private_key(destination, KEY, context='CA 1') is True
        assert destination.read_bytes() == KEY
        assert _mode(destination) == 0o600

    def test_an_existing_mirror_is_replaced(self, tmp_path, mirrors_enabled):
        destination = tmp_path / 'ca-1.key'
        destination.write_bytes(PREVIOUS)

        assert mirror_private_key(destination, KEY, context='CA 1') is True
        assert destination.read_bytes() == KEY


class TestAFailedMirrorKeepsThePreviousOne:
    def test_a_full_disk_does_not_destroy_what_was_there(
            self, tmp_path, mirrors_enabled, monkeypatch):
        destination = tmp_path / 'ca-1.key'
        destination.write_bytes(PREVIOUS)

        def no_space(fd):
            raise OSError(errno.ENOSPC, 'No space left on device')

        # fsync is where a full disk reports itself: the buffered write can
        # succeed and the data never reach the platter.
        monkeypatch.setattr(os, 'fsync', no_space)
        monkeypatch.setattr(
            os, 'replace',
            lambda *args, **kwargs: pytest.fail('the mirror was published'))

        assert mirror_private_key(destination, KEY, context='CA 1') is False
        assert destination.read_bytes() == PREVIOUS, \
            'the previous key was destroyed by a write that failed'

    def test_a_failed_rename_leaves_the_previous_content(
            self, tmp_path, mirrors_enabled, monkeypatch):
        destination = tmp_path / 'ca-1.key'
        destination.write_bytes(PREVIOUS)

        def denied(src, dst, *args, **kwargs):
            raise OSError(errno.EACCES, 'Permission denied')

        monkeypatch.setattr(os, 'replace', denied)

        assert mirror_private_key(destination, KEY, context='CA 1') is False
        assert destination.read_bytes() == PREVIOUS

    def test_no_temporary_file_is_left_behind(
            self, tmp_path, mirrors_enabled, monkeypatch):
        destination = tmp_path / 'ca-1.key'
        destination.write_bytes(PREVIOUS)

        def denied(src, dst, *args, **kwargs):
            raise OSError(errno.EACCES, 'Permission denied')

        monkeypatch.setattr(os, 'replace', denied)
        mirror_private_key(destination, KEY, context='CA 1')

        assert sorted(p.name for p in tmp_path.iterdir()) == ['ca-1.key']


class TestAStaleMirrorGoesWhenEncryptionIsOn:
    def test_the_mirror_is_removed(self, tmp_path, monkeypatch):
        from security import encryption

        monkeypatch.setattr(
            type(encryption.key_encryption), 'is_encrypting',
            property(lambda self: True))
        destination = tmp_path / 'ca-1.key'
        destination.write_bytes(PREVIOUS)

        assert mirror_private_key(destination, KEY, context='CA 1') is False
        assert not destination.exists()
