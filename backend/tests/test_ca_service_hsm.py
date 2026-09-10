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
from models import db


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
    def fake_sign(key_id, data, algo=None, hash_algorithm=None):
        digest = {'sha384': hashes.SHA384, 'sha512': hashes.SHA512}.get(hash_algorithm, hashes.SHA256)()
        return real_key.sign(data, padding.PKCS1v15(), digest)

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

            def fake_sign(key_id, data, algo=None, hash_algorithm=None):
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
            ca = db.session.get(CA, data['id'])
            d = ca.to_dict()
            assert d['uses_hsm'] is False
            assert d['hsm_key_id'] is None
            assert d['hsm_provider_id'] is None
            assert d['hsm_provider_name'] is None
            assert d['hsm_key_label'] is None


class TestHsmCaReimport:
    """Sixth review of #347: re-importing a re-keyed certificate onto an
    HSM-backed CA must not keep an HSM binding that is no longer its key."""

    @staticmethod
    def _selfsigned(cn, key, signer=None):
        from datetime import datetime, timedelta, timezone
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
        now = datetime.now(timezone.utc)
        return (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                .public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=365))
                .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                .sign(signer or key, hashes.SHA256()))

    def _bound_ca(self, app, fx, cn):
        import base64
        with app.app_context():
            from models import db, CA
            cert = self._selfsigned(cn, fx['real_key'])
            ca = CA(refid=f'hsm-reimport-{cn}', descr=cn, serial=0,
                    crt=base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode(),
                    prv=None, hsm_key_id=fx['hsm_key_id'],
                    subject=cert.subject.rfc4514_string(), issuer=cert.issuer.rfc4514_string())
            db.session.add(ca); db.session.commit()
            return ca.id

    @staticmethod
    def _import(auth_client, cert):
        pem = cert.public_bytes(serialization.Encoding.PEM).decode()
        return auth_client.post('/api/v2/cas/import', data={'pem_content': pem},
                                content_type='multipart/form-data')

    def test_rekeyed_certificate_unbinds_the_hsm_key(self, app, auth_client, hsm_provider_and_key):
        import json
        fx = hsm_provider_and_key
        ca_id = self._bound_ca(app, fx, 'HSM Rekey CA')
        other = rsa.generate_private_key(65537, 2048)
        rekeyed = self._selfsigned('HSM Rekey CA', other)
        patches = _patch_hsm(fx['real_key'], fx['pub_pem'])
        for p in patches: p.start()
        try:
            r = self._import(auth_client, rekeyed)
        finally:
            for p in patches: p.stop()
        assert r.status_code == 200, r.data
        body = json.loads(r.data)
        assert body['data']['id'] == ca_id
        assert 'unbound' in body['message']
        with app.app_context():
            from models import db, CA
            row = db.session.get(CA, ca_id)
            assert row.hsm_key_id is None
            assert row.has_private_key is False

    def test_renewed_certificate_keeps_the_hsm_key(self, app, auth_client, hsm_provider_and_key):
        import json
        fx = hsm_provider_and_key
        ca_id = self._bound_ca(app, fx, 'HSM Renew CA')
        renewed = self._selfsigned('HSM Renew CA', fx['real_key'])
        patches = _patch_hsm(fx['real_key'], fx['pub_pem'])
        for p in patches: p.start()
        try:
            r = self._import(auth_client, renewed)
        finally:
            for p in patches: p.stop()
        assert r.status_code == 200, r.data
        assert 'unbound' not in json.loads(r.data)['message']
        with app.app_context():
            from models import db, CA
            assert db.session.get(CA, ca_id).hsm_key_id == fx['hsm_key_id']

    def test_unreachable_hsm_refuses_the_update(self, app, auth_client, hsm_provider_and_key):
        fx = hsm_provider_and_key
        ca_id = self._bound_ca(app, fx, 'HSM Down CA')
        other = rsa.generate_private_key(65537, 2048)
        rekeyed = self._selfsigned('HSM Down CA', other)
        with app.app_context():
            from models.hsm import HsmKey
            HsmKey.query.filter_by(id=fx['hsm_key_id']).update({'public_key_pem': None})
            from models import db; db.session.commit()
        with patch('services.hsm.HsmService.get_public_key', side_effect=RuntimeError('hsm down')):
            r = self._import(auth_client, rekeyed)
        assert r.status_code == 409, r.data
        with app.app_context():
            from models import db, CA
            assert db.session.get(CA, ca_id).hsm_key_id == fx['hsm_key_id']  # untouched

    @staticmethod
    def _garbage_provider():
        """A provider whose public key is unusable: the lookup caches it, and
        commits, before the binding check finds it invalid."""
        fake = MagicMock()
        fake.__enter__.return_value = fake
        fake.get_public_key.return_value = 'not a public key'
        return patch('services.hsm.hsm_service.HsmService._get_provider_instance', return_value=fake)

    @pytest.mark.parametrize('path', ['/api/v2/cas/import', '/api/v2/certificates/import'])
    def test_refused_update_persists_nothing_even_when_the_lookup_commits(self, app, auth_client, hsm_provider_and_key, path):
        """Eighth review of #347: the record must not be touched before the
        HSM check, since that check may commit on its way."""
        fx = hsm_provider_and_key
        cn = f"HSM Atomic CA {path.split('/')[3]}"
        ca_id = self._bound_ca(app, fx, cn)
        with app.app_context():
            from models import db, CA
            from models.hsm import HsmKey
            HsmKey.query.filter_by(id=fx['hsm_key_id']).update({'public_key_pem': None}); db.session.commit()
            row = db.session.get(CA, ca_id)
            before = (row.crt, row.descr, row.hsm_key_id, row.valid_to)
        rekeyed = self._selfsigned(cn, rsa.generate_private_key(65537, 2048))
        pem = rekeyed.public_bytes(serialization.Encoding.PEM).decode()
        with self._garbage_provider():
            r = auth_client.post(path, data={'pem_content': pem, 'name': 'renamed on the way'},
                                 content_type='multipart/form-data')
        assert r.status_code == 409, r.data
        with app.app_context():
            from models import db, CA
            db.session.expire_all()
            row = db.session.get(CA, ca_id)
            assert (row.crt, row.descr, row.hsm_key_id, row.valid_to) == before

    @pytest.mark.parametrize('path', ['/api/v2/cas/import', '/api/v2/certificates/import'])
    def test_pending_hsm_ca_next_to_a_homonym_is_completed(self, app, auth_client, hsm_provider_and_key, path):
        """Tenth review of #347: a pending HSM CA (no certificate, no key
        column) is known by its request's key and completed through the
        dedicated path instead of being refused as ambiguous."""
        import base64, json
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        fx = hsm_provider_and_key
        tag = path.split('/')[3]
        cn = f'Pending HSM Homonym {tag}'
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
        homonym = self._selfsigned(cn, rsa.generate_private_key(65537, 2048))
        with app.app_context():
            from models import db, CA
            row1 = CA(refid=f'hsm-homonym-{tag}', descr=cn, serial=0, prv=None,
                      crt=base64.b64encode(homonym.public_bytes(serialization.Encoding.PEM)).decode(),
                      subject=homonym.subject.rfc4514_string(), issuer=homonym.issuer.rfc4514_string())
            csr = x509.CertificateSigningRequestBuilder().subject_name(name).sign(fx['real_key'], hashes.SHA256())
            row2 = CA(refid=f'hsm-pending-{tag}', descr=cn, serial=0, crt='', prv=None,
                      csr=base64.b64encode(csr.public_bytes(serialization.Encoding.PEM)).decode(),
                      hsm_key_id=fx['hsm_key_id'], subject=name.rfc4514_string(), imported_from='external_csr')
            db.session.add_all([row1, row2]); db.session.commit()
            id1, id2, crt1 = row1.id, row2.id, row1.crt
        from datetime import datetime, timedelta, timezone
        ext_key = rsa.generate_private_key(65537, 2048)
        now = datetime.now(timezone.utc)
        signed = (x509.CertificateBuilder().subject_name(name)
                  .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'External Root HSM 347')]))
                  .public_key(fx['real_key'].public_key()).serial_number(x509.random_serial_number())
                  .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=365))
                  .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                  .sign(ext_key, hashes.SHA256()))
        patches = _patch_hsm(fx['real_key'], fx['pub_pem'])
        for p in patches: p.start()
        try:
            r = auth_client.post(path, data={'pem_content': signed.public_bytes(serialization.Encoding.PEM).decode()},
                                 content_type='multipart/form-data')
        finally:
            for p in patches: p.stop()
        assert r.status_code == 200, r.data
        body = json.loads(r.data)
        assert body['data']['id'] == id2, (body['data']['id'], id1, id2)
        assert body['data']['uses_hsm'] and body['data']['hsm_key_id'] == fx['hsm_key_id']
        assert 'installed' in body['message']
        with app.app_context():
            from models import db, CA
            db.session.expire_all()
            assert db.session.get(CA, id1).crt == crt1
            row = db.session.get(CA, id2)
            assert row.crt and not row.is_pending and row.hsm_key_id == fx['hsm_key_id']

    def test_record_identity_falls_back_to_the_cached_hsm_public_key(self, app, hsm_provider_and_key):
        """Without certificate, key column or request, the cached public key of
        the bound HSM key still identifies the record, without reaching the HSM."""
        from cryptography.hazmat.primitives import serialization as ser
        from services.import_service import _record_identity
        fx = hsm_provider_and_key
        with app.app_context():
            from models import db, CA
            row = CA(refid='hsm-identity-only', descr='HSM identity', serial=0, crt='', prv=None, csr=None,
                     hsm_key_id=fx['hsm_key_id'], subject='CN=HSM identity')
            db.session.add(row); db.session.commit()
            with patch('services.hsm.HsmService.get_public_key', side_effect=AssertionError('must not reach the HSM')):
                stored_cert, spki = _record_identity(row)
            assert stored_cert is None
            assert spki == fx['real_key'].public_key().public_bytes(ser.Encoding.DER, ser.PublicFormat.SubjectPublicKeyInfo)
