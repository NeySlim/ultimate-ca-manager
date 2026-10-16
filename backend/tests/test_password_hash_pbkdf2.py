"""Passwords and secrets hash with PBKDF2-HMAC-SHA256, which a FIPS module
approves; a FIPS provider refuses scrypt, and UCM failed to seed its admin.
Older scrypt hashes still verify and are replaced at the next login."""
import hashlib
import json
import uuid

import pytest
from werkzeug.security import generate_password_hash

from models import SystemConfig, User, db
from utils.backup_codes import consume_code, hash_codes, verify_code_only
from utils.password_hash import PASSWORD_METHOD, hash_password, verify_password

CONTENT_JSON = 'application/json'
PBKDF2 = PASSWORD_METHOD + '$'


@pytest.fixture
def fips_scrypt(monkeypatch):
    """hashlib.scrypt as a FIPS provider leaves it."""
    def _refused(*args, **kwargs):
        raise ValueError('[digital envelope routines] unsupported')
    monkeypatch.setattr(hashlib, 'scrypt', _refused)


def _user(app, password_hash):
    name = f'pw-{uuid.uuid4().hex[:8]}'
    with app.app_context():
        user = User(username=name, email=f'{name}@example.test', role='viewer',
                    active=True, password_hash=password_hash)
        db.session.add(user)
        db.session.commit()
        return name, user.id


def _hash_of(app, user_id):
    with app.app_context():
        return db.session.get(User, user_id).password_hash


def _drop(app, user_id):
    with app.app_context():
        user = db.session.get(User, user_id)
        if user is not None:
            db.session.delete(user)
            db.session.commit()


def _login(app, username, password):
    return app.test_client().post('/api/v2/auth/login', content_type=CONTENT_JSON,
                                  data=json.dumps({'username': username, 'password': password}))


def test_new_hashes_are_pbkdf2_without_scrypt(fips_scrypt):
    user = User(username='x')
    user.set_password('S3cret-pass!')
    assert user.password_hash.startswith(PBKDF2)
    assert user.check_password('S3cret-pass!') and not user.check_password('wrong')
    assert json.loads(hash_codes(['ABCD-EF01']))[0].startswith(PBKDF2)


def test_a_scrypt_password_is_replaced_at_login(app):
    name, uid = _user(app, generate_password_hash('Old-scrypt-pw1', method='scrypt'))
    try:
        assert _login(app, name, 'Wrong-pw-123').status_code == 401
        assert _hash_of(app, uid).startswith('scrypt:')
        assert _login(app, name, 'Old-scrypt-pw1').status_code == 200
        assert _hash_of(app, uid).startswith(PBKDF2)
        assert _login(app, name, 'Old-scrypt-pw1').status_code == 200
    finally:
        _drop(app, uid)


def test_a_refused_scrypt_hash_is_a_failed_login_not_an_error(app, fips_scrypt):
    name, uid = _user(app, 'scrypt:32768:8:1$c2FsdHNhbHQ$' + '0' * 128)
    try:
        assert verify_password('scrypt:32768:8:1$salt$00', 'pw') is False
        assert _login(app, name, 'Whatever-pw1').status_code == 401
    finally:
        _drop(app, uid)


def test_backup_codes_keep_working_across_the_change(app):
    old = json.dumps([generate_password_hash('AAAA-BBBB', method='scrypt')])
    assert verify_code_only(old, 'AAAA-BBBB')
    new = hash_codes(['CCCC-DDDD', 'EEEE-FFFF'])
    assert all(h.startswith(PBKDF2) for h in json.loads(new))
    assert verify_code_only(new, 'EEEE-FFFF') and not verify_code_only(new, 'AAAA-BBBB')
    name, uid = _user(app, hash_password('Unused-pw-123'))
    try:
        with app.app_context():
            user = db.session.get(User, uid)
            user.backup_codes = new
            db.session.commit()
            assert consume_code(user, 'CCCC-DDDD')
    finally:
        _drop(app, uid)


def test_the_change_password_route_stores_pbkdf2(app, fips_scrypt):
    name, uid = _user(app, hash_password('Current-pw-123'))
    try:
        c = app.test_client()
        assert c.post('/api/v2/auth/login', content_type=CONTENT_JSON, data=json.dumps(
            {'username': name, 'password': 'Current-pw-123'})).status_code == 200
        r = c.post('/api/v2/account/password', content_type=CONTENT_JSON, data=json.dumps(
            {'current_password': 'Current-pw-123', 'new_password': 'Brand-New-pw-456!'}))
        assert r.status_code == 200, r.data
        assert _hash_of(app, uid).startswith(PBKDF2)
    finally:
        _drop(app, uid)


@pytest.mark.parametrize('route,key', [('/api/v2/est/config', 'est_password'),
                                       ('/api/v2/wstep/config', 'wstep_password'),
                                       ('/api/v2/xcep/config', 'xcep_password')])
def test_protocol_passwords_are_pbkdf2(app, auth_client, fips_scrypt, route, key):
    with app.app_context():
        row = SystemConfig.query.filter_by(key=key).first()
        before = row.value if row else None
    try:
        r = auth_client.patch(route, content_type=CONTENT_JSON,
                              data=json.dumps({'password': 'Proto-pw-789!'}))
        assert r.status_code == 200, r.data
        with app.app_context():
            stored = SystemConfig.query.filter_by(key=key).first().value
        assert stored.startswith(PBKDF2) and verify_password(stored, 'Proto-pw-789!')
    finally:
        with app.app_context():
            row = SystemConfig.query.filter_by(key=key).first()
            if before is None and row is not None:
                db.session.delete(row)
            elif row is not None:
                row.value = before
            db.session.commit()


def test_the_salt_carries_128_bits():
    salt = hash_password('S3cret-pass!').split('$')[1]
    assert len(salt) >= 22  # 62-symbol alphabet: 22 characters > 128 bits (SP 800-132)


def test_a_non_string_password_is_refused_not_an_error(app):
    assert verify_password(hash_password('12345678'), 12345678) is False
    name, uid = _user(app, hash_password('Current-pw-123'))
    try:
        c = app.test_client()
        assert c.post('/api/v2/auth/login', content_type=CONTENT_JSON, data=json.dumps(
            {'username': name, 'password': 'Current-pw-123'})).status_code == 200
        r = c.post('/api/v2/account/password', content_type=CONTENT_JSON, data=json.dumps(
            {'current_password': 12345678, 'new_password': 'Brand-New-pw-456!'}))
        assert r.status_code == 401, r.data
    finally:
        _drop(app, uid)
