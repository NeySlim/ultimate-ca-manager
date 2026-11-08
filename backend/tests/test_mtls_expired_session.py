"""The parallel calls of a browser whose session expired open one certificate session, not one each."""
import threading
from datetime import timedelta

import pytest
from flask_session.base import ServerSideSession

from auth.unified import AuthManager
from models import AuditLog, db
from tests.test_mtls_session_reuse import _logins, _stored
from tests.test_session_lifecycle import _cert_login, _login, _sid, make_user  # noqa: F401 (fixture)
from utils.datetime_utils import utc_now

PARALLEL = 4


@pytest.fixture
def cert_user(app, make_user, monkeypatch):
    """A user whose browser holds a client certificate and an expired password session."""
    import middleware.mtls_middleware as mtls_middleware
    from services.mtls_auth_service import MTLSAuthService
    uid, username, _ = make_user()
    c = app.test_client()
    assert _login(c, username).status_code == 200
    sid = _sid(c)
    _age(app, sid, days=2)
    monkeypatch.setattr(MTLSAuthService, 'is_mtls_enabled', staticmethod(lambda: True))
    monkeypatch.setattr(mtls_middleware, '_extract_certificate', lambda: {'serial': '0a'})
    _cert_login(monkeypatch, app, uid)
    with app.app_context():
        floor = db.session.query(db.func.max(AuditLog.id)).scalar() or 0
    return uid, floor, sid


def _age(app, sid, days):
    """Move the stored session's last activity back, as the inactivity timeout sees it."""
    iface = app.session_interface
    with app.app_context():
        store_id = iface._get_store_id(sid)
        data = iface._retrieve_session_data(store_id)
        data['last_activity'] = (utc_now() - timedelta(days=days)).isoformat()
        iface._upsert_session(app.permanent_session_lifetime, ServerSideSession(data, sid=sid), store_id)


@pytest.fixture
def written(app, monkeypatch):
    """Identifiers of every session the store saves from now on."""
    iface, seen = app.session_interface, []
    upsert = iface._upsert_session

    def record(lifetime, session, store_id):
        seen.append(session.sid)
        return upsert(lifetime, session, store_id)
    monkeypatch.setattr(iface, '_upsert_session', record)
    return seen


def _call(app, sid, path='/api/v2/account/profile'):
    c = app.test_client()
    c.set_cookie('session', sid)
    return c, c.get(path)


def _in_another_thread(fn):
    done, errors = threading.Event(), []

    def body():
        try:
            fn()
        except BaseException as exc:  # noqa: BLE001 - re-raised in the test thread
            errors.append(exc)
        finally:
            done.set()
    threading.Thread(target=body, daemon=True).start()
    assert done.wait(30)
    if errors:
        raise errors[0]


def _parallel_after_expiry(app, sid, monkeypatch):
    """While the first call holds the expired session, the others run to completion
    in their own threads; the clients of every call, first one last."""
    timeout, clients = AuthManager._get_session_timeout, []

    def siblings_first():
        monkeypatch.setattr(AuthManager, '_get_session_timeout', staticmethod(timeout))
        for _ in range(PARALLEL - 1):
            _in_another_thread(lambda: clients.append(_call(app, sid)))
        return timeout()
    monkeypatch.setattr(AuthManager, '_get_session_timeout', staticmethod(siblings_first))
    clients.append(_call(app, sid))
    return clients


def test_parallel_calls_after_expiry_open_one_session(app, cert_user, written, monkeypatch):
    _uid, _floor, sid = cert_user
    clients = _parallel_after_expiry(app, sid, monkeypatch)
    assert [r.status_code for _c, r in clients] == [200] * PARALLEL
    sids = {_sid(c) for c, _r in clients}
    assert len(sids) == 1 and sid not in sids and set(written) == sids
    assert _stored(app, sids.pop()) and not _stored(app, sid)
    assert _logins(app, cert_user[:2]) == 1


def test_a_call_after_a_sibling_replaced_the_session_joins_it(app, cert_user, written):
    """The cookie now names no stored session: the late call takes the same new one."""
    _uid, _floor, sid = cert_user
    first, r = _call(app, sid)
    assert r.status_code == 200
    late, r = _call(app, sid, '/login')
    assert _sid(late) == _sid(first) != sid and set(written) == {_sid(first)}
    assert late.get('/api/v2/auth/verify').status_code == 200
    assert _logins(app, cert_user[:2]) == 1


