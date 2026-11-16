"""A TOTP secret pyotp refuses (under 112 bits, or not base32), restored or set
outside UCM, refuses its codes like wrong ones instead of failing the request."""
import logging

from models import User, db
from tests.test_webauthn_second_factor import _password, _post, make_user  # noqa: F401 (fixture)

SHORT = 'JBSWY3DPEHPK3PXP'  # 80 bits: pyotp 2.12 refuses it


RECOVERY = 'ABCD-EF01-2345-6789'


def _short_secret(app, username, confirmed):
    from utils.backup_codes import hash_codes
    with app.app_context():
        user = User.query.filter_by(username=username).first()
        user.totp_secret, user.totp_confirmed, user.totp_last_step = SHORT, confirmed, None
        user.backup_codes = hash_codes([RECOVERY]) if confirmed else None
        db.session.commit()


def test_matched_step_refuses_an_unusable_secret_and_logs_it_once(caplog):
    from auth.totp import matched_step
    with caplog.at_level(logging.WARNING, logger='auth.totp'):
        assert matched_step(SHORT, '123456') is None
        assert matched_step('01890189018901890189', '123456') is None
    unusable = [r for r in caplog.records if 'unusable' in r.getMessage()]
    assert len(unusable) == 2
    assert SHORT not in caplog.text and '0189' not in caplog.text


def test_a_login_with_an_unusable_secret_is_a_wrong_code(app, make_user):
    username, _key, _ = make_user(key=False)
    _short_secret(app, username, confirmed=True)
    c = app.test_client()
    assert _password(c, username).status_code == 200
    r = _post(c, '/api/v2/auth/login/2fa', {'code': '123456'})
    assert r.status_code == 401, r.data


def test_a_recovery_code_still_signs_in_over_an_unusable_secret(app, make_user):
    username, _key, _ = make_user(key=False)
    _short_secret(app, username, confirmed=True)
    c = app.test_client()
    assert _password(c, username).status_code == 200
    r = _post(c, '/api/v2/auth/login/2fa', {'code': RECOVERY})
    assert r.status_code == 200, r.data


def test_confirm_cannot_set_an_unusable_secret(app, make_user):
    username, _key, _ = make_user(totp=False, key=False)
    _short_secret(app, username, confirmed=False)
    c = app.test_client()
    assert _password(c, username).status_code == 200
    r = _post(c, '/api/v2/account/2fa/confirm', {'code': '123456'})
    assert r.status_code == 400 and r.get_json()['message'] == 'Invalid verification code', r.data
    with app.app_context():
        assert User.query.filter_by(username=username).first().totp_confirmed is False
