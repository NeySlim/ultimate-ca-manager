"""HA on PostgreSQL: two nodes see, download and prune one set of backup archives.

Node A and node B are the same application under two node ids and two archive
directories, on one database: whatever B lists or serves came through the database.
"""
import base64
import contextlib
import gc
import hashlib
import io
import json
import os
import resource
import secrets
import shutil
import threading
import tracemalloc
from contextlib import contextmanager
from datetime import timedelta

import pytest
from sqlalchemy import func, select, text

from config.settings import Config
from services.backup import container, schedule, shared_store, storage
from tests import pg_app_harness
from utils.datetime_utils import utc_now

pytestmark = pytest.mark.skipif(not pg_app_harness.ENABLED,
                                reason='needs UCM_TEST_APP_PG_URL (HA runs on PostgreSQL)')

PASSWORD = 'shared-store-pass-2026'
PREFIX = f'hd2-{secrets.token_hex(3)}'
# Archive size of the memory measurement; the report's figures used several hundred MB
MEASURED_MB = int(os.environ.get('UCM_TEST_BACKUP_STORE_MB', '48'))


def _tables():
    from models import BackupArchive, BackupArchiveChunk
    return BackupArchive.__table__, BackupArchiveChunk.__table__


def _count(app, table, **where):
    from models import db
    with app.app_context():
        query = select(func.count()).select_from(table)
        for column, value in where.items():
            query = query.where(table.c[column] == value)
        with db.engine.connect() as conn:
            return conn.execute(query).scalar()


@pytest.fixture
def nodes(app, monkeypatch, tmp_path):
    """HA mode; `on(name)` makes the code run as that node, with its own archive directory.

    Archives created by the test are dropped afterwards, chunks with them.
    """
    monkeypatch.setattr(Config, 'HA_MODE', True)
    dirs = {}

    @contextmanager
    def on(name):
        directory = dirs.setdefault(name, tmp_path / name)
        directory.mkdir(exist_ok=True)
        with monkeypatch.context() as m:
            m.setattr(Config, 'NODE_ID', f'{PREFIX}-{name}')
            m.setattr(Config, 'BACKUP_DIR', str(directory))
            yield directory
    on.dirs = dirs
    with app.app_context():
        before = {a['filename'] for a in shared_store.list_archives()}
    yield on
    with app.app_context():
        made = [a['filename'] for a in shared_store.list_archives() if a['filename'] not in before]
        if made:
            shared_store.delete_archives(made, wait=30)


def _payload(size):
    """An archive-like stream: incompressible bytes, as an encrypted container is."""
    seed = secrets.token_bytes(64)
    out, n = bytearray(), 0
    while len(out) < size:
        out += hashlib.sha512(seed + n.to_bytes(8, 'big')).digest()
        n += 1
    return bytes(out[:size])


def _on_disk(directory):
    return [p.name for p in directory.iterdir() if storage.is_archive_name(p.name)]


def _listing(client):
    r = client.get('/api/v2/system/backups?per_page=100')
    assert r.status_code == 200, r.data
    return json.loads(r.data)['data']


def _ours(items):
    return [i for i in items if i.get('node', '').startswith(PREFIX)]


# --- 1. The same list from every node --------------------------------------------------------

def test_an_archive_made_on_a_is_listed_the_same_on_b_with_its_node(app, auth_client, nodes):
    data = _payload(3 * shared_store.CHUNK_SIZE + 17)
    with app.app_context(), nodes('a') as dir_a:
        _path, name = storage.create_archive(data)
        assert not _on_disk(dir_a), 'HA writes no archive to the node disk'
        on_a = _listing(auth_client)
    with nodes('b'):
        on_b = _listing(auth_client)
        history = json.loads(auth_client.get('/api/v2/settings/backup/history?per_page=100').data)
    assert on_a == on_b
    assert on_b['meta']['storage'] == 'database' and 'disk_free' not in on_b['meta']
    (item,) = [i for i in _ours(on_b['items']) if i['filename'] == name]
    assert item['node'] == f'{PREFIX}-a'
    assert item['size_bytes'] == len(data)
    assert item['sha256'] == hashlib.sha256(data).hexdigest()
    assert item['created_at'].endswith('UTC')
    (row,) = [h for h in history['data'] if h['filename'] == name]
    assert (row['node'], row['size'], row['sha256']) == (item['node'], len(data), item['sha256'])
    with app.app_context(), nodes('b'):
        assert schedule.get_schedule()['last_archive'] == name


# --- 2. Downloadable from every node, byte for byte --------------------------------------------

