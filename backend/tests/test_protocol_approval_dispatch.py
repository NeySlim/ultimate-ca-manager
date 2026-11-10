"""The approval gate shared by the protocols and the dispatch of their
approved requests.

The gate holds a protocol request when a policy requires approval, finds it
again by its protocol reference, and refuses when the policies cannot be
read; the approval routes hand approved, rejected and expired requests to
the protocol that queued them.
"""
import uuid

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from models import CA, db
from models.policy import ApprovalRequest
from services import protocol_approval
from tests.protocol_approval_support import approval_policy, expire, reject, requests_of


def _csr(cn='gate.example'):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return (x509.CertificateSigningRequestBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(cn)]), critical=False)
            .sign(key, hashes.SHA256()))


@pytest.fixture
def gate_ca(app, create_ca):
    return create_ca(cn=f'Gate CA {uuid.uuid4().hex[:6]}')['id']


def _gate(app, ca_id, ref, protocol='wstep'):
    with app.app_context():
        csr = _csr()
        cn, dns = protocol_approval.csr_names(csr)
        approval = protocol_approval.gate_protocol_issuance(
            protocol, ca=db.session.get(CA, ca_id), cn=cn, san_list=dns,
            csr_pem='-----BEGIN CERTIFICATE REQUEST-----', identity='tester', protocol_ref=ref)
        return approval.id if approval is not None else None


@pytest.fixture
def fake_handler(monkeypatch):
    """A protocol handler recording what the approval routes hand it."""
    calls = []
    handler = protocol_approval._Handler(
        issue=lambda approval, data: calls.append(('issue', data['protocol_ref'])) or {'id': None},
        closed=lambda approval, data: calls.append(('closed', approval.status)),
        gone=lambda approval, data: None)
    monkeypatch.setitem(protocol_approval._HANDLERS, 'wstep_request', handler)
    return calls


def test_no_policy_lets_the_request_through(app, gate_ca):
    assert _gate(app, gate_ca, 'ref-free') is None


def test_policy_holds_the_request_once(app, gate_ca):
    with approval_policy(app, gate_ca, 'gate-hold') as pid:
        first = _gate(app, gate_ca, 'ref-held')
        assert first is not None
        assert _gate(app, gate_ca, 'ref-held') == first
        assert _gate(app, gate_ca, 'ref-other') != first
        rows = requests_of(app, pid)
        assert [r[1] for r in rows] == ['pending', 'pending']
        data = rows[0][2]
        assert data['protocol'] == 'wstep' and data['ca_id'] == gate_ca
        assert data['requested_by'] == 'wstep:tester'
        with app.app_context():
            row = db.session.get(ApprovalRequest, first)
            assert row.request_type == 'wstep_request' and row.requester_id is None
            assert row.to_dict()['requester_username'] == 'wstep:tester'
            # The approvals page shows who asked through which protocol, with which CSR
            summary = row.to_dict()['request_summary']
            assert summary['protocol'] == 'wstep' and summary['identity'] == 'tester'
            assert summary['csr'].startswith('-----BEGIN CERTIFICATE REQUEST-----')


def test_a_delivered_decision_is_forgotten(app, gate_ca, fake_handler):
    with approval_policy(app, gate_ca, 'gate-delivered'):
        first = _gate(app, gate_ca, 'ref-delivered')
        with app.app_context():
            protocol_approval.mark_delivered(db.session.get(ApprovalRequest, first))
        assert _gate(app, gate_ca, 'ref-delivered') not in (None, first)


def test_unreadable_policies_fail_closed(app, gate_ca, monkeypatch):
    from services.policy_service import PolicyEvaluationService

    def broken(*a, **k):
        raise RuntimeError('policy table unreadable')
    monkeypatch.setattr(PolicyEvaluationService, 'check_approval_required', broken)
    with pytest.raises(protocol_approval.ApprovalGateUnavailable):
        _gate(app, gate_ca, 'ref-broken')


def test_approval_dispatches_to_the_protocol(app, auth_client, gate_ca, fake_handler):
    with approval_policy(app, gate_ca, 'gate-dispatch') as pid:
        approval_id = _gate(app, gate_ca, 'ref-dispatch')
        r = auth_client.post(f'/api/v2/approvals/{approval_id}/approve', json={})
        assert r.status_code == 200, r.get_json()
        assert fake_handler == [('issue', 'ref-dispatch')]
        assert requests_of(app, pid)[0][1] == 'approved'


def test_a_gone_protocol_request_closes_the_approval(app, auth_client, gate_ca, monkeypatch):
    def gone_issue(approval, data):
        raise protocol_approval.ProtocolRequestGone('The order went away')
    monkeypatch.setitem(protocol_approval._HANDLERS, 'wstep_request',
                        protocol_approval._Handler(issue=gone_issue))
    with approval_policy(app, gate_ca, 'gate-gone') as pid:
        approval_id = _gate(app, gate_ca, 'ref-gone')
        r = auth_client.post(f'/api/v2/approvals/{approval_id}/approve', json={})
        assert r.status_code == 200
        assert r.get_json()['data']['request_closed'] is True
        assert requests_of(app, pid)[0][1] == 'rejected'


def test_rejection_reaches_the_protocol(app, auth_client, gate_ca, fake_handler):
    with approval_policy(app, gate_ca, 'gate-reject'):
        approval_id = _gate(app, gate_ca, 'ref-reject')
        reject(auth_client, approval_id)
        assert fake_handler == [('closed', 'rejected')]
        with app.app_context():
            reason = protocol_approval.decision_reason(db.session.get(ApprovalRequest, approval_id))
        assert reason == 'The request was rejected: not this one'


def test_expiry_reaches_the_protocol(app, gate_ca, fake_handler):
    with approval_policy(app, gate_ca, 'gate-expire'):
        approval_id = _gate(app, gate_ca, 'ref-expire')
        expire(app, approval_id)
        assert fake_handler == [('closed', 'expired')]
        # An expired request is forgotten: the client's next request is a new one
        assert _gate(app, gate_ca, 'ref-expire') not in (None, approval_id)
