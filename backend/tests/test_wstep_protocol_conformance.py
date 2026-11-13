"""MS-WSTEP message handling: CMC response, token format, RequestType, wsu:Timestamp, faults."""
import base64
import datetime

from asn1crypto import cms, core
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding
from lxml import etree

from services.ca_service import CAService
from services.wstep.cmc_response import ID_CCT_PKIRESPONSE, _CMCStatusInfoV2, _PKIResponse
from services.wstep.soap_envelope import ADDRESSING_NS, SOAP_NS, WSSE_NS, WST_NS, WSU_NS
from tests.test_wstep_issue import ISSUE_URL, _basic_auth, _build_rst, _make_csr, wstep_config  # noqa: F401
from tests.test_wstep_renew import wstep_renew_config  # noqa: F401
from tests.test_wstep_renew_tls import _cmc_renewal, _signer_info
from tests.test_wstep_renew_tls import _issue as _ca_issued, _post as _post_renewal, _renewal_csr
from tests.test_wstep_renew_tls import _rst as _renewal_rst
from tests.windows_profile_support import windows_profiles_restored  # noqa: F401

PKCS7 = 'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd#PKCS7'
PKCS10 = 'http://schemas.microsoft.com/windows/pki/2009/01/enrollment#PKCS10'
ISSUE = 'http://docs.oasis-open.org/ws-sx/ws-trust/200512/Issue'


def _rst(token_der, value_type=PKCS10, request_type=ISSUE, timestamp=None, message_id='urn:uuid:conf-1'):
    """``timestamp``: (created, expires) datetimes for a wsu:Timestamp in wsse:Security."""
    envelope = etree.fromstring(_build_rst(_make_csr()[0], message_id=message_id))
    rst = envelope.find(f'.//{{{WST_NS}}}RequestSecurityToken')
    bst = rst.find(f'{{{WSSE_NS}}}BinarySecurityToken')
    bst.set('ValueType', value_type)
    bst.text = base64.b64encode(token_der).decode()
    rt = rst.find(f'{{{WST_NS}}}RequestType')
    if request_type is None:
        rst.remove(rt)
    else:
        rt.text = request_type
    if timestamp is not None:
        header = envelope.find(f'{{{SOAP_NS}}}Header')
        security = etree.SubElement(header, f'{{{WSSE_NS}}}Security')
        ts = etree.SubElement(security, f'{{{WSU_NS}}}Timestamp')
        for tag, when in zip(('Created', 'Expires'), timestamp):
            etree.SubElement(ts, f'{{{WSU_NS}}}{tag}').text = (
                when if isinstance(when, str) else when.strftime('%Y-%m-%dT%H:%M:%SZ'))
    return etree.tostring(envelope, xml_declaration=True, encoding='UTF-8')


def _post(client, body):
    return client.post(ISSUE_URL, data=body, headers=_basic_auth())


def _fault_code(data):
    return etree.fromstring(data).find(f'.//{{{SOAP_NS}}}Fault/{{{SOAP_NS}}}Code/{{{SOAP_NS}}}Value').text


def _rstr_tokens(data):
    root = etree.fromstring(data)
    rstr = root.find(f'.//{{{WST_NS}}}RequestSecurityTokenResponse')
    issued = rstr.find(f'{{{WST_NS}}}RequestedSecurityToken/{{{WSSE_NS}}}BinarySecurityToken')
    cmc = [b for b in rstr.findall(f'{{{WSSE_NS}}}BinarySecurityToken') if b.get('ValueType') == PKCS7]
    return x509.load_der_x509_certificate(base64.b64decode(issued.text)), cmc


def _fault(data):
    root = etree.fromstring(data)
    fault = root.find(f'.//{{{SOAP_NS}}}Fault')
    assert fault is not None
    relates = root.find(f'.//{{{ADDRESSING_NS}}}RelatesTo')
    subcode = fault.find(f'{{{SOAP_NS}}}Code/{{{SOAP_NS}}}Subcode/{{{SOAP_NS}}}Value')
    return (fault.find(f'.//{{{SOAP_NS}}}Text').text, relates.text if relates is not None else None,
            subcode.text if subcode is not None else None)