def test_an_archive_made_on_a_downloads_from_b_after_a_is_gone(app, auth_client, nodes, server):
    data = _payload(2 * shared_store.CHUNK_SIZE + 5)
    with app.app_context(), nodes('a'):
        _path, name = storage.create_archive(data)
    shutil.rmtree(nodes.dirs['a'])
    with nodes('b'):
        for url in (f'/api/v2/system/backup/{name}/download',
                    f'/api/v2/settings/backup/{name}/download'):
            r = auth_client.get(url, environ_base=server)
            assert r.status_code == 200, r.data
            assert r.data == data
            assert r.headers['Content-Length'] == str(len(data))
            assert r.headers['Repr-Digest'] == (
                'sha-256=:' + base64.b64encode(hashlib.sha256(data).digest()).decode() + ':')
            assert 'attachment' in r.headers['Content-Disposition']
        assert auth_client.get('/api/v2/system/backup/ucm_backup_absent.ucmbkp/download').status_code == 404
        assert auth_client.get('/api/v2/system/backup/..%2Fx.ucmbkp/download').status_code in (400, 404)


def _checked_out(app):
    from models import db
    with app.app_context():
        return db.engine.pool.checkedout()


def test_a_head_request_gives_its_connection_back(app, auth_client, nodes, server):
    data = _payload(shared_store.CHUNK_SIZE + 9)
    with app.app_context(), nodes('a'):
        _path, name = storage.create_archive(data)
    before = _checked_out(app)
    with nodes('b'):
        r = auth_client.head(f'/api/v2/system/backup/{name}/download', environ_base=server)
        assert r.status_code == 200 and r.data == b''
        assert r.headers['Content-Length'] == str(len(data))
        r.close()
    gc.collect()
    assert _checked_out(app) == before


def test_a_download_closed_before_its_first_chunk_gives_its_connection_back(app, nodes):
    with app.app_context(), nodes('a'):
        _path, name = storage.create_archive(_payload(2 * shared_store.CHUNK_SIZE))
    before = _checked_out(app)
    with app.test_request_context(f'/api/v2/system/backup/{name}/download'):
        response = shared_store.download_response(name)
        assert _checked_out(app) == before
        response.close()
        assert _checked_out(app) == before
        del response


DOWNLOADS = ('/api/v2/system/backup/{}/download', '/api/v2/settings/backup/{}/download')


@pytest.fixture(params=['test-client', 'gunicorn'])
def server(request):
    """The environ a download meets: the test client's, or gunicorn's (its own wsgi.file_wrapper)."""
    if request.param == 'test-client':
        return {}
    from gunicorn.http.wsgi import FileWrapper
    return {'wsgi.file_wrapper': FileWrapper}


@contextmanager
def _chunk_reads(app):
    """The `seq` of every chunk read from the store while the block runs."""
    from sqlalchemy import event
    from models import db
    seen = []

    def record(_conn, _cursor, statement, parameters, _context, _many):
        if 'backup_archive_chunks' in statement and statement.lstrip().upper().startswith('SELECT'):
            params = parameters if isinstance(parameters, dict) else {}
            seen.extend(v for k, v in params.items() if k.startswith('seq'))
    with app.app_context():
        engine = db.engine
    event.listen(engine, 'before_cursor_execute', record)
    try:
        yield seen
    finally:
        event.remove(engine, 'before_cursor_execute', record)


def test_a_resumed_download_reads_from_its_chunk_on(app, auth_client, nodes, server):
    data = _payload(5 * shared_store.CHUNK_SIZE + 99)
    with app.app_context(), nodes('a'):
        _path, name = storage.create_archive(data)
    start = 3 * shared_store.CHUNK_SIZE + 10
    with nodes('b'), _chunk_reads(app) as seqs:
        r = auth_client.get(DOWNLOADS[0].format(name), headers={'Range': f'bytes={start}-'},
                            environ_base=server)
        assert r.status_code == 206 and r.data == data[start:]
        r.close()
    assert sorted(set(seqs)) == [3, 4, 5], seqs


@pytest.mark.parametrize('method, headers', [
    ('GET', {'Range': 'bytes=10-'}),
    ('HEAD', {'Range': 'bytes=10-'}),
    ('GET', {}),
])
def test_closing_an_unread_download_gives_its_connection_back(
        app, auth_client, nodes, server, method, headers):
    with app.app_context(), nodes('a'):
        _path, name = storage.create_archive(_payload(2 * shared_store.CHUNK_SIZE))
    before = _checked_out(app)
    with nodes('b'):
        r = auth_client.open(DOWNLOADS[0].format(name), method=method, headers=headers,
                             environ_base=server)
        assert r.status_code == (206 if headers else 200)
        r.close()  # no iteration and no garbage collection
    assert _checked_out(app) == before


