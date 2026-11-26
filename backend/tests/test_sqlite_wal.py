"""SQLite runs in WAL: the application switches a new or an existing database at its first
connection, a migration snapshot holds the last commits as one self-contained file, and in the
gunicorn worker (gevent) a request waiting for another writer never stops the others."""
import json
import sqlite3
import subprocess
import sys
import textwrap

import pytest
from sqlalchemy.engine import make_url

from tests.test_initial_admin_password import BACKEND, _child_env

PASSWORD = 'Initial-Admin-Pass-9'

# The child boots the testing app on a file, as test_initial_admin_password does
_BOOT = '''
    import json, os, sys
    import dotenv
    dotenv.load_dotenv = lambda *a, **k: False
    from pathlib import Path
    from security import encryption
    encryption.MASTER_KEY_PATH = Path(os.environ['DATA_DIR']) / 'master.key'
    encryption.key_encryption.reload()
    from config import settings
    settings.TestingConfig.SQLALCHEMY_DATABASE_URI = os.environ['CHILD_DB_URI']
    from app import create_app
    app = create_app('testing')
'''

OPENED = textwrap.dedent(_BOOT + '''
    from models import db
    with app.app_context():
        out = {k: db.session.execute(db.text(f'PRAGMA {k}')).scalar()
               for k in ('journal_mode', 'synchronous', 'journal_size_limit')}
    print('RESULT ' + json.dumps(out), flush=True)
''')


def _database(tmp_path):
    path = tmp_path / 'data' / 'ucm.db'
    return path, {'CHILD_DB_URI': f'sqlite:///{path}', 'DATABASE_PATH': str(path),
                  'DATABASE_URL': ''}


def _child(script, tmp_path, timeout=240):
    path, database = _database(tmp_path)
    env = _child_env(database, tmp_path / 'data', {'INITIAL_ADMIN_PASSWORD': PASSWORD})
    out = subprocess.run([sys.executable, '-c', script], cwd=BACKEND, env=env, capture_output=True,
                         text=True, timeout=timeout)
    assert out.returncode == 0, (out.stdout + out.stderr)[-4000:]
    line = next(x for x in out.stdout.splitlines() if x.startswith('RESULT '))
    return json.loads(line[len('RESULT '):])


def _header_mode(path):
    """Bytes 18-19 of the file: 1 for a rollback journal, 2 for WAL."""
    return path.read_bytes()[18:20]


@pytest.mark.slow
def test_a_new_and_an_existing_delete_database_open_in_wal(tmp_path):
    path, _ = _database(tmp_path)
    opened = _child(OPENED, tmp_path)
    assert opened == {'journal_mode': 'wal', 'synchronous': 2, 'journal_size_limit': 64 * 1024 * 1024}
    assert _header_mode(path) == b'\2\2'
    # An installation that ran in journal_mode=delete: switched at its next start
    conn = sqlite3.connect(path)
    assert conn.execute('PRAGMA journal_mode=DELETE').fetchone()[0] == 'delete'
    users = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    conn.close()
    assert _header_mode(path) == b'\1\1' and users == 1
    assert _child(OPENED, tmp_path)['journal_mode'] == 'wal'
    assert _header_mode(path) == b'\2\2'
    conn = sqlite3.connect(path)
    assert conn.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 1
    assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    conn.close()


_COMMIT_AND_DIE = '''
import os, sqlite3, sys
c = sqlite3.connect(sys.argv[1])
c.execute("PRAGMA wal_autocheckpoint = 0")
c.execute("INSERT INTO t VALUES (?)", (sys.argv[2],))
c.commit()
os._exit(0)  # the commit stays in the -wal file, never checkpointed
'''


def wal_with_pending_commit(path, value='last'):
    """A WAL database whose last commit is only in its -wal file, as after a crash."""
    conn = sqlite3.connect(path)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('CREATE TABLE t (v TEXT)')
    conn.execute("INSERT INTO t VALUES ('first')")
    conn.commit()
    conn.close()
    subprocess.run([sys.executable, '-I', '-c', _COMMIT_AND_DIE, str(path), value], check=True)
    assert path.with_name(path.name + '-wal').stat().st_size > 0


def test_a_migration_snapshot_holds_the_last_commits_in_one_file(app, tmp_path):
    from services.database_admin.helpers import _dump_sqlite
    from services.database_admin.snapshot import _verify_sqlite
    source = tmp_path / 'live.db'
    wal_with_pending_commit(source)
    # A write in progress meanwhile: not committed, so not in the snapshot
    writer = sqlite3.connect(source, isolation_level=None)
    writer.execute('BEGIN IMMEDIATE')
    writer.execute("INSERT INTO t VALUES ('uncommitted')")
    snapshots = tmp_path / 'snapshots'
    snapshots.mkdir()
    target, reasons = snapshots / 'ucm-sqlite-test.db', []
    try:
        assert _dump_sqlite(make_url(f'sqlite:///{source}'), target, reasons, {}), reasons
    finally:
        writer.execute('ROLLBACK')
        writer.close()
    assert _header_mode(target) == b'\1\1'
    assert _verify_sqlite(target, {'t'}).startswith('quick_check ok')
    assert sorted(p.name for p in snapshots.iterdir()) == ['ucm-sqlite-test.db']
    conn = sqlite3.connect(target)
    assert sorted(v for (v,) in conn.execute('SELECT v FROM t')) == ['first', 'last']
    assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    conn.close()


