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
import pytest
import os
import sys
import json
import tempfile

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
os.environ.setdefault('UCM_DEV_MODE', 'true')

# Add backend to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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


@pytest.fixture(scope='session')
def client(app):
    """Unauthenticated Flask test client."""
    return app.test_client()


@pytest.fixture(scope='session')
def auth_client(app):
    """Authenticated Flask test client (admin role)."""
    c = app.test_client()
    r = c.post('/api/v2/auth/login',
               data=json.dumps({'username': 'admin', 'password': 'changeme123'}),
               content_type='application/json')
    assert r.status_code == 200, f'Admin login failed: {r.data}'
    return c


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
    """Factory fixture to create a certificate. Returns cert dict."""
    _ca_cache = {}
    _counter = [0]

    def _create(cn=None, ca_id=None, **kwargs):
        _counter[0] += 1
        if ca_id is None:
            if 'default' not in _ca_cache:
                ca = create_ca(cn='Default Test CA')
                _ca_cache['default'] = ca.get('id', ca.get('ca_id', 1))
            ca_id = _ca_cache['default']

        data = {
            'cn': cn or f'test-cert-{_counter[0]}.example.com',
            'ca_id': ca_id,
            'validity_days': 365,
        }
        data.update(kwargs)
        r = auth_client.post('/api/v2/certificates',
                             data=json.dumps(data),
                             content_type='application/json')
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


@pytest.fixture(autouse=True)
def _clear_acme_public_vhost_settings(app):
    """Clear acme_proxy_* SystemConfig so public URL tests do not leak into ACME JWS tests."""
    from models import db, SystemConfig

    keys = ('acme_proxy_vhost', 'acme_proxy_port', 'acme_proxy_tls_cert_id')

    def _delete_keys():
        with app.app_context():
            SystemConfig.query.filter(
                SystemConfig.key.in_(keys)
            ).delete(synchronize_session=False)
            db.session.commit()

    _delete_keys()
    yield
    _delete_keys()


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
