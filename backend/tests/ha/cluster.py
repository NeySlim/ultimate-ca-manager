"""Real UCM nodes (gunicorn, two or three) in HA mode on one PostgreSQL schema.

Every node gets an environment built here and nothing else: its own DATA_DIR,
UCM_CONFIG_DIR, logs and port under the bench directory, its own database URL
(application_name = schema_node), the shared SECRET_KEY, KEY_ENCRYPTION_KEY and
UCM_DB_ENCRYPTION_KEY.
The guard on its PYTHONPATH stops a node that touches an installation path.
"""
import json
import os
import re
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BACKEND = Path(__file__).resolve().parents[2]
GUARD_DIR = Path(__file__).resolve().parent / 'guard'
PG_URL = os.environ.get('UCM_TEST_PG_URL', '')
ENABLED = os.environ.get('UCM_TEST_HA') == '1' and bool(PG_URL)
SCHEMA_PREFIX = 'ucm_ha_'
# Startup waits on another node's migrations for at most BOOT_LOCK_TIMEOUT_SECONDS
READY_TIMEOUT = 240
STOP_TIMEOUT = 45
POLL = 0.25
NODE_NAMES = ('node-a', 'node-b', 'node-c')


def free_port() -> int:
    return free_ports(1)[0]


def free_ports(count) -> list:
    """`count` distinct free ports: every probe socket stays bound until all are drawn,
    since a port released is free to be handed out again."""
    socks = []
    try:
        for _ in range(count):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            socks.append(sock)
            sock.bind(('127.0.0.1', 0))
        return [sock.getsockname()[1] for sock in socks]
    finally:
        for sock in socks:
            sock.close()


def wait_until(predicate, timeout, what):
    """Poll `predicate` until it returns a truthy value or `timeout` seconds pass."""
    deadline = time.monotonic() + timeout
    pause = threading.Event()
    last = None
    while True:
        try:
            last = predicate()
        except requests.RequestException as e:
            last = e
            if time.monotonic() >= deadline:
                break
        else:
            if last:
                return last
            if time.monotonic() >= deadline:
                break
        pause.wait(POLL)
    raise AssertionError(f'{what}: not reached within {timeout}s (last: {last!r})')


def pg_connect(application_name, **overrides):
    import psycopg
    return psycopg.connect(PG_URL, application_name=application_name, autocommit=True, **overrides)


def group_pids(pgid) -> set:
    """Live processes of a process group, read from /proc."""
    pids = set()
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / 'stat').read_text().rsplit(')', 1)[1].split()
        except OSError:
            continue
        # fields[0] is the state, fields[2] the process group; a zombie is gone
        if int(fields[2]) == pgid and fields[0] != 'Z':
            pids.add(int(entry.name))
    return pids


