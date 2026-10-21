"""HSM-resident CA keys sign RSA-PSS on the providers that can.

PKCS#11 (checked against SoftHSM) and OpenBao sign PSS with a salt as long as
the digest; Azure and Google KMS are refused up front. Whatever the provider
returns is verified before it reaches a certificate.
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
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID, SignatureAlgorithmOID

from services.hsm.ca_key_loader import bind_signature_scheme
from services.hsm.hsm_private_key import HsmRSAPrivateKey
from utils.signing_hash import rsa_padding_for

SOFTHSM_LIB = '/usr/lib/softhsm/libsofthsm2.so'
HAS_SOFTHSM = bool(shutil.which('softhsm2-util')) and os.path.exists(SOFTHSM_LIB)


def _self_signed(key, public_key):
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'HSM PSS')])
    now = datetime.now(timezone.utc)
    builder = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(public_key)
               .serial_number(1).not_valid_before(now).not_valid_after(now + timedelta(days=1))
               .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True))
    return builder.sign(key, hashes.SHA256(), rsa_padding=rsa_padding_for(key, hashes.SHA256()))


class _SoftwareProvider:
    """Signs with a software key as a provider would; *salt* overrides the PSS salt."""

    SIGNS_PSS = True

    def __init__(self, key, salt=None):
        self.key, self.salt, self.calls = key, salt, []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def sign(self, key_identifier, data, algorithm=None, hash_algorithm=None, padding=None):
        self.calls.append(padding)
        digest = {'sha256': hashes.SHA256(), 'sha384': hashes.SHA384()}[hash_algorithm]
        from cryptography.hazmat.primitives.asymmetric import padding as pad
        if padding == 'pss':
            return self.key.sign(data, pad.PSS(mgf=pad.MGF1(digest),
                                               salt_length=self.salt or digest.digest_size), digest)
        return self.key.sign(data, pad.PKCS1v15(), digest)


@contextmanager
def _hsm_rsa_key(app, provider_type='pkcs11', provider=None):
    key = rsa.generate_private_key(65537, 2048)
    with app.app_context():
        from models import db
        from models.hsm import HsmKey, HsmProvider
        row = HsmProvider(name=f'PSS {provider_type} {id(key)}', type=provider_type, config='{}')
        db.session.add(row)
        db.session.commit()
        hsm_key = HsmKey(provider_id=row.id, key_identifier=f'pss-{id(key)}', label=f'pss-{id(key)}',
                         algorithm='RSA-2048', key_type='asymmetric', purpose='signing',
                         public_key_pem=key.public_key().public_bytes(
                             serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode())
        db.session.add(hsm_key)
        db.session.commit()
        ids = hsm_key.id, row.id
    fake = provider or _SoftwareProvider(key)
    try:
        with patch('services.hsm.HsmService._get_provider_instance', return_value=fake), app.app_context():
            yield ids[0], key, fake
    finally:
        with app.app_context():
            from models import db
            from models.hsm import HsmKey, HsmProvider
            db.session.query(HsmKey).filter_by(id=ids[0]).delete()
            db.session.query(HsmProvider).filter_by(id=ids[1]).delete()
            db.session.commit()


def test_a_bound_hsm_key_signs_a_pss_certificate(app):
    with _hsm_rsa_key(app) as (key_id, key, fake):
        wrapper = bind_signature_scheme(HsmRSAPrivateKey(key_id, key.public_key(), 'RSA-2048'), 'pss')
        cert = _self_signed(wrapper, key.public_key())
    assert cert.signature_algorithm_oid == SignatureAlgorithmOID.RSASSA_PSS
    cert.verify_directly_issued_by(cert)
    assert fake.calls == ['pss']


def test_a_provider_salt_that_differs_is_caught(app):
    with _hsm_rsa_key(app, provider=None) as (key_id, key, fake):
        fake.salt = 222
        wrapper = bind_signature_scheme(HsmRSAPrivateKey(key_id, key.public_key(), 'RSA-2048'), 'pss')
        with pytest.raises(ValueError, match='does not verify'):
            _self_signed(wrapper, key.public_key())


def test_a_bound_hsm_key_refuses_v15(app):
    with _hsm_rsa_key(app) as (key_id, key, fake):
        wrapper = bind_signature_scheme(HsmRSAPrivateKey(key_id, key.public_key(), 'RSA-2048'), 'pss')
        with pytest.raises(ValueError, match='RSA-PSS'):
            wrapper.sign(b'tbs', padding.PKCS1v15(), hashes.SHA256())
    assert fake.calls == []


def test_a_provider_without_pss_is_refused(app):
    from services.hsm import HsmService
    from services.hsm.base_provider import HsmOperationError

    class _V15Only(_SoftwareProvider):
        SIGNS_PSS = False

    with _hsm_rsa_key(app, provider=_V15Only(rsa.generate_private_key(65537, 2048))) as (key_id, _k, fake):
        with pytest.raises(HsmOperationError, match='does not sign RSA-PSS'):
            HsmService.sign(key_id, b'tbs', 'RSA-2048', hash_algorithm='sha256', padding='pss')
    assert fake.calls == []


def test_openbao_asks_transit_for_a_digest_length_salt():
    from services.hsm.openbao_provider import OpenBaoProvider
    provider = OpenBaoProvider({'url': 'http://bao.invalid:8200', 'token': 't'})
    seen = {}

    def _api(method, path, **kwargs):
        seen.update(kwargs.get('json') or {})
        return {'data': {'signature': 'vault:v1:' + base64.b64encode(b'sig').decode()}}

    with patch.object(provider, '_api', _api):
        provider.sign('k', b'tbs', 'RSA-2048', hash_algorithm='sha384', padding='pss')
    assert seen['signature_algorithm'] == 'pss' and seen['salt_length'] == 'hash'
    assert seen['hash_algorithm'] == 'sha2-384'


def test_cloud_providers_are_refused_and_pkcs11_accepted():
    from services.ca.signature_scheme import pss_refusal
    from services.hsm import HsmService
    assert pss_refusal(True, 'azure-keyvault') and pss_refusal(True, 'google-kms')
    assert HsmService.signs_pss('openbao')
    if 'pkcs11' in HsmService.get_available_providers():
        assert pss_refusal(True, 'pkcs11') is None


@pytest.mark.skipif(not HAS_SOFTHSM, reason='SoftHSM not installed')
@pytest.mark.parametrize('digest', ['sha256', 'sha384', 'sha512'])
def test_softhsm_signs_pss(tmp_path, monkeypatch, digest):
    from services.hsm.pkcs11_provider import PKCS11_AVAILABLE, Pkcs11Provider
    if not PKCS11_AVAILABLE:
        pytest.skip('python-pkcs11 not installed')
    import pkcs11
    from tests.test_issue_366_hsm_ecdsa_der import _release_pkcs11_lib
    conf = tmp_path / 'softhsm2.conf'
    (tmp_path / 'tokens').mkdir()
    conf.write_text(f"directories.tokendir = {tmp_path / 'tokens'}\nobjectstore.backend = file\nlog.level = ERROR\n")
    monkeypatch.setenv('SOFTHSM2_CONF', str(conf))
    subprocess.run(['softhsm2-util', '--init-token', '--free', '--label', 'ucmpss',
                    '--so-pin', '1234', '--pin', '1234'], check=True, capture_output=True)
    _release_pkcs11_lib(pkcs11, SOFTHSM_LIB)
    provider = Pkcs11Provider({'module_path': SOFTHSM_LIB, 'token_label': 'ucmpss', 'user_pin': '1234'})
    try:
        with provider:
            info = provider.generate_key('pss', 'RSA-3072')
            public_key = serialization.load_pem_public_key(provider.get_public_key(info.key_identifier).encode())
            signature = provider.sign(info.key_identifier, b'tbs', 'RSA-3072', hash_algorithm=digest,
                                      padding='pss')
        algorithm = {'sha256': hashes.SHA256(), 'sha384': hashes.SHA384(), 'sha512': hashes.SHA512()}[digest]
        public_key.verify(signature, b'tbs', padding.PSS(mgf=padding.MGF1(algorithm),
                                                        salt_length=algorithm.digest_size), algorithm)
    finally:
        _release_pkcs11_lib(pkcs11, SOFTHSM_LIB)
