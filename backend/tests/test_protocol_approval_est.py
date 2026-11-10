"""EST requests held by a policy requiring approval (RFC 7030 §4.2.3, §4.4.2).

The server answers 202 with Retry-After; the client sends the same request
again and receives the certificate once approved, a 403 once rejected.
"""
import base64

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs7

from models import Certificate
from tests.protocol_approval_support import made_rows_removed  # noqa: F401
from tests.protocol_approval_support import (approval_policy, approve, expire, profile_of, reject,
                                             requests_of)
from tests.test_est_rfc7030 import (  # noqa: F401
    _basic_auth, _make_csr, _multipart_parts, _post_csr, _set_config, est_config,
)


@pytest.fixture(autouse=True)
def _est_on(app, est_config):
    with app.app_context():
        _set_config('est_enabled', 'true')


def _cert_of(response):
    assert response.status_code == 200, response.data
    return pkcs7.load_der_pkcs7_certificates(base64.b64decode(response.data))[0]


def _enroll(client, csr):
    return _post_csr(client, 'simpleenroll', csr, headers=_basic_auth())


def _held(response):
    assert response.status_code == 202, response.data
    assert int(response.headers['Retry-After']) > 0
    return response


def test_without_policy_enrolment_is_immediate(client, est_config):
    csr, _ = _make_csr(common_name='free.est-approval.test')
    _cert_of(_enroll(client, csr))


def test_enrolment_waits_then_delivers_the_approved_certificate(app, client, auth_client, est_config):
    with approval_policy(app, est_config['id'], 'est-held-enroll') as pid:
        csr, _ = _make_csr(common_name='held.est-approval.test', san_names=['held.est-approval.test'])
        _held(_enroll(client, csr))
        _held(_enroll(client, csr))
        (approval_id, status, data, _cert), = requests_of(app, pid, 'est_enroll')
        assert status == 'pending' and data['operation'] == 'enroll'
        assert data['identity'] == 'basic:est-test'

        approve(auth_client, approval_id)
        cert = _cert_of(_enroll(client, csr))
        assert cert.public_key() == csr.public_key()
        with app.app_context():
            row = Certificate.query.filter_by(serial_number=str(cert.serial_number)).first()
            assert row.source == 'est'
        # Delivered once: the same request later is a new one
        _held(_enroll(client, csr))
        assert [r[1] for r in requests_of(app, pid, 'est_enroll')] == ['approved', 'pending']


def test_another_csr_is_another_request(app, client, est_config):
    with approval_policy(app, est_config['id'], 'est-held-other') as pid:
        first, _ = _make_csr(common_name='one.est-approval.test')
        second, _ = _make_csr(common_name='one.est-approval.test')
        _held(_enroll(client, first))
        _held(_enroll(client, second))
        assert len(requests_of(app, pid, 'est_enroll')) == 2


def test_rejection_is_forbidden(app, client, auth_client, est_config):
    with approval_policy(app, est_config['id'], 'est-held-reject') as pid:
        csr, _ = _make_csr(common_name='refused.est-approval.test')
        _held(_enroll(client, csr))
        (approval_id, *_), = requests_of(app, pid, 'est_enroll')
        reject(auth_client, approval_id, 'unknown host')
        refused = _enroll(client, csr)
        assert refused.status_code == 403
        # The approver's comment stays on the server side
        assert refused.data == b'Rejected by an approver'


def test_expired_request_starts_again(app, client, est_config):
    with approval_policy(app, est_config['id'], 'est-held-expire') as pid:
        csr, _ = _make_csr(common_name='late.est-approval.test')
        _held(_enroll(client, csr))
        (approval_id, *_), = requests_of(app, pid, 'est_enroll')
        expire(app, approval_id)
        _held(_enroll(client, csr))
        assert [r[1] for r in requests_of(app, pid, 'est_enroll')] == ['expired', 'pending']


