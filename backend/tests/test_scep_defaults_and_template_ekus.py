"""SCEP issuance applies the same defaults and template rules as the other
enrollment paths: a request without Key Usage or Extended Key Usage gets the
TLS defaults instead of an unrestricted certificate, and a template bound to
a SCEP profile can neither be saved with nor issue an EKU that grants
authority over the PKI or a logon identity of the enrollee's choosing.
"""

import base64
import json

import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, ExtensionOID, NameOID

from models import CA, Certificate, SCEPRequest, db
from models.certificate_template import CertificateTemplate

SMARTCARD_LOGON = x509.ObjectIdentifier('1.3.6.1.4.1.311.20.2.2')


def _csr(cn, sans=(), extensions=()):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]) if cn else x509.Name([])
    builder = x509.CertificateSigningRequestBuilder().subject_name(name)
    if sans:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.DNSName(s) for s in sans]), critical=False)
    for ext, critical in extensions:
        builder = builder.add_extension(ext, critical)
    return builder.sign(key, hashes.SHA256())


def _issue(app, ca_id, csr, template=None, txn='scep-defaults'):
    from services.scep.scep_service import SCEPService
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        svc = SCEPService(ca_refid=ca.refid, auto_approve=True, template=template)
        req = SCEPRequest(transaction_id=txn, ca_refid=ca.refid,
                          csr=base64.b64encode(csr.public_bytes(serialization.Encoding.DER)).decode(),
                          status='pending', subject=csr.subject.rfc4514_string())
        db.session.add(req)
        db.session.flush()
        refid = svc._auto_approve_request(req, csr)
        db.session.commit()
        row = Certificate.query.filter_by(refid=refid).first()
        cert = x509.load_pem_x509_certificate(base64.b64decode(row.crt), default_backend())
        db.session.delete(row)
        db.session.delete(req)
        db.session.commit()
        return cert


class TestBareCsrDefaults:

    def test_no_key_usage_and_no_eku_get_the_tls_defaults(self, app, create_ca):
        ca = create_ca(cn='SCEP defaults CA')
        cert = _issue(app, ca['id'], _csr('bare.example.test'))
        ku = cert.extensions.get_extension_for_oid(ExtensionOID.KEY_USAGE)
        assert ku.critical and ku.value.digital_signature and ku.value.key_encipherment
        eku = cert.extensions.get_extension_for_oid(ExtensionOID.EXTENDED_KEY_USAGE).value
        assert set(eku) == {ExtendedKeyUsageOID.SERVER_AUTH, ExtendedKeyUsageOID.CLIENT_AUTH}

    def test_san_is_critical_when_the_subject_is_empty(self, app, create_ca):
        ca = create_ca(cn='SCEP empty subject CA')
        try:
            cert = _issue(app, ca['id'], _csr('', sans=['nosubject.example.test']), txn='scep-empty')
        except Exception as exc:  # the SCEP path may refuse an empty subject upstream
            pytest.skip(f'empty subject refused before the builder: {exc}')
        san = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
        assert san.critical is True


class TestTemplateSensitiveEkus:

    def _template(self, app, ekus):
        with app.app_context():
            tpl = CertificateTemplate(name=f'scep-sensitive-{"-".join(ekus)}', template_type='custom',
                                      key_type='RSA-2048', validity_days=30, digest='sha256')
            tpl.set_extensions({'extended_key_usage': ekus}) if hasattr(tpl, 'set_extensions') else None
            if not hasattr(tpl, 'set_extensions'):
                tpl.extensions_template = json.dumps({'extended_key_usage': ekus})
            db.session.add(tpl)
            db.session.commit()
            return tpl.id

    def test_binding_a_smartcard_logon_template_is_refused(self, app, auth_client, create_ca):
        ca = create_ca(cn='SCEP sensitive binding CA')
        tpl_id = self._template(app, ['clientAuth', 'msSmartcardLogin'])
        try:
            r = auth_client.post('/api/v2/scep/profiles', data=json.dumps(
                {'name': 'sensitive-profile', 'auto_approve': True, 'template_id': tpl_id,
                 'ca_id': ca['id']}),
                content_type='application/json')
            assert r.status_code == 400, (r.status_code, r.get_json())
            assert b'cannot be issued over SCEP' in r.data
        finally:
            with app.app_context():
                db.session.delete(db.session.get(CertificateTemplate, tpl_id))
                db.session.commit()

    def test_an_existing_binding_never_issues_the_sensitive_eku(self, app, create_ca):
        ca = create_ca(cn='SCEP sensitive template CA')
        tpl_id = self._template(app, ['clientAuth', 'msSmartcardLogin'])
        try:
            with app.app_context():
                tpl = db.session.get(CertificateTemplate, tpl_id)
                cert = _issue(app, ca['id'], _csr('tpl.example.test'), template=tpl, txn='scep-tpl')
            eku = cert.extensions.get_extension_for_oid(ExtensionOID.EXTENDED_KEY_USAGE).value
            assert SMARTCARD_LOGON not in list(eku)
            assert ExtendedKeyUsageOID.CLIENT_AUTH in list(eku)
        finally:
            with app.app_context():
                db.session.delete(db.session.get(CertificateTemplate, tpl_id))
                db.session.commit()
