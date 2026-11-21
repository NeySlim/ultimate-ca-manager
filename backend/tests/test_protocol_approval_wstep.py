"""WSTEP requests held by a policy requiring approval (MS-WSTEP 3.1.4.2.1).

A held Issue is answered by a pending RSTR carrying a RequestID and a CMC
response marking it pending; QueryTokenStatus with that RequestID then
returns the pending RSTR, the certificate once approved, or a fault with
InvalidRequest once denied.
"""
import base64

from lxml import etree

from models import Certificate
from services.wstep.soap_envelope import ADDRESSING_NS, SOAP_NS, WSSE_NS, WST_NS, WSTEP_NS
from tests.protocol_approval_support import made_rows_removed  # noqa: F401
from tests.protocol_approval_support import (approval_policy, approve, expire, profile_of, reject,
                                             requests_of)
from tests.test_wstep_issue import (  # noqa: F401
    ISSUE_URL, _basic_auth, _build_rst, _issued_cert_from_rstr, _make_csr, wstep_config,
)
from tests.test_wstep_renew_tls import _cmc_renewal, _issue, _post, _renewal_csr, _rst
from tests.windows_profile_support import windows_profiles_restored  # noqa: F401

QUERY_TOKEN_STATUS = 'http://schemas.microsoft.com/windows/pki/2009/01/enrollment/QueryTokenStatus'


def _query_rst(request_id):
    """The MS-WSTEP 4.1.3.1 QueryTokenStatus request."""
    nsmap = {'s': SOAP_NS, 'a': ADDRESSING_NS, 'wst': WST_NS}
    envelope = etree.Element('{%s}Envelope' % SOAP_NS, nsmap=nsmap)
    header = etree.SubElement(envelope, '{%s}Header' % SOAP_NS)
    etree.SubElement(header, '{%s}MessageID' % ADDRESSING_NS).text = 'urn:uuid:query-1'
    body = etree.SubElement(envelope, '{%s}Body' % SOAP_NS)
    rst = etree.SubElement(body, '{%s}RequestSecurityToken' % WST_NS)
    etree.SubElement(rst, '{%s}TokenType' % WST_NS).text = (
        'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-x509-token-profile-1.0#X509v3')
    etree.SubElement(rst, '{%s}RequestType' % WST_NS).text = QUERY_TOKEN_STATUS
    etree.SubElement(rst, '{%s}RequestID' % WSTEP_NS).text = str(request_id)
    return etree.tostring(envelope, xml_declaration=True, encoding='UTF-8')


def _issue_rst(client, csr):
    return client.post(ISSUE_URL, data=_build_rst(csr), headers=_basic_auth())


def _query(client, request_id):
    return client.post(ISSUE_URL, data=_query_rst(request_id), headers=_basic_auth())


def _pending(response):
    """The RequestID of a pending RSTR, after checking its shape."""
    assert response.status_code == 200, response.data
    root = etree.fromstring(response.data)
    rstr = root.find(f'.//{{{WST_NS}}}RequestSecurityTokenResponse')
    assert rstr.find(f'{{{WSTEP_NS}}}DispositionMessage').text == 'Pending'
    assert rstr.find(f'{{{WST_NS}}}RequestedSecurityToken') is None
    cmc = rstr.find(f'{{{WSSE_NS}}}BinarySecurityToken')
    from services.wstep.cmc_response import _ContentInfo, _PendingStatusInfoV2, _PKIResponse
    signed = _ContentInfo.load(base64.b64decode(cmc.text))['content']
    assert len(signed['certificates']) == 0
    pki_response = _PKIResponse.load(signed['encap_content_info']['content'].native)
    status = _PendingStatusInfoV2.load(pki_response['control_sequence'][0]['attr_values'][0].dump())
    assert status['cmc_status'].native == 3  # RFC 5272 CMCStatus pending
    assert status['pend_info']['pend_token'].native == rstr.find(f'{{{WSTEP_NS}}}RequestID').text.encode()
    return rstr.find(f'{{{WSTEP_NS}}}RequestID').text


def _fault(response):
    assert response.status_code == 400, response.data
    root = etree.fromstring(response.data)
    detail = root.find(f'.//{{{SOAP_NS}}}Detail/{{{WSTEP_NS}}}CertificateEnrollmentWSDetail')
    return (root.find(f'.//{{{SOAP_NS}}}Reason/{{{SOAP_NS}}}Text').text,
            detail.find(f'{{{WSTEP_NS}}}InvalidRequest').text,
            detail.find(f'{{{WSTEP_NS}}}RequestID').text)


