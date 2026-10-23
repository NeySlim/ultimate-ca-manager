"""Every third-party GitHub Action is pinned to a full commit SHA."""
import pathlib
import re

WORKFLOWS = pathlib.Path(__file__).resolve().parents[2] / '.github' / 'workflows'
USES = re.compile(r'^\s*(?:-\s*)?uses:\s*(\S+)', re.M)


def test_actions_are_pinned_by_sha():
    files = sorted(WORKFLOWS.glob('*.yml'))
    assert files
    loose = [f'{f.name}: {ref}' for f in files for ref in USES.findall(f.read_text())
             if not ref.startswith('./') and not re.fullmatch(r'[\w.-]+/[\w./-]+@[0-9a-f]{40}', ref)]
    assert not loose, loose
