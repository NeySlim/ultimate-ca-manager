"""The approval workflow issues the certificate the requester asked for:
subject e-mail, URI and UPN Subject Alternative Names, OCSP Must-Staple and
the same clock-skew allowance as the issue form."""

import base64
from datetime import datetime, timezone

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.x509.oid import ExtensionOID, NameOID

from models import Certificate, db
from models.policy import ApprovalRequest

UPN_OID = x509.ObjectIdentifier('1.3.6.1.4.1.311.20.2.3')


def test_approved_certificate_carries_every_requested_field(app, create_ca):
    from tests.test_approval_template_issuance import _mk_approval_id, _requester_id
    from api.v2.policies import _issue_approved_certificate
    ca = create_ca(cn='Approval fields CA')
    with app.app_context():
        approval = db.session.get(ApprovalRequest, _mk_approval_id(app, _requester_id(app), {
            'cn': 'fields.example.test', 'ca_id': ca['id'], 'cert_type': 'client',
            'validity_days': 30, 'email': 'holder@example.test',
            'san_uri': ['https://fields.example.test/id'], 'san_upn': ['holder@corp.example'],
            'ocsp_must_staple': True,
        }))
        result = _issue_approved_certificate(approval)
        row = db.session.get(Certificate, result['id'])
        cert = x509.load_pem_x509_certificate(base64.b64decode(row.crt), default_backend())
        assert row.ocsp_must_staple is True
        row_id = row.id
    assert cert.subject.get_attributes_for_oid(NameOID.EMAIL_ADDRESS)[0].value == 'holder@example.test'
    san = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME).value
    assert san.get_values_for_type(x509.UniformResourceIdentifier) == ['https://fields.example.test/id']
    assert any(n.type_id == UPN_OID for n in san.get_values_for_type(x509.OtherName))
    cert.extensions.get_extension_for_oid(ExtensionOID.TLS_FEATURE)
    assert cert.not_valid_before_utc < datetime.now(timezone.utc)
    with app.app_context():
        db.session.delete(db.session.get(Certificate, row_id))
        db.session.commit()
