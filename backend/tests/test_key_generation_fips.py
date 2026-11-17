"""In FIPS mode keys come from ``openssl genpkey`` (the provider's EVP path),
never from pyca's low-level generators; outside FIPS mode nothing changes (#399).
"""
import base64
import datetime
import json
import subprocess

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import NameOID

import fips_mode
from fips_mode import FipsRestricted
from tests.test_est_rfc7030 import (  # noqa: F401 (est_config is a fixture)
    _basic_auth, _make_csr, _multipart_parts, _post_csr, est_config)
from utils import key_algorithms
from utils.key_algorithms import KeyGenerationError


@pytest.fixture
def genpkey(monkeypatch):
    """Records every ``openssl genpkey`` run, with the key it printed."""
    calls = []
    real_run = subprocess.run

    def spy(cmd, *args, **kwargs):
        result = real_run(cmd, *args, **kwargs)
        if isinstance(cmd, (list, tuple)) and 'genpkey' in cmd:
            calls.append({'cmd': list(cmd), 'stdout': result.stdout})
        return result

    monkeypatch.setattr(subprocess, 'run', spy)
    return calls


@pytest.fixture
def fips_on(monkeypatch):
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)


@pytest.fixture
def fips_off(monkeypatch):
    monkeypatch.setattr(fips_mode, 'enabled', lambda: False)


def _public_der(key):
    return key.public_key().public_bytes(serialization.Encoding.DER,
                                         serialization.PublicFormat.SubjectPublicKeyInfo)


def _from_subprocess(call):
    return serialization.load_pem_private_key(call['stdout'], password=None)


def _assert_single_genpkey(calls, key):
    """Exactly one genpkey run, and *key* (private or public) is the one it printed."""
    assert len(calls) == 1, calls
    public = key.public_key() if hasattr(key, 'public_key') else key
    assert public.public_bytes(serialization.Encoding.DER,
                               serialization.PublicFormat.SubjectPublicKeyInfo) \
        == _public_der(_from_subprocess(calls[0]))


