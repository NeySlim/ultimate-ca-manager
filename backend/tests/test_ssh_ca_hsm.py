"""SSH CAs whose private key stays on an HSM/PKCS#11 token.

The CA row stores only the public half; signing goes through the HSM wrappers
(services/hsm/hsm_private_key.py), the same path the X.509 HSM CAs use. The
token itself is stubbed: an HsmKey row backed by a real local key, with
HsmService.sign/get_public_key patched, as in tests/test_ca_service_hsm.py.
"""
import json

import pytest
from unittest.mock import patch

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, padding, rsa
from cryptography.hazmat.primitives.serialization import ssh as ssh_serialization

from models import db
from models.ssh import SSHCertificate, SSHCertificateAuthority
from services.ssh_ca_service import SSHCAService
from services.ssh_cert import SSHCertificateService


def post_json(client, url, payload):
    return client.post(url, data=json.dumps(payload), content_type='application/json')


@pytest.fixture
def hsm_key(app):
    """Factory: a stub HsmProvider + HsmKey row backed by a real local key."""
    created = []

    def make(real_key, algorithm):
        pub_pem = real_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()
        with app.app_context():
            from models.hsm import HsmKey, HsmProvider

            tag = algorithm.replace('-', '_').lower()
            provider = HsmProvider(name=f'SshCaProvider-{tag}', type='pkcs11', config='{}')
            db.session.add(provider)
            db.session.commit()
            key = HsmKey(
                provider_id=provider.id,
                key_identifier=f'sshca-{tag}',
                label=f'ssh-ca-key-{tag}',
                algorithm=algorithm,
                key_type='asymmetric',
                purpose='signing',
                public_key_pem=pub_pem,
            )
            db.session.add(key)
            db.session.commit()
            provider_id, key_id = provider.id, key.id

        created.append((provider_id, key_id))
        return {'hsm_key_id': key_id, 'real_key': real_key, 'pub_pem': pub_pem}

    yield make

    with app.app_context():
        from models.hsm import HsmKey, HsmProvider

        db.session.rollback()
        for provider_id, key_id in created:
            ca_ids = [ca.id for ca in SSHCertificateAuthority.query.filter_by(hsm_key_id=key_id)]
            if ca_ids:
                SSHCertificate.query.filter(SSHCertificate.ssh_ca_id.in_(ca_ids)).delete(
                    synchronize_session=False)
            SSHCertificateAuthority.query.filter_by(hsm_key_id=key_id).delete(
                synchronize_session=False)
            HsmKey.query.filter_by(id=key_id).delete(synchronize_session=False)
            HsmProvider.query.filter_by(id=provider_id).delete(synchronize_session=False)
        db.session.commit()


def _patch_hsm(real_key, pub_pem):
    """HsmService.sign/get_public_key served by ``real_key``."""
    def fake_sign(key_id, data, algo=None, hash_algorithm=None):
        digest = {'sha256': hashes.SHA256, 'sha384': hashes.SHA384,
                  'sha512': hashes.SHA512}.get(hash_algorithm, hashes.SHA256)()
        if isinstance(real_key, rsa.RSAPrivateKey):
            return real_key.sign(data, padding.PKCS1v15(), digest)
        return real_key.sign(data, ec.ECDSA(digest))

    return [
        patch('services.hsm.HsmService.sign', side_effect=fake_sign),
        patch('services.hsm.HsmService.get_public_key', return_value=pub_pem),
    ]


def _with_hsm(hsm):
    """Start the HSM patches, return the stopper."""
    patches = _patch_hsm(hsm['real_key'], hsm['pub_pem'])
    for p in patches:
        p.start()
    return lambda: [p.stop() for p in patches]


def _client_public_key():
    key = ec.generate_private_key(ec.SECP256R1())
    return ssh_serialization.serialize_ssh_public_key(key.public_key()).decode()


