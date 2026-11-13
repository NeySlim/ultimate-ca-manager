"""KB5014754 strong mapping across a WSTEP renewal: the SID security extension of the
renewed certificate goes on the new one, byte for byte, whatever the CSR carries; an
enabled AD Connector must still find the account, as at issuance."""
import base64

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from lxml import etree

from models import CA, Certificate, db
from services.ad_connector import lookup as ad_lookup
from services.ca_service import CAService
from services.trust_store import csr_operations_mixin
from services.trust_store.csr_operations_mixin import _SID_SECURITY_EXT_OID, _ad_security_extension
from services.wstep.soap_envelope import WSSE_NS, WST_NS
from tests.protocol_approval_support import approval_policy, approve, requests_of
from tests.test_protocol_approval_wstep import _pending, _query_rst
from tests.test_wstep_issue import _issued_cert_from_rstr, wstep_config  # noqa: F401
from tests.test_wstep_renew import RENEW_URL, _build_signed_rst, wstep_renew_config  # noqa: F401
from tests.test_wstep_renew_tls import _cmc_renewal, _key, _post, _rst
from tests.test_wstep_strong_cert_mapping import _clear_ad_connector, _configure_ad_connector
from tests.windows_profile_support import windows_profiles_restored  # noqa: F401

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')

SID = 'S-1-5-21-1608104657-630783805-1473387121-1105'
OTHER_SID = 'S-1-5-21-1608104657-630783805-1473387121-500'


@pytest.fixture(autouse=True)
def _no_connector(app):
    _clear_ad_connector(app)
    yield
    _clear_ad_connector(app)


def _issue(app, ca_id, cn, sid=SID):
    key = _key()
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
           .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
           .sign(key, hashes.SHA256()))
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        cert_pem, _serial = CAService.sign_csr_from_crypto(ca=ca, csr=csr, validity_days=30, source='wstep',
                                                           requester_sid=sid)
    return x509.load_pem_x509_certificate(cert_pem.encode()), key


def _renewal_csr(cert, key, sid=None):
    builder = (x509.CertificateSigningRequestBuilder().subject_name(cert.subject)
               .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False))
    if sid:
        builder = builder.add_extension(_ad_security_extension(sid), critical=False)
    return builder.sign(key, hashes.SHA256())


def _sid_ext(cert):
    try:
        return cert.extensions.get_extension_for_oid(_SID_SECURITY_EXT_OID)
    except x509.ExtensionNotFound:
        return None


def _renew_tls(client, old_cert, old_key, csr_sid=None):
    return _post(client, _rst(_cmc_renewal(_renewal_csr(old_cert, old_key, csr_sid), [(old_key, old_cert)])),
                 tls_cert=old_cert)


def _renew_xml(client, old_cert, old_key):
    return client.post(RENEW_URL, data=_build_signed_rst(old_cert, old_key, _renewal_csr(old_cert, old_key),
                                                         message_id='urn:uuid:renew-sid'))


def _issued(response):
    assert response.status_code == 200, response.data
    bst = etree.fromstring(response.data).find(
        f'.//{{{WST_NS}}}RequestedSecurityToken/{{{WSSE_NS}}}BinarySecurityToken')
    return x509.load_der_x509_certificate(base64.b64decode(bst.text))


def _count(app):
    with app.app_context():
        return Certificate.query.count()


@pytest.mark.parametrize('renew', [_renew_tls, _renew_xml], ids=['tls-client-cert', 'ws-security'])
def test_renewal_keeps_the_sid_extension_byte_for_byte(client, app, wstep_renew_config, renew):
    old_cert, old_key = _issue(app, wstep_renew_config['id'], f'sid-keep-{renew.__name__.strip('_').replace('_', '-')}.example.test')
    renewed = _issued(renew(client, old_cert, old_key))
    ext = _sid_ext(renewed)
    assert ext is not None and ext.critical is False
    assert ext.value.value == _sid_ext(old_cert).value.value == _ad_security_extension(SID).value


@pytest.mark.parametrize('renew', [_renew_tls, _renew_xml], ids=['tls-client-cert', 'ws-security'])
def test_a_certificate_the_ca_did_not_sign_is_refused(client, app, auth_client, wstep_renew_config,
                                                     monkeypatch, renew):
    from tests.test_protocol_renewal_sid import forged_import
    _row_id, forged, key = forged_import(app, auth_client, wstep_renew_config['id'],
                                         f'sid-forged-{renew.__name__.strip('_').replace('_', '-')}.example.test')
    with app.app_context():
        # Recorded as a Windows enrollment, so that the CA's signature is what refuses it
        db.session.get(Certificate, _row_id).source = 'wstep'
        db.session.commit()
    monkeypatch.setattr(ad_lookup, 'lookup_account_by_sid', lambda _config, sid: pytest.fail('unsigned SID'))
    _configure_ad_connector(app)
    before = _count(app)
    r = renew(client, forged, key)
    assert r.status_code == 400 and b'Signing certificate is not recognized' in r.data
    assert _count(app) == before


def test_a_sid_in_the_renewal_csr_is_ignored(client, app, wstep_renew_config):
    old_cert, old_key = _issue(app, wstep_renew_config['id'], 'sid-csr.example.test')
    renewed = _issued(_renew_tls(client, old_cert, old_key, csr_sid=OTHER_SID))
    assert _sid_ext(renewed).value.value == _ad_security_extension(SID).value


