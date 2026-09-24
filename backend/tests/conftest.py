"""
pytest configuration and fixtures for UCM backend tests.

Shared fixtures used by all test_*.py files:
  - app: Flask app with temp SQLite DB
  - client: unauthenticated test client
  - auth_client: authenticated as admin
  - viewer_client: authenticated as viewer (read-only)
  - create_ca: factory to create a root CA
  - create_cert: factory to create a certificate under a CA
  - create_user: factory to create a user
"""
import atexit
import contextlib
import fcntl
import pytest
import os
import shutil
import sys
import json
import tempfile
from pathlib import Path

# Set required env vars at MODULE LOAD time, before any test file is collected.
# settings.py reads SECRET_KEY / JWT_SECRET_KEY at class-body load time, so they
# must be present before the first `from app import create_app` (which can be
# triggered by any test module's import or fixture).
os.environ.setdefault('SECRET_KEY', 'test-secret-key-for-testing')
os.environ.setdefault('JWT_SECRET_KEY', 'test-jwt-secret-key-for-testing')
os.environ.setdefault('UCM_ENV', 'test')
os.environ.setdefault('HTTP_REDIRECT', 'false')
os.environ.setdefault('INITIAL_ADMIN_PASSWORD', 'changeme123')
os.environ.setdefault('CSRF_DISABLED', 'true')

# Isolate DATA_DIR from the machine's live install. settings.py runs
# load_dotenv("/etc/ucm/ucm.env"), which on a dev box points DATA_DIR at the
# running service's data dir — tests would then write session files there
# (root-owned, breaking the service's session pruning) and touch its
# .restart_requested watcher signal. load_dotenv never overrides pre-set env
# vars, so pinning a temp dir here keeps tests off the real data dir.
# Under xdist the workers inherit the controller's environment, so a single
# temp dir would be shared by all of them — and with it the inter-process
# locks that live in it (the backup lock, the migration lock). A test holding
# one would then refuse an unrelated test running on another worker. Each
# worker is an independent instance and gets its own directory.
def _sweep_abandoned_test_dirs(prefix='ucm-test-', older_than=86400):
    """Remove the temp directories of runs that never got to clean up.

    The `atexit` below does not run when an xdist worker is killed, so a
    suite that is interrupted leaves its directory behind; on a machine that
    runs the suite all day that is hundreds of them. Only this suite's own
    prefix is touched, and only after a day, so a run happening right now is
    never disturbed.
    """
    import time

    cutoff = time.time() - older_than
    root = Path(tempfile.gettempdir())
    try:
        candidates = list(root.glob(f'{prefix}*'))
    except OSError:
        return
    for path in candidates:
        try:
            if path.is_dir() and path.stat().st_mtime < cutoff:
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            continue


_sweep_abandoned_test_dirs()

# Pre-migration snapshots are kept for the operator, not for a test run: two
# are enough to exercise both the retention and the fact that two snapshots
# never claim the same name, and they keep a worker's directory small.
os.environ.setdefault('UCM_DB_MIGRATION_KEEP', '2')

_xdist_worker = os.environ.get('PYTEST_XDIST_WORKER')
if 'DATA_DIR' not in os.environ or _xdist_worker:
    _tmp_data_dir = tempfile.mkdtemp(
        prefix=f'ucm-test-data-{_xdist_worker or "main"}-')
    os.environ['DATA_DIR'] = _tmp_data_dir
    atexit.register(shutil.rmtree, _tmp_data_dir, ignore_errors=True)

# ucm.env also names the live database, and create_app() hands the migration
# runner whatever DATABASE_PATH / DATABASE_URL say while the app itself runs
# in memory. Pinned before settings.py loads the file, like DATA_DIR above.
if 'DATABASE_PATH' not in os.environ or _xdist_worker:
    os.environ['DATABASE_PATH'] = os.path.join(os.environ['DATA_DIR'], 'ucm.db')
os.environ.setdefault('DATABASE_URL', '')