def test_a_pkcs10_request_gets_a_cmc_full_pki_response(client, wstep_config):
    """MS-WSTEP 3.1.4.1.3.2 MUST; RFC 5272 6.1.1: bodyList is 1 for a Simple PKI Request."""
    csr, _key = _make_csr('conf-cmc.example.test')
    r = _post(client, _rst(csr.public_bytes(Encoding.DER)))
    assert r.status_code == 200, r.data
    cert, cmc_tokens = _rstr_tokens(r.data)
    assert len(cmc_tokens) == 1
    content_info = cms.ContentInfo.load(base64.b64decode(cmc_tokens[0].text))
    signed = content_info['content']
    assert signed['encap_content_info']['content_type'].dotted == ID_CCT_PKIRESPONSE
    response = _PKIResponse.load(signed['encap_content_info']['content'].native)
    control = response['control_sequence'][0]
    assert control['attr_type'].dotted == '1.3.6.1.5.5.7.7.25'  # id-cmc-statusInfoV2, id-cmc = id-pkix 7
    status = _CMCStatusInfoV2.load(control['attr_values'][0].dump())
    assert status['cmc_status'].native == 0
    assert [p.native for p in status['body_list']] == [1]
    assert cert.public_bytes(Encoding.DER) in [c.dump() for c in signed['certificates']]


def _pkcs10_in_signed_data(csr, key):
    """A bare PKCS#10 as the id-data content of a SignedData, with no CMC PKIData around it."""
    csr_der = csr.public_bytes(Encoding.DER)
    digest = hashes.Hash(hashes.SHA256())
    digest.update(csr_der)
    signed_attrs = cms.CMSAttributes([
        {'type': 'content_type', 'values': ['data']},
        {'type': 'message_digest', 'values': [core.OctetString(digest.finalize())]},
    ])
    sid = {'subject_key_identifier': x509.SubjectKeyIdentifier.from_public_key(key.public_key()).digest}
    return cms.ContentInfo({'content_type': 'signed_data', 'content': {
        'version': 'v3', 'digest_algorithms': [{'algorithm': 'sha256'}],
        'encap_content_info': {'content_type': 'data', 'content': csr_der},
        'signer_infos': [_signer_info(key, sid, signed_attrs)],
    }}).dump()


def _status_body_list(cmc_token):
    signed = cms.ContentInfo.load(base64.b64decode(cmc_token.text))['content']
    response = _PKIResponse.load(signed['encap_content_info']['content'].native)
    status = _CMCStatusInfoV2.load(response['control_sequence'][0]['attr_values'][0].dump())
    return [p.native for p in status['body_list']]


def test_a_pkcs10_in_a_signed_data_is_referenced_as_body_part_1(client, wstep_config):
    """RFC 5272 3.2.2: bodyPartID 0 names the current PKIData, which this request has none of."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr, _ = _make_csr('conf-p10-in-sd.example.test', key=key)
    r = _post(client, _rst(_pkcs10_in_signed_data(csr, key), value_type=PKCS7))
    assert r.status_code == 200, r.data
    _cert, cmc_tokens = _rstr_tokens(r.data)
    assert _status_body_list(cmc_tokens[0]) == [1]


def test_a_pkcs10_request_under_the_pkcs7_value_type_is_issued(client, wstep_config):
    """The MS-WSTEP 4.1.1.1 example sends a bare PKCS#10 under ValueType #PKCS7."""
    csr, key = _make_csr('conf-p10-as-p7.example.test')
    r = _post(client, _rst(csr.public_bytes(Encoding.DER), value_type=PKCS7))
    assert r.status_code == 200, r.data
    cert, _cmc = _rstr_tokens(r.data)
    assert cert.public_key().public_numbers() == key.public_key().public_numbers()


def test_a_cmc_request_under_the_pkcs10_value_type_is_unwrapped(client, wstep_config):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr, _ = _make_csr('conf-p7-as-p10.example.test', key=key)
    r = _post(client, _rst(_cmc_renewal(csr, [(key, None)]), value_type=PKCS10))
    assert r.status_code == 200, r.data
    cert, _cmc = _rstr_tokens(r.data)
    assert cert.public_key().public_numbers() == key.public_key().public_numbers()


def test_only_issue_and_query_token_status_are_served(client, wstep_config):
    """MS-WSTEP 3.1.4.2.1: absent or any other value MUST get a SOAP fault."""
    der = _make_csr('conf-rt.example.test')[0].public_bytes(Encoding.DER)
    for request_type in (None, 'http://docs.oasis-open.org/ws-sx/ws-trust/200512/Renew', 'urn:bogus'):
        r = _post(client, _rst(der, request_type=request_type))
        assert r.status_code == 400, request_type
        reason, relates_to, _sub = _fault(r.data)
        assert reason == 'Unsupported wst:RequestType: only Issue and QueryTokenStatus are served'
        assert relates_to == 'urn:uuid:conf-1'
        assert _fault_code(r.data) == 's:Sender'


