"""A template's SAN types bind the requests made with it.

``extensions_template.san_types`` was offered on the template form and
never read at issuance. An empty or absent list still allows every type.
"""
import base64
import json
import uuid
from types import SimpleNamespace

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from models import CA, Certificate, CertificateTemplate, db
from services.policy_service import PolicyViolation
from tests.test_csr_sign_extra_names import _csr, _upload


def _template(app, san_types, name=None):
    with app.app_context():
        tpl = CertificateTemplate(
            name=name or f'san-types-{uuid.uuid4().hex[:8]}', template_type='custom',
            key_type='RSA-2048', validity_days=30, digest='sha256',
            dn_template=json.dumps({'CN': '{cn}'}),
            extensions_template=json.dumps({'key_usage': ['digitalSignature'],
                                            'extended_key_usage': ['serverAuth', 'clientAuth'],
                                            'san_types': san_types}))
        db.session.add(tpl)
        db.session.commit()
        return tpl.id


def _set_types(app, tpl_id, san_types):
    with app.app_context():
        tpl = db.session.get(CertificateTemplate, tpl_id)
        ext = json.loads(tpl.extensions_template)
        ext['san_types'] = san_types
        tpl.extensions_template = json.dumps(ext)
        db.session.commit()


@pytest.fixture
def make_template(app):
    made = []

    def make(san_types):
        made.append(_template(app, san_types))
        return made[-1]
    yield make
    from tests.test_acme_profile_template import _drop_template
    for tpl_id in made:
        _drop_template(app, tpl_id)


@pytest.fixture
def dns_only(make_template):
    return make_template(['dns'])


def _count(app, model):
    with app.app_context():
        return db.session.query(model).count()


class TestIssueForm:
    def test_a_refused_type_is_named_and_nothing_is_issued(self, app, auth_client, create_ca, dns_only):
        ca = create_ca(cn='SAN types form CA')
        before = _count(app, Certificate)
        r = auth_client.post('/api/v2/certificates', json={
            'cn': 'form.san.test', 'ca_id': ca['id'], 'template_id': dns_only,
            'san_dns': ['form.san.test'], 'san_email': ['ops@example.com']})
        assert r.status_code == 400
        assert 'email' in r.get_json()['message']
        assert _count(app, Certificate) == before

    def test_allowed_types_issue(self, app, auth_client, create_ca, dns_only):
        ca = create_ca(cn='SAN types form ok CA')
        r = auth_client.post('/api/v2/certificates', json={
            'cn': 'form-ok.san.test', 'ca_id': ca['id'], 'template_id': dns_only,
            'san_dns': ['form-ok.san.test']})
        assert r.status_code in (200, 201), r.get_json()

    def test_a_cn_implied_name_of_another_type_is_left_out(self, app, auth_client, create_ca, make_template):
        tpl_id = make_template(['dns'])
        ca = create_ca(cn='SAN types implicit CA')
        r = auth_client.post('/api/v2/certificates', json={
            'cn': '192.0.2.7', 'ca_id': ca['id'], 'template_id': tpl_id,
            'san_dns': ['implicit.san.test']})
        assert r.status_code in (200, 201), r.get_json()
        with app.app_context():
            row = db.session.get(Certificate, r.get_json()['data']['id'])
            cert = x509.load_pem_x509_certificate(base64.b64decode(row.crt))
        names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        assert not names.get_values_for_type(x509.IPAddress)

    def test_no_types_allows_every_type(self, app, auth_client, create_ca, make_template):
        tpl_id = make_template([])
        ca = create_ca(cn='SAN types open CA')
        r = auth_client.post('/api/v2/certificates', json={
            'cn': 'open.san.test', 'ca_id': ca['id'], 'template_id': tpl_id,
            'san_dns': ['open.san.test'], 'san_email': ['ops@example.com'],
            'san_uri': ['https://example.com/']})
        assert r.status_code in (200, 201), r.get_json()


