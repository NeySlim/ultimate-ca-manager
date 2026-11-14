"""The CA option enforce_unique_subject on the enrollment protocols (RFC 5280 §4.1.2.6): a taken
subject is refused in each protocol's own form, the same entity is recognised by its key, its
renewal, its ACME account or its SID; no protocol has an override."""
import base64
import json
import uuid

import asn1crypto.core
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import NameOID

from models import CA, AuditLog, Certificate, db
from tests.test_est_rfc7030 import _basic_auth, _post_csr, _set_config, est_config  # noqa: F401
from tests.test_wstep_cn_pattern import _served_realm as served_realm, pattern_ca  # noqa: F401
from tests.test_wstep_cn_pattern_unique import accounts  # noqa: F401

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')


@pytest.fixture(autouse=True, scope='module')
def _made_rows_removed(app):
    """The accounts, orders, users and API keys this file makes go with it."""
    from models import User
    from models.acme_models import AcmeAccount, AcmeOrder
    from models.api_key import APIKey
    models = (AcmeOrder, AcmeAccount, APIKey, User)
    with app.app_context():
        floors = {m: db.session.query(db.func.max(m.id)).scalar() or 0 for m in models}
    yield
    with app.app_context():
        db.session.rollback()
        for model in models:
            model.query.filter(model.id > floors[model]).delete(synchronize_session=False)
        db.session.commit()


def _enforce(app, ca_id, on=True):
    with app.app_context():
        db.session.get(CA, ca_id).enforce_unique_subject = on
        db.session.commit()


def _refusals(app, ca_id):
    with app.app_context():
        return [a.details for a in AuditLog.query.filter_by(action='certificate.subject_taken',
                                                            resource_id=str(ca_id)).order_by(AuditLog.id)]


def _rows(app, ca_id, cn):
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        return Certificate.query.filter_by(caref=ca.refid, subject=f'CN={cn}').count()


def _rsa():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _csr(cn, key):
    return x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])).sign(key, hashes.SHA256())


# --- EST (RFC 7030 §4.2.3: a 4xx with a plaintext reason) ---------------------------------------

@pytest.fixture
def est_unique(app, est_config):
    with app.app_context():
        _set_config('est_enabled', 'true')
    _enforce(app, est_config['id'])
    yield est_config
    _enforce(app, est_config['id'], False)


def _est_cert(response):
    assert response.status_code == 200, response.data
    return pkcs7.load_der_pkcs7_certificates(base64.b64decode(response.data))[0]


def test_est_refuses_a_taken_subject_in_plain_text_without_the_serial(app, client, est_unique):
    key = _rsa()
    first = _est_cert(_post_csr(client, 'simpleenroll', _csr('est.unique.test', key), headers=_basic_auth()))
    r = _post_csr(client, 'simpleenroll', _csr('est.unique.test', _rsa()), headers=_basic_auth())
    assert r.status_code == 400 and r.mimetype == 'text/plain'
    assert r.data.decode() == ('the subject CN=est.unique.test is already carried by a certificate '
                               'of this CA issued to another entity')
    assert _refusals(app, est_unique['id'])[-1] == (
        f'est issuance refused: the subject CN=est.unique.test is already carried by certificate '
        f'serial {first.serial_number}')
    assert _rows(app, est_unique['id'], 'est.unique.test') == 1
    # The same key is the same entity
    _est_cert(_post_csr(client, 'simpleenroll', _csr('est.unique.test', key), headers=_basic_auth()))


def test_est_reenrolment_with_new_keys_is_the_same_entity_over_generations(app, client, est_unique):
    """Each simplereenroll designates the certificate it renews; the lineage keeps the first one's."""
    key = _rsa()
    cert = _est_cert(_post_csr(client, 'simpleenroll', _csr('est-renew.unique.test', key), headers=_basic_auth()))
    for _ in range(2):
        key = _rsa()
        cert = _est_cert(_post_csr(client, 'simplereenroll', _csr('est-renew.unique.test', key),
                                   client_cert_pem=cert.public_bytes(serialization.Encoding.PEM).decode()))
    with app.app_context():
        rows = (Certificate.query.filter_by(subject='CN=est-renew.unique.test')
                .order_by(Certificate.id).all())
        assert [r.subject_holder for r in rows] == [None, f'cert:{rows[0].refid}', f'cert:{rows[0].refid}']


