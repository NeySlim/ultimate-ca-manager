"""The fresh app of tests.fresh_app: its own empty database, and nothing left behind."""
import json

from config.settings import Config
from tests.fresh_app import fresh_app, fresh_app_fixtures


def _certificate_count(app):
    from models import Certificate
    with app.app_context():
        return Certificate.query.count()


def test_it_has_a_database_of_its_own(app, create_cert):
    create_cert(cn='session-side.example.com')
    with fresh_app() as other:
        assert other is not app
        assert _certificate_count(other) == 0
        assert _certificate_count(app) >= 1


def test_its_paths_and_scheduler_are_put_back(app):
    from services import scheduler_service
    before = {name: getattr(Config, name) for name in ('BACKUP_DIR', 'HTTPS_CERT_PATH')}
    scheduler = scheduler_service._scheduler
    with fresh_app() as other:
        assert other.config['BACKUP_DIR'] != before['BACKUP_DIR']
        assert Config.BACKUP_DIR == other.config['BACKUP_DIR']
    assert {name: getattr(Config, name) for name in before} == before
    assert scheduler_service._scheduler is scheduler


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
