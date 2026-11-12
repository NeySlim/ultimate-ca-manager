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


def forged_import(app, auth_client, ca_id, cn, sid=SID, with_key=False):
    """A certificate naming the CA as issuer (DN and AKI) and carrying ``sid``, signed by
    another key, on a row linked to that CA as an earlier release's import left it."""
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID
    from utils.datetime_utils import utc_now
    from datetime import timedelta
    with app.app_context():
        ca_cert = x509.load_pem_x509_certificate(base64.b64decode(db.session.get(CA, ca_id).crt))
    key, forger = _key(), ec.generate_private_key(ec.SECP256R1())
    now = utc_now()
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
            .issuer_name(ca_cert.subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=30))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_subject_key_identifier(
                ca_cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value), critical=False)
            .add_extension(_ad_security_extension(sid), critical=False)
            .sign(forger, hashes.SHA256()))
    pem = cert.public_bytes(serialization.Encoding.PEM)
    if with_key:
        pem += key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                 serialization.NoEncryption())
    # The import refuses to link it: the link is the one an earlier release stored
    r = auth_client.post('/api/v2/certificates/import',
                         data={'pem_content': pem.decode(), 'name': cn},
                         content_type='multipart/form-data')
    assert r.status_code in (200, 201), r.get_json()
    with app.app_context():
        row = db.session.get(Certificate, r.get_json()['data']['id'])
        assert row.caref is None
        row.caref = db.session.get(CA, ca_id).refid
        db.session.commit()
        return row.id, cert, key


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

    def test_a_certificate_the_ca_did_not_sign_is_refused(self, client, app, auth_client,
                                                         est_config, monkeypatch):
        _row_id, forged, key = forged_import(app, auth_client, est_config['id'], 'est-sid-forged.example.test')
        monkeypatch.setattr(ad_lookup, 'lookup_account_by_sid', lambda sid: pytest.fail('unsigned SID'))
        _configure_ad_connector(app)
        before = _count(app)
        assert _est_reenrol(client, forged, key).status_code == 403
        assert _count(app) == before

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

    def test_unreachable_directory_asks_to_retry_later(self, client, app, est_config, monkeypatch):
        """RFC 9110 §15.6.4: a passing outage is a 503 that may name when to come back."""
        from api.est_protocol import EST_RETRY_AFTER_DEFAULT
        old, key = _issue(app, est_config['id'], 'est-sid-down.example.test')
        _configure_ad_connector(app)
        monkeypatch.setattr(ad_lookup, 'lookup_account_by_sid', lambda sid: ad_lookup.UNREACHABLE)
        before = _count(app)
        r = _est_reenrol(client, old, key)
        assert r.status_code == 503
        assert r.headers['Retry-After'] == str(EST_RETRY_AFTER_DEFAULT)
        assert _count(app) == before


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

    def test_a_certificate_the_ca_did_not_sign_is_refused(self, app, auth_client, scep_ca):
        """SCEP checks the signer's signature with the CA key before any lookup by bytes."""
        (ca, ca_cert), ca_id = scep_ca
        _row_id, forged, key = forged_import(app, auth_client, ca_id, 'scep-sid-forged.example.test')
        before = _count(app)
        attrs, _response = _scep_renew(ca, ca_cert, forged, key)
        assert attrs[PKI_STATUS_OID] == '2'
        assert _count(app) == before

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

    def _held(self, app, ca_id, cn):
        """A RenewalReq left pending, as an endpoint without auto-approval leaves it: its row id."""
        from models import SCEPRequest
        old, old_key = _issue(app, ca_id, cn)
        with app.app_context():
            ca = db.session.get(CA, ca_id)
            ca_cert = _load_ca_material(ca_id)[1]
            request = _message(ca_cert, old, old_key, 17, _csr(_key(), cn, challenge=ROTATED))
            response, _status = SCEPService(ca.refid, challenge_password=ROTATED,
                                            auto_approve=False).process_pkcs_req(request, '127.0.0.1')
            assert _response_attributes(response)[PKI_STATUS_OID] == '3'
            row = SCEPRequest.query.filter_by(ca_refid=ca.refid, subject=f'CN={cn}').one()
            self._rows.append(row.id)
            return row.id

    @pytest.fixture(autouse=True)
    def _drop_requests(self, app):
        from models import SCEPRequest
        self._rows = []
        yield
        with app.app_context():
            SCEPRequest.query.filter(SCEPRequest.id.in_(self._rows)).delete(synchronize_session=False)
            db.session.commit()

    def _approve(self, auth_client, req_id):
        return auth_client.post(f'/api/v2/scep/{req_id}/approve', data='{}', content_type='application/json')

    def test_approved_renewal_keeps_the_sid(self, app, auth_client, scep_ca):
        from models import SCEPRequest
        _material, ca_id = scep_ca
        req_id = self._held(app, ca_id, 'scep-sid-held.example.test')
        r = self._approve(auth_client, req_id)
        assert r.status_code == 200, r.get_json()
        with app.app_context():
            row = Certificate.query.filter_by(refid=db.session.get(SCEPRequest, req_id).cert_refid).one()
            renewed = x509.load_pem_x509_certificate(base64.b64decode(row.crt))
        assert _sid_ext(renewed) == _ad_security_extension(SID).value

    def test_approved_renewal_checks_the_account_when_it_signs(self, app, auth_client, scep_ca,
                                                               monkeypatch):
        """The SID is read and resolved at approval, not frozen when the request was held."""
        from models import SCEPRequest
        _material, ca_id = scep_ca
        req_id = self._held(app, ca_id, 'scep-sid-held-gone.example.test')
        _configure_ad_connector(app)
        monkeypatch.setattr(ad_lookup, 'lookup_account_by_sid', lambda sid: ad_lookup.NO_ACCOUNT)
        before = _count(app)
        r = self._approve(auth_client, req_id)
        assert r.status_code == 400
        assert 'The requester was not found in the directory' in r.get_json()['message']
        assert _count(app) == before
        with app.app_context():
            assert db.session.get(SCEPRequest, req_id).status == 'rejected'

    def test_approved_renewal_says_why_when_the_directory_does_not_answer(
            self, app, auth_client, scep_ca, monkeypatch):
        from models import SCEPRequest
        from services.ad_connector.renewal_identity import UNRESOLVED_MESSAGE
        _material, ca_id = scep_ca
        req_id = self._held(app, ca_id, 'scep-sid-held-down.example.test')
        _configure_ad_connector(app)
        monkeypatch.setattr(ad_lookup, 'lookup_account_by_sid', lambda sid: ad_lookup.UNREACHABLE)
        r = self._approve(auth_client, req_id)
        assert r.status_code == 503
        assert UNRESOLVED_MESSAGE in r.get_json()['message']
        with app.app_context():
            row = db.session.get(SCEPRequest, req_id)
            assert row.status == 'pending' and row.cert_refid is None