def test_retry_after_is_configurable(app, client, est_config):
    with app.app_context():
        _set_config('est_retry_after_seconds', '42')
    try:
        with approval_policy(app, est_config['id'], 'est-held-retry'):
            csr, _ = _make_csr(common_name='retry.est-approval.test')
            assert _held(_enroll(client, csr)).headers['Retry-After'] == '42'
    finally:
        with app.app_context():
            _set_config('est_retry_after_seconds', '300')


def test_reenrolment_waits_then_delivers(app, client, auth_client, est_config):
    csr, key = _make_csr(common_name='renew.est-approval.test')
    leaf = _cert_of(_enroll(client, csr))
    client_pem = leaf.public_bytes(serialization.Encoding.PEM).decode()
    renewal = x509.CertificateSigningRequestBuilder().subject_name(leaf.subject).sign(key, hashes.SHA256())
    with approval_policy(app, est_config['id'], 'est-held-reenroll') as pid:
        _held(_post_csr(client, 'simplereenroll', renewal, client_cert_pem=client_pem))
        (approval_id, _s, data, _c), = requests_of(app, pid, 'est_enroll')
        assert data['operation'] == 'reenroll' and data['renewal'] is True
        approve(auth_client, approval_id)
        renewed = _cert_of(_post_csr(client, 'simplereenroll', renewal, client_cert_pem=client_pem))
        assert renewed.serial_number != leaf.serial_number
        assert profile_of(renewed) == profile_of(leaf)


def test_server_key_generation_waits_then_generates(app, client, auth_client, est_config):
    with approval_policy(app, est_config['id'], 'est-held-keygen') as pid:
        csr, _ = _make_csr(common_name='keygen.est-approval.test')
        _held(_post_csr(client, 'serverkeygen', csr, headers=_basic_auth()))
        (approval_id, _s, data, _c), = requests_of(app, pid, 'est_enroll')
        assert data['operation'] == 'serverkeygen'
        # Approved only: the key and its certificate wait for the client's retry
        r = auth_client.post(f'/api/v2/approvals/{approval_id}/approve', json={'comment': 'ok'})
        assert r.status_code == 200, r.get_json()
        body = r.get_json()['data']
        assert body['certificate_issued'] is False and body['deferred'] is True
        assert body['status'] == 'approved' and 'issue_error' not in body
        response = _post_csr(client, 'serverkeygen', csr, headers=_basic_auth())
        assert response.status_code == 200, response.data
        assert len(_multipart_parts(response)) == 2
        (_id, status, data, cert_id), = requests_of(app, pid, 'est_enroll')
        assert status == 'approved' and cert_id is not None and data.get('delivered_at')
        _held(_post_csr(client, 'serverkeygen', csr, headers=_basic_auth()))


def test_server_key_generation_rejected(app, client, auth_client, est_config):
    with approval_policy(app, est_config['id'], 'est-held-keygen-reject') as pid:
        csr, _ = _make_csr(common_name='keygen-no.est-approval.test')
        _held(_post_csr(client, 'serverkeygen', csr, headers=_basic_auth()))
        (approval_id, *_), = requests_of(app, pid, 'est_enroll')
        reject(auth_client, approval_id)
        assert _post_csr(client, 'serverkeygen', csr, headers=_basic_auth()).status_code == 403


def test_approved_enrolment_matches_a_direct_one(app, client, auth_client, est_config):
    direct_csr, _ = _make_csr(common_name='same.est-approval.test', san_names=['same.est-approval.test'])
    direct = _cert_of(_enroll(client, direct_csr))
    with approval_policy(app, est_config['id'], 'est-held-compare') as pid:
        csr, _ = _make_csr(common_name='same.est-approval.test', san_names=['same.est-approval.test'])
        _held(_enroll(client, csr))
        (approval_id, *_), = requests_of(app, pid, 'est_enroll')
        approve(auth_client, approval_id)
        approved = _cert_of(_enroll(client, csr))
    assert profile_of(approved) == profile_of(direct)
    with app.app_context():
        rows = [Certificate.query.filter_by(serial_number=str(c.serial_number)).first()
                for c in (direct, approved)]
        assert [r.source for r in rows] == ['est', 'est']
        assert rows[0].cert_type == rows[1].cert_type


