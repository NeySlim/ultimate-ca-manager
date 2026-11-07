"""psycopg 3 is the only PostgreSQL driver: psycopg2 is not shipped, so code that imports it would fail."""
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
_PSYCOPG2 = re.compile(r'^\s*(import|from)\s+psycopg2\b|\bpsycopg2\.', re.MULTILINE)
_SKIPPED = {'venv', '.venv', 'node_modules', '__pycache__'}


def _sources():
    for path in BACKEND.rglob('*.py'):
        if not _SKIPPED.intersection(path.relative_to(BACKEND).parts) and path != Path(__file__):
            yield path


def test_nothing_imports_psycopg2():
    found = [f'{path.relative_to(BACKEND)}:{text[:match.start()].count(chr(10)) + 1}'
             for path in _sources()
             for text in [path.read_text(encoding='utf-8', errors='replace')]
             for match in _PSYCOPG2.finditer(text)]
    assert not found, found


def test_the_guard_sees_an_import():
    assert _PSYCOPG2.search('def f():\n    import psycopg2\n')
    assert _PSYCOPG2.search('from psycopg2 import errors\n')
    assert _PSYCOPG2.search('psycopg2.connect(url)\n')
    assert not _PSYCOPG2.search("URL = 'postgresql+psycopg2://u@h/d'\nimport psycopg\n")
