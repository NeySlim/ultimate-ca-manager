"""#366: an ECDSA signature returned raw (r || s) by an HSM must reach X.509 as DER.

PKCS#11 and Azure Key Vault hand back the raw concatenation; cryptography
embeds whatever the key wrapper returns, so a CSR, certificate or CRL signed
by an EC HSM key carried an unverifiable signature. The provider is faked at
``HsmService._get_provider_instance`` so the normalisation in
``HsmService.sign`` is what gets exercised, not a mock of it.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import (
    decode_dss_signature, encode_dss_signature,
)
from cryptography.x509.oid import NameOID

from services.hsm.ecdsa_signature import coordinate_bytes, ecdsa_to_der

CURVES = {
    'EC-P256': (ec.SECP256R1(), 32, hashes.SHA256()),
    'EC-P384': (ec.SECP384R1(), 48, hashes.SHA384()),
    'EC-P521': (ec.SECP521R1(), 66, hashes.SHA512()),
}


def _raw(der_signature: bytes, size: int) -> bytes:
    r, s = decode_dss_signature(der_signature)
    return r.to_bytes(size, 'big') + s.to_bytes(size, 'big')


class TestEcdsaToDer:
    @pytest.mark.parametrize('algorithm', sorted(CURVES))
    def test_raw_becomes_der_that_verifies(self, algorithm):
        curve, size, digest = CURVES[algorithm]
        key = ec.generate_private_key(curve)
        der = key.sign(b'tbs', ec.ECDSA(digest))
        converted = ecdsa_to_der(_raw(der, size), coordinate_bytes(algorithm))
        assert converted == der
        key.public_key().verify(converted, b'tbs', ec.ECDSA(digest))

    def test_der_passes_through_unchanged(self):
        key = ec.generate_private_key(ec.SECP384R1())
        der = key.sign(b'tbs', ec.ECDSA(hashes.SHA384()))
        assert ecdsa_to_der(der, 48) == der

    def test_der_of_exactly_two_coordinates_is_kept(self):
        # r and s short enough that the DER is 96 bytes: the codec round trip
        # recognises it, the length alone would not.
        r = int.from_bytes(b'\x01' + b'\x00' * 44, 'big')
        s = int.from_bytes(b'\x01' + b'\x00' * 44, 'big')
        der = encode_dss_signature(r, s)
        assert len(der) == 96
        assert ecdsa_to_der(der, 48) == der

    def test_unknown_key_or_other_length_is_left_alone(self):
        assert ecdsa_to_der(b'\x00' * 96, None) == b'\x00' * 96
        assert ecdsa_to_der(b'\x00' * 95, 48) == b'\x00' * 95

    def test_coordinate_bytes_from_algorithm_or_public_key(self):
        assert coordinate_bytes('EC-P521') == 66
        assert coordinate_bytes('RSA-2048') is None
        pem = ec.generate_private_key(ec.SECP384R1()).public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        assert coordinate_bytes('EC', pem) == 48
        assert coordinate_bytes('EC-P256', pem) == 48  # the key wins over a guessed label
        assert coordinate_bytes(None, 'not a pem') is None


class _FakeProvider:
    """Signs with a software key and returns what a PKCS#11 module returns.

    With ``bound=True`` it behaves like Azure or GCP: the digest is the curve's
    whatever is asked for, and ``hash_for_key`` says so.
    """

    def __init__(self, key, digest, raw: bool, bound: bool = False):
        self.key, self.digest, self.raw, self.bound = key, digest, raw, bound

    def hash_for_key(self, key_identifier, key_algorithm, requested='sha256'):
        return self.digest.name if self.bound else requested

    def delete_key(self, key_identifier):
        return True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def sign(self, key_identifier, data, algorithm=None, hash_algorithm=None):
        digest = self.digest if self.bound else {
            'sha256': hashes.SHA256(), 'sha384': hashes.SHA384(), 'sha512': hashes.SHA512(),
        }.get(hash_algorithm, self.digest)
        der = self.key.sign(data, ec.ECDSA(digest))
        return _raw(der, (self.key.curve.key_size + 7) // 8) if self.raw else der


@contextmanager
def _hsm_ec_key(app, algorithm, raw, bound=False):
    curve, _size, digest = CURVES[algorithm]
    key = ec.generate_private_key(curve)
    pub_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    with app.app_context():
        from models import db
        from models.hsm import HsmProvider, HsmKey
        tag = f'{algorithm}-{raw}-{bound}'
        provider = HsmProvider(name=f'P366-{tag}', type='pkcs11', config='{}')
        db.session.add(provider)
        db.session.commit()
        hsm_key = HsmKey(provider_id=provider.id, key_identifier=f'k366-{tag}',
                         label=f'L366-{tag}', algorithm=algorithm,
                         key_type='asymmetric', purpose='signing', public_key_pem=pub_pem)
        db.session.add(hsm_key)
        db.session.commit()
        key_id, provider_id = hsm_key.id, provider.id
    fake = _FakeProvider(key, digest, raw, bound)
    try:
        with patch('services.hsm.HsmService._get_provider_instance', return_value=fake):
            with app.app_context():
                yield key_id, key.public_key(), digest
    finally:
        with app.app_context():
            from models import db
            from models.hsm import HsmProvider, HsmKey
            from services.hsm import HsmService
            db.session.query(HsmKey).filter_by(id=key_id).delete()
            db.session.query(HsmProvider).filter_by(id=provider_id).delete()
            db.session.commit()
            HsmService.forget_signing_hash(key_id)  # SQLite may hand the id to the next key


@pytest.mark.parametrize('algorithm', sorted(CURVES))
@pytest.mark.parametrize('raw', [True, False], ids=['raw-pkcs11', 'der-openbao'])
def test_csr_and_certificate_signed_by_an_ec_hsm_key_verify(app, algorithm, raw):
    from services.hsm.hsm_private_key import load_hsm_private_key
    with _hsm_ec_key(app, algorithm, raw) as (key_id, public_key, digest):
        wrapped = load_hsm_private_key(key_id)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Test Intermediate CA')])
        csr = x509.CertificateSigningRequestBuilder().subject_name(name).sign(wrapped, digest)
        assert csr.is_signature_valid
        now = datetime.now(timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                .public_key(public_key).serial_number(7)
                .not_valid_before(now).not_valid_after(now + timedelta(days=1))
                .sign(wrapped, digest))
        public_key.verify(cert.signature, cert.tbs_certificate_bytes, ec.ECDSA(digest))


def test_generic_sign_endpoint_returns_der(app, auth_client):
    import base64
    with _hsm_ec_key(app, 'EC-P384', raw=True) as (key_id, public_key, digest):
        resp = auth_client.post(f'/api/v2/hsm/keys/{key_id}/sign',
                                json={'data': base64.b64encode(b'payload').decode()})
        assert resp.status_code == 200, resp.get_json()
        signature = base64.b64decode(resp.get_json()['data']['signature'])
        assert signature[0] == 0x30
        public_key.verify(signature, b'payload', ec.ECDSA(digest))


def test_external_ca_on_an_hsm_key_gets_the_curve_digest_by_default(app, auth_client):
    """'auto' used to resolve from the local key_type default, giving SHA-256 on P-384."""
    import base64
    with _hsm_ec_key(app, 'EC-P384', raw=True) as (key_id, _public_key, _digest):
        resp = auth_client.post('/api/v2/cas', json={
            'type': 'external', 'commonName': 'hsm-p384-auto.test', 'organization': 'T',
            'hsm_key_id': key_id, 'digest': 'auto',
        })
        assert resp.status_code in (200, 201), resp.get_json()
        ca = resp.get_json()['data']
        try:
            csr = x509.load_pem_x509_csr(ca['csr_pem'].encode())
            assert csr.is_signature_valid
            assert csr.signature_hash_algorithm.name == 'sha384'
        finally:
            auth_client.delete(f"/api/v2/cas/{ca['id']}")


@pytest.mark.skipif(
    not (__import__('shutil').which('softhsm2-util') and __import__('os').path.exists('/usr/lib/softhsm/libsofthsm2.so')),
    reason='SoftHSM not installed')
def test_pkcs11_provider_falls_back_to_raw_ecdsa_on_softhsm(tmp_path, monkeypatch):
    """SoftHSM has no ECDSA_SHA* mechanism: the provider hashes and signs raw, same signature."""
    import os
    import subprocess
    conf = tmp_path / 'softhsm2.conf'
    (tmp_path / 'tokens').mkdir()
    conf.write_text(f"directories.tokendir = {tmp_path / 'tokens'}\nobjectstore.backend = file\nlog.level = ERROR\n")
    monkeypatch.setenv('SOFTHSM2_CONF', str(conf))
    subprocess.run(['softhsm2-util', '--init-token', '--free', '--label', 'ucm366',
                    '--so-pin', '1234', '--pin', '1234'], check=True, capture_output=True)
    from services.hsm.pkcs11_provider import Pkcs11Provider, PKCS11_AVAILABLE
    if not PKCS11_AVAILABLE:
        pytest.skip('python-pkcs11 not installed')
    from services.hsm.ecdsa_signature import ecdsa_to_der
    import pkcs11
    lib_path = '/usr/lib/softhsm/libsofthsm2.so'
    _release_pkcs11_lib(pkcs11, lib_path)  # a token dir another test loaded would shadow ours
    provider = Pkcs11Provider({'module_path': lib_path, 'token_label': 'ucm366', 'user_pin': '1234'})
    try:
        with provider:
            info = provider.generate_key('p384', 'EC-P384')
            public_key = serialization.load_pem_public_key(provider.get_public_key(info.key_identifier).encode())
            signature = provider.sign(info.key_identifier, b'tbs', 'EC-P384', hash_algorithm='sha384')
            assert len(signature) == 96
            public_key.verify(ecdsa_to_der(signature, 48), b'tbs', ec.ECDSA(hashes.SHA384()))
    finally:
        _release_pkcs11_lib(pkcs11, lib_path)


def _release_pkcs11_lib(pkcs11, lib_path):
    # python-pkcs11 caches the initialised library per path and SoftHSM reads
    # SOFTHSM2_CONF once: release it so each test can use its own token dir.
    lib = getattr(pkcs11, '_loaded', {}).pop(lib_path, None)
    if lib is not None:
        lib.finalize()


def test_renewing_the_csr_keeps_the_curve_digest(app, auth_client):
    """renew-csr without a digest used to fall back to sha256 whatever the key."""
    with _hsm_ec_key(app, 'EC-P384', raw=True) as (key_id, _public_key, _digest):
        resp = auth_client.post('/api/v2/cas', json={
            'type': 'external', 'commonName': 'hsm-p384-renew.test', 'organization': 'T',
            'hsm_key_id': key_id, 'digest': 'auto',
        })
        assert resp.status_code in (200, 201), resp.get_json()
        ca = resp.get_json()['data']
        try:
            renewed = auth_client.post(f"/api/v2/cas/{ca['id']}/renew-csr", json={})
            assert renewed.status_code == 200, renewed.get_json()
            csr = x509.load_pem_x509_csr(renewed.get_json()['data']['csr_pem'].encode())
            assert csr.is_signature_valid
            assert csr.signature_hash_algorithm.name == 'sha384'
        finally:
            auth_client.delete(f"/api/v2/cas/{ca['id']}")


def _install_external_certificate(auth_client, ca, csr_pem, root_digest):
    """Sign the CA's CSR with a throwaway RSA root and install it."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    root_key = rsa.generate_private_key(65537, 2048)
    root_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'External Root 366')])
    now = datetime.now(timezone.utc)
    root = (x509.CertificateBuilder().subject_name(root_name).issuer_name(root_name)
            .public_key(root_key.public_key()).serial_number(1)
            .not_valid_before(now).not_valid_after(now + timedelta(days=30))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(root_key, root_digest))
    csr = x509.load_pem_x509_csr(csr_pem.encode())
    cert = (x509.CertificateBuilder().subject_name(csr.subject).issuer_name(root_name)
            .public_key(csr.public_key()).serial_number(2)
            .not_valid_before(now).not_valid_after(now + timedelta(days=10))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(root_key, root_digest))
    resp = auth_client.post(f"/api/v2/cas/{ca['id']}/certificate", json={
        'pem_content': cert.public_bytes(serialization.Encoding.PEM).decode()
        + root.public_bytes(serialization.Encoding.PEM).decode(),
    })
    assert resp.status_code == 200, resp.get_json()