# The backend-switch routes rewrite /etc/ucm/ucm.env, the file the installed
# service reads at boot: a test that reached it would take this machine's own
# instance down. Redirected here rather than in the `app` fixture, because a
# test that never asks for `app` would otherwise resolve the real path, and
# the protection would rest on a convention instead of on the structure.
UCM_TEST_ENV_FILE = Path(os.environ['DATA_DIR']) / 'etc' / 'ucm.env'
UCM_TEST_ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
if not UCM_TEST_ENV_FILE.exists():
    UCM_TEST_ENV_FILE.write_text('# test sandbox\n')
os.environ.setdefault('UCM_DEV_MODE', 'true')

# Add backend to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The path is a module constant, bound by value wherever it was imported, so
# each module that holds a copy is redirected as soon as it is importable.
from services.database_admin import helpers as _db_helpers  # noqa: E402
from services.database_admin import persistence as _db_persistence  # noqa: E402

_db_helpers.UCM_ENV_PATH = UCM_TEST_ENV_FILE
_db_persistence.UCM_ENV_PATH = UCM_TEST_ENV_FILE


class _GuardResolverProxy:
    """Stand-in for utils.ssrf_protection's `socket` module (and ONLY its):
    getaddrinfo falls back to a fixed TEST-NET-3 answer when the real
    resolver fails; everything else forwards to the real socket module."""

    def __init__(self, real_socket):
        self._real = real_socket

    def __getattr__(self, name):
        return getattr(self._real, name)

    def getaddrinfo(self, host, *args, **kwargs):
        try:
            return self._real.getaddrinfo(host, *args, **kwargs)
        except self._real.gaierror:
            return [(self._real.AF_INET, self._real.SOCK_STREAM, 6, '',
                     ('203.0.113.10', 0))]


@pytest.fixture(autouse=True)
def _deterministic_dns(monkeypatch):
    """Make the SSRF guards' hostname resolution deterministic.

    The guards fail CLOSED on an unresolvable host (#256), which made every
    test that validates a made-up hostname (hook.example.com, fake OIDC
    issuers, ACME upstream stubs, ...) hostage to the runner's resolver: an
    honest resolver NXDOMAINs those names and the guard refuses them, while
    an NXDOMAIN-hijacking one resolves them and the guard does not. Neither
    outcome is about the code under test.

    Only utils.ssrf_protection's view of `socket` is replaced: real answers
    win, and only a resolver failure falls back to a fixed TEST-NET-3
    address, which the guards treat as public — so save-time URL validation
    passes deterministically. Everything else (requests, ldap3, discovery)
    keeps the REAL resolver, so an actual connection attempt to a made-up
    host still fails fast with the same error as before, instead of hanging
    on an unroutable address. SSRF-focused tests that need a specific answer
    or a resolution FAILURE monkeypatch ssrf_protection.socket.getaddrinfo
    themselves; that lands on this proxy instance and fully replaces the
    fallback for the test's duration.
    """
    import socket as _socket
    import utils.ssrf_protection as _ssrf

    monkeypatch.setattr(_ssrf, 'socket', _GuardResolverProxy(_socket))


@pytest.fixture(autouse=True)
def _reset_acme_proxy_caches():
    """Drop the ACME proxy's process-level caches around every test.

    The upstream directory, finalize-URL, challenge->order and Replay-Nonce
    caches are module-level by design — they outlive a request, which also
    means they outlive a test. Two modules that stub the same upstream
    directory URL with different payloads would otherwise see each other's
    entries, and a pooled nonce would make _get_nonce() skip the HEAD request
    a later test asserts on. Cleared on both sides so run order cannot matter.
    """
    from services.acme.acme_proxy_service import reset_proxy_caches

    reset_proxy_caches()
    yield
    reset_proxy_caches()


