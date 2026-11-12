"""KB5014754 strong mapping across an EST re-enrolment and a SCEP renewal: the SID security
extension of the renewed certificate goes on the new one, never the CSR's; an enabled AD
Connector must still find the account, as on a WSTEP renewal."""
import base64

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import AttributeOID, NameOID

from models import CA, Certificate, db
from services.ad_connector import lookup as ad_lookup
from services.ca_service import CAService
from services.scep.scep_service import SCEPService
from services.trust_store.csr_operations_mixin import _SID_SECURITY_EXT_OID, _ad_security_extension
from tests.protocol_approval_support import approval_policy, approve, requests_of
from tests.test_est_rfc7030 import _post_csr, est_config  # noqa: F401
from tests.test_scep_renewal_challenge import ROTATED, _message
from tests.test_scep_rfc8894_operations import (
    FAIL_INFO_OID, PKI_STATUS_OID, _decrypt_response, _load_ca_material, _response_attributes,
)
from tests.test_wstep_strong_cert_mapping import _clear_ad_connector, _configure_ad_connector

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')

SID = 'S-1-5-21-1608104657-630783805-1473387121-1105'
OTHER_SID = 'S-1-5-21-1608104657-630783805-1473387121-500'


@pytest.fixture(autouse=True)
def _no_connector(app):
    _clear_ad_connector(app)
    yield
    _clear_ad_connector(app)


def _key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _csr(key, cn, sid=None, challenge=None):
    builder = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
    if challenge:
        builder = builder.add_attribute(AttributeOID.CHALLENGE_PASSWORD, challenge.encode())
    if sid:
        builder = builder.add_extension(_ad_security_extension(sid), critical=False)
    return builder.sign(key, hashes.SHA256())


def _issue(app, ca_id, cn, sid=SID):
    key = _key()
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        pem, _serial = CAService.sign_csr_from_crypto(ca=ca, csr=_csr(key, cn), validity_days=30,
                                                      source='test', requester_sid=sid)
    return x509.load_pem_x509_certificate(pem.encode()), key


def _sid_ext(cert):
    try:
        return cert.extensions.get_extension_for_oid(_SID_SECURITY_EXT_OID).value.value
    except x509.ExtensionNotFound:
        return None


def _count(app):
    with app.app_context():
        return Certificate.query.count()


def _est_reenrol(client, cert, key, csr_sid=None):
    cn = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
    return _post_csr(client, 'simplereenroll', _csr(key, cn, csr_sid),
                     client_cert_pem=cert.public_bytes(serialization.Encoding.PEM).decode())


def _est_leaf(response):
    assert response.status_code == 200, response.data
    certs = pkcs7.load_der_pkcs7_certificates(base64.b64decode(response.data))
    return [c for c in certs if not c.extensions.get_extension_for_oid(
        x509.ExtensionOID.BASIC_CONSTRAINTS).value.ca][0]