def test_an_api_client_without_a_cookie_still_logs_in(app, cert_user):
    """curl with a client certificate and no cookie jar authenticates on every call."""
    _uid, _floor, sid = cert_user
    _call(app, sid)
    c = app.test_client()
    assert c.get('/api/v2/account/profile').status_code == 200
    assert _logins(app, cert_user[:2]) == 2


def test_another_certificate_does_not_join(app, cert_user, make_user, monkeypatch):
    _uid, _floor, sid = cert_user
    first, _r = _call(app, sid)
    other, _name, _ = make_user()
    _cert_login(monkeypatch, app, other)
    stranger, r = _call(app, sid)
    assert r.status_code == 200 and _sid(stranger) not in (sid, _sid(first))


def test_a_closed_successor_is_not_joined(app, cert_user):
    _uid, _floor, sid = cert_user
    first, _r = _call(app, sid)
    first.post('/api/v2/auth/logout')
    late, r = _call(app, sid)
    assert r.status_code == 200 and _sid(late) not in (sid, _sid(first))
    assert _logins(app, cert_user[:2]) == 2


def test_the_successor_is_joined_only_for_a_while(app, cert_user, monkeypatch):
    import middleware.mtls_middleware as mtls_middleware
    monkeypatch.setattr(mtls_middleware, 'SUCCESSOR_TTL', -1)
    _uid, _floor, sid = cert_user
    first, _r = _call(app, sid)
    late, _r = _call(app, sid)
    assert _sid(late) not in (sid, _sid(first))


def test_a_planted_identifier_never_leads_to_the_new_session(app, make_user, monkeypatch):
    """Fixation: a stored identifier the login replaced is not an expired session,
    so the certificate's new session is never handed to whoever planted it."""
    import middleware.mtls_middleware as mtls_middleware
    from services.mtls_auth_service import MTLSAuthService
    from tests.test_session_lifecycle import _planted, _victim
    uid, _username, _ = make_user()
    planted = _planted(app, make_user)
    monkeypatch.setattr(MTLSAuthService, 'is_mtls_enabled', staticmethod(lambda: True))
    monkeypatch.setattr(mtls_middleware, '_extract_certificate', lambda: {'serial': '0a'})
    _cert_login(monkeypatch, app, uid)
    victim = _victim(app, planted)
    victim.get('/api/v2/account/profile')
    attacker = _victim(app, planted)
    attacker.get('/api/v2/account/profile')
    assert _sid(attacker) not in (planted, _sid(victim))


def test_without_a_certificate_an_expired_session_stays_closed(app, cert_user, written, monkeypatch):
    import middleware.mtls_middleware as mtls_middleware
    monkeypatch.setattr(mtls_middleware, '_extract_certificate', lambda: None)
    _uid, _floor, sid = cert_user
    assert _call(app, sid)[1].status_code == 401
    assert written == [] and _logins(app, cert_user[:2]) == 0


def test_calls_arriving_while_the_first_still_logs_in_join_it(app, cert_user, written, monkeypatch):
    """The new session is stored before the first call answers: the others read it."""
    from services.audit_service import AuditService
    _uid, _floor, sid = cert_user
    log_auth, clients = AuditService.log_auth, []

    def siblings_meanwhile(*args, **kwargs):
        monkeypatch.setattr(AuditService, 'log_auth', log_auth)
        for _ in range(PARALLEL - 1):
            _in_another_thread(lambda: clients.append(_call(app, sid)))
        return log_auth(*args, **kwargs)
    monkeypatch.setattr(AuditService, 'log_auth', staticmethod(siblings_meanwhile))
    clients.append(_call(app, sid))
    assert [r.status_code for _c, r in clients] == [200] * PARALLEL
    assert len({_sid(c) for c, _r in clients}) == 1 and len(set(written)) == 1
    assert _logins(app, cert_user[:2]) == 1


def test_a_successor_closed_by_a_credential_change_is_not_joined(app, cert_user):
    from models import User
    uid, _floor, sid = cert_user
    first, _r = _call(app, sid)
    with app.app_context():
        db.session.get(User, uid).end_sessions()
        db.session.commit()
    late, r = _call(app, sid)
    assert r.status_code == 200 and _sid(late) not in (sid, _sid(first))
