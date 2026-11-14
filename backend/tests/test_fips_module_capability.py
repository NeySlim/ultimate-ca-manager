"""FIPS mode allows EdDSA and ML-DSA if and only if the loaded module approves them.

The module is simulated both ways (``module_approves``): approving (OpenSSL FIPS
Provider 3.5.9) and not approving (3.1.2, RHEL 9, Ubuntu 24.04). Not approving, every
refusal keeps its message; approving, the same paths succeed, except a signature made
outside the module (paramiko's Ed25519, PyNaCl), which stays refused.
"""
import base64
import datetime
import json
import uuid

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed448, ed25519, mldsa, rsa
from cryptography.x509.oid import NameOID

import fips_mode
from fips_mode import FipsRestricted
from models import CA, SSHCertificateAuthority, db
from utils import key_algorithms

ALL = frozenset(fips_mode.MODULE_DEPENDENT_SIGNATURES)
CLASSICAL = ('RSA-2048', 'RSA-3072', 'RSA-4096', 'EC-P256', 'EC-P384', 'EC-P521')


@pytest.fixture
def fips_on(monkeypatch):
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)


def _module(monkeypatch, approves):
    approves = frozenset(a.upper() for a in approves)
    monkeypatch.setattr(fips_mode, 'module_approves', lambda alg: str(alg).upper() in approves)


@pytest.fixture
def approving(monkeypatch, fips_on):
    _module(monkeypatch, ALL)


@pytest.fixture
def not_approving(monkeypatch, fips_on):
    _module(monkeypatch, ())


def _post(client, url, payload):
    return client.post(url, data=json.dumps(payload), content_type='application/json')


def _assert_fips_problem(r, name):
    body = r.get_json()
    assert r.status_code == 400, body
    assert body['type'] == fips_mode.PROBLEM_TYPE, body
    assert name in body['detail'] and 'not available in FIPS mode' in body['detail'], body


def _self_signed_ca(key, cn, digest=None):
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.datetime.now(datetime.timezone.utc)
    builder = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
               .public_key(key.public_key()).serial_number(x509.random_serial_number())
               .not_valid_before(now - datetime.timedelta(minutes=5))
               .not_valid_after(now + datetime.timedelta(days=30))
               .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True))
    return builder.sign(key, digest)


# ---------------------------------------------------------------- the capability

class TestCapability:
    def test_the_query_asks_the_module_by_algorithm_name(self, monkeypatch):
        # The local libcrypto has no FIPS provider; the default one answers the same query shape
        fips_mode._module_offers.cache_clear()
        monkeypatch.setattr(fips_mode, '_APPROVED_QUERY', b'provider=default')
        try:
            assert fips_mode._module_offers('ML-DSA-65') is True
            assert fips_mode._module_offers('ED25519') is True
            assert fips_mode._module_offers('NO-SUCH-SIGNATURE') is False
        finally:
            fips_mode._module_offers.cache_clear()

    def test_without_a_fips_provider_nothing_is_approved(self):
        fips_mode._module_offers.cache_clear()
        assert fips_mode.approved_module_signatures() == ()
        assert not fips_mode.module_approves('ED25519')

    def test_refuse_unless_approved_keeps_the_refusal_message(self, not_approving):
        with pytest.raises(FipsRestricted, match='^Ed25519 keys not available in FIPS mode$'):
            fips_mode.refuse_unless_approved('ED25519', 'Ed25519 keys')

    def test_refuse_unless_approved_lets_an_approved_algorithm_through(self, approving):
        fips_mode.refuse_unless_approved('ML-DSA-65', 'ML-DSA-65 keys')

    def test_outside_fips_mode_nothing_is_refused(self, monkeypatch):
        monkeypatch.setattr(fips_mode, 'enabled', lambda: False)
        _module(monkeypatch, ())
        fips_mode.refuse_unless_approved('ED25519', 'Ed25519 keys')


class TestSelfTests:
    @pytest.mark.parametrize('algorithm', sorted(ALL))
    def test_each_signature_self_test_signs_and_verifies(self, algorithm):
        fips_mode._signature_self_test(algorithm)

    def test_a_failing_signature_stops_the_start(self, monkeypatch):
        def broken(self, data):
            raise ValueError('provider refused')
        monkeypatch.setattr(ed25519.Ed25519PrivateKey, 'sign', broken, raising=False)
        monkeypatch.setattr(ed25519.Ed25519PrivateKey, 'from_private_bytes',
                            classmethod(lambda cls, data: type('K', (), {
                                'sign': broken, 'public_key': lambda self: None})()))
        with pytest.raises(RuntimeError, match='ED25519 self-test failed'):
            fips_mode._signature_self_test('ED25519')

    def test_self_tests_run_one_per_approved_signature(self, monkeypatch):
        import hashlib
        from cryptography.hazmat.primitives import hashes as pyca_hashes
        real_hash = pyca_hashes.Hash

        def refusing_md5(algorithm, *args, **kwargs):
            if isinstance(algorithm, pyca_hashes.MD5):
                raise ValueError('MD5 refused')
            return real_hash(algorithm, *args, **kwargs)

        def refusing_scrypt(*args, **kwargs):
            raise ValueError('scrypt refused')
        monkeypatch.setattr(pyca_hashes, 'Hash', refusing_md5)
        monkeypatch.setattr(hashlib, 'scrypt', refusing_scrypt)
        ran = []
        monkeypatch.setattr(fips_mode, '_signature_self_test', ran.append)
        _module(monkeypatch, ('ED25519', 'ML-DSA-65'))
        fips_mode.self_tests()
        assert ran == ['ED25519', 'ML-DSA-65']
        _module(monkeypatch, ())
        ran.clear()
        fips_mode.self_tests()
        assert ran == []

    def test_enforce_at_startup_exits_on_a_failed_signature_self_test(self, monkeypatch):
        import logging
        from cryptography.hazmat.bindings._rust import openssl as rust_openssl
        import _hashlib
        monkeypatch.setenv('UCM_FIPS', '1')
        monkeypatch.setattr(rust_openssl, 'is_fips_enabled', lambda: True)
        monkeypatch.setattr(_hashlib, 'get_fips_mode', lambda: 1, raising=False)

        def failing():
            raise RuntimeError('ML-DSA-65 self-test failed although the module approves it: x')
        monkeypatch.setattr(fips_mode, 'self_tests', failing)
        with pytest.raises(SystemExit):
            fips_mode.enforce_at_startup(logging.getLogger('test'))


# ------------------------------------------------------------------ the registry

