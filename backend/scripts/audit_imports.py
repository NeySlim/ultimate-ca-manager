#!/usr/bin/env python3
"""Import smoke check, always run with pytest's isolated configuration."""
import importlib
import pathlib
import subprocess
import sys

BACKEND = pathlib.Path(__file__).resolve().parent.parent
EXCLUDE_DIRS = {'__pycache__', 'venv', '.venv', 'migrations', 'tests', 'scripts'}
EXCLUDE_FILES = {'app.py', 'wsgi.py', 'gunicorn_config.py', 'workers.py',
                 'reset_admin.py', 'gen_keys.py', 'init_db.py'}


def audit_imports():
    """Return import failures; pytest must have installed its safe environment first."""
    if 'tests.conftest' not in sys.modules and 'conftest' not in sys.modules:
        raise RuntimeError('Backend import checks must run under pytest')
    errors = []
    for py in BACKEND.rglob('*.py'):
        relative = py.relative_to(BACKEND)
        if any(part in EXCLUDE_DIRS for part in relative.parts) or py.name in EXCLUDE_FILES:
            continue
        mod = '.'.join(relative.with_suffix('').parts)
        if mod.endswith('.__init__'):
            mod = mod[:-9]
        try:
            importlib.import_module(mod)
        except Exception as exc:
            errors.append(f'{mod}: {type(exc).__name__}: {exc}')
    return errors


if __name__ == '__main__':
    raise SystemExit(subprocess.call([
        sys.executable, '-m', 'pytest', 'tests/test_backend_import_smoke.py',
        '-q', '-p', 'no:cacheprovider',
    ], cwd=BACKEND))