class TestSignCsr:
    def test_a_refused_type_in_the_request_is_refused_before_signing(self, app, auth_client, create_ca,
                                                                     dns_only):
        ca = create_ca(cn='SAN types CSR CA')
        csr_id = _upload(auth_client, _csr('csr.san.test', [
            x509.DNSName('csr.san.test'), x509.UniformResourceIdentifier('https://example.com/')]))
        r = auth_client.post(f'/api/v2/csrs/{csr_id}/sign', json={
            'ca_id': ca['id'], 'validity_days': 30, 'template_id': dns_only})
        assert r.status_code == 400
        assert 'URI' in r.get_json()['message']
        r = auth_client.post('/api/v2/csrs/bulk/sign', json={
            'ids': [csr_id], 'ca_id': ca['id'], 'validity_days': 30, 'template_id': dns_only})
        assert 'URI' in r.get_json()['data']['failed'][0]['error']
        with app.app_context():
            assert db.session.get(Certificate, csr_id).crt is None

    def test_a_name_added_at_signing_is_checked_too(self, app, auth_client, create_ca, dns_only):
        ca = create_ca(cn='SAN types CSR extra CA')
        csr_id = _upload(auth_client, _csr('extra.san.test', [x509.DNSName('extra.san.test')]))
        r = auth_client.post(f'/api/v2/csrs/{csr_id}/sign', json={
            'ca_id': ca['id'], 'validity_days': 30, 'template_id': dns_only,
            'san_ip': ['192.0.2.9']})
        assert r.status_code == 400
        assert 'IP' in r.get_json()['message']

    def test_the_signing_trunk_refuses_on_its_own(self, app, create_ca, dns_only):
        """Every path that reaches CertificateService.sign_csr with a template is bound."""
        from services.cert_service import CertificateService
        ca = create_ca(cn='SAN types trunk CA')
        key = ec.generate_private_key(ec.SECP256R1())
        csr = x509.CertificateSigningRequestBuilder().subject_name(
            x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'trunk.san.test')])).add_extension(
            x509.SubjectAlternativeName([x509.RFC822Name('a@example.com')]), critical=False
        ).sign(key, hashes.SHA256())
        with app.app_context():
            row = Certificate(refid=uuid.uuid4().hex, descr='trunk', caref=db.session.get(CA, ca['id']).refid,
                              csr=base64.b64encode(csr.public_bytes(serialization.Encoding.PEM)).decode())
            db.session.add(row)
            db.session.commit()
            with pytest.raises(PolicyViolation, match='email'):
                CertificateService.sign_csr(cert_id=row.id, caref=row.caref, template_id=dns_only)
            with pytest.raises(PolicyViolation, match='email'):
                CertificateService.sign_csr(cert_id=row.id, caref=row.caref,
                                            policy_template_id=dns_only)
            db.session.delete(row)
            db.session.commit()


class TestProtocols:
    def test_acme_finalize_refuses_a_dns_order_for_an_email_only_template(self, app, monkeypatch,
                                                                         create_ca, make_template):
        from tests.test_acme_profile_template import (TestFinalizeWithBoundTemplate, _clear_profiles,
                                                      _install_profiles)
        tpl_id = make_template(['email'])
        _install_profiles(app, {'mail': {'validity_days': 30, 'template_id': tpl_id}})
        try:
            # Refused at the order check, before a certificate row exists to sign
            with pytest.raises(AssertionError, match=r"^Template '[^']+' does not allow DNS"):
                TestFinalizeWithBoundTemplate()._finalize(app, monkeypatch, create_ca, 'mail')
        finally:
            _clear_profiles(app)

    def test_scep_profile_template_refuses_the_csr_types(self, app, dns_only):
        from services.scep.scep_service import SCEPService
        csr = _csr('scep.san.test', [x509.RFC822Name('a@example.com')])
        with app.app_context():
            tpl = db.session.get(CertificateTemplate, dns_only)
            svc = SimpleNamespace(template=tpl)
            assert 'email' in SCEPService._san_type_violations(svc, csr)[0]
            assert SCEPService._san_type_violations(
                svc, _csr('scep.san.test', [x509.DNSName('scep.san.test')])) == []

    def test_wstep_matched_template_binds_the_names(self, app, create_ca, dns_only):
        from services.ca_service import CAService
        from utils.upn_san import build_upn_other_name
        ca = create_ca(cn='SAN types WSTEP CA')
        csr = _csr('wstep.san.test', [build_upn_other_name('user@example.com')])
        with app.app_context():
            with pytest.raises(PolicyViolation, match='UPN'):
                CAService.sign_csr_from_crypto(ca=db.session.get(CA, ca['id']), csr=csr,
                                               policy_template_id=dns_only)