class TestRegistry:
    def test_approving_module_adds_eddsa_and_mldsa(self, approving):
        labels = key_algorithms.fips_approved_labels()
        assert labels[:6] == CLASSICAL
        assert {'ED25519', 'ED448', 'ML-DSA-44', 'ML-DSA-65', 'ML-DSA-87'} <= set(labels)
        assert not key_algorithms.fips_approved('EC-BP256')
        assert key_algorithms.fips_approved_for_key(ed25519.Ed25519PrivateKey.generate())

    def test_not_approving_module_keeps_the_classical_list(self, not_approving):
        assert key_algorithms.fips_approved_labels() == CLASSICAL
        assert not key_algorithms.fips_approved_for_key(ed448.Ed448PrivateKey.generate())

    @pytest.mark.parametrize('label', ['ED25519', 'ED448', 'ML-DSA-65'])
    def test_generation_is_refused_with_the_same_message(self, not_approving, label):
        display = key_algorithms.get(label).display
        with pytest.raises(FipsRestricted, match=f'^{display} keys not available in FIPS mode$'):
            key_algorithms.generate(label)

    @pytest.mark.parametrize('label,cls', [
        ('ED25519', ed25519.Ed25519PrivateKey), ('ED448', ed448.Ed448PrivateKey),
        ('ML-DSA-44', mldsa.MLDSA44PrivateKey), ('ML-DSA-65', mldsa.MLDSA65PrivateKey),
        ('ML-DSA-87', mldsa.MLDSA87PrivateKey)])
    def test_generation_runs_genpkey_and_the_key_reloads(self, approving, monkeypatch, label, cls):
        import subprocess
        printed = []
        real_run = subprocess.run

        def spy(cmd, *args, **kwargs):
            result = real_run(cmd, *args, **kwargs)
            if isinstance(cmd, (list, tuple)) and 'genpkey' in cmd:
                printed.append(result.stdout)
            return result
        monkeypatch.setattr(subprocess, 'run', spy)
        key = key_algorithms.generate(label)
        assert isinstance(key, cls) and len(printed) == 1
        # The printed PEM loads on its own, and so does the PKCS#8 UCM stores
        reloaded = serialization.load_pem_private_key(printed[0], password=None)
        pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
        again = serialization.load_pem_private_key(pem, password=None)
        assert reloaded.public_key().public_bytes_raw() == again.public_key().public_bytes_raw()
        again.public_key().verify(again.sign(b'ucm'), b'ucm')


# ------------------------------------------------------------- keys by their name

class TestKeysByName:
    def _pem(self, key):
        return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                 serialization.NoEncryption())

    @pytest.mark.parametrize('key,name', [(ed25519.Ed25519PrivateKey.generate(), 'Ed25519'),
                                          (ed448.Ed448PrivateKey.generate(), 'Ed448')])
    def test_refuse_eddsa_key(self, monkeypatch, fips_on, key, name):
        from utils.key_codec import refuse_eddsa_key
        _module(monkeypatch, ())
        with pytest.raises(FipsRestricted, match=f'^{name} key of the file not available in FIPS mode$'):
            refuse_eddsa_key(self._pem(key), 'the file')
        _module(monkeypatch, ALL)
        refuse_eddsa_key(self._pem(key), 'the file')

    def test_a_key_signed_outside_the_module_stays_refused(self, approving):
        from utils.key_codec import refuse_eddsa_key
        with pytest.raises(FipsRestricted, match='Ed25519 key of x not available in FIPS mode'):
            refuse_eddsa_key(self._pem(ed25519.Ed25519PrivateKey.generate()), 'x',
                             signed_in_module=False)

    def test_deploy_ed25519_key_stays_refused_with_an_approving_module(self, approving):
        """paramiko signs Ed25519 with PyNaCl: approved by the module, but not signed in it."""
        from services.deploy.ssh import generate_keypair, load_private_key
        key = ed25519.Ed25519PrivateKey.generate()
        text = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH,
                                 serialization.NoEncryption()).decode()
        with pytest.raises(FipsRestricted, match='Ed25519 key of the deploy target'):
            load_private_key(text)
        assert generate_keypair()[1].startswith('ecdsa-sha2-nistp256 ')


# --------------------------------------------------------------- enrollment keys

class TestEnrollmentKeys:
    def test_mldsa_csr_key(self, monkeypatch, fips_on):
        from utils.key_type import validate_enrollment_public_key
        public = mldsa.MLDSA65PrivateKey.generate().public_key()
        _module(monkeypatch, ())
        assert validate_enrollment_public_key(public) == 'ML-DSA-65 keys are not available in FIPS mode'
        _module(monkeypatch, ALL)
        assert validate_enrollment_public_key(public) is None

    def test_slh_dsa_stays_refused(self, monkeypatch, fips_on):
        """pyca cannot load SLH-DSA, whatever the module approves (3.5.9 approves it)."""
        from services.fips_preflight import certificate_key
        _module(monkeypatch, ALL | {'SLH-DSA-SHA2-128s'})

        class Unloadable:
            public_key_algorithm_oid = x509.ObjectIdentifier('2.16.840.1.101.3.4.3.20')
        assert certificate_key(Unloadable()) == ('SLH-DSA-SHA2-128s', False)

    def test_scep_mldsa_cms_signature(self, monkeypatch, fips_on):
        from services.scep.message_parser import extract_signer_certificate, verify_cms_signature
        from tests.pqc_fixtures import fixture_bytes
        from tests.test_scep_pq import _signed_data
        sd = _signed_data(fixture_bytes('mldsa65-signed.cms'))
        signer = extract_signer_certificate(sd)
        _module(monkeypatch, ())
        with pytest.raises(FipsRestricted, match='^ML-DSA-65 CMS signatures not available in FIPS mode$'):
            verify_cms_signature(sd, signer)
        _module(monkeypatch, ALL)
        verify_cms_signature(sd, signer)

    def test_xcep_offers_mldsa_only_with_an_approving_module(self, monkeypatch, app, fips_on):
        from services.xcep.policy_builder import _key_type_info
        with app.app_context():
            _module(monkeypatch, ())
            assert _key_type_info('ML-DSA-65') is None
            _module(monkeypatch, ALL)
            assert _key_type_info('ML-DSA-65') == ('ML-DSA-65', 0)


# ------------------------------------------------------------------- SSH and HSM