@pytest.mark.parametrize('route', DOWNLOADS)
def test_an_interrupted_download_resumes_at_its_byte(app, auth_client, nodes, route, server):
    data = _payload(3 * shared_store.CHUNK_SIZE + 333)
    whole = hashlib.sha256(data)
    with app.app_context(), nodes('a'):
        _path, name = storage.create_archive(data)
    url, size, cut = route.format(name), len(data), shared_store.CHUNK_SIZE + 4321
    before = _checked_out(app)
    with nodes('b'):
        full = auth_client.get(url, environ_base=server)
        assert full.status_code == 200 and full.headers['Accept-Ranges'] == 'bytes'
        etag = full.headers['ETag']
        assert etag == f'"{whole.hexdigest()}"'
        first = auth_client.get(url, headers={'Range': f'bytes=0-{cut - 1}'}, environ_base=server)
        rest = auth_client.get(url, headers={'Range': f'bytes={cut}-', 'If-Range': etag},
                               environ_base=server)
    assert (first.status_code, rest.status_code) == (206, 206)
    assert first.headers['Content-Range'] == f'bytes 0-{cut - 1}/{size}'
    assert rest.headers['Content-Range'] == f'bytes {cut}-{size - 1}/{size}'
    assert rest.headers['Content-Length'] == str(size - cut)
    assert hashlib.sha256(first.data + rest.data).digest() == whole.digest()
    # Repr-Digest names the whole representation, whatever part is sent
    assert rest.headers['Repr-Digest'] == full.headers['Repr-Digest']
    for response in (full, first, rest):
        response.close()  # what the WSGI server does once it has sent the body
    gc.collect()
    assert _checked_out(app) == before


def test_a_download_honours_suffix_ranges_validators_and_refusals(app, auth_client, nodes, server):
    data = _payload(2 * shared_store.CHUNK_SIZE + 77)
    with app.app_context(), nodes('a'):
        _path, name = storage.create_archive(data)
    url, size = DOWNLOADS[0].format(name), len(data)
    etag = f'"{hashlib.sha256(data).hexdigest()}"'
    before = _checked_out(app)
    with nodes('b'):
        tail = auth_client.get(url, headers={'Range': 'bytes=-1000'}, environ_base=server)
        assert tail.status_code == 206 and tail.data == data[-1000:]
        assert tail.headers['Content-Range'] == f'bytes {size - 1000}-{size - 1}/{size}'
        refused = auth_client.get(url, headers={'Range': f'bytes={size}-'}, environ_base=server)
        assert refused.status_code == 416
        assert refused.headers['Content-Range'] == f'bytes */{size}'
        same = auth_client.get(url, headers={'If-None-Match': etag}, environ_base=server)
        assert same.status_code == 304 and same.data == b''
        # A changed representation, or several ranges: the whole archive
        changed = auth_client.get(url, headers={'Range': 'bytes=10-', 'If-Range': '"other"'},
                                  environ_base=server)
        assert changed.status_code == 200 and changed.data == data
        several = auth_client.get(url, headers={'Range': 'bytes=0-9,20-29'}, environ_base=server)
        assert several.status_code == 200 and several.data == data
    for response in (tail, refused, same, changed, several):
        response.close()  # what the WSGI server does once it has sent the body
    gc.collect()
    assert _checked_out(app) == before


@pytest.fixture
def short_idle_timeout(app, monkeypatch):
    """The store's connections under a server that ends a transaction idle for 300 ms."""
    from sqlalchemy import create_engine, event
    from models import db
    with app.app_context():
        engine = create_engine(db.engine.url, pool_size=2)

    @event.listens_for(engine, 'connect')
    def _short(dbapi_conn, _record):
        with dbapi_conn.cursor() as cur:
            cur.execute("SET idle_in_transaction_session_timeout = 300")
    monkeypatch.setattr(shared_store, '_engine', lambda: engine)
    yield engine
    engine.dispose()


def test_a_slow_write_and_a_slow_read_outlive_an_idle_transaction_timeout(
        app, nodes, short_idle_timeout):
    import time
    pieces = [_payload(shared_store.CHUNK_SIZE) for _ in range(2)]

    def slow():
        for piece in pieces:
            yield piece
            time.sleep(1)
    with app.app_context(), nodes('a'):
        _path, name = storage.create_archive(slow())
    with app.test_request_context(f'/api/v2/system/backup/{name}/download'):
        response = shared_store.download_response(name)
        got = bytearray()
        try:
            for part in response.response:
                got += part
                time.sleep(0.5)
        finally:
            response.close()
    assert bytes(got) == b''.join(pieces)


