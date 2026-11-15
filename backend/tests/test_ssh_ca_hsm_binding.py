"""An HSM key backs one authority (X.509 or SSH CA), and what an SSH CA on an HSM key asks of the caller.

The token is stubbed as in tests/test_ssh_ca_hsm.py: an HsmKey row backed by a local key,
HsmService.sign and get_public_key patched.
"""
import json
import uuid
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

from config.settings import Config
from models import CA, AuditLog, db
from models.hsm import HsmKey, HsmProvider
from models.ssh import SSHCertificateAuthority
from services.hsm.base_provider import (HsmConfigError, HsmConnectionError, HsmKeyNotFoundError,
                                        HsmOperationError)

SSH_CAS = '/api/v2/ssh/cas'
OPENSC = '/usr/lib/x86_64-linux-gnu/opensc-pkcs11.so'
YKCS11 = '/usr/lib/x86_64-linux-gnu/libykcs11.so'
SOFT = '/nonexistent/softhsm/libsofthsm2.so'
VENDOR = '/opt/vendor/lib/libcs_pkcs11_R3.so'


def _pem(real):
    return real.public_key().public_bytes(serialization.Encoding.PEM,
                                          serialization.PublicFormat.SubjectPublicKeyInfo).decode()


@pytest.fixture
def token_key(app):
    """Factory: (provider id, key id) of a stub token key; HSM calls served by its local twin."""
    made, reals, pubs = [], {}, {}

    def make(module=VENDOR, real=None, algorithm='EC-P256', provider_name=None):
        real = real or ec.generate_private_key(ec.SECP256R1())
        pub = _pem(real)
        tag = uuid.uuid4().hex[:8]
        with app.app_context():
            provider = HsmProvider(type='pkcs11', name=provider_name or f'bind-{tag}',
                                   config=json.dumps({'module_path': module}))
            db.session.add(provider)
            db.session.commit()
            key = HsmKey(provider_id=provider.id, key_identifier=f'k-{tag}', label=f'k-{tag}',
                         algorithm=algorithm, key_type='asymmetric', purpose='signing', public_key_pem=pub)
            db.session.add(key)
            db.session.commit()
            ids = {'provider': provider.id, 'key': key.id, 'label': key.label, 'provider_name': provider.name}
        made.append(ids)
        reals[ids['key']], pubs[ids['key']] = real, pub
        return ids

    def sign(key_id, data, algo=None, hash_algorithm=None):
        real = reals[key_id]
        digest = {'sha384': hashes.SHA384, 'sha512': hashes.SHA512}.get(hash_algorithm, hashes.SHA256)()
        if isinstance(real, rsa.RSAPrivateKey):
            return real.sign(data, padding.PKCS1v15(), digest)
        return real.sign(data, ec.ECDSA(digest))

    patches = [patch('services.hsm.HsmService.sign', side_effect=sign),
               patch('services.hsm.HsmService.get_public_key', side_effect=lambda key_id: pubs[key_id])]
    for p in patches:
        p.start()
    yield make
    for p in patches:
        p.stop()
    from tests.seeded_rows import delete_cas
    with app.app_context():
        db.session.rollback()
        for ids in made:
            SSHCertificateAuthority.query.filter_by(hsm_key_id=ids['key']).delete(synchronize_session=False)
            delete_cas(CA.query.filter_by(hsm_key_id=ids['key']))
            HsmKey.query.filter_by(id=ids['key']).delete(synchronize_session=False)
            HsmProvider.query.filter_by(id=ids['provider']).delete(synchronize_session=False)
        db.session.commit()


def _ssh_ca(client, key_id, ca_type='user', headers=None, **extra):
    body = {'descr': f'ssh-{ca_type}-{uuid.uuid4().hex[:6]}', 'ca_type': ca_type, 'hsm_key_id': key_id, **extra}
    return client.post(SSH_CAS, json=body, headers=headers or {})


def _x509_ca(client, key_id):
    descr = f'x509-{uuid.uuid4().hex[:6]}'
    return descr, client.post('/api/v2/cas', json={'commonName': descr, 'descr': descr, 'validityYears': 1,
                                                    'hsm_key_id': key_id})


