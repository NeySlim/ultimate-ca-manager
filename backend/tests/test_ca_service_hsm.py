"""
Tests for HSM-backed CA creation via CAService.create_internal_ca.

Mocks the HSM provider so signing happens locally with a fake key, but
exercises the full code path: HsmKey lookup, public-key fetch, wrapper
construction, certificate signing, and CA persistence with hsm_key_id.
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


@pytest.fixture
def hsm_provider_and_key(app, request):
    """Create a stub HsmProvider + HsmKey row backed by a real local key."""
    suffix = request.node.name[-20:]
    with app.app_context():
        from models import db
        from models.hsm import HsmProvider, HsmKey

        provider = HsmProvider(
            name=f'Mock-Provider-CA-{suffix}',
            type='pkcs11',
            config='{}',
        )
        db.session.add(provider)
        db.session.commit()

        real_key = rsa.generate_private_key(65537, 2048)
        pub_pem = real_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()

        hsm_key = HsmKey(
            provider_id=provider.id,
            key_identifier=f'abcd1234-{suffix}',
            label=f'ca-signing-key-{suffix}',
            algorithm='RSA-2048',
            key_type='asymmetric',
            purpose='signing',
            public_key_pem=pub_pem,
        )
        db.session.add(hsm_key)
        db.session.commit()

        provider_name = provider.name
        provider_id = provider.id
        hsm_key_id = hsm_key.id
        hsm_key_label = hsm_key.label

    yield {
        'provider_id': provider_id,
        'provider_name': provider_name,
        'hsm_key_id': hsm_key_id,
        'hsm_key_label': hsm_key_label,
        'real_key': real_key,
        'pub_pem': pub_pem,
    }

    # Teardown — remove records and any CAs bound to this key
    with app.app_context():
        from models import db, CA
        from models.hsm import HsmProvider, HsmKey
        CA.query.filter_by(hsm_key_id=hsm_key_id).delete()
        HsmKey.query.filter_by(id=hsm_key_id).delete()
        HsmProvider.query.filter_by(id=provider_id).delete()
        db.session.commit()


def _patch_hsm(real_key, pub_pem):
    """Patch HsmService.sign + get_public_key so they use ``real_key``."""
    def fake_sign(key_id, data, algo=None):
        return real_key.sign(data, padding.PKCS1v15(), hashes.SHA256())

    return [
        patch('services.hsm.HsmService.sign', side_effect=fake_sign),
        patch('services.hsm.HsmService.get_public_key', return_value=pub_pem),
    ]


class TestCreateInternalCaWithExistingHsmKey:

    def test_creates_ca_bound_to_hsm_key(self, app, hsm_provider_and_key):
        from services.ca_service import CAService
        from models import CA

        with app.app_context():
            patches = _patch_hsm(
                hsm_provider_and_key['real_key'],
                hsm_provider_and_key['pub_pem'],
            )
            for p in patches:
                p.start()
            try:
                ca = CAService.create_internal_ca(
                    descr='HSM Root',
                    dn={'CN': 'HSM Root', 'O': 'Test', 'C': 'US'},
                    validity_days=365,
                    username='tester',
                    hsm_key_id=hsm_provider_and_key['hsm_key_id'],
                )
            finally:
                for p in patches:
                    p.stop()

            assert ca.hsm_key_id == hsm_provider_and_key['hsm_key_id']
            assert ca.prv is None, "HSM-backed CA must not have a local prv"
            assert ca.uses_hsm is True
            assert ca.has_private_key is True

            # Cert is valid and self-signed
            cert = x509.load_pem_x509_certificate(
                __import__('base64').b64decode(ca.crt), default_backend()
            )
            hsm_provider_and_key['real_key'].public_key().verify(
                cert.signature, cert.tbs_certificate_bytes,
                padding.PKCS1v15(), cert.signature_hash_algorithm,
            )

            # Cleanup
            from models import db
            CA.query.filter_by(id=ca.id).delete()
            db.session.commit()

    def test_rejects_unknown_hsm_key(self, app):
        from services.ca_service import CAService
        with app.app_context():
            with pytest.raises(ValueError, match='not found'):
                CAService.create_internal_ca(
                    descr='Bad', dn={'CN': 'Bad'},
                    hsm_key_id=999999,
                )

    def test_rejects_double_binding(self, app, hsm_provider_and_key):
        from services.ca_service import CAService
        from models import db, CA

        with app.app_context():
            patches = _patch_hsm(
                hsm_provider_and_key['real_key'],
                hsm_provider_and_key['pub_pem'],
            )
            for p in patches:
                p.start()
            try:
                ca = CAService.create_internal_ca(
                    descr='First HSM CA', dn={'CN': 'First'},
                    hsm_key_id=hsm_provider_and_key['hsm_key_id'],
                )
                with pytest.raises(ValueError, match='already bound'):
                    CAService.create_internal_ca(
                        descr='Second', dn={'CN': 'Second'},
                        hsm_key_id=hsm_provider_and_key['hsm_key_id'],
                    )
            finally:
                for p in patches:
                    p.stop()
                CA.query.filter_by(id=ca.id).delete()
                db.session.commit()


class TestCreateInternalCaWithNewHsmKey:

    def test_generates_key_then_creates_ca(self, app, hsm_provider_and_key):
        from services.ca_service import CAService
        from models import db, CA
        from models.hsm import HsmKey

        provider_id = hsm_provider_and_key['provider_id']
        real = rsa.generate_private_key(65537, 2048)
        pub_pem = real.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()

        with app.app_context():
            new_hsm_key = HsmKey(
                provider_id=provider_id,
                key_identifier='xyz9999',
                label='new-ca-key',
                algorithm='RSA-2048',
                key_type='asymmetric',
                purpose='signing',
                public_key_pem=pub_pem,
            )

            def fake_generate_key(provider_id, label, algorithm,
                                  purpose='signing'):
                db.session.add(new_hsm_key)
                db.session.commit()
                return new_hsm_key

            def fake_sign(key_id, data, algo=None):
                return real.sign(data, padding.PKCS1v15(), hashes.SHA256())

            with patch('services.hsm.HsmService.generate_key',
                       side_effect=fake_generate_key), \
                 patch('services.hsm.HsmService.sign', side_effect=fake_sign), \
                 patch('services.hsm.HsmService.get_public_key',
                       return_value=pub_pem):
                ca = CAService.create_internal_ca(
                    descr='Generated HSM CA',
                    dn={'CN': 'Generated HSM CA'},
                    validity_days=365,
                    hsm_provider_id=provider_id,
                    hsm_key_label='new-ca-key',
                    hsm_key_algorithm='RSA-2048',
                )

            assert ca.hsm_key_id == new_hsm_key.id
            assert ca.prv is None
            assert ca.uses_hsm is True

            CA.query.filter_by(id=ca.id).delete()
            HsmKey.query.filter_by(id=new_hsm_key.id).delete()
            db.session.commit()

    def test_validates_required_fields(self, app, hsm_provider_and_key):
        from services.ca_service import CAService
        with app.app_context():
            with pytest.raises(ValueError, match='all required'):
                CAService.create_internal_ca(
                    descr='Bad', dn={'CN': 'Bad'},
                    hsm_provider_id=hsm_provider_and_key['provider_id'],
                    # missing hsm_key_label & hsm_key_algorithm
                )

    def test_rejects_mixed_modes(self, app, hsm_provider_and_key):
        from services.ca_service import CAService
        with app.app_context():
            with pytest.raises(ValueError, match='hsm_key_id'):
                CAService.create_internal_ca(
                    descr='Bad', dn={'CN': 'Bad'},
                    hsm_key_id=hsm_provider_and_key['hsm_key_id'],
                    hsm_provider_id=hsm_provider_and_key['provider_id'],
                    hsm_key_label='whatever',
                    hsm_key_algorithm='RSA-2048',
                )


class TestCaToDictHsmFields:

    def test_to_dict_exposes_hsm_metadata(self, app, hsm_provider_and_key):
        from services.ca_service import CAService
        from models import db, CA

        with app.app_context():
            patches = _patch_hsm(
                hsm_provider_and_key['real_key'],
                hsm_provider_and_key['pub_pem'],
            )
            for p in patches:
                p.start()
            try:
                ca = CAService.create_internal_ca(
                    descr='HSM dict CA', dn={'CN': 'HSM dict CA'},
                    hsm_key_id=hsm_provider_and_key['hsm_key_id'],
                )
                d = ca.to_dict()
                assert d['uses_hsm'] is True
                assert d['hsm_key_id'] == hsm_provider_and_key['hsm_key_id']
                assert d['hsm_provider_id'] == hsm_provider_and_key['provider_id']
                assert d['hsm_provider_name'] == hsm_provider_and_key['provider_name']
                assert d['hsm_key_label'] == hsm_provider_and_key['hsm_key_label']
            finally:
                for p in patches:
                    p.stop()
                CA.query.filter_by(id=ca.id).delete()
                db.session.commit()

    def test_to_dict_local_ca_has_null_hsm_fields(self, app, create_ca):
        from models import CA
        with app.app_context():
            data = create_ca(cn='Plain Local CA HSM Test')
            ca = CA.query.get(data['id'])
            d = ca.to_dict()
            assert d['uses_hsm'] is False
            assert d['hsm_key_id'] is None
            assert d['hsm_provider_id'] is None
            assert d['hsm_provider_name'] is None
            assert d['hsm_key_label'] is None