class TestSshAndHsm:
    def test_ssh_default_key_type(self, monkeypatch, fips_on):
        from services.ssh_ca_service import default_key_type
        _module(monkeypatch, ())
        assert default_key_type() == 'ecdsa-p256'
        _module(monkeypatch, ALL)
        assert default_key_type() == 'ed25519'

    def test_ssh_ca_of_an_ed25519_key(self, monkeypatch, fips_on):
        from services.ssh_ca_service import SSHCAService
        ca = SSHCertificateAuthority(descr='Ed CA', key_type='ed25519')
        _module(monkeypatch, ())
        with pytest.raises(FipsRestricted, match="^Ed25519 key of SSH CA 'Ed CA' not available in FIPS mode$"):
            SSHCAService.refuse_unusable_ca(ca)
        _module(monkeypatch, ALL)
        SSHCAService.refuse_unusable_ca(ca)

    def test_ssh_ca_api(self, monkeypatch, auth_client, fips_on):
        _module(monkeypatch, ())
        r = _post(auth_client, '/api/v2/ssh/cas', {'descr': 'FIPS ed', 'key_type': 'ed25519'})
        _assert_fips_problem(r, 'Ed25519')
        _module(monkeypatch, ALL)
        r = _post(auth_client, '/api/v2/ssh/cas', {'descr': f'FIPS ed {uuid.uuid4().hex[:6]}',
                                                   'key_type': 'ed25519', 'allow_any_principal': True})
        assert r.status_code == 201, r.get_json()
        assert r.get_json()['data']['key_type'] == 'ed25519'

    @pytest.mark.parametrize('approves', [(), ALL])
    def test_ca_on_an_hsm_ml_dsa_key(self, monkeypatch, app, auth_client, fips_on, approves):
        from models.hsm import HsmKey, HsmProvider
        _module(monkeypatch, approves)
        public = mldsa.MLDSA65PrivateKey.generate().public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        suffix = uuid.uuid4().hex[:6]
        with app.app_context():
            provider = HsmProvider(name=f'tok-{suffix}', type='pkcs11', config='{}')
            db.session.add(provider)
            db.session.commit()
            key = HsmKey(provider_id=provider.id, key_identifier=f'pq-{suffix}', label=f'pq-{suffix}',
                         algorithm='ML-DSA-65', key_type='asymmetric', purpose='signing',
                         public_key_pem=public)
            db.session.add(key)
            db.session.commit()
            provider_id, key_id = provider.id, key.id
        try:
            base = {'type': 'root', 'commonName': f'FIPS HSM PQ {suffix}', 'validityYears': 2}
            for body in ({'hsmKeyId': key_id}, {'hsmProviderId': provider_id, 'hsmKeyLabel': f'new-{suffix}',
                                                'hsmKeyAlgorithm': 'ML-DSA-65'}):
                r = _post(auth_client, '/api/v2/cas', {**base, **body})
                if approves or 'hsmKeyId' in body:  # an existing key: the signing rule, at binding
                    _assert_fips_problem(r, 'ML-DSA-65')
                else:  # the FIPS mode policy refuses a key to generate first, as before
                    assert r.status_code == 400 and 'Key type ML-DSA-65 is not allowed by policy "FIPS mode"' \
                        in r.get_json()['detail'], r.get_json()
        finally:
            with app.app_context():
                db.session.delete(db.session.get(HsmKey, key_id))
                db.session.delete(db.session.get(HsmProvider, provider_id))
                db.session.commit()

    @pytest.mark.parametrize('approves', [(), ALL])
    def test_openbao_inventory(self, monkeypatch, fips_on, approves):
        # OpenBao signs, not the loaded module: its EdDSA and ML-DSA keys stay out either way
        from services.hsm.openbao_provider import fips_hides_transit
        _module(monkeypatch, approves)
        assert all(fips_hides_transit(t) for t in ('ed25519', 'mldsa-65', 'mldsa-87', 'chacha20-poly1305'))
        assert not fips_hides_transit('rsa-2048')
        monkeypatch.setattr(fips_mode, 'enabled', lambda: False)
        assert not fips_hides_transit('mldsa-65')

    @pytest.mark.parametrize('approves', [(), ALL])
    def test_hsm_ml_dsa_key_signed_outside_the_module(self, monkeypatch, app, fips_on, approves):
        from models.hsm import HsmProvider
        from services.hsm import HsmService
        _module(monkeypatch, approves)
        with app.app_context():
            provider = HsmProvider(name=f'bao-{uuid.uuid4().hex[:6]}', type='openbao', config='{}')
            db.session.add(provider)
            db.session.commit()
            try:
                with pytest.raises(FipsRestricted, match='^ML-DSA-65 keys not available in FIPS mode$'):
                    HsmService.generate_key(provider.id, 'pq-key', 'ML-DSA-65')
            finally:
                db.session.delete(provider)
                db.session.commit()

    @pytest.mark.parametrize('approves', [(), ALL])
    def test_hsm_sign_refuses_ml_dsa_in_fips_mode(self, monkeypatch, app, approves):
        # A CA bound to an HSM ML-DSA key before the switch must not keep signing after it
        from models.hsm import HsmKey, HsmProvider
        from services.hsm import HsmService
        _module(monkeypatch, approves)

        class _Stub:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def sign(self, *args, **kwargs):
                return b'signature'

        monkeypatch.setattr(HsmService, '_get_provider_instance', classmethod(lambda cls, p: _Stub()))
        pq = mldsa.MLDSA65PrivateKey.generate().public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        suffix = uuid.uuid4().hex[:6]
        with app.app_context():
            provider = HsmProvider(name=f'bao-{suffix}', type='openbao', config='{}')
            db.session.add(provider)
            db.session.commit()
            key = HsmKey(provider_id=provider.id, key_identifier=f'pq-{suffix}', label=f'pq-{suffix}',
                         algorithm='ML-DSA-65', key_type='asymmetric', purpose='signing',
                         public_key_pem=pq)
            db.session.add(key)
            db.session.commit()
            try:
                monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
                with pytest.raises(FipsRestricted, match='^ML-DSA-65 keys not available in FIPS mode$'):
                    HsmService.sign(key.id, b'tbs')
                monkeypatch.setattr(fips_mode, 'enabled', lambda: False)
                assert HsmService.sign(key.id, b'tbs') == b'signature'
            finally:
                db.session.delete(key)
                db.session.delete(provider)
                db.session.commit()


def _pem(public_key):
    return public_key.public_bytes(serialization.Encoding.PEM,
                                   serialization.PublicFormat.SubjectPublicKeyInfo).decode()


def _rsa_public(bits):
    # Any odd modulus of the size: the stub signs, nothing is computed with it
    return rsa.RSAPublicNumbers(65537, (1 << (bits - 1)) | 1).public_key()


def _ec_public(curve):
    return ec.generate_private_key(curve).public_key()


class _SigningStub:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def sign(self, *args, **kwargs):
        return b'signature'