class TestEstReenrolment:

    def test_keeps_the_sid_extension_and_ignores_the_csr(self, client, app, est_config):
        old, key = _issue(app, est_config['id'], 'est-sid-keep.example.test')
        renewed = _est_leaf(_est_reenrol(client, old, key, csr_sid=OTHER_SID))
        assert _sid_ext(renewed) == _sid_ext(old) == _ad_security_extension(SID).value

    def test_without_the_extension_renews_without_it(self, client, app, est_config, monkeypatch):
        old, key = _issue(app, est_config['id'], 'est-sid-none.example.test', sid=None)
        _configure_ad_connector(app)
        monkeypatch.setattr(ad_lookup, 'lookup_account_by_sid', lambda sid: pytest.fail('no SID'))
        assert _sid_ext(_est_leaf(_est_reenrol(client, old, key, csr_sid=OTHER_SID))) is None

    def test_connector_without_the_account_refuses(self, client, app, est_config, monkeypatch):
        old, key = _issue(app, est_config['id'], 'est-sid-gone.example.test')
        _configure_ad_connector(app)
        monkeypatch.setattr(ad_lookup, 'lookup_account_by_sid', lambda sid: ad_lookup.NO_ACCOUNT)
        before = _count(app)
        r = _est_reenrol(client, old, key)
        assert r.status_code == 400
        assert b'The requester was not found in the directory' in r.data
        assert _count(app) == before

    def test_unreachable_directory_is_a_server_fault(self, client, app, est_config, monkeypatch):
        old, key = _issue(app, est_config['id'], 'est-sid-down.example.test')
        _configure_ad_connector(app)
        monkeypatch.setattr(ad_lookup, 'lookup_account_by_sid', lambda sid: ad_lookup.UNREACHABLE)
        before = _count(app)
        r = _est_reenrol(client, old, key)
        assert r.status_code == 500
        assert _count(app) == before

    def test_approved_reenrolment_keeps_the_sid(self, client, app, auth_client, est_config):
        old, key = _issue(app, est_config['id'], 'est-sid-held.example.test')
        with approval_policy(app, est_config['id'], 'est-held-reenroll-sid') as pid:
            assert _est_reenrol(client, old, key).status_code == 202
            (approval_id, *_), = requests_of(app, pid, 'est_enroll')
            approve(auth_client, approval_id)
            (_id, status, _data, cert_id), = requests_of(app, pid, 'est_enroll')
            assert status == 'approved' and cert_id is not None
            with app.app_context():
                renewed = x509.load_pem_x509_certificate(
                    base64.b64decode(db.session.get(Certificate, cert_id).crt))
        assert _sid_ext(renewed) == _ad_security_extension(SID).value

    def test_approved_reenrolment_checks_the_account_when_it_signs(self, client, app, auth_client,
                                                                   est_config, monkeypatch):
        old, key = _issue(app, est_config['id'], 'est-sid-held-gone.example.test')
        with approval_policy(app, est_config['id'], 'est-held-reenroll-sid-gone') as pid:
            assert _est_reenrol(client, old, key).status_code == 202
            (approval_id, *_), = requests_of(app, pid, 'est_enroll')
            _configure_ad_connector(app)
            monkeypatch.setattr(ad_lookup, 'lookup_account_by_sid', lambda sid: ad_lookup.NO_ACCOUNT)
            r = auth_client.post(f'/api/v2/approvals/{approval_id}/approve', json={'comment': 'ok'})
            assert r.get_json()['message'] == 'Request closed'
            (_id, status, _data, cert_id), = requests_of(app, pid, 'est_enroll')
            assert status == 'rejected' and cert_id is None


@pytest.fixture
def scep_ca(app, create_ca):
    ca_data = create_ca(cn='SCEP renewal SID CA')
    with app.app_context():
        yield _load_ca_material(ca_data['id'])[:2], ca_data['id']


def _scep_renew(ca, ca_cert, old, old_key, csr_sid=None):
    # A certificate SCEP did not issue renews with the endpoint's secret (RFC 8894 §2.4)
    cn = old.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
    request = _message(ca_cert, old, old_key, 17, _csr(_key(), cn, csr_sid, challenge=ROTATED))
    response, _status = SCEPService(ca.refid, challenge_password=ROTATED,
                                    auto_approve=True).process_pkcs_req(request, '127.0.0.1')
    return _response_attributes(response), response


