"""SCEP requests held by a policy requiring approval (RFC 8894 §3.3.2.2).

The policy holds the request PENDING even on an auto-approving endpoint; the
approval request decides, from either queue, and GetCertInitial then answers
SUCCESS or FAILURE.
"""
import uuid

import asn1crypto.core
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509.oid import AttributeOID

from models import CA, SCEPRequest, SystemConfig, db
from services.scep.scep_service import SCEPService
from tests.protocol_approval_support import made_rows_removed  # noqa: F401
from tests.protocol_approval_support import approval_policy, approve, expire, reject, requests_of
from tests.test_scep_rfc8894_operations import (
    PKI_STATUS_OID, TRANSACTION_ID_OID, _build_request, _client_identity, _load_ca_material,
    _response_attributes, _rewrite_signed_attributes,
)

CHALLENGE = 'held horse battery staple'
SUCCESS, FAILURE, PENDING = '0', '2', '3'


@pytest.fixture
def scep_ca(app, create_ca):
    ca_data = create_ca(cn=f'SCEP approval CA {uuid.uuid4().hex[:6]}')
    with app.app_context():
        db.session.add(SystemConfig(key=f'scep_challenge_{ca_data["id"]}', value=CHALLENGE))
        db.session.commit()
    yield ca_data['id']
    with app.app_context():
        SystemConfig.query.filter_by(key=f'scep_challenge_{ca_data["id"]}').delete()
        db.session.commit()


def _service(ca_id):
    return SCEPService(db.session.get(CA, ca_id).refid, challenge_password=CHALLENGE, auto_approve=True)


def _enroll(app, ca_id, identity):
    with app.app_context():
        _ca, ca_cert, _ = _load_ca_material(ca_id)
        key_cert, key = identity
        csr = (x509.CertificateSigningRequestBuilder().subject_name(key_cert.subject)
               .add_attribute(AttributeOID.CHALLENGE_PASSWORD, CHALLENGE.encode())
               .sign(key, hashes.SHA256()))
        message = _build_request(ca_cert, key_cert, key, 19,
                                 csr.public_bytes(serialization.Encoding.DER), b'held-nonce-16byt')
        response, _status = _service(ca_id).process_pkcs_req(message, '127.0.0.1')
        return _response_attributes(response)[PKI_STATUS_OID]


def _poll(app, ca_id, identity):
    """GetCertInitial for the enrolment's transaction (txn-19)."""
    def same_transaction(attrs):
        for attr in attrs:
            if attr['type'].dotted == TRANSACTION_ID_OID:
                attr['values'] = [asn1crypto.core.PrintableString('txn-19')]
        return attrs
    with app.app_context():
        _ca, ca_cert, _ = _load_ca_material(ca_id)
        key_cert, key = identity
        message = _build_request(ca_cert, key_cert, key, 20, b'issuer-and-subject', b'poll-nonce-16byt')
        message = _rewrite_signed_attributes(message, key, same_transaction)
        response, _status = _service(ca_id).process_pkcs_req(message, '127.0.0.1')
        return _response_attributes(response)[PKI_STATUS_OID]


def _scep_row(app, ca_id):
    with app.app_context():
        row = SCEPRequest.query.filter_by(transaction_id='txn-19',
                                          ca_refid=db.session.get(CA, ca_id).refid).first()
        return row.id, row.status, row.cert_refid


def test_auto_approval_without_policy_issues(app, scep_ca):
    assert _enroll(app, scep_ca, _client_identity('scep free')) == SUCCESS


def test_policy_holds_an_auto_approving_endpoint(app, scep_ca):
    identity = _client_identity('scep held')
    with approval_policy(app, scep_ca, 'scep-held-pending') as pid:
        assert _enroll(app, scep_ca, identity) == PENDING
        assert _poll(app, scep_ca, identity) == PENDING
        (_id, status, data, _cert), = requests_of(app, pid, 'scep_request')
        scep_id, scep_status, _ = _scep_row(app, scep_ca)
        assert status == 'pending' and scep_status == 'pending'
        assert data['scep_request_id'] == scep_id and data['transaction_id'] == 'txn-19'


