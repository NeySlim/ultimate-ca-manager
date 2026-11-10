"""ACME orders held by a policy requiring approval (RFC 8555 §7.1.6, §7.4).

Finalize leaves the order ``processing`` with a Retry-After; the approval
makes it ``valid`` with its certificate, a rejection or an expiry
``invalid`` with an ``unauthorized`` error (§6.7).
"""
import uuid

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from models import CA, Certificate, db
from models.acme_models import AcmeLocalDomain, AcmeOrder
from tests.protocol_approval_support import approval_policy, approve, expire, reject, requests_of
from tests.test_acme_server_rfc_conformance import _b64u, _csr_pem, _new_account, _ready_order, _signed


@pytest.fixture
def acme_ca(app, create_ca, monkeypatch):
    """A CA serving one ACME domain, with CAA checks off."""
    import utils.caa_checker as caa
    monkeypatch.setattr(caa, 'check_caa_for_domains', lambda *a, **k: (True, 'test'))
    ca = create_ca(cn=f'ACME approval CA {uuid.uuid4().hex[:6]}')
    domain = f'held-{uuid.uuid4().hex[:8]}.example'
    with app.app_context():
        db.session.add(AcmeLocalDomain(domain=domain, issuing_ca_id=ca['id']))
        db.session.commit()
    yield ca['id'], domain
    with app.app_context():
        AcmeLocalDomain.query.filter_by(domain=domain).delete()
        db.session.commit()


def _finalize(client, account, order_id, domain):
    key = rsa.generate_private_key(65537, 2048)
    csr_der = x509.load_pem_x509_csr(_csr_pem(key, cn=domain, dns=[domain]).encode()).public_bytes(
        serialization.Encoding.DER)
    return _signed(client, account, f'/acme/order/{order_id}/finalize', {'csr': _b64u(csr_der)})


def _read(client, account, order_id):
    return _signed(client, account, f'/acme/order/{order_id}', None)


def _held(app, client, acme_ca):
    ca_id, domain = acme_ca
    account = _new_account(app)
    order_id = _ready_order(app, account, [{'type': 'dns', 'value': domain}])
    r = _finalize(client, account, order_id, domain)
    return account, order_id, r


def test_without_policy_finalize_issues_at_once(app, client, acme_ca):
    _account, order_id, r = _held(app, client, acme_ca)
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['status'] == 'valid'
    assert 'certificate' in r.get_json()


def test_finalize_leaves_the_order_processing(app, client, acme_ca):
    with approval_policy(app, acme_ca[0], 'acme-held-processing') as pid:
        account, order_id, r = _held(app, client, acme_ca)
        assert r.status_code == 200, r.get_json()
        assert r.get_json()['status'] == 'processing'
        assert 'certificate' not in r.get_json()
        assert int(r.headers['Retry-After']) > 0
        (approval_id, status, data, _cert), = requests_of(app, pid, 'acme_order')
        assert status == 'pending'
        assert data['order_id'] == order_id and data['protocol'] == 'acme'
        assert 'BEGIN CERTIFICATE REQUEST' in data['csr']

        read = _read(client, account, order_id)
        assert read.status_code == 200
        assert read.get_json()['status'] == 'processing'
        assert int(read.headers['Retry-After']) > 0

        # §7.4: an order that is not ready cannot be finalized again
        again = _finalize(client, account, order_id, acme_ca[1])
        assert again.status_code == 403
        assert again.get_json()['type'] == 'urn:ietf:params:acme:error:orderNotReady'
        assert len(requests_of(app, pid, 'acme_order')) == 1


def test_approval_makes_the_order_valid(app, client, auth_client, acme_ca):
    with approval_policy(app, acme_ca[0], 'acme-held-approve') as pid:
        account, order_id, _r = _held(app, client, acme_ca)
        (approval_id, *_), = requests_of(app, pid, 'acme_order')
        body = approve(auth_client, approval_id)

        read = _read(client, account, order_id).get_json()
        assert read['status'] == 'valid'
        assert read['certificate'].endswith(f'/acme/cert/{order_id}')
        download = _signed(client, account, f'/acme/cert/{order_id}', None)
        assert download.status_code == 200
        assert b'BEGIN CERTIFICATE' in download.data
        with app.app_context():
            order = AcmeOrder.query.filter_by(order_id=order_id).first()
            cert = db.session.get(Certificate, order.certificate_id)
            assert cert.source == 'acme'
            assert cert.caref == db.session.get(CA, acme_ca[0]).refid
            assert body['certificate']['id'] == cert.id
        (_id, status, _data, cert_id), = requests_of(app, pid, 'acme_order')
        assert status == 'approved' and cert_id == order.certificate_id


def test_rejection_makes_the_order_invalid(app, client, auth_client, acme_ca):
    with approval_policy(app, acme_ca[0], 'acme-held-reject') as pid:
        account, order_id, _r = _held(app, client, acme_ca)
        (approval_id, *_), = requests_of(app, pid, 'acme_order')
        reject(auth_client, approval_id, 'unknown host')

        read = _read(client, account, order_id).get_json()
        assert read['status'] == 'invalid'
        assert read['error']['type'] == 'urn:ietf:params:acme:error:unauthorized'
        assert 'rejected' in read['error']['detail']


def test_expiry_makes_the_order_invalid(app, client, acme_ca):
    with approval_policy(app, acme_ca[0], 'acme-held-expire') as pid:
        account, order_id, _r = _held(app, client, acme_ca)
        (approval_id, *_), = requests_of(app, pid, 'acme_order')
        expire(app, approval_id)

        read = _read(client, account, order_id).get_json()
        assert read['status'] == 'invalid'
        assert read['error']['type'] == 'urn:ietf:params:acme:error:unauthorized'