def test_without_policy_issue_is_immediate(client, wstep_config):
    csr, _ = _make_csr(common_name='free.wstep-approval.test')
    _issued_cert_from_rstr(_issue_rst(client, csr).data)


def test_held_issue_then_query_until_issued(app, client, auth_client, wstep_config):
    with approval_policy(app, wstep_config['id'], 'wstep-held-issue') as pid:
        csr, _ = _make_csr(common_name='held.wstep-approval.test')
        request_id = _pending(_issue_rst(client, csr))
        (approval_id, status, data, _c), = requests_of(app, pid, 'wstep_request')
        assert request_id == str(approval_id) and status == 'pending'
        assert data['identity'] == 'user:wstep-test' and data['operation'] == 'issue'

        assert _pending(_query(client, request_id)) == request_id
        approve(auth_client, approval_id)
        issued = _query(client, request_id)
        assert issued.status_code == 200, issued.data
        root = etree.fromstring(issued.data)
        assert root.find(f'.//{{{WSTEP_NS}}}DispositionMessage').text == 'Issued'
        assert root.find(f'.//{{{WSTEP_NS}}}RequestID').text == request_id
        cert = _issued_cert_from_rstr(issued.data)
        assert cert.public_key() == csr.public_key()
        with app.app_context():
            assert Certificate.query.filter_by(serial_number=str(cert.serial_number)).first().source == 'wstep'


def test_query_is_denied_after_rejection(app, client, auth_client, wstep_config):
    with approval_policy(app, wstep_config['id'], 'wstep-held-reject') as pid:
        csr, _ = _make_csr(common_name='refused.wstep-approval.test')
        request_id = _pending(_issue_rst(client, csr))
        (approval_id, *_), = requests_of(app, pid, 'wstep_request')
        reject(auth_client, approval_id, 'not a known machine')
        reason, invalid, echoed = _fault(_query(client, request_id))
        assert reason == 'Rejected by an approver'
        assert invalid == 'true' and echoed == request_id


def test_query_is_denied_when_the_approved_certificate_went_away(app, client, auth_client, wstep_config):
    from tests.test_protocol_approval_est import _withdraw
    with approval_policy(app, wstep_config['id'], 'wstep-held-withdrawn') as pid:
        csr, _ = _make_csr(common_name='withdrawn.wstep-approval.test')
        request_id = _pending(_issue_rst(client, csr))
        (approval_id, *_), = requests_of(app, pid, 'wstep_request')
        approve(auth_client, approval_id)
        _withdraw(app, approval_id)
        reason, invalid, echoed = _fault(_query(client, request_id))
        assert reason == 'Certificate withdrawn'
        assert invalid == 'true' and echoed == request_id
        assert requests_of(app, pid, 'wstep_request')[0][1] == 'rejected'


def test_query_is_denied_after_expiry(app, client, wstep_config):
    with approval_policy(app, wstep_config['id'], 'wstep-held-expire') as pid:
        csr, _ = _make_csr(common_name='late.wstep-approval.test')
        request_id = _pending(_issue_rst(client, csr))
        (approval_id, *_), = requests_of(app, pid, 'wstep_request')
        expire(app, approval_id)
        _reason, invalid, _echo = _fault(_query(client, request_id))
        assert invalid == 'true'


def test_unknown_request_id_is_a_fault(client, wstep_config):
    _reason, invalid, echoed = _fault(_query(client, 999999))
    assert invalid == 'false' and echoed == '999999'


def test_query_without_request_id_is_a_fault(client, wstep_config):
    body = _query_rst('').replace(b'<wstep:RequestID', b'<wstep:Ignored').replace(
        b'</wstep:RequestID', b'</wstep:Ignored')
    assert client.post(ISSUE_URL, data=body, headers=_basic_auth()).status_code == 400


