"""HA mode: no SoftHSM token is created, a SoftHSM provider already there is kept and flagged."""
import json
import pathlib
import subprocess
import uuid

import pytest

from config.settings import Config

PROVIDERS = '/api/v2/hsm/providers'
SOFT = '/usr/lib/softhsm/libsofthsm2.so'
VENDOR = '/opt/vendor/lib/libcs_pkcs11_R3.so'
ROOT = pathlib.Path(__file__).resolve().parents[2]
HELPER = ROOT / 'docker' / 'ha-database.sh'


def _body(module, name=None):
    return {'name': name or f'p11-{uuid.uuid4().hex[:8]}', 'type': 'pkcs11',
            'config': {'module_path': module, 'token_label': 't', 'user_pin': '1234'}}


def _count(app):
    from models.hsm import HsmProvider
    with app.app_context():
        return HsmProvider.query.count()


@pytest.fixture
def ha(monkeypatch):
    monkeypatch.setattr(Config, 'HA_MODE', True)


def _assert_refused(r):
    assert r.status_code == 409, r.data
    assert r.get_json()['code'] == 'ha_mode'


class TestInHa:

    def test_creating_a_softhsm_provider_is_refused_and_writes_nothing(self, app, auth_client, ha):
        before = _count(app)
        _assert_refused(auth_client.post(PROVIDERS, json=_body(SOFT)))
        assert _count(app) == before

    def test_a_softhsm_name_is_refused_too(self, auth_client, ha):
        _assert_refused(auth_client.post(PROVIDERS, json=_body(VENDOR, name=f'SoftHSM {uuid.uuid4().hex[:5]}')))

    def test_a_network_provider_is_accepted(self, auth_client, ha):
        assert auth_client.post(PROVIDERS, json=_body(VENDOR)).status_code == 201

    def test_pointing_a_provider_at_softhsm_is_refused(self, auth_client, monkeypatch):
        monkeypatch.setattr(Config, 'HA_MODE', False)
        pid = auth_client.post(PROVIDERS, json=_body(VENDOR)).get_json()['data']['id']
        monkeypatch.setattr(Config, 'HA_MODE', True)
        _assert_refused(auth_client.put(f'{PROVIDERS}/{pid}', json={'config': _body(SOFT)['config']}))
        got = auth_client.get(f'{PROVIDERS}/{pid}').get_json()['data']
        assert got['softhsm'] is False

    def test_an_existing_softhsm_provider_stays_editable(self, auth_client, monkeypatch):
        monkeypatch.setattr(Config, 'HA_MODE', False)
        pid = auth_client.post(PROVIDERS, json=_body(SOFT)).get_json()['data']['id']
        monkeypatch.setattr(Config, 'HA_MODE', True)
        r = auth_client.put(f'{PROVIDERS}/{pid}', json={'name': f'renamed-{uuid.uuid4().hex[:6]}'})
        assert r.status_code == 200, r.data

    def test_generating_a_key_on_softhsm_is_refused(self, app, auth_client, monkeypatch):
        from models.hsm import HsmKey
        monkeypatch.setattr(Config, 'HA_MODE', False)
        pid = auth_client.post(PROVIDERS, json=_body(SOFT)).get_json()['data']['id']
        monkeypatch.setattr(Config, 'HA_MODE', True)
        r = auth_client.post(f'{PROVIDERS}/{pid}/keys',
                             json={'label': 'k', 'algorithm': 'EC-P256', 'purpose': 'signing'})
        _assert_refused(r)
        with app.app_context():
            assert HsmKey.query.filter_by(provider_id=pid).count() == 0

    def test_a_ca_on_a_new_softhsm_key_is_refused(self, app, auth_client, monkeypatch):
        from models import CA
        monkeypatch.setattr(Config, 'HA_MODE', False)
        pid = auth_client.post(PROVIDERS, json=_body(SOFT)).get_json()['data']['id']
        monkeypatch.setattr(Config, 'HA_MODE', True)
        descr = f'ha-soft-{uuid.uuid4().hex[:6]}'
        r = auth_client.post('/api/v2/cas', json={
            'commonName': descr, 'descr': descr, 'keyType': 'EC-P256', 'validityYears': 1,
            'hsm_provider_id': pid, 'hsm_key_label': descr, 'hsm_key_algorithm': 'EC-P256'})
        _assert_refused(r)
        with app.app_context():
            assert CA.query.filter_by(descr=descr).count() == 0

    def test_the_boot_registers_no_softhsm_default(self, app, ha, monkeypatch):
        from unittest.mock import patch
        from models import db
        from models.hsm import HsmProvider
        from services.hsm.hsm_service import HsmService
        with app.app_context():
            HsmProvider.query.filter_by(name='SoftHSM-Default').delete()
            db.session.commit()
            monkeypatch.setenv('HSM_DEFAULT_PIN', '1234')
            with patch('utils.hsm_check._find_softhsm', return_value=SOFT):
                HsmService.auto_register_softhsm()
            assert HsmProvider.query.filter_by(name='SoftHSM-Default').first() is None

    def test_an_existing_softhsm_provider_is_named_in_one_warning(self, app, ha, caplog):
        from models import db
        from models.hsm import HsmProvider
        from services.hsm.hsm_service import HsmService
        name = f'old-softhsm-{uuid.uuid4().hex[:6]}'
        with app.app_context():
            row = HsmProvider(type='pkcs11', name=name, config=json.dumps({'module_path': SOFT}))
            db.session.add(row)
            db.session.commit()
            try:
                with caplog.at_level('WARNING'):
                    names = HsmService.warn_local_softhsm()
                assert name in names
                assert caplog.text.count(name) == 1 and 'this node only' in caplog.text
            finally:
                db.session.delete(row)
                db.session.commit()


class TestWithoutHa:

    def test_softhsm_provider_and_warning_unchanged(self, app, auth_client, monkeypatch, caplog):
        from services.hsm.hsm_service import HsmService
        monkeypatch.setattr(Config, 'HA_MODE', False)
        assert auth_client.post(PROVIDERS, json=_body(SOFT)).status_code == 201
        with app.app_context(), caplog.at_level('WARNING'):
            assert HsmService.warn_local_softhsm() == []
        assert 'this node only' not in caplog.text


def _skip(env):
    return subprocess.run(['bash', '-c', f'. {HELPER}; ucm_ha_skip_softhsm_token'],
                          env={'PATH': '/usr/bin:/bin', **env}, capture_output=True, text=True)


@pytest.mark.parametrize('flag', ['1', 'true', ' YES '])
@pytest.mark.parametrize('auto', ['true', 'false', None])
def test_entrypoint_skips_the_default_token_in_ha(flag, auto):
    env = {'UCM_HA': flag, **({'HSM_AUTO_INIT': auto} if auto else {})}
    r = _skip(env)
    assert r.returncode == 0 and 'not created in HA mode' in r.stdout


@pytest.mark.parametrize('flag', [None, '0', 'false', ''])
def test_entrypoint_keeps_the_default_token_without_ha(flag):
    r = _skip({'UCM_HA': flag} if flag is not None else {})
    assert r.returncode == 1 and r.stdout == ''


def test_entrypoint_branch_uses_the_helper_before_hsm_auto_init():
    text = (ROOT / 'docker' / 'entrypoint.sh').read_text()
    block = text[text.index('HSM / SoftHSM AUTO-INIT'):]
    assert block.index('ucm_ha_active') < block.index('HSM_AUTO_INIT:-true')