class TestCreateHsmSshCa:

    def test_ec_key_creates_ca_without_private_material(self, app, hsm_key):
        hsm = hsm_key(ec.generate_private_key(ec.SECP384R1()), 'EC-P384')
        stop = _with_hsm(hsm)
        try:
            with app.app_context():
                ca = SSHCAService.import_hsm_ca(
                    descr='Token user CA', ca_type='user', hsm_key_id=hsm['hsm_key_id'],
                    username='tester', allow_any_principal=True,
                )
                assert ca.key_source == 'hsm'
                assert ca.hsm_key_id == hsm['hsm_key_id']
                assert ca.private_key == '', "an HSM CA stores no private key"
                assert ca.key_type == 'ecdsa-p384'
                assert ca.public_key.startswith('ecdsa-sha2-nistp384')
                expected = ssh_serialization.serialize_ssh_public_key(
                    hsm['real_key'].public_key()).decode()
                assert ca.public_key.split()[:2] == expected.split()[:2]

                row = ca.to_dict()
                assert row['key_source'] == 'hsm'
                assert row['hsm_key_label'] == f'ssh-ca-key-ec_p384'

                SSHCAService.delete_ca(ca.id)
        finally:
            stop()

    def test_rsa_key_creates_rsa_ca(self, app, hsm_key):
        hsm = hsm_key(rsa.generate_private_key(65537, 2048), 'RSA-2048')
        stop = _with_hsm(hsm)
        try:
            with app.app_context():
                ca = SSHCAService.import_hsm_ca(
                    descr='Token host CA', ca_type='host', hsm_key_id=hsm['hsm_key_id'],
                )
                assert ca.key_type == 'rsa'
                assert ca.public_key.startswith('ssh-rsa')
                SSHCAService.delete_ca(ca.id)
        finally:
            stop()

    def test_rejects_unknown_key(self, app):
        with app.app_context():
            with pytest.raises(ValueError, match='not found'):
                SSHCAService.import_hsm_ca(descr='Bad', ca_type='user', hsm_key_id=999999)

    def test_rejects_a_key_that_is_not_rsa_or_nist_ec(self, app, hsm_key):
        hsm = hsm_key(ed25519.Ed25519PrivateKey.generate(), 'ED25519')
        stop = _with_hsm(hsm)
        try:
            with app.app_context():
                with pytest.raises(ValueError):
                    SSHCAService.import_hsm_ca(
                        descr='Bad', ca_type='user', hsm_key_id=hsm['hsm_key_id'])
        finally:
            stop()

    def test_one_key_backs_a_user_and_a_host_ca(self, app, hsm_key):
        """OpenSSH keeps the two roles separate, so one token key may serve both."""
        hsm = hsm_key(ec.generate_private_key(ec.SECP384R1()), 'EC-P384')
        stop = _with_hsm(hsm)
        try:
            with app.app_context():
                user = SSHCAService.import_hsm_ca(
                    descr='Token user CA', ca_type='user', hsm_key_id=hsm['hsm_key_id'])
                host = SSHCAService.import_hsm_ca(
                    descr='Token host CA', ca_type='host', hsm_key_id=hsm['hsm_key_id'])
                assert user.fingerprint == host.fingerprint
                assert user.ca_type == 'user' and host.ca_type == 'host'
                SSHCAService.delete_ca(user.id)
                SSHCAService.delete_ca(host.id)
        finally:
            stop()

    def test_rejects_a_second_ca_of_the_same_role(self, app, hsm_key):
        hsm = hsm_key(ec.generate_private_key(ec.SECP384R1()), 'EC-P384')
        stop = _with_hsm(hsm)
        try:
            with app.app_context():
                ca = SSHCAService.import_hsm_ca(
                    descr='First user CA', ca_type='user', hsm_key_id=hsm['hsm_key_id'])
                with pytest.raises(ValueError, match='already exists'):
                    SSHCAService.import_hsm_ca(
                        descr='Second user CA', ca_type='user', hsm_key_id=hsm['hsm_key_id'])
                SSHCAService.delete_ca(ca.id)
        finally:
            stop()


