"""The journal the diagnostic bundle and the log viewer read holds the update watcher too.

ucm-watcher logs to the journal only: its lines, and the output of dpkg, apt-get and dnf
during an update, are read under its own unit. A fake journalctl answers per unit asked.
"""
import os

from services import log_bundle

FAKE = """#!/bin/sh
for a in "$@"; do
    case $prev in -u) echo "2026-11-26T10:00:00+00:00 host $a[1]: line of $a" ;; esac
    prev=$a
done
"""


def test_the_journal_includes_the_update_watcher(monkeypatch, tmp_path):
    fake = tmp_path / 'journalctl'
    fake.write_text(FAKE)
    fake.chmod(0o755)
    monkeypatch.setenv('PATH', f'{tmp_path}{os.pathsep}{os.environ.get("PATH", "")}')
    monkeypatch.setattr(log_bundle, 'is_docker', lambda: False)
    text = log_bundle.collect_journal().decode()
    assert 'host ucm[1]: line of ucm' in text, text
    assert 'host ucm-watcher[1]: line of ucm-watcher' in text, text
