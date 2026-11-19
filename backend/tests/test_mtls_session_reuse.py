"""A browser holding a client certificate opens one mTLS session, not one per request."""
import pytest

from models import AuditLog, db
from tests.test_session_lifecycle import _cert_login, _sid, make_user  # noqa: F401 (fixture)


@pytest.fixture
def cert_user(app, make_user, monkeypatch):
    import middleware.mtls_middleware as mtls_middleware
    from services.mtls_auth_service import MTLSAuthService
    uid, username, _ = make_user()
    monkeypatch.setattr(MTLSAuthService, 'is_mtls_enabled', staticmethod(lambda: True))
    monkeypatch.setattr(mtls_middleware, '_extract_certificate', lambda: {'serial': '0a'})
    _cert_login(monkeypatch, app, uid)
    with app.app_context():
        floor = db.session.query(db.func.max(AuditLog.id)).scalar() or 0
    return uid, floor


def _logins(app, cert_user):
    uid, floor = cert_user
    with app.app_context():
        return AuditLog.query.filter(
            AuditLog.id > floor, AuditLog.action == 'login_success',
            AuditLog.resource_id == str(uid), AuditLog.details.like('mTLS auto-login%')).count()


def _stored(app, sid):
    iface = app.session_interface
    with app.app_context():
        return iface._retrieve_session_data(iface._get_store_id(sid)) is not None


def test_an_established_certificate_session_is_reused(app, cert_user):
    c = app.test_client()
    assert c.get('/api/v2/account/profile').status_code == 200
    sid = _sid(c)
    assert _logins(app, cert_user) == 1
    for url in ('/audit', '/api/v2/auth/verify', '/api/v2/account/profile'):
        c.get(url)
    assert _sid(c) == sid and _logins(app, cert_user) == 1


@pytest.mark.parametrize('path', ['/favicon.svg', '/assets/index-0a1b2c.js', '/fonts/Inter-Regular.woff2'])
def test_a_cookieless_file_request_opens_no_session(app, cert_user, path):
    """The browser fetches its favicon without the session cookie: no login there."""
    c = app.test_client()
    assert c.get('/api/v2/account/profile').status_code == 200
    favicon = app.test_client()
    favicon.get(path)
    assert _logins(app, cert_user) == 1
    sid = _sid(favicon)
    assert sid is None or not _stored(app, sid)


def test_a_page_load_opens_one_session(app, cert_user):
    """Navigation logs in once; the cookieless favicon fetches next to it do not."""
    c = app.test_client()
    c.get('/audit')
    sid = _sid(c)
    assert sid and _stored(app, sid)
    for _ in range(3):
        app.test_client().get('/favicon.svg')
    for url in ('/api/v2/auth/verify', '/api/v2/audit/logs', '/api/v2/account/profile'):
        c.get(url)
    assert _sid(c) == sid and _logins(app, cert_user) == 1


def test_parallel_requests_on_one_cookie_keep_it(app, cert_user):
    c = app.test_client()
    c.get('/api/v2/account/profile')
    sid = _sid(c)
    replies = [app.test_client() for _ in range(3)]
    for r in replies:
        r.set_cookie('session', sid)
        assert r.get('/api/v2/account/profile').status_code == 200
        assert _sid(r) == sid
    assert _logins(app, cert_user) == 1


def test_an_api_path_with_a_dot_still_logs_in(app, cert_user):
    """API clients (curl with a client certificate) keep authenticating on any API path."""
    c = app.test_client()
    c.get('/api/v2/system/backup/ucm-backup.ucmbak')
    assert _logins(app, cert_user) == 1 and _stored(app, _sid(c))