def test_renewing_after_installation_follows_the_key_not_the_root(app, auth_client):
    """The installed certificate is signed by the external root; its digest is the root's."""
    with _hsm_ec_key(app, 'EC-P384', raw=True) as (key_id, _public_key, _digest):
        resp = auth_client.post('/api/v2/cas', json={
            'type': 'external', 'commonName': 'hsm-p384-installed.test', 'organization': 'T',
            'hsm_key_id': key_id, 'digest': 'auto',
        })
        assert resp.status_code in (200, 201), resp.get_json()
        ca = resp.get_json()['data']
        try:
            _install_external_certificate(auth_client, ca, ca['csr_pem'], hashes.SHA512())
            renewed = auth_client.post(f"/api/v2/cas/{ca['id']}/renew-csr", json={})
            assert renewed.status_code == 200, renewed.get_json()
            csr = x509.load_pem_x509_csr(renewed.get_json()['data']['csr_pem'].encode())
            assert csr.is_signature_valid
            assert csr.signature_hash_algorithm.name == 'sha384'
        finally:
            auth_client.delete(f"/api/v2/cas/{ca['id']}")


def test_csr_names_the_digest_a_bound_provider_signs_with(app, auth_client):
    """Azure and GCP sign a P-384 key with SHA-384 whatever is asked: the CSR must say so."""
    with _hsm_ec_key(app, 'EC-P384', raw=True, bound=True) as (key_id, _public_key, _digest):
        resp = auth_client.post('/api/v2/cas', json={
            'type': 'external', 'commonName': 'hsm-p384-bound.test', 'organization': 'T',
            'hsm_key_id': key_id, 'digest': 'sha256',
        })
        assert resp.status_code in (200, 201), resp.get_json()
        ca = resp.get_json()['data']
        try:
            csr = x509.load_pem_x509_csr(ca['csr_pem'].encode())
            assert csr.is_signature_valid
            assert csr.signature_hash_algorithm.name == 'sha384'
        finally:
            auth_client.delete(f"/api/v2/cas/{ca['id']}")


def test_deleting_a_key_forgets_its_cached_digest(app):
    """SQLite may give the next key the same id; a stale cached digest would then mis-sign it."""
    from services.hsm import HsmService
    with _hsm_ec_key(app, 'EC-P384', raw=True, bound=True) as (key_id, _public_key, _digest):
        assert HsmService.signing_hash(key_id, 'EC-P384', 'sha256') == 'sha384'
        assert (key_id, 'sha256') in HsmService._signing_hash_cache
        HsmService.delete_key(key_id)
        assert (key_id, 'sha256') not in HsmService._signing_hash_cache
