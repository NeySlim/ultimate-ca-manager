"""A session of a deleted account does not open the account that takes its id.

SQLite used to give a new row the id of the last one deleted, and the session
cookie only held that id and a session version both accounts start at 0. The
session now also carries the account's creation time, compared on every
request. Ids are no longer reused (migration 150): the scenarios move the new
account onto the old id themselves, so this defence stays proven on its own.
"""
from sqlalchemy import text
import json

import pytest

from models import db, User, APIKey

PROTECTED = '/api/v2/account/apikeys'


def _login(app, username):
    client = app.test_client()
    answer = client.post('/api/v2/auth/login',
                         data=json.dumps({'username': username, 'password': 'TestPass123!'}),
                         content_type='application/json')
    assert answer.status_code == 200, answer.data[:300]
    return client


def _delete_last(app, auth_client, user_id):
    """Delete the account through the API and check its row is gone."""
    assert auth_client.delete(f'/api/v2/users/{user_id}').status_code == 200
    with app.app_context():
        assert db.session.get(User, user_id) is None


def _reuses(app, old, new):
    """Give the new account the old one's id, as SQLite did before migration 150."""
    with app.app_context():
        db.session.execute(text(f'UPDATE {User.__tablename__} SET id = :old WHERE id = :new'),
                           {'old': old['id'], 'new': new['id']})
        db.session.commit()
    new['id'] = old['id']


@pytest.fixture
def cleanup(app):
    names = []
    yield names
    with app.app_context():
        for name in names:
            user = User.query.filter_by(username=name).first()
            if user is not None:
                APIKey.query.filter_by(user_id=user.id).delete()
                db.session.delete(user)
        db.session.commit()


class TestAReusedIdIsAnotherAccount:
    def test_the_old_cookie_is_refused(self, app, auth_client, create_user, cleanup):
        cleanup.extend(['reused_id_first', 'reused_id_second'])
        first = create_user(username='reused_id_first', role='operator')
        old_session = _login(app, 'reused_id_first')
        assert old_session.get(PROTECTED).status_code == 200

        _delete_last(app, auth_client, first['id'])
        second = create_user(username='reused_id_second', role='admin')
        _reuses(app, first, second)

        assert old_session.get(PROTECTED).status_code == 401
        # The new account's own login is unaffected
        assert _login(app, 'reused_id_second').get(PROTECTED).status_code == 200

    def test_an_api_key_goes_with_its_account(self, app, auth_client, create_user, cleanup):
        cleanup.extend(['reused_key_first', 'reused_key_second'])
        first = create_user(username='reused_key_first', role='operator')
        owner = _login(app, 'reused_key_first')
        made = owner.post(PROTECTED, data=json.dumps({'name': 'probe', 'permissions': ['read:certificates']}),
                          content_type='application/json')
        assert made.status_code == 201, made.data[:300]
        key = json.loads(made.data)['data']['key']
        assert app.test_client().get('/api/v2/certificates', headers={'X-API-Key': key}).status_code == 200

        _delete_last(app, auth_client, first['id'])
        second = create_user(username='reused_key_second', role='admin')
        _reuses(app, first, second)
        with app.app_context():
            assert APIKey.query.filter_by(user_id=second['id']).count() == 0
        assert app.test_client().get('/api/v2/certificates', headers={'X-API-Key': key}).status_code == 401