def test_the_restore_reader_streams_and_seeks_a_stored_archive(app, nodes):
    data = b'UCMB' + bytes([4]) + _payload(3 * shared_store.CHUNK_SIZE)
    with app.app_context(), nodes('a'):
        _path, name = storage.create_archive(data)
        with shared_store.open_archive(name) as reader:
            assert container.format_version_of(reader.read(container.HEADER_PREFIX_SIZE)) == 4
            reader.seek(shared_store.CHUNK_SIZE - 3)
            assert reader.read(10) == data[shared_store.CHUNK_SIZE - 3:shared_store.CHUNK_SIZE + 7]
            assert reader.seek(0, io.SEEK_END) == len(data)
            reader.seek(0)
            assert hashlib.sha256(reader.read()).digest() == hashlib.sha256(data).digest()
        assert shared_store.open_archive('ucm_backup_absent.ucmbkp') is None


def _in_transaction_on_chunks(app):
    """Other sessions of this role idle inside a transaction whose last query read chunks."""
    from models import db
    with app.app_context(), db.engine.connect() as conn:
        return conn.execute(text(
            "SELECT count(*) FROM pg_stat_activity WHERE pid <> pg_backend_pid() "
            "AND usename = current_user AND datname = current_database() "
            "AND state LIKE 'idle in transaction%' AND query LIKE '%backup_archive_chunks%'")).scalar()


@contextmanager
def _suspended_download(app, name, server=None):
    """A download that has sent its first chunk and waits for the client: yields (body, first)."""
    with app.test_request_context(f'/api/v2/system/backup/{name}/download',
                                  environ_base=server or {}):
        response = shared_store.download_response(name)
    body = iter(response.response)
    try:
        yield body, next(body)
    finally:
        response.close()


def test_a_suspended_download_holds_no_connection_and_no_transaction(app, nodes, server):
    data = _payload(3 * shared_store.CHUNK_SIZE)
    with app.app_context(), nodes('a'):
        _path, name = storage.create_archive(data)
    before = _checked_out(app)
    with _suspended_download(app, name, server) as (body, first):
        assert _checked_out(app) == before
        assert _in_transaction_on_chunks(app) == 0
        got = first + b''.join(body)
    assert got == data


def test_a_restore_reader_holds_no_connection_between_two_reads(app, nodes):
    data = _payload(2 * shared_store.CHUNK_SIZE)
    with app.app_context(), nodes('a'):
        _path, name = storage.create_archive(data)
        before = _checked_out(app)
        with shared_store.open_archive(name) as reader:
            head = reader.read(100)
            assert _checked_out(app) == before
            assert _in_transaction_on_chunks(app) == 0
            assert head + reader.read() == data


def test_an_archive_deleted_mid_download_cuts_the_stream_short(app, nodes, server, caplog):
    data = _payload(3 * shared_store.CHUNK_SIZE)
    with app.app_context(), nodes('a'):
        _path, name = storage.create_archive(data)
    got = bytearray()
    with _suspended_download(app, name, server) as (body, first):
        got += first
        with app.app_context():
            assert shared_store.delete_archives([name], wait=5) == [name]
        with pytest.raises(OSError):
            for piece in body:
                got += piece
    assert len(got) < len(data) and data.startswith(bytes(got))
    assert any(name in record.getMessage() and 'deleted' in record.getMessage()
               for record in caplog.records)


def test_fifteen_suspended_downloads_leave_the_pool_to_other_requests(
        app, auth_client, nodes, monkeypatch):
    from models import db
    data = _payload(2 * shared_store.CHUNK_SIZE)
    with app.app_context(), nodes('a'):
        _path, name = storage.create_archive(data)
        # A pool short of connections fails in 2 s instead of 30
        monkeypatch.setattr(db.engine.pool, '_timeout', 2)
    with contextlib.ExitStack() as stack:
        for _ in range(15):
            stack.enter_context(_suspended_download(app, name))
        with nodes('b'):
            r = auth_client.get('/api/v2/system/backups?per_page=100')
        assert r.status_code == 200, r.data
        assert name in {i['filename'] for i in json.loads(r.data)['data']['items']}


# --- 3. An archive appears once whole, an interrupted write leaves nothing -------------------

