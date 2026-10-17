"""Keys, IVs, salts and nonces come from the FIPS module's DRBG in FIPS mode
(ssl.RAND_bytes), from os.urandom otherwise (#399)."""
import base64
import datetime
import json
import os
import ssl

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import NameOID

import fips_mode

_real_urandom = os.urandom


@pytest.fixture
def drbg(monkeypatch):
    """FIPS mode on, every ssl.RAND_bytes draw recorded."""
    drawn = []

    def rand_bytes(n):
        value = _real_urandom(n)
        drawn.append(value)
        return value

    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
    monkeypatch.setattr(ssl, 'RAND_bytes', rand_bytes)
    return drawn


def _self_signed(key):
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'randomness')])
    now = datetime.datetime.now(datetime.timezone.utc)
    return (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now).not_valid_after(now + datetime.timedelta(days=1))
            .sign(key, hashes.SHA256()))


@pytest.fixture(scope='module')
def rsa_identity():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key, _self_signed(key)


class TestCspBytes:
    def test_fips_mode_draws_from_the_module_drbg(self, drbg):
        from utils.randomness import csp_bytes
        value = csp_bytes(24)
        assert drbg == [value] and len(value) == 24

    def test_standard_mode_uses_os_urandom(self, monkeypatch):
        from utils.randomness import csp_bytes

        def rand_bytes(n):
            raise AssertionError('ssl.RAND_bytes used outside FIPS mode')

        drawn = []

        def urandom(n):
            drawn.append(_real_urandom(n))
            return drawn[-1]

        monkeypatch.setattr(fips_mode, 'enabled', lambda: False)
        monkeypatch.setattr(ssl, 'RAND_bytes', rand_bytes)
        monkeypatch.setattr(os, 'urandom', urandom)
        value = csp_bytes(24)
        assert drawn == [value] and len(value) == 24

    @pytest.mark.parametrize('fips', [False, True])
    def test_length_and_uniqueness(self, monkeypatch, fips):
        from utils.randomness import csp_bytes
        monkeypatch.setattr(fips_mode, 'enabled', lambda: fips)
        values = {csp_bytes(16) for _ in range(64)}
        assert len(values) == 64 and all(len(v) == 16 for v in values)
        assert csp_bytes(0) == b''


class TestSitesDrawFromTheDrbg:
    def test_master_key(self, drbg):
        from security.encryption import KeyEncryption
        key = KeyEncryption.generate_key()
        assert base64.urlsafe_b64decode(key) == drbg[0] and len(drbg[0]) == 32

    def test_machine_key_fallback(self, drbg, monkeypatch):
        import utils.encryption as module
        written = {}

        class _Sink:
            def __init__(self, path):
                self.path = path

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def write(self, data):
                written[self.path] = data

        def fake_open(path, mode='r', *a, **k):
            if 'w' in mode:
                return _Sink(path)
            raise FileNotFoundError(path)

        monkeypatch.setattr(module, 'open', fake_open, raising=False)
        monkeypatch.setattr(module.os, 'makedirs', lambda *a, **k: None)
        monkeypatch.delenv('UCM_DB_ENCRYPTION_KEY', raising=False)
        monkeypatch.setattr(module, '_require_db_encryption_key', lambda: False)
        module._get_encryption_key()
        assert list(written.values()) == [drbg[0].hex()]

    def test_est_server_generated_key(self, drbg, rsa_identity):
        from utils.est_cms import build_server_generated_key_cms
        key, cert = rsa_identity
        build_server_generated_key_cms(key, cert, cert)
        assert [len(v) for v in drbg] == [32, 16]

    def test_scep_key_transport_envelope(self, drbg, rsa_identity):
        from services.scep.crypto_helpers import AES256_CBC, encrypt_for_client
        _key, cert = rsa_identity
        encrypt_for_client(b'payload', cert, content_encryption_algorithm=AES256_CBC)
        assert [len(v) for v in drbg] == [32, 16]

    def test_scep_password_envelope(self, drbg):
        from services.scep.crypto_helpers import AES128_CBC, encrypt_for_client
        key = ec.generate_private_key(ec.SECP256R1())
        encrypt_for_client(b'payload', _self_signed(key), password='challenge',
                           content_encryption_algorithm=AES128_CBC)
        # content key and IV, PWRI salt and KEK IV, RFC 3211 padding
        assert [len(v) for v in drbg] == [16, 16, 16, 16, 12]

    def test_backup_salt_and_nonces(self, drbg, app):
        from services.backup import container, manifest
        from services.backup_service import BackupService
        include = {name: name == 'groups' for name in manifest.SECTIONS}
        with app.app_context():
            blob = BackupService().create_backup('Correct-Horse-Battery-9', include=include)
        metadata, _header, _ciphertext = container.parse_header(blob)
        salt, nonce, _params = container.validate_kdf(metadata['kdf_id'], metadata)
        assert salt in drbg and nonce in drbg

    def test_backup_private_key_blob(self, drbg):
        from services.backup_service import BackupService
        blob = BackupService()._encrypt_private_key('pem', b'k' * 32)
        assert [bytes.fromhex(blob['salt']), bytes.fromhex(blob['nonce'])] == drbg

    def test_legacy_backup_helpers(self, drbg):
        from services.backup_service import BackupService
        svc = BackupService()
        _key, salt = svc._derive_master_key('Correct-Horse-Battery-9')
        sealed = svc._encrypt_backup(b'data', b'k' * 32)
        assert drbg == [salt, sealed[:svc.NONCE_SIZE]]

    def test_acme_eab_hmac_key(self, drbg, auth_client):
        r = auth_client.post('/api/v2/acme/eab-credentials',
                             data=json.dumps({'label': 'fips-drbg'}),
                             content_type='application/json')
        assert r.status_code == 201, r.data
        cred = json.loads(r.data)['data']
        auth_client.delete(f"/api/v2/acme/eab-credentials/{cred['id']}")
        hmac_key = base64.urlsafe_b64decode(cred['hmac_key'] + '=' * (-len(cred['hmac_key']) % 4))
        assert hmac_key in drbg
