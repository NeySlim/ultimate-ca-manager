"""HA on PostgreSQL: node A rotates the session key, node B reloads it through the cluster command.

Node B is a second Flask application on the same schema, holding its own signing keys; its
CommandApplier replays reload_secret_key over a connection of its own, as on a second host.
The session id is not signed (server-side store): only CSRF tokens depend on the key.
"""
import secrets
import time
from datetime import timedelta

import pytest
from flask import Flask

from config.settings import Config
from models import db
from services import cluster_commands as cc
from tests import pg_app_harness
from tests.test_session_key_rotation import (  # noqa: F401  (fixtures)
    _later, _no_host_side_effects, stored,
)
from utils.datetime_utils import utc_now

pytestmark = pytest.mark.skipif(not pg_app_harness.ENABLED,
                                reason='needs UCM_TEST_APP_PG_URL (HA runs on PostgreSQL)')

PREFIX = f'sk-{secrets.token_hex(3)}-'


def wait_for(predicate, timeout=8.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


@pytest.fixture
def node_b(app, stored, encryption_enabled, monkeypatch):
    """A second application on the session database, started before the rotation."""
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.setattr(cc, 'GAP_GRACE_SECONDS', 0.3)
    b = Flask('node_b')
    b.config.update(SQLALCHEMY_DATABASE_URI=app.config['SQLALCHEMY_DATABASE_URI'],
                    SQLALCHEMY_ENGINE_OPTIONS=app.config.get('SQLALCHEMY_ENGINE_OPTIONS', {}),
                    SECRET_KEY=stored.environment_key(app))
    db.init_app(b)
    with b.app_context():
        stored.load_keys(b, at_start=True)  # as create_app does
    applier = cc.CommandApplier(b, PREFIX + 'b', tick=0.05, record=False,
                                started_at=utc_now() - timedelta(seconds=30))
    yield b, applier
    applier.stop()
    with b.app_context():
        db.session.remove()
        db.engine.dispose()


def _csrf(app, user_id=1):
    from security.csrf import CSRFProtection
    with app.app_context():
        return CSRFProtection.generate_token(user_id)


def _valid(app, token, user_id=1):
    from security.csrf import CSRFProtection
    with app.app_context():
        return CSRFProtection.validate_token(token, user_id)[0]


def test_a_rotation_on_a_reaches_b_and_both_accept_the_previous_key_during_the_grace(
        app, auth_client, stored, node_b, monkeypatch):
    from models import ClusterCommand
    b, applier = node_b
    from_b = _csrf(b)
    assert _valid(app, from_b)
    r = auth_client.post('/api/v2/system/security/rotate-secrets', json={})
    assert r.status_code == 200, r.data
    new = app.config['SECRET_KEY']
    assert new != stored.environment_key(app) and b.config['SECRET_KEY'] != new
    with app.app_context():
        payloads = [c.payload for c in ClusterCommand.query.filter_by(kind='reload_secret_key')]
    assert payloads == [None]

    applier.start()
    assert wait_for(lambda: b.config['SECRET_KEY'] == new)
    from_a = _csrf(app)
    assert _valid(app, from_b) and _valid(b, from_b)
    assert _valid(b, from_a)
    # The session is a server-side record, not signed: the rotation leaves it alone
    assert auth_client.get('/api/v2/auth/verify').get_json()['data']['authenticated']

    _later(monkeypatch, stored.GRACE_SECONDS + 1)
    with app.app_context():
        assert stored.retire_if_due(app) is True
    # The command alone empties B's memory: nothing on B has checked a token since
    assert wait_for(lambda: b.extensions[stored._STATE]['previous_until'] is None)
    assert b.config['SECRET_KEY_FALLBACKS'] == []
    assert not _valid(app, from_b) and not _valid(b, from_b)
    assert _valid(app, from_a) and _valid(b, from_a)

