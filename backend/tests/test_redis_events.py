"""WebSocket events between processes through a real Redis server.

Two web processes and a scheduler-like process share one SQLite file and one Redis.
An event emitted by a request on A, or by the scheduler process, reaches a Socket.IO
client of A and one of B exactly once; the database relay stays off (no reader, no
publisher, no row in websocket_relay) and Redis carries one message per event.
"""
import json
import sqlite3
import subprocess
import sys
import threading
import time

import pytest
import requests

from tests.ha.cluster import free_port, wait_until
from tests.redis_support import BACKEND, guard_hits, needs_redis, sandbox_env

pytestmark = needs_redis

CHANNEL = 'ucm:session:socketio:0'
NODE = str(BACKEND / 'tests' / 'redis_event_node.py')


class Process:
    def __init__(self, root, role, database, redis_url, port=None):
        self.root, self.port = root, port
        self.log = open(root / 'console.log', 'ab')
        args = [sys.executable, NODE, role, database] + ([str(port)] if port else [])
        env = sandbox_env(root, REDIS_URL=redis_url, WEBSOCKET_ASYNC_MODE='threading',
                          HTTPS_PORT=port or 8443)
        self.proc = subprocess.Popen(args, cwd=BACKEND, env=env, start_new_session=True,
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE if not port else self.log,
                                     stderr=self.log, text=True)

    @property
    def base(self):
        return f'http://127.0.0.1:{self.port}'

    def state(self):
        try:
            r = requests.get(self.base + '/zz-node', timeout=2)
        except requests.RequestException:
            assert self.proc.poll() is None, self.console()
            return None
        return r.json() if r.status_code == 200 else None

    def console(self):
        self.log.flush()
        return (self.root / 'console.log').read_text(errors='replace')[-5000:] + guard_hits(self.root)

    def answer(self):
        """The scheduler process's next answer (its other output is the application's)."""
        for line in self.proc.stdout:
            if line.startswith('NODE '):
                return line[5:].strip()
        raise AssertionError(self.console())

    def stop(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(15)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(15)
        self.log.close()


class Browser:
    """A Socket.IO client (long polling) signed in with the admin's session cookie."""

    def __init__(self, node, cookie):
        import socketio
        self.events, self._lock = [], threading.Lock()
        self.sio = socketio.Client(reconnection=False)
        self.sio.on('event', self._record)
        self.sio.connect(node.base, headers={'Cookie': f'session={cookie}'}, transports=['polling'],
                         wait_timeout=20)

    def _record(self, payload):
        with self._lock:
            self.events.append(payload)

    def named(self, name):
        with self._lock:
            return [e for e in self.events if e.get('type') == 'ca.created' and e['data'].get('name') == name]

    def close(self):
        self.sio.disconnect()


class Published:
    """Every message published on the Socket.IO channel, as Redis delivers it."""

    def __init__(self, server):
        self.messages = []
        self.pubsub = server.client().pubsub()
        self.pubsub.subscribe(CHANNEL)
        self.pubsub.get_message(timeout=5)  # the subscription confirmation
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self):
        while not self._stop.is_set():
            message = self.pubsub.get_message(timeout=0.2)
            if message and message['type'] == 'message':
                self.messages.append(json.loads(message["data"]))

    def named(self, name):
        return [m for m in self.messages if m.get('method') == 'emit' and m.get('event') == 'event'
                and [d.get('data', {}).get('name') for d in m.get('data') or []] == [name]]

    def close(self):
        self._stop.set()
        self.thread.join(5)
        self.pubsub.close()


@pytest.fixture
def cluster(redis_server, tmp_path):
    redis_server.client().flushdb()
    database = f'sqlite:///{tmp_path / "shared.db"}'
    started = []
    try:
        for name in ('a', 'b'):
            (tmp_path / name).mkdir()
            node = Process(tmp_path / name, 'web', database, redis_server.url(), port=free_port())
            started.append(node)
            wait_until(node.state, 120, f'node {name} serving')
        (tmp_path / 's').mkdir()
        scheduler = Process(tmp_path / 's', 'scheduler', database, redis_server.url())
        started.append(scheduler)
        yield started[0], started[1], scheduler, tmp_path / 'shared.db'
    finally:
        for process in started:
            process.stop()
        redis_server.client().flushdb()


def _login(node):
    r = requests.post(node.base + '/api/v2/auth/login/password', timeout=30,
                      json={'username': 'admin', 'password': 'changeme123'})
    assert r.status_code == 200, r.text
    return r.cookies['session']


def test_an_event_reaches_a_client_of_each_web_process_once_through_redis(cluster, redis_server):
    node_a, node_b, scheduler, database = cluster
    first = json.loads(scheduler.answer())
    assert first == {'publisher': False, 'queue': True}, scheduler.console()
    assert node_a.state() == {'reader': False, 'queue': True}
    assert node_b.state() == {'reader': False, 'queue': True}

    cookie = _login(node_a)
    published = Published(redis_server)
    browsers = [Browser(node_a, cookie), Browser(node_b, cookie)]
    try:
        # Each web process listens on the channel once its first client is connected
        wait_until(lambda: dict(redis_server.client().pubsub_numsub(CHANNEL))[CHANNEL.encode()] >= 3,
                   20, 'both web processes subscribed')
        assert requests.post(node_a.base + '/zz-emit/from-a-request', timeout=10).status_code == 200
        scheduler.proc.stdin.write('from-the-scheduler\n')
        scheduler.proc.stdin.flush()
        assert scheduler.answer() == 'emitted'
        for name in ('from-a-request', 'from-the-scheduler'):
            for browser in browsers:
                wait_until(lambda b=browser, n=name: b.named(n), 20, f'{name} delivered')
        time.sleep(3)  # anything sent twice arrives meanwhile
        for name in ('from-a-request', 'from-the-scheduler'):
            assert [len(browser.named(name)) for browser in browsers] == [1, 1], name
            assert len(published.named(name)) == 1, name
    finally:
        for browser in browsers:
            browser.close()
        published.close()
    with sqlite3.connect(database) as conn:
        assert conn.execute('SELECT COUNT(*) FROM websocket_relay').fetchone()[0] == 0