_HOLDER = '''
import os, sqlite3, sys, time
c = sqlite3.connect(sys.argv[1], isolation_level=None)
c.execute("BEGIN IMMEDIATE")
c.execute("UPDATE users SET failed_logins = failed_logins")
open(sys.argv[3], "w").close()
time.sleep(float(sys.argv[2]))
c.execute("ROLLBACK")
'''

# The production worker: gevent, monkey-patched, one process serving every request
WORKER = textwrap.dedent('''
    from gevent import monkey
    monkey.patch_all()
''' + _BOOT + '''
    import subprocess, time, urllib.error, urllib.request
    import gevent
    from gevent.pywsgi import WSGIServer
    from utils.sqlite_wait import serve_web_worker
    serve_web_worker(app)
    server = WSGIServer(('127.0.0.1', 0), app, log=None)
    server.start()
    base = f'http://127.0.0.1:{server.server_port}'
    db_path = os.environ['DATABASE_PATH']

    def call(method, path, body=None):
        started = time.monotonic()
        req = urllib.request.Request(base + path, data=body, method=method,
                                     headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                status, headers = r.status, r.headers
        except urllib.error.HTTPError as e:
            status, headers = e.code, e.headers
        return {'status': status, 'retry_after': headers.get('Retry-After'),
                'took': time.monotonic() - started}

    def idle_gap(count=20):
        """The longest gap between two reads with no write waiting: what the host costs alone."""
        ticks = []
        for i in range(count):
            ticks.append(time.monotonic())
            call('GET', '/health/ready' if i % 2 else '/health/live')
            time.sleep(0.05)
        ticks.append(time.monotonic())
        return max(b - a for a, b in zip(ticks, ticks[1:]))

    def scenario(hold):
        idle = idle_gap()
        ready = db_path + '.held'
        holder = subprocess.Popen([sys.executable, '-I', '-c', sys.argv[1], db_path, str(hold), ready])
        while not os.path.exists(ready):
            time.sleep(0.01)
        login = json.dumps({'username': 'admin', 'password': 'Not-The-Password-1'}).encode()
        write = gevent.spawn(call, 'POST', '/api/v2/auth/login', login)
        # Reads all along the write's wait: a stopped worker shows as a gap between two of them
        reads, ticks = [], []
        while not write.ready():
            ticks.append(time.monotonic())
            reads.append(call('GET', '/health/ready' if len(reads) % 2 else '/health/live'))
            time.sleep(0.05)
        ticks.append(time.monotonic())
        gap = max(b - a for a, b in zip(ticks, ticks[1:]))
        result = {'write': write.get(), 'reads': reads, 'gap': gap, 'idle': idle, 'hold': hold}
        holder.wait()
        os.remove(ready)
        return result

    assert call('GET', '/health/ready')['status'] == 200
    print('RESULT ' + json.dumps({'short': scenario(2.0), 'long': scenario(8.0)}), flush=True)
''')


@pytest.fixture(scope='module')
def served(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp('gevent-worker')
    path, database = _database(tmp_path)
    env = _child_env(database, tmp_path / 'data', {'INITIAL_ADMIN_PASSWORD': PASSWORD})
    out = subprocess.run([sys.executable, '-c', WORKER, _HOLDER], cwd=BACKEND, env=env,
                         capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, (out.stdout + out.stderr)[-4000:]
    line = next(x for x in out.stdout.splitlines() if x.startswith('RESULT '))
    return json.loads(line[len('RESULT '):])


@pytest.mark.slow
@pytest.mark.parametrize('case', ['short', 'long'])
def test_the_worker_serves_reads_while_a_request_waits_for_another_writer(served, case):
    reads, gap, idle, hold = (served[case][k] for k in ('reads', 'gap', 'idle', 'hold'))
    assert len(reads) >= 10 and all(r['status'] == 200 for r in reads), reads
    # A worker stopped by the wait shows a gap as long as the hold (or the 5 s busy timeout);
    # a loaded host only stretches what it costs idle, measured in the same worker just before
    bound = min(hold / 2, max(0.5, 4 * idle))
    assert gap < bound and max(r['took'] for r in reads) < bound, \
        f'the worker stopped for {gap:.2f}s (bound {bound:.2f}s, idle {idle:.2f}s) while a write waited: {reads}'


@pytest.mark.slow
def test_the_waiting_write_goes_through_once_the_other_writer_ends(served):
    write = served['short']['write']
    assert write['status'] == 401, write  # a wrong password, counted once the lock is free
    assert 1.2 < write['took'] < 3.5, write


@pytest.mark.slow
def test_past_its_wait_the_write_answers_503_busy_with_retry_after(served):
    write = served['long']['write']
    assert write['status'] == 503 and write['retry_after'] == '5', write
    assert 4.5 < write['took'] < 7.5, write
