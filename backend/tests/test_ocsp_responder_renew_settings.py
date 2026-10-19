"""The OCSP responder auto-renewal switch and window are settable.

The daily task read `ocsp_responder_auto_renew` and
`ocsp_responder_renew_days`, but no screen or API wrote them.
"""
import json

import pytest

from models import SystemConfig, db
from services import ocsp_responder_renewal


@pytest.fixture
def clean(app):
    keys = ('ocsp_responder_auto_renew', 'ocsp_responder_renew_days')
    yield
    with app.app_context():
        SystemConfig.query.filter(SystemConfig.key.in_(keys)).delete(synchronize_session=False)
        db.session.commit()


def _patch(auth_client, body):
    return auth_client.patch('/api/v2/settings/general', data=json.dumps(body), content_type='application/json')


def test_the_settings_reach_the_renewal_task(app, auth_client, clean):
    data = auth_client.get('/api/v2/settings/general').get_json()['data']
    assert data['ocsp_responder_auto_renew'] is True and data['ocsp_responder_renew_days'] == 30
    assert _patch(auth_client, {'ocsp_responder_auto_renew': False, 'ocsp_responder_renew_days': 10}).status_code == 200
    with app.app_context():
        assert ocsp_responder_renewal.run_ocsp_responder_renewal() == {'renewed': 0, 'failed': 0, 'skipped': 0}
        assert ocsp_responder_renewal._renew_threshold_days(365) == 10
    data = auth_client.get('/api/v2/settings/general').get_json()['data']
    assert data['ocsp_responder_auto_renew'] is False and data['ocsp_responder_renew_days'] == 10


def test_the_window_is_bounded(auth_client, clean):
    assert _patch(auth_client, {'ocsp_responder_renew_days': 0}).status_code == 400
    assert _patch(auth_client, {'ocsp_responder_renew_days': 400}).status_code == 400