def test_a_certificate_without_the_extension_renews_without_it(client, app, wstep_renew_config, monkeypatch):
    old_cert, old_key = _issue(app, wstep_renew_config['id'], 'sid-none.example.test', sid=None)
    _configure_ad_connector(app)
    monkeypatch.setattr(ad_lookup, 'lookup_account_by_sid', lambda _config, sid: pytest.fail('no SID to resolve'))
    renewed = _issued(_renew_tls(client, old_cert, old_key, csr_sid=OTHER_SID))
    assert _sid_ext(renewed) is None


def test_an_unreadable_extension_renews_without_it(client, app, wstep_renew_config, monkeypatch):
    monkeypatch.setattr(csr_operations_mixin, '_ad_security_extension',
                        lambda sid: x509.UnrecognizedExtension(_SID_SECURITY_EXT_OID, b'\x30\x00'))
    old_cert, old_key = _issue(app, wstep_renew_config['id'], 'sid-garbled.example.test')
    monkeypatch.undo()
    assert _sid_ext(old_cert) is not None
    renewed = _issued(_renew_tls(client, old_cert, old_key))
    assert _sid_ext(renewed) is None


def test_connector_finds_the_account_and_the_sid_is_kept(client, app, wstep_renew_config, monkeypatch):
    old_cert, old_key = _issue(app, wstep_renew_config['id'], 'sid-found.example.test')
    _configure_ad_connector(app)
    asked = []
    monkeypatch.setattr(ad_lookup, 'lookup_account_by_sid', lambda _config, sid: asked.append(sid) or 'WIN11$')
    renewed = _issued(_renew_tls(client, old_cert, old_key, csr_sid=OTHER_SID))
    assert asked == [SID]
    assert _sid_ext(renewed).value.value == _ad_security_extension(SID).value


def test_connector_without_the_account_refuses(client, app, wstep_renew_config, monkeypatch):
    old_cert, old_key = _issue(app, wstep_renew_config['id'], 'sid-gone.example.test')
    _configure_ad_connector(app)
    monkeypatch.setattr(ad_lookup, 'lookup_account_by_sid', lambda _config, sid: ad_lookup.NO_ACCOUNT)
    before = _count(app)
    r = _renew_tls(client, old_cert, old_key)
    assert r.status_code == 400
    assert b'The requester was not found in the directory' in r.data
    assert _count(app) == before


@pytest.mark.parametrize('renew', [_renew_tls, _renew_xml], ids=['tls-client-cert', 'ws-security'])
def test_unreachable_directory_is_a_server_fault(client, app, wstep_renew_config, monkeypatch, renew):
    old_cert, old_key = _issue(app, wstep_renew_config['id'], f'sid-down-{renew.__name__.strip('_').replace('_', '-')}.example.test')
    _configure_ad_connector(app)
    monkeypatch.setattr(ad_lookup, 'lookup_account_by_sid', lambda _config, sid: ad_lookup.UNREACHABLE)
    before = _count(app)
    r = renew(client, old_cert, old_key)
    assert r.status_code == 500
    assert b'Could not resolve requester identity for strong certificate mapping' in r.data
    assert _count(app) == before


def test_a_directory_object_without_an_account_name_refuses(client, app, wstep_renew_config, monkeypatch):
    """A foreignSecurityPrincipal carries the SID but is no account of this directory."""
    from tests.test_ad_connector_lookup import _FakeConnection, _FakeEntry

    old_cert, old_key = _issue(app, wstep_renew_config['id'], 'sid-fsp.example.test')
    _configure_ad_connector(app)
    fsp = _FakeEntry({'objectSid': ad_lookup._sid_string_to_bytes(SID)})
    fsp.entry_dn = f'CN={SID},CN=ForeignSecurityPrincipals,DC=lab'
    monkeypatch.setattr(ad_lookup, '_connect', lambda config: _FakeConnection(entries=[fsp]))
    before = _count(app)
    r = _renew_tls(client, old_cert, old_key)
    assert r.status_code == 400
    assert b'The requester was not found in the directory' in r.data
    assert _count(app) == before


def test_approved_renewal_keeps_the_sid(app, client, auth_client, wstep_config):
    old_cert, old_key = _issue(app, wstep_config['id'], 'sid-held.wstep-approval.test')
    with approval_policy(app, wstep_config['id'], 'wstep-held-renew-sid') as pid:
        request_id = _pending(_renew_tls(client, old_cert, old_key, csr_sid=OTHER_SID))
        (approval_id, *_), = requests_of(app, pid, 'wstep_request')
        approve(auth_client, approval_id)
        issued = _post(client, _query_rst(request_id), tls_cert=old_cert)
        assert issued.status_code == 200, issued.data
        renewed = _issued_cert_from_rstr(issued.data)
    assert _sid_ext(renewed).value.value == _ad_security_extension(SID).value


def test_approved_renewal_checks_the_account_when_it_signs(app, client, auth_client, wstep_config,
                                                           monkeypatch):
    """The SID is read and resolved at signing, not frozen when the request was held."""
    old_cert, old_key = _issue(app, wstep_config['id'], 'sid-held-gone.wstep-approval.test')
    with approval_policy(app, wstep_config['id'], 'wstep-held-renew-sid-gone') as pid:
        _pending(_renew_tls(client, old_cert, old_key))
        (approval_id, *_), = requests_of(app, pid, 'wstep_request')
        _configure_ad_connector(app)
        monkeypatch.setattr(ad_lookup, 'lookup_account_by_sid', lambda _config, sid: ad_lookup.NO_ACCOUNT)
        r = auth_client.post(f'/api/v2/approvals/{approval_id}/approve', json={'comment': 'ok'})
        assert r.get_json()['message'] == 'Request closed'
        (_id, status, data, cert_id), = requests_of(app, pid, 'wstep_request')
        assert status == 'rejected' and cert_id is None