def _deleted(client, url):
    r = client.delete(url)
    assert r.status_code in (200, 204), (url, r.data)


def _detail(r):
    body = r.get_json()
    return body.get('detail') or body.get('message') or body.get('error') or ''


class TestOneKeyOneAuthority:

    def test_a_key_backs_one_ssh_ca_whatever_its_role(self, auth_client, token_key):
        key = token_key()
        first = _ssh_ca(auth_client, key['key'], 'user')
        assert first.status_code == 201, first.data
        r = _ssh_ca(auth_client, key['key'], 'host')
        assert r.status_code == 409, r.data
        assert f"SSH user CA '{first.get_json()['data']['descr']}'" in _detail(r)

    def test_an_ssh_ca_never_takes_the_key_of_an_x509_ca(self, auth_client, token_key):
        key = token_key()
        descr, r = _x509_ca(auth_client, key['key'])
        assert r.status_code == 201, r.data
        r = _ssh_ca(auth_client, key['key'])
        assert r.status_code == 409, r.data
        assert f"X.509 CA '{descr}'" in _detail(r)

    def test_an_x509_ca_never_takes_the_key_of_an_ssh_ca(self, app, auth_client, token_key):
        key = token_key()
        r = _ssh_ca(auth_client, key['key'], 'host')
        assert r.status_code == 201, r.data
        ssh_descr = r.get_json()['data']['descr']
        descr, r = _x509_ca(auth_client, key['key'])
        assert r.status_code == 409, r.data
        assert f"SSH host CA '{ssh_descr}'" in _detail(r)
        with app.app_context():
            assert CA.query.filter_by(descr=descr).count() == 0

    def test_a_second_x509_ca_on_a_key_is_a_conflict(self, auth_client, token_key):
        key = token_key()
        first, r = _x509_ca(auth_client, key['key'])
        assert r.status_code == 201, r.data
        _, r = _x509_ca(auth_client, key['key'])
        assert r.status_code == 409, r.data
        assert f"X.509 CA '{first}'" in _detail(r)

    def test_two_key_rows_on_one_token_key_are_one_key(self, auth_client, token_key):
        real = ec.generate_private_key(ec.SECP256R1())
        one, two = token_key(real=real), token_key(real=real)
        first = _ssh_ca(auth_client, one['key'], 'user')
        assert first.status_code == 201, first.data
        r = _ssh_ca(auth_client, two['key'], 'host')
        assert r.status_code == 409, r.data
        assert _detail(r) == (f"HSM key '{two['label']}' already backs the SSH user CA "
                              f"'{first.get_json()['data']['descr']}': an HSM key backs one authority only")

    def test_a_software_ca_on_the_same_public_key_is_named_as_software(self, app, auth_client, token_key):
        real = ec.generate_private_key(ec.SECP256R1())
        descr = f'soft-{uuid.uuid4().hex[:6]}'
        pem = real.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH,
                                 serialization.NoEncryption()).decode()
        r = auth_client.post(f'{SSH_CAS}/import', json={'descr': descr, 'ca_type': 'user', 'private_key': pem})
        assert r.status_code == 201, r.data
        try:
            key = token_key(real=real)
            r = _ssh_ca(auth_client, key['key'], 'host')
            assert r.status_code == 409, r.data
            assert _detail(r) == (f"HSM key '{key['label']}' holds the key of the software SSH user CA "
                                  f"'{descr}': a key backs one authority only")
        finally:
            with app.app_context():
                SSHCertificateAuthority.query.filter_by(descr=descr).delete(synchronize_session=False)
                db.session.commit()

    def test_an_ssh_ca_never_takes_another_row_of_an_x509_ca_key(self, auth_client, token_key):
        real = ec.generate_private_key(ec.SECP256R1())
        one, two = token_key(real=real), token_key(real=real)
        descr, r = _x509_ca(auth_client, one['key'])
        assert r.status_code == 201, r.data
        r = _ssh_ca(auth_client, two['key'])
        assert r.status_code == 409, r.data
        assert _detail(r) == (f"HSM key '{two['label']}' is the token key of HSM key '{one['label']}', "
                              f"which backs the X.509 CA '{descr}': an HSM key backs one authority only")

    def test_a_bound_key_of_another_public_key_takes_nothing(self, auth_client, token_key):
        held, free = token_key(), token_key()
        _, r = _x509_ca(auth_client, held['key'])
        assert r.status_code == 201, r.data
        assert _ssh_ca(auth_client, free['key']).status_code == 201

    @pytest.mark.parametrize('first', ['ssh', 'x509'])
    def test_an_x509_ca_never_takes_another_row_of_a_bound_key(self, app, auth_client, token_key, first):
        real = ec.generate_private_key(ec.SECP256R1())
        one, two = token_key(real=real), token_key(real=real)
        if first == 'ssh':
            r = _ssh_ca(auth_client, one['key'], 'host')
            holder = f"SSH host CA '{r.get_json()['data']['descr']}'"
        else:
            held, r = _x509_ca(auth_client, one['key'])
            holder = f"X.509 CA '{held}'"
        assert r.status_code == 201, r.data
        descr, r = _x509_ca(auth_client, two['key'])
        assert r.status_code == 409, r.data
        assert _detail(r) == (f"HSM key '{two['label']}' is the token key of HSM key '{one['label']}', "
                              f"which backs the {holder}: an HSM key backs one authority only")
        with app.app_context():
            assert CA.query.filter_by(descr=descr).count() == 0

    def test_unused_keys_leave_out_a_key_an_ssh_ca_holds(self, auth_client, token_key):
        held, free = token_key(), token_key()
        assert _ssh_ca(auth_client, held['key']).status_code == 201
        listed = {k['id'] for k in auth_client.get('/api/v2/hsm/keys?unused=true').get_json()['data']}
        assert free['key'] in listed and held['key'] not in listed


