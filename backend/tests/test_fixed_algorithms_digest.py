"""Digest of the paths where nobody picks one (#397 follow-up): the bound
template's, else the CA key's, bounded by the issuance policies."""
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from models import CA, Certificate, db
from models.certificate_template import CertificateTemplate
from models.policy import CertificatePolicy
from services.policy_service import PolicyEvaluationService
from tests.test_policy_algorithms_397 import _csr, _drop, _pol, _policy, _signed, _store_csr
from utils import issuance_defaults


def _ec384_ca(create_ca, cn):
    return create_ca(cn=cn, keyAlgo='EC-P384', keyType='EC-P384', keySize='secp384r1',
                     hashAlgorithm='sha384')


def _template(app, name, digest):
    with app.app_context():
        row = CertificateTemplate(name=name, template_type='server', key_type='RSA-2048',
                                  digest=digest, validity_days=30, is_active=True,
                                  extensions_template='{}')
        db.session.add(row)
        db.session.commit()
        return row.id


class TestRule:

    @pytest.mark.parametrize('curve,digest', [
        (ec.SECP256R1, 'sha256'), (ec.SECP384R1, 'sha384'), (ec.SECP521R1, 'sha512'),
        (ec.BrainpoolP384R1, 'sha384')])
    def test_ca_key_digest_follows_the_curve(self, curve, digest):
        key = ec.generate_private_key(curve())
        assert issuance_defaults.digest_for_key(key) == digest
        assert issuance_defaults.digest_for_key(key.public_key()) == digest

    def test_a_policy_refusing_the_default_keeps_its_strength(self):
        weak = _pol({'allowed_digests': ['sha256', 'sha384']})
        assert PolicyEvaluationService.choose_digest([weak], 'sha512') == 'sha384'
        assert PolicyEvaluationService.choose_digest([weak], 'sha256') == 'sha256'

    def test_an_implicit_request_without_digest_takes_the_curve_one(self):
        key = ec.generate_private_key(ec.SECP384R1())
        sign_hash, v = PolicyEvaluationService.checked_signing_hash([], key, None, explicit=False)
        assert sign_hash.name == 'sha384' and v == []

    def test_a_weaker_template_digest_does_not_lower_the_ca_key(self):
        key = ec.generate_private_key(ec.SECP384R1())
        tpl = CertificateTemplate(digest='sha256')
        assert issuance_defaults.template_digest(tpl, key) is None
        tpl.digest = 'sha512'
        assert issuance_defaults.template_digest(tpl, key) == 'sha512'
        assert issuance_defaults.template_digest(None, key) is None


