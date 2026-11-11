"""An approved request fires the event its direct twin fires, once."""
from models import Certificate, db
from tests.event_recorder import events, cert_events  # noqa: F401
from tests.test_approval_on_sign_and_renew import (
    _cert_row, _csr_row, _drop_policy, _drop_rows, _json, _operator, _policy)
from tests.test_approval_template_issuance import _mk_approval_id, _requester_id


def test_approved_issuance_fires_certificate_issued(app, create_ca, events):
    from api.v2.policies import _issue_approved_certificate
    from models.policy import ApprovalRequest
    ca = create_ca(cn='Approval event issue CA')
    approval_id = _mk_approval_id(app, _requester_id(app), {
        'cn': 'appr-event.example.test', 'ca_id': ca['id'], 'cert_type': 'server',
        'key_type': 'EC', 'curve': 'P-256', 'validity_days': 30})
    with app.app_context():
        cert_id = _issue_approved_certificate(db.session.get(ApprovalRequest, approval_id))['id']
    try:
        assert cert_events(events, cert_id) == [('certificate.issued', cert_id)]
    finally:
        _drop_rows(app, cert_id)


def test_approved_csr_signature_fires_certificate_issued(app, auth_client, create_ca, create_user, events):
    ca = create_ca(cn='Approval event sign CA')
    pid = _policy(app, ca['id'], 'approval-event-sign')
    csr_id = _csr_row(app, 'approval-event-sign.example.test')
    operator = _operator(app, create_user)
    try:
        r = _json(operator, 'post', f'/api/v2/csrs/{csr_id}/sign', {'ca_id': ca['id'], 'validity_days': 30})
        approval_id = r.get_json()['data']['approval_id']
        r = _json(auth_client, 'post', f'/api/v2/approvals/{approval_id}/approve', {'comment': 'ok'})
        assert r.get_json()['data']['certificate_issued'] is True
        assert cert_events(events, csr_id) == [('certificate.issued', csr_id)]
    finally:
        _drop_policy(app, pid)
        _drop_rows(app, csr_id)


def test_approved_renewal_fires_certificate_renewed(app, auth_client, create_ca, create_user, events):
    ca = create_ca(cn='Approval event renew CA')
    pid = _policy(app, ca['id'], 'approval-event-renew')
    cert_id = _cert_row(app, ca['id'], 'approval-event-renew.example.test')
    operator = _operator(app, create_user)
    try:
        events.clear()
        r = _json(operator, 'post', f'/api/v2/certificates/{cert_id}/renew')
        approval_id = r.get_json()['data']['approval_id']
        r = _json(auth_client, 'post', f'/api/v2/approvals/{approval_id}/approve', {'comment': 'ok'})
        assert r.get_json()['data']['certificate_issued'] is True
        with app.app_context():
            assert db.session.get(Certificate, cert_id).renewed_times == 1
        assert cert_events(events, cert_id) == [('certificate.renewed', cert_id)]
    finally:
        _drop_policy(app, pid)
        _drop_rows(app, cert_id)