class TestScepRenewal:

    def test_keeps_the_sid_extension_and_ignores_the_csr(self, app, scep_ca):
        (ca, ca_cert), ca_id = scep_ca
        old, old_key = _issue(app, ca_id, 'scep-sid-keep.example.test')
        attrs, response = _scep_renew(ca, ca_cert, old, old_key, csr_sid=OTHER_SID)
        assert attrs[PKI_STATUS_OID] == '0', attrs.get(FAIL_INFO_OID)
        renewed = pkcs7.load_der_pkcs7_certificates(_decrypt_response(response, old_key, old))[0]
        assert _sid_ext(renewed) == _sid_ext(old) == _ad_security_extension(SID).value

    @pytest.mark.parametrize('answer', ['NO_ACCOUNT', 'UNREACHABLE'])
    def test_connector_without_the_account_refuses(self, app, scep_ca, monkeypatch, answer):
        (ca, ca_cert), ca_id = scep_ca
        old, old_key = _issue(app, ca_id, f"scep-sid-{answer.lower().replace('_', '-')}.example.test")
        _configure_ad_connector(app)
        monkeypatch.setattr(ad_lookup, 'lookup_account_by_sid', lambda sid: getattr(ad_lookup, answer))
        before = _count(app)
        attrs, _response = _scep_renew(ca, ca_cert, old, old_key)
        assert attrs[PKI_STATUS_OID] == '2'
        assert _count(app) == before

    def _held(self, app, ca_id, cn, pid):
        with app.app_context():
            ca, ca_cert = _load_ca_material(ca_id)[:2]
        old, old_key = _issue(app, ca_id, cn)
        with app.app_context():
            attrs, _response = _scep_renew(db.session.get(CA, ca_id), ca_cert, old, old_key)
        assert attrs[PKI_STATUS_OID] == '3', attrs.get(FAIL_INFO_OID)
        (approval_id, *_), = requests_of(app, pid, 'scep_request')
        return approval_id

    def test_approved_renewal_keeps_the_sid(self, app, auth_client, scep_ca):
        _material, ca_id = scep_ca
        with approval_policy(app, ca_id, 'scep-held-renew-sid', operations=['renewal']) as pid:
            approve(auth_client, self._held(app, ca_id, 'scep-sid-held.example.test', pid))
            (_id, status, _data, cert_id), = requests_of(app, pid, 'scep_request')
            assert status == 'approved' and cert_id is not None
            with app.app_context():
                renewed = x509.load_pem_x509_certificate(
                    base64.b64decode(db.session.get(Certificate, cert_id).crt))
        assert _sid_ext(renewed) == _ad_security_extension(SID).value

    def test_approved_renewal_checks_the_account_when_it_signs(self, app, auth_client, scep_ca,
                                                               monkeypatch):
        _material, ca_id = scep_ca
        with approval_policy(app, ca_id, 'scep-held-renew-sid-gone', operations=['renewal']) as pid:
            approval_id = self._held(app, ca_id, 'scep-sid-held-gone.example.test', pid)
            _configure_ad_connector(app)
            monkeypatch.setattr(ad_lookup, 'lookup_account_by_sid', lambda sid: ad_lookup.NO_ACCOUNT)
            r = auth_client.post(f'/api/v2/approvals/{approval_id}/approve', json={'comment': 'ok'})
            assert r.get_json()['message'] == 'Request closed'
            (_id, status, _data, cert_id), = requests_of(app, pid, 'scep_request')
            assert status == 'rejected' and cert_id is None

    def test_approved_renewal_says_why_when_the_directory_does_not_answer(
            self, app, auth_client, scep_ca, monkeypatch):
        from services.ad_connector.renewal_identity import UNRESOLVED_MESSAGE
        _material, ca_id = scep_ca
        with approval_policy(app, ca_id, 'scep-held-renew-sid-down', operations=['renewal']) as pid:
            approval_id = self._held(app, ca_id, 'scep-sid-held-down.example.test', pid)
            _configure_ad_connector(app)
            monkeypatch.setattr(ad_lookup, 'lookup_account_by_sid', lambda sid: ad_lookup.UNREACHABLE)
            r = auth_client.post(f'/api/v2/approvals/{approval_id}/approve', json={'comment': 'ok'})
            assert UNRESOLVED_MESSAGE in r.get_data(as_text=True)
            (_id, status, _data, cert_id), = requests_of(app, pid, 'scep_request')
            assert status == 'pending' and cert_id is None
