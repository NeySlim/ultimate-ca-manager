"""download_update confines the package to DATA_DIR/updates."""
import logging
import os

import pytest

from services import updates


class _Resp:
    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size=8192):
        yield b'package-bytes'


@pytest.fixture
def env(monkeypatch, tmp_path):
    data = tmp_path / 'data'
    data.mkdir()
    calls = []

    def fake_get(*a, **k):
        calls.append(a)
        return _Resp()

    monkeypatch.setattr(updates, 'DATA_DIR', str(data))
    monkeypatch.setattr(updates.requests, 'get', fake_get)
    return data, calls, tmp_path


def _all_files(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob('*') if p.is_file())


class TestPathReduction:
    def test_traversal_lands_in_updates(self, env, caplog):
        data, _, tmp = env
        with caplog.at_level(logging.WARNING, logger='ucm.updates'):
            path = updates.download_update('http://x/p', '../../etc/cron.d/evil')
        assert path == str(data / 'updates' / 'evil')
        assert _all_files(tmp) == ['data/updates/evil']
        assert any(r.levelno == logging.WARNING for r in caplog.records)

    def test_absolute_path_lands_in_updates(self, env):
        data, _, tmp = env
        path = updates.download_update('http://x/p', '/etc/passwd')
        assert path == str(data / 'updates' / 'passwd')
        assert _all_files(tmp) == ['data/updates/passwd']

    @pytest.mark.parametrize('name', [
        'ucm_2.236_all.deb', 'ucm_2.223.rc1_all.deb',
        'ucm-2.242-1.fc43.noarch.rpm', 'ucm-el9-2.242-1.el9.noarch.rpm',
    ])
    def test_legit_names_unchanged_and_not_warned(self, env, caplog, name):
        data, _, _ = env
        with caplog.at_level(logging.WARNING, logger='ucm.updates'):
            path = updates.download_update('http://x/p', name)
        assert path == str(data / 'updates' / name)
        assert os.path.exists(path)
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


class TestRefusals:
    @pytest.mark.parametrize('name', ['', '.', '..', 'dir/', '../', '/', 'a/b/..', 'x\x00y'])
    def test_invalid_names_fail_before_network_and_disk(self, env, name):
        data, calls, tmp = env
        with pytest.raises(Exception, match='Invalid package name'):
            updates.download_update('http://x/p', name)
        assert calls == []
        assert _all_files(tmp) == []

    def test_symlink_escaping_updates_is_refused(self, env):
        data, calls, tmp = env
        outside = tmp / 'outside.deb'
        outside.write_bytes(b'keep')
        (data / 'updates').mkdir()
        (data / 'updates' / 'p.deb').symlink_to(outside)
        with pytest.raises(Exception, match='Invalid package name'):
            updates.download_update('http://x/p', 'p.deb')
        assert calls == []
        assert outside.read_bytes() == b'keep'