@pytest.fixture
def hsm_signing_key(monkeypatch, app):
    """Factory of HSM signing keys on a stub provider; rows removed afterwards."""
    from models.hsm import HsmKey, HsmProvider
    from services.hsm import HsmService
    monkeypatch.setattr(HsmService, '_get_provider_instance', classmethod(lambda cls, p: _SigningStub()))
    created = []

    def make(algorithm, public_pem):
        suffix = uuid.uuid4().hex[:6]
        provider = HsmProvider(name=f'tok-{suffix}', type='pkcs11', config='{}')
        db.session.add(provider)
        db.session.commit()
        key = HsmKey(provider_id=provider.id, key_identifier=f'k-{suffix}', label=f'k-{suffix}',
                     algorithm=algorithm, key_type='asymmetric', purpose='signing',
                     public_key_pem=public_pem)
        db.session.add(key)
        db.session.commit()
        created.append((key, provider))
        return key

    with app.app_context():
        yield make
        for key, provider in created:
            db.session.delete(key)
            db.session.delete(provider)
        db.session.commit()


class TestHsmSigningInFipsMode:
    """An HSM signs outside the module: only RSA 2048+ and NIST curves sign in FIPS mode."""

    @pytest.mark.parametrize('algorithm,public,name', [
        ('RSA-1024', lambda: _rsa_public(1024), 'RSA 1024'),
        ('RSA-2047', lambda: _rsa_public(2047), 'RSA 2047'),
        ('UNKNOWN', lambda: _ec_public(ec.SECP256K1()), 'EC secp256k1'),
        ('EC-BP256', lambda: _ec_public(ec.BrainpoolP256R1()), 'EC Brainpool P256r1'),
        ('UNKNOWN', lambda: None, 'UNKNOWN'),
    ])
    @pytest.mark.parametrize('approves', [(), ALL])
    def test_unapproved_keys_are_refused(self, monkeypatch, hsm_signing_key, approves,
                                         algorithm, public, name):
        from services.hsm import HsmService
        _module(monkeypatch, approves)
        pem = public()
        key = hsm_signing_key(algorithm, _pem(pem) if pem is not None else None)
        monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
        with pytest.raises(FipsRestricted, match=f'^{name} keys not available in FIPS mode$'):
            HsmService.sign(key.id, b'tbs', hash_algorithm='sha256')
        monkeypatch.setattr(fips_mode, 'enabled', lambda: False)
        assert HsmService.sign(key.id, b'tbs', hash_algorithm='sha256') == b'signature'

    @pytest.mark.parametrize('algorithm,bits', [
        ('RSA-2048', 2048), ('RSA-3072', 3072), ('RSA-4096', 4096), ('RSA-8192', 8192),
        ('EC-P256', 256), ('EC-P384', 384), ('EC-P521', 521),
    ])
    @pytest.mark.parametrize('approves', [(), ALL])
    def test_classical_keys_sign(self, monkeypatch, hsm_signing_key, fips_on, approves, algorithm, bits):
        from services.hsm import HsmService
        _module(monkeypatch, approves)
        if algorithm.startswith('RSA'):
            public = _rsa_public(bits)
        else:
            public = _ec_public({256: ec.SECP256R1, 384: ec.SECP384R1, 521: ec.SECP521R1}[bits]())
        key = hsm_signing_key(algorithm, _pem(public))
        assert HsmService.sign(key.id, b'tbs', hash_algorithm='sha256') == b'signature'

    @pytest.mark.parametrize('label,bits,signs', [
        ('RSA-8192', 2048, True), ('UNKNOWN', 3072, True), ('RSA-2048', 1024, False),
    ])
    def test_uncached_key_is_judged_on_the_fetched_public_key(self, monkeypatch, hsm_signing_key,
                                                             fips_on, label, bits, signs):
        # A synced key without a cached public key (Google KMS) is judged on the one its provider returns
        from services.hsm import HsmService
        pem = _pem(_rsa_public(bits))

        class _Publishing(_SigningStub):
            def get_public_key(self, key_identifier):
                return pem

        monkeypatch.setattr(HsmService, '_get_provider_instance', classmethod(lambda cls, p: _Publishing()))
        key = hsm_signing_key(label, None)
        if signs:
            assert HsmService.sign(key.id, b'tbs', hash_algorithm='sha256') == b'signature'
        else:
            with pytest.raises(FipsRestricted, match=f'^RSA {bits} keys not available in FIPS mode$'):
                HsmService.sign(key.id, b'tbs', hash_algorithm='sha256')
        assert key.public_key_pem == pem


# ----------------------------------------------------------- renewal and imports

class TestRenewalAndImport:
    @pytest.mark.parametrize('key_algo,name', [('Ed25519', 'Ed25519'), ('Ed448', 'Ed448')])
    def test_renewal_of_an_eddsa_certificate(self, monkeypatch, app, fips_on, key_algo, name):
        from models import Certificate
        from services.cert.renewal import RenewalError, check_renewable
        cert = Certificate(id=987654, key_algo=key_algo, prv='x', crt='x', caref='nope')

        def reaches_the_fips_check():
            try:
                check_renewable(cert)
            except RenewalError as e:
                return e
            return None
        with app.app_context():
            _module(monkeypatch, ())
            err = reaches_the_fips_check()
            assert err is not None and err.problem_type == fips_mode.PROBLEM_TYPE, err
            assert str(err) == f'{name} key of certificate 987654 not available in FIPS mode'
            _module(monkeypatch, ALL)
            err = reaches_the_fips_check()
            assert err is None or err.problem_type != fips_mode.PROBLEM_TYPE, err

    def test_ml_dsa_ca_import(self, monkeypatch, auth_client, fips_on):
        key = mldsa.MLDSA65PrivateKey.generate()
        cert = _self_signed_ca(key, f'PQ import {uuid.uuid4().hex[:8]}')
        pem = (cert.public_bytes(serialization.Encoding.PEM) + key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption())).decode()
        _module(monkeypatch, ())
        r = auth_client.post('/api/v2/cas/import', data={'pem_content': pem})
        _assert_fips_problem(r, 'ML-DSA-65 key of the imported file')
        _module(monkeypatch, ALL)
        r = auth_client.post('/api/v2/cas/import', data={'pem_content': pem})
        assert r.status_code == 201, r.get_json()

    def test_ml_dsa_smart_import(self, monkeypatch, fips_on):
        from services.smart_import.importer import SmartImporter
        key = mldsa.MLDSA44PrivateKey.generate()
        pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
        _module(monkeypatch, ())
        with pytest.raises(FipsRestricted, match='ML-DSA-44 key of the imported file'):
            SmartImporter()._parse_fresh(pem, None)
        _module(monkeypatch, ALL)
        assert SmartImporter()._parse_fresh(pem, None)


