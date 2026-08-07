"""Approval-driven issuance must honor the linked template (#226 semantics).

Regression tests for the legacy stub ``_issue_approved_certificate`` which
ignored template KU/EKU, digest, key-type and validity defaults, stored the
private key unencrypted, and dropped the template link entirely.
"""
import base64
import json

import itertools

import pytest
from cryptography import x509
from cryptography.x509.oid import ExtendedKeyUsageOID

from models import db, User
from models.certificate import Certificate
from models.certificate_template import CertificateTemplate
from models.policy import ApprovalRequest, CertificatePolicy
from services.policy_service import PolicyEvaluationService
from api.v2.policies import _issue_approved_certificate

_SEQ = itertools.count(1)


@pytest.fixture
def encryption_enabled(monkeypatch):
    """Force private-key encryption on for this test, then restore.

    The KeyEncryption singleton is process-global and other test files may
    leave it disabled — without pinning it here the encrypted-at-rest
    assertion depends on test ordering (flaky under -n auto and in CI).
    """
    from cryptography.fernet import Fernet
    from security import encryption as enc_mod
    monkeypatch.setenv("KEY_ENCRYPTION_KEY", Fernet.generate_key().decode())
    enc_mod.KeyEncryption().reload()
    assert enc_mod.KeyEncryption().is_enabled
    yield
    monkeypatch.undo()
    enc_mod.KeyEncryption().reload()

TEMPLATE_4096_30D = {
    'name': 'approval-tpl',
    'template_type': 'custom',
    'key_type': 'RSA-4096',
    'validity_days': 30,
    'digest': 'sha384',
    'extensions_template': json.dumps({
        'key_usage': ['digitalSignature', 'keyEncipherment'],
        'extended_key_usage': ['clientAuth'],
    }),
}


def _mk_template(app, **over):
    data = {**TEMPLATE_4096_30D, 'name': f'approval-tpl-{next(_SEQ)}', **over}
    with app.app_context():
        tpl = CertificateTemplate(**data)
        db.session.add(tpl)
        db.session.commit()
        return tpl.id


def _requester_id(app):
    with app.app_context():
        u = User.query.filter_by(role='admin').first() or User.query.first()
        assert u is not None
        return u.id


def _mk_approval_id(app, requester_id, request_data):
    """Persist a pending approval storing request_data (as cert_create does)."""
    with app.app_context():
        pol = CertificatePolicy(name=f'approval-tpl-pol-{next(_SEQ)}', policy_type='issuance',
                                requires_approval=True, min_approvers=1,
                                is_active=True)
        db.session.add(pol)
        db.session.commit()
        approval = PolicyEvaluationService.create_approval_request(
            policy=pol, request_data=request_data, requester_id=requester_id)
        return approval.id


def _issue_from_request(app, create_ca, request_data):
    """Full round-trip: persist approval data, issue, return (cert, row)."""
    app_request_data = dict(request_data)
    with app.app_context():
        approval = db.session.get(
            ApprovalRequest,
            _mk_approval_id(app, _requester_id(app), app_request_data))
        result = _issue_approved_certificate(approval)
        row = db.session.get(Certificate, result['id'])
        row_id = row.id
        tpl_id = row.template_id
        overrides = row.template_overrides_list
        prv_raw = base64.b64decode(row.prv, validate=True)
    # re-load cert material outside the ORM for assertion convenience
    with app.app_context():
        row = db.session.get(Certificate, row_id)
        cert = x509.load_pem_x509_certificate(base64.b64decode(row.crt))
    return cert, (row_id, tpl_id, overrides, prv_raw)


class TestApprovalHonorsTemplate:
    def test_template_defaults_apply(self, app, create_ca):
        ca = create_ca(cn='ApprTpl CA')
        tpl_id = _mk_template(app)

        cert, (row_id, row_tpl, overrides, _) = _issue_from_request(
            app, create_ca, {
                'cn': 'appr-defaults.test', 'ca_id': ca['id'],
                'cert_type': 'server', 'template_id': tpl_id,
            })

        # validity from template (30d), key from template (RSA-4096),
        # digest from template (sha384) — all absent from request data
        delta = cert.not_valid_after_utc - cert.not_valid_before_utc
        assert delta.days == 30
        assert cert.public_key().key_size == 4096
        assert cert.signature_hash_algorithm.name == 'sha384'
        # template KU/EKU, not the legacy 'server' profile
        eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
        assert list(eku) == [ExtendedKeyUsageOID.CLIENT_AUTH]
        ku = cert.extensions.get_extension_for_class(x509.KeyUsage).value
        assert ku.digital_signature and ku.key_encipherment
        assert not ku.key_cert_sign and not ku.crl_sign
        # template linkage + no divergence recorded (everything inherited)
        assert row_tpl == tpl_id
        assert overrides == []

    def test_explicit_values_recorded_as_overrides(self, app, create_ca):
        ca = create_ca(cn='ApprOvr CA')
        tpl_id = _mk_template(app)

        cert, (row_id, row_tpl, overrides, _) = _issue_from_request(
            app, create_ca, {
                'cn': 'appr-over.test', 'ca_id': ca['id'],
                'cert_type': 'server', 'template_id': tpl_id,
                'key_type': 'RSA', 'key_size': '2048', 'validity_days': 60,
            })

        assert cert.public_key().key_size == 2048
        assert sorted(overrides) == ['key_type', 'validity_days']
        assert row_tpl == tpl_id

    def test_private_key_encrypted_at_rest(self, app, create_ca, encryption_enabled):
        ca = create_ca(cn='ApprEnc CA')
        tpl_id = _mk_template(app)

        _cert, (_, _, _, prv_raw) = _issue_from_request(
            app, create_ca, {
                'cn': 'appr-enc.test', 'ca_id': ca['id'],
                'cert_type': 'server', 'template_id': tpl_id,
            })
        # Not the legacy plaintext base64-of-PEM shape
        assert not prv_raw.startswith(b'-----BEGIN')

    def test_no_template_keeps_legacy_profile(self, app, create_ca):
        ca = create_ca(cn='ApprLegacy CA')
        cert, (row_id, row_tpl, overrides, _) = _issue_from_request(
            app, create_ca, {
                'cn': 'appr-legacy.test', 'ca_id': ca['id'],
                'cert_type': 'client', 'validity_days': 90,
            })
        eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
        assert list(eku) == [ExtendedKeyUsageOID.CLIENT_AUTH]
        ku = cert.extensions.get_extension_for_class(x509.KeyUsage).value
        assert ku.digital_signature and not ku.key_encipherment
        assert row_tpl is None

    def test_missing_template_raises(self, app, create_ca):
        ca = create_ca(cn='ApprNoTpl CA')
        with app.app_context():
            approval = db.session.get(
                ApprovalRequest,
                _mk_approval_id(app, _requester_id(app), {
                    'cn': 'appr-notpl.test', 'ca_id': ca['id'],
                    'cert_type': 'server', 'template_id': 999999,
                }))
            with pytest.raises(ValueError, match='Template 999999 not found'):
                _issue_approved_certificate(approval)