def _drop_unreadable_key_material(app):
    """Forget key material that was written under a now-discarded key.

    The test database is shared by the whole session, so a key or secret
    written while `encryption_enabled` held an ephemeral key stays there after
    the key is gone — and its key material can no longer be read by anything.
    Since the backup service refuses to export a key it cannot decrypt, one
    such leftover row would fail every later backup test. A row without key
    material is a state the product supports (an offline or imported CA), so
    the column is cleared rather than the row deleted, which would take its
    certificates and approvals with it.
    """
    from models import db
    from security.encryption import (
        decrypt_master_key_value, key_encryption, master_key_values,
    )

    with app.app_context():
        changed = False
        for _, row, attribute, fmt in list(master_key_values()):
            value = getattr(row, attribute)
            if not key_encryption.is_encrypted(value):
                continue
            try:
                decrypt_master_key_value(value, fmt)
            except Exception:
                # prv may be NULL; the other columns are NOT NULL: '' is "none"
                setattr(row, attribute, None if attribute == 'prv' else '')
                changed = True
        if changed:
            db.session.commit()


@pytest.fixture
def encryption_enabled(monkeypatch, tmp_path, app):
    """Enable private-key encryption with an isolated ephemeral key."""
    from cryptography.fernet import Fernet
    from security import encryption as enc_mod

    with monkeypatch.context() as patch:
        patch.setattr(enc_mod, 'MASTER_KEY_PATH', tmp_path / 'master.key')
        patch.setenv('KEY_ENCRYPTION_KEY', Fernet.generate_key().decode('ascii'))
        patch.delenv('KEY_ENCRYPTION_KEY_FILE', raising=False)
        enc_mod.key_encryption.reload()
        assert enc_mod.key_encryption.is_enabled
        yield enc_mod

    enc_mod.key_encryption.reload()
    _drop_unreadable_key_material(app)


@pytest.fixture(scope='session')
def app():
    """Create Flask app with test configuration (shared across all tests)."""
    os.environ['SECRET_KEY'] = 'test-secret-key-for-testing'
    os.environ['JWT_SECRET_KEY'] = 'test-jwt-secret-key-for-testing'
    os.environ['UCM_ENV'] = 'test'
    os.environ['HTTP_REDIRECT'] = 'false'
    os.environ['INITIAL_ADMIN_PASSWORD'] = 'changeme123'
    os.environ['CSRF_DISABLED'] = 'true'
    os.environ['UCM_DEV_MODE'] = 'true'

    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        os.environ['UCM_DATABASE_PATH'] = f.name
        temp_db = f.name

    from app import create_app
    application = create_app('testing')

    # Keep the suite off the machine's real files. The restore writes the
    # HTTPS certificate and key where the configuration points, and the
    # backup routes write archives to the configured directory: pointed at
    # /etc/ucm and /opt/ucm as they are by default, a test run would replace
    # the files the installed service is using.
    from config.settings import Config as _Config
    _sandbox = Path(tempfile.mkdtemp(prefix='ucm-test-paths-'))
    for _name, _relative in (
        ('HTTPS_CERT_PATH', 'etc/https_cert.pem'),
        ('HTTPS_KEY_PATH', 'etc/https_key.pem'),
        ('DATA_DIR', 'data'),
        ('BACKUP_DIR', 'data/backups'),
        ('CA_DIR', 'data/ca'),
        ('CRL_DIR', 'data/crl'),
        ('CERT_DIR', 'data/certs'),
        ('PRIVATE_DIR', 'data/private'),
    ):
        if not hasattr(_Config, _name):
            continue
        _target = _sandbox / _relative
        (_target.parent if _target.suffix else _target).mkdir(parents=True, exist_ok=True)
        setattr(_Config, _name, _target)
        application.config[_name] = _target

    application.config['TESTING'] = True
    application.config['WTF_CSRF_ENABLED'] = False
    # Deterministic FQDN so CA OCSP/CDP/AIA auto-URL generation does not depend
    # on the CI runner's `hostname -f` (which can lack a domain part and thus
    # resolve to None, flaking tests that patch `ocsp_enabled=True` without a
    # configured protocol_base_url).
    application.config['FQDN'] = 'ucm.test'

    yield application

    if os.path.exists(temp_db):
        os.unlink(temp_db)