def test_held_renewal_then_query(app, client, auth_client, wstep_config):
    old_cert, old_key = _issue(app, wstep_config['id'], 'renew.wstep-approval.test')
    body = _rst(_cmc_renewal(_renewal_csr(old_cert, old_key), [(old_key, old_cert)]))
    with approval_policy(app, wstep_config['id'], 'wstep-held-renew') as pid:
        request_id = _pending(_post(client, body, tls_cert=old_cert))
        (approval_id, _s, data, _c), = requests_of(app, pid, 'wstep_request')
        assert data['operation'] == 'renew' and data['renewal'] is True
        approve(auth_client, approval_id)
        issued = _post(client, _query_rst(request_id), tls_cert=old_cert)
        assert issued.status_code == 200, issued.data
        renewed = _issued_cert_from_rstr(issued.data)
        assert renewed.subject == old_cert.subject and renewed.serial_number != old_cert.serial_number
        assert profile_of(renewed)['eku'] == profile_of(old_cert)['eku']
        with app.app_context():
            old_row = Certificate.query.filter_by(serial_number=str(old_cert.serial_number)).first()
            assert old_row.archived


def test_another_requester_cannot_query(app, client, wstep_config):
    old_cert, _key = _issue(app, wstep_config['id'], 'stranger.wstep-approval.test')
    with approval_policy(app, wstep_config['id'], 'wstep-held-stranger'):
        csr, _ = _make_csr(common_name='mine.wstep-approval.test')
        request_id = _pending(_issue_rst(client, csr))
        r = _post(client, _query_rst(request_id), tls_cert=old_cert)
        assert _fault(r)[0] == 'Unknown RequestID'


def test_approved_issue_matches_a_direct_one(app, client, auth_client, wstep_config):
    direct_csr, _ = _make_csr(common_name='same.wstep-approval.test')
    direct = _issued_cert_from_rstr(_issue_rst(client, direct_csr).data)
    with approval_policy(app, wstep_config['id'], 'wstep-held-compare') as pid:
        csr, _ = _make_csr(common_name='same.wstep-approval.test')
        request_id = _pending(_issue_rst(client, csr))
        (approval_id, *_), = requests_of(app, pid, 'wstep_request')
        approve(auth_client, approval_id)
        approved = _issued_cert_from_rstr(_query(client, request_id).data)
    assert profile_of(approved) == profile_of(direct)
    with app.app_context():
        rows = [Certificate.query.filter_by(serial_number=str(c.serial_number)).first()
                for c in (direct, approved)]
        assert [r.source for r in rows] == ['wstep', 'wstep']
        assert rows[0].template_id == rows[1].template_id


def test_unreadable_policies_refuse(client, wstep_config, monkeypatch):
    from services.policy_service import PolicyEvaluationService

    def broken(*a, **k):
        raise RuntimeError('policy table unreadable')
    monkeypatch.setattr(PolicyEvaluationService, 'check_approval_required', broken)
    csr, _ = _make_csr(common_name='broken.wstep-approval.test')
    assert _issue_rst(client, csr).status_code == 500


def test_parsed_query_carries_its_request_id():
    from services.wstep.rst_parser import REQUEST_TYPE_QUERY_TOKEN_STATUS, parse_rst
    parsed = parse_rst(_query_rst(65))
    assert parsed.request_type == REQUEST_TYPE_QUERY_TOKEN_STATUS
    assert parsed.request_id == '65' and parsed.csr_der is None


def test_renewal_approved_then_revoked_is_refused(app, client, auth_client, wstep_config):
    from models import db
    old_cert, old_key = _issue(app, wstep_config['id'], 'renew-revoked.wstep-approval.test')
    body = _rst(_cmc_renewal(_renewal_csr(old_cert, old_key), [(old_key, old_cert)]))
    with approval_policy(app, wstep_config['id'], 'wstep-held-renew-revoked') as pid:
        request_id = _pending(_post(client, body, tls_cert=old_cert))
        (approval_id, *_), = requests_of(app, pid, 'wstep_request')
        approve(auth_client, approval_id)
        with app.app_context():
            row = Certificate.query.filter_by(serial_number=str(old_cert.serial_number)).first()
            row.revoked = True
            db.session.commit()
        reason, invalid, echoed = _fault(_post(client, _query_rst(request_id), tls_cert=old_cert))
        assert reason == 'Renewed certificate revoked'
        assert invalid == 'true' and echoed == request_id
        (_id, status, data, _cert), = requests_of(app, pid, 'wstep_request')
        assert status == 'rejected' and data['closed_reason'] == 'Renewed certificate revoked'