# --------------------------------------------------------------- CA and policies

class TestCaAndPolicies:
    @pytest.mark.parametrize('body,name', [
        ({'keyAlgo': 'ML-DSA', 'keySize': 65}, 'ML-DSA-65'),
        ({'keyAlgo': 'EdDSA', 'keySize': 'Ed25519'}, 'Ed25519'),
    ])
    def test_ca_creation(self, monkeypatch, app, auth_client, fips_on, body, name):
        payload = {'type': 'root', 'commonName': f'FIPS {name} {uuid.uuid4().hex[:6]}',
                   'validityYears': 2, **body}
        _module(monkeypatch, ())
        _assert_fips_problem(_post(auth_client, '/api/v2/cas', payload), name)
        _module(monkeypatch, ALL)
        r = _post(auth_client, '/api/v2/cas', payload)
        assert r.status_code == 201, r.get_json()
        with app.app_context():
            row = db.session.get(CA, r.get_json()['data']['id'])
            public = x509.load_pem_x509_certificate(base64.b64decode(row.crt)).public_key()
        assert key_algorithms.label_for_public_key(public) == name.upper()

    def test_policy_rules(self, monkeypatch, app, fips_on):
        from api.v2.policies import _validated_algorithm_rules
        with app.app_context():
            _module(monkeypatch, ())
            with pytest.raises(FipsRestricted, match='^ED25519 keys not available in FIPS mode$'):
                _validated_algorithm_rules({'allowed_key_types': ['ED25519']})
            _module(monkeypatch, ALL)
            assert _validated_algorithm_rules({'allowed_key_types': ['ED25519', 'ML-DSA-65']}) is None

    def test_effective_policy_names_what_the_module_approves(self, monkeypatch, auth_client, fips_on):
        _module(monkeypatch, ('ML-DSA-65',))
        data = auth_client.get('/api/v2/policies/effective').get_json()['data']
        assert data['fips'] is True
        assert data['fips_key_types'] == [*CLASSICAL, 'ML-DSA-65']
        assert 'ML-DSA-65' in data['allowed_key_types'] and 'ED25519' not in data['allowed_key_types']

    def test_effective_policy_outside_fips_mode_is_unchanged(self, auth_client):
        data = auth_client.get('/api/v2/policies/effective').get_json()['data']
        assert 'fips' not in data and 'fips_key_types' not in data


# ------------------------------------------------------------- HMAC key length

class TestShortHmacKeys:
    def _webhook(self, auth_client, secret):
        return _post(auth_client, '/api/v2/webhooks', {
            'name': f'fips-hook-{uuid.uuid4().hex[:6]}', 'url': 'https://hooks.example.test/in',
            'secret': secret})

    def test_webhook_secret_under_14_bytes_is_refused_in_fips_mode(self, auth_client, fips_on):
        r = self._webhook(auth_client, 'x' * 13)
        body = r.get_json()
        assert r.status_code == 400 and body['type'] == fips_mode.PROBLEM_TYPE, body
        assert 'Webhook secret of 13 bytes' in body['detail'], body
        r = self._webhook(auth_client, 'x' * 14)
        assert r.status_code == 201, r.get_json()
        hook = r.get_json()['data']['id']
        r = auth_client.put(f'/api/v2/webhooks/{hook}', data=json.dumps({'secret': 'short'}),
                            content_type='application/json')
        assert r.status_code == 400 and r.get_json()['type'] == fips_mode.PROBLEM_TYPE
        auth_client.delete(f'/api/v2/webhooks/{hook}')

    def test_webhook_short_secret_outside_fips_mode_is_unchanged(self, auth_client):
        r = self._webhook(auth_client, 'short')
        assert r.status_code == 201, r.get_json()
        auth_client.delete(f"/api/v2/webhooks/{r.get_json()['data']['id']}")

    def test_dns_provider_api_refuses_a_short_tsig_secret(self, auth_client, fips_on):
        body = {'name': f'fips-tsig-{uuid.uuid4().hex[:6]}', 'provider_type': 'rfc2136',
                'credentials': {'server': '192.0.2.53', 'tsig_key_name': 'ucm.',
                                'tsig_key_secret': base64.b64encode(b'8 bytes!').decode(),
                                'tsig_algorithm': 'hmac-sha256'}}
        r = _post(auth_client, '/api/v2/dns-providers', body)
        assert r.status_code == 400 and r.get_json()['type'] == fips_mode.PROBLEM_TYPE, r.get_json()
        body['credentials']['tsig_key_secret'] = base64.b64encode(bytes(32)).decode()
        r = _post(auth_client, '/api/v2/dns-providers', body)
        assert r.status_code == 201, r.get_json()
        provider = r.get_json()['data']['id']
        r = auth_client.patch(f'/api/v2/dns-providers/{provider}', data=json.dumps({
            'credentials': {'tsig_key_secret': base64.b64encode(b'short').decode()}}),
            content_type='application/json')
        assert r.status_code == 400 and r.get_json()['type'] == fips_mode.PROBLEM_TYPE, r.get_json()
        auth_client.delete(f'/api/v2/dns-providers/{provider}')

    def test_tsig_secret(self, monkeypatch, fips_on):
        from services.acme.dns_providers.rfc2136 import Rfc2136DnsProvider
        short = {'tsig_key_secret': base64.b64encode(b'8 bytes!').decode()}
        with pytest.raises(FipsRestricted, match='TSIG key secret of 8 bytes'):
            Rfc2136DnsProvider.refuse_short_secret(short)
        Rfc2136DnsProvider.refuse_short_secret({'tsig_key_secret': base64.b64encode(bytes(14)).decode()})
        monkeypatch.setattr(fips_mode, 'enabled', lambda: False)
        Rfc2136DnsProvider.refuse_short_secret(short)


# ----------------------------------------------------------- the preflight report