class TestASessionOpenedBeforeTheUpdate:
    def test_is_kept_and_bound_on_its_next_request(self, app, create_user, cleanup):
        from auth.session_start import ACCOUNT_KEY
        cleanup.append('proofless_session')
        create_user(username='proofless_session', role='operator')
        client = _login(app, 'proofless_session')
        with client.session_transaction() as stored:
            assert stored.pop(ACCOUNT_KEY, None) is not None
        assert client.get(PROTECTED).status_code == 200
        with client.session_transaction() as stored:
            assert stored.get(ACCOUNT_KEY)

    def test_is_refused_by_the_account_that_took_its_id(self, app, auth_client, create_user, cleanup):
        from auth.session_start import ACCOUNT_KEY
        cleanup.extend(['proofless_first', 'proofless_second'])
        first = create_user(username='proofless_first', role='operator')
        old_session = _login(app, 'proofless_first')
        with old_session.session_transaction() as stored:
            assert stored.pop(ACCOUNT_KEY, None) is not None

        _delete_last(app, auth_client, first['id'])
        second = create_user(username='proofless_second', role='admin')
        _reuses(app, first, second)

        assert old_session.get(PROTECTED).status_code == 401
        with old_session.session_transaction() as stored:
            assert ACCOUNT_KEY not in stored
        assert _login(app, 'proofless_second').get(PROTECTED).status_code == 200

    def test_is_refused_by_a_namesake_that_took_its_id(self, app, auth_client, create_user, cleanup):
        from auth.session_start import ACCOUNT_KEY
        cleanup.append('proofless_namesake')
        first = create_user(username='proofless_namesake', role='operator')
        old_session = _login(app, 'proofless_namesake')
        with old_session.session_transaction() as stored:
            assert stored.pop(ACCOUNT_KEY, None) is not None

        _delete_last(app, auth_client, first['id'])
        second = create_user(username='proofless_namesake', role='admin')
        _reuses(app, first, second)

        assert old_session.get(PROTECTED).status_code == 401
        assert _login(app, 'proofless_namesake').get(PROTECTED).status_code == 200

    def test_is_refused_by_an_undated_account_that_took_its_id(self, app, auth_client, create_user, cleanup):
        # An account without a creation time leaves the username as the only binding
        from auth.session_start import ACCOUNT_KEY
        cleanup.extend(['proofless_dated', 'proofless_undated'])
        first = create_user(username='proofless_dated', role='operator')
        old_session = _login(app, 'proofless_dated')
        with old_session.session_transaction() as stored:
            assert stored.pop(ACCOUNT_KEY, None) is not None

        _delete_last(app, auth_client, first['id'])
        second = create_user(username='proofless_undated', role='admin')
        _reuses(app, first, second)
        with app.app_context():
            db.session.get(User, second['id']).created_at = None
            db.session.commit()

        assert old_session.get(PROTECTED).status_code == 401

    def test_without_a_login_time_is_refused(self, app, create_user, cleanup):
        from auth.session_start import ACCOUNT_KEY
        cleanup.append('proofless_no_time')
        create_user(username='proofless_no_time', role='operator')
        client = _login(app, 'proofless_no_time')
        with client.session_transaction() as stored:
            assert stored.pop(ACCOUNT_KEY, None) is not None
            assert stored.pop('login_time', None) is not None
        assert client.get(PROTECTED).status_code == 401


class TestAPending2faSessionOpenedBeforeTheUpdate:
    """Known effect of the update: a second-factor step begun before it holds no
    proof and no login time, so it is refused and the password is asked again."""

    def test_is_refused_and_a_new_login_completes(self, app, create_user, cleanup):
        import pyotp
        from auth.session_start import ACCOUNT_KEY
        cleanup.append('proofless_pending_2fa')
        made = create_user(username='proofless_pending_2fa', role='operator')
        secret = pyotp.random_base32()
        with app.app_context():
            user = db.session.get(User, made['id'])
            user.totp_secret, user.totp_confirmed = secret, True
            db.session.commit()

        def _password_step():
            client = app.test_client()
            answer = client.post('/api/v2/auth/login', content_type='application/json', data=json.dumps(
                {'username': 'proofless_pending_2fa', 'password': 'TestPass123!'}))
            assert json.loads(answer.data)['data'].get('requires_2fa') is True, answer.data[:300]
            return client

        def _second_step(client):
            return client.post('/api/v2/auth/login/2fa', content_type='application/json',
                               data=json.dumps({'code': pyotp.TOTP(secret).now()}))

        pending = _password_step()
        with pending.session_transaction() as stored:
            assert stored.pop(ACCOUNT_KEY, None) is not None
        assert _second_step(pending).status_code == 401
        with pending.session_transaction() as stored:
            assert 'pending_2fa_user_id' not in stored

        fresh = _password_step()
        assert _second_step(fresh).status_code == 200
        assert fresh.get(PROTECTED).status_code == 200