@pytest.fixture
def client(app):
    """Unauthenticated Flask test client, one per test.

    It used to be session-scoped, so six thousand tests shared one cookie jar
    and one server-side session. Tests asserting 401 failed intermittently
    with a 200 and a full payload: something in the worker had filled that
    session. A client with nothing to authenticate has no state worth sharing.
    """
    return app.test_client()


class _ReloggingClient:
    """A test client that signs back in when its session disappears.

    A restore revokes every session that existed before it, the caller's
    included — that is the point of it. The session-scoped client would then
    fail every later test in the worker, so it signs in again once and replays
    the request, the way a person would.
    """

    def __init__(self, client, login):
        self._client = client
        self._login = login

    def _call(self, method, *args, **kwargs):
        response = getattr(self._client, method)(*args, **kwargs)
        if response.status_code != 401:
            return response
        self._login(self._client)
        try:
            return getattr(self._client, method)(*args, **kwargs)
        except ValueError:
            # An upload whose stream the first attempt consumed cannot be
            # replayed; the original answer is what the test asked for.
            return response

    def get(self, *a, **k): return self._call('get', *a, **k)
    def post(self, *a, **k): return self._call('post', *a, **k)
    def put(self, *a, **k): return self._call('put', *a, **k)
    def patch(self, *a, **k): return self._call('patch', *a, **k)
    def delete(self, *a, **k): return self._call('delete', *a, **k)

    def __getattr__(self, name):
        return getattr(self._client, name)


@pytest.fixture(scope='session')
def auth_client(app):
    """Authenticated Flask test client (admin role)."""
    def login(client):
        r = client.post('/api/v2/auth/login',
                        data=json.dumps({'username': 'admin',
                                         'password': 'changeme123'}),
                        content_type='application/json')
        assert r.status_code == 200, f'Admin login failed: {r.data}'
        return r

    c = app.test_client()
    login(c)
    return _ReloggingClient(c, login)


@pytest.fixture(scope='module')
def viewer_client(app):
    """Authenticated test client with viewer role (read-only)."""
    admin = app.test_client()
    r = admin.post('/api/v2/auth/login',
                   data=json.dumps({'username': 'admin', 'password': 'changeme123'}),
                   content_type='application/json')
    assert r.status_code == 200

    # Create viewer user
    r = admin.post('/api/v2/users',
                   data=json.dumps({
                       'username': 'viewer_test',
                       'password': 'ViewerPass123!',
                       'email': 'viewer@test.local',
                       'role': 'viewer'
                   }),
                   content_type='application/json')

    # Login as viewer
    vc = app.test_client()
    r = vc.post('/api/v2/auth/login',
                data=json.dumps({'username': 'viewer_test', 'password': 'ViewerPass123!'}),
                content_type='application/json')
    if r.status_code == 200:
        return vc
    # Fallback — if viewer creation failed (already exists), just return admin
    return admin


# ============================================================
# Factory fixtures
# ============================================================

@pytest.fixture(scope='session')
def create_ca(auth_client):
    """Factory fixture to create a root CA. Returns CA dict."""
    _counter = [0]

    def _create(cn=None, **kwargs):
        _counter[0] += 1
        data = {
            'type': 'root',
            'commonName': cn or f'Test CA {_counter[0]}',
            'organization': 'Test Org',
            'country': 'US',
            'state': 'CA',
            'locality': 'Test City',
            'keyType': 'RSA',
            'keySize': 2048,
            'validityYears': 10,
            'hashAlgorithm': 'sha256',
        }
        data.update(kwargs)
        r = auth_client.post('/api/v2/cas',
                             data=json.dumps(data),
                             content_type='application/json')
        assert r.status_code in (200, 201), f'Create CA failed ({r.status_code}): {r.data}'
        result = json.loads(r.data)
        return result.get('data', result)
    return _create


