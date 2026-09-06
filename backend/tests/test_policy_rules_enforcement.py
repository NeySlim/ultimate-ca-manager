"""Certificate policy Rules enforced at issuance (issue #335).

Allowed Key Types and Max SANs were stored but never checked, and Max
Validity applied only on the approval path. Both issuance paths now refuse a
request outside the rules (key type, DNS name count) and cap the validity,
for every role; the DNS pattern keeps scoping which requests a policy covers.
"""
import base64
import json

import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from models import db, Certificate
from models.policy import CertificatePolicy
from services.policy_service import PolicyEvaluationService, PolicyViolation
from tests.conftest import get_json

CONTENT_JSON = 'application/json'


def _policy(app, name, ca_id=None, rules=None, requires_approval=False, active=True, priority=100):
    with app.app_context():
        pol = CertificatePolicy(name=name, policy_type='issuance', ca_id=ca_id,
                                requires_approval=requires_approval, min_approvers=1,
                                is_active=active, priority=priority)
        pol.set_rules(rules or {})
        db.session.add(pol)
        db.session.commit()
        return pol.id


def _drop(app, *ids):
    with app.app_context():
        for pid in ids:
            pol = db.session.get(CertificatePolicy, pid)
            if pol:
                db.session.delete(pol)
        db.session.commit()


def _issue(auth_client, ca_id, cn, **extra):
    payload = {'cn': cn, 'ca_id': ca_id, 'key_type': 'rsa', 'key_size': 2048,
               'validity_days': 90, 'cert_type': 'server'}
    payload.update(extra)
    return auth_client.post('/api/v2/certificates', data=json.dumps(payload),
                            content_type=CONTENT_JSON)


def _cert(app, cert_id):
    with app.app_context():
        row = db.session.get(Certificate, cert_id)
        return x509.load_pem_x509_certificate(base64.b64decode(row.crt), default_backend())


class TestEnforceRulesHelper:

    def _pol(self, rules, name='p'):
        pol = CertificatePolicy(name=name)
        pol.set_rules(rules)
        return pol

    def test_key_type_labels_are_normalised(self):
        pol = self._pol({'allowed_key_types': ['EC-P256', 'rsa:4096']})
        v, _ = PolicyEvaluationService.enforce_rules([pol], key_type='secp256r1')
        assert v == []
        v, _ = PolicyEvaluationService.enforce_rules([pol], key_type='4096')
        assert v == []
        v, _ = PolicyEvaluationService.enforce_rules([pol], key_type='2048')
        assert len(v) == 1 and 'RSA-2048' in v[0] and 'EC-P256' in v[0]

    def test_dns_cap_and_validity_cap(self):
        pol = self._pol({'san_restrictions': {'max_dns_names': 2}, 'max_validity_days': 30})
        v, days = PolicyEvaluationService.enforce_rules([pol], dns_name_count=3, validity_days=90)
        assert len(v) == 1 and '3 DNS names exceed the 2' in v[0]
        assert days == 30
        v, days = PolicyEvaluationService.enforce_rules([pol], dns_name_count=2, validity_days=10)
        assert v == [] and days == 10

    def test_unset_or_zero_rules_do_nothing(self):
        pol = self._pol({'allowed_key_types': [], 'san_restrictions': {'max_dns_names': 0},
                         'max_validity_days': 0})
        v, days = PolicyEvaluationService.enforce_rules([pol], key_type='2048', dns_name_count=99,
                                                        validity_days=3000)
        assert v == [] and days == 3000

    def test_most_restrictive_validity_wins(self):
        a = self._pol({'max_validity_days': 60}, 'a')
        b = self._pol({'max_validity_days': 20}, 'b')
        _, days = PolicyEvaluationService.enforce_rules([a, b], validity_days=90)
        assert days == 20


