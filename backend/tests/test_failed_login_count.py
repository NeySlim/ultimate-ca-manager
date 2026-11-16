"""Every failed password counts toward the lockout, even when another node counted one
while this request was checking the password: a lost count is a free guess."""
import uuid

import pytest
from sqlalchemy import select

from models import User, db

PASSWORD = 'Counted-Passw0rd!'
TABLE = User.__table__


@pytest.fixture
def username(app):
    name = f'cnt{uuid.uuid4().hex[:8]}'
    with app.app_context():
        user = User(username=name, email=f'{name}@example.test', role='viewer')
        user.set_password(PASSWORD)
        db.session.add(user)
        db.session.commit()
    yield name
    with app.app_context():
        User.query.filter_by(username=name).delete(synchronize_session=False)
        db.session.commit()


def _another_node_counted(name, failures):
    with db.engine.begin() as conn:
        conn.execute(TABLE.update().where(TABLE.c.username == name).values(failed_logins=failures))


def _stored(name):
    with db.engine.connect() as conn:
        return conn.execute(select(TABLE.c.failed_logins, TABLE.c.locked_until)
                            .where(TABLE.c.username == name)).one()


def _max_attempts():
    from api.v2.sso.helpers import _get_ldap_lockout_settings
    return _get_ldap_lockout_settings()[0]


def test_a_wrong_password_counts_on_top_of_another_nodes_failures(app, client, username, monkeypatch):
    with app.app_context():
        threshold = _max_attempts()

    def another_node_fails_meanwhile(self, password):
        _another_node_counted(self.username, threshold - 1)
        return False

    monkeypatch.setattr(User, 'check_password', another_node_fails_meanwhile)
    response = client.post('/api/v2/auth/login/password',
                           json={'username': username, 'password': 'wrong'})
    assert response.status_code == 401
    with app.app_context():
        failures, locked_until = _stored(username)
    assert failures == threshold and locked_until is not None


def test_an_ldap_failure_counts_on_top_of_another_nodes_failures(app, username):
    from api.v2.sso.helpers import _record_ldap_failed_attempt
    with app.app_context():
        threshold = _max_attempts()
        loaded = User.query.filter_by(username=username).one()  # as the lockout check left it
        assert (loaded.failed_logins or 0) == 0
        _another_node_counted(username, threshold - 1)
        _record_ldap_failed_attempt(username)
        failures, locked_until = _stored(username)
        assert failures == threshold and locked_until is not None
        assert loaded.failed_logins == threshold
        db.session.remove()