class Node:
    def __init__(self, name, root: Path, shared_env: dict, port=None):
        self.name = name
        self.root = root
        self.port = port or free_port()
        self.data_dir = root / 'data'
        self.config_dir = root / 'config'
        self.console = root / 'console.log'
        self.app_log = root / 'logs' / 'ucm.log'
        self.guard_file = root / 'guard.log'
        for path in (self.data_dir, self.config_dir, self.app_log.parent, root / 'tmp'):
            path.mkdir(parents=True, exist_ok=True)
        self.env = {
            **shared_env,
            'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
            'HOME': str(root),
            'TMPDIR': str(root / 'tmp'),
            'LC_ALL': 'C.UTF-8',
            'PYTHONPATH': os.pathsep.join([str(GUARD_DIR), str(BACKEND)]),
            'PYTHONDONTWRITEBYTECODE': '1',
            'UCM_HA_GUARD_FILE': str(self.guard_file),
            'UCM_NODE_ID': name,
            'UCM_CONFIG_DIR': str(self.config_dir),
            'UCM_BASE_PATH': str(root),
            'DATA_DIR': str(self.data_dir),
            'HOST': '127.0.0.1',
            'HTTPS_PORT': str(self.port),
            'HTTP_PROTOCOL_PORT': '0',
            'HTTP_REDIRECT': 'false',
            'UCM_LOG_FILE': str(self.app_log),
            'UCM_LOG_DIR': str(self.app_log.parent),
            'ACCESS_LOG': str(root / 'logs' / 'access.log'),
            'ERROR_LOG': str(root / 'logs' / 'error.log'),
        }
        self.proc = None
        self.sessions = []
        self.http = self.session()

    def session(self):
        """An HTTP session closed before the node stops: an open keep-alive delays a graceful stop."""
        http = requests.Session()
        http.verify = False
        self.sessions.append(http)
        return http

    @property
    def base(self):
        return f'https://127.0.0.1:{self.port}'

    def url(self, path):
        return self.base + path

    def start(self):
        out = open(self.console, 'ab')
        try:
            self.proc = subprocess.Popen(
                [sys.executable, '-m', 'gunicorn', '-c', 'gunicorn_config.py', 'wsgi:app'],
                cwd=BACKEND, env=self.env, stdin=subprocess.DEVNULL, stdout=out,
                stderr=subprocess.STDOUT, start_new_session=True)
        finally:
            out.close()

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def ready(self):
        if not self.alive():
            raise AssertionError(f'node {self.name} exited ({self.proc.returncode})')
        try:
            r = self.http.get(self.url('/health/ready'), timeout=5)
        except requests.ConnectionError:
            return None
        if r.status_code != 200:
            return None
        report = r.json()
        if report.get('node_id', self.name) != self.name:
            raise AssertionError(f'{self.name} at {self.base} answered by {report["node_id"]}: {report}')
        return report

    def health(self) -> dict:
        r = self.http.get(self.url('/health'), timeout=10)
        r.raise_for_status()
        report = r.json()
        # Another node's process listening on this node's address must not pass for this node
        if report.get('node_id') != self.name:
            raise AssertionError(f'{self.name} at {self.base} answered by {report.get("node_id")}: {report}')
        return report

    def pids(self) -> set:
        return group_pids(self.proc.pid) if self.proc is not None else set()

    def _signal(self, signum):
        try:
            os.killpg(self.proc.pid, signum)
        except ProcessLookupError:
            pass

    def kill(self):
        """Every process of the node at once, as a crash would."""
        if self.proc is None:
            return
        self._signal(signal.SIGKILL)
        self.proc.wait(timeout=STOP_TIMEOUT)
        wait_until(lambda: not self.pids(), STOP_TIMEOUT, f'node {self.name} processes gone')

    def terminate(self):
        for http in self.sessions:
            http.close()
        if self.proc is not None and self.proc.poll() is None:
            self._signal(signal.SIGTERM)

    def stop(self):
        """SIGTERM to the master, then SIGKILL to the group as a last resort."""
        if self.proc is None:
            return
        self.terminate()
        if self.proc.poll() is None:
            try:
                self.proc.wait(timeout=STOP_TIMEOUT)
            except subprocess.TimeoutExpired:
                pass
        try:
            wait_until(lambda: not self.pids(), 10, f'node {self.name} processes gone')
        except AssertionError:
            self._signal(signal.SIGKILL)
            self.proc.wait(timeout=STOP_TIMEOUT)
            wait_until(lambda: not self.pids(), STOP_TIMEOUT, f'node {self.name} processes gone')

    def log_text(self) -> str:
        parts = []
        for path in (self.console, self.app_log, self.guard_file):
            if path.exists():
                parts.append(f'--- {path.name} ---\n' + path.read_text(errors='replace'))
        return '\n'.join(parts)

    def app_log_text(self) -> str:
        return self.app_log.read_text(errors='replace') if self.app_log.exists() else ''

    def guard_hits(self) -> str:
        return self.guard_file.read_text() if self.guard_file.exists() else ''


