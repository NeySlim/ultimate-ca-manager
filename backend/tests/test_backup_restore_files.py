"""Restore: the files are staged, then published, or not written at all.

The restore used to write key mirrors and the HTTPS pair while the database
transaction was still open. Each test here pins one half of the fix: nothing
reaches a destination before the commit, and a publication that fails partway
puts back exactly what it overwrote.
"""
import errno
import os
import stat
from pathlib import Path

import pytest

from services.backup.restore.files import StagedFiles


def _mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


class TestStagingTouchesNothing:
    """Staging happens while the transaction can still roll back, so a
    destination must look untouched until publication."""

    def test_a_staged_file_is_not_at_its_destination(self, tmp_path):
        destination = tmp_path / 'keys' / 'ca-1.key'

        with StagedFiles(base_dir=tmp_path / 'staging') as staged:
            staged_path = staged.stage(destination, b'staged key')

            assert not destination.exists()
            assert staged_path.read_bytes() == b'staged key'
            assert staged.destinations == [destination]

    def test_the_staging_directory_is_private_and_created_on_demand(self, tmp_path):
        staged = StagedFiles(base_dir=tmp_path / 'staging')
        try:
            assert staged.staging_dir is None

            staged.stage(tmp_path / 'ca.key', b'key')

            assert staged.staging_dir is not None
            assert _mode(staged.staging_dir) == 0o700
            assert _mode(next(staged.staging_dir.iterdir())) == 0o600
        finally:
            staged.discard()


class TestPublicationWritesEverything:
    def test_publish_writes_each_destination_with_its_mode(self, tmp_path):
        key = tmp_path / 'private' / 'ca-1.key'
        cert = tmp_path / 'certs' / 'ca-1.crt'

        # `__exit__` keeps the staging on purpose when the block succeeds, so
        # that a commit failing afterwards can still undo the publication. The
        # caller discards it once the commit is through, and so does this test:
        # staged content is key material in the clear.
        with StagedFiles(base_dir=tmp_path / 'staging') as staged:
            staged.stage(key, b'-----BEGIN PRIVATE KEY-----\n')
            staged.stage(cert, b'-----BEGIN CERTIFICATE-----\n', mode=0o644)
            published = staged.publish()
            staged.discard()

        assert published == [key, cert]
        assert key.read_bytes() == b'-----BEGIN PRIVATE KEY-----\n'
        assert cert.read_bytes() == b'-----BEGIN CERTIFICATE-----\n'
        assert _mode(key) == 0o600
        assert _mode(cert) == 0o644

    def test_publishing_replaces_an_existing_destination(self, tmp_path):
        destination = tmp_path / 'https.key'
        destination.write_bytes(b'old key')

        with StagedFiles(base_dir=tmp_path / 'staging') as staged:
            staged.stage(destination, b'restored key')
            staged.publish()
            staged.discard()

        assert destination.read_bytes() == b'restored key'
        assert _mode(destination) == 0o600

    def test_the_staging_survives_publication_until_discarded(self, tmp_path):
        """Publication happens before the database commit, so what it needs to
        undo itself has to outlive it: the caller discards once the commit is
        through."""
        staged = StagedFiles(base_dir=tmp_path / 'staging')
        staged.stage(tmp_path / 'ca.key', b'key')
        staging_dir = staged.staging_dir

        staged.publish()
        assert staging_dir.exists(), 'the staging is needed to unpublish'

        staged.discard()
        assert not staging_dir.exists()
        assert staged.staging_dir is None


class TestPublicationCanBeUndone:
    def test_unpublish_puts_the_destinations_back(self, tmp_path):
        """A commit that fails after publication must not leave files
        describing a restore that did not happen."""
        destination = tmp_path / 'https_cert.pem'
        destination.write_bytes(b'the certificate in use')

        staged = StagedFiles(base_dir=tmp_path / 'staging')
        staged.stage(destination, b'the certificate from the archive')
        staged.publish()
        assert destination.read_bytes() == b'the certificate from the archive'

        staged.unpublish()
        assert destination.read_bytes() == b'the certificate in use'
        staged.discard()