def test_approval_from_the_queue_issues_to_the_poll(app, auth_client, scep_ca):
    identity = _client_identity('scep approved')
    with approval_policy(app, scep_ca, 'scep-held-approve') as pid:
        assert _enroll(app, scep_ca, identity) == PENDING
        (approval_id, *_), = requests_of(app, pid, 'scep_request')
        body = approve(auth_client, approval_id)
        _id, scep_status, cert_refid = _scep_row(app, scep_ca)
        assert scep_status == 'approved' and cert_refid
        assert _poll(app, scep_ca, identity) == SUCCESS
        with app.app_context():
            from models import Certificate
            cert = Certificate.query.filter_by(refid=cert_refid).first()
            assert cert.id == body['certificate']['id'] == requests_of(app, pid)[0][3]


def test_approval_from_the_scep_queue_resolves_the_approval(app, auth_client, scep_ca):
    identity = _client_identity('scep approved here')
    with approval_policy(app, scep_ca, 'scep-held-approve-scep') as pid:
        assert _enroll(app, scep_ca, identity) == PENDING
        scep_id, *_ = _scep_row(app, scep_ca)
        r = auth_client.post(f'/api/v2/scep/{scep_id}/approve', json={})
        assert r.status_code == 200, r.get_json()
        assert requests_of(app, pid, 'scep_request')[0][1] == 'approved'
        assert _scep_row(app, scep_ca)[1] == 'approved'
        assert _poll(app, scep_ca, identity) == SUCCESS


def test_rejection_from_either_queue_fails_the_poll(app, auth_client, scep_ca):
    identity = _client_identity('scep refused')
    with approval_policy(app, scep_ca, 'scep-held-reject') as pid:
        assert _enroll(app, scep_ca, identity) == PENDING
        (approval_id, *_), = requests_of(app, pid, 'scep_request')
        reject(auth_client, approval_id, 'unknown host')
        assert _scep_row(app, scep_ca)[1] == 'rejected'
        assert _poll(app, scep_ca, identity) == FAILURE
        with app.app_context():
            row = db.session.get(SCEPRequest, _scep_row(app, scep_ca)[0])
            assert row.rejection_reason == 'Rejected by an approver'


def test_rejection_from_the_scep_queue_rejects_the_approval(app, auth_client, scep_ca):
    identity = _client_identity('scep refused here')
    with approval_policy(app, scep_ca, 'scep-held-reject-scep') as pid:
        assert _enroll(app, scep_ca, identity) == PENDING
        scep_id, *_ = _scep_row(app, scep_ca)
        r = auth_client.post(f'/api/v2/scep/{scep_id}/reject', json={'reason': 'unknown device'})
        assert r.status_code == 200, r.get_json()
        assert requests_of(app, pid, 'scep_request')[0][1] == 'rejected'
        assert _scep_row(app, scep_ca)[1] == 'rejected'
        assert _poll(app, scep_ca, identity) == FAILURE


def test_expiry_fails_the_poll(app, scep_ca):
    identity = _client_identity('scep late')
    with approval_policy(app, scep_ca, 'scep-held-expire') as pid:
        assert _enroll(app, scep_ca, identity) == PENDING
        (approval_id, *_), = requests_of(app, pid, 'scep_request')
        expire(app, approval_id)
        assert _scep_row(app, scep_ca)[1] == 'rejected'
        assert _poll(app, scep_ca, identity) == FAILURE


def test_unreadable_policies_store_nothing(app, scep_ca, monkeypatch):
    from services.policy_service import PolicyEvaluationService

    def broken(*a, **k):
        raise RuntimeError('policy table unreadable')
    monkeypatch.setattr(PolicyEvaluationService, 'check_approval_required', broken)
    assert _enroll(app, scep_ca, _client_identity('scep broken')) == FAILURE
    with app.app_context():
        assert SCEPRequest.query.filter_by(ca_refid=db.session.get(CA, scep_ca).refid).count() == 0


def _issued_cert(app, ca_id):
    import base64
    from models import Certificate
    _id, _status, cert_refid = _scep_row(app, ca_id)
    with app.app_context():
        row = Certificate.query.filter_by(refid=cert_refid).first()
        return row.source, x509.load_pem_x509_certificate(base64.b64decode(row.crt))


