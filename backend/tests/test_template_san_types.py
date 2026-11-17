"""A template's SAN types bind the requests made with it when it enforces them.

``extensions_template.san_types`` was offered on the template form and
never read at issuance. An empty or absent list still allows every type;
templates older than the switch, and the built-in ones, enforce nothing.
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


def _template(app, san_types, name=None, enforce=True):
    with app.app_context():
        tpl = CertificateTemplate(
            name=name or f'san-types-{uuid.uuid4().hex[:8]}', template_type='custom',
            key_type='RSA-2048', validity_days=30, digest='sha256',
            dn_template=json.dumps({'CN': '{cn}'}),
            extensions_template=json.dumps({'key_usage': ['digitalSignature'],
                                            'extended_key_usage': ['serverAuth', 'clientAuth'],
                                            'san_types': san_types}),
            enforce_san_types=enforce)
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

    def make(san_types, enforce=True):
        made.append(_template(app, san_types, enforce=enforce))
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


class TestEnforcementSwitch:
    def test_a_template_that_does_not_enforce_refuses_nothing(self, app, auth_client, create_ca,
                                                             make_template):
        tpl_id = make_template(['dns'], enforce=False)
        ca = create_ca(cn='SAN types not enforced CA')
        r = auth_client.post('/api/v2/certificates', json={
            'cn': 'loose.san.test', 'ca_id': ca['id'], 'template_id': tpl_id,
            'san_dns': ['loose.san.test'], 'san_email': ['ops@example.com']})
        assert r.status_code in (200, 201), r.get_json()

    def test_a_new_template_enforces_and_the_switch_turns_it_off(self, app, auth_client, create_ca):
        r = auth_client.post('/api/v2/templates', json={
            'name': f'new-san-{uuid.uuid4().hex[:8]}', 'template_type': 'custom',
            'extensions_template': {'key_usage': ['digitalSignature'],
                                    'extended_key_usage': ['serverAuth'], 'san_types': ['dns']}})
        assert r.status_code == 201, r.get_json()
        tpl = r.get_json()['data']
        assert tpl['enforce_san_types'] is True
        ca = create_ca(cn='SAN types switch CA')
        body = {'cn': 'switch.san.test', 'ca_id': ca['id'], 'template_id': tpl['id'],
                'san_dns': ['switch.san.test'], 'san_ip': ['192.0.2.4']}
        try:
            assert auth_client.post('/api/v2/certificates', json=body).status_code == 400
            r = auth_client.put(f"/api/v2/templates/{tpl['id']}", json={'enforce_san_types': False})
            assert r.status_code == 200 and r.get_json()['data']['enforce_san_types'] is False
            assert auth_client.post('/api/v2/certificates', json=body).status_code in (200, 201)
        finally:
            from tests.test_acme_profile_template import _drop_template
            _drop_template(app, tpl['id'])

    def test_an_imported_template_without_the_switch_enforces_nothing(self, app, auth_client):
        name = f'imported-san-{uuid.uuid4().hex[:8]}'
        r = auth_client.post('/api/v2/templates/import', data={'json_content': json.dumps({
            'name': name, 'template_type': 'custom',
            'extensions_template': {'key_usage': ['digitalSignature'], 'san_types': ['dns']}})})
        assert r.status_code in (200, 201), r.get_json()
        with app.app_context():
            tpl = CertificateTemplate.query.filter_by(name=name).one()
            assert tpl.enforce_san_types is False
            tid = tpl.id
        from tests.test_acme_profile_template import _drop_template
        _drop_template(app, tid)

    def test_built_in_templates_enforce_nothing_and_allow_their_real_names(self, app):
        from services.template_service import TemplateService
        by_name = {t['name']: t for t in TemplateService.SYSTEM_TEMPLATES}
        assert not any(t.get('enforce_san_types', False) for t in by_name.values())
        types = {name: json.loads(t['extensions_template'])['san_types'] for name, t in by_name.items()}
        assert set(types['Client Authentication']) == {'dns', 'email', 'upn'}
        assert set(types['VPN Client']) == {'dns', 'email', 'upn'}
        assert set(types['Smartcard Logon']) == {'upn', 'email'}


class TestWindowsShapedRequests:
    """Windows/Intune CSRs carry CA:FALSE with a path length, which the raw
    cryptography accessor refuses: the SAN type check reads them as the rest does."""

    @staticmethod
    def _csr(cn):
        from cryptography.hazmat.primitives.asymmetric import rsa
        from tests.test_csr_windows_basic_constraints import _windows_shaped_csr
        return _windows_shaped_csr(rsa.generate_private_key(public_exponent=65537, key_size=2048), cn)

    @pytest.mark.parametrize('enforce, allowed, refused', [
        (False, ['email'], False), (True, ['dns'], False), (True, ['email'], True)])
    def test_scep(self, app, make_template, enforce, allowed, refused):
        from services.scep.scep_service import SCEPService
        tpl_id = make_template(allowed, enforce=enforce)
        with app.app_context():
            svc = SimpleNamespace(template=db.session.get(CertificateTemplate, tpl_id))
            violations = SCEPService._san_type_violations(svc, self._csr('win.san.test'))
        assert bool(violations) is refused

    def test_sign_csr_check(self, app, make_template):
        from api.v2.csrs import _san_type_refusal
        csr = self._csr('win-csr.san.test')
        row = SimpleNamespace(csr=csr.public_bytes(serialization.Encoding.PEM).decode())
        with app.app_context():
            assert 'DNS' in _san_type_refusal(row, make_template(['email']))
            assert _san_type_refusal(row, make_template(['dns'])) is None


def test_an_override_san_alone_is_checked(app, create_ca, make_template):
    """WSTEP's AD-derived names replace a naked request's: they are what the template binds."""
    from services.ca_service import CAService
    from utils.upn_san import build_upn_other_name
    ca = create_ca(cn='SAN types override CA')
    naked = x509.CertificateSigningRequestBuilder().subject_name(x509.Name([])).sign(
        ec.generate_private_key(ec.SECP256R1()), hashes.SHA256())
    override = dict(override_subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Jane Doe')]),
                    override_san=[build_upn_other_name('jane@example.com')])
    with app.app_context():
        signing_ca = db.session.get(CA, ca['id'])
        pem, _ = CAService.sign_csr_from_crypto(ca=signing_ca, csr=naked,
                                                policy_template_id=make_template(['upn']), **override)
        assert pem
        with pytest.raises(PolicyViolation, match='UPN'):
            CAService.sign_csr_from_crypto(ca=signing_ca, csr=naked,
                                           policy_template_id=make_template(['dns']), **override)