def test_an_archive_is_not_listed_before_its_last_chunk(app, nodes):
    _archives, chunks = _tables()
    started, release, done = threading.Event(), threading.Event(), []
    before = _count(app, chunks)

    def slow():
        for _ in range(3):
            yield _payload(shared_store.CHUNK_SIZE)
        started.set()
        assert release.wait(30)
        yield b'tail'

    def write():
        with app.app_context(), nodes('a'):
            done.append(storage.create_archive(slow())[1])
    writer = threading.Thread(target=write)
    writer.start()
    try:
        assert started.wait(30)
        with app.app_context():
            assert not [a for a in shared_store.list_archives() if a['node'].startswith(PREFIX)]
        assert _count(app, chunks) == before, 'chunks of an unfinished archive are visible'
    finally:
        release.set()
        writer.join(60)
    (name,) = done
    with app.app_context():
        assert shared_store.get_archive(name)['size'] == 3 * shared_store.CHUNK_SIZE + 4


def test_an_interrupted_write_leaves_no_row_and_no_chunk(app, nodes):
    archives, chunks = _tables()
    before = (_count(app, archives), _count(app, chunks))

    def broken():
        yield _payload(shared_store.CHUNK_SIZE)
        yield _payload(shared_store.CHUNK_SIZE)
        raise RuntimeError('export died')

    with app.app_context(), nodes('a'):
        with pytest.raises(RuntimeError):
            storage.create_archive(broken())
    assert (_count(app, archives), _count(app, chunks)) == before


# --- Retention, once, over the shared set ------------------------------------------------------

def _aged(app, names, days):
    archives = _tables()[0]
    from models import db
    with app.app_context(), db.engine.begin() as conn:
        for offset, name in enumerate(names):
            conn.execute(archives.update().where(archives.c.filename == name).values(
                created_at=utc_now() - timedelta(days=days, minutes=len(names) - offset)))


def _settings(app, **values):
    from models import SystemConfig, db
    with app.app_context():
        saved = {}
        for key, value in values.items():
            row = SystemConfig.query.filter_by(key=key).first()
            saved[key] = row.value if row else None
            if row:
                row.value = value
            else:
                db.session.add(SystemConfig(key=key, value=value))
        db.session.commit()
    return saved


@pytest.fixture
def retention_settings(app):
    saved = []

    def put(**values):
        saved.append(_settings(app, **values))
    yield put
    for values in reversed(saved):
        from models import SystemConfig, db
        with app.app_context():
            for key, value in values.items():
                SystemConfig.query.filter_by(key=key).delete()
                if value is not None:
                    db.session.add(SystemConfig(key=key, value=value))
            db.session.commit()


def _make(app, nodes, count, node='a', size=1000):
    names = []
    with app.app_context(), nodes(node):
        for _ in range(count):
            names.append(storage.create_archive(_payload(size))[1])
    return names


def _stored_names(app):
    with app.app_context():
        return {a['filename'] for a in shared_store.list_archives()}


def test_retention_applies_the_disk_rule_to_the_shared_set(app, nodes, retention_settings):
    retention_settings(backup_retention_days='30', backup_min_keep='2', backup_max_total_mb='0')
    old = _make(app, nodes, 4, 'a')
    recent = _make(app, nodes, 1, 'b')
    _aged(app, old, 40)
    with app.app_context(), nodes('b'):
        assert schedule.run_backup_retention() == 3
    left = _stored_names(app)
    # the newest one of B, and the newest old one to keep two whatever their age
    assert set(recent) <= left and old[-1] in left and not set(old[:3]) & left
    _, chunks = _tables()
    with app.app_context():
        assert _count(app, chunks) >= 2


def test_the_size_ceiling_drops_the_oldest_and_keeps_the_restore_points(app, nodes, retention_settings):
    retention_settings(backup_retention_days='30', backup_min_keep='1', backup_max_total_mb='1')
    names = _make(app, nodes, 3, 'a', size=600 * 1024)
    with app.app_context(), nodes('a'):
        assert schedule.run_backup_retention() == 2
    assert _stored_names(app) & set(names) == {names[-1]}


def _db_now(app):
    from models import db
    with app.app_context(), db.engine.connect() as conn:
        return conn.execute(text("SELECT clock_timestamp() AT TIME ZONE 'UTC'")).scalar()