def test_approved_request_matches_a_direct_issuance(app, auth_client, create_ca, scep_ca):
    from tests.protocol_approval_support import profile_of
    direct_ca = create_ca(cn=f'SCEP direct CA {uuid.uuid4().hex[:6]}')['id']
    with app.app_context():
        db.session.add(SystemConfig(key=f'scep_challenge_{direct_ca}', value=CHALLENGE))
        db.session.commit()
    assert _enroll(app, direct_ca, _client_identity('scep same')) == SUCCESS
    with approval_policy(app, scep_ca, 'scep-held-compare') as pid:
        assert _enroll(app, scep_ca, _client_identity('scep same')) == PENDING
        (approval_id, *_), = requests_of(app, pid, 'scep_request')
        approve(auth_client, approval_id)
    direct_source, direct = _issued_cert(app, direct_ca)
    held_source, held = _issued_cert(app, scep_ca)
    assert profile_of(held) == profile_of(direct)
    assert held_source == direct_source


def test_a_ca_revoked_while_held_closes_the_request(app, auth_client, scep_ca):
    identity = _client_identity('scep ca revoked')
    with approval_policy(app, scep_ca, 'scep-held-ca-revoked') as pid:
        assert _enroll(app, scep_ca, identity) == PENDING
        (approval_id, *_), = requests_of(app, pid, 'scep_request')
        with app.app_context():
            db.session.get(CA, scep_ca).revoked = True
            db.session.commit()
        try:
            r = auth_client.post(f'/api/v2/approvals/{approval_id}/approve', json={'comment': 'ok'})
            assert r.status_code == 200, r.get_json()
            assert r.get_json()['message'] == 'Request closed'
            assert requests_of(app, pid, 'scep_request')[0][1] == 'rejected'
            scep_id, status, cert_refid = _scep_row(app, scep_ca)
            assert status == 'rejected' and cert_refid is None
            with app.app_context():
                assert 'revoked' in db.session.get(SCEPRequest, scep_id).rejection_reason
        finally:
            with app.app_context():
                db.session.get(CA, scep_ca).revoked = False
                db.session.commit()
        assert _poll(app, scep_ca, identity) == FAILURE


def test_an_expiry_not_yet_swept_fails_the_poll(app, scep_ca):
    """The poll reads the approval: past its deadline, it is expired on the
    way and the client hears FAILURE without waiting for the hourly sweep."""
    from datetime import timedelta
    from models.policy import ApprovalRequest
    from utils.datetime_utils import utc_now
    identity = _client_identity('scep late unswept')
    with approval_policy(app, scep_ca, 'scep-held-lazy-expire') as pid:
        assert _enroll(app, scep_ca, identity) == PENDING
        (approval_id, *_), = requests_of(app, pid, 'scep_request')
        with app.app_context():
            db.session.get(ApprovalRequest, approval_id).expires_at = utc_now() - timedelta(minutes=1)
            db.session.commit()
        assert _poll(app, scep_ca, identity) == FAILURE
        assert requests_of(app, pid, 'scep_request')[0][1] == 'expired'
        assert _scep_row(app, scep_ca)[1] == 'rejected'


def test_a_rejection_whose_echo_was_lost_fails_the_poll(app, scep_ca):
    """A rejection recorded while its echo to the SCEP request failed is
    carried over when the client polls."""
    from models.policy import ApprovalRequest
    identity = _client_identity('scep echo lost')
    with approval_policy(app, scep_ca, 'scep-held-echo-lost') as pid:
        assert _enroll(app, scep_ca, identity) == PENDING
        (approval_id, *_), = requests_of(app, pid, 'scep_request')
        with app.app_context():
            db.session.get(ApprovalRequest, approval_id).status = 'rejected'
            db.session.commit()
        assert _scep_row(app, scep_ca)[1] == 'pending'
        assert _poll(app, scep_ca, identity) == FAILURE
        assert _scep_row(app, scep_ca)[1] == 'rejected'


class _FakeIntune:
    """Records what Intune is told about the requests it validated."""
    calls = []
    fail_success = False

    def __init__(self, tenant_id, client_id, client_secret, provider_name=None):
        pass

    def send_success_notification(self, transaction_id, der_csr, cert):
        if _FakeIntune.fail_success:
            raise RuntimeError('Intune unreachable')
        _FakeIntune.calls.append(('success', transaction_id, cert.serial_number))

    def send_failure_notification(self, transaction_id, der_csr, hresult, description):
        _FakeIntune.calls.append(('failure', transaction_id, description))


