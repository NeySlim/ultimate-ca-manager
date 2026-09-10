"""The digest an HSM-resident key is signed with is the one the signature
names (self-review of #347): builders ask signing_hash_for(), wrappers pass
the digest hint to the provider, providers honour it or report the digest
they bind to the key."""
from unittest.mock import MagicMock, patch

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, padding, rsa

from utils.signing_hash import signing_hash_for


class TestSigningHashFor:
    def test_software_keys_and_ed_keys(self):
        assert signing_hash_for(ed25519.Ed25519PrivateKey.generate()) is None
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        assert isinstance(signing_hash_for(key), hashes.SHA256)
        assert isinstance(signing_hash_for(key, hashes.SHA384()), hashes.SHA384)

    def test_hsm_wrapper_reports_the_provider_bound_digest(self):
        from services.hsm.hsm_private_key import HsmRSAPrivateKey, HsmECPrivateKey
        rsa_pub = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key()
        ec_pub = ec.generate_private_key(ec.SECP384R1()).public_key()
        with patch('services.hsm.HsmService.signing_hash', return_value='sha512') as m:
            wrapped = HsmRSAPrivateKey(7, rsa_pub, key_algorithm='RSA-4096')
            assert isinstance(signing_hash_for(wrapped, hashes.SHA256()), hashes.SHA512)
            m.assert_called_with(7, 'RSA-4096', 'sha256')
        with patch('services.hsm.HsmService.signing_hash', return_value='sha384'):
            wrapped = HsmECPrivateKey(8, ec_pub, key_algorithm='EC-P384')
            assert isinstance(signing_hash_for(wrapped), hashes.SHA384)


class TestWrappersPassTheDigestHint:
    def test_rsa_and_ec_wrappers_forward_the_requested_digest(self):
        from services.hsm.hsm_private_key import HsmRSAPrivateKey, HsmECPrivateKey
        rsa_pub = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key()
        ec_pub = ec.generate_private_key(ec.SECP384R1()).public_key()
        with patch('services.hsm.HsmService.sign', return_value=b'sig') as m:
            HsmRSAPrivateKey(1, rsa_pub, key_algorithm='RSA-4096').sign(b'tbs', padding.PKCS1v15(), hashes.SHA384())
            m.assert_called_once_with(1, b'tbs', 'RSA-4096', hash_algorithm='sha384')
        with patch('services.hsm.HsmService.sign', return_value=b'sig') as m:
            HsmECPrivateKey(2, ec_pub, key_algorithm='EC-P384').sign(b'tbs', ec.ECDSA(hashes.SHA512()))
            m.assert_called_once_with(2, b'tbs', 'EC-P384', hash_algorithm='sha512')


class TestProvidersHonourTheDigest:
    def test_openbao_sends_the_declared_digest_not_the_key_size_default(self):
        from services.hsm.openbao_provider import OpenBaoProvider
        provider = OpenBaoProvider({'url': 'http://bao.test', 'token': 't', 'mount_path': 'transit'})
        calls = []
        def fake_api(method, path, *args, **kw):
            payload = kw.get('json') or kw.get('data') or (args[0] if args else None)
            calls.append((method, path, payload))
            return {'data': {'signature': 'vault:v1:AAAA'}}
        with patch.object(provider, '_api', side_effect=fake_api):
            provider.sign('k', b'data', 'RSA-4096', hash_algorithm='sha256')
        sign_calls = [c for c in calls if 'sign' in c[1]]
        assert sign_calls, calls
        assert sign_calls[0][2]['hash_algorithm'] == 'sha2-256'
        assert provider.hash_for_key('k', 'RSA-4096', 'sha256') == 'sha256'

    def test_azure_binds_ecdsa_to_the_curve_and_rsa_to_the_request(self):
        from services.hsm.azure_provider import AzureKeyVaultProvider as Provider
        p = object.__new__(Provider)
        assert p.hash_for_key('k', 'EC-P384', 'sha256') == 'sha384'
        assert p.hash_for_key('k', 'EC-P521', 'sha256') == 'sha512'
        assert p.hash_for_key('k', 'RSA-4096', 'sha256') == 'sha256'

    def test_gcp_reads_the_digest_off_the_key_version(self):
        from services.hsm.gcp_provider import GcpKmsProvider as Provider
        version = MagicMock(); version.algorithm = MagicMock(); version.algorithm.name = 'RSA_SIGN_PKCS1_3072_SHA256'
        assert Provider._digest_of_version(version) == 'sha256'
        version.algorithm.name = 'EC_SIGN_P384_SHA384'
        assert Provider._digest_of_version(version) == 'sha384'
        version.algorithm.name = 'RSA_SIGN_PKCS1_4096_SHA512'
        assert Provider._digest_of_version(version) == 'sha512'


class TestOcspNamesTheDigestUsed:
    def test_multi_response_algorithm_follows_the_bound_digest(self):
        from services.hsm.hsm_private_key import HsmRSAPrivateKey
        from services.ocsp_service import OCSPService
        real = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        wrapped = HsmRSAPrivateKey(5, real.public_key(), key_algorithm='RSA-4096')
        def fake_sign(key_id, data, algo=None, hash_algorithm=None):
            digest = {'sha384': hashes.SHA384, 'sha512': hashes.SHA512}.get(hash_algorithm, hashes.SHA256)()
            return real.sign(data, padding.PKCS1v15(), digest)
        with patch('services.hsm.HsmService.signing_hash', return_value='sha512'), \
             patch('services.hsm.HsmService.sign', side_effect=fake_sign):
            signature, algorithm = OCSPService._sign_response_data(wrapped, b'response-data')
        assert algorithm == 'sha512_rsa'
        real.public_key().verify(signature, b'response-data', padding.PKCS1v15(), hashes.SHA512())