def test_an_est_request_held_for_approval_is_checked_again_and_closed(app, client, auth_client, est_unique):
    from models.policy import ApprovalRequest
    from tests.protocol_approval_support import approval_policy
    with approval_policy(app, est_unique['id'], 'unique-held-est') as pid:
        csr = _csr('est-held.unique.test', _rsa())
        assert _post_csr(client, 'simpleenroll', csr, headers=_basic_auth()).status_code == 202
        # Meanwhile an operator issues the subject to someone else (admins bypass the policy)
        r = auth_client.post('/api/v2/certificates', json={
            'cn': 'est-held.unique.test', 'ca_id': est_unique['id'], 'validity_days': 30})
        assert r.status_code == 201, r.get_json()
        serial = r.get_json()['data']['serial_number']
        with app.app_context():
            approval_id = ApprovalRequest.query.filter_by(policy_id=pid).one().id
        r = auth_client.post(f'/api/v2/approvals/{approval_id}/approve', json={'comment': 'ok'})
        assert r.status_code == 200 and r.get_json()['data'].get('certificate_issued') is not True
        with app.app_context():
            assert db.session.get(ApprovalRequest, approval_id).status == 'rejected'
            closed = (AuditLog.query.filter_by(action='approval_closed', resource_id=str(approval_id))
                      .order_by(AuditLog.id.desc()).first())  # ids of deleted requests come back
            assert f'already carried by certificate serial {serial}' in closed.details
        assert _post_csr(client, 'simpleenroll', csr, headers=_basic_auth()).status_code == 403
    assert _rows(app, est_unique['id'], 'est-held.unique.test') == 1


# --- SCEP (RFC 8894 §3.2.1.4: FAILURE, failInfo badRequest) --------------------------------------

def _scep(app, ca_id, signer_cert, signer_key, message_type, csr):
    from services.scep.crypto_helpers import create_signed_pkcs7, encrypt_for_client
    from services.scep.scep_service import SCEPService
    from tests.test_scep_rfc8894_operations import (
        MESSAGE_TYPE_OID, SENDER_NONCE_OID, TRANSACTION_ID_OID, _load_ca_material, _response_attributes)
    with app.app_context():
        ca, ca_cert, _ = _load_ca_material(ca_id)
        attrs = [{'type': TRANSACTION_ID_OID, 'values': [asn1crypto.core.PrintableString(uuid.uuid4().hex)]},
                 {'type': MESSAGE_TYPE_OID, 'values': [asn1crypto.core.PrintableString(str(message_type))]},
                 {'type': SENDER_NONCE_OID, 'values': [asn1crypto.core.OctetString(uuid.uuid4().bytes)]}]
        request = create_signed_pkcs7(
            encrypt_for_client(csr.public_bytes(serialization.Encoding.DER), ca_cert),
            signer_key, signer_cert, signed_attributes=attrs)
        response, status = SCEPService(ca.refid, auto_approve=True).process_pkcs_req(request, '127.0.0.1')
    assert status == 200
    return response, _response_attributes(response)


def _scep_issued(response, key, signer):
    from tests.test_scep_rfc8894_operations import _decrypt_response
    return pkcs7.load_der_pkcs7_certificates(_decrypt_response(response, key, signer))[0]


def test_scep_refuses_a_taken_subject_and_renews_its_holder(app, create_ca, monkeypatch):
    from tests.test_scep_rfc8894_operations import FAIL_INFO_OID, PKI_STATUS_OID, _client_identity
    monkeypatch.setenv('UCM_SCEP_ALLOW_NO_CHALLENGE', '1')
    ca = create_ca(cn='Unique SCEP CA')
    _enforce(app, ca['id'])
    key = _rsa()
    signer, _ = _client_identity('scep.unique.test', key=key)
    response, attrs = _scep(app, ca['id'], signer, key, 19, _csr('scep.unique.test', key))
    assert attrs['2.16.840.1.113733.1.9.3'] == '0', attrs
    issued = _scep_issued(response, key, signer)
    other = _rsa()
    other_signer, _ = _client_identity('scep.unique.test', key=other)
    _response, attrs = _scep(app, ca['id'], other_signer, other, 19, _csr('scep.unique.test', other))
    assert (attrs[PKI_STATUS_OID], attrs[FAIL_INFO_OID]) == ('2', '2')
    assert attrs['1.3.6.1.5.5.7.24.1'] == ('the subject CN=scep.unique.test is already carried by a '
                                           'certificate of this CA issued to another entity')
    assert _refusals(app, ca['id'])[-1].endswith(f'serial {issued.serial_number}')
    # A RenewalReq signed by the issued certificate designates it: a new key is the same entity
    new_key = _rsa()
    response, attrs = _scep(app, ca['id'], issued, key, 17, _csr('scep.unique.test', new_key))
    assert attrs[PKI_STATUS_OID] == '0', attrs
    assert _rows(app, ca['id'], 'scep.unique.test') == 2


