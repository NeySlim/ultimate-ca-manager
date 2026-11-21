"""The ACME client certificate key type has one default, shown by the settings and used
for the key it generates; the ACME account key keeps its own constant."""
import pytest

from models import SystemConfig, db
from utils import issuance_defaults


@pytest.fixture
def unset_key_type(app):
    with app.app_context():
        row = SystemConfig.query.filter_by(key='acme.client.key_type').first()
        saved = row.value if row else None
        if row:
            db.session.delete(row)
            db.session.commit()
    yield
    with app.app_context():
        SystemConfig.query.filter_by(key='acme.client.key_type').delete()
        if saved is not None:
            db.session.add(SystemConfig(key='acme.client.key_type', value=saved))
        db.session.commit()


def test_settings_and_generated_key_share_the_default(app, auth_client, unset_key_type, monkeypatch):
    from services.acme.acme_client_service import AcmeClientService
    monkeypatch.setattr(issuance_defaults, 'DEFAULT_ACME_CLIENT_CERT_KEY_TYPE', 'EC-P256')
    monkeypatch.setattr(issuance_defaults, 'DEFAULT_ACME_ACCOUNT_KEY_TYPE', 'RSA-4096')
    r = auth_client.get('/api/v2/acme/client/settings')
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['data']['key_type'] == 'EC-P256'
    with app.app_context():
        assert AcmeClientService._get_default_key_type() == 'EC-P256'
