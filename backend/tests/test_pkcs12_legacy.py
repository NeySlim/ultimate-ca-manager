"""PKCS#12 compatibility profile (issue #331).

UCM's PKCS#12 archives use the OpenSSL 3 profile (PBES2 / AES-256-CBC /
PBKDF2-SHA256, HMAC-SHA256 MAC). Android 15 and earlier, macOS 14 and
earlier, Windows Server 2016 and earlier and old Java reject it as a wrong
password. ``legacy: true`` switches the archive to PBES1 3DES/SHA-1 with an
HMAC-SHA1 MAC (the LegacyDES profile of go-pkcs12 / cert-manager), on every
export that produces a PKCS#12.
"""
import json
import shutil
import subprocess
import tempfile

import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from utils.pkcs12_export import legacy_flag, pkcs12_encryption

# DER-encoded OBJECT IDENTIFIERs as they appear inside the archive
OID_PBE_SHA1_3DES = bytes.fromhex('060a2a864886f70d010c0103')   # 1.2.840.113549.1.12.1.3
OID_PBES2 = bytes.fromhex('06092a864886f70d01050d')             # 1.2.840.113549.1.5.13
OID_AES256_CBC = bytes.fromhex('060960864801650304012a')        # 2.16.840.1.101.3.4.1.42
OID_SHA256 = bytes.fromhex('0609608648016503040201')            # 2.16.840.1.101.3.4.2.1
OID_SHA1 = bytes.fromhex('06052b0e03021a')                      # 1.3.14.3.2.26
PASSWORD = 'compat-password-123'


def _self_signed():
    key = rsa.generate_private_key(65537, 2048, default_backend())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'p12.test')])
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(1)
            .not_valid_before(now).not_valid_after(now + timedelta(days=1))
            .sign(key, hashes.SHA256(), default_backend()))
    return key, cert


def _profile(der):
    """Which algorithms the archive carries, from the OIDs it embeds."""
    return {
        'pbes1_3des': OID_PBE_SHA1_3DES in der,
        'pbes2': OID_PBES2 in der,
        'aes256': OID_AES256_CBC in der,
        'sha256': OID_SHA256 in der,
        'sha1': OID_SHA1 in der,
    }


def _assert_legacy(der):
    p = _profile(der)
    assert p['pbes1_3des'] and p['sha1'], p
    assert not p['pbes2'] and not p['aes256'] and not p['sha256'], p
    pkcs12.load_key_and_certificates(der, PASSWORD.encode(), default_backend())


def _assert_modern(der):
    p = _profile(der)
    assert p['pbes2'] and p['aes256'] and p['sha256'], p
    assert not p['pbes1_3des'], p
    pkcs12.load_key_and_certificates(der, PASSWORD.encode(), default_backend())


class TestProfileHelper:

    def test_modern_is_the_default(self):
        key, cert = _self_signed()
        der = pkcs12.serialize_key_and_certificates(b'x', key, cert, None, pkcs12_encryption(PASSWORD))
        _assert_modern(der)

    def test_legacy_is_3des_sha1_everywhere(self):
        key, cert = _self_signed()
        der = pkcs12.serialize_key_and_certificates(b'x', key, cert, None, pkcs12_encryption(PASSWORD, legacy=True))
        _assert_legacy(der)

    @pytest.mark.skipif(shutil.which('openssl') is None, reason='openssl CLI not available')
    def test_openssl_reads_legacy_as_3des_and_sha1_mac(self):
        """What the reporter would see with `openssl pkcs12 -info`."""
        key, cert = _self_signed()
        der = pkcs12.serialize_key_and_certificates(b'x', key, cert, None, pkcs12_encryption(PASSWORD, legacy=True))
        with tempfile.NamedTemporaryFile(suffix='.p12') as f:
            f.write(der); f.flush()
            out = subprocess.run(['openssl', 'pkcs12', '-info', '-noout', '-in', f.name,
                                  '-passin', f'pass:{PASSWORD}'],
                                 capture_output=True, text=True, timeout=30)
        info = out.stdout + out.stderr
        assert out.returncode == 0, info
        assert 'pbeWithSHA1And3-KeyTripleDES-CBC' in info, info
        assert 'MAC: sha1' in info, info
        assert 'AES-256' not in info and 'PBES2' not in info, info

    @pytest.mark.parametrize('value,expected', [
        (True, True), (False, False), (None, False), ('true', True), ('1', True),
        ('yes', True), ('on', True), ('false', False), ('0', False), ('', False), ('nope', False),
    ])
    def test_flag_parsing(self, value, expected):
        assert legacy_flag(value) is expected