class TestRenewalAndApproval:
    def test_renewal_refuses_names_the_template_no_longer_allows(self, app, auth_client, create_ca, make_template):
        tpl_id = make_template(['dns'])
        ca = create_ca(cn='SAN types renew CA')
        r = auth_client.post('/api/v2/certificates', json={
            'cn': 'renew.san.test', 'ca_id': ca['id'], 'template_id': tpl_id,
            'san_dns': ['renew.san.test']})
        assert r.status_code in (200, 201), r.get_json()
        cert_id = r.get_json()['data']['id']
        _set_types(app, tpl_id, ['email'])
        with app.app_context():
            serial = db.session.get(Certificate, cert_id).serial_number
        r = auth_client.post(f'/api/v2/certificates/{cert_id}/renew', json={})
        assert r.status_code == 400
        assert 'DNS' in r.get_json()['message']
        with app.app_context():
            assert db.session.get(Certificate, cert_id).serial_number == serial

    def test_approval_refuses_a_type_the_template_refuses(self, app, create_ca, dns_only):
        from api.v2.policies import _issue_approved_certificate
        from models import ApprovalRequest
        from tests.test_approval_template_issuance import _mk_approval_id, _requester_id
        ca = create_ca(cn='SAN types approval CA')
        approval_id = _mk_approval_id(app, _requester_id(app), {
            'cn': 'approval.san.test', 'ca_id': ca['id'], 'template_id': dns_only,
            'san_dns': ['approval.san.test'], 'san_email': ['a@example.com']})
        with app.app_context():
            with pytest.raises(PolicyViolation, match='email'):
                _issue_approved_certificate(db.session.get(ApprovalRequest, approval_id))


class TestNothingQueuedForApproval:
    """A refused type never reaches the approval queue (operator under an approval policy)."""

    def test_form_and_csr_signing(self, app, create_ca, create_user, dns_only):
        from models.policy import ApprovalRequest
        from tests.test_approval_on_sign_and_renew import _drop_policy, _operator, _policy
        ca = create_ca(cn='SAN types approval gate CA')
        pid = _policy(app, ca['id'], 'san-types-gate')
        operator = _operator(app, create_user)
        try:
            r = operator.post('/api/v2/certificates', json={
                'cn': 'gate.san.test', 'ca_id': ca['id'], 'template_id': dns_only,
                'san_email': ['a@example.com']})
            assert r.status_code == 400, r.get_json()
            csr_id = _upload(operator, _csr('gate-csr.san.test', [x509.RFC822Name('a@example.com')]))
            r = operator.post(f'/api/v2/csrs/{csr_id}/sign', json={
                'ca_id': ca['id'], 'validity_days': 30, 'template_id': dns_only})
            assert r.status_code == 400, r.get_json()
            r = operator.post('/api/v2/csrs/bulk/sign', json={
                'ids': [csr_id], 'ca_id': ca['id'], 'validity_days': 30, 'template_id': dns_only})
            assert not r.get_json()['data'].get('pending_approval')
            with app.app_context():
                assert ApprovalRequest.query.filter_by(policy_id=pid).count() == 0
        finally:
            _drop_policy(app, pid)

    def test_renewal(self, app, auth_client, create_ca, create_user, make_template):
        from models.policy import ApprovalRequest
        from tests.test_approval_on_sign_and_renew import _drop_policy, _operator, _policy
        tpl_id = make_template(['dns'])
        ca = create_ca(cn='SAN types renew gate CA')
        r = auth_client.post('/api/v2/certificates', json={
            'cn': 'renew-gate.san.test', 'ca_id': ca['id'], 'template_id': tpl_id,
            'san_dns': ['renew-gate.san.test']})
        cert_id = r.get_json()['data']['id']
        _set_types(app, tpl_id, ['email'])
        pid = _policy(app, ca['id'], 'san-types-renew-gate')
        try:
            r = _operator(app, create_user).post(f'/api/v2/certificates/{cert_id}/renew', json={})
            assert r.status_code == 400, r.get_json()
            with app.app_context():
                assert ApprovalRequest.query.filter_by(policy_id=pid).count() == 0
        finally:
            _drop_policy(app, pid)
