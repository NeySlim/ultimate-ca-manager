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


class TestSoftHsmOutsideTheApi:

    @staticmethod
    def _boot(monkeypatch):
        from unittest.mock import patch
        from models import db
        from models.hsm import HsmProvider
        from services.hsm.hsm_service import HsmService
        HsmProvider.query.filter_by(name='SoftHSM-Default').delete()
        db.session.commit()
        monkeypatch.setenv('HSM_DEFAULT_PIN', '1234')
        with patch('utils.hsm_check._find_softhsm', return_value=SOFTHSM_PATH):
            HsmService.auto_register_softhsm()
        return HsmProvider.query.filter_by(name='SoftHSM-Default').first()

    def test_the_boot_registers_no_softhsm_in_fips(self, app, fips_on, monkeypatch, caplog):
        with app.app_context():
            assert self._boot(monkeypatch) is None
            assert 'UCM_FIPS_ALLOW_SOFTHSM' in caplog.text

    def test_the_escape_hatch_lets_the_boot_register_it(self, app, fips_on, monkeypatch):
        from models import db
        monkeypatch.setenv('UCM_FIPS_ALLOW_SOFTHSM', '1')
        with app.app_context():
            row = self._boot(monkeypatch)
            assert row is not None and row.is_softhsm
            db.session.delete(row)
            db.session.commit()

    def test_a_restored_softhsm_provider_is_flagged_in_fips(self, app, fips_on, caplog):
        from models import db
        from models.hsm import HsmProvider
        from tests.test_backup_hsm_and_key_pairs import _service
        name = f'restored-softhsm-{uuid.uuid4().hex[:6]}'
        item = {'name': name, 'type': 'pkcs11', 'config': json.dumps({'module_path': SOFTHSM_PATH})}
        with app.app_context():
            try:
                _service()._restore_hsm_providers({'hsm_providers': [item]}, {'hsm_providers': 0})
                db.session.commit()
                assert HsmProvider.query.filter_by(name=name).first() is not None
                assert name in caplog.text and 'SoftHSM' in caplog.text
            finally:
                db.session.rollback()
                HsmProvider.query.filter_by(name=name).delete()
                db.session.commit()


class TestUnreadableModule:

    def test_a_module_that_cannot_describe_itself_still_tests_ok(self):
        from types import SimpleNamespace
        from services.hsm.pkcs11_provider import Pkcs11Provider

        class Silent:
            def __getattr__(self, name):
                raise RuntimeError(f'{name} not supported')

        provider = Pkcs11Provider.__new__(Pkcs11Provider)
        provider._lib = Silent()
        provider._token = SimpleNamespace(slot=Silent())
        assert provider._module_info() == {}

    def test_a_failed_description_closes_the_session(self, monkeypatch):
        from types import SimpleNamespace
        from services.hsm.pkcs11_provider import Pkcs11Provider

        class Unreadable:
            def __getattr__(self, name):
                raise RuntimeError(f'{name} not supported')

        provider = Pkcs11Provider.__new__(Pkcs11Provider)
        closed = []
        monkeypatch.setattr(provider, 'connect', lambda: setattr(provider, '_token', Unreadable()), raising=False)
        monkeypatch.setattr(provider, 'disconnect', lambda: closed.append(True), raising=False)
        assert provider.test_connection()['success'] is False
        assert closed

    def test_a_module_that_no_longer_describes_itself_forgets_the_old_description(self, app, monkeypatch):
        from models import db
        from models.hsm import HsmProvider
        from services.hsm import HsmService
        with app.app_context():
            row = HsmProvider(name=f'stale-{uuid.uuid4().hex[:8]}', type='pkcs11',
                              config=json.dumps({'module_path': VENDOR_PATH}),
                              module_info=json.dumps({'library': 'old'}))
            db.session.add(row)
            db.session.commit()
            fake = type('Fake', (), {'test_connection': lambda self: {'success': True, 'module': {}}})()
            monkeypatch.setattr(HsmService, '_get_provider_instance', classmethod(lambda cls, p: fake))
            try:
                HsmService.test_provider(row.id)
                assert db.session.get(HsmProvider, row.id).module_info is None
            finally:
                HsmProvider.query.filter_by(id=row.id).delete()
                db.session.commit()