@pytest.fixture
def node_clock(monkeypatch):
    """`skew(seconds)`: this node's clock (utc_now, time.time) runs that far from the server's."""
    import time as real_time
    import types

    def skew(seconds):
        fake = types.SimpleNamespace(**{k: getattr(real_time, k) for k in dir(real_time)
                                        if not k.startswith('__')})
        fake.time = lambda: real_time.time() + seconds
        for module in (shared_store, schedule):
            monkeypatch.setattr(module, 'time', fake)
            monkeypatch.setattr(module, 'utc_now', lambda: utc_now() + timedelta(seconds=seconds),
                                raising=False)
    return skew


def test_an_archive_is_dated_on_the_cluster_clock(app, nodes, node_clock):
    node_clock(40 * 86400)
    with app.app_context(), nodes('a'):
        name = storage.create_archive(_payload(1000))[1]
        created = shared_store.get_archive(name)['created_at']
    assert abs((created - _db_now(app)).total_seconds()) < 60


def test_retention_compares_ages_on_the_cluster_clock(app, nodes, retention_settings, node_clock):
    retention_settings(backup_retention_days='30', backup_min_keep='1', backup_max_total_mb='0')
    names = _make(app, nodes, 3, 'a')
    archives = _tables()[0]
    from models import db
    with app.app_context(), db.engine.begin() as conn:
        conn.execute(archives.update().where(archives.c.filename.in_(names[:2])).values(
            created_at=text("clock_timestamp() AT TIME ZONE 'UTC' - interval '40 days'")))
    node_clock(-40 * 86400)
    with app.app_context(), nodes('a'):
        assert schedule.run_backup_retention() == 2
    assert _stored_names(app) & set(names) == {names[-1]}


def test_the_age_of_the_last_archive_is_read_on_the_cluster_clock(app, nodes, node_clock):
    _make(app, nodes, 1, 'a')
    node_clock(86400)
    with app.app_context(), nodes('b'):
        assert schedule.get_schedule()['last_archive_age_seconds'] < 600


def test_two_nodes_running_retention_together_delete_once(app, nodes, retention_settings, monkeypatch):
    retention_settings(backup_retention_days='30', backup_min_keep='1', backup_max_total_mb='0')
    old = _make(app, nodes, 3, 'a')
    _aged(app, old, 40)
    chosen, release, results = threading.Event(), threading.Event(), {}
    real = shared_store._before_deleting

    def pause(victims):
        if threading.current_thread().name == 'node-a':
            chosen.set()
            assert release.wait(30)
        real(victims)
    monkeypatch.setattr(shared_store, '_before_deleting', pause)

    def run_a():
        # Node A's pass past its own disk lock, which a node B never shares
        with app.app_context():
            results['a'] = schedule._apply_shared_retention(30)
    a = threading.Thread(target=run_a, name='node-a')
    a.start()
    try:
        assert chosen.wait(30)
        with app.app_context(), nodes('b'):
            results['b'] = schedule.run_backup_retention()  # the daily pass: no wait
    finally:
        release.set()
        a.join(60)
    assert results == {'a': 2, 'b': 0}
    assert _stored_names(app) & set(old) == {old[-1]}


def test_retention_asked_while_another_node_prunes_waits_then_answers_409(
        app, auth_client, nodes, monkeypatch):
    from api.v2.system import backup as routes
    from models import db
    monkeypatch.setattr(routes, 'RETENTION_LOCK_WAIT', 0.5)
    with app.app_context(), db.engine.connect() as other:
        shared_store._take_lock(other, 0, 'node A')
        try:
            with nodes('b'):
                r = auth_client.post('/api/v2/system/backups/run-retention')
        finally:
            other.rollback()
    assert r.status_code == 409, r.data


def test_an_archive_that_does_not_read_back_is_not_stored(app, nodes, monkeypatch):
    from services.backup.errors import BackupValidationError
    archives, chunks = _tables()
    before = (_count(app, archives), _count(app, chunks))
    real = shared_store._read_chunks

    def flipped(conn, archive_id, count):
        for n, piece in enumerate(real(conn, archive_id, count)):
            yield bytes([piece[0] ^ 1]) + piece[1:] if n == 0 else piece
    monkeypatch.setattr(shared_store, '_read_chunks', flipped)
    with app.app_context(), nodes('a'):
        with pytest.raises(BackupValidationError):
            storage.create_archive(_payload(1000))
    assert (_count(app, archives), _count(app, chunks)) == before


