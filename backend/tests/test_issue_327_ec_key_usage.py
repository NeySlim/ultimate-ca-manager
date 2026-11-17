"""Issue #327: keyUsage must follow the key algorithm on every leaf path.

An ECDSA leaf issued over ACME carried ``digitalSignature, keyEncipherment``
with no way to constrain it: an ACME order selects no template, and only a
template with the bit deselected avoided it on the UI path. keyEncipherment
is RSA key transport and an EC key cannot honour it (RFC 5480 §3), so every
leaf path now routes its KeyUsage through ``utils.leaf_key_usage``:

* the issue form (cert_create), the approval workflow (policies), the
  low-level create_certificate, sign_csr (ACME / EST / WSTEP / Sign CSR)
  and SCEP all drop keyEncipherment / dataEncipherment on a non-RSA key;
* an S/MIME (emailProtection) leaf on an EC key keeps its encryption intent
  as keyAgreement, the bit ECDH-based CMS encryption needs;
* RSA leaves are untouched.
"""
import base64
import json

import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, ExtensionOID, NameOID

from models import db, CA, Certificate
from tests.conftest import get_json
from tests.test_scep_rfc8894_operations import _load_ca_material
from utils.leaf_key_usage import constrain_builder_key_usage, key_usage_for_key
from tests.fixtures.templates import templates_created_here_removed


@pytest.fixture(autouse=True, scope='module')
def _templates_stay_in_this_module(app):
    with templates_created_here_removed(app):
        yield


CONTENT_JSON = 'application/json'

_KU_BITS = ('digital_signature', 'content_commitment', 'key_encipherment',
            'data_encipherment', 'key_agreement', 'key_cert_sign', 'crl_sign')


def _ku(usage_or_cert):
    """Set of asserted KeyUsage bit names (encipherOnly/decipherOnly included)."""
    ku = usage_or_cert
    if isinstance(ku, x509.Certificate):
        ku = ku.extensions.get_extension_for_oid(ExtensionOID.KEY_USAGE).value
    bits = {name for name in _KU_BITS if getattr(ku, name)}
    if ku.key_agreement:
        bits |= {name for name in ('encipher_only', 'decipher_only') if getattr(ku, name)}
    return bits


def _eku(cert):
    ext = cert.extensions.get_extension_for_oid(ExtensionOID.EXTENDED_KEY_USAGE)
    return set(ext.value)


def _usage(**on):
    flags = dict.fromkeys(_KU_BITS + ('encipher_only', 'decipher_only'), False)
    flags.update(on)
    return x509.KeyUsage(**flags)


def _csr(key, cn, extensions=()):
    builder = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
    for value, critical in extensions:
        builder = builder.add_extension(value, critical)
    return builder.sign(key, hashes.SHA256(), default_backend())


def _issued_cert(app, cert_id):
    with app.app_context():
        row = db.session.get(Certificate, cert_id)
        assert row is not None and row.crt
        pem = base64.b64decode(row.crt)
    return x509.load_pem_x509_certificate(pem, default_backend())


class TestKeyUsageForKey:
    """Pure helper semantics."""

    def test_rsa_passes_through(self):
        key = rsa.generate_private_key(65537, 2048, default_backend())
        usage = _usage(digital_signature=True, key_encipherment=True)
        assert key_usage_for_key(key.public_key(), usage) is usage

    def test_ec_server_keeps_signature_only(self):
        key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        usage = _usage(digital_signature=True, key_encipherment=True,
                       data_encipherment=True)
        fixed = key_usage_for_key(key.public_key(), usage,
                                  [ExtendedKeyUsageOID.SERVER_AUTH])
        assert _ku(fixed) == {'digital_signature'}

    def test_ec_smime_translates_encipherment_to_key_agreement(self):
        key = ec.generate_private_key(ec.SECP384R1(), default_backend())
        usage = _usage(digital_signature=True, content_commitment=True,
                       key_encipherment=True)
        fixed = key_usage_for_key(key.public_key(), usage,
                                  [ExtendedKeyUsageOID.EMAIL_PROTECTION])
        assert _ku(fixed) == {'digital_signature', 'content_commitment',
                              'key_agreement'}

    def test_ec_explicit_key_agreement_and_encipher_only_survive(self):
        key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        usage = _usage(digital_signature=True, key_agreement=True,
                       encipher_only=True)
        fixed = key_usage_for_key(key.public_key(), usage)
        assert _ku(fixed) == {'digital_signature', 'key_agreement', 'encipher_only'}

    def test_ec_without_encryption_intent_gains_nothing(self):
        key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        usage = _usage(digital_signature=True)
        fixed = key_usage_for_key(key.public_key(), usage,
                                  [ExtendedKeyUsageOID.EMAIL_PROTECTION])
        assert _ku(fixed) == {'digital_signature'}

    def test_ed25519_is_signature_only(self):
        key = ed25519.Ed25519PrivateKey.generate()
        usage = _usage(digital_signature=True, key_encipherment=True,
                       key_agreement=True, encipher_only=True)
        fixed = key_usage_for_key(key.public_key(), usage,
                                  [ExtendedKeyUsageOID.EMAIL_PROTECTION])
        assert _ku(fixed) == {'digital_signature'}

    def test_ca_bits_untouched(self):
        key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        usage = _usage(digital_signature=True, key_cert_sign=True, crl_sign=True)
        assert _ku(key_usage_for_key(key.public_key(), usage)) == \
            {'digital_signature', 'key_cert_sign', 'crl_sign'}