# --- ACME (RFC 8555 §7.4: badCSR) ----------------------------------------------------------------

def _acme_finalize(app, monkeypatch, ca, cn, key, account=None):
    from models.acme_models import AcmeAccount, AcmeOrder
    from services.acme.acme_service import AcmeService
    from utils import caa_checker
    with app.app_context():
        if account is None:
            row = AcmeAccount(jwk='{}', jwk_thumbprint=uuid.uuid4().hex + uuid.uuid4().hex[:11], status='valid')
            db.session.add(row)
            db.session.flush()
            account = row.account_id
        order = AcmeOrder(account_id=account, status='ready',
                          identifiers=json.dumps([{'type': 'dns', 'value': cn}]))
        db.session.add(order)
        db.session.commit()
        service = AcmeService(base_url='http://localhost')
        monkeypatch.setattr(caa_checker, 'check_caa_for_domains', lambda *a, **k: (True, 'allowed'))
        monkeypatch.setattr(service, '_resolve_ca_for_domains', lambda _d: ca['refid'])
        csr = x509.CertificateSigningRequestBuilder().subject_name(
            x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])).add_extension(
            x509.SubjectAlternativeName([x509.DNSName(cn)]), critical=False).sign(key, hashes.SHA256())
        service.begin_order_processing(order)
        service._finalizing_order_id = order.order_id
        success, error = service.finalize_order(order.order_id, csr.public_bytes(serialization.Encoding.PEM).decode())
        order = db.session.get(AcmeOrder, order.id)
        holder = (db.session.get(Certificate, order.certificate_id).subject_holder
                  if order.certificate_id else None)
        return account, success, error, getattr(service, '_last_finalize_error_type', None), order.status, holder


def test_acme_refuses_a_taken_subject_as_bad_csr_and_serves_the_same_account(app, create_ca, monkeypatch):
    ca = create_ca(cn='Unique ACME CA')
    _enforce(app, ca['id'])
    account, success, error, _type, status, holder = _acme_finalize(app, monkeypatch, ca, 'acme.unique.test', _rsa())
    assert (success, error, status, holder) == (True, None, 'valid', f'acme:{account}')
    other = _acme_finalize(app, monkeypatch, ca, 'acme.unique.test', _rsa())
    assert other[1:5] == (False, 'Certificate signing failed: the subject CN=acme.unique.test is already '
                                 'carried by a certificate of this CA issued to another entity',
                          'badCSR', 'invalid')
    assert _refusals(app, ca['id'])[-1].startswith('acme issuance refused: the subject CN=acme.unique.test')
    # The same account, a new key (proof 3)
    same = _acme_finalize(app, monkeypatch, ca, 'acme.unique.test', _rsa(), account=account)
    assert same[1:5] == (True, None, None, 'valid'), same
    assert _rows(app, ca['id'], 'acme.unique.test') == 2


# --- WSTEP without a common name pattern --------------------------------------------------------

@pytest.mark.usefixtures('served_realm')
def test_wstep_without_a_pattern_is_checked_once_the_option_is_on(app, pattern_ca, accounts):  # noqa: F811
    from tests.test_wstep_cn_pattern_unique import _issue as wstep_issue
    from services.wstep import wstep_service
    off_id, _ = pattern_ca('Unique WSTEP off CA')
    on_id, _ = pattern_ca('Unique WSTEP on CA')
    _enforce(app, on_id)
    for ca_id in (off_id, on_id):
        first, err = wstep_issue(app, ca_id, 'alice')
        assert err is None, err
        _cert, err = wstep_issue(app, ca_id, 'carol')  # the same directory DN, another account
        if ca_id == off_id:
            assert err is None, err
        else:
            assert isinstance(err, wstep_service.SubjectHeldByAnother), err
            assert err.audited.endswith(f'(serial {first.serial_number})')
    # The same SID with a new key
    cert, err = wstep_issue(app, on_id, 'alice')
    assert err is None and cert is not None, err
    with app.app_context():
        rows = Certificate.query.filter_by(caref=db.session.get(CA, on_id).refid).all()
    assert {r.subject_holder for r in rows} == {'sid:S-1-5-21-7-8-9-1101'}
