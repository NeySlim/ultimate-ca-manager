"""
End-to-end tests for issuing leaf certificates from HSM-backed CAs and
generating CRLs from HSM-backed CAs.

The HSM round-trip is faked with a real local key, so the resulting
signature can be verified with cryptography.
"""

import base64
import os
import sys
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.backends import default_backend


@pytest.fixture
def hsm_ca(app, request):
    """Create an HSM-backed CA whose 'HSM' is actually a local RSA key."""
    suffix = request.node.name[-25:]
    with app.app_context():
        from models import db, CA
        from models.hsm import HsmProvider, HsmKey

        provider = HsmProvider(
            name=f'P-{suffix}', type='pkcs11', config='{}',
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
            key_identifier=f'k-{suffix}',
            label=f'L-{suffix}',
            algorithm='RSA-2048',
            key_type='asymmetric',
            purpose='signing',
            public_key_pem=pub_pem,
        )
        db.session.add(hsm_key)
        db.session.commit()

        provider_id = provider.id
        hsm_key_id = hsm_key.id

    def fake_sign(key_id, data, algo=None):
        return real_key.sign(data, padding.PKCS1v15(), hashes.SHA256())

    p1 = patch('services.hsm.HsmService.sign', side_effect=fake_sign)
    p2 = patch('services.hsm.HsmService.get_public_key', return_value=pub_pem)
    p1.start()
    p2.start()

    with app.app_context():
        from services.ca_service import CAService
        ca = CAService.create_internal_ca(
            descr=f'HSM CA {suffix}',
            dn={'CN': f'HSM CA {suffix}'},
            validity_days=365,
            hsm_key_id=hsm_key_id,
        )
        ca_id = ca.id
        ca_refid = ca.refid

    yield {
        'ca_id': ca_id,
        'ca_refid': ca_refid,
        'real_key': real_key,
        'pub_pem': pub_pem,
        'hsm_key_id': hsm_key_id,
        'provider_id': provider_id,
    }

    p1.stop()
    p2.stop()
    with app.app_context():
        from models import db, CA, Certificate
        from models.hsm import HsmProvider, HsmKey
        Certificate.query.filter_by(caref=ca_refid).delete()
        CA.query.filter_by(id=ca_id).delete()
        HsmKey.query.filter_by(id=hsm_key_id).delete()
        HsmProvider.query.filter_by(id=provider_id).delete()
        db.session.commit()


class TestCertServiceHsm:

    def test_issue_leaf_under_hsm_ca(self, app, hsm_ca):
        from services.cert_service import CertificateService
        with app.app_context():
            cert = CertificateService.create_certificate(
                descr='Leaf via HSM',
                caref=hsm_ca['ca_refid'],
                dn={'CN': 'leaf.example.com'},
                cert_type='server_cert',
                validity_days=30,
                key_type='2048',
                username='tester',
            )

            assert cert.crt
            cert_pem = base64.b64decode(cert.crt)
            x509_cert = x509.load_pem_x509_certificate(
                cert_pem, default_backend()
            )

            # Issued by our HSM CA — verify signature with the public key
            hsm_ca['real_key'].public_key().verify(
                x509_cert.signature,
                x509_cert.tbs_certificate_bytes,
                padding.PKCS1v15(),
                x509_cert.signature_hash_algorithm,
            )


class TestCrlServiceHsm:

    def test_generate_crl_for_hsm_ca(self, app, hsm_ca):
        from services.crl_service import CRLService
        from models import CA, CRLMetadata, db

        with app.app_context():
            crl_meta = CRLService.generate_crl(hsm_ca['ca_id'], validity_days=7)
            assert crl_meta is not None
            assert crl_meta.crl_pem

            crl = x509.load_pem_x509_crl(
                crl_meta.crl_pem.encode() if isinstance(crl_meta.crl_pem, str)
                else crl_meta.crl_pem,
                default_backend(),
            )
            hsm_ca['real_key'].public_key().verify(
                crl.signature,
                crl.tbs_certlist_bytes,
                padding.PKCS1v15(),
                crl.signature_hash_algorithm,
            )

            # Cleanup CRL row to keep DB tidy
            CRLMetadata.query.filter_by(ca_id=hsm_ca['ca_id']).delete()
            db.session.commit()