class TestConstrainBuilder:
    """The builder rewrite used by the CSR-driven paths."""

    @staticmethod
    def _builder(key, usage=None, ekus=None):
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'b.test')])
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        b = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
             .public_key(key.public_key()).serial_number(7)
             .not_valid_before(now).not_valid_after(now + timedelta(days=1))
             .add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
             .add_extension(x509.SubjectAlternativeName([x509.DNSName('b.test')]), False))
        if usage is not None:
            b = b.add_extension(usage, True)
        if ekus:
            b = b.add_extension(x509.ExtendedKeyUsage(ekus), False)
        return b

    def test_no_key_usage_is_a_noop(self):
        key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        b = self._builder(key)
        assert constrain_builder_key_usage(b) is b

    def test_rsa_is_a_noop(self):
        key = rsa.generate_private_key(65537, 2048, default_backend())
        b = self._builder(key, _usage(digital_signature=True, key_encipherment=True))
        assert constrain_builder_key_usage(b) is b

    def test_ec_rewrite_keeps_every_other_extension_and_criticality(self):
        key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        b = self._builder(key, _usage(digital_signature=True, key_encipherment=True),
                          [ExtendedKeyUsageOID.SERVER_AUTH])
        before = [(e.oid, e.critical) for e in b._extensions]
        fixed = constrain_builder_key_usage(b)
        assert fixed is not b
        assert [(e.oid, e.critical) for e in fixed._extensions] == before
        cert = fixed.sign(key, hashes.SHA256(), default_backend())
        assert _ku(cert) == {'digital_signature'}
        assert cert.serial_number == 7

    def test_ec_smime_builder_gets_key_agreement(self):
        key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        b = self._builder(key, _usage(digital_signature=True, key_encipherment=True),
                          [ExtendedKeyUsageOID.EMAIL_PROTECTION])
        cert = constrain_builder_key_usage(b).sign(key, hashes.SHA256(), default_backend())
        assert _ku(cert) == {'digital_signature', 'key_agreement'}