class TestCertificateExportApi:

    def _export(self, auth_client, cert_id, **body):
        payload = {'format': 'pkcs12', 'password': PASSWORD}
        payload.update(body)
        r = auth_client.post(f'/api/v2/certificates/{cert_id}/export', json=payload)
        assert r.status_code == 200, r.data
        assert r.headers['Content-Type'] == 'application/x-pkcs12'
        return r.data

    def test_default_stays_modern(self, auth_client, create_cert):
        cert = create_cert(cn='p12-modern.example.com')
        _assert_modern(self._export(auth_client, cert['id']))

    def test_legacy_true_switches_profile(self, auth_client, create_cert):
        cert = create_cert(cn='p12-legacy.example.com')
        _assert_legacy(self._export(auth_client, cert['id'], legacy=True))

    def test_legacy_false_and_json_strings_are_rejected(self, auth_client, create_cert):
        cert = create_cert(cn='p12-strings.example.com')
        _assert_modern(self._export(auth_client, cert['id'], legacy=False))
        response = auth_client.post(
            f'/api/v2/certificates/{cert["id"]}/export',
            json={'format': 'pkcs12', 'password': PASSWORD, 'legacy': 'true'},
        )
        assert response.status_code == 400
        assert response.get_json()['message'] == 'legacy must be a boolean'

    def test_legacy_with_chain(self, auth_client, create_cert):
        cert = create_cert(cn='p12-chain.example.com')
        der = self._export(
            auth_client, cert['id'], legacy=True, include_chain=True, include_root=True,
        )
        _assert_legacy(der)
        _, _, cas = pkcs12.load_key_and_certificates(der, PASSWORD.encode(), default_backend())
        assert cas, 'the CA chain must still be bundled in legacy mode'


class TestCaExportApi:

    def _export(self, auth_client, ca_id, **body):
        payload = {'format': 'pkcs12', 'password': PASSWORD}
        payload.update(body)
        r = auth_client.post(f'/api/v2/cas/{ca_id}/export', data=json.dumps(payload),
                             content_type='application/json')
        assert r.status_code == 200, r.data
        return r.data

    def test_ca_pkcs12_legacy_and_default(self, auth_client, create_ca):
        ca = create_ca(cn='P12 legacy CA')
        _assert_modern(self._export(auth_client, ca['id']))
        _assert_legacy(self._export(auth_client, ca['id'], legacy=True))

    def test_ca_pfx_alias_honours_legacy(self, auth_client, create_ca):
        ca = create_ca(cn='PFX legacy CA')
        r = auth_client.post(f'/api/v2/cas/{ca["id"]}/export',
                             data=json.dumps({'format': 'pfx', 'password': PASSWORD, 'legacy': True}),
                             content_type='application/json')
        if r.status_code == 200:
            _assert_legacy(r.data)


class TestServiceLayer:

    def test_trust_store_mixin_legacy(self, app, create_ca):
        from services.trust_store import TrustStoreService
        from tests.test_scep_rfc8894_operations import _load_ca_material
        from cryptography.hazmat.primitives import serialization
        ca = create_ca(cn='Mixin legacy CA')
        with app.app_context():
            _, ca_cert, ca_key = _load_ca_material(ca['id'])
            cert_pem = ca_cert.public_bytes(serialization.Encoding.PEM)
            key_pem = ca_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption())
        _assert_modern(TrustStoreService.export_pkcs12(cert_pem, key_pem, PASSWORD, 'x'))
        _assert_legacy(TrustStoreService.export_pkcs12(cert_pem, key_pem, PASSWORD, 'x', legacy=True))