def test_unreadable_policies_refuse(app, client, est_config, monkeypatch):
    from services.policy_service import PolicyEvaluationService

    def broken(*a, **k):
        raise RuntimeError('policy table unreadable')
    monkeypatch.setattr(PolicyEvaluationService, 'check_approval_required', broken)
    csr, _ = _make_csr(common_name='broken.est-approval.test')
    assert _enroll(client, csr).status_code == 500


def _approved_keygen(app, client, auth_client, est_config, pid, cn):
    csr, _ = _make_csr(common_name=cn)
    _held(_post_csr(client, 'serverkeygen', csr, headers=_basic_auth()))
    (approval_id, *_), = requests_of(app, pid, 'est_enroll')
    r = auth_client.post(f'/api/v2/approvals/{approval_id}/approve', json={'comment': 'ok'})
    assert r.status_code == 200, r.get_json()
    return csr, approval_id


def test_two_key_generation_retries_issue_one_certificate(app, client, auth_client, est_config):
    with approval_policy(app, est_config['id'], 'est-held-keygen-twice') as pid:
        cn = 'keygen-twice.est-approval.test'
        csr, _approval_id = _approved_keygen(app, client, auth_client, est_config, pid, cn)
        first = _post_csr(client, 'serverkeygen', csr, headers=_basic_auth())
        second = _post_csr(client, 'serverkeygen', csr, headers=_basic_auth())
        assert first.status_code == 200, first.data
        # Delivered once: the second retry is a new request, held again
        _held(second)
        with app.app_context():
            assert Certificate.query.filter(Certificate.subject.contains(cn)).count() == 1
        assert [r[1] for r in requests_of(app, pid, 'est_enroll')] == ['approved', 'pending']


def test_a_delivery_claimed_meanwhile_is_not_claimed_again(app, client, auth_client, est_config):
    """The retry that waited on the row lock reads the row again: another
    retry delivered the key meanwhile, so this one issues nothing."""
    import json
    from models import db
    from models.policy import ApprovalRequest
    from services import protocol_approval
    with approval_policy(app, est_config['id'], 'est-held-keygen-claim') as pid:
        _csr, approval_id = _approved_keygen(app, client, auth_client, est_config, pid,
                                             'keygen-claim.est-approval.test')
        with app.app_context():
            stale = db.session.get(ApprovalRequest, approval_id)
            assert not protocol_approval.request_data(stale).get('delivered_at')
            data = dict(protocol_approval.request_data(stale), delivered_at='2026-01-01T00:00:00Z')
            # Another worker's claim, committed on its own connection: this
            # session's copy is stale
            with db.engine.begin() as other:
                other.execute(ApprovalRequest.__table__.update()
                              .where(ApprovalRequest.__table__.c.id == approval_id)
                              .values(request_data=json.dumps(data)))
            assert protocol_approval.claim_delivery(stale) is False
            fresh = db.session.get(ApprovalRequest, approval_id)
            assert protocol_approval.claim_delivery(fresh) is False


def test_a_failed_key_generation_keeps_the_approval(app, client, auth_client, est_config, monkeypatch):
    import api.est_protocol as est
    with approval_policy(app, est_config['id'], 'est-held-keygen-fail') as pid:
        csr, _approval_id = _approved_keygen(app, client, auth_client, est_config, pid,
                                             'keygen-fail.est-approval.test')
        real = est.sign_est_csr
        monkeypatch.setattr(est, 'sign_est_csr', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('down')))
        assert _post_csr(client, 'serverkeygen', csr, headers=_basic_auth()).status_code == 400
        monkeypatch.setattr(est, 'sign_est_csr', real)
        assert _post_csr(client, 'serverkeygen', csr, headers=_basic_auth()).status_code == 200
        assert [r[1] for r in requests_of(app, pid, 'est_enroll')] == ['approved']