class TestDeletion:

    def test_a_provider_whose_key_backs_an_ssh_ca_stays(self, app, auth_client, token_key):
        key = token_key()
        r = _ssh_ca(auth_client, key['key'])
        assert r.status_code == 201, r.data
        r = auth_client.delete(f"/api/v2/hsm/providers/{key['provider']}")
        assert r.status_code == 409, r.data
        assert 'SSH user CA' in _detail(r)
        with app.app_context():
            assert db.session.get(HsmKey, key['key']) is not None
            assert SSHCertificateAuthority.query.filter_by(hsm_key_id=key['key']).count() == 1

    def test_a_key_that_backs_an_ssh_ca_says_which(self, auth_client, token_key):
        key = token_key()
        r = _ssh_ca(auth_client, key['key'], 'host')
        descr = r.get_json()['data']['descr']
        r = auth_client.delete(f"/api/v2/hsm/keys/{key['key']}")
        assert r.status_code == 409, r.data
        assert _detail(r) == f"Cannot delete key: it backs the SSH host CA '{descr}'"

    def test_a_sync_that_no_longer_lists_the_key_keeps_it_for_the_ssh_ca(self, app, auth_client, token_key):
        from services.hsm import HsmService
        from tests.test_hsm_sync_and_listing import _ListingProvider
        key = token_key()
        r = _ssh_ca(auth_client, key['key'])
        assert r.status_code == 201, r.data
        with app.app_context(), patch.object(HsmService, '_get_provider_instance',
                                             return_value=_ListingProvider([])):
            result = HsmService.sync_keys(key['provider'])
        assert result['removed'] == 0 and result['missing_kept'] == 1
        with app.app_context():
            ca = db.session.get(SSHCertificateAuthority, r.get_json()['data']['id'])
            assert (ca.key_source, ca.hsm_key_id) == ('hsm', key['key'])

    def test_a_provider_without_bound_keys_is_deleted(self, app, auth_client, token_key):
        key = token_key()
        with patch('services.hsm.HsmService.delete_provider') as deleted:
            r = auth_client.delete(f"/api/v2/hsm/providers/{key['provider']}")
        assert r.status_code in (200, 204), r.data
        deleted.assert_called_once_with(key['provider'])


