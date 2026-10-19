"""Removing a second factor is checked under the user row lock.

A change committed by another request right before the lock is taken must be
seen by the check: the guard reads the account after locking it, never before.
The lock itself, on both backends, is exercised in test_second_factor_lock_concurrent.py.
"""
import pyotp
import pytest
from sqlalchemy import update

from models import User, db
from models.webauthn import WebAuthnCredential
from tests.test_2fa_security_key_enforcement import _key_ids, _key_session
from tests.test_webauthn_second_factor import enforce_2fa, make_user, _post  # noqa: F401 (fixtures)


@pytest.fixture
def competing(app, monkeypatch):
    """Run a change committed by "another request" right before the lock is taken."""
    from auth import twofa_enforcement
    real = twofa_enforcement.lock_user
    pending = []

    def lock_user(user_id):
        while pending:
            pending.pop()(user_id)
            db.session.commit()
        return real(user_id)

    monkeypatch.setattr(twofa_enforcement, 'lock_user', lock_user)
    return pending


def test_key_removal_rechecks_after_a_concurrent_totp_disable(app, make_user, enforce_2fa, competing):
    username, key, _ = make_user()
    c = _key_session(app, username, key)
    key_id, = _key_ids(app, username)
    competing.append(lambda uid: db.session.execute(
        update(User).where(User.id == uid).values(totp_confirmed=False)))
    assert c.delete(f'/api/v2/webauthn/credentials/{key_id}').status_code == 403
    assert _key_ids(app, username) == [key_id]


def test_totp_disable_rechecks_after_a_concurrent_key_removal(app, make_user, enforce_2fa, competing):
    username, key, secret = make_user()
    c = _key_session(app, username, key)
    competing.append(lambda uid: WebAuthnCredential.query.filter_by(user_id=uid).delete())
    r = _post(c, '/api/v2/account/2fa/disable', {'code': pyotp.TOTP(secret).now()})
    assert r.status_code == 403
    with app.app_context():
        assert User.query.filter_by(username=username).first().totp_confirmed is True