@pytest.fixture
def intune_held(app, scep_ca, monkeypatch):
    """A request held on an Intune profile: the profile validates with a
    patched Intune client."""
    import services.scep.intune_client as intune
    from models.scep import ScepProfile
    monkeypatch.setattr(intune, 'IntuneScepClient', _FakeIntune)
    monkeypatch.setattr(ScepProfile, 'intune_credentials', lambda self: ('t', 'c', 's'))
    _FakeIntune.calls, _FakeIntune.fail_success = [], False
    slug = f'intune-held-{uuid.uuid4().hex[:6]}'
    with app.app_context():
        ca = db.session.get(CA, scep_ca)
        profile = ScepProfile(name=slug, url_slug=slug, ca_refid=ca.refid, auto_approve=True,
                              intune_enabled=True, enabled=True)
        db.session.add(profile)
        db.session.commit()
        profile_id = profile.id
    yield profile_id
    with app.app_context():
        SCEPRequest.query.filter_by(profile_id=profile_id).update({'profile_id': None})
        db.session.delete(db.session.get(ScepProfile, profile_id))
        db.session.commit()


def _on_profile(app, scep_ca, profile_id):
    with app.app_context():
        row = db.session.get(SCEPRequest, _scep_row(app, scep_ca)[0])
        row.profile_id = profile_id
        db.session.commit()


def test_an_approved_intune_request_is_notified(app, auth_client, scep_ca, intune_held):
    identity = _client_identity('scep intune approved')
    with approval_policy(app, scep_ca, 'scep-held-intune-ok') as pid:
        assert _enroll(app, scep_ca, identity) == PENDING
        _on_profile(app, scep_ca, intune_held)
        (approval_id, *_), = requests_of(app, pid, 'scep_request')
        body = approve(auth_client, approval_id)
        assert _FakeIntune.calls == [('success', 'txn-19', int(body['certificate']['serial_number']))]


def test_an_intune_notification_failure_keeps_the_request_pending(app, auth_client, scep_ca, intune_held):
    identity = _client_identity('scep intune down')
    with approval_policy(app, scep_ca, 'scep-held-intune-down') as pid:
        assert _enroll(app, scep_ca, identity) == PENDING
        _on_profile(app, scep_ca, intune_held)
        (approval_id, *_), = requests_of(app, pid, 'scep_request')
        _FakeIntune.fail_success = True
        r = auth_client.post(f'/api/v2/approvals/{approval_id}/approve', json={'comment': 'ok'})
        assert r.status_code == 200 and r.get_json()['data']['certificate_issued'] is False
        assert 'Intune' in r.get_json()['data']['issue_error']
        assert requests_of(app, pid, 'scep_request')[0][1] == 'pending'
        _id, status, cert_refid = _scep_row(app, scep_ca)
        assert status == 'pending' and cert_refid is None


def test_a_rejected_intune_request_is_notified(app, auth_client, scep_ca, intune_held):
    identity = _client_identity('scep intune rejected')
    with approval_policy(app, scep_ca, 'scep-held-intune-no') as pid:
        assert _enroll(app, scep_ca, identity) == PENDING
        _on_profile(app, scep_ca, intune_held)
        (approval_id, *_), = requests_of(app, pid, 'scep_request')
        reject(auth_client, approval_id, 'unknown host')
        assert _FakeIntune.calls == [('failure', 'txn-19', 'Rejected by an approver')]


def _poll_transaction(app, ca_id, identity, transaction_id):
    """GetCertInitial for *transaction_id*, signed by *identity*."""
    def same_transaction(attrs):
        for attr in attrs:
            if attr['type'].dotted == TRANSACTION_ID_OID:
                attr['values'] = [asn1crypto.core.PrintableString(transaction_id)]
        return attrs
    with app.app_context():
        _ca, ca_cert, _ = _load_ca_material(ca_id)
        key_cert, key = identity
        message = _build_request(ca_cert, key_cert, key, 20, b'issuer-and-subject', b'poll-nonce-16byt')
        message = _rewrite_signed_attributes(message, key, same_transaction)
        response, _status = _service(ca_id).process_pkcs_req(message, '127.0.0.1')
        return _response_attributes(response)[PKI_STATUS_OID]