class TestPaths:

    def test_est_bridge_signs_with_the_ca_curve_digest(self, app, create_ca):
        from services.ca_service import CAService
        ca = _ec384_ca(create_ca, 'Fixed EST P-384 CA')
        with app.app_context():
            pem, _ = CAService.sign_csr_from_crypto(
                ca=db.session.get(CA, ca['id']), csr=_csr(), validity_days=30, source='est')
        cert = x509.load_pem_x509_certificate(pem.encode())
        assert isinstance(cert.signature_hash_algorithm, hashes.SHA384)

    def test_wstep_template_digest_is_used(self, app, create_ca):
        from services.ca_service import CAService
        ca = create_ca(cn='Fixed WSTEP CA')
        tid = _template(app, 'fixed-wstep-sha512', 'sha512')
        try:
            with app.app_context():
                pem, _ = CAService.sign_csr_from_crypto(
                    ca=db.session.get(CA, ca['id']), csr=_csr(cn='wstep.fixed.test'),
                    validity_days=30, source='wstep', policy_template_id=tid)
            cert = x509.load_pem_x509_certificate(pem.encode())
            assert isinstance(cert.signature_hash_algorithm, hashes.SHA512)
        finally:
            _drop(app, CertificateTemplate, tid)

    def test_sign_csr_form_template_digest_is_used(self, app, create_ca):
        from services.cert_service import CertificateService
        ca = create_ca(cn='Fixed Sign CSR CA')
        tid = _template(app, 'fixed-sign-sha384', 'sha384')
        cert_id = _store_csr(app, _csr(cn='sign.fixed.test'))
        try:
            with app.app_context():
                CertificateService.sign_csr(cert_id=cert_id, caref=db.session.get(CA, ca['id']).refid,
                                            validity_days=30, policy_template_id=tid)
                db.session.commit()
            assert isinstance(_signed(app, cert_id).signature_hash_algorithm, hashes.SHA384)
        finally:
            _drop(app, Certificate, cert_id)
            _drop(app, CertificateTemplate, tid)

    def test_a_template_sha256_yields_to_a_policy_on_every_protocol_path(self, app, create_ca):
        # RSA CA, policy [sha384, sha512], template left at SHA-256: a preference, not a refusal
        from services.ca_service import CAService
        from services.cert_service import CertificateService
        from services.scep.scep_service import SCEPService
        ca = create_ca(cn='Fixed yield CA')
        tid = _template(app, 'fixed-yield-sha256', 'sha256')
        pid = _policy(app, 'fixed-strong-only', ca['id'], {'allowed_digests': ['sha384', 'sha512']})
        cert_id = _store_csr(app, _csr(cn='yield-sign.fixed.test'))
        try:
            with app.app_context():
                row = db.session.get(CA, ca['id'])
                svc = SCEPService(row.refid, template=db.session.get(CertificateTemplate, tid))
                sign_hash, v = svc._policy_signing_hash(_csr(cn='yield-scep.fixed.test'))
                assert sign_hash.name == 'sha384' and v == []
                pem, _ = CAService.sign_csr_from_crypto(
                    ca=row, csr=_csr(cn='yield-wstep.fixed.test'), validity_days=30,
                    source='wstep', policy_template_id=tid)
                assert isinstance(x509.load_pem_x509_certificate(pem.encode()).signature_hash_algorithm,
                                  hashes.SHA384)
                CertificateService.sign_csr(cert_id=cert_id, caref=row.refid, validity_days=30,
                                            policy_template_id=tid)
                db.session.commit()
            assert isinstance(_signed(app, cert_id).signature_hash_algorithm, hashes.SHA384)
        finally:
            _drop(app, CertificatePolicy, pid)
            _drop(app, Certificate, cert_id)
            _drop(app, CertificateTemplate, tid)

    def test_issue_form_template_digest_is_floored_at_the_ca_key(self, app, auth_client, create_ca):
        import json
        from tests.conftest import get_json
        ca = _ec384_ca(create_ca, 'Fixed issue form P-384 CA')
        tid = _template(app, 'fixed-issue-sha256', 'sha256')
        cert_id = None
        try:
            r = auth_client.post('/api/v2/certificates', content_type='application/json', data=json.dumps({
                'cn': 'issue.fixed.test', 'ca_id': ca['id'], 'key_type': 'rsa', 'key_size': 2048,
                'validity_days': 30, 'template_id': tid}))
            assert r.status_code in (200, 201), r.data
            cert_id = get_json(r)['data']['id']
            assert isinstance(_signed(app, cert_id).signature_hash_algorithm, hashes.SHA384)
        finally:
            if cert_id:
                _drop(app, Certificate, cert_id)
            _drop(app, CertificateTemplate, tid)

    def test_acme_finalize_without_configured_digest_takes_the_ca_curve_digest(
            self, app, monkeypatch, create_ca):
        from tests.test_acme_profile_template import TestFinalizeWithBoundTemplate
        cert, _, _ = TestFinalizeWithBoundTemplate()._finalize(
            app, monkeypatch, lambda cn: _ec384_ca(create_ca, cn), None)
        assert isinstance(cert.signature_hash_algorithm, hashes.SHA384)

    def test_scep_profile_template_digest_is_used(self, app, create_ca):
        from services.scep.scep_service import SCEPService
        ca = create_ca(cn='Fixed SCEP CA')
        tid = _template(app, 'fixed-scep-sha512', 'sha512')
        try:
            with app.app_context():
                svc = SCEPService(db.session.get(CA, ca['id']).refid,
                                  template=db.session.get(CertificateTemplate, tid))
                sign_hash, v = svc._policy_signing_hash(_csr(cn='scep.fixed.test'))
                assert sign_hash.name == 'sha512' and v == []
        finally:
            _drop(app, CertificateTemplate, tid)

    def test_tsa_signer_of_a_p384_ca_signed_with_sha256_takes_sha384(self, app, auth_client, create_ca):
        import base64
        import json
        from models import SystemConfig
        ca = create_ca(cn='Fixed TSA P-384 CA', keyAlgo='EC-P384', keyType='EC-P384',
                       keySize='secp384r1', hashAlgorithm='sha256')
        try:
            r = auth_client.post('/api/v2/tsa/signer-certificate', content_type='application/json',
                                 data=json.dumps({'ca_id': ca['id'], 'cn': 'fixed-tsa-signer'}))
            assert r.status_code == 200, r.data
            pem = json.loads(r.data)['data']['certificate']['pem']
            data = pem.encode() if '-----BEGIN' in pem else base64.b64decode(pem)
            assert isinstance(x509.load_pem_x509_certificate(data).signature_hash_algorithm, hashes.SHA384)
        finally:
            with app.app_context():
                SystemConfig.query.filter(SystemConfig.key.in_(
                    ['tsa_enabled', 'tsa_signer_cert_refid'])).delete(synchronize_session=False)
                db.session.commit()

    def test_crl_of_a_p384_ca_defaults_to_sha384(self, app, create_ca):
        ca = _ec384_ca(create_ca, 'Fixed CRL P-384 CA')
        with app.app_context():
            assert db.session.get(CA, ca['id']).effective_crl_digest() == 'sha384'


