"""SoftHSM in FIPS mode, and the PKCS#11 module a provider reports.

SoftHSM is not a validated module: FIPS mode refuses to create a provider on
it unless UCM_FIPS_ALLOW_SOFTHSM=1. A connection test records what the
PKCS#11 library says it is, so the module can be named next to its keys.
"""
import json
import uuid

import pytest

import fips_mode
from tests.test_hsm_sync_and_listing import SOFTHSM_MODULE, needs_softhsm, softhsm_token  # noqa: F401

PROVIDERS = '/api/v2/hsm/providers'
SOFTHSM_PATH = '/usr/lib/softhsm/libsofthsm2.so'
VENDOR_PATH = '/opt/vendor/lib/libcs_pkcs11_R3.so'


def _create(client, module_path, name=None):
    return client.post(PROVIDERS, json={
        'name': name or f'p11-{uuid.uuid4().hex[:8]}', 'type': 'pkcs11',
        'config': {'module_path': module_path, 'token_label': 't', 'user_pin': '1234'}})


@pytest.fixture
def fips_on(monkeypatch):
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
    monkeypatch.delenv('UCM_FIPS_ALLOW_SOFTHSM', raising=False)


class TestSoftHsmInFips:

    def test_a_softhsm_provider_is_refused(self, auth_client, fips_on):
        r = _create(auth_client, SOFTHSM_PATH)
        assert r.status_code == 400, r.data
        assert r.get_json()['type'] == fips_mode.PROBLEM_TYPE
        assert 'UCM_FIPS_ALLOW_SOFTHSM' in r.get_json()['detail']

    def test_a_softhsm_name_is_refused_too(self, auth_client, fips_on):
        r = _create(auth_client, VENDOR_PATH, name=f'SoftHSM lab {uuid.uuid4().hex[:6]}')
        assert r.status_code == 400

    def test_the_escape_hatch_allows_it(self, auth_client, fips_on, monkeypatch):
        monkeypatch.setenv('UCM_FIPS_ALLOW_SOFTHSM', '1')
        assert _create(auth_client, SOFTHSM_PATH).status_code == 201

    def test_another_module_is_accepted(self, auth_client, fips_on):
        assert _create(auth_client, VENDOR_PATH).status_code == 201

    def test_outside_fips_softhsm_is_accepted(self, auth_client, monkeypatch):
        monkeypatch.setattr(fips_mode, 'enabled', lambda: False)
        assert _create(auth_client, SOFTHSM_PATH).status_code == 201

    def test_pointing_a_provider_at_softhsm_is_refused(self, auth_client, fips_on):
        pid = _create(auth_client, VENDOR_PATH).get_json()['data']['id']
        r = auth_client.put(f'{PROVIDERS}/{pid}', json={'config': {
            'module_path': SOFTHSM_PATH, 'token_label': 't', 'user_pin': '1234'}})
        assert r.status_code == 400
        assert r.get_json()['type'] == fips_mode.PROBLEM_TYPE

    def test_an_existing_softhsm_provider_stays_editable(self, auth_client, monkeypatch):
        monkeypatch.setattr(fips_mode, 'enabled', lambda: False)
        pid = _create(auth_client, SOFTHSM_PATH).get_json()['data']['id']
        monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
        monkeypatch.delenv('UCM_FIPS_ALLOW_SOFTHSM', raising=False)
        r = auth_client.put(f'{PROVIDERS}/{pid}', json={'name': f'renamed-{uuid.uuid4().hex[:6]}'})
        assert r.status_code == 200, r.data

    def test_the_provider_says_it_is_softhsm(self, auth_client, monkeypatch):
        monkeypatch.setattr(fips_mode, 'enabled', lambda: False)
        soft = _create(auth_client, SOFTHSM_PATH).get_json()['data']
        vendor = _create(auth_client, VENDOR_PATH).get_json()['data']
        assert soft['softhsm'] is True
        assert vendor['softhsm'] is False


@needs_softhsm
class TestModuleInfo:

    def test_a_connection_test_records_the_module(self, app, softhsm_token):
        from models import db
        from models.hsm import HsmProvider
        from services.hsm import HsmService
        with app.app_context():
            provider = HsmService.create_provider(
                name=f'module-{uuid.uuid4().hex[:8]}', provider_type='pkcs11', config=softhsm_token)
            result = HsmService.test_provider(provider.id)
            assert result['success'], result
            module = db.session.get(HsmProvider, provider.id).to_dict()['module_info']
            assert module['library']
            assert module['manufacturer'] == 'SoftHSM'
            assert module['firmware_version'] and module['library_version']

            # Another module: what was read from the old one no longer describes it
            HsmService.update_provider(provider.id, config={**softhsm_token, 'token_label': 'other'})
            assert db.session.get(HsmProvider, provider.id).to_dict()['module_info'] is None

    def test_an_unreadable_record_is_no_module(self, app):
        from models.hsm import HsmProvider
        row = HsmProvider(type='pkcs11', name='x', config=json.dumps({}), module_info='not json')
        assert row.to_dict()['module_info'] is None