class TestDirectIssuance:

    def test_disallowed_key_type_is_refused_even_for_admin(self, app, auth_client, create_ca):
        ca = create_ca(cn='Policy EC-only CA')
        pid = _policy(app, 'ec-only', ca_id=ca['id'], rules={'allowed_key_types': ['EC-P256', 'EC-P384']})
        try:
            r = _issue(auth_client, ca['id'], 'rsa.policy.test')
            assert r.status_code == 400, r.data
            body = r.get_data(as_text=True)
            assert 'ec-only' in body and 'RSA-2048' in body
            r = _issue(auth_client, ca['id'], 'ec.policy.test', key_type='ecdsa', key_size=256)
            assert r.status_code in (200, 201), r.data
            assert isinstance(_cert(app, get_json(r)['data']['id']).public_key(), ec.EllipticCurvePublicKey)
        finally:
            _drop(app, pid)

    def test_too_many_dns_names_is_refused(self, app, auth_client, create_ca):
        ca = create_ca(cn='Policy SAN cap CA')
        pid = _policy(app, 'san-cap', ca_id=ca['id'], rules={'san_restrictions': {'max_dns_names': 2}})
        try:
            # CN is added as a DNS SAN: cn + 2 extra names = 3 > 2
            r = _issue(auth_client, ca['id'], 'a.policy.test', san_dns=['b.policy.test', 'c.policy.test'])
            assert r.status_code == 400, r.data
            assert 'san-cap' in r.get_data(as_text=True)
            r = _issue(auth_client, ca['id'], 'a2.policy.test', san_dns=['b2.policy.test'])
            assert r.status_code in (200, 201), r.data
        finally:
            _drop(app, pid)

    def test_validity_is_capped(self, app, auth_client, create_ca):
        ca = create_ca(cn='Policy validity CA')
        pid = _policy(app, 'short-lived', ca_id=ca['id'], rules={'max_validity_days': 30})
        try:
            r = _issue(auth_client, ca['id'], 'short.policy.test', validity_days=365)
            assert r.status_code in (200, 201), r.data
            cert = _cert(app, get_json(r)['data']['id'])
            assert (cert.not_valid_after_utc - cert.not_valid_before_utc).days <= 30
        finally:
            _drop(app, pid)

    def test_policy_scoped_to_another_ca_does_not_apply(self, app, auth_client, create_ca):
        ca = create_ca(cn='Policy scope CA A')
        other = create_ca(cn='Policy scope CA B')
        pid = _policy(app, 'other-ca-ec-only', ca_id=other['id'], rules={'allowed_key_types': ['EC-P256']})
        try:
            r = _issue(auth_client, ca['id'], 'scope.policy.test')
            assert r.status_code in (200, 201), r.data
        finally:
            _drop(app, pid)

    def test_inactive_policy_is_ignored(self, app, auth_client, create_ca):
        ca = create_ca(cn='Policy inactive CA')
        pid = _policy(app, 'inactive-ec-only', ca_id=ca['id'], rules={'allowed_key_types': ['EC-P256']}, active=False)
        try:
            r = _issue(auth_client, ca['id'], 'inactive.policy.test')
            assert r.status_code in (200, 201), r.data
        finally:
            _drop(app, pid)

    def test_dns_pattern_scopes_the_policy(self, app, auth_client, create_ca):
        ca = create_ca(cn='Policy pattern CA')
        pid = _policy(app, 'corp-ec-only', ca_id=ca['id'],
                      rules={'allowed_key_types': ['EC-P256'], 'san_restrictions': {'dns_pattern': '.corp.test'}})
        try:
            r = _issue(auth_client, ca['id'], 'web.other.test')
            assert r.status_code in (200, 201), r.data
            r = _issue(auth_client, ca['id'], 'web.corp.test')
            assert r.status_code == 400, r.data
            # the pattern is also matched against the requested DNS SANs
            r = _issue(auth_client, ca['id'], 'alias.other.test', san_dns=['web.corp.test'])
            assert r.status_code == 400, r.data
        finally:
            _drop(app, pid)


class TestApprovalPath:

    def test_rules_apply_when_the_approved_request_is_issued(self, app, create_ca):
        from tests.test_approval_template_issuance import _mk_approval_id, _requester_id
        from models.policy import ApprovalRequest
        from api.v2.policies import _issue_approved_certificate
        ca = create_ca(cn='Policy approval CA')
        pid = _policy(app, 'approval-ec-only', ca_id=ca['id'], rules={'allowed_key_types': ['EC-P256'], 'max_validity_days': 15})
        try:
            with app.app_context():
                approval = db.session.get(ApprovalRequest, _mk_approval_id(app, _requester_id(app), {
                    'cn': 'appr-rsa.policy.test', 'ca_id': ca['id'], 'cert_type': 'server',
                    'key_type': 'rsa', 'key_size': '2048', 'validity_days': 90}))
                with pytest.raises(PolicyViolation) as exc:
                    _issue_approved_certificate(approval)
                assert 'approval-ec-only' in str(exc.value)
                db.session.rollback()
                approval = db.session.get(ApprovalRequest, _mk_approval_id(app, _requester_id(app), {
                    'cn': 'appr-ec.policy.test', 'ca_id': ca['id'], 'cert_type': 'server',
                    'key_type': 'ecdsa', 'key_size': '256', 'validity_days': 90}))
                result = _issue_approved_certificate(approval)
                cert = x509.load_pem_x509_certificate(
                    base64.b64decode(db.session.get(Certificate, result['id']).crt), default_backend())
                assert (cert.not_valid_after_utc - cert.not_valid_before_utc).days <= 15
        finally:
            _drop(app, pid)
