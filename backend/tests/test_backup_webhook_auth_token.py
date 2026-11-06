"""A webhook's authentication token travels in the clear only, never as the source's ciphertext."""
import pytest

from models import db
from services.backup.export_generic import IdentityIndex, export_section
from tests.test_backup_restore_failfast import PASSWORD, _only, _reseal, _service

NAME = 'auth-token-archive-hook'
TOKEN = 'bearer-token-of-the-source'


@pytest.fixture
def endpoint(app):
    from services.webhook_service import WebhookEndpoint
    with app.app_context():
        hook = WebhookEndpoint(name=NAME, url='https://hook.example.test/token', auth_type='bearer')
        hook.auth_token = TOKEN
        db.session.add(hook)
        db.session.commit()
    yield
    with app.app_context():
        db.session.rollback()
        WebhookEndpoint.query.filter_by(name=NAME).delete()
        db.session.commit()


def test_the_archive_carries_the_token_once_in_the_clear(app, endpoint):
    with app.app_context():
        row = next(r for r in export_section('webhook_endpoints', IdentityIndex()) if r['name'] == NAME)
    assert row['auth_token'] == TOKEN
    assert '_auth_token' not in row


@pytest.mark.parametrize('clear', [TOKEN, None], ids=['with-the-clear-token', 'ciphertext-only'])
def test_an_older_archives_ciphertext_is_ignored(app, endpoint, clear):
    from services.webhook_service import WebhookEndpoint
    from utils.encryption import decrypt_if_needed
    with app.app_context():
        svc = _service()
        blob = svc.create_backup(PASSWORD, include=_only('webhook_endpoints'))
        _key, data = svc._decrypt_framed(blob, PASSWORD)
        row = next(r for r in data['webhook_endpoints'] if r['name'] == NAME)
        # As an archive before this version wrote it: the source's ciphertext, unusable here
        row['_auth_token'] = 'gAAAAA-sealed-under-another-installation'
        if clear is None:
            del row['auth_token']
        WebhookEndpoint.query.filter_by(name=NAME).delete()
        db.session.commit()

        svc.restore_backup(_reseal(blob, data), PASSWORD, mode='merge')
        db.session.expire_all()
        back = WebhookEndpoint.query.filter_by(name=NAME).one()
        assert back.auth_token == clear
        if clear:
            assert back._auth_token != TOKEN and decrypt_if_needed(back._auth_token) == TOKEN
        else:
            assert back._auth_token is None
