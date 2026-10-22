"""Brainpool keys on HSMs: PKCS#11 only, refused clearly on the other providers.

Real checks run against SoftHSM (generation by curve OID, curve read back,
raw r||s signatures turned into DER); a CA on such a key signs a certificate
and a CRL that openssl verifies.
"""
import base64
import os
import shutil
import subprocess
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from models.hsm import HsmKey
from services.hsm.base_provider import HsmOperationError
from services.hsm.ecdsa_signature import coordinate_bytes, ecdsa_to_der

SOFTHSM_LIB = '/usr/lib/softhsm/libsofthsm2.so'
HAS_SOFTHSM = bool(shutil.which('softhsm2-util')) and os.path.exists(SOFTHSM_LIB)
needs_softhsm = pytest.mark.skipif(not HAS_SOFTHSM, reason='SoftHSM not installed')

BRAINPOOL = {
    'EC-BP256': (ec.BrainpoolP256R1, 32, hashes.SHA256, 'sha256'),
    'EC-BP384': (ec.BrainpoolP384R1, 48, hashes.SHA384, 'sha384'),
    'EC-BP512': (ec.BrainpoolP512R1, 64, hashes.SHA512, 'sha512'),
}


def test_the_model_accepts_the_brainpool_labels():
    for label in BRAINPOOL:
        assert label in HsmKey.VALID_ALGORITHMS


@pytest.mark.parametrize('label', sorted(BRAINPOOL))
def test_coordinate_size_without_a_public_key(label):
    assert coordinate_bytes(label) == BRAINPOOL[label][1]


@pytest.mark.parametrize('label', sorted(BRAINPOOL))
def test_raw_signature_becomes_der_at_each_size(label):
    curve, size, digest, _name = BRAINPOOL[label]
    key = ec.generate_private_key(curve())
    der = key.sign(b'tbs', ec.ECDSA(digest()))
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    r, s = decode_dss_signature(der)
    raw = r.to_bytes(size, 'big') + s.to_bytes(size, 'big')
    assert ecdsa_to_der(raw, coordinate_bytes(label)) == der


def _provider_for(type_name):
    import services.hsm.azure_provider as azure
    import services.hsm.gcp_provider as gcp
    import services.hsm.openbao_provider as openbao
    cls = {'azure-keyvault': azure.AzureKeyVaultProvider, 'google-kms': gcp.GcpKmsProvider,
           'openbao': openbao.OpenBaoProvider}[type_name]
    return object.__new__(cls)


@pytest.mark.parametrize('type_name', ['azure-keyvault', 'google-kms', 'openbao'])
@pytest.mark.parametrize('label', sorted(BRAINPOOL))
def test_other_providers_refuse_brainpool_and_say_why(type_name, label):
    try:
        provider = _provider_for(type_name)
    except (ImportError, AttributeError):
        pytest.skip('provider SDK not installed')
    with pytest.raises(HsmOperationError, match='only PKCS#11'):
        provider.generate_key('bp', label)


def test_the_refusal_names_the_provider_and_curve():
    from services.hsm import HsmService
    msg = HsmService.brainpool_refusal('azure-keyvault', 'EC-BP384')
    assert 'EC-BP384' in msg and 'azure-keyvault' in msg and 'only PKCS#11' in msg
    assert HsmService.brainpool_refusal('pkcs11', 'EC-BP384') is None
    assert HsmService.brainpool_refusal('azure-keyvault', 'EC-P384') is None
    assert HsmService.brainpool_refusal('openbao', 'RSA-2048') is None


def _mk_provider_row(app, type_name, name):
    with app.app_context():
        from models import db
        from models.hsm import HsmProvider
        row = HsmProvider(name=name, type=type_name, config='{}')
        db.session.add(row)
        db.session.commit()
        return row.id


def _drop_provider(app, provider_id):
    with app.app_context():
        from models import db
        from models.hsm import HsmKey as K, HsmProvider
        db.session.query(K).filter_by(provider_id=provider_id).delete()
        db.session.query(HsmProvider).filter_by(id=provider_id).delete()
        db.session.commit()


@pytest.mark.parametrize('type_name', ['azure-keyvault', 'google-kms', 'openbao'])
def test_key_generation_api_refuses_brainpool_on_other_providers(app, auth_client, type_name):
    pid = _mk_provider_row(app, type_name, f'bp-refuse-{type_name}')
    try:
        resp = auth_client.post(f'/api/v2/hsm/providers/{pid}/keys', json={
            'label': 'bp', 'algorithm': 'EC-BP256', 'purpose': 'signing'})
        assert resp.status_code == 400, resp.get_json()
        assert 'only PKCS#11' in resp.get_data(as_text=True)
    finally:
        _drop_provider(app, pid)


