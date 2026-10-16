"""Key type and digest policies (#397) through the real SCEP, WSTEP and
approval paths, not only through the helpers they call."""
import base64
import json
import uuid

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import AttributeOID, ExtendedKeyUsageOID, NameOID

from models import CA, Certificate, SCEPRequest, User, db
from models.ca_template_pin import CATemplatePin
from models.certificate_template import CertificateTemplate
from models.policy import ApprovalRequest, CertificatePolicy
from services.scep.scep_service import SCEPService
from services.policy_service import PolicyEvaluationService, PolicyViolation
from tests.test_scep_rfc8894_operations import (
    FAIL_INFO_OID, PKI_STATUS_OID, _build_request, _client_identity,
    _load_ca_material, _response_attributes,
)

CHALLENGE = 'policy paths horse battery'


def _rsa(bits):
    return rsa.generate_private_key(public_exponent=65537, key_size=bits)


def _policy(name, rules, ca_id=None, template_id=None, requires_approval=False):
    pol = CertificatePolicy(name=f'{name}-{uuid.uuid4().hex[:8]}', policy_type='issuance',
                            ca_id=ca_id, template_id=template_id,
                            requires_approval=requires_approval, min_approvers=1,
                            is_active=True, priority=100)
    pol.set_rules(rules)
    db.session.add(pol)
    db.session.commit()
    return pol.id


def _template(**over):
    data = {'name': f'algo-paths-{uuid.uuid4().hex[:8]}', 'template_type': 'custom',
            'key_type': 'RSA-2048', 'validity_days': 30, 'digest': 'sha256',
            'dn_template': json.dumps({'CN': '{cn}'}),
            'extensions_template': json.dumps({'key_usage': ['digitalSignature'],
                                               'extended_key_usage': ['clientAuth']}),
            'is_active': True, **over}
    tpl = CertificateTemplate(**data)
    db.session.add(tpl)
    db.session.commit()
    return tpl.id


def _cleanup(app, ca_id, policy_ids=(), template_ids=(), cert_ids=()):
    """Drop what a test created: approvals, policies, issued rows, SCEP
    requests and templates (pins go with their template)."""
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        for pid in policy_ids:
            for ap in ApprovalRequest.query.filter_by(policy_id=pid).all():
                db.session.delete(ap)
        db.session.flush()
        for pid in policy_ids:
            row = db.session.get(CertificatePolicy, pid)
            if row is not None:
                db.session.delete(row)
        if ca is not None:
            for row in SCEPRequest.query.filter_by(ca_refid=ca.refid).all():
                db.session.delete(row)
            for row in Certificate.query.filter_by(caref=ca.refid).all():
                db.session.delete(row)
        for cid in cert_ids:
            row = db.session.get(Certificate, cid)
            if row is not None:
                db.session.delete(row)
        db.session.flush()
        for tid in template_ids:
            row = db.session.get(CertificateTemplate, tid)
            if row is not None:
                db.session.delete(row)
        db.session.commit()


# ---------------------------------------------------------------- SCEP

def _scep_request(ca_cert, key, cn):
    identity_cert, _ = _client_identity(cn, key=key)
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(identity_cert.subject)
           .add_attribute(AttributeOID.CHALLENGE_PASSWORD, CHALLENGE.encode())
           .sign(key, hashes.SHA256()))
    return _build_request(ca_cert, identity_cert, key, 19,
                          csr.public_bytes(serialization.Encoding.DER), b'policy-nonce-16b')


class TestScepRequest:

    def test_disallowed_key_is_refused_before_anything_is_stored(self, app, create_ca):
        # Manual approval: without the check at request time the request
        # would be stored and left PENDING, refused only at approval
        ca_data = create_ca(cn='Algo SCEP request CA')
        with app.app_context():
            pid = _policy('algo-scep-req', {'allowed_key_types': ['RSA-3072']}, ca_id=ca_data['id'])
        try:
            with app.app_context():
                ca, ca_cert, _ = _load_ca_material(ca_data['id'])
                svc = SCEPService(ca.refid, challenge_password=CHALLENGE, auto_approve=False)
                response, status = svc.process_pkcs_req(
                    _scep_request(ca_cert, _rsa(2048), 'scep-weak.policy.test'), '127.0.0.1')
                attrs = _response_attributes(response)
                assert status == 200
                assert attrs[PKI_STATUS_OID] == '2'      # FAILURE
                assert attrs[FAIL_INFO_OID] == '2'       # badRequest
                assert SCEPRequest.query.filter_by(ca_refid=ca.refid).count() == 0

                svc = SCEPService(ca.refid, challenge_password=CHALLENGE, auto_approve=False)
                response, _ = svc.process_pkcs_req(
                    _scep_request(ca_cert, _rsa(3072), 'scep-ok.policy.test'), '127.0.0.1')
                assert _response_attributes(response)[PKI_STATUS_OID] == '3'   # PENDING
                assert SCEPRequest.query.filter_by(ca_refid=ca.refid).count() == 1
        finally:
            _cleanup(app, ca_data['id'], policy_ids=[pid])


# ---------------------------------------------------------------- WSTEP

def _wstep_csr(key, cn):
    return (x509.CertificateSigningRequestBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
            .sign(key, hashes.SHA256()))