class TestInput:

    @pytest.mark.parametrize('value', [True, False, 1.9, 1.0, '1', 0, -3, [1], {}])
    def test_hsm_key_id_is_a_strict_positive_integer(self, app, auth_client, value):
        with app.app_context():
            before = SSHCertificateAuthority.query.count()
        r = _ssh_ca(auth_client, value)
        assert r.status_code == 400, (value, r.data)
        assert 'hsm_key_id' in _detail(r)
        with app.app_context():
            assert SSHCertificateAuthority.query.count() == before

    @pytest.mark.parametrize('error,status', [
        (HsmConnectionError('socket refused'), 503),
        (HsmKeyNotFoundError('CKR_OBJECT_HANDLE_INVALID'), 409),
        (HsmConfigError('bad slot'), 400),
        (HsmOperationError('CKR_DEVICE_ERROR'), 502),
    ])
    def test_a_token_error_answers_by_its_cause(self, app, auth_client, token_key, error, status):
        key = token_key()
        with patch('services.hsm.HsmService.get_public_key', side_effect=error):
            r = _ssh_ca(auth_client, key['key'])
        assert r.status_code == status, r.data
        assert str(error) not in _detail(r)
        with app.app_context():
            assert SSHCertificateAuthority.query.filter_by(hsm_key_id=key['key']).count() == 0

    @pytest.mark.parametrize('error,status', [
        (HsmConnectionError('socket refused'), 503),
        (HsmKeyNotFoundError('CKR_OBJECT_HANDLE_INVALID'), 409),
        (HsmOperationError('CKR_DEVICE_ERROR'), 502),
    ])
    def test_a_cached_public_key_still_reaches_the_token(self, app, auth_client, token_key, error, status):
        """The public key is read from the row: only the proof of possession reaches the token."""
        key = token_key()
        with patch('services.hsm.HsmService.sign', side_effect=error):
            r = _ssh_ca(auth_client, key['key'])
        assert r.status_code == status, r.data
        assert str(error) not in _detail(r)
        with app.app_context():
            assert SSHCertificateAuthority.query.filter_by(hsm_key_id=key['key']).count() == 0

    def test_the_audit_names_the_key_its_fingerprint_and_provider(self, app, auth_client, token_key):
        key = token_key()
        r = _ssh_ca(auth_client, key['key'])
        assert r.status_code == 201, r.data
        ca = r.get_json()['data']
        with app.app_context():
            row = AuditLog.query.filter_by(action='ssh_ca_created', resource_name=ca['descr']).one()
        assert f"HSM key #{key['key']} '{key['label']}'" in row.details
        assert f"provider '{key['provider_name']}'" in row.details
        assert ca['fingerprint'] in row.details


