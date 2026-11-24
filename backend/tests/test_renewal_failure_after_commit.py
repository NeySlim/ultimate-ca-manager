"""A change committed, then the caller's own session not renewed: the change stands, so its
audit entry stands too, and the answer says the change is saved, never that it failed.

The renewal moves the caller's record to a new identifier (RFC 6265 §8.4). A store that
fails that move (database gone, record held) ends the request on an error, after the commit:
the audit is written before the move, and the answer names what happened.
"""
import pytest

from models import AuditLog, User, db
from tests.test_factor_change_sessions import (
    OPERATIONS, PASSWORD, SoftKey, _cleanup, _make_user, _open_session, _post, _signed_in)

NEW_PASSWORD = 'Renewal-Fails-After-0k!'
NOT_KEPT = 'The change is saved, but this session could not be kept: sign in again'


def _renewal_fails(monkeypatch, application, how='raises'):
    """The store fails the move of the caller's record: rotate() raises ('raises'), or the
    store refuses the write without raising ('busy': held, or paused by an HA maintenance)."""
    calls = []
    interface = type(application.session_interface)
    if how == 'raises':
        def rotate(self, session):
            calls.append(session.sid)
            session.store_refused = 'busy'
            raise RuntimeError('session store unreachable (test)')

        monkeypatch.setattr(interface, 'rotate', rotate)
        return calls
    upsert = interface._upsert_session

    def refusing(self, lifetime, session, store_id):
        if getattr(session, 'rotated_from', None):
            calls.append(session.sid)
            setattr(session, 'store_refused' if how == 'busy' else 'record_gone',
                    'busy' if how == 'busy' else True)
            return None
        return upsert(self, lifetime, session, store_id)

    monkeypatch.setattr(interface, '_upsert_session', refusing)
    return calls


def _admin(application, user):
    with application.app_context():
        db.session.execute(db.update(User).where(User.id == user['id']).values(role='admin'))
        db.session.commit()
        db.session.remove()


def _audited(application, action, user):
    with application.app_context():
        found = AuditLog.query.filter(
            AuditLog.action == action,
            (AuditLog.resource_name == user['username']) | (AuditLog.username == user['username']),
        ).count()
        db.session.remove()
        return found


def _password_is(application, user, password):
    with application.app_context():
        ok = db.session.get(User, user['id']).check_password(password)
        db.session.remove()
        return ok


def _change_password(application, c, user):
    return _post(c, '/api/v2/account/password',
                 {'current_password': PASSWORD, 'new_password': NEW_PASSWORD})


def _close_other_sessions(application, c, user):
    return _post(c, '/api/v2/account/sessions/revoke-all')


def _admin_resets_own_password(application, c, user):
    return _post(c, f"/api/v2/users/{user['id']}/reset-password",
                 {'current_password': PASSWORD, 'new_password': NEW_PASSWORD})


def _admin_updates_own_password(application, c, user):
    return c.put(f"/api/v2/users/{user['id']}",
                 json={'password': NEW_PASSWORD, 'current_password': PASSWORD})


def _admin_resets_own_2fa(application, c, user):
    return _post(c, f"/api/v2/users/{user['id']}/reset-2fa")


def _admin_key(method):
    def _call(application, c, user):
        url = f"/api/v2/users/{user['id']}/webauthn/{user['key_id']}"
        return c.delete(url) if method == 'delete' else c.patch(url, json={'enabled': False})
    return _call


# operation: (user it starts from, administrator, request, audit action, password it sets)
CHANGES = {name: (start, False, call, action, None)
           for name, (start, call, action) in OPERATIONS.items()}
CHANGES.update({
    'change-password': ({}, False, _change_password, 'password_change', NEW_PASSWORD),
    'close-other-sessions': ({}, False, _close_other_sessions, 'session_revoke_all', None),
    'admin-reset-own-password': ({}, True, _admin_resets_own_password, 'password_change',
                                 NEW_PASSWORD),
    'admin-update-own-password': ({}, True, _admin_updates_own_password, 'user_update',
                                  NEW_PASSWORD),
    'admin-reset-own-2fa': ({'totp': True}, True, _admin_resets_own_2fa, 'mfa_reset', None),
    'admin-delete-own-key': ({'key': True}, True, _admin_key('delete'), 'webauthn_admin_delete',
                             None),
    'admin-disable-own-key': ({'key': True}, True, _admin_key('patch'), 'webauthn_admin_disable',
                              None),
})


@pytest.mark.parametrize('how', ['raises', 'busy'])
@pytest.mark.parametrize('operation', sorted(CHANGES))
def test_a_renewal_that_fails_after_the_commit_keeps_the_audit_and_says_saved(
        app, monkeypatch, operation, how):
    start, admin, call, action, password = CHANGES[operation]
    start = dict(start)
    if start.pop('key', False):
        start['key'] = SoftKey()
    user = _make_user(app, **start)
    try:
        if admin:
            _admin(app, user)
        this = _open_session(app, user)
        renewals = _renewal_fails(monkeypatch, app, how)
        r = call(app, this, user)
        assert renewals, 'the operation never renewed the session'
        assert r.status_code == 500, r.data
        assert r.get_json()['message'] == NOT_KEPT
        assert _audited(app, action, user) == 1
        if password:
            assert _password_is(app, user, password)
        # The record left at its replaced version serves no more
        monkeypatch.undo()
        assert not _signed_in(this)
    finally:
        monkeypatch.undo()
        _cleanup(app, user)


def test_a_session_signed_out_during_its_renewal_is_not_a_failure(app, monkeypatch):
    """The record gone meanwhile is a concurrent sign-out: the change answers saved."""
    user = _make_user(app)
    try:
        this = _open_session(app, user)
        renewals = _renewal_fails(monkeypatch, app, 'gone')
        r = _change_password(app, this, user)
        assert renewals and r.status_code == 200, r.data
    finally:
        monkeypatch.undo()
        _cleanup(app, user)