class TestPreflight:
    def test_certificate_key(self, monkeypatch, fips_on):
        from services.fips_preflight import certificate_key
        ed = _self_signed_ca(ed25519.Ed25519PrivateKey.generate(), 'pf ed')
        pq = _self_signed_ca(mldsa.MLDSA65PrivateKey.generate(), 'pf pq')
        _module(monkeypatch, ())
        assert certificate_key(ed) == ('Ed25519', False)
        assert certificate_key(pq) == ('ML-DSA-65', False)
        _module(monkeypatch, ALL)
        assert certificate_key(ed) == ('Ed25519', True)
        assert certificate_key(pq) == ('ML-DSA-65', True)

    def test_ca_detectors(self, monkeypatch, app, fips_on):
        from services import fips_preflight
        rows = []
        with app.app_context():
            for key, cn in ((ed448.Ed448PrivateKey.generate(), 'pf Ed448 CA'),
                            (mldsa.MLDSA87PrivateKey.generate(), 'pf ML-DSA CA')):
                cert = _self_signed_ca(key, f'{cn} {uuid.uuid4().hex[:6]}')
                row = CA(refid=str(uuid.uuid4()), descr=cert.subject.rfc4514_string(), serial=0,
                         crt=base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode())
                db.session.add(row)
                rows.append(row)
            db.session.commit()
            try:
                ids = [f'#{r.id}' for r in rows]
                _module(monkeypatch, ())
                assert any(ids[0] in f for f in fips_preflight._ca_eddsa())
                assert any(ids[1] in f for f in fips_preflight._ca_unapproved_algorithm())
                _module(monkeypatch, ALL)
                assert not any(ids[0] in f for f in fips_preflight._ca_eddsa())
                assert not any(ids[1] in f for f in fips_preflight._ca_unapproved_algorithm())
            finally:
                for row in rows:
                    db.session.delete(row)
                db.session.commit()

    @pytest.mark.parametrize('approves', [(), ALL])
    def test_hsm_ml_dsa_ca_blocks_whatever_the_module(self, monkeypatch, app, fips_on, approves):
        # The HSM signs, not the module: an HSM ML-DSA CA is a blocker even when the module approves
        from models.hsm import HsmKey, HsmProvider
        from services import fips_preflight
        _module(monkeypatch, approves)
        suffix = uuid.uuid4().hex[:6]
        with app.app_context():
            soft = _self_signed_ca(mldsa.MLDSA65PrivateKey.generate(), f'pf soft PQ {suffix}')
            hard = _self_signed_ca(mldsa.MLDSA65PrivateKey.generate(), f'pf hsm PQ {suffix}')
            provider = HsmProvider(name=f'bao-{suffix}', type='openbao', config='{}')
            db.session.add(provider)
            db.session.commit()
            key = HsmKey(provider_id=provider.id, key_identifier=f'pq-{suffix}', label=f'pq-{suffix}',
                         algorithm='ML-DSA-65', key_type='asymmetric', purpose='signing',
                         public_key_pem=hard.public_key().public_bytes(
                             serialization.Encoding.PEM,
                             serialization.PublicFormat.SubjectPublicKeyInfo).decode())
            db.session.add(key)
            db.session.commit()
            rows = []
            for cert, hsm_key_id in ((soft, None), (hard, key.id)):
                row = CA(refid=str(uuid.uuid4()), descr=cert.subject.rfc4514_string(), serial=0,
                         hsm_key_id=hsm_key_id,
                         crt=base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode())
                db.session.add(row)
                rows.append(row)
            db.session.commit()
            try:
                soft_id, hard_id = (f'(#{r.id})' for r in rows)
                found = fips_preflight._ca_unapproved_algorithm()
                assert any(hard_id in f for f in found), found
                assert any(soft_id in f for f in found) is (not approves), found
                assert not any(hard_id in f for f in fips_preflight._ca_weak())
            finally:
                for row in rows:
                    db.session.delete(row)
                db.session.commit()
                db.session.delete(key)
                db.session.delete(provider)
                db.session.commit()

    @pytest.mark.parametrize('approves', [(), ALL])
    def test_hsm_classical_cas_are_not_listed(self, monkeypatch, app, hsm_signing_key, fips_on, approves):
        # The HSM exception covers only what the module alone approves: RSA and NIST curves pass
        from cryptography.hazmat.primitives import hashes
        from services import fips_preflight
        _module(monkeypatch, approves)
        rows = []
        for algorithm, private in (('RSA-2048', rsa.generate_private_key(65537, 2048)),
                                   ('EC-P256', ec.generate_private_key(ec.SECP256R1()))):
            key = hsm_signing_key(algorithm, _pem(private.public_key()))
            cert = _self_signed_ca(private, f'pf hsm {algorithm} {uuid.uuid4().hex[:6]}', hashes.SHA256())
            row = CA(refid=str(uuid.uuid4()), descr=cert.subject.rfc4514_string(), serial=0,
                     hsm_key_id=key.id,
                     crt=base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode())
            db.session.add(row)
            rows.append(row)
        db.session.commit()
        try:
            ids = [f'(#{r.id})' for r in rows]
            listed = (fips_preflight._ca_weak() + fips_preflight._ca_eddsa()
                      + fips_preflight._ca_unapproved_algorithm())
            assert not [f for f in listed if any(i in f for i in ids)], listed
        finally:
            for row in rows:
                db.session.delete(row)
            db.session.commit()

    def test_hsm_brainpool_keys_are_listed(self, hsm_signing_key, fips_on):
        from services import fips_preflight
        key = hsm_signing_key('EC-BP256', _pem(ec.generate_private_key(ec.BrainpoolP256R1()).public_key()))
        found = fips_preflight._hsm_keys()
        assert f'{key.label} (#{key.id}): EC-BP256' in found, found

    @pytest.mark.parametrize('approves', [(), ALL])
    def test_hsm_keys_listed_are_those_sign_refuses(self, monkeypatch, hsm_signing_key, fips_on, approves):
        from services import fips_preflight
        from services.hsm import HsmService
        _module(monkeypatch, approves)
        keys = [hsm_signing_key(label, _pem(public) if public is not None else None) for label, public in (
            ('RSA-1024', _rsa_public(1024)), ('RSA-2048', _rsa_public(2048)),
            ('EC-P256', _ec_public(ec.SECP256R1())), ('UNKNOWN', _ec_public(ec.SECP256K1())),
            ('EC-BP256', _ec_public(ec.BrainpoolP256R1())),
            ('ML-DSA-65', mldsa.MLDSA65PrivateKey.generate().public_key()),
            ('Ed25519', ed25519.Ed25519PrivateKey.generate().public_key()), ('UNKNOWN', None),
        )]
        found = fips_preflight._hsm_keys()
        for key in keys:
            try:
                HsmService.sign(key.id, b'tbs')
                refused = False
            except FipsRestricted:
                refused = True
            listed = any(f.startswith(f'{key.label} (#{key.id})') for f in found)
            assert listed == refused, (key.algorithm, refused, found)
        assert [k.algorithm for k in keys if any(f.startswith(f'{k.label} (#') for f in found)] == [
            'RSA-1024', 'UNKNOWN', 'EC-BP256', 'ML-DSA-65', 'Ed25519', 'UNKNOWN']

    def test_ssh_and_hsm_detectors(self, monkeypatch, fips_on):
        from services import fips_preflight
        _module(monkeypatch, ())
        assert fips_preflight._ssh_eddsa('ed25519', None) == 'Ed25519'
        assert fips_preflight._ssh_cert_key_refused('ed25519')
        _module(monkeypatch, ALL)
        assert fips_preflight._ssh_eddsa('ed25519', None) is None
        assert not fips_preflight._ssh_cert_key_refused('ed25519')
        assert not fips_preflight._ssh_cert_key_refused('ecdsa-p256')

    def test_short_hmac_secrets_are_listed(self, app, auth_client, monkeypatch):
        from services import fips_preflight
        r = _post(auth_client, '/api/v2/webhooks', {
            'name': f'pf-hook-{uuid.uuid4().hex[:6]}', 'url': 'https://hooks.example.test/pf',
            'secret': 'six-b!'})
        hook = r.get_json()['data']['id']
        try:
            with app.app_context():
                assert any(f'#{hook}' in f for f in fips_preflight._short_hmac_secrets())
            assert fips_preflight._short_tsig_secret(base64.b64encode(b'8 bytes!').decode())
            assert not fips_preflight._short_tsig_secret(base64.b64encode(bytes(32)).decode())
        finally:
            auth_client.delete(f'/api/v2/webhooks/{hook}')

    def test_deploy_detectors_ignore_the_module(self, monkeypatch, app, approving):
        """Deploy keys and pinned host keys go through PyNaCl: listed whatever the module approves."""
        from models import DeployTarget
        from services import fips_preflight
        key = ed25519.Ed25519PrivateKey.generate()
        public = key.public_key().public_bytes(serialization.Encoding.OpenSSH,
                                               serialization.PublicFormat.OpenSSH).decode()
        with app.app_context():
            target = DeployTarget(name=f'pf-ed-{uuid.uuid4().hex[:6]}', host='h.example.test',
                                  username='u', private_key='unused', public_key=public,
                                  host_key=public)
            db.session.add(target)
            db.session.commit()
            try:
                assert any(f'#{target.id}' in f for f in fips_preflight._deploy_eddsa())
                assert any(f'#{target.id}' in f for f in fips_preflight._deploy_eddsa_host_key())
            finally:
                db.session.delete(target)
                db.session.commit()



