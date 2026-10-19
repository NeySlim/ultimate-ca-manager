"""The private-address switch of the ACME server is reachable from the API.

`acme.allow_private_ips` was read by challenge validation but no screen or API
wrote it, and the in-app help pointed at a settings page that does not exist.
"""
import json

import pytest

from models import SystemConfig, db
from services.acme.acme_service import AcmeService


@pytest.fixture
def restore_flag(app):
    with app.app_context():
        row = SystemConfig.query.filter_by(key='acme.allow_private_ips').first()
        saved = row.value if row else None
    yield
    with app.app_context():
        row = SystemConfig.query.filter_by(key='acme.allow_private_ips').first()
        if saved is None:
            if row:
                db.session.delete(row)
        else:
            row.value = saved
        db.session.commit()


def _patch(auth_client, value):
    r = auth_client.patch('/api/v2/acme/settings', data=json.dumps({'allow_private_ips': value}),
                          content_type='application/json')
    assert r.status_code == 200, r.data


def test_default_is_on(app, auth_client, restore_flag):
    with app.app_context():
        SystemConfig.query.filter_by(key='acme.allow_private_ips').delete()
        db.session.commit()
    assert auth_client.get('/api/v2/acme/settings').get_json()['data']['allow_private_ips'] is True


def test_turning_it_off_reaches_challenge_validation(app, auth_client, restore_flag):
    _patch(auth_client, False)
    assert auth_client.get('/api/v2/acme/settings').get_json()['data']['allow_private_ips'] is False
    with app.app_context():
        assert AcmeService(base_url='http://localhost')._acme_allow_private_ips() is False

    _patch(auth_client, True)
    with app.app_context():
        assert AcmeService(base_url='http://localhost')._acme_allow_private_ips() is True