class TestIssueForm:
    """POST /api/v2/certificates (the web UI path)."""

    @staticmethod
    def _issue(auth_client, ca_id, cn, **extra):
        payload = {'cn': cn, 'ca_id': ca_id, 'validity_days': 90}
        payload.update(extra)
        r = auth_client.post('/api/v2/certificates', data=json.dumps(payload),
                             content_type=CONTENT_JSON)
        assert r.status_code in (200, 201), r.data
        return get_json(r)['data']['id']

    def test_ec_server_is_digital_signature_only(self, app, auth_client, create_ca):
        ca = create_ca(cn='Issue327 UI CA')
        cid = self._issue(auth_client, ca['id'], 'ec-server.test',
                          key_type='ecdsa', key_size=256, cert_type='server')
        cert = _issued_cert(app, cid)
        assert isinstance(cert.public_key(), ec.EllipticCurvePublicKey)
        assert _ku(cert) == {'digital_signature'}
        assert _eku(cert) == {ExtendedKeyUsageOID.SERVER_AUTH}

    def test_rsa_server_keeps_key_encipherment(self, app, auth_client, create_ca):
        ca = create_ca(cn='Issue327 UI RSA CA')
        cid = self._issue(auth_client, ca['id'], 'rsa-server.test',
                          key_type='rsa', key_size=2048, cert_type='server')
        assert _ku(_issued_cert(app, cid)) == {'digital_signature', 'key_encipherment'}

    def test_ec_combined_is_digital_signature_only(self, app, auth_client, create_ca):
        ca = create_ca(cn='Issue327 UI combined CA')
        cid = self._issue(auth_client, ca['id'], 'ec-combined.test',
                          key_type='ecdsa', key_size=384, cert_type='combined')
        assert _ku(_issued_cert(app, cid)) == {'digital_signature'}

    def test_ec_email_gets_key_agreement(self, app, auth_client, create_ca):
        ca = create_ca(cn='Issue327 UI email CA')
        cid = self._issue(auth_client, ca['id'], 'someone@ec-mail.test',
                          key_type='ecdsa', key_size=256, cert_type='email')
        cert = _issued_cert(app, cid)
        assert _ku(cert) == {'digital_signature', 'content_commitment', 'key_agreement'}
        assert _eku(cert) == {ExtendedKeyUsageOID.EMAIL_PROTECTION}

    def test_template_key_encipherment_dropped_on_ec_key(self, app, auth_client, create_ca):
        ca = create_ca(cn='Issue327 UI tpl CA')
        r = auth_client.post('/api/v2/templates', data=json.dumps({
            'name': 'issue327-ec-tls', 'template_type': 'custom',
            'key_type': 'EC-P256', 'validity_days': 90, 'digest': 'sha256',
            'extensions_template': {
                'key_usage': ['digitalSignature', 'keyEncipherment'],
                'extended_key_usage': ['serverAuth'],
            }}), content_type=CONTENT_JSON)
        assert r.status_code in (200, 201), r.data
        tpl = get_json(r)
        tpl = tpl.get('data', tpl)
        cid = self._issue(auth_client, ca['id'], 'tpl-ec.test', template_id=tpl['id'])
        cert = _issued_cert(app, cid)
        assert isinstance(cert.public_key(), ec.EllipticCurvePublicKey)
        assert _ku(cert) == {'digital_signature'}


class TestSignCsr:
    """CertificateService.sign_csr as ACME, EST, WSTEP and Sign CSR use it."""

    @staticmethod
    def _sign(app, ca, csr, cert_type='server_cert'):
        from services.cert_service import CertificateService
        with app.app_context():
            ca_row = db.session.get(CA, ca['id'])
            row = Certificate(
                refid=f'i327-{csr.subject.rfc4514_string()}',
                descr='issue 327', caref=ca_row.refid,
                csr=base64.b64encode(csr.public_bytes(serialization.Encoding.PEM)).decode(),
                cert_type=cert_type, source='acme', created_by='acme',
            )
            db.session.add(row)
            db.session.flush()
            signed = CertificateService.sign_csr(
                cert_id=row.id, caref=ca_row.refid, cert_type=cert_type,
                validity_days=90, digest='sha256', username='acme')
            db.session.commit()
            pem = base64.b64decode(signed.crt)
        return x509.load_pem_x509_certificate(pem, default_backend())

    def test_acme_shaped_ec_csr_without_key_usage(self, app, create_ca):
        """certbot --key-type ecdsa: no KeyUsage in the CSR, server_cert default."""
        ca = create_ca(cn='Issue327 ACME CA')
        key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        csr = _csr(key, 'acme-ec.test', [
            (x509.SubjectAlternativeName([x509.DNSName('acme-ec.test')]), False)])
        cert = self._sign(app, ca, csr)
        assert _ku(cert) == {'digital_signature'}
        assert _eku(cert) == {ExtendedKeyUsageOID.SERVER_AUTH}

    def test_rsa_csr_without_key_usage_unchanged(self, app, create_ca):
        ca = create_ca(cn='Issue327 ACME RSA CA')
        key = rsa.generate_private_key(65537, 2048, default_backend())
        cert = self._sign(app, ca, _csr(key, 'acme-rsa.test'))
        assert _ku(cert) == {'digital_signature', 'key_encipherment'}

    def test_ec_csr_requesting_key_encipherment_is_clamped(self, app, create_ca):
        ca = create_ca(cn='Issue327 CSR KU CA')
        key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        csr = _csr(key, 'csr-ku-ec.test', [
            (_usage(digital_signature=True, key_encipherment=True), True),
            (x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False)])
        cert = self._sign(app, ca, csr)
        assert _ku(cert) == {'digital_signature'}

    def test_ec_csr_key_agreement_kept(self, app, create_ca):
        ca = create_ca(cn='Issue327 CSR KA CA')
        key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        csr = _csr(key, 'csr-ka-ec.test', [
            (_usage(digital_signature=True, key_agreement=True), True)])
        cert = self._sign(app, ca, csr)
        assert _ku(cert) == {'digital_signature', 'key_agreement'}

    def test_ec_smime_csr_gets_key_agreement(self, app, create_ca):
        ca = create_ca(cn='Issue327 CSR SMIME CA')
        key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        csr = _csr(key, 'csr-smime-ec.test', [
            (_usage(digital_signature=True, key_encipherment=True), True),
            (x509.ExtendedKeyUsage([ExtendedKeyUsageOID.EMAIL_PROTECTION]), False)])
        cert = self._sign(app, ca, csr, cert_type='email_cert')
        assert _ku(cert) == {'digital_signature', 'key_agreement'}