def _self_signed_ca():
    """A CA built straight with pyca, so it never reaches the generator under test."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'FIPS keygen issuer')])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5))
            .not_valid_after(now + datetime.timedelta(days=365))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    return cert, key


def _fake_run(stdout=b'', stderr=b'', returncode=0):
    def run(cmd, *args, **kwargs):
        return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)
    return run


def _pem(key):
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())


class TestRegistryInFipsMode:
    @pytest.mark.parametrize('label,family,size,curve,pkeyopt', [
        ('RSA-2048', rsa.RSAPrivateKey, 2048, None, 'rsa_keygen_bits:2048'),
        ('RSA-3072', rsa.RSAPrivateKey, 3072, None, 'rsa_keygen_bits:3072'),
        ('EC-P256', ec.EllipticCurvePrivateKey, 256, 'secp256r1', 'ec_paramgen_curve:P-256'),
        ('EC-P384', ec.EllipticCurvePrivateKey, 384, 'secp384r1', 'ec_paramgen_curve:P-384'),
    ])
    def test_generation_goes_through_openssl_genpkey(self, fips_on, genpkey, label, family,
                                                      size, curve, pkeyopt):
        key = key_algorithms.generate(label)
        assert isinstance(key, family) and key.key_size == size
        if curve:
            assert key.curve.name == curve
        else:
            assert key.private_numbers().public_numbers.e == 65537
        _assert_single_genpkey(genpkey, key)
        cmd = genpkey[0]['cmd']
        assert pkeyopt in cmd and '-out' not in cmd

    @pytest.mark.parametrize('label', ['ED25519', 'ED448'])
    def test_edwards_keys_are_refused(self, fips_on, genpkey, label):
        with pytest.raises(FipsRestricted):
            key_algorithms.generate(label)
        assert genpkey == []

    def test_weak_rsa_is_refused(self, fips_on, genpkey):
        with pytest.raises(FipsRestricted):
            key_algorithms.generate_rsa(1024)
        assert genpkey == []

    @pytest.mark.parametrize('curve', [ec.SECP256K1(), ec.BrainpoolP256R1()])
    def test_unapproved_curves_are_refused(self, fips_on, genpkey, curve):
        with pytest.raises(FipsRestricted):
            key_algorithms.generate_ec(curve)
        assert genpkey == []


class TestRegistryOutsideFipsMode:
    @pytest.mark.parametrize('label', ['RSA-2048', 'EC-P256', 'EC-P384', 'ED25519', 'ED448'])
    def test_no_subprocess(self, fips_off, genpkey, label):
        alg = key_algorithms.get(label)
        assert alg.matches_key(key_algorithms.generate(label))
        assert genpkey == []

    def test_off_registry_sizes_and_curves_still_generate(self, fips_off, genpkey):
        assert key_algorithms.generate_rsa(1024).key_size == 1024
        assert key_algorithms.generate_ec(ec.SECP256K1()).curve.name == 'secp256k1'
        assert genpkey == []


class TestGenpkeyFailures:
    def test_missing_binary(self, fips_on, monkeypatch):
        monkeypatch.setattr(key_algorithms.shutil, 'which', lambda name: None)
        with pytest.raises(KeyGenerationError, match='openssl'):
            key_algorithms.generate('RSA-2048')

    def test_failure_reports_stderr_not_stdout(self, fips_on, monkeypatch):
        monkeypatch.setattr(subprocess, 'run', _fake_run(
            stdout=b'-----BEGIN PRIVATE KEY-----SECRET', returncode=1,
            stderr=b'genpkey: Error setting rsa_keygen_bits:2048 parameter\n'))
        with pytest.raises(KeyGenerationError) as exc:
            key_algorithms.generate('RSA-2048')
        assert 'rsa_keygen_bits' in str(exc.value) and 'SECRET' not in str(exc.value)

    def test_timeout(self, fips_on, monkeypatch):
        def run(cmd, *args, **kwargs):
            raise subprocess.TimeoutExpired(cmd, kwargs.get('timeout'))
        monkeypatch.setattr(subprocess, 'run', run)
        with pytest.raises(KeyGenerationError, match='timed out'):
            key_algorithms.generate('EC-P256')

    def test_garbage_output(self, fips_on, monkeypatch):
        monkeypatch.setattr(subprocess, 'run', _fake_run(stdout=b'not a key'))
        with pytest.raises(KeyGenerationError):
            key_algorithms.generate('EC-P256')

    @pytest.mark.parametrize('label,wrong', [
        ('RSA-3072', lambda: rsa.generate_private_key(65537, 2048)),
        ('RSA-2048', lambda: rsa.generate_private_key(3, 2048)),
        ('EC-P384', lambda: ec.generate_private_key(ec.SECP256R1())),
        ('EC-P256', lambda: rsa.generate_private_key(65537, 2048)),
    ])
    def test_a_key_of_the_wrong_shape_is_rejected(self, fips_on, monkeypatch, label, wrong):
        monkeypatch.setattr(subprocess, 'run', _fake_run(stdout=_pem(wrong())))
        with pytest.raises(KeyGenerationError):
            key_algorithms.generate(label)


class TestSitesInFipsMode:
    """Each generation site reaches the subprocess in FIPS mode."""

    def test_ca_creation_api(self, app, auth_client, fips_on, genpkey):
        from models import CA, db
        r = auth_client.post('/api/v2/cas', data=json.dumps({
            'type': 'root', 'commonName': 'FIPS keygen CA', 'keyAlgo': 'EC-P384',
            'validityYears': 5, 'hashAlgorithm': 'sha384'}), content_type='application/json')
        assert r.status_code in (200, 201), r.data
        body = json.loads(r.data)
        ca_id = body.get('data', body)['id']
        with app.app_context():
            ca = db.session.get(CA, ca_id)
            cert = x509.load_pem_x509_certificate(base64.b64decode(ca.crt))
            db.session.delete(ca)
            db.session.commit()
        _assert_single_genpkey(genpkey, cert.public_key())

    def test_trust_store_issuance(self, app, fips_on, genpkey):
        from services.trust_store import TrustStoreService
        ca_cert, ca_key = _self_signed_ca()
        with app.app_context():
            cert_pem, _key = TrustStoreService.create_certificate(
                x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'fips.leaf.test')]),
                ca_cert, ca_key, cert_type='server_cert', validity_days=30,
                key_type='secp384r1')
        _assert_single_genpkey(genpkey, x509.load_pem_x509_certificate(cert_pem).public_key())

    def test_trust_store_csr(self, fips_on, genpkey):
        from services.trust_store import TrustStoreService
        csr_pem, _key = TrustStoreService.generate_csr(
            x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'fips.csr.test')]), key_type='3072')
        _assert_single_genpkey(genpkey, x509.load_pem_x509_csr(csr_pem).public_key())

    @pytest.mark.parametrize('alg', ['RS256', 'ES256', 'ES384'])
    def test_acme_client_account_key(self, app, fips_on, genpkey, alg):
        from models import AcmeClientAccount, db
        from services.acme.acme_client_service import AcmeClientService
        with app.app_context():
            acct = AcmeClientAccount(directory_url='https://fips-keygen-test.example/directory',
                                     label=f'fips-{alg}', email='ops@example.com',
                                     account_key_algorithm=alg)
            db.session.add(acct)
            db.session.commit()
            try:
                key = AcmeClientService(account=acct)._get_account_key()
            finally:
                db.session.delete(acct)
                db.session.commit()
        _assert_single_genpkey(genpkey, key)

    @pytest.mark.parametrize('key_type', ['RSA-2048', 'EC-P384'])
    def test_acme_client_certificate_key(self, fips_on, genpkey, key_type):
        from services.acme.acme_client_service import CERT_KEY_TYPES
        _assert_single_genpkey(genpkey, CERT_KEY_TYPES[key_type]())

    @pytest.mark.parametrize('key_type', ['ecdsa-p256', 'rsa'])
    def test_ssh_ca_key(self, fips_on, genpkey, key_type):
        from services.ssh_ca_service import SSHCAService
        _assert_single_genpkey(genpkey, SSHCAService._generate_key(key_type))

    def test_ssh_ca_ed25519_is_refused(self, fips_on, genpkey):
        from services.ssh_ca_service import SSHCAService
        with pytest.raises(FipsRestricted):
            SSHCAService._generate_key('ed25519')

    def test_deploy_keypair_is_ecdsa_p256_from_genpkey(self, fips_on, genpkey):
        from services.deploy.ssh import generate_keypair
        _, public = generate_keypair()
        assert public.startswith('ecdsa-sha2-nistp256 ')
        assert len(genpkey) == 1 and 'ec_paramgen_curve:P-256' in genpkey[0]['cmd']

    @pytest.mark.parametrize('make', [
        lambda: rsa.generate_private_key(65537, 3072),
        lambda: ec.generate_private_key(ec.SECP521R1()),
    ])
    def test_renewal_regenerates_through_genpkey(self, app, create_ca, monkeypatch, genpkey, make):
        # Set up outside FIPS mode; only the renewal itself runs inside it
        from tests.test_renewal_alignment import _craft_row, _drop, _renew
        original = make()
        ca = create_ca(cn='FIPS rekey CA')
        row_id = _craft_row(app, ca['id'], original, f'fips-rekey-{original.key_size}.test')
        monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
        genpkey.clear()
        try:
            _, renewed = _renew(app, row_id, rekey=True)
            _assert_single_genpkey(genpkey, renewed.public_key())
            assert key_algorithms.key_algo_for_public_key(renewed.public_key()) == \
                key_algorithms.key_algo_for_public_key(original.public_key())
        finally:
            _drop(app, row_id)

    def test_renewal_of_an_off_policy_curve_is_refused(self, app, create_ca, monkeypatch, genpkey):
        from tests.test_renewal_alignment import _craft_row, _drop, _renew
        ca = create_ca(cn='FIPS off-policy curve CA')
        row_id = _craft_row(app, ca['id'], ec.generate_private_key(ec.SECP256K1()), 'fips-secp256k1.test')
        monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
        genpkey.clear()
        try:
            with pytest.raises(Exception, match='(?i)secp256k1'):
                _renew(app, row_id, rekey=True)
            assert genpkey == []
        finally:
            _drop(app, row_id)

    def test_tls_alpn_proof_certificate(self, fips_on, genpkey):
        from utils.acme_ip import build_tls_alpn01_certificate
        cert_pem, _key_pem = build_tls_alpn01_certificate('example.test', 'token.thumb')
        _assert_single_genpkey(genpkey, x509.load_pem_x509_certificate(cert_pem).public_key())

    def test_ocsp_unknown_placeholder(self, fips_on, genpkey):
        from services.ocsp_service import _build_unknown_certificate
        issuer, _issuer_key = _self_signed_ca()
        placeholder = _build_unknown_certificate(42, issuer)
        _assert_single_genpkey(genpkey, placeholder.public_key())

    def test_https_self_signed(self, fips_on, genpkey, tmp_path):
        from config.https_manager import HTTPSManager
        cert_path, _key_path = HTTPSManager.generate_self_signed_cert(
            tmp_path / 'c.pem', tmp_path / 'k.pem', common_name='fips.local')
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
        _assert_single_genpkey(genpkey, cert.public_key())

    def test_est_serverkeygen(self, client, est_config, fips_on, genpkey):
        csr, _ = _make_csr(san_names=('fips-keygen.example.test',))
        response = _post_csr(client, 'serverkeygen', csr, headers=_basic_auth())
        assert response.status_code == 200, response.data
        part = _multipart_parts(response)[0].get_payload(decode=True)
        _assert_single_genpkey(genpkey, pkcs7.load_der_pkcs7_certificates(part)[0].public_key())