@pytest.fixture(scope='session')
def create_cert(auth_client, create_ca):
    """Factory fixture to create a certificate. Returns cert dict.

    The default CA is remembered across the session, and one test resets the
    database for real (`test_database_reset_records_itself`): every later
    caller then asked for a CA id that no longer exists and got a 404. The
    cache is rebuilt when the row behind it is gone, so a destructive test
    costs its own file rather than every file after it in the run.
    """
    _ca_cache = {}
    _counter = [0]

    def _default_ca():
        ca = create_ca(cn='Default Test CA')
        _ca_cache['default'] = ca.get('id', ca.get('ca_id', 1))
        return _ca_cache['default']

    def _create(cn=None, ca_id=None, **kwargs):
        _counter[0] += 1
        from_cache = ca_id is None
        if from_cache:
            ca_id = _ca_cache.get('default') or _default_ca()

        data = {
            'cn': cn or f'test-cert-{_counter[0]}.example.com',
            'ca_id': ca_id,
            'validity_days': 365,
        }
        data.update(kwargs)

        def _post():
            return auth_client.post('/api/v2/certificates',
                                    data=json.dumps(data),
                                    content_type='application/json')

        r = _post()
        if r.status_code == 404 and from_cache and 'ca_id' not in kwargs:
            data['ca_id'] = _default_ca()
            r = _post()
        assert r.status_code in (200, 201), f'Create cert failed ({r.status_code}): {r.data}'
        result = json.loads(r.data)
        return result.get('data', result)
    return _create


@pytest.fixture(scope='session')
def create_user(auth_client):
    """Factory fixture to create a user. Returns user dict."""
    _counter = [0]

    def _create(username=None, role='operator', **kwargs):
        _counter[0] += 1
        data = {
            'username': username or f'testuser{_counter[0]}',
            'password': 'TestPass123!',
            'email': f'testuser{_counter[0]}@test.local',
            'role': role,
        }
        data.update(kwargs)
        r = auth_client.post('/api/v2/users',
                             data=json.dumps(data),
                             content_type='application/json')
        # If the username already exists in the shared session DB (e.g. a
        # rerun or shard collision in CI), fetch and return it instead of
        # failing with 500. Tests treat the user as ephemeral context.
        if r.status_code in (409, 500):
            r2 = auth_client.get('/api/v2/users')
            if r2.status_code == 200:
                users = json.loads(r2.data).get('data', [])
                for u in users:
                    if u.get('username') == data['username']:
                        return u
        assert r.status_code in (200, 201), f'Create user failed ({r.status_code}): {r.data}'
        result = json.loads(r.data)
        return result.get('data', result)
    return _create


@pytest.fixture
def clear_acme_public_vhost_settings(app):
    """Clear acme_public_* SystemConfig before and after tests that set them."""
    from models import db, SystemConfig

    keys = ('acme_public_vhost', 'acme_public_port', 'acme_public_tls_cert_id')

    def _delete_keys():
        with app.app_context():
            SystemConfig.query.filter(
                SystemConfig.key.in_(keys)
            ).delete(synchronize_session=False)
            db.session.commit()

    _delete_keys()
    yield
    _delete_keys()


@pytest.fixture
def set_acme_public_config(app, clear_acme_public_vhost_settings):
    """Callable fixture: persist acme_public_vhost/port SystemConfig rows.

    Depends on clear_acme_public_vhost_settings so any value set here is
    removed after the test (shared session-scoped DB).
    """
    from models import db, SystemConfig

    def _set(vhost: str = '', port: str = '443'):
        with app.app_context():
            for key, value in (
                ('acme_public_vhost', vhost),
                ('acme_public_port', port),
            ):
                row = SystemConfig.query.filter_by(key=key).first()
                if not row:
                    row = SystemConfig(key=key)
                    db.session.add(row)
                row.value = value
            db.session.commit()

    return _set


# ============================================================
# Helpers
# ============================================================

def get_json(response):
    """Parse JSON response, return dict."""
    return json.loads(response.data)


def assert_success(response, status=200):
    """Assert response is successful and return parsed data."""
    assert response.status_code == status, \
        f'Expected {status}, got {response.status_code}: {response.data[:500]}'
    data = json.loads(response.data)
    return data.get('data', data)