class TestFailedPublicationCompensates:
    """Publication happens with the database work done but not yet committed,
    so a failure partway must not leave the files of two different states side
    by side: what it overwrote goes back, and the caller rolls the database
    back with it."""

    def _fail_on(self, monkeypatch, target):
        real_replace = os.replace

        def replace(src, dst, *args, **kwargs):
            if Path(dst) == target:
                raise OSError(errno.EIO, 'replace failed')
            return real_replace(src, dst, *args, **kwargs)

        monkeypatch.setattr(os, 'replace', replace)

    def test_already_published_files_get_their_previous_content_back(
            self, tmp_path, monkeypatch):
        first = tmp_path / 'ca-1.key'
        second = tmp_path / 'ca-2.key'
        first.write_bytes(b'previous first')
        second.write_bytes(b'previous second')
        previous_mode = _mode(first)
        self._fail_on(monkeypatch, second)

        staged = StagedFiles(base_dir=tmp_path / 'staging')
        staged.stage(first, b'restored first')
        staged.stage(second, b'restored second')

        with pytest.raises(OSError):
            staged.publish()

        assert first.read_bytes() == b'previous first'
        assert second.read_bytes() == b'previous second'
        # The file is put back as it was found, mode included: the restore
        # never owned it.
        assert _mode(first) == previous_mode
        staged.discard()

    def test_a_destination_that_did_not_exist_does_not_exist_after(
            self, tmp_path, monkeypatch):
        created = tmp_path / 'new' / 'ca-1.key'
        second = tmp_path / 'new' / 'ca-2.key'
        self._fail_on(monkeypatch, second)

        staged = StagedFiles(base_dir=tmp_path / 'staging')
        staged.stage(created, b'restored first')
        staged.stage(second, b'restored second')

        with pytest.raises(OSError):
            staged.publish()

        assert not created.exists()
        assert not second.exists()
        staged.discard()

    def test_no_temporary_file_is_left_in_the_destination_directory(
            self, tmp_path, monkeypatch):
        first = tmp_path / 'ca-1.key'
        second = tmp_path / 'ca-2.key'
        first.write_bytes(b'previous first')
        self._fail_on(monkeypatch, second)

        staged = StagedFiles(base_dir=tmp_path / 'staging')
        staged.stage(first, b'restored first')
        staged.stage(second, b'restored second')

        with pytest.raises(OSError):
            staged.publish()
        staged.discard()

        assert sorted(p.name for p in tmp_path.iterdir()) == [
            'ca-1.key', 'staging']


class TestDiscardLeavesNothing:
    def test_discard_publishes_nothing_and_removes_the_staging(self, tmp_path):
        key = tmp_path / 'ca.key'
        cert = tmp_path / 'ca.crt'

        staged = StagedFiles(base_dir=tmp_path / 'staging')
        staged.stage(key, b'key')
        staged.stage(cert, b'cert')
        staging_dir = staged.staging_dir

        staged.discard()

        assert not key.exists()
        assert not cert.exists()
        assert not staging_dir.exists()
        assert staged.staging_dir is None
        assert staged.destinations == []

    def test_the_context_manager_discards_when_the_block_raises(self, tmp_path):
        destination = tmp_path / 'ca.key'
        destination.write_bytes(b'untouched')
        staging_dir = None

        with pytest.raises(RuntimeError):
            with StagedFiles(base_dir=tmp_path / 'staging') as staged:
                staged.stage(destination, b'restored')
                staging_dir = staged.staging_dir
                raise RuntimeError('the transaction failed')

        assert destination.read_bytes() == b'untouched'
        assert not staging_dir.exists()


class _CountingPath(type(Path())):
    """A path that counts equality tests, the cost of finding a destination."""

    comparisons = 0

    def __eq__(self, other):
        type(self).comparisons += 1
        return super().__eq__(other)

    __hash__ = type(Path()).__hash__


class TestStagingCostIsLinear:
    """A restore stages one file per key mirror; finding an earlier entry for
    a destination must not walk every entry staged before it."""

    @staticmethod
    def _comparisons(monkeypatch, tmp_path, count):
        import services.backup.restore.files as files
        monkeypatch.setattr(files, 'Path', _CountingPath)
        _CountingPath.comparisons = 0
        staged = StagedFiles(base_dir=tmp_path / f'staging{count}')
        try:
            for index in range(count):
                staged.stage(tmp_path / f'k{index}.key', b'k')
                staged.stage_removal(tmp_path / f'gone{index}.key')
            return _CountingPath.comparisons
        finally:
            staged.discard()

    def test_comparisons_do_not_grow_with_the_square(self, monkeypatch, tmp_path):
        small = self._comparisons(monkeypatch, tmp_path, 100)
        large = self._comparisons(monkeypatch, tmp_path, 400)
        # Quadratic staging makes this ratio about 16; linear keeps it near 4.
        assert large <= 5 * max(small, 1)
        assert large <= 4 * 400

    def test_restaging_replaces_and_keeps_the_order(self, tmp_path):
        first, second = tmp_path / 'a.key', tmp_path / 'b.key'
        with StagedFiles(base_dir=tmp_path / 'staging') as staged:
            path_one = staged.stage(first, b'one')
            staged.stage(second, b'two')
            staged.stage_removal(first)
            assert staged.stage(first, b'again') == path_one
            assert staged.destinations == [first, second]
            assert path_one.read_bytes() == b'again'
            staged.publish()
            staged.discard()
        assert first.read_bytes() == b'again'
        assert second.read_bytes() == b'two'

    def test_a_removal_staged_first_gets_a_staging_path_when_restaged(self, tmp_path):
        gone, other = tmp_path / 'gone.key', tmp_path / 'other.key'
        gone.write_bytes(b'old')
        with StagedFiles(base_dir=tmp_path / 'staging') as staged:
            staged.stage_removal(gone)
            staged.stage(other, b'o')
            path = staged.stage(gone, b'new')
            assert path.name.startswith('0000_')
            staged.publish()
            staged.discard()
        assert gone.read_bytes() == b'new'