class TestHsmCaBindingInFipsMode:
    """Binding an existing HSM key to a new CA applies the signing rule before anything is loaded."""

    @pytest.mark.parametrize('algorithm,public,name', [
        ('UNKNOWN', lambda: None, 'UNKNOWN'),
        ('RSA-1024', lambda: _pem(_rsa_public(1024)), 'RSA 1024'),
        ('UNKNOWN', lambda: _pem(_ec_public(ec.SECP256K1())), 'EC secp256k1'),
    ])
    def test_refused_at_creation_without_a_row(self, auth_client, hsm_signing_key, fips_on,
                                               algorithm, public, name):
        key = hsm_signing_key(algorithm, public())
        before = CA.query.count()
        r = _post(auth_client, '/api/v2/cas', {'type': 'root', 'commonName': f'bind {uuid.uuid4().hex[:6]}',
                                               'organization': 'T', 'hsm_key_id': key.id})
        _assert_fips_problem(r, name)
        assert r.get_json()['detail'] == f'{name} keys not available in FIPS mode'
        assert CA.query.count() == before
        assert CA.query.filter_by(hsm_key_id=key.id).first() is None

    def test_an_approved_key_is_bound(self, monkeypatch, auth_client, hsm_signing_key, fips_on):
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        from services.hsm import HsmService
        private = rsa.generate_private_key(65537, 2048)

        class _Signer(_SigningStub):
            def sign(self, key_identifier, data, algorithm=None, hash_algorithm=None, **kwargs):
                return private.sign(data, padding.PKCS1v15(), getattr(hashes, hash_algorithm.upper())())

        monkeypatch.setattr(HsmService, '_get_provider_instance', classmethod(lambda cls, p: _Signer()))
        key = hsm_signing_key('RSA-2048', _pem(private.public_key()))
        r = _post(auth_client, '/api/v2/cas', {'type': 'root', 'commonName': f'bind ok {uuid.uuid4().hex[:6]}',
                                               'organization': 'T', 'hsm_key_id': key.id})
        assert r.status_code == 201, r.get_json()
        row = CA.query.filter_by(hsm_key_id=key.id).one()
        db.session.delete(row)
        db.session.commit()


class TestHsmCaKeyLoadInFipsMode:
    """A CA key the module cannot load still gets the FIPS refusal, not a load error."""

    @staticmethod
    def _load(monkeypatch, error):
        from services.hsm import ca_key_loader

        def failing(key_id):
            raise error
        monkeypatch.setattr(ca_key_loader, 'load_hsm_private_key', failing)

    @staticmethod
    def _ca(key):
        import types
        return types.SimpleNamespace(id=1, hsm_key_id=key.id, revoked_in_chain=False, signature_scheme=None)

    def test_a_cached_public_key_is_judged_before_loading(self, monkeypatch, hsm_signing_key, fips_on):
        from services.hsm.ca_key_loader import get_ca_signing_key
        self._load(monkeypatch, RuntimeError('provider unreachable'))
        key = hsm_signing_key('UNKNOWN', _pem(_ec_public(ec.SECP256K1())))
        with pytest.raises(FipsRestricted, match='^EC secp256k1 keys not available in FIPS mode$'):
            get_ca_signing_key(self._ca(key))

    @pytest.mark.parametrize('algorithm,public', [
        ('EC-BP256', lambda: None), ('UNKNOWN', lambda: '-----BEGIN PUBLIC KEY-----\nnot read\n'),
    ])
    def test_a_load_error_gets_the_label_refusal(self, monkeypatch, hsm_signing_key, fips_on, algorithm, public):
        from services.hsm.ca_key_loader import get_ca_signing_key
        self._load(monkeypatch, ValueError('unsupported curve'))
        key = hsm_signing_key(algorithm, public())
        with pytest.raises(FipsRestricted, match='keys not available in FIPS mode$'):
            get_ca_signing_key(self._ca(key))

    def test_a_public_key_fetched_by_the_load_is_judged(self, monkeypatch, hsm_signing_key, fips_on):
        from services.hsm import HsmService
        from services.hsm.ca_key_loader import get_ca_signing_key
        pem = _pem(_rsa_public(1024))

        class _Publishing(_SigningStub):
            def get_public_key(self, key_identifier):
                return pem

        monkeypatch.setattr(HsmService, '_get_provider_instance', classmethod(lambda cls, p: _Publishing()))
        key = hsm_signing_key('RSA-2048', None)
        with pytest.raises(FipsRestricted, match='^RSA 1024 keys not available in FIPS mode$'):
            get_ca_signing_key(self._ca(key))

    def test_a_load_error_of_an_approved_key_stays(self, monkeypatch, hsm_signing_key, fips_on):
        from services.hsm.ca_key_loader import get_ca_signing_key
        self._load(monkeypatch, ValueError('unsupported curve'))
        key = hsm_signing_key('EC-P256', None)
        with pytest.raises(ValueError, match='^unsupported curve$'):
            get_ca_signing_key(self._ca(key))


