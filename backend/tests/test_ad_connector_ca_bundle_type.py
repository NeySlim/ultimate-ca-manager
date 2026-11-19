"""A connector's `ca_bundle` that is not text answers 400, on save and on the unsaved test."""
import pytest

from tests.ad_connector_support import clear_connectors
from tests.windows_profile_support import connectors_kept

URL = '/api/v2/ad-connectors'
BASE = {'name': 'bundle-type', 'server': 'dc1.example.com', 'port': 636, 'use_ssl': True,
        'bind_dn': 'CN=svc,DC=example,DC=com', 'bind_password': 'irrelevant',
        'base_dn': 'DC=example,DC=com'}


@pytest.fixture(autouse=True)
def _connectors_put_back(app):
    with connectors_kept(app):
        with app.app_context():
            clear_connectors()
        yield


@pytest.mark.parametrize('bundle', [5, ['-----BEGIN CERTIFICATE-----'], {'pem': 'x'}, True])
@pytest.mark.parametrize('route', ['save', 'test'])
def test_a_ca_bundle_that_is_not_text_is_a_400(auth_client, route, bundle):
    path = URL if route == 'save' else f'{URL}/test'
    r = auth_client.post(path, json={**BASE, 'ca_bundle': bundle})
    assert r.status_code == 400, r.data[:300]
    assert 'ca_bundle' in r.get_json()['message']


def test_a_text_ca_bundle_is_still_saved(auth_client):
    r = auth_client.post(URL, json={**BASE, 'ca_bundle': '  '})
    assert r.status_code in (200, 201), r.data[:300]
