"""
Tests for HSM-backed private key wrappers (services.hsm.hsm_private_key).

These tests use the real `cryptography` library with locally generated keys
and only mock the HSM round-trip — `HsmService.sign` and
`HsmService.get_public_key`.  This way we exercise the full code path from
``CertificateBuilder.sign(wrapper, ...)`` down to the `.sign()` call on the
wrapper, and verify the resulting signature would be issued by the HSM.
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.backends import default_backend
from cryptography.x509.oid import NameOID
from datetime import datetime, timedelta, timezone


def _name(cn='Test'):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def _builder(public_key, cn='Test'):
    return (
        x509.CertificateBuilder()
        .subject_name(_name(cn))
        .issuer_name(_name(cn))
        .public_key(public_key)
        .serial_number(1)
        .not_valid_before(datetime.now(timezone.utc))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=1))
    )


# ---------------------------------------------------------------------------
# RSA wrapper
# ---------------------------------------------------------------------------

class TestHsmRSAPrivateKey:

    def test_isinstance_rsa_private_key(self):
        from services.hsm.hsm_private_key import HsmRSAPrivateKey
        real = rsa.generate_private_key(65537, 2048)
        w = HsmRSAPrivateKey(42, real.public_key(), 'RSA-2048')
        assert isinstance(w, rsa.RSAPrivateKey), \
            "Wrapper must be registered as a virtual subclass of RSAPrivateKey"

    def test_public_key_returns_real_pub(self):
        from services.hsm.hsm_private_key import HsmRSAPrivateKey
        real = rsa.generate_private_key(65537, 2048)
        w = HsmRSAPrivateKey(1, real.public_key(), 'RSA-2048')
        assert w.public_key() is real.public_key() or \
            w.public_key().public_numbers() == real.public_key().public_numbers()
        assert w.key_size == 2048

    def test_sign_delegates_to_hsm_service(self):
        from services.hsm.hsm_private_key import HsmRSAPrivateKey
        real = rsa.generate_private_key(65537, 2048)

        with patch('services.hsm.HsmService.sign') as mock_sign:
            mock_sign.return_value = b'\x01' * 256
            w = HsmRSAPrivateKey(99, real.public_key(), 'RSA-2048')
            sig = w.sign(b'tbs-bytes', padding.PKCS1v15(), hashes.SHA256())
            assert sig == b'\x01' * 256
            mock_sign.assert_called_once_with(99, b'tbs-bytes', 'RSA-2048')

    def test_certificate_builder_sign_calls_hsm(self):
        """End-to-end: builder.sign(wrapper, SHA256) must end up at HsmService.sign."""
        from services.hsm.hsm_private_key import HsmRSAPrivateKey
        real = rsa.generate_private_key(65537, 2048)

        captured = {}

        def fake_sign(key_id, data, algo):
            captured['key_id'] = key_id
            captured['algo'] = algo
            captured['data_len'] = len(data)
            return real.sign(data, padding.PKCS1v15(), hashes.SHA256())

        with patch('services.hsm.HsmService.sign', side_effect=fake_sign):
            w = HsmRSAPrivateKey(7, real.public_key(), 'RSA-2048')
            cert = _builder(real.public_key()).sign(w, hashes.SHA256())

        assert captured['key_id'] == 7
        assert captured['algo'] == 'RSA-2048'
        assert captured['data_len'] > 0
        # Resulting cert is a valid signed X.509
        assert isinstance(cert, x509.Certificate)
        # And the signature actually verifies
        real.public_key().verify(
            cert.signature,
            cert.tbs_certificate_bytes,
            padding.PKCS1v15(),
            cert.signature_hash_algorithm,
        )

    def test_private_bytes_raises(self):
        from services.hsm.hsm_private_key import HsmRSAPrivateKey
        real = rsa.generate_private_key(65537, 2048)
        w = HsmRSAPrivateKey(1, real.public_key())
        with pytest.raises(NotImplementedError):
            w.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )


# ---------------------------------------------------------------------------
# EC wrapper
# ---------------------------------------------------------------------------

class TestHsmECPrivateKey:

    def test_isinstance_ec_private_key(self):
        from services.hsm.hsm_private_key import HsmECPrivateKey
        real = ec.generate_private_key(ec.SECP256R1())
        w = HsmECPrivateKey(1, real.public_key(), 'EC-P256')
        assert isinstance(w, ec.EllipticCurvePrivateKey)

    def test_curve_and_key_size(self):
        from services.hsm.hsm_private_key import HsmECPrivateKey
        real = ec.generate_private_key(ec.SECP256R1())
        w = HsmECPrivateKey(1, real.public_key(), 'EC-P256')
        assert isinstance(w.curve, ec.SECP256R1)
        assert w.key_size == 256

    def test_sign_delegates_to_hsm(self):
        from services.hsm.hsm_private_key import HsmECPrivateKey
        real = ec.generate_private_key(ec.SECP256R1())

        with patch('services.hsm.HsmService.sign') as mock_sign:
            # Real DER ECDSA signature so cryptography accepts it
            mock_sign.return_value = real.sign(b'x', ec.ECDSA(hashes.SHA256()))
            w = HsmECPrivateKey(11, real.public_key(), 'EC-P256')
            sig = w.sign(b'tbs', ec.ECDSA(hashes.SHA256()))
            assert sig
            mock_sign.assert_called_once_with(11, b'tbs', 'EC-P256')

    def test_builder_sign_round_trip(self):
        from services.hsm.hsm_private_key import HsmECPrivateKey
        real = ec.generate_private_key(ec.SECP256R1())

        def fake_sign(key_id, data, algo):
            return real.sign(data, ec.ECDSA(hashes.SHA256()))

        with patch('services.hsm.HsmService.sign', side_effect=fake_sign):
            w = HsmECPrivateKey(3, real.public_key(), 'EC-P256')
            cert = _builder(real.public_key()).sign(w, hashes.SHA256())
        assert isinstance(cert, x509.Certificate)
        real.public_key().verify(
            cert.signature, cert.tbs_certificate_bytes,
            ec.ECDSA(cert.signature_hash_algorithm)
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

class TestLoadHsmPrivateKey:

    def _make_key_record(self, algo, public_pem, purpose='signing',
                         key_type='asymmetric', key_id=42):
        rec = MagicMock()
        rec.id = key_id
        rec.algorithm = algo
        rec.purpose = purpose
        rec.key_type = key_type
        rec.label = f'test-{algo}'
        return rec

    def test_factory_detects_rsa(self, app):
        from services.hsm.hsm_private_key import (
            HsmRSAPrivateKey, load_hsm_private_key,
        )
        with app.app_context():
            real = rsa.generate_private_key(65537, 2048)
            pub_pem = real.public_key().public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            ).decode()
            rec = self._make_key_record('RSA-2048', pub_pem)

            with patch('models.hsm.HsmKey.query') as mock_q, \
                 patch('services.hsm.HsmService.get_public_key', return_value=pub_pem):
                mock_q.get.return_value = rec
                wrapper = load_hsm_private_key(42)

            assert isinstance(wrapper, HsmRSAPrivateKey)
            assert isinstance(wrapper, rsa.RSAPrivateKey)

    def test_factory_detects_ec(self, app):
        from services.hsm.hsm_private_key import (
            HsmECPrivateKey, load_hsm_private_key,
        )
        with app.app_context():
            real = ec.generate_private_key(ec.SECP256R1())
            pub_pem = real.public_key().public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            ).decode()
            rec = self._make_key_record('EC-P256', pub_pem)

            with patch('models.hsm.HsmKey.query') as mock_q, \
                 patch('services.hsm.HsmService.get_public_key', return_value=pub_pem):
                mock_q.get.return_value = rec
                wrapper = load_hsm_private_key(42)

            assert isinstance(wrapper, HsmECPrivateKey)

    def test_factory_unknown_key_id(self, app):
        from services.hsm.hsm_private_key import load_hsm_private_key
        with app.app_context():
            with patch('models.hsm.HsmKey.query') as mock_q:
                mock_q.get.return_value = None
                with pytest.raises(ValueError, match='not found'):
                    load_hsm_private_key(999)

    def test_factory_rejects_symmetric(self, app):
        from services.hsm.hsm_private_key import load_hsm_private_key
        with app.app_context():
            rec = self._make_key_record(
                'AES-256', 'irrelevant', key_type='symmetric'
            )
            with patch('models.hsm.HsmKey.query') as mock_q:
                mock_q.get.return_value = rec
                with pytest.raises(ValueError, match='asymmetric'):
                    load_hsm_private_key(1)

    def test_factory_rejects_non_signing(self, app):
        from services.hsm.hsm_private_key import load_hsm_private_key
        with app.app_context():
            rec = self._make_key_record(
                'RSA-2048', 'irrelevant', purpose='encryption'
            )
            with patch('models.hsm.HsmKey.query') as mock_q:
                mock_q.get.return_value = rec
                with pytest.raises(ValueError, match='signing'):
                    load_hsm_private_key(1)