class TestHsmSignApiInFipsMode:
    def test_refusal_is_the_fips_problem(self, monkeypatch, auth_client, hsm_signing_key, fips_on):
        key = hsm_signing_key('RSA-1024', _pem(_rsa_public(1024)))
        r = _post(auth_client, f'/api/v2/hsm/keys/{key.id}/sign',
                  {'data': base64.b64encode(b'tbs').decode()})
        _assert_fips_problem(r, 'RSA 1024')

    def test_refusal_is_audited(self, auth_client, hsm_signing_key, fips_on):
        from models.audit_log import AuditLog
        key = hsm_signing_key('RSA-1024', _pem(_rsa_public(1024)))
        r = _post(auth_client, f'/api/v2/hsm/keys/{key.id}/sign', {'data': base64.b64encode(b'tbs').decode()})
        assert r.status_code == 400
        entries = AuditLog.query.filter_by(action='hsm_key_used_sign', resource_name=key.label).all()
        assert [(e.success, e.details) for e in entries] == [
            (False, 'Sign refused: RSA 1024 keys not available in FIPS mode')]
        AuditLog.query.filter_by(action='hsm_key_used_sign', resource_name=key.label).delete()
        db.session.commit()

    @pytest.fixture
    def weak_hsm_ca(self, monkeypatch, app, hsm_signing_key):
        """A root CA whose HSM key is RSA 1024, bound before the switch; the stub signs for real."""
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding

        private = rsa.generate_private_key(65537, 1024)

        class _Signer(_SigningStub):
            def sign(self, key_identifier, data, algorithm=None, hash_algorithm=None, **kwargs):
                return private.sign(data, padding.PKCS1v15(), hashes.SHA256())

        from services.hsm import HsmService
        monkeypatch.setattr(HsmService, '_get_provider_instance', classmethod(lambda cls, p: _Signer()))
        key = hsm_signing_key('RSA-1024', _pem(private.public_key()))
        cert = _self_signed_ca(private, f'weak hsm {uuid.uuid4().hex[:6]}', hashes.SHA256())
        row = CA(refid=str(uuid.uuid4()), descr=cert.subject.rfc4514_string(), serial=0, hsm_key_id=key.id,
                 crt=base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode())
        db.session.add(row)
        db.session.commit()
        yield row.id
        from models import Certificate, CRLMetadata, OCSPResponse
        Certificate.query.filter_by(caref=row.refid).delete()
        CRLMetadata.query.filter_by(ca_id=row.id).delete()
        OCSPResponse.query.filter_by(ca_id=row.id).delete()
        db.session.delete(row)
        db.session.commit()

    def test_issuance_and_crl_are_refused(self, monkeypatch, auth_client, weak_hsm_ca, fips_on):
        r = _post(auth_client, '/api/v2/certificates',
                  {'cn': 'weak.example.test', 'ca_id': weak_hsm_ca, 'validity_days': 7})
        _assert_fips_problem(r, 'RSA 1024')
        r = _post(auth_client, f'/api/v2/crl/{weak_hsm_ca}/regenerate', {})
        _assert_fips_problem(r, 'RSA 1024')
        monkeypatch.setattr(fips_mode, 'enabled', lambda: False)
        r = _post(auth_client, f'/api/v2/crl/{weak_hsm_ca}/regenerate', {})
        assert r.status_code == 200, r.get_json()

    def test_ocsp_answers_unauthorized_without_error(self, monkeypatch, caplog, weak_hsm_ca, fips_on):
        # Refused when the key is loaded, as a software key is: UNAUTHORIZED and a warning
        import logging
        from services.ocsp_service import OCSPService
        ca = db.session.get(CA, weak_hsm_ca)
        with caplog.at_level(logging.WARNING):
            _, status = OCSPService().generate_response(ca, 12345)
        assert status == 'unauthorized'
        assert 'RSA 1024 keys not available in FIPS mode' in caplog.text
        assert not [r for r in caplog.records if r.levelno >= logging.ERROR
                    and r.name == 'services.ocsp_service'], caplog.text

    def test_scheduled_crl_logs_one_line(self, caplog, weak_hsm_ca, fips_on):
        import logging
        from services.crl_scheduler_task import CRLSchedulerTask
        with caplog.at_level(logging.WARNING):
            assert CRLSchedulerTask.regenerate_crl(weak_hsm_ca) is False
        ours = [r for r in caplog.records if r.name.startswith(('services.crl', 'services.hsm'))]
        assert [r.getMessage() for r in ours] == [
            f'CRL of CA {weak_hsm_ca} not signed: RSA 1024 keys not available in FIPS mode'], caplog.text
        assert all(r.exc_info is None and r.levelno == logging.WARNING for r in ours)

    def test_scheduled_delta_crl_logs_one_line(self, monkeypatch, caplog, weak_hsm_ca, fips_on):
        import logging
        from services.crl_scheduler_task import CRLSchedulerTask
        ca = db.session.get(CA, weak_hsm_ca)
        ca.cdp_enabled, ca.delta_crl_enabled = True, True
        db.session.commit()
        monkeypatch.setattr(CRLSchedulerTask, 'should_regenerate_crl', staticmethod(lambda ca_id: (False, None)))
        monkeypatch.setattr(CRLSchedulerTask, '_delta_interval_if_due',
                            staticmethod(lambda ca_id: 4 if ca_id == weak_hsm_ca else None))
        with caplog.at_level(logging.WARNING):
            CRLSchedulerTask.execute()
        ours = [r for r in caplog.records if r.name.startswith(('services.crl', 'services.hsm'))]
        assert [r.getMessage() for r in ours] == [
            f'Delta CRL of CA {weak_hsm_ca} not signed: RSA 1024 keys not available in FIPS mode'], caplog.text
        assert all(r.exc_info is None and r.levelno == logging.WARNING for r in ours)