def test_reenrolment_approved_then_revoked_is_refused(app, client, auth_client, est_config):
    from models import db
    csr, key = _make_csr(common_name='renew-revoked.est-approval.test')
    leaf = _cert_of(_enroll(client, csr))
    client_pem = leaf.public_bytes(serialization.Encoding.PEM).decode()
    renewal = x509.CertificateSigningRequestBuilder().subject_name(leaf.subject).sign(key, hashes.SHA256())
    with approval_policy(app, est_config['id'], 'est-held-reenroll-revoked') as pid:
        _held(_post_csr(client, 'simplereenroll', renewal, client_cert_pem=client_pem))
        (approval_id, *_), = requests_of(app, pid, 'est_enroll')
        approve(auth_client, approval_id)
        with app.app_context():
            row = Certificate.query.filter_by(serial_number=str(leaf.serial_number)).first()
            row.revoked = True
            db.session.commit()
        refused = _post_csr(client, 'simplereenroll', renewal, client_cert_pem=client_pem)
        assert refused.status_code == 403, refused.data
        assert b'revoked' in refused.data


def _withdraw(app, approval_id):
    """The approved request loses its certificate before delivery."""
    from models import db
    from models.policy import ApprovalRequest
    with app.app_context(), db.engine.begin() as conn:
        conn.execute(ApprovalRequest.__table__.update()
                     .where(ApprovalRequest.__table__.c.id == approval_id).values(certificate_id=None))


def test_an_approved_enrolment_whose_certificate_went_away_is_refused(app, client, auth_client, est_config):
    with approval_policy(app, est_config['id'], 'est-held-withdrawn') as pid:
        csr, _ = _make_csr(common_name='withdrawn.est-approval.test')
        _held(_enroll(client, csr))
        (approval_id, *_), = requests_of(app, pid, 'est_enroll')
        approve(auth_client, approval_id)
        _withdraw(app, approval_id)
        refused = _enroll(client, csr)
        assert refused.status_code == 403, refused.data
        assert refused.data == b'Certificate withdrawn'
        (_id, status, data, _cert), = requests_of(app, pid, 'est_enroll')
        assert status == 'rejected' and data['delivered_at']
        _held(_enroll(client, csr))


def _failing_response(monkeypatch):
    import api.est_protocol as est

    def broken(*a, **k):
        raise RuntimeError('response could not be built')
    real = est._certs_only_response
    monkeypatch.setattr(est, '_certs_only_response', broken)
    return lambda: monkeypatch.setattr(est, '_certs_only_response', real)


def test_an_enrolment_answer_that_fails_is_not_marked_delivered(app, client, auth_client, est_config,
                                                                 monkeypatch):
    with approval_policy(app, est_config['id'], 'est-held-answer-fails') as pid:
        csr, _ = _make_csr(common_name='answer-fails.est-approval.test')
        _held(_enroll(client, csr))
        (approval_id, *_), = requests_of(app, pid, 'est_enroll')
        approve(auth_client, approval_id)
        restore = _failing_response(monkeypatch)
        assert _enroll(client, csr).status_code != 200
        restore()
        (_id, status, data, _cert), = requests_of(app, pid, 'est_enroll')
        assert status == 'approved' and not data.get('delivered_at')
        _cert_of(_enroll(client, csr))


