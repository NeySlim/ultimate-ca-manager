"""Two requests changing one account's second factors run one at a time.

Disabling TOTP and removing the last security key each check that enforced
2FA keeps a factor. Without the user row lock, both checks read the state
before either commits and the account ends with neither. Only PostgreSQL can
show it: the suite's SQLite runs on a single connection.
"""
import os
import threading
import time

import pytest

from models import SystemConfig, User, db
from models.webauthn import WebAuthnCredential
from tests.test_backup_cross_installation import _bound_to
from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own

_PG_URL = os.environ.get('UCM_TEST_PG_URL')

pytestmark = [pytest.mark.postgres,
              pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')]

HOLD_SECONDS = 1.0


@pytest.fixture
def on_postgresql(app):
    with _a_schema_of_our_own('second_factor_lock') as url, _bound_to(app, url, is_postgresql=True):
        with app.app_context():
            db.session.add(SystemConfig(key='enforce_2fa', value='true'))
            user = User(username='lock-race', email='lock-race@example.test', role='operator',
                        totp_secret='JBSWY3DPEHPK3PXP', totp_confirmed=True)
            user.set_password('Lock-Race-Pass1!')
            db.session.add(user)
            db.session.flush()
            key = WebAuthnCredential(user_id=user.id, credential_id=b'lock-race-key',
                                     public_key=b'\x00' * 32, sign_count=0)
            db.session.add(key)
            db.session.commit()
            ids = (user.id, key.id)
            db.session.remove()
        yield ids


def test_key_removal_waits_for_a_totp_disable_and_sees_it(app, on_postgresql):
    from auth import twofa_enforcement
    user_id, key_id = on_postgresql
    locked, result = threading.Event(), {}

    def disable_totp():
        with app.app_context():
            user = twofa_enforcement.lock_user(user_id)
            locked.set()
            time.sleep(HOLD_SECONDS)
            user.totp_confirmed = False
            db.session.commit()
            db.session.remove()

    def remove_key():
        with app.app_context():
            # Loaded first, as require_auth does: the lock must refresh it.
            seen = db.session.get(User, user_id)
            assert seen.totp_confirmed
            locked.wait(5)
            started = time.monotonic()
            _user, refused = twofa_enforcement.lock_for_factor_change(user_id, dropping_key=key_id)
            result['waited'] = time.monotonic() - started
            result['refused'] = refused
            if not refused:
                WebAuthnCredential.query.filter_by(id=key_id).delete()
            db.session.commit()
            db.session.remove()

    threads = [threading.Thread(target=disable_totp), threading.Thread(target=remove_key)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(15)

    assert result['refused'] is True
    assert result['waited'] >= HOLD_SECONDS * 0.8
    with app.app_context():
        assert WebAuthnCredential.query.filter_by(id=key_id).count() == 1
        db.session.remove()