def test_query_token_status_without_request_id_is_a_fault(client, wstep_config):
    """MS-WSTEP 3.1.4.2.1.2: an absent RequestID MUST get a SOAP fault."""
    der = _make_csr('conf-qts.example.test')[0].public_bytes(Encoding.DER)
    r = _post(client, _rst(der, request_type=(
        'http://schemas.microsoft.com/windows/pki/2009/01/enrollment/QueryTokenStatus')))
    assert r.status_code == 400
    assert 'RequestID' in _fault(r.data)[0]
    assert _fault_code(r.data) == 's:Sender'


def test_an_expired_message_is_refused(client, wstep_config):
    """WSS 1.1 SOAP Message Security 10: wsu:MessageExpired, past a 5 minute skew."""
    now = datetime.datetime.now(datetime.timezone.utc)
    der = _make_csr('conf-ts.example.test')[0].public_bytes(Encoding.DER)
    old = (datetime.datetime(2001, 1, 1, tzinfo=datetime.timezone.utc),
           datetime.datetime(2001, 1, 1, 0, 5, tzinfo=datetime.timezone.utc))
    r = _post(client, _rst(der, timestamp=old))
    assert r.status_code == 400
    reason, relates_to, subcode = _fault(r.data)
    assert reason == 'The message has expired (wsu:Timestamp)'
    assert subcode == 'wsse:MessageExpired' and relates_to == 'urn:uuid:conf-1'
    assert _fault_code(r.data) == 's:Sender'  # WSS 1.1 section 12: subcodes of env:Sender
    within_skew = (now - datetime.timedelta(minutes=10), now - datetime.timedelta(minutes=2))
    assert _post(client, _rst(der, timestamp=within_skew)).status_code == 200
    assert _post(client, _rst(der, timestamp=(now, 'tomorrow'))).status_code == 400


def test_the_expiry_skew_is_five_minutes(client, wstep_config):
    now = datetime.datetime.now(datetime.timezone.utc)
    der = _make_csr('conf-skew.example.test')[0].public_bytes(Encoding.DER)
    created = now - datetime.timedelta(minutes=20)
    late = _post(client, _rst(der, timestamp=(created, now - datetime.timedelta(minutes=6))))
    assert late.status_code == 400 and _fault(late.data)[2] == 'wsse:MessageExpired'
    on_time = _post(client, _rst(der, timestamp=(created, now - datetime.timedelta(minutes=4))))
    assert on_time.status_code == 200, on_time.data


def test_a_malformed_request_fault_relates_to_its_message(client, wstep_config):
    r = _post(client, _rst(b'\x30\x03\x02\x01\x00'))
    assert r.status_code == 400
    _reason, relates_to, _sub = _fault(r.data)
    assert relates_to == 'urn:uuid:conf-1'
    garbage = _rst(b'').replace(b'</wsse:BinarySecurityToken>', b'!!</wsse:BinarySecurityToken>')
    _reason, relates_to, _sub = _fault(_post(client, garbage).data)
    assert relates_to == 'urn:uuid:conf-1'



def _failing_signature(monkeypatch):
    def _sign(*_args, **_kwargs):
        raise RuntimeError('HSM unreachable')
    monkeypatch.setattr(CAService, 'sign_csr_from_crypto', staticmethod(_sign))


def test_a_signing_failure_is_a_receiver_fault(client, wstep_config, monkeypatch):
    """SOAP 1.2 HTTP binding: a failure on the CA side is env:Receiver, sent as 500."""
    _failing_signature(monkeypatch)
    r = _post(client, _rst(_make_csr('conf-hsm.example.test')[0].public_bytes(Encoding.DER)))
    assert r.status_code == 500
    assert _fault(r.data)[0] == 'Certificate issuance failed'
    assert _fault_code(r.data) == 's:Receiver'


def test_a_renewal_signing_failure_is_a_receiver_fault(client, app, wstep_renew_config, monkeypatch):
    old_cert, old_key = _ca_issued(app, wstep_renew_config['id'], 'conf-renew-hsm.example.test')
    _failing_signature(monkeypatch)
    body = _renewal_rst(_cmc_renewal(_renewal_csr(old_cert, old_key), [(old_key, old_cert)]))
    r = _post_renewal(client, body, tls_cert=old_cert)
    assert r.status_code == 500
    assert _fault(r.data)[0] == 'Certificate renewal failed'
    assert _fault_code(r.data) == 's:Receiver'