def test_a_reenrolment_answer_that_fails_is_not_marked_delivered(app, client, auth_client, est_config,
                                                                  monkeypatch):
    csr, key = _make_csr(common_name='reanswer-fails.est-approval.test')
    leaf = _cert_of(_enroll(client, csr))
    client_pem = leaf.public_bytes(serialization.Encoding.PEM).decode()
    renewal = x509.CertificateSigningRequestBuilder().subject_name(leaf.subject).sign(key, hashes.SHA256())
    with approval_policy(app, est_config['id'], 'est-held-reanswer-fails') as pid:
        _held(_post_csr(client, 'simplereenroll', renewal, client_cert_pem=client_pem))
        (approval_id, *_), = requests_of(app, pid, 'est_enroll')
        approve(auth_client, approval_id)
        restore = _failing_response(monkeypatch)
        assert _post_csr(client, 'simplereenroll', renewal, client_cert_pem=client_pem).status_code != 200
        restore()
        (_id, status, data, _cert), = requests_of(app, pid, 'est_enroll')
        assert status == 'approved' and not data.get('delivered_at')
        _cert_of(_post_csr(client, 'simplereenroll', renewal, client_cert_pem=client_pem))


@pytest.mark.parametrize('refusal', ['policy', 'content'])
def test_a_key_generation_refused_at_issuance_closes_the_request(app, client, auth_client, est_config,
                                                                 monkeypatch, refusal):
    """A refusal for good on the approved retry closes the request: the
    next retry is a new request, not the same refusal forever."""
    import api.est_protocol as est
    from services.policy_service import PolicyViolation
    from utils.request_names import RequestRejected
    error = (PolicyViolation if refusal == 'policy' else RequestRejected)('refused for good')
    with approval_policy(app, est_config['id'], f'est-held-keygen-refused-{refusal}') as pid:
        csr, _approval_id = _approved_keygen(app, client, auth_client, est_config, pid,
                                             f'keygen-refused-{refusal}.est-approval.test')

        def refused(*a, **k):
            raise error
        monkeypatch.setattr(est, 'sign_est_csr', refused)
        assert _post_csr(client, 'serverkeygen', csr, headers=_basic_auth()).status_code == 400
        (_id, status, data, _cert), = requests_of(app, pid, 'est_enroll')
        assert status == 'rejected' and data['closed_reason'] == 'Refused at issuance'
        _held(_post_csr(client, 'serverkeygen', csr, headers=_basic_auth()))
        assert [r[1] for r in requests_of(app, pid, 'est_enroll')] == ['rejected', 'pending']


def _retry_while_linking(app, monkeypatch, retry):
    """Run *retry* (a fresh client's request) right after the approved
    request is issued and before the approval route goes on: what the
    client would hear at that instant."""
    from services import protocol_approval
    real = protocol_approval.issue_approved
    heard = []

    def issue_then_retry(approval, data):
        outcome = real(approval, data)
        heard.append(retry(app.test_client()))
        return outcome
    monkeypatch.setattr(protocol_approval, 'issue_approved', issue_then_retry)
    return heard


def test_an_approval_is_never_seen_without_its_certificate(app, client, auth_client, est_config,
                                                           monkeypatch):
    with approval_policy(app, est_config['id'], 'est-held-linking') as pid:
        csr, _ = _make_csr(common_name='linking.est-approval.test')
        _held(_enroll(client, csr))
        (approval_id, *_), = requests_of(app, pid, 'est_enroll')
        heard = _retry_while_linking(app, monkeypatch, lambda c: _enroll(c, csr))
        approve(auth_client, approval_id)
        assert heard[0].data != b'Certificate withdrawn'
        assert _cert_of(heard[0]).public_key() == csr.public_key()
        (_id, status, data, cert_id), = requests_of(app, pid, 'est_enroll')
        assert status == 'approved' and cert_id is not None and data['delivered_at']