def test_a_deletion_on_b_removes_the_archive_and_its_chunks(app, auth_client, nodes):
    _archives, chunks = _tables()
    names = _make(app, nodes, 3, 'a', size=shared_store.CHUNK_SIZE + 1)
    with app.app_context():
        from models import BackupArchive
        ids = {n: BackupArchive.query.filter_by(filename=n).one().id for n in names}
    with nodes('b'):
        assert auth_client.delete(f'/api/v2/system/backup/{names[0]}').status_code == 200
        assert auth_client.delete(f'/api/v2/system/backup/{names[0]}').status_code == 404
        assert auth_client.delete(f'/api/v2/settings/backup/{names[1]}').status_code == 204
        r = auth_client.post('/api/v2/system/backups/bulk-delete', json={
            'filenames': [names[2], names[2], names[0], '../x.ucmbkp']})
        assert json.loads(r.data)['data'] == {'deleted': 1, 'missing': 1, 'invalid': 1, 'failed': 0}
    assert not _stored_names(app) & set(names)
    for archive_id in ids.values():
        assert _count(app, chunks, archive_id=archive_id) == 0


# --- 5. Scheduled and manual archives follow the same rule ---------------------------------------

def test_a_manual_backup_on_a_is_encrypted_in_the_database_and_restorable_from_its_stream(
        app, auth_client, nodes):
    from models import SystemConfig, db
    marker = f'{PREFIX}-plaintext-marker'
    with app.app_context():
        db.session.add(SystemConfig(key=f'{PREFIX}.marker', value=marker))
        db.session.commit()
    try:
        with nodes('a') as dir_a:
            r = auth_client.post('/api/v2/system/backup', json={'password': PASSWORD})
            assert r.status_code == 200, r.data
            name = json.loads(r.data)['data']['filename']
            assert not _on_disk(dir_a)
        with app.app_context():
            with shared_store.open_archive(name) as reader:
                stored = reader.read()
        assert stored[:4] == container.MAGIC
        assert marker.encode() not in stored
        # What a restore reads (HD-1): the stream decrypts with the password
        from services.backup.backup_service import BackupService
        from services.backup.section_store import SectionStore
        with app.app_context(), shared_store.open_archive(name) as reader, SectionStore() as store:
            assert BackupService()._read_v4(reader, PASSWORD, store)
    finally:
        with app.app_context():
            SystemConfig.query.filter_by(key=f'{PREFIX}.marker').delete()
            db.session.commit()


def test_the_scheduled_backup_goes_to_the_database(app, nodes, retention_settings):
    from utils.encryption import encrypt_value
    retention_settings(auto_backup_enabled='true', backup_frequency='daily',
                       backup_password=encrypt_value(PASSWORD), **{'backup.last_run': None,
                                                                   'backup.concluded_run': None})
    with app.app_context(), nodes('a') as dir_a:
        from models import SystemConfig, db
        SystemConfig.query.filter(SystemConfig.key.in_(('backup.last_run', 'backup.concluded_run'))).delete(
            synchronize_session=False)
        db.session.commit()
        result = schedule.run_scheduled_backup()
        assert result['status'] == 'ok', result
        assert not _on_disk(dir_a)
    with app.app_context():
        assert shared_store.get_archive(result['filename'])['node'] == f'{PREFIX}-a'


# --- 6. Same permissions as on disk --------------------------------------------------------------

def test_listing_and_download_keep_their_permission(app, nodes, create_user):
    names = _make(app, nodes, 1, 'a')
    create_user(username=f'{PREFIX}-op', role='operator')
    client = app.test_client()
    r = client.post('/api/v2/auth/login', json={'username': f'{PREFIX}-op', 'password': 'TestPass123!'})
    assert r.status_code == 200, r.data
    try:
        with nodes('b'):
            for url in ('/api/v2/system/backups', f'/api/v2/system/backup/{names[0]}/download',
                        f'/api/v2/settings/backup/{names[0]}/download',
                        '/api/v2/settings/backup/history'):
                r = client.get(url)
                assert r.status_code == 403, (url, r.status_code)
                assert names[0].encode() not in r.data
            assert app.test_client().get('/api/v2/system/backups').status_code == 401
    finally:
        from models import User, UserSession, db
        with app.app_context():
            ids = [u.id for u in User.query.filter_by(username=f'{PREFIX}-op')]
            UserSession.query.filter(UserSession.user_id.in_(ids)).delete(synchronize_session=False)
            User.query.filter(User.id.in_(ids)).delete(synchronize_session=False)
            db.session.commit()


# --- Memory stays bounded, writing and reading ----------------------------------------------------