class TestPermission:

    @pytest.fixture
    def api_key(self, auth_client):
        made = []

        def make(permissions):
            r = auth_client.post('/api/v2/account/apikeys', json={'name': 'ssh-hsm', 'permissions': permissions})
            assert r.status_code == 201, r.data
            made.append(r.get_json()['data']['id'])
            return {'X-API-Key': r.get_json()['data']['key']}

        yield make
        for key_id in made:
            auth_client.delete(f'/api/v2/account/apikeys/{key_id}')

    def test_an_api_key_without_read_hsm_cannot_bind_a_key(self, app, auth_client, token_key, api_key):
        key = token_key()
        headers = api_key(['read:ssh_cas', 'write:ssh_cas'])
        r = _ssh_ca(app.test_client(), key['key'], headers=headers)
        assert r.status_code == 403, r.data
        assert 'read:hsm' in _detail(r)
        with app.app_context():
            assert SSHCertificateAuthority.query.filter_by(hsm_key_id=key['key']).count() == 0
        # A software CA asks nothing more of the same key
        r = app.test_client().post(SSH_CAS, json={'descr': 'soft', 'ca_type': 'user', 'key_type': 'ed25519'},
                                   headers=headers)
        assert r.status_code == 201, r.data

    def test_an_api_key_with_both_binds_it(self, app, auth_client, token_key, api_key):
        key = token_key()
        r = _ssh_ca(app.test_client(), key['key'], headers=api_key(['write:ssh_cas', 'read:hsm']))
        assert r.status_code == 201, r.data

    def test_the_hsm_right_alone_creates_no_ssh_ca(self, app, auth_client, token_key, api_key):
        key = token_key()
        r = _ssh_ca(app.test_client(), key['key'], headers=api_key(['read:hsm']))
        assert r.status_code == 403, r.data

    @pytest.mark.parametrize('permissions,status', [
        (['write:ssh_cas'], 403),
        (['write:ssh_cas', 'read:hsm'], 201),
    ])
    def test_a_custom_role(self, app, auth_client, create_user, token_key, request, permissions, status):
        from models import User
        name = f'sshhsm{uuid.uuid4().hex[:6]}'
        r = auth_client.post('/api/v2/rbac/roles', json={'name': f'{name} role', 'permissions': permissions})
        assert r.status_code == 200, r.data
        role_id = r.get_json()['data']['id']
        # The user goes before its role: the shared tables end as they began
        request.addfinalizer(lambda: _deleted(auth_client, f'/api/v2/rbac/roles/{role_id}'))
        create_user(username=name, role='viewer')
        with app.app_context():
            user_id = User.query.filter_by(username=name).first().id
        request.addfinalizer(lambda: _deleted(auth_client, f'/api/v2/users/{user_id}'))
        assert auth_client.put(f'/api/v2/users/{user_id}',
                               json={'custom_role_id': role_id}).status_code == 200
        client = app.test_client()
        assert client.post('/api/v2/auth/login', json={'username': name, 'password': 'TestPass123!'}
                           ).status_code == 200
        r = _ssh_ca(client, token_key()['key'])
        assert r.status_code == status, r.data


class TestFipsAndHa:

    def test_fips_refuses_a_key_it_does_not_approve_before_the_token(self, app, auth_client, token_key,
                                                                     monkeypatch):
        import fips_mode
        key = token_key(real=rsa.generate_private_key(65537, 1024), algorithm='RSA-1024')
        monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
        with patch('services.hsm.hsm_private_key.load_hsm_private_key') as loaded:
            r = _ssh_ca(auth_client, key['key'])
        assert r.status_code == 400, r.data
        assert 'RSA 1024' in json.dumps(r.get_json())
        loaded.assert_not_called()

    @pytest.mark.parametrize('module,word', [(SOFT, 'SoftHSM'), (OPENSC, 'smart card reader'),
                                             (YKCS11, 'smart card reader')])
    def test_ha_refuses_a_token_one_node_reaches(self, app, auth_client, token_key, monkeypatch, module, word):
        key = token_key(module=module)
        monkeypatch.setattr(Config, 'HA_MODE', True)
        r = _ssh_ca(auth_client, key['key'])
        assert r.status_code == 409, r.data
        assert r.get_json()['code'] == 'ha_mode' and word in _detail(r)
        _, r = _x509_ca(auth_client, key['key'])
        assert r.status_code == 409 and r.get_json()['code'] == 'ha_mode', r.data

    def test_ha_takes_a_network_token(self, auth_client, token_key, monkeypatch):
        key = token_key(module=VENDOR)
        monkeypatch.setattr(Config, 'HA_MODE', True)
        assert _ssh_ca(auth_client, key['key']).status_code == 201

    def test_without_ha_a_reader_key_is_taken(self, auth_client, token_key):
        assert _ssh_ca(auth_client, token_key(module=OPENSC)['key']).status_code == 201

    def test_ha_generates_no_x509_ca_key_on_a_reader(self, auth_client, token_key, monkeypatch):
        key = token_key(module=OPENSC)
        monkeypatch.setattr(Config, 'HA_MODE', True)
        with patch('services.hsm.HsmService.generate_key') as generated:
            r = auth_client.post('/api/v2/cas', json={
                'commonName': 'reader-ca', 'descr': 'reader-ca', 'validityYears': 1,
                'hsm_provider_id': key['provider'], 'hsm_key_label': 'new', 'hsm_key_algorithm': 'EC-P256'})
        assert r.status_code == 409 and r.get_json()['code'] == 'ha_mode', r.data
        generated.assert_not_called()
