"""The fresh app of tests.fresh_app: its own empty database, and nothing left behind."""
import json

from config.settings import Config
from tests.fresh_app import fresh_app, fresh_app_fixtures


def _certificate_count(app):
    from models import Certificate
    with app.app_context():
        return Certificate.query.count()


def test_it_has_a_database_of_its_own(app, create_ca, create_cert):
    # Its own CA: the session's default one stays, other tests' certificates sit under it
    ca = create_ca(cn='Fresh App Own CA')
    cert = create_cert(cn='session-side.example.com', ca_id=ca['id'])
    try:
        with fresh_app() as other:
            assert other is not app
            assert _certificate_count(other) == 0
            assert _certificate_count(app) >= 1
    finally:
        from models import CA, Certificate, db
        with app.app_context():
            Certificate.query.filter_by(id=cert['id']).delete()
            CA.query.filter_by(id=ca['id']).delete()
            db.session.commit()


def test_its_paths_and_scheduler_are_put_back(app):
    from services import scheduler_service
    before = {name: getattr(Config, name) for name in ('BACKUP_DIR', 'HTTPS_CERT_PATH')}
    scheduler = scheduler_service._scheduler
    with fresh_app() as other:
        assert other.config['BACKUP_DIR'] != before['BACKUP_DIR']
        assert Config.BACKUP_DIR == other.config['BACKUP_DIR']
    assert {name: getattr(Config, name) for name in before} == before
    assert scheduler_service._scheduler is scheduler


def test_its_session_store_is_its_own_even_when_the_testing_config_pins_one(app, monkeypatch, tmp_path):
    """On PostgreSQL TestingConfig carries a SESSION_FILE_DIR of its own, which shadows Config's."""
    from config.settings import config
    pinned = tmp_path / 'pinned'
    monkeypatch.setattr(config['testing'], 'SESSION_FILE_DIR', pinned, raising=False)
    with fresh_app() as other:
        assert str(other.config['SESSION_FILE_DIR']) != str(pinned)
        assert str(other.config['SESSION_FILE_DIR']) != str(app.config['SESSION_FILE_DIR'])
    assert config['testing'].SESSION_FILE_DIR == pinned


def test_its_restores_do_not_sign_the_session_app_out(auth_client):
    from services.backup.restore.invalidate import invalidate_after_restore
    signed_in = auth_client._client  # the raw client: no silent sign-in again
    assert signed_in.get('/api/v2/users').status_code == 200
    with fresh_app() as other:
        fresh_admin = other.test_client()
        assert fresh_admin.post('/api/v2/auth/login', json={
            'username': 'admin', 'password': 'changeme123'}).status_code == 200
        with other.app_context():
            assert invalidate_after_restore()['session_files_removed'] >= 1
        assert fresh_admin.get('/api/v2/users').status_code == 401
    assert signed_in.get('/api/v2/users').status_code == 200


class TestTheClassVariant:
    app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures('class')

    def test_its_factories_write_to_the_fresh_database(self, app, auth_client, create_cert):
        from tests.conftest import _SESSION_APP
        assert not _SESSION_APP or app is not _SESSION_APP[0]
        cert = create_cert(cn='fresh-side.example.com')
        assert _certificate_count(app) == 1
        r = auth_client.get(f"/api/v2/certificates/{cert['id']}")
        assert json.loads(r.data)['data']['refid'] == cert['refid']


def test_outside_the_class_the_session_app_is_back(app):
    from tests.conftest import _SESSION_APP
    assert app is _SESSION_APP[0]