class TestWstep:

    def test_policy_bound_to_the_matched_template_applies(self, app, create_ca):
        from services.wstep import wstep_service
        ca_data = create_ca(cn='Algo WSTEP template CA')
        with app.app_context():
            tid = _template()
            db.session.add(CATemplatePin(ca_id=ca_data['id'], template_id=tid))
            db.session.commit()
            # Bound to the template only: it reaches the signer through the match
            pid = _policy('algo-wstep-tpl', {'allowed_key_types': ['RSA-3072']}, template_id=tid)
        try:
            with app.app_context():
                ca = db.session.get(CA, ca_data['id'])
                assert wstep_service._match_template(
                    ca, _wstep_csr(_rsa(2048), 'probe.policy.test')).id == tid
                cert_pem, err = wstep_service.issue(
                    ca, _wstep_csr(_rsa(2048), 'wstep-weak.policy.test')
                    .public_bytes(serialization.Encoding.DER), validity_days=30)
                assert cert_pem is None
                assert err and err.startswith('Policy violation') and 'RSA-2048' in err

                cert_pem, err = wstep_service.issue(
                    ca, _wstep_csr(_rsa(3072), 'wstep-ok.policy.test')
                    .public_bytes(serialization.Encoding.DER), validity_days=30)
                assert err is None, err
                assert x509.load_pem_x509_certificate(cert_pem.encode()).public_key().key_size == 3072
        finally:
            _cleanup(app, ca_data['id'], policy_ids=[pid], template_ids=[tid])


# ------------------------------------------------------------- Approval

def _approval(request_data, request_type='certificate'):
    """A pending approval under its own rule-less policy, so that only the
    template-bound policy carries the rule under test."""
    gate = CertificatePolicy(name=f'algo-gate-{uuid.uuid4().hex[:8]}', policy_type='issuance',
                             requires_approval=True, min_approvers=1, is_active=False)
    db.session.add(gate)
    db.session.commit()
    requester = User.query.filter_by(role='admin').first() or User.query.first()
    approval = PolicyEvaluationService.create_approval_request(
        policy=gate, request_data=request_data, requester_id=requester.id,
        request_type=request_type)
    # As the approve route leaves it before issuing: a pending one would be
    # closed as moot by the signature itself
    approval.status = 'approved'
    db.session.commit()
    return approval.id, gate.id


def _stored_csr(key, cn):
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
           .add_extension(x509.SubjectAlternativeName([x509.DNSName(cn)]), critical=False)
           .sign(key, hashes.SHA256()))
    row = Certificate(refid=str(uuid.uuid4()), descr=cn, source='manual',
                      csr=base64.b64encode(csr.public_bytes(serialization.Encoding.PEM)).decode())
    db.session.add(row)
    db.session.commit()
    return row.id


class TestApproval:

    def test_signing_a_request_follows_the_template_policy(self, app, create_ca):
        from api.v2.policies import _issue_approved_certificate
        ca_data = create_ca(cn='Algo approval CSR CA')
        with app.app_context():
            tid = _template()
            pid = _policy('algo-appr-csr', {'allowed_key_types': ['RSA-3072']}, template_id=tid)
            weak_id = _stored_csr(_rsa(2048), 'appr-weak.policy.test')
            ok_id = _stored_csr(_rsa(3072), 'appr-ok.policy.test')
            base = {'ca_id': ca_data['id'], 'cert_type': 'server_cert',
                    'validity_days': 30, 'template_id': tid}
            weak_ap, gate_a = _approval({**base, 'csr_id': weak_id, 'cn': 'appr-weak.policy.test'}, 'csr')
            ok_ap, gate_b = _approval({**base, 'csr_id': ok_id, 'cn': 'appr-ok.policy.test'}, 'csr')
        try:
            with app.app_context():
                with pytest.raises(PolicyViolation, match='RSA-2048'):
                    _issue_approved_certificate(db.session.get(ApprovalRequest, weak_ap))
                db.session.rollback()
                assert not db.session.get(Certificate, weak_id).crt

                result = _issue_approved_certificate(db.session.get(ApprovalRequest, ok_ap))
                assert result['id'] == ok_id
                db.session.commit()
                assert db.session.get(Certificate, ok_id).crt
        finally:
            _cleanup(app, ca_data['id'], policy_ids=[pid, gate_a, gate_b],
                     template_ids=[tid], cert_ids=[weak_id, ok_id])

    def test_issuing_a_request_checks_the_template_digest(self, app, create_ca):
        from api.v2.policies import _issue_approved_certificate
        ca_data = create_ca(cn='Algo approval digest CA')
        with app.app_context():
            tid = _template(digest='sha256')
            pid = _policy('algo-appr-digest', {'allowed_digests': ['sha384']}, template_id=tid)
            ap_id, gate = _approval({'cn': 'appr-digest.policy.test', 'ca_id': ca_data['id'],
                                     'cert_type': 'server', 'template_id': tid})
        try:
            with app.app_context():
                with pytest.raises(PolicyViolation, match='SHA256'):
                    _issue_approved_certificate(db.session.get(ApprovalRequest, ap_id))
                db.session.rollback()
                assert Certificate.query.filter_by(
                    caref=db.session.get(CA, ca_data['id']).refid).count() == 0

                # The same request passes once the template digest is allowed
                db.session.get(CertificateTemplate, tid).digest = 'sha384'
                db.session.commit()
                result = _issue_approved_certificate(db.session.get(ApprovalRequest, ap_id))
                db.session.commit()
                row = db.session.get(Certificate, result['id'])
                cert = x509.load_pem_x509_certificate(base64.b64decode(row.crt))
                assert cert.signature_hash_algorithm.name == 'sha384'
        finally:
            _cleanup(app, ca_data['id'], policy_ids=[pid, gate], template_ids=[tid])
