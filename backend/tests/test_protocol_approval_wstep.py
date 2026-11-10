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
from tests.protocol_approval_support import (approval_policy, approve, expire, profile_of, reject,
                                             requests_of)
from tests.test_wstep_issue import (  # noqa: F401
    ISSUE_URL, _basic_auth, _build_rst, _issued_cert_from_rstr, _make_csr, wstep_config,
)
from tests.test_wstep_renew_tls import _cmc_renewal, _issue, _post, _renewal_csr, _rst

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
        assert 'not a known machine' in reason
        assert invalid == 'true' and echoed == request_id


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