class Cluster:
    """Nodes A and B (and C), on a schema created here and dropped by close()."""

    def __init__(self, root: Path, names=NODE_NAMES[:2]):
        self.schema = f'{SCHEMA_PREFIX}{os.getpid()}_{secrets.token_hex(3)}'
        self.root = root
        self._admin = None
        self.password = f'Ha-{secrets.token_hex(8)}-9z'
        from cryptography.fernet import Fernet
        shared = {
            'SECRET_KEY': secrets.token_hex(32),
            'KEY_ENCRYPTION_KEY': Fernet.generate_key().decode(),
            'UCM_DB_ENCRYPTION_KEY': Fernet.generate_key().decode(),
            'UCM_HA': '1',
            'INITIAL_ADMIN_PASSWORD': self.password,
            'FQDN': 'ucm-ha.test',
        }
        self.nodes = [Node(name, root / name, {**shared, 'DATABASE_URL': self.database_url(name)}, port)
                      for name, port in zip(names, free_ports(len(names)))]

    def app_name(self, node_name):
        """A node's application_name: it names the node in pg_stat_activity whatever client
        address PostgreSQL sees (a published port shows the proxy's), and starts with the schema."""
        return f'{self.schema}_{node_name}'

    def app_names(self) -> list:
        return [self.app_name(node.name) for node in self.nodes]

    def database_url(self, node_name):
        separator = '&' if '?' in PG_URL else '?'
        return (f'{PG_URL}{separator}options={quote(f"-csearch_path={self.schema}")}'
                f'&application_name={quote(self.app_name(node_name))}')

    def __getitem__(self, index):
        return self.nodes[index]

    def create_schema(self):
        self._admin = pg_connect(f'{self.schema}_admin')
        with self._admin.cursor() as cur:
            _sweep_abandoned(cur)
            cur.execute(f'CREATE SCHEMA "{self.schema}"')

    def start(self):
        """Every node at once on the empty schema, then a bounded wait for readiness."""
        for node in self.nodes:
            node.start()
        for node in self.nodes:
            wait_until(node.ready, READY_TIMEOUT, f'node {node.name} ready')

    def sql(self, statement, params=None):
        with self._admin.cursor() as cur:
            cur.execute(f'SET search_path TO "{self.schema}"')
            cur.execute(statement, params)
            return cur.fetchall() if cur.description else None

    def backends(self) -> list:
        """The nodes' database sessions: dicts of pid, node (a name, or None), wait_event_type, query."""
        rows = self.sql('SELECT pid, application_name, wait_event_type, query FROM pg_stat_activity '
                        'WHERE application_name = ANY(%s)', (self.app_names(),))
        owners = {self.app_name(node.name): node.name for node in self.nodes}
        return [{'pid': pid, 'node': owners.get(app), 'wait': wait, 'query': query or ''}
                for pid, app, wait, query in rows]

    def waiting_on_lock(self, node, needle='') -> int:
        """Sessions of `node` blocked on a lock, in a statement that contains `needle`."""
        return sum(1 for b in self.backends()
                   if b['node'] == node.name and b['wait'] == 'Lock' and needle in b['query'])

    @contextmanager
    def holding(self, statement, params=None):
        """Run `statement` in a transaction of its own and keep its locks until the block ends:
        the instant a node reaches them is then observable in pg_stat_activity."""
        with pg_connect(f'{self.schema}_hold') as conn:
            conn.autocommit = False
            conn.execute(f'SET search_path TO "{self.schema}"')
            conn.execute(statement, params)
            try:
                yield conn
            finally:
                conn.rollback()

    @contextmanager
    def database_closed(self):
        """New connections to the bench's database refused until the block ends; PostgreSQL
        changes that from another database only, its owner may (here the maintenance one)."""
        (database,), = self.sql('SELECT current_database()')
        with pg_connect(f'{self.schema}_gate', dbname='postgres') as gate:
            gate.execute(f'ALTER DATABASE "{database}" WITH ALLOW_CONNECTIONS false')
            try:
                yield
            finally:
                gate.execute(f'ALTER DATABASE "{database}" WITH ALLOW_CONNECTIONS true')

    def schema_exists(self) -> bool:
        with pg_connect(f'{self.schema}_check') as conn:
            return conn.execute('SELECT 1 FROM pg_namespace WHERE nspname = %s',
                                (self.schema,)).fetchone() is not None

    def sessions_left(self) -> int:
        with pg_connect(f'{self.schema}_check') as conn:
            return conn.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE application_name = ANY(%s)",
                (self.app_names(),)).fetchone()[0]

    def guard_hits(self) -> str:
        return ''.join(f'{n.name}: {hit}' for n in self.nodes for hit in n.guard_hits().splitlines(True))

    def logs(self) -> dict:
        return {n.name: n.log_text() for n in self.nodes}

    def close(self):
        errors = []
        for node in self.nodes:
            node.terminate()
        for node in self.nodes:
            try:
                node.stop()
            except Exception as e:  # keep stopping the others, then drop the schema
                errors.append(f'{node.name}: {e}')
        if self._admin is not None:
            with self._admin.cursor() as cur:
                cur.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity '
                            'WHERE application_name = ANY(%s) AND pid <> pg_backend_pid()',
                            (self.app_names(),))
                cur.execute(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE')
            self._admin.close()
            self._admin = None
        if errors:
            raise AssertionError('; '.join(errors))


def _sweep_abandoned(cur):
    """Drop the schemas of benches that were killed: no session carries their name."""
    cur.execute("""
        SELECT n.nspname FROM pg_namespace n
        WHERE n.nspname ~ %s AND pg_get_userbyid(n.nspowner) = current_user
          AND NOT EXISTS (SELECT 1 FROM pg_stat_activity a
                          WHERE a.application_name LIKE n.nspname || '%%')
    """, (f'^{SCHEMA_PREFIX}[0-9]+_[0-9a-f]{{6}}$',))
    for (name,) in cur.fetchall():
        cur.execute(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')


class Client:
    """A logged-in API client bound to one node; `on(node)` reuses its cookie elsewhere."""

    def __init__(self, node, cookies=None, csrf=None):
        self.node = node
        self.http = node.session()
        if cookies:
            self.http.cookies.update(cookies)
        self.csrf = csrf

    @classmethod
    def login(cls, node, password, username='admin'):
        client = cls(node)
        r = client.http.post(node.url('/api/v2/auth/login'),
                             json={'username': username, 'password': password}, timeout=30)
        assert r.status_code == 200, f'login on {node.name}: {r.status_code} {r.text[:500]}'
        client.csrf = (r.json().get('data') or {}).get('csrf_token')
        return client

    def on(self, node):
        return Client(node, cookies=self.http.cookies.get_dict(), csrf=self.csrf)

    def _headers(self):
        return {'X-CSRF-Token': self.csrf} if self.csrf else {}

    def get(self, path, **kw):
        return self.http.get(self.node.url(path), timeout=60, **kw)

    def post(self, path, payload=None, **kw):
        return self.http.post(self.node.url(path), json=payload or {}, headers=self._headers(),
                              timeout=120, **kw)

    def patch(self, path, payload=None, **kw):
        return self.http.patch(self.node.url(path), json=payload or {}, headers=self._headers(),
                               timeout=120, **kw)


class _Answer:
    """The answer a restore route would have given, read back from its job."""

    def __init__(self, result):
        self.status_code = result['code']
        if result['code'] < 400:
            self._body = {'data': result.get('data'), 'message': result.get('message')}
        else:
            self._body = {'message': result.get('message'), 'code': result['code'],
                          **(result.get('problem') or {})}
        self.text = json.dumps(self._body)

    def json(self):
        return self._body


def restore_answer(client, node, name, content, password, admin_password, timeout=300):
    """POST a restore to ``node``; past the route's wait (202) follow its job, signing in again
    once the restore has revoked the session, and answer what the route would have."""
    r = client.http.post(node.url('/api/v2/system/restore'), headers=client._headers(),
                         files={'file': (name, content)}, data={'password': password},
                         timeout=timeout)
    if r.status_code != 202:
        return r
    location, reader = r.headers['Location'], client
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        seen = reader.http.get(node.url(location), timeout=60)
        if seen.status_code == 401:
            reader = Client.login(node, admin_password)
            continue
        assert seen.status_code == 200, seen.text[:500]
        job = seen.json()['data']
        if job['state'] in ('succeeded', 'failed', 'cancelled'):
            assert job['result'] is not None, job
            return _Answer(job['result'])
        time.sleep(1)
    raise AssertionError(f'restore job not final within {timeout}s')


TASK_LINE = re.compile(r"Task '([A-Za-z0-9_]+)' (?:completed|skipped|failed)")


def single_leader(nodes, settling=False):
    """The one node of `nodes` that every report names as leader, None while they disagree.

    `settling`: just after the lock changed hands. Each report reads its node's heartbeat
    flag, which follows the lock within a pass; reports read one after the other can then
    straddle the move, so two leaders mean "not yet" instead of failing."""
    reports = {node.name: node.health() for node in nodes}
    leaders = [name for name, r in reports.items() if r['leader'] is True]
    named = {r['cluster']['leader_node_id'] for r in reports.values()}
    if len(leaders) > 1:
        if settling:
            return None
        raise AssertionError(f'more than one leader: {reports}')
    if len(leaders) == 1 and named == set(leaders) \
            and all(r['leader'] is False for name, r in reports.items() if name != leaders[0]):
        return next(node for node in nodes if node.name == leaders[0])
    return None


def lock_acquisitions(node) -> int:
    """How many times this node's scheduler processes took the leader lock, restarts included."""
    return node.app_log_text().count('Scheduler lock acquired:')


def node_counts(*counts):
    """Run a module's tests on a cluster of each size (the `cluster` fixture's parameter)."""
    import pytest
    return pytest.mark.parametrize('cluster', counts, indirect=True,
                                   ids=[f'{n}-nodes' for n in counts])


def task_runs(text, name) -> int:
    """How many runs of task `name` a node's log records."""
    return sum(1 for m in TASK_LINE.finditer(text) if m.group(1) == name)


def create_ca(client, cn):
    r = client.post('/api/v2/cas', {
        'type': 'root', 'commonName': cn, 'organization': 'HA bench', 'country': 'US',
        'keyAlgo': 'RSA', 'keySize': 2048, 'validityYears': 5, 'hashAlgorithm': 'sha256'})
    assert r.status_code in (200, 201), f'create CA on {client.node.name}: {r.status_code} {r.text[:500]}'
    return r.json()['data']


def issue(client, ca_id, cn):
    r = client.post('/api/v2/certificates', {'cn': cn, 'ca_id': ca_id, 'validity_days': 30})
    assert r.status_code in (200, 201), f'issue on {client.node.name}: {r.status_code} {r.text[:500]}'
    return r.json()['data']
