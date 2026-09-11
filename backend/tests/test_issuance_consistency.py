"""Lot 9: consistency fixes across issuance paths (restore key match,
template CA bits, Certificate Transparency on every builder, typed CA
lookups, concurrency guards, ACME failure classification).
"""

import base64
import json

import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtensionOID

from models import CA, Certificate, db
from models.certificate_template import CertificateTemplate
from utils.key_codec import load_pem_bytes


def _post(client, url, payload):
    return client.post(url, data=json.dumps(payload), content_type='application/json')


def _encrypted_pkcs8(key, password: str) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(password.encode()),
    )


class TestRestoreKeyMustMatch:

    def _take_offline(self, app, ca_id):
        with app.app_context():
            ca = db.session.get(CA, ca_id)
            own_key = serialization.load_pem_private_key(
                load_pem_bytes(ca.prv, context='test'), password=None, backend=default_backend())
            ca.prv = None
            ca.offline = True
            ca.offline_mode = 'file_exported'
            db.session.commit()
            return own_key

    def test_foreign_key_is_refused(self, app, auth_client, create_ca):
        ca = create_ca(cn='Restore foreign key CA')
        self._take_offline(app, ca['id'])
        foreign = rsa.generate_private_key(65537, 2048)
        r = auth_client.post(f"/api/v2/cas/{ca['id']}/restore", data={
            'password': 'Restore-Pass-123',
            'key_file': (__import__('io').BytesIO(_encrypted_pkcs8(foreign, 'Restore-Pass-123')), 'ca.key'),
        }, content_type='multipart/form-data')
        assert r.status_code == 400, (r.status_code, r.data[:200])
        with app.app_context():
            row = db.session.get(CA, ca['id'])
            assert row.offline is True and not row.prv

    def test_own_key_restores(self, app, auth_client, create_ca):
        ca = create_ca(cn='Restore own key CA')
        own_key = self._take_offline(app, ca['id'])
        r = auth_client.post(f"/api/v2/cas/{ca['id']}/restore", data={
            'password': 'Restore-Pass-123',
            'key_file': (__import__('io').BytesIO(_encrypted_pkcs8(own_key, 'Restore-Pass-123')), 'ca.key'),
        }, content_type='multipart/form-data')
        assert r.status_code == 200, (r.status_code, r.data[:200])
        with app.app_context():
            row = db.session.get(CA, ca['id'])
            assert row.offline is False and row.prv


class TestTemplateCaBits:

    def test_leaf_template_drops_the_ca_bits(self, app, auth_client):
        r = _post(auth_client, '/api/v2/templates', {
            'name': 'ca-bits-leaf', 'template_type': 'custom', 'key_type': 'RSA-2048',
            'validity_days': 30, 'digest': 'sha256',
            'extensions_template': {'key_usage': ['digitalSignature', 'keyCertSign', 'cRLSign']},
        })
        assert r.status_code == 201, (r.status_code, r.get_json())
        tpl_id = r.get_json()['data']['id']
        with app.app_context():
            tpl = db.session.get(CertificateTemplate, tpl_id)
            assert json.loads(tpl.extensions_template)['key_usage'] == ['digitalSignature']
            db.session.delete(tpl)
            db.session.commit()

    def test_existing_template_ca_bits_never_land_on_a_leaf(self, app, auth_client, create_ca):
        ca = create_ca(cn='Template CA bits CA')
        with app.app_context():
            tpl = CertificateTemplate(name='ca-bits-existing', template_type='custom', key_type='RSA-2048',
                                      validity_days=30, digest='sha256',
                                      extensions_template=json.dumps(
                                          {'key_usage': ['digitalSignature', 'keyCertSign', 'cRLSign']}))
            db.session.add(tpl)
            db.session.commit()
            tpl_id = tpl.id
        try:
            r = _post(auth_client, '/api/v2/certificates', {
                'cn': 'cabits.example.test', 'ca_id': ca['id'], 'template_id': tpl_id, 'validity_days': 30})
            assert r.status_code == 201, r.get_json()
            with app.app_context():
                row = db.session.get(Certificate, r.get_json()['data']['id'])
                leaf = x509.load_pem_x509_certificate(base64.b64decode(row.crt), default_backend())
                ku = leaf.extensions.get_extension_for_oid(ExtensionOID.KEY_USAGE).value
                assert not ku.key_cert_sign and not ku.crl_sign and ku.digital_signature
                db.session.delete(row)
                db.session.commit()
        finally:
            with app.app_context():
                db.session.delete(db.session.get(CertificateTemplate, tpl_id))
                db.session.commit()