@pytest.mark.parametrize('type_name', ['azure-keyvault', 'google-kms', 'openbao'])
def test_ca_creation_refuses_a_new_brainpool_key_on_other_providers(app, auth_client, type_name):
    pid = _mk_provider_row(app, type_name, f'bp-ca-new-{type_name}')
    try:
        resp = auth_client.post('/api/v2/cas', json={
            'type': 'root', 'commonName': 'bp-refused.test', 'organization': 'T',
            'hsm_provider_id': pid, 'hsm_key_label': 'bp', 'hsm_key_algorithm': 'EC-BP384'})
        assert resp.status_code == 400, resp.get_json()
        assert 'only PKCS#11' in resp.get_data(as_text=True)
    finally:
        _drop_provider(app, pid)


def test_ca_creation_refuses_an_existing_brainpool_key_on_another_provider(app, auth_client):
    pid = _mk_provider_row(app, 'openbao', 'bp-ca-existing')
    with app.app_context():
        from models import db
        key = HsmKey(provider_id=pid, key_identifier='bp-x', label='bp-x', algorithm='EC-BP256',
                     key_type='asymmetric', purpose='signing')
        db.session.add(key)
        db.session.commit()
        key_id = key.id
    try:
        resp = auth_client.post('/api/v2/cas', json={
            'type': 'external', 'commonName': 'bp-existing.test', 'organization': 'T',
            'hsm_key_id': key_id})
        assert resp.status_code == 400, resp.get_json()
        assert 'only PKCS#11' in resp.get_data(as_text=True)
    finally:
        _drop_provider(app, pid)


def test_fips_mode_refuses_brainpool_key_generation(app, monkeypatch):
    import fips_mode
    from services.hsm import HsmService
    pid = _mk_provider_row(app, 'pkcs11', 'bp-fips')
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
    try:
        with app.app_context():
            with pytest.raises(fips_mode.FipsRestricted, match='FIPS'):
                HsmService.generate_key(pid, 'bp', 'EC-BP256')
    finally:
        _drop_provider(app, pid)


# ---------------------------------------------------------------------------
# SoftHSM
# ---------------------------------------------------------------------------

def _release(pkcs11):
    lib = getattr(pkcs11, '_loaded', {}).pop(SOFTHSM_LIB, None)
    if lib is not None:
        lib.finalize()


@pytest.fixture
def softhsm(tmp_path, monkeypatch):
    if not HAS_SOFTHSM:
        pytest.skip('SoftHSM not installed')
    from services.hsm.pkcs11_provider import PKCS11_AVAILABLE, Pkcs11Provider
    if not PKCS11_AVAILABLE:
        pytest.skip('python-pkcs11 not installed')
    import pkcs11
    conf = tmp_path / 'softhsm2.conf'
    (tmp_path / 'tokens').mkdir()
    conf.write_text(f"directories.tokendir = {tmp_path / 'tokens'}\nobjectstore.backend = file\nlog.level = ERROR\n")
    monkeypatch.setenv('SOFTHSM2_CONF', str(conf))
    subprocess.run(['softhsm2-util', '--init-token', '--free', '--label', 'ucmbp',
                    '--so-pin', '1234', '--pin', '1234'], check=True, capture_output=True)
    _release(pkcs11)
    try:
        yield lambda: Pkcs11Provider({'module_path': SOFTHSM_LIB, 'token_label': 'ucmbp', 'user_pin': '1234'})
    finally:
        _release(pkcs11)


@needs_softhsm
@pytest.mark.parametrize('label', sorted(BRAINPOOL))
def test_softhsm_generates_reads_and_signs_brainpool(softhsm, label):
    curve, size, digest, name = BRAINPOOL[label]
    provider = softhsm()
    with provider:
        info = provider.generate_key('bp-' + name, label)
        assert info.algorithm == label
        pem = provider.get_public_key(info.key_identifier)
        public_key = serialization.load_pem_public_key(pem.encode())
        assert isinstance(public_key.curve, curve)
        # The curve of an existing key is read back, not 'UNKNOWN'
        listed = {k.key_identifier: k for k in provider.list_keys()}
        assert listed[info.key_identifier].algorithm == label
        for hash_name, hash_cls in (('sha256', hashes.SHA256), ('sha384', hashes.SHA384),
                                    ('sha512', hashes.SHA512)):
            raw = provider.sign(info.key_identifier, b'tbs', label, hash_algorithm=hash_name)
            assert len(raw) == 2 * size
            public_key.verify(ecdsa_to_der(raw, size), b'tbs', ec.ECDSA(hash_cls()))