def test_a_certificate_the_ca_did_not_sign_carries_no_sid(app, auth_client, create_ca):
    """The row's link to the CA is not proof: only the signature is."""
    from services.ad_connector import renewal_identity
    ca_data = create_ca(cn='SID forged issuer CA')
    _row_id, forged, _key_ = forged_import(app, auth_client, ca_data['id'], 'sid-forged-unit.example.test')
    with app.app_context():
        ca_cert = x509.load_pem_x509_certificate(base64.b64decode(db.session.get(CA, ca_data['id']).crt))
        assert renewal_identity.renewal_requester_sid(forged, ca_cert, 'TEST') is None


class TestScepManualApproval:
    """The SCEP queue's own approval, no policy holding the request."""

    def _pending(self, app, scep_ca, cn):
        (ca, ca_cert), ca_id = scep_ca
        old, old_key = _issue(app, ca_id, cn)
        request = _message(ca_cert, old, old_key, 17, _csr(_key(), cn, challenge=ROTATED))
        response, _status = SCEPService(ca.refid, challenge_password=ROTATED,
                                        auto_approve=False).process_pkcs_req(request, '127.0.0.1')
        assert _response_attributes(response)[PKI_STATUS_OID] == '3'
        from models import SCEPRequest
        return SCEPRequest.query.filter_by(ca_refid=ca.refid, status='pending').one().id

    def _status(self, request_id):
        from models import SCEPRequest
        db.session.expire_all()
        row = db.session.get(SCEPRequest, request_id)
        return row.status, row.rejection_reason

    def test_unreachable_directory_answers_503_and_leaves_it_pending(self, app, auth_client, scep_ca,
                                                                     monkeypatch):
        from services.ad_connector.renewal_identity import UNRESOLVED_MESSAGE
        request_id = self._pending(app, scep_ca, 'scep-manual-sid-down.example.test')
        _configure_ad_connector(app)
        monkeypatch.setattr(ad_lookup, 'lookup_account_by_sid', lambda sid: ad_lookup.UNREACHABLE)
        before = _count(app)
        r = auth_client.post(f'/api/v2/scep/{request_id}/approve', json={})
        assert r.status_code == 503
        assert UNRESOLVED_MESSAGE in r.get_data(as_text=True)
        assert self._status(request_id) == ('pending', None)
        assert _count(app) == before

    def test_account_gone_closes_the_request_with_its_reason(self, app, auth_client, scep_ca, monkeypatch):
        from services.ad_connector.renewal_identity import NOT_FOUND_MESSAGE
        request_id = self._pending(app, scep_ca, 'scep-manual-sid-gone.example.test')
        _configure_ad_connector(app)
        monkeypatch.setattr(ad_lookup, 'lookup_account_by_sid', lambda sid: ad_lookup.NO_ACCOUNT)
        before = _count(app)
        r = auth_client.post(f'/api/v2/scep/{request_id}/approve', json={})
        assert r.status_code == 400
        assert NOT_FOUND_MESSAGE in r.get_data(as_text=True)
        assert self._status(request_id) == ('rejected', NOT_FOUND_MESSAGE)
        assert _count(app) == before


def test_an_issuer_key_that_cannot_be_checked_carries_no_sid(app, create_ca, monkeypatch):
    """Unverifiable is never read as signed by the CA."""
    from services.ad_connector import renewal_identity
    from utils import cert_issuer
    ca_data = create_ca(cn='SID unverifiable issuer CA')
    old, _key_ = _issue(app, ca_data['id'], 'sid-unverifiable.example.test')
    with app.app_context():
        ca_cert = x509.load_pem_x509_certificate(base64.b64decode(db.session.get(CA, ca_data['id']).crt))
        assert renewal_identity.renewal_requester_sid(old, ca_cert, 'TEST') == SID

        def unverifiable(cert, issuer):
            raise cert_issuer.UnsupportedIssuerKey('test')
        monkeypatch.setattr(cert_issuer, 'certificate_signed_by', unverifiable)
        assert renewal_identity.renewal_requester_sid(old, ca_cert, 'TEST') is None


def test_a_scep_request_gone_before_it_is_closed_answers_404(app):
    from api.v2 import scep
    with app.test_request_context():
        assert scep._close_refused(987654321, 'admin', 'gone')[1] == 404
