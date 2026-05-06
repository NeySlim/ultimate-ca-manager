#!/usr/bin/env python3
"""
Smoke import : importe tous les modules backend pour détecter les NameError
et ImportError au chargement (ce que les tests pytest ne couvrent pas tant que
le module concerné n'est pas exercé par un test).

Exit code 1 si au moins un module échoue à l'import.

Note : les modules entry-point (app.py, wsgi.py, gunicorn_*.py) sont skippés
car leur import déclenche le démarrage de Flask + DB.
"""
import importlib
import pathlib
import sys
import os

BACKEND = pathlib.Path(__file__).resolve().parent.parent
EXCLUDE_DIRS = {'__pycache__', 'venv', '.venv', 'migrations', 'tests', 'scripts'}
EXCLUDE_FILES = {'app.py', 'wsgi.py', 'gunicorn_config.py', 'workers.py',
                 'reset_admin.py', 'gen_keys.py', 'init_db.py'}

# Travaille depuis backend/ pour que les imports relatifs marchent
os.chdir(BACKEND)
sys.path.insert(0, str(BACKEND))

errors = []
checked = 0

for py in pathlib.Path('.').rglob('*.py'):
    if any(p in EXCLUDE_DIRS for p in py.parts):
        continue
    if py.name in EXCLUDE_FILES:
        continue

    mod = str(py.with_suffix('')).replace('/', '.')
    if mod.endswith('.__init__'):
        mod = mod[:-9]

    try:
        importlib.import_module(mod)
        checked += 1
    except Exception as e:
        errors.append(f'{mod}: {type(e).__name__}: {e}')

if errors:
    print(f'{len(errors)} module(s) failed to import (out of {checked + len(errors)} attempted):',
          file=sys.stderr)
    for e in errors:
        print(f'  {e}', file=sys.stderr)
    sys.exit(1)

print(f'OK: {checked} backend modules imported cleanly')