def test_an_expiry_not_yet_swept_is_seen_by_the_client(app, client, acme_ca):
    from datetime import timedelta
    from models.policy import ApprovalRequest
    from utils.datetime_utils import utc_now
    with approval_policy(app, acme_ca[0], 'acme-held-lazy-expire') as pid:
        account, order_id, _r = _held(app, client, acme_ca)
        (approval_id, *_), = requests_of(app, pid, 'acme_order')
        with app.app_context():
            db.session.get(ApprovalRequest, approval_id).expires_at = utc_now() - timedelta(minutes=1)
            db.session.commit()
        assert _read(client, account, order_id).get_json()['status'] == 'invalid'
        assert requests_of(app, pid, 'acme_order')[0][1] == 'expired'


def test_unreadable_policies_refuse_the_finalize(app, client, acme_ca, monkeypatch):
    from services.policy_service import PolicyEvaluationService

    def broken(*a, **k):
        raise RuntimeError('policy table unreadable')
    monkeypatch.setattr(PolicyEvaluationService, 'check_approval_required', broken)
    account, order_id, r = _held(app, client, acme_ca)
    assert r.status_code == 500
    assert r.get_json()['type'] == 'urn:ietf:params:acme:error:serverInternal'
    assert _read(client, account, order_id).get_json()['status'] == 'ready'


def _order_certificate(app, order_id):
    import base64
    with app.app_context():
        order = AcmeOrder.query.filter_by(order_id=order_id).first()
        row = db.session.get(Certificate, order.certificate_id)
        return x509.load_pem_x509_certificate(base64.b64decode(row.crt))


def test_approved_order_matches_a_direct_issuance(app, client, auth_client, acme_ca):
    from tests.protocol_approval_support import profile_of
    _account, direct_id, r = _held(app, client, acme_ca)
    assert r.get_json()['status'] == 'valid'
    with approval_policy(app, acme_ca[0], 'acme-held-compare') as pid:
        _account, held_id, _r = _held(app, client, acme_ca)
        (approval_id, *_), = requests_of(app, pid, 'acme_order')
        approve(auth_client, approval_id)
    assert profile_of(_order_certificate(app, held_id)) == profile_of(_order_certificate(app, direct_id))


def test_a_refusal_at_approval_closes_the_request(app, client, auth_client, acme_ca, monkeypatch):
    import utils.caa_checker as caa
    with approval_policy(app, acme_ca[0], 'acme-held-caa-refused') as pid:
        account, order_id, _r = _held(app, client, acme_ca)
        (approval_id, *_), = requests_of(app, pid, 'acme_order')
        monkeypatch.setattr(caa, 'check_caa_for_domains', lambda *a, **k: (False, 'issuance forbidden'))
        r = auth_client.post(f'/api/v2/approvals/{approval_id}/approve', json={'comment': 'ok'})
        assert r.status_code == 200, r.get_json()
        assert r.get_json()['message'] == 'Request closed'
        assert r.get_json()['data']['certificate_issued'] is False

        (_id, status, _data, cert_id), = requests_of(app, pid, 'acme_order')
        assert status == 'rejected' and cert_id is None
        read = _read(client, account, order_id).get_json()
        assert read['status'] == 'invalid'
        assert read['error']['type'] == 'urn:ietf:params:acme:error:caa'
        assert 'issuance forbidden' in read['error']['detail']


def test_a_bad_csr_at_approval_closes_the_request(app, client, auth_client, acme_ca, monkeypatch):
    from services.acme.mixins.issuance import IssuanceMixin

    def refuse(self, order, csr_pem, ca_refid):
        self._last_signing_exception = ValueError('key too weak')
        return False, None, 'key too weak'
    with approval_policy(app, acme_ca[0], 'acme-held-badcsr') as pid:
        account, order_id, _r = _held(app, client, acme_ca)
        (approval_id, *_), = requests_of(app, pid, 'acme_order')
        monkeypatch.setattr(IssuanceMixin, '_sign_certificate_with_ca', refuse)
        monkeypatch.setattr(IssuanceMixin, '_is_request_failure', lambda self, e: True)
        r = auth_client.post(f'/api/v2/approvals/{approval_id}/approve', json={'comment': 'ok'})
        assert r.status_code == 200, r.get_json()
        assert r.get_json()['message'] == 'Request closed'
        assert requests_of(app, pid, 'acme_order')[0][1] == 'rejected'
        read = _read(client, account, order_id).get_json()
        assert read['status'] == 'invalid'
        assert read['error']['type'] == 'urn:ietf:params:acme:error:badCSR'


def test_a_caa_dns_error_at_approval_keeps_the_request_pending(app, client, auth_client, acme_ca,
                                                               monkeypatch):
    import utils.caa_checker as caa
    with approval_policy(app, acme_ca[0], 'acme-held-caa-dns') as pid:
        account, order_id, _r = _held(app, client, acme_ca)
        (approval_id, *_), = requests_of(app, pid, 'acme_order')
        # What check_caa_for_domains returns on a lookup failure under acme_caa_enforce
        monkeypatch.setattr(caa, 'check_caa_for_domains', lambda *a, **k: (
            False, 'CAA check failed for x: CAA DNS lookup failed (DNS error) for x'))
        r = auth_client.post(f'/api/v2/approvals/{approval_id}/approve', json={'comment': 'ok'})
        assert r.get_json()['message'] != 'Request closed', r.get_json()
        assert requests_of(app, pid, 'acme_order')[0][1] == 'pending'
        assert _read(client, account, order_id).get_json()['status'] == 'processing'