class TestSignWithHsmCa:

    def test_user_certificate_verifies_against_the_token_public_key(self, app, hsm_key):
        hsm = hsm_key(ec.generate_private_key(ec.SECP384R1()), 'EC-P384')
        stop = _with_hsm(hsm)
        try:
            with app.app_context():
                ca = SSHCAService.import_hsm_ca(
                    descr='Token user CA', ca_type='user', hsm_key_id=hsm['hsm_key_id'],
                    allow_any_principal=True, allow_custom_key_id=True)
                ssh_cert = SSHCertificateService.sign_certificate(
                    ca_id=ca.id, public_key_data=_client_public_key(), cert_type='user',
                    principals=['alice'], validity_seconds=3600, key_id='alice-key',
                    username='tester')
                pem, ca_fingerprint, ca_id = ssh_cert.certificate, ca.fingerprint, ca.id
        finally:
            stop()

        cert = ssh_serialization.load_ssh_public_identity(pem.encode())
        cert.verify_cert_signature()
        # The signature key inside the certificate is the token's public half
        assert SSHCertificateService._compute_fingerprint(
            cert.signature_key()) == ca_fingerprint
        assert [p.decode() for p in cert.valid_principals] == ['alice']

        with app.app_context():
            SSHCertificate.query.filter_by(ssh_ca_id=ca_id).delete(synchronize_session=False)
            SSHCAService.delete_ca(ca_id)

    def test_host_certificate_signs_with_a_token_rsa_key(self, app, hsm_key):
        hsm = hsm_key(rsa.generate_private_key(65537, 2048), 'RSA-2048')
        stop = _with_hsm(hsm)
        try:
            with app.app_context():
                ca = SSHCAService.import_hsm_ca(
                    descr='Token host CA', ca_type='host', hsm_key_id=hsm['hsm_key_id'],
                    allow_any_principal=True, allow_custom_key_id=True)
                host_pub = ssh_serialization.serialize_ssh_public_key(
                    ed25519.Ed25519PrivateKey.generate().public_key()).decode()
                ssh_cert = SSHCertificateService.sign_certificate(
                    ca_id=ca.id, public_key_data=host_pub, cert_type='host',
                    principals=['server.example.com'], validity_seconds=3600,
                    key_id='host-key')
                pem, ca_id = ssh_cert.certificate, ca.id
        finally:
            stop()

        cert = ssh_serialization.load_ssh_public_identity(pem.encode())
        cert.verify_cert_signature()

        with app.app_context():
            SSHCertificate.query.filter_by(ssh_ca_id=ca_id).delete(synchronize_session=False)
            SSHCAService.delete_ca(ca_id)

    def test_private_key_object_is_the_hsm_wrapper(self, app, hsm_key):
        hsm = hsm_key(ec.generate_private_key(ec.SECP384R1()), 'EC-P384')
        stop = _with_hsm(hsm)
        try:
            with app.app_context():
                ca = SSHCAService.import_hsm_ca(
                    descr='Token user CA', ca_type='user', hsm_key_id=hsm['hsm_key_id'])
                from services.hsm.hsm_private_key import HsmECPrivateKey
                key = SSHCAService.get_private_key_object(ca.id)
                assert isinstance(key, HsmECPrivateKey)
                assert isinstance(key, ec.EllipticCurvePrivateKey), \
                    "cryptography checks the isinstance of the key it is asked to sign with"
                SSHCAService.delete_ca(ca.id)
        finally:
            stop()


class TestHsmSshCaApi:

    def test_create_accepts_hsm_key_id(self, app, auth_client, hsm_key):
        hsm = hsm_key(ec.generate_private_key(ec.SECP384R1()), 'EC-P384')
        stop = _with_hsm(hsm)
        try:
            r = post_json(auth_client, '/api/v2/ssh/cas', {
                'descr': 'API token CA', 'ca_type': 'user',
                'hsm_key_id': hsm['hsm_key_id'], 'allow_any_principal': True,
            })
            assert r.status_code == 201, r.data
            data = json.loads(r.data)['data']
            assert data['key_source'] == 'hsm'
            assert data['key_type'] == 'ecdsa-p384'
            assert data['hsm_key_label'] == 'ssh-ca-key-ec_p384'
        finally:
            stop()
            with app.app_context():
                SSHCertificateAuthority.query.filter_by(
                    hsm_key_id=hsm['hsm_key_id']).delete(synchronize_session=False)
                db.session.commit()

    def test_rejects_an_unknown_hsm_key_id(self, auth_client):
        r = post_json(auth_client, '/api/v2/ssh/cas',
                      {'descr': 'Bad', 'ca_type': 'user', 'hsm_key_id': 999999})
        assert r.status_code == 400, r.data

    def test_hsm_key_cannot_be_deleted_while_a_ca_uses_it(self, app, auth_client, hsm_key):
        hsm = hsm_key(ec.generate_private_key(ec.SECP384R1()), 'EC-P384')
        stop = _with_hsm(hsm)
        try:
            r = post_json(auth_client, '/api/v2/ssh/cas', {
                'descr': 'API token CA', 'ca_type': 'user', 'hsm_key_id': hsm['hsm_key_id'],
            })
            assert r.status_code == 201, r.data
            r = auth_client.delete(f"/api/v2/hsm/keys/{hsm['hsm_key_id']}")
            assert r.status_code == 409, r.data
            assert 'depend on it' in json.loads(r.data)['detail']
        finally:
            stop()
            with app.app_context():
                SSHCertificateAuthority.query.filter_by(
                    hsm_key_id=hsm['hsm_key_id']).delete(synchronize_session=False)
                db.session.commit()
