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


@pytest.fixture
def bound_key(app, request):
    """A key row on a SoftHSM (or network) provider, signing locally through patches."""
    from unittest.mock import patch
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    from models import db, CA
    from models.hsm import HsmKey, HsmProvider
    from tests.seeded_rows import delete_cas
    module = getattr(request, 'param', SOFT)
    tag = uuid.uuid4().hex[:8]
    real = rsa.generate_private_key(65537, 2048)
    pub = real.public_key().public_bytes(serialization.Encoding.PEM,
                                         serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    with app.app_context():
        provider = HsmProvider(type='pkcs11', name=f'bound-{tag}', config=json.dumps({'module_path': module}))
        db.session.add(provider)
        db.session.commit()
        key = HsmKey(provider_id=provider.id, key_identifier=f'k-{tag}', label=f'k-{tag}', algorithm='RSA-2048',
                     key_type='asymmetric', purpose='signing', public_key_pem=pub)
        db.session.add(key)
        db.session.commit()
        ids = {'provider': provider.id, 'key': key.id}

    def sign(key_id, data, algo=None, hash_algorithm=None):
        digest = {'sha384': hashes.SHA384, 'sha512': hashes.SHA512}.get(hash_algorithm, hashes.SHA256)()
        return real.sign(data, padding.PKCS1v15(), digest)

    with patch('services.hsm.HsmService.sign', side_effect=sign), \
            patch('services.hsm.HsmService.get_public_key', return_value=pub):
        yield ids
    with app.app_context():
        db.session.rollback()
        delete_cas(CA.query.filter_by(hsm_key_id=ids['key']))
        HsmKey.query.filter_by(id=ids['key']).delete()
        HsmProvider.query.filter_by(id=ids['provider']).delete()
        db.session.commit()


def _ca_on_key(auth_client, key_id, **extra):
    descr = f'ha-key-{uuid.uuid4().hex[:6]}'
    body = {'commonName': descr, 'descr': descr, 'validityYears': 1, 'hsm_key_id': key_id, **extra}
    return descr, auth_client.post('/api/v2/cas', json=body)


def _no_ca(app, descr):
    from models import CA
    with app.app_context():
        assert CA.query.filter_by(descr=descr).count() == 0


class TestExistingSoftHsmKeyInHa:

    def test_a_root_ca_on_it_is_refused(self, app, auth_client, bound_key, ha):
        descr, r = _ca_on_key(auth_client, bound_key['key'])
        _assert_refused(r)
        _no_ca(app, descr)

    def test_an_intermediate_ca_on_it_is_refused(self, app, auth_client, bound_key, ha):
        parent = auth_client.post('/api/v2/cas', json={
            'commonName': f'ha-parent-{uuid.uuid4().hex[:6]}', 'keyType': 'EC-P256', 'validityYears': 2})
        assert parent.status_code == 201, parent.data
        parent_id = parent.get_json()['data']['id']
        try:
            descr, r = _ca_on_key(auth_client, bound_key['key'], type='intermediate', parentCAId=parent_id)
            _assert_refused(r)
            _no_ca(app, descr)
        finally:
            from models import CA
            from tests.seeded_rows import delete_cas
            with app.app_context():
                delete_cas(CA.query.filter_by(id=parent_id))
                from models import db
                db.session.commit()

    def test_an_external_csr_ca_on_it_is_refused(self, app, auth_client, bound_key, ha):
        descr, r = _ca_on_key(auth_client, bound_key['key'], type='external')
        _assert_refused(r)
        _no_ca(app, descr)

    @pytest.mark.parametrize('bound_key', [VENDOR], indirect=True)
    def test_a_network_key_is_accepted(self, auth_client, bound_key, ha):
        assert _ca_on_key(auth_client, bound_key['key'])[1].status_code == 201

    def test_a_ca_already_on_it_keeps_signing(self, auth_client, bound_key, monkeypatch):
        monkeypatch.setattr(Config, 'HA_MODE', False)
        _, r = _ca_on_key(auth_client, bound_key['key'])
        assert r.status_code == 201, r.data
        monkeypatch.setattr(Config, 'HA_MODE', True)
        cert = auth_client.post('/api/v2/certificates', json={
            'cn': f'ha-{uuid.uuid4().hex[:6]}.test', 'ca_id': r.get_json()['data']['id'],
            'key_type': 'rsa', 'key_size': 2048, 'validity_days': 30})
        assert cert.status_code in (200, 201), cert.data


class TestWithoutHa:

    def test_softhsm_provider_and_warning_unchanged(self, app, auth_client, monkeypatch, caplog):
        from services.hsm.hsm_service import HsmService
        monkeypatch.setattr(Config, 'HA_MODE', False)
        assert auth_client.post(PROVIDERS, json=_body(SOFT)).status_code == 201
        with app.app_context(), caplog.at_level('WARNING'):
            assert HsmService.warn_local_softhsm() == []
        assert 'this node only' not in caplog.text


def _auto_init(env):
    return subprocess.run(['bash', '-c', f'. {HELPER}; ucm_softhsm_auto_init'],
                          env={'PATH': '/usr/bin:/bin', **env}, capture_output=True, text=True)


@pytest.mark.parametrize('flag', ['1', 'true', ' YES '])
@pytest.mark.parametrize('auto', ['true', 'false', None])
def test_no_default_token_in_ha(flag, auto):
    env = {'UCM_HA': flag, **({'HSM_AUTO_INIT': auto} if auto else {})}
    assert _auto_init(env).returncode == 1


@pytest.mark.parametrize('flag', [None, '0', 'false', ''])
@pytest.mark.parametrize('auto,expected', [('true', 0), (None, 0), ('false', 1)])
def test_default_token_without_ha_follows_hsm_auto_init(flag, auto, expected):
    env = {**({'UCM_HA': flag} if flag is not None else {}),
           **({'HSM_AUTO_INIT': auto} if auto else {})}
    assert _auto_init(env).returncode == expected


def test_entrypoint_gates_token_init_on_the_helper():
    text = (ROOT / 'docker' / 'entrypoint.sh').read_text()
    block = text[text.index('HSM / SoftHSM AUTO-INIT'):]
    assert 'ucm_softhsm_auto_init' in block and 'init-token' in block