def _held_renewal(app, scep_ca, pid, cn):
    """An enrolment issued directly, then its RenewalReq held: ``(issued, key, approval_id)``."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    identity = _client_identity(cn)
    assert _enroll(app, scep_ca, identity) == SUCCESS
    _source, issued = _issued_cert(app, scep_ca)
    key = identity[1]
    new_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = x509.CertificateSigningRequestBuilder().subject_name(issued.subject).sign(new_key, hashes.SHA256())
    with app.app_context():
        _ca, ca_cert, _ = _load_ca_material(scep_ca)
        message = _build_request(ca_cert, issued, key, 17, csr.public_bytes(serialization.Encoding.DER),
                                 b'renew-nonce-16by')
        response, _status = _service(scep_ca).process_pkcs_req(message, '127.0.0.1')
        assert _response_attributes(response)[PKI_STATUS_OID] == PENDING
    (approval_id, *_), = requests_of(app, pid, 'scep_request')
    return issued, key, approval_id


def _renewal_row(app, ca_id):
    with app.app_context():
        return SCEPRequest.query.filter_by(transaction_id='txn-17',
                                           ca_refid=db.session.get(CA, ca_id).refid).first().status


def test_an_approved_renewal_whose_signer_was_revoked_fails_the_poll(app, auth_client, scep_ca):
    from models import Certificate
    with approval_policy(app, scep_ca, 'scep-held-renew-revoked', operations=['renewal']) as pid:
        issued, key, approval_id = _held_renewal(app, scep_ca, pid, 'scep renew revoked')
        approve(auth_client, approval_id)
        assert _poll_transaction(app, scep_ca, (issued, key), 'txn-17') == SUCCESS
        with app.app_context():
            row = Certificate.query.filter_by(serial_number=str(issued.serial_number)).first()
            row.revoked = True
            db.session.commit()
        assert _poll_transaction(app, scep_ca, (issued, key), 'txn-17') == FAILURE
        assert _renewal_row(app, scep_ca) == 'rejected'
        (_id, status, data, _cert), = requests_of(app, pid, 'scep_request')
        assert status == 'rejected' and data['closed_reason'] == 'Renewed certificate revoked'


def test_an_approved_request_whose_certificate_went_away_fails_the_poll(app, auth_client, scep_ca):
    from models import Certificate
    identity = _client_identity('scep withdrawn')
    with approval_policy(app, scep_ca, 'scep-held-withdrawn') as pid:
        assert _enroll(app, scep_ca, identity) == PENDING
        (approval_id, *_), = requests_of(app, pid, 'scep_request')
        approve(auth_client, approval_id)
        _id, _status, cert_refid = _scep_row(app, scep_ca)
        from tests.test_protocol_approval_est import _withdraw
        _withdraw(app, approval_id)
        with app.app_context():
            Certificate.query.filter_by(refid=cert_refid).delete()
            db.session.commit()
        assert _poll(app, scep_ca, identity) == FAILURE
        assert _scep_row(app, scep_ca)[1] == 'rejected'
        (_id, status, data, _cert), = requests_of(app, pid, 'scep_request')
        assert status == 'rejected' and data['closed_reason'] == 'Certificate withdrawn'


@pytest.mark.parametrize('route', ['/api/v2/approvals?status=all', '/api/v2/approvals/stats', 'detail'])
def test_an_expiry_seen_by_a_read_route_is_told_to_intune_by_the_scheduled_task(
        app, auth_client, scep_ca, intune_held, route):
    """A GET never calls Intune: the hourly expiry task tells it."""
    from datetime import timedelta
    from models.policy import ApprovalRequest
    from services.approval_gate import scheduled_expiry
    from utils.datetime_utils import utc_now
    identity = _client_identity('scep intune expired')
    with approval_policy(app, scep_ca, f'scep-held-intune-late-{route[-5:]}') as pid:
        assert _enroll(app, scep_ca, identity) == PENDING
        _on_profile(app, scep_ca, intune_held)
        (approval_id, *_), = requests_of(app, pid, 'scep_request')
        with app.app_context():
            db.session.get(ApprovalRequest, approval_id).expires_at = utc_now() - timedelta(minutes=1)
            db.session.commit()
        url = f'/api/v2/approvals/{approval_id}' if route == 'detail' else route
        assert auth_client.get(url).status_code == 200
        assert requests_of(app, pid, 'scep_request')[0][1] == 'expired'
        assert _scep_row(app, scep_ca)[1] == 'rejected'
        assert _FakeIntune.calls == []
        with app.app_context():
            scheduled_expiry()
        assert _FakeIntune.calls == [('failure', 'txn-19', 'Approval request expired')]
        with app.app_context():
            scheduled_expiry()
        assert len(_FakeIntune.calls) == 1