def test_an_approval_is_never_seen_without_its_certificate(app, client, auth_client, wstep_config,
                                                           monkeypatch):
    from tests.test_protocol_approval_est import _retry_while_linking
    with approval_policy(app, wstep_config['id'], 'wstep-held-linking') as pid:
        csr, _ = _make_csr(common_name='linking.wstep-approval.test')
        request_id = _pending(_issue_rst(client, csr))
        (approval_id, *_), = requests_of(app, pid, 'wstep_request')
        heard = _retry_while_linking(app, monkeypatch, lambda c: _query(c, request_id))
        approve(auth_client, approval_id)
        assert heard[0].status_code == 200, heard[0].data
        assert _issued_cert_from_rstr(heard[0].data).public_key() == csr.public_key()
        (_id, status, _data, cert_id), = requests_of(app, pid, 'wstep_request')
        assert status == 'approved' and cert_id is not None


def test_a_renewal_approval_is_never_seen_without_its_certificate(app, client, auth_client, wstep_config,
                                                                  monkeypatch):
    from tests.test_protocol_approval_est import _retry_while_linking
    old_cert, old_key = _issue(app, wstep_config['id'], 'linking-renew.wstep-approval.test')
    body = _rst(_cmc_renewal(_renewal_csr(old_cert, old_key), [(old_key, old_cert)]))
    with approval_policy(app, wstep_config['id'], 'wstep-held-linking-renew') as pid:
        request_id = _pending(_post(client, body, tls_cert=old_cert))
        (approval_id, *_), = requests_of(app, pid, 'wstep_request')
        heard = _retry_while_linking(
            app, monkeypatch, lambda c: _post(c, _query_rst(request_id), tls_cert=old_cert))
        approve(auth_client, approval_id)
        assert heard[0].status_code == 200, heard[0].data
        assert _issued_cert_from_rstr(heard[0].data).subject == old_cert.subject


def test_a_renewal_refused_at_issuance_is_announced_as_such(app, client, auth_client, wstep_config):
    """Closed by the issuance (renewed certificate revoked while held), not by an approver."""
    from models import db
    old_cert, old_key = _issue(app, wstep_config['id'], 'renew-refused.wstep-approval.test')
    body = _rst(_cmc_renewal(_renewal_csr(old_cert, old_key), [(old_key, old_cert)]))
    with approval_policy(app, wstep_config['id'], 'wstep-held-renew-refused') as pid:
        request_id = _pending(_post(client, body, tls_cert=old_cert))
        (approval_id, *_), = requests_of(app, pid, 'wstep_request')
        with app.app_context():
            row = Certificate.query.filter_by(serial_number=str(old_cert.serial_number)).first()
            row.revoked = True
            db.session.commit()
        r = auth_client.post(f'/api/v2/approvals/{approval_id}/approve', json={'comment': 'ok'})
        assert r.get_json()['message'] == 'Request closed'
        reason, invalid, _echo = _fault(_post(client, _query_rst(request_id), tls_cert=old_cert))
        assert reason == 'Refused at issuance' and invalid == 'true'


def test_renewal_approved_then_renewed_row_deleted_is_delivered(app, client, auth_client, wstep_config):
    """Only a revocation refuses an approved renewal: a renewed certificate
    no longer on record (UNKNOWN) lets the approved one through."""
    from models import db
    from tests.protocol_approval_support import _delete_with_dependents
    old_cert, old_key = _issue(app, wstep_config['id'], 'renew-unknown.wstep-approval.test')
    body = _rst(_cmc_renewal(_renewal_csr(old_cert, old_key), [(old_key, old_cert)]))
    with approval_policy(app, wstep_config['id'], 'wstep-held-renew-unknown') as pid:
        request_id = _pending(_post(client, body, tls_cert=old_cert))
        (approval_id, *_), = requests_of(app, pid, 'wstep_request')
        approve(auth_client, approval_id)
        with app.app_context():
            old_id = Certificate.query.filter_by(serial_number=str(old_cert.serial_number)).first().id
            _delete_with_dependents(Certificate, {'id': [old_id]})
            db.session.commit()
        issued = _post(client, _query_rst(request_id), tls_cert=old_cert)
        assert issued.status_code == 200, issued.data
        assert _issued_cert_from_rstr(issued.data).subject == old_cert.subject
        assert requests_of(app, pid, 'wstep_request')[0][1] == 'approved'


