"""A session of a deleted account does not open the account that takes its id.

SQLite gives a new row the id of the last one deleted (INTEGER PRIMARY KEY
without AUTOINCREMENT), and the session cookie only held that id and a session
version both accounts start at 0. The session now also carries the account's
creation time, compared on every request.
"""
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
    """Delete the account, then make sure it was the last row so its id comes back."""
    assert auth_client.delete(f'/api/v2/users/{user_id}').status_code == 200
    with app.app_context():
        assert db.session.get(User, user_id) is None


def _reuses(app, old_id, new_id):
    with app.app_context():
        if db.engine.dialect.name == 'sqlite':
            assert new_id == old_id, 'the scenario needs the id handed out again'


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
        _reuses(app, first['id'], second['id'])

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
        _reuses(app, first['id'], second['id'])
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