def test_a_withdrawn_certificate_closes_the_request_as_any_closure(app, client, auth_client, est_config,
                                                                   monkeypatch):
    """Vote, audit and webhook, as when an approver finds the target gone."""
    from models import AuditLog
    from services import webhook_service
    emitted = []
    monkeypatch.setattr(webhook_service, 'emit_csr_rejected',
                        lambda csr, reason=None, actor=None: emitted.append((csr['id'], reason, actor)))
    with approval_policy(app, est_config['id'], 'est-held-withdrawn-audit') as pid:
        csr, _ = _make_csr(common_name='withdrawn-audit.est-approval.test')
        _held(_enroll(client, csr))
        (approval_id, *_), = requests_of(app, pid, 'est_enroll')
        approve(auth_client, approval_id)
        _withdraw(app, approval_id)
        assert _enroll(client, csr).status_code == 403
        assert emitted == [(approval_id, 'Certificate withdrawn', 'system')]
        with app.app_context():
            from models import db
            from models.policy import ApprovalRequest
            entry = (AuditLog.query.filter_by(action='approval_closed', resource_id=str(approval_id))
                     .order_by(AuditLog.id.desc()).first())
            assert entry is not None and 'Certificate withdrawn' in entry.details
            votes = db.session.get(ApprovalRequest, approval_id).get_approvals()
            assert votes[-1]['action'] == 'reject' and votes[-1]['comment'] == 'Certificate withdrawn'


def test_a_reenrolment_refused_at_issuance_is_announced_as_such(app, client, auth_client, est_config,
                                                                monkeypatch):
    """Closed by the issuance, not by an approver: the client is told so."""
    from services.cert import issued_lookup
    csr, key = _make_csr(common_name='renew-refused.est-approval.test')
    leaf = _cert_of(_enroll(client, csr))
    client_pem = leaf.public_bytes(serialization.Encoding.PEM).decode()
    renewal = x509.CertificateSigningRequestBuilder().subject_name(leaf.subject).sign(key, hashes.SHA256())
    with approval_policy(app, est_config['id'], 'est-held-reenroll-refused') as pid:
        _held(_post_csr(client, 'simplereenroll', renewal, client_cert_pem=client_pem))
        (approval_id, *_), = requests_of(app, pid, 'est_enroll')
        real = issued_lookup.issued_certificate_status
        monkeypatch.setattr(issued_lookup, 'issued_certificate_status',
                            lambda ca, cert: (real(ca, cert)[0], issued_lookup.REVOKED))
        r = auth_client.post(f'/api/v2/approvals/{approval_id}/approve', json={'comment': 'ok'})
        monkeypatch.setattr(issued_lookup, 'issued_certificate_status', real)
        assert r.get_json()['message'] == 'Request closed'
        refused = _post_csr(client, 'simplereenroll', renewal, client_cert_pem=client_pem)
        assert refused.status_code == 403 and refused.data == b'Refused at issuance'


def test_an_approval_already_linked_issues_no_second_certificate(app, client, est_config):
    """Linking is a compare-and-set: a copy of the request read before
    another issuance linked it stores no second certificate."""
    import json

    from models import db
    from models.policy import ApprovalRequest
    from services import protocol_approval
    first = _cert_of(_enroll(client, _make_csr(common_name='first.est-approval.test')[0]))
    with approval_policy(app, est_config['id'], 'est-held-linked-twice') as pid:
        csr, _ = _make_csr(common_name='linked-twice.est-approval.test')
        _held(_enroll(client, csr))
        (approval_id, *_), = requests_of(app, pid, 'est_enroll')
        with app.app_context():
            linked_id = Certificate.query.filter_by(serial_number=str(first.serial_number)).first().id
            stale = db.session.get(ApprovalRequest, approval_id)
            with db.engine.begin() as conn:
                conn.execute(ApprovalRequest.__table__.update()
                             .where(ApprovalRequest.__table__.c.id == approval_id)
                             .values(status='approved', certificate_id=linked_id))
            with pytest.raises(RuntimeError, match='already issued'):
                protocol_approval.issue_approved(stale, json.loads(stale.request_data))
            db.session.rollback()
            assert Certificate.query.filter(
                Certificate.subject_cn == 'linked-twice.est-approval.test').count() == 0
            assert Certificate.query.filter(
                Certificate.subject_cn == 'first.est-approval.test').count() >= 1
        assert requests_of(app, pid, 'est_enroll')[0][3] == linked_id
