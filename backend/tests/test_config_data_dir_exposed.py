"""`app.config['DATA_DIR']` is the directory the data paths are built from.

Each case starts a fresh interpreter: `DATA_DIR` is read once, when
`config.settings` is imported, and the suite's own app has already done that.
"""
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent

_PROBE = textwrap.dedent("""
    import json, os, time
    from app import create_app
    from services.session_cleanup_task import SessionCleanupTask

    app = create_app('testing')
    sessions = os.path.join(os.environ['DATA_DIR'], 'sessions')
    os.makedirs(sessions, exist_ok=True)
    stale = os.path.join(sessions, 'stale-session')
    open(stale, 'w').close()
    old = time.time() - 30 * 86400
    os.utime(stale, (old, old))

    # No session store configured: the cleanup falls back on DATA_DIR.
    app.config['SESSION_FILE_DIR'] = None
    with app.app_context():
        SessionCleanupTask.execute()

    print(json.dumps({
        'data_dir': str(app.config['DATA_DIR']),
        'backup_dir': str(app.config['BACKUP_DIR']),
        'stale_left': os.path.exists(stale),
    }))
""")


def _start_app_with(data_dir, tmp_path):
    env = dict(os.environ)
    env['DATA_DIR'] = str(data_dir)
    env['DATABASE_PATH'] = str(tmp_path / 'probe.db')
    env['UCM_DATABASE_PATH'] = str(tmp_path / 'probe.db')
    result = subprocess.run([sys.executable, '-c', _PROBE], cwd=BACKEND, env=env,
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr[-2000:]
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_custom_data_dir_reaches_app_config(tmp_path):
    custom = tmp_path / 'custom' / 'path'
    custom.mkdir(parents=True)

    seen = _start_app_with(custom, tmp_path)

    assert seen['data_dir'] == str(custom)
    # Same value as the one the storage paths are derived from.
    assert seen['backup_dir'] == str(custom / 'backups')


def test_session_cleanup_uses_the_custom_data_dir(tmp_path):
    custom = tmp_path / 'elsewhere'
    custom.mkdir()

    seen = _start_app_with(custom, tmp_path)

    assert seen['stale_left'] is False