def _hash_of(obj):
    return obj.signature_hash_algorithm.name


class TestFallbacks:
    """Where no digest is named, a P-384 key signs with SHA-384, never a literal SHA-256 (#397)."""

    def test_issue_without_digest_or_template(self, app, create_ca):
        from services.cert_service import CertificateService
        ca = _ec384_ca(create_ca, 'Fallback lifecycle P-384 CA')
        with app.app_context():
            row = CertificateService.create_certificate(
                descr='fallback', caref=db.session.get(CA, ca['id']).refid,
                dn={'CN': 'fallback-lifecycle.test'}, validity_days=30)
            import base64
            cert = x509.load_pem_x509_certificate(base64.b64decode(row.crt))
            assert _hash_of(cert) == 'sha384'
            db.session.delete(row)
            db.session.commit()

    def test_internal_ca_without_digest(self, app, create_ca):
        import base64
        from services.ca_service import CAService
        parent = _ec384_ca(create_ca, 'Fallback CA creation parent')
        with app.app_context():
            parent_ref = db.session.get(CA, parent['id']).refid
            root = CAService.create_internal_ca(
                descr='fallback root', dn={'CN': 'Fallback P-384 root'}, key_type='secp384r1')
            child = CAService.create_internal_ca(
                descr='fallback child', dn={'CN': 'Fallback RSA child'}, caref=parent_ref)
            hashes_ = [_hash_of(x509.load_pem_x509_certificate(base64.b64decode(c.crt)))
                       for c in (root, child)]
            for c in (root, child):
                db.session.delete(c)
            db.session.commit()
        assert hashes_ == ['sha384', 'sha384']

    def test_trust_store_signers_without_digest(self):
        import datetime as dt
        from services.trust_store import TrustStoreService
        key = ec.generate_private_key(ec.SECP384R1())
        subject = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, 'Fallback TS CA')])
        pem, _ = TrustStoreService.create_ca_certificate(subject=subject, private_key=key)
        ca_cert = x509.load_pem_x509_certificate(pem)
        assert _hash_of(ca_cert) == 'sha384'
        crl = x509.load_pem_x509_crl(TrustStoreService.generate_crl(ca_cert, key, []))
        assert crl.signature_hash_algorithm.name == 'sha384'
        csr = x509.load_pem_x509_csr(TrustStoreService.generate_ca_csr(subject, key))
        assert csr.signature_hash_algorithm.name == 'sha384'
        csr_pem, _ = TrustStoreService.generate_csr(subject, key_type='secp384r1')
        assert x509.load_pem_x509_csr(csr_pem).signature_hash_algorithm.name == 'sha384'

    def test_stored_csr_without_digest(self, app):
        import base64
        from services.cert_service import CertificateService
        with app.app_context():
            row = CertificateService.generate_csr(
                descr='fallback csr', dn={'CN': 'fallback-csr.test'}, key_type='secp384r1')
            csr = x509.load_pem_x509_csr(base64.b64decode(row.csr))
            db.session.delete(row)
            db.session.commit()
        assert csr.signature_hash_algorithm.name == 'sha384'

    @pytest.mark.parametrize('key_label,expected', [
        ('EC-P384', '2.16.840.1.101.3.4.2.2'), ('EC-P521', '2.16.840.1.101.3.4.2.3'),
        ('RSA-3072', '2.16.840.1.101.3.4.2.1')])
    def test_xcep_template_without_digest_announces_the_key_hash(self, app, key_label, expected):
        from types import SimpleNamespace
        from services.xcep.policy_builder import _request_hash
        with app.app_context():
            assert _request_hash(SimpleNamespace(digest=None, name='t'), key_label)[0] == expected

    def test_xcep_template_without_key_or_digest_follows_the_default_key(self, app, monkeypatch):
        from types import SimpleNamespace
        from services.xcep.policy_builder import _request_hash
        monkeypatch.setattr(issuance_defaults, 'BASELINE_ISSUE_KEY', 'EC-P384')
        with app.app_context():
            assert _request_hash(SimpleNamespace(digest=None, name='t'))[0] == '2.16.840.1.101.3.4.2.2'