@needs_softhsm
def test_softhsm_still_generates_nist_curves(softhsm):
    provider = softhsm()
    with provider:
        info = provider.generate_key('p256', 'EC-P256')
        assert info.algorithm == 'EC-P256'
        assert provider.list_keys()[0].algorithm == 'EC-P256'


def _openssl(*args):
    return subprocess.run(['openssl', *args], capture_output=True, text=True)


@needs_softhsm
@pytest.mark.parametrize('label', ['EC-BP256', 'EC-BP384', 'EC-BP512'])
def test_ca_on_a_softhsm_brainpool_key_signs_certificate_and_crl(app, auth_client, softhsm, tmp_path, label):
    if not shutil.which('openssl'):
        pytest.skip('openssl not installed')
    _curve, _size, digest, hash_name = BRAINPOOL[label]
    real = softhsm()
    pid = _mk_provider_row(app, 'pkcs11', f'bp-softhsm-{label}')
    ca_id = None
    try:
        with patch('services.hsm.HsmService._get_provider_instance', return_value=real):
            resp = auth_client.post('/api/v2/cas', json={
                'type': 'root', 'commonName': f'bp-root-{label}.test', 'organization': 'T',
                'validityYears': 5, 'hsm_provider_id': pid, 'hsm_key_label': f'bp-{label}',
                'hsm_key_algorithm': label, 'digest': 'auto'})
            assert resp.status_code in (200, 201), resp.get_json()
            ca_id = resp.get_json()['data']['id']
            with app.app_context():
                from models import CA, db
                from services.hsm.hsm_private_key import load_hsm_private_key
                ca = db.session.get(CA, ca_id)
                assert ca.hsm_key.algorithm == label
                ca_cert = x509.load_pem_x509_certificate(base64.b64decode(ca.crt))
                assert ca_cert.signature_hash_algorithm.name == hash_name
                signer = load_hsm_private_key(ca.hsm_key_id)

                leaf_key = ec.generate_private_key(ec.SECP256R1())
                now = datetime.now(timezone.utc)
                leaf = (x509.CertificateBuilder()
                        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'leaf.test')]))
                        .issuer_name(ca_cert.subject).public_key(leaf_key.public_key())
                        .serial_number(x509.random_serial_number())
                        .not_valid_before(now).not_valid_after(now + timedelta(days=30))
                        .sign(signer, digest()))
                crl = (x509.CertificateRevocationListBuilder()
                       .issuer_name(ca_cert.subject).last_update(now)
                       .next_update(now + timedelta(days=7)).sign(signer, digest()))
        (tmp_path / 'ca.pem').write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
        (tmp_path / 'leaf.pem').write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
        (tmp_path / 'crl.pem').write_bytes(crl.public_bytes(serialization.Encoding.PEM))
        ca_check = _openssl('verify', '-CAfile', str(tmp_path / 'ca.pem'), str(tmp_path / 'ca.pem'))
        assert ca_check.returncode == 0, ca_check.stderr + ca_check.stdout
        leaf_check = _openssl('verify', '-CAfile', str(tmp_path / 'ca.pem'), str(tmp_path / 'leaf.pem'))
        assert leaf_check.returncode == 0, leaf_check.stderr + leaf_check.stdout
        crl_check = _openssl('verify', '-crl_check', '-CAfile', str(tmp_path / 'ca.pem'),
                             '-CRLfile', str(tmp_path / 'crl.pem'), str(tmp_path / 'leaf.pem'))
        assert crl_check.returncode == 0, crl_check.stderr + crl_check.stdout
    finally:
        if ca_id:
            with patch('services.hsm.HsmService._get_provider_instance', return_value=real):
                auth_client.delete(f'/api/v2/cas/{ca_id}')
        _drop_provider(app, pid)


def test_the_service_refuses_before_reaching_a_provider_that_would_accept(app):
    from services.hsm import HsmService

    class _Accepting:
        def __enter__(self):
            raise AssertionError('the provider was reached')

        def __exit__(self, *exc):
            return False

    pid = _mk_provider_row(app, 'azure-keyvault', 'bp-service-guard')
    try:
        with app.app_context(), patch('services.hsm.HsmService._get_provider_instance',
                                      return_value=_Accepting()):
            with pytest.raises(HsmOperationError, match='only PKCS#11'):
                HsmService.generate_key(pid, 'bp', 'EC-BP256')
    finally:
        _drop_provider(app, pid)