class TestCtPolicyOnEveryBuilder:

    def test_issue_form_honours_ct_required(self, auth_client, create_ca, monkeypatch):
        import utils.ct_client as ct_client

        def refuse(cert, issuer_cert, issuer_key):
            raise ValueError('ct_required: no SCT could be obtained')
        monkeypatch.setattr(ct_client, 'apply_ct_policy', refuse)
        ca = create_ca(cn='CT issue form CA')
        r = _post(auth_client, '/api/v2/certificates',
                  {'cn': 'ct.example.test', 'ca_id': ca['id'], 'validity_days': 30})
        assert r.status_code == 400, (r.status_code, r.get_json())


class TestTypedCaLookups:

    def test_issue_form_accepts_a_refid_and_refuses_garbage(self, app, auth_client, create_ca):
        ca = create_ca(cn='Typed lookup CA')
        r = _post(auth_client, '/api/v2/certificates',
                  {'cn': 'refid.example.test', 'ca_id': ca['refid'], 'validity_days': 30})
        assert r.status_code == 201, r.get_json()
        with app.app_context():
            row = db.session.get(Certificate, r.get_json()['data']['id'])
            db.session.delete(row)
            db.session.commit()
        r = _post(auth_client, '/api/v2/certificates',
                  {'cn': 'garbage.example.test', 'ca_id': 'not-a-ca', 'validity_days': 30})
        assert r.status_code == 404


class TestConcurrencyGuards:

    def test_only_one_request_flips_an_order_to_processing(self, app, create_ca):
        from models.acme_models import AcmeOrder
        from services.acme.acme_service import AcmeService
        with app.app_context():
            order = AcmeOrder(order_id='race-order-1', account_id='race-account', status='ready',
                              identifiers=json.dumps([{'type': 'dns', 'value': 'race.example.test'}]))
            db.session.add(order)
            db.session.commit()
            service = AcmeService()
            try:
                assert service.begin_order_processing(order) is True
                assert service.begin_order_processing(order) is False
            finally:
                db.session.delete(db.session.get(AcmeOrder, order.id))
                db.session.commit()

    def test_a_csr_signed_meanwhile_is_not_signed_again(self, app, create_ca):
        from services.cert_service import CertificateService
        from sqlalchemy.orm.attributes import set_committed_value
        ca = create_ca(cn='CSR race CA')
        with app.app_context():
            ca_row = db.session.get(CA, ca['id'])
            csr_row = CertificateService.generate_csr(
                descr='race-csr', dn={'CN': 'race-csr.example.test'}, key_type='2048')
            db.session.commit()
            first = CertificateService.sign_csr(cert_id=csr_row.id, caref=ca_row.refid, validity_days=30)
            db.session.commit()
            stored_crt = first.crt
            row = db.session.get(Certificate, csr_row.id)
            set_committed_value(row, 'crt', None)  # what a stale worker still believes
            with pytest.raises(ValueError, match='another request'):
                CertificateService.sign_csr(cert_id=csr_row.id, caref=ca_row.refid, validity_days=30)
            db.session.rollback()
            row = db.session.get(Certificate, csr_row.id)
            assert row.crt == stored_crt
            db.session.delete(row)
            db.session.commit()


class TestAcmeFailureClassification:

    def test_server_side_failures_are_not_the_requests_fault(self):
        from services.acme.mixins.issuance import IssuanceMixin
        from utils.ca_signing_window import IssuerWindowError
        assert IssuanceMixin._is_request_failure(IssuerWindowError('expired')) is False
        assert IssuanceMixin._is_request_failure(RuntimeError('Failed to load CA signing key')) is False
        assert IssuanceMixin._is_request_failure(ValueError('CSR public key too weak')) is True
        assert IssuanceMixin._is_request_failure(None) is True