def test_storing_and_reading_an_archive_holds_a_chunk_not_the_archive(app, nodes):
    size = MEASURED_MB * 1024 * 1024
    seed = _payload(shared_store.CHUNK_SIZE)

    def stream():
        for n in range(size // shared_store.CHUNK_SIZE):
            yield seed[n % 7:] + seed[:n % 7]
    expected = hashlib.sha256()
    for piece in stream():
        expected.update(piece)

    bound = 12 * shared_store.CHUNK_SIZE
    with app.app_context(), nodes('a'):
        gc.collect()
        rss_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        tracemalloc.start()
        try:
            _path, name = storage.create_archive(stream())
            written = tracemalloc.get_traced_memory()[1]
            tracemalloc.reset_peak()
            got = hashlib.sha256()
            for piece in shared_store.iter_archive(name):
                got.update(piece)
            read = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        rss_growth = (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - rss_before) * 1024
    print(f'\n{MEASURED_MB} MiB archive: peak {written / 2**20:.1f} MiB writing, '
          f'{read / 2**20:.1f} MiB reading, peak RSS +{rss_growth / 2**20:.1f} MiB')
    assert got.hexdigest() == expected.hexdigest()
    assert written < bound and read < bound, (written, read)
    assert rss_growth < 8 * bound, rss_growth


def test_the_store_lock_is_per_schema(app):
    """Two installations sharing a database never wait on each other; two nodes of one do."""
    import psycopg
    from sqlalchemy import create_engine
    from services.backup.locking import BackupBusyError
    other = f'{pg_app_harness.SCHEMA}_lockb'
    with psycopg.connect(pg_app_harness.APP_PG_URL, autocommit=True) as admin:
        admin.execute(f'CREATE SCHEMA IF NOT EXISTS "{other}"')
    engines = {schema: create_engine(pg_app_harness.app_url(schema))
               for schema in (pg_app_harness.SCHEMA, other)}
    try:
        with engines[pg_app_harness.SCHEMA].connect() as holder, \
                engines[other].connect() as neighbour, \
                engines[pg_app_harness.SCHEMA].connect() as same:
            shared_store._take_lock(holder, 0, 'node A')
            shared_store._take_lock(neighbour, 0, 'other installation')
            with pytest.raises(BackupBusyError):
                shared_store._take_lock(same, 0, 'node B')
    finally:
        for engine in engines.values():
            engine.dispose()
        with psycopg.connect(pg_app_harness.APP_PG_URL, autocommit=True) as admin:
            admin.execute(f'DROP SCHEMA IF EXISTS "{other}" CASCADE')


def test_the_fips_preflight_reads_the_kdf_of_the_stored_archives(app, nodes):
    from services import fips_preflight
    argon = container.MAGIC + bytes([4, 0, container.KDF_ARGON2ID]) + _payload(64)
    pbkdf2 = container.MAGIC + bytes([4, 0, 1]) + _payload(64)
    names = _make(app, nodes, 0)
    with app.app_context(), nodes('a'):
        names = [storage.create_archive(data)[1] for data in (argon, pbkdf2)]
        found = fips_preflight._backup_archives()
    assert names[0] in found and names[1] not in found


def test_chunks_are_stored_out_of_line_uncompressed(app):
    # Encrypted bytes do not compress: EXTERNAL spares PostgreSQL the attempt
    from models import db
    with app.app_context(), db.engine.connect() as conn:
        storage_kind = conn.execute(text(
            "SELECT a.attstorage FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = current_schema() "
            "WHERE c.relname = 'backup_archive_chunks' AND a.attname = 'data'")).scalar()
    assert storage_kind == 'e'


def test_a_busy_store_refuses_with_the_sentence_of_the_disk_lock(app, nodes):
    from models import db
    from services.backup.locking import BackupBusyError, backup_operation_lock
    refusals, held, release = {}, threading.Event(), threading.Event()

    def hold_disk_lock():
        with backup_operation_lock(purpose='holder'):
            held.set()
            assert release.wait(30)
    with nodes('a'):
        holder = threading.Thread(target=hold_disk_lock)
        holder.start()
        try:
            assert held.wait(30)
            with pytest.raises(BackupBusyError) as disk:
                with backup_operation_lock(timeout=0.2, purpose='deleting a backup'):
                    pass
            refusals['disk'] = str(disk.value)
        finally:
            release.set()
            holder.join(30)
    with app.app_context(), db.engine.connect() as other:
        shared_store._take_lock(other, 0, 'node A')
        try:
            with pytest.raises(BackupBusyError) as store:
                shared_store.delete_archives(['ucm_backup_x.ucmbkp'], wait=0.2,
                                             purpose='deleting a backup')
            refusals['store'] = str(store.value)
        finally:
            other.rollback()
    assert refusals['store'] == refusals['disk']