def test_a_delivered_issue_is_never_judged_again(app, client, auth_client, wstep_config, monkeypatch):
    """A second QueryTokenStatus after delivery whose certificate went away
    is told so, without closing the delivered request or a webhook."""
    from services import webhook_service
    from tests.test_protocol_approval_est import _withdraw
    emitted = []
    monkeypatch.setattr(webhook_service, 'emit_csr_rejected',
                        lambda *a, **k: emitted.append(a))
    with approval_policy(app, wstep_config['id'], 'wstep-held-delivered') as pid:
        csr, _ = _make_csr(common_name='delivered.wstep-approval.test')
        request_id = _pending(_issue_rst(client, csr))
        (approval_id, *_), = requests_of(app, pid, 'wstep_request')
        approve(auth_client, approval_id)
        first = _issued_cert_from_rstr(_query(client, request_id).data)
        again = _issued_cert_from_rstr(_query(client, request_id).data)
        assert again.serial_number == first.serial_number
        _withdraw(app, approval_id)
        reason, _invalid, echoed = _fault(_query(client, request_id))
        assert reason == 'Certificate withdrawn' and echoed == request_id
        (_id, status, data, _cert), = requests_of(app, pid, 'wstep_request')
        assert status == 'approved' and data['delivered_at'] and 'closed_reason' not in data
        assert emitted == []


def _issue_already_linked(app, approval_id, linked_serial):
    """Issue *approval_id* from a copy read before another issuance linked
    it to the certificate *linked_serial*."""
    import json

    import pytest

    from models import db
    from models.policy import ApprovalRequest
    from services import protocol_approval
    with app.app_context():
        linked_id = Certificate.query.filter_by(serial_number=str(linked_serial)).first().id
        stale = db.session.get(ApprovalRequest, approval_id)
        with db.engine.begin() as conn:
            conn.execute(ApprovalRequest.__table__.update()
                         .where(ApprovalRequest.__table__.c.id == approval_id)
                         .values(status='approved', certificate_id=linked_id))
        with pytest.raises(RuntimeError, match='already issued'):
            protocol_approval.issue_approved(stale, json.loads(stale.request_data))
        db.session.rollback()
    return linked_id


def test_an_issue_already_linked_tells_the_approver_why(app, client, wstep_config):
    first = _issued_cert_from_rstr(_issue_rst(client, _make_csr(common_name='first.wstep-approval.test')[0]).data)
    with approval_policy(app, wstep_config['id'], 'wstep-held-linked-twice') as pid:
        csr, _ = _make_csr(common_name='linked-twice.wstep-approval.test')
        _pending(_issue_rst(client, csr))
        (approval_id, *_), = requests_of(app, pid, 'wstep_request')
        linked_id = _issue_already_linked(app, approval_id, first.serial_number)
        assert requests_of(app, pid, 'wstep_request')[0][3] == linked_id


def test_a_renewal_already_linked_tells_the_approver_why(app, client, wstep_config):
    old_cert, old_key = _issue(app, wstep_config['id'], 'renew-linked.wstep-approval.test')
    other, _k = _issue(app, wstep_config['id'], 'renew-linked-other.wstep-approval.test')
    body = _rst(_cmc_renewal(_renewal_csr(old_cert, old_key), [(old_key, old_cert)]))
    with approval_policy(app, wstep_config['id'], 'wstep-held-renew-linked') as pid:
        _pending(_post(client, body, tls_cert=old_cert))
        (approval_id, *_), = requests_of(app, pid, 'wstep_request')
        linked_id = _issue_already_linked(app, approval_id, other.serial_number)
        assert requests_of(app, pid, 'wstep_request')[0][3] == linked_id


def _profile_enabled(app, enabled):
    from models import db
    from tests.windows_profile_support import default_profile
    with app.app_context():
        default_profile().enabled = enabled
        db.session.commit()


def test_an_approval_after_the_profile_was_disabled_is_refused(app, client, auth_client, wstep_config):
    """Disabled while held: the approved request is refused like any other refused at issuance,
    never signed with a validity of its own."""
    with approval_policy(app, wstep_config['id'], 'wstep-held-profile-off') as pid:
        csr, _ = _make_csr(common_name='profile-off.wstep-approval.test')
        request_id = _pending(_issue_rst(client, csr))
        (approval_id, *_), = requests_of(app, pid, 'wstep_request')
        _profile_enabled(app, False)
        try:
            r = auth_client.post(f'/api/v2/approvals/{approval_id}/approve', json={'comment': 'ok'})
            assert r.get_json()['message'] == 'Request closed', r.get_json()
        finally:
            _profile_enabled(app, True)
        reason, invalid, _echo = _fault(_query(client, request_id))
        assert reason == 'Refused at issuance' and invalid == 'true'