def assert_error(response, status):
    """Assert response is an error with given status code."""
    assert response.status_code == status, \
        f'Expected {status}, got {response.status_code}: {response.data[:500]}'


def clean_dangling_rows(app):
    """Delete rows of the shared test database that break its own schema.

    The suite's database is shared by every file of a worker and is not
    guaranteed to satisfy its own foreign keys: it is written by fixtures that
    bypass the routes, and SQLite enforces nothing. Anything that reads it as
    a *database* rather than as a fixture — the migration, which refuses to
    copy rows PostgreSQL would reject — then fails depending on which files
    ran before it.

    Returns the number of rows removed, so a caller can say so.
    """
    from sqlalchemy import text as _text
    from models import db as _db
    from services.database_admin.helpers import _force_register_all_models

    _force_register_all_models()
    removed = 0
    with app.app_context():
        present = set(_db.inspect(_db.engine).get_table_names())
        for table in reversed(_db.metadata.sorted_tables):
            if table.name not in present:
                continue
            for constraint in table.foreign_key_constraints:
                elements = list(constraint.elements)
                child = [e.parent.name for e in elements]
                parent_table = elements[0].column.table.name
                parent = [e.column.name for e in elements]
                if parent_table not in present:
                    continue
                on = ' AND '.join(
                    f'c."{a}" = p."{b}"' for a, b in zip(child, parent))
                not_null = ' AND '.join(f'c."{a}" IS NOT NULL' for a in child)
                result = _db.session.execute(_text(
                    f'DELETE FROM "{table.name}" WHERE rowid IN ('
                    f'  SELECT c.rowid FROM "{table.name}" c '
                    f'  LEFT JOIN "{parent_table}" p ON {on} '
                    f'  WHERE {not_null} AND p."{parent[0]}" IS NULL)'))
                removed += result.rowcount or 0
        if removed:
            _db.session.commit()
        else:
            _db.session.rollback()
    return removed


def clean_unreadable_secrets(app):
    """Delete rows of the shared test database whose secrets do not decrypt.

    Companion to :func:`clean_dangling_rows`, for the same reason: fixtures
    write placeholder values into encrypted columns, and a key rotated by one
    file leaves rows the current key cannot read. Anything that reads this
    database as a *database* rather than as a fixture then refuses it, by
    design -- a migration will not copy a secret it cannot prove survived.

    Returns the number of rows removed.
    """
    from sqlalchemy import text as _text
    from models import db as _db

    removed = 0
    with app.app_context():
        from services.database_admin.verify import encrypted_columns
        from services.backup.key_material import decrypt_stored_secret

        present = set(_db.inspect(_db.engine).get_table_names())
        for table, column in encrypted_columns():
            if table not in present:
                continue
            try:
                rows = _db.session.execute(_text(
                    f'SELECT rowid, "{column}" FROM "{table}" '
                    f'WHERE "{column}" IS NOT NULL')).fetchall()
            except Exception:
                _db.session.rollback()
                continue
            doomed = []
            for rowid, value in rows:
                if not isinstance(value, str) or not value:
                    continue
                try:
                    decrypt_stored_secret(value, label=f'{table}.{column}')
                except Exception:
                    doomed.append(rowid)
            for rowid in doomed:
                _db.session.execute(_text(
                    f'DELETE FROM "{table}" WHERE rowid = :rowid'),
                    {'rowid': rowid})
                removed += 1
        if removed:
            _db.session.commit()
        else:
            _db.session.rollback()
    return removed


@contextlib.contextmanager
def pg_bench_exclusive():
    """Exclusive use of the shared PostgreSQL bench (public schema).

    Three files reset that schema with ``DROP SCHEMA public CASCADE``. On
    different xdist workers they empty each other's target mid-test, so the
    opt-in PostgreSQL run only passed sequentially.
    """
    lock_path = Path(tempfile.gettempdir()) / 'ucm-pg-bench.lock'
    with open(lock_path, 'w') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