class TestApprovalPath:
    def test_ec_key_from_request_is_digital_signature_only(self, app, create_ca):
        from tests.test_approval_template_issuance import _issue_from_request, _mk_template
        ca = create_ca(cn='Issue327 approval CA')
        tpl_id = _mk_template(app)  # RSA-4096 template asking DS + keyEncipherment
        cert, _ = _issue_from_request(app, create_ca, {
            'cn': 'appr-ec.test', 'ca_id': ca['id'], 'cert_type': 'server',
            'template_id': tpl_id, 'key_type': 'ecdsa', 'key_size': '256',
        })
        assert isinstance(cert.public_key(), ec.EllipticCurvePublicKey)
        assert _ku(cert) == {'digital_signature'}


class TestCreateCertificate:
    def test_low_level_ec_server_cert(self, app, create_ca):
        from services.trust_store import TrustStoreService
        ca = create_ca(cn='Issue327 low-level CA')
        with app.app_context():
            _, ca_cert, ca_key = _load_ca_material(ca['id'])
            cert_pem, _key = TrustStoreService.create_certificate(
                x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'low.test')]),
                ca_cert, ca_key, cert_type='server_cert', validity_days=30,
                key_type='secp256r1')
        cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
        assert isinstance(cert.public_key(), ec.EllipticCurvePublicKey)
        assert _ku(cert) == {'digital_signature'}
        assert _eku(cert) == {ExtendedKeyUsageOID.SERVER_AUTH}

    def test_low_level_rsa_client_cert_unchanged(self, app, create_ca):
        from services.trust_store import TrustStoreService
        ca = create_ca(cn='Issue327 low-level RSA CA')
        with app.app_context():
            _, ca_cert, ca_key = _load_ca_material(ca['id'])
            cert_pem, _key = TrustStoreService.create_certificate(
                x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'low-rsa.test')]),
                ca_cert, ca_key, cert_type='client_cert', validity_days=30,
                key_type='2048')
        cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
        assert _ku(cert) == {'digital_signature', 'content_commitment', 'key_encipherment'}
        assert _eku(cert) == {ExtendedKeyUsageOID.CLIENT_AUTH}


class TestScep:
    def test_ec_enrollee_key_usage_from_csr_is_clamped(self, app, create_ca):
        from models import SCEPRequest
        from services.scep.scep_service import SCEPService
        ca = create_ca(cn='Issue327 SCEP CA')
        with app.app_context():
            ca_obj = db.session.get(CA, ca['id'])
            svc = SCEPService(ca_refid=ca_obj.refid, auto_approve=True)
            key = ec.generate_private_key(ec.SECP256R1(), default_backend())
            csr = _csr(key, 'scep-ec.test', [
                (_usage(digital_signature=True, key_encipherment=True), True),
                (x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), False)])
            scep_req = SCEPRequest(
                transaction_id='issue327-ec-txn', ca_refid=ca_obj.refid,
                csr=base64.b64encode(csr.public_bytes(serialization.Encoding.DER)).decode(),
                status='pending', subject='CN=scep-ec.test')
            db.session.add(scep_req)
            db.session.flush()
            refid = svc._auto_approve_request(scep_req, csr)
            db.session.commit()
            row = Certificate.query.filter_by(refid=refid).first()
            pem = base64.b64decode(row.crt)
        cert = x509.load_pem_x509_certificate(pem, default_backend())
        assert _ku(cert) == {'digital_signature'}
        assert _eku(cert) == {ExtendedKeyUsageOID.CLIENT_AUTH}
