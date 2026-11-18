"""What a failed ACME finalize leaves behind (RFC 8555 §7.1.6, §7.4).

A refusal of the CSR answers badCSR and leaves the order ``ready`` for an
amended CSR; a refusal of the order itself, or a failure on the server once
the order is ``processing``, leaves it ``invalid`` with the problem in its
``error`` field. No path takes a processing order back to ready but the
first.
"""
import base64
import json
import threading
import uuid

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from models import CA, Certificate, db
from models.acme_models import AcmeLocalDomain, AcmeOrder
from services.acme.acme_service import AcmeService
from tests.test_acme_server_rfc_conformance import _b64u, _csr_pem, _new_account, _ready_order, _signed
from tests.test_template_san_types import make_template  # noqa: F401 (fixture)

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')

SERVER = 'urn:ietf:params:acme:error:serverInternal'
GENERIC = 'Certificate signing failed on the server; retry later'


@pytest.fixture
def served(app, create_ca, monkeypatch):
    """(account, ca_id, domain): a domain issued by its own CA, CAA off."""
    import utils.caa_checker as caa
    monkeypatch.setattr(caa, 'check_caa_for_domains', lambda *a, **k: (True, 'test'))
    ca = create_ca(cn=f'ACME outcome CA {uuid.uuid4().hex[:6]}')
    domain = f'out-{uuid.uuid4().hex[:8]}.example'
    with app.app_context():
        db.session.add(AcmeLocalDomain(domain=domain, issuing_ca_id=ca['id']))
        db.session.commit()
    return _new_account(app), ca['id'], domain


def _csr_der(key, cn=None, dns=()):
    pem = _csr_pem(key, cn=cn, dns=dns)
    return _b64u(x509.load_pem_x509_csr(pem.encode()).public_bytes(serialization.Encoding.DER))


def _finalize(client, account, order_id, domain, key=None, cn='', dns=None):
    key = key or rsa.generate_private_key(65537, 2048)
    csr = _csr_der(key, cn=domain if cn == '' else cn, dns=[domain] if dns is None else dns)
    return _signed(client, account, f'/acme/order/{order_id}/finalize', {'csr': csr})


def _read(client, account, order_id):
    r = _signed(client, account, f'/acme/order/{order_id}', None)
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def _order(app, account, domain, **kw):
    return _ready_order(app, account, [{'type': 'dns', 'value': domain}], **kw)


def _assert_issued(client, account, order_id, response):
    assert response.status_code == 200, response.get_json()
    assert response.get_json()['status'] == 'valid'
    download = _signed(client, account, f'/acme/cert/{order_id}', None)
    assert download.status_code == 200 and b'BEGIN CERTIFICATE' in download.data


def _assert_ready_after_bad_csr(client, account, order_id, response, words):
    assert response.status_code == 400, response.get_json()
    problem = response.get_json()
    assert problem['type'] == 'urn:ietf:params:acme:error:badCSR'
    assert words in problem['detail'], problem
    read = _read(client, account, order_id)
    assert read['status'] == 'ready' and 'error' not in read


def _assert_server_invalid(client, account, order_id, response, secret):
    assert response.status_code == 500, response.get_json()
    assert response.get_json()['type'] == SERVER
    assert secret not in json.dumps(response.get_json())
    read = _read(client, account, order_id)
    assert read['status'] == 'invalid'
    assert read['error'] == {'type': SERVER, 'detail': GENERIC}


def _drop_key(app, ca_id):
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        ca.prv, ca.hsm_key_id = None, None
        db.session.commit()


# --- A: a server failure once processing ----------------------------------------------------------

def test_a_server_failure_invalidates_the_order_and_a_new_order_succeeds(app, client, create_ca, served):
    from models import AuditLog
    account, ca_id, domain = served
    _drop_key(app, ca_id)
    order_id = _order(app, account, domain)

    r = _finalize(client, account, order_id, domain)
    _assert_server_invalid(client, account, order_id, r, secret='private key')
    again = _finalize(client, account, order_id, domain)
    assert again.status_code == 403
    assert again.get_json()['type'] == 'urn:ietf:params:acme:error:orderNotReady'
    with app.app_context():
        # G: the real cause stays in the audit
        line = (AuditLog.query.filter_by(action='acme.order.finalize', resource_id=str(order_id))
                .order_by(AuditLog.id.desc()).first())
        assert line is not None and not line.success and 'private key' in line.details

    # The cause lifted, a new order reuses the valid authorizations and is issued
    able = create_ca(cn=f'ACME outcome able CA {uuid.uuid4().hex[:6]}')
    with app.app_context():
        AcmeLocalDomain.query.filter_by(domain=domain).one().issuing_ca_id = able['id']
        db.session.commit()
    created = _signed(client, account, '/acme/new-order', {'identifiers': [{'type': 'dns', 'value': domain}]})
    assert created.status_code == 201, created.get_json()
    assert created.get_json()['status'] == 'ready'
    new_id = created.headers['Location'].rsplit('/', 1)[-1]
    _assert_issued(client, account, new_id, _finalize(client, account, new_id, domain))


def test_a_signing_failure_on_the_server_invalidates_the_order(app, client, served, monkeypatch):
    from services.acme.mixins.issuance import IssuanceMixin

    def offline(self, order, csr_pem, ca_refid):
        self._last_signing_exception = ValueError('HSM slot 3 unreachable')
        return False, None, 'Certificate signing failed: HSM slot 3 unreachable'
    monkeypatch.setattr(IssuanceMixin, '_sign_certificate_with_ca', offline)
    account, _ca_id, domain = served
    order_id = _order(app, account, domain)
    _assert_server_invalid(client, account, order_id, _finalize(client, account, order_id, domain),
                           secret='HSM')


def test_a_transient_caa_failure_invalidates_the_order(app, client, served, monkeypatch):
    import utils.caa_checker as caa
    account, _ca_id, domain = served
    monkeypatch.setattr(caa, 'check_caa_for_domains', lambda *a, **k: (
        False, f'CAA check failed for {domain}: CAA DNS lookup failed ({caa.DNS_ERROR_MARKER}) for x'))
    order_id = _order(app, account, domain)
    _assert_server_invalid(client, account, order_id, _finalize(client, account, order_id, domain),
                           secret='lookup')


# --- B: a refused CSR leaves the order ready -------------------------------------------------------

def test_an_identifier_outside_the_order_is_refused_before_processing(app, client, served, monkeypatch):
    account, _ca_id, domain = served
    order_id = _order(app, account, domain)
    seen = []
    real = AcmeService.begin_order_processing
    monkeypatch.setattr(AcmeService, 'begin_order_processing',
                        lambda self, order: seen.append(order.order_id) or real(self, order))
    r = _finalize(client, account, order_id, domain, dns=[domain, 'stranger.example'])
    _assert_ready_after_bad_csr(client, account, order_id, r, 'stranger.example')
    assert seen == []  # judged without taking the order
    from models import AuditLog
    with app.app_context():
        # The refusal is audited with its cause, like any failed finalize
        line = (AuditLog.query.filter_by(action='acme.order.finalize', resource_id=str(order_id))
                .order_by(AuditLog.id.desc()).first())
        assert line is not None and not line.success and 'stranger.example' in line.details
    _assert_issued(client, account, order_id, _finalize(client, account, order_id, domain))


def test_a_policy_refusal_leaves_the_order_ready_for_another_key(app, client, served):
    from models.policy import CertificatePolicy
    account, ca_id, domain = served
    with app.app_context():
        policy = CertificatePolicy(name=f'acme-outcome-ec-{uuid.uuid4().hex[:6]}', policy_type='issuance',
                                   ca_id=ca_id, requires_approval=False, min_approvers=1,
                                   is_active=True, priority=100, notify_on_violation=False)
        policy.set_rules({'allowed_key_types': ['EC-P256']})
        db.session.add(policy)
        db.session.commit()
    order_id = _order(app, account, domain)
    r = _finalize(client, account, order_id, domain)
    _assert_ready_after_bad_csr(client, account, order_id, r, 'RSA-2048')
    _assert_issued(client, account, order_id,
                   _finalize(client, account, order_id, domain, key=ec.generate_private_key(ec.SECP256R1())))


def test_a_taken_subject_leaves_the_order_ready_for_another_csr(app, client, served):
    account, ca_id, domain = served
    with app.app_context():
        db.session.get(CA, ca_id).enforce_unique_subject = True
        db.session.commit()
    first = _order(app, account, domain)
    _assert_issued(client, account, first, _finalize(client, account, first, domain))

    other = _new_account(app)
    order_id = _order(app, other, domain)
    r = _finalize(client, other, order_id, domain)
    _assert_ready_after_bad_csr(client, other, order_id, r, 'already carried')
    # Another subject (an organization beside the name) is no longer taken
    from cryptography.hazmat.primitives import hashes
    from cryptography.x509.oid import NameOID
    amended = x509.CertificateSigningRequestBuilder().subject_name(x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, domain),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Other entity')])).add_extension(
        x509.SubjectAlternativeName([x509.DNSName(domain)]), critical=False).sign(
        rsa.generate_private_key(65537, 2048), hashes.SHA256())
    r = _signed(client, other, f'/acme/order/{order_id}/finalize',
                {'csr': _b64u(amended.public_bytes(serialization.Encoding.DER))})
    _assert_issued(client, other, order_id, r)


# --- C and the other refusals of the order itself -------------------------------------------------

def test_a_requested_validity_past_its_bound_invalidates_the_order(app, client, served):
    from datetime import timedelta
    from utils.datetime_utils import utc_now
    account, _ca_id, domain = served
    order_id = _order(app, account, domain, not_after=utc_now().replace(microsecond=0) - timedelta(hours=1))
    r = _finalize(client, account, order_id, domain)
    assert r.status_code == 400, r.get_json()
    assert r.get_json()['type'] == 'urn:ietf:params:acme:error:malformed'
    read = _read(client, account, order_id)
    assert read['status'] == 'invalid'
    assert read['error']['type'] == 'urn:ietf:params:acme:error:malformed'


def test_a_window_a_policy_refuses_invalidates_the_order(app, client, served):
    from datetime import timedelta
    from models.policy import CertificatePolicy
    from utils.datetime_utils import utc_now
    account, ca_id, domain = served
    with app.app_context():
        policy = CertificatePolicy(name=f'acme-outcome-cap-{uuid.uuid4().hex[:6]}', policy_type='issuance',
                                   ca_id=ca_id, requires_approval=False, min_approvers=1,
                                   is_active=True, priority=100, notify_on_violation=False)
        policy.set_rules({'max_validity_days': 5})
        db.session.add(policy)
        db.session.commit()
    order_id = _order(app, account, domain, not_after=utc_now().replace(microsecond=0) + timedelta(days=30))
    r = _finalize(client, account, order_id, domain)
    assert r.status_code == 400, r.get_json()
    assert r.get_json()['type'] == 'urn:ietf:params:acme:error:malformed'
    read = _read(client, account, order_id)
    assert read['status'] == 'invalid' and 'allowed by policy' in read['error']['detail']


def test_a_withdrawn_profile_invalidates_the_order(app, client, served):
    account, _ca_id, domain = served
    order_id = _order(app, account, domain)
    with app.app_context():
        AcmeOrder.query.filter_by(order_id=order_id).one().profile = 'withdrawn-profile'
        db.session.commit()
    r = _finalize(client, account, order_id, domain)
    assert r.status_code == 400, r.get_json()
    assert r.get_json()['type'] == 'urn:ietf:params:acme:error:invalidProfile'
    read = _read(client, account, order_id)
    assert read['status'] == 'invalid'
    assert read['error']['type'] == 'urn:ietf:params:acme:error:invalidProfile'


def test_a_template_refusing_the_order_names_invalidates_it(app, client, served, make_template):
    from tests.test_acme_profile_template import _clear_profiles, _install_profiles
    account, _ca_id, domain = served
    tpl_id = make_template(['email'])
    _install_profiles(app, {'mailonly': {'validity_days': 30, 'template_id': tpl_id}})
    try:
        order_id = _order(app, account, domain, profile='mailonly')
        r = _finalize(client, account, order_id, domain)
        assert r.status_code == 400, r.get_json()
        assert r.get_json()['type'] == 'urn:ietf:params:acme:error:rejectedIdentifier'
        read = _read(client, account, order_id)
        assert read['status'] == 'invalid'
        assert read['error']['type'] == 'urn:ietf:params:acme:error:rejectedIdentifier'
    finally:
        _clear_profiles(app)


# --- D: an exception nobody expected --------------------------------------------------------------

def test_an_unexpected_exception_invalidates_the_order(app, client, served, monkeypatch):
    from services.acme.mixins.issuance import IssuanceMixin

    def explode(self, order, csr_pem, ca_refid):
        raise RuntimeError('disk /srv/secret full')
    monkeypatch.setattr(IssuanceMixin, '_sign_certificate_with_ca', explode)
    account, _ca_id, domain = served
    order_id = _order(app, account, domain)
    r = _finalize(client, account, order_id, domain)
    assert r.status_code == 500
    assert r.get_json()['type'] == SERVER and 'secret' not in json.dumps(r.get_json())
    read = _read(client, account, order_id)
    assert read['status'] == 'invalid'
    assert read['error'] == {'type': SERVER, 'detail': GENERIC}


# --- E: two finalizes of one order ---------------------------------------------------------------

def test_two_concurrent_finalizes_issue_once(app, client, served, monkeypatch):
    """The second finalize arrives while the first signs: orderNotReady, one certificate."""
    from services.acme.mixins.issuance import IssuanceMixin
    account, _ca_id, domain = served
    order_id = _order(app, account, domain)
    real = IssuanceMixin._sign_certificate_with_ca
    second = []

    def sign_after_a_rival(self, order, csr_pem, ca_refid):
        if not second:
            second.append(None)
            box = []
            # Its own thread, its own session: the rival reads what was committed
            worker = threading.Thread(target=lambda: box.append(app.test_client().post(
                f'/acme/order/{order_id}/finalize', data=json.dumps(rival), content_type='application/jose+json')))
            worker.start()
            worker.join()
            second[0] = box[0]
        return real(self, order, csr_pem, ca_refid)

    from tests.test_acme_security_paths import _build_jws, _nonce
    rival = _build_jws(f'http://localhost/acme/order/{order_id}/finalize',
                       {'csr': _csr_der(rsa.generate_private_key(65537, 2048), cn=domain, dns=[domain])},
                       account['key'], kid=account['kid'], nonce=_nonce(client))
    monkeypatch.setattr(IssuanceMixin, '_sign_certificate_with_ca', sign_after_a_rival)
    first = _finalize(client, account, order_id, domain)
    _assert_issued(client, account, order_id, first)
    assert second[0].status_code == 403, second[0].get_json()
    assert second[0].get_json()['type'] == 'urn:ietf:params:acme:error:orderNotReady'
    with app.app_context():
        order = AcmeOrder.query.filter_by(order_id=order_id).one()
        refid = db.session.get(Certificate, order.certificate_id).caref
        assert Certificate.query.filter_by(caref=refid, source='acme').count() == 1


def test_only_one_claim_of_a_ready_order_wins(app, served):
    account, _ca_id, domain = served
    order_id = _order(app, account, domain)
    with app.app_context():
        one = AcmeOrder.query.filter_by(order_id=order_id).one()
        assert AcmeService(base_url='http://localhost').begin_order_processing(one)
        db.session.expire_all()
    with app.app_context():
        two = AcmeOrder.query.filter_by(order_id=order_id).one()
        from sqlalchemy.orm.attributes import set_committed_value
        set_committed_value(two, 'status', 'ready')  # read before the first claim landed
        assert not AcmeService(base_url='http://localhost').begin_order_processing(two)
        assert two.status == 'processing'


# --- Approval: a server failure at issuance closes the request ------------------------------------

def test_a_server_failure_at_approval_invalidates_the_order_and_closes_the_request(
        app, client, auth_client, served, monkeypatch):
    from services.acme.mixins.issuance import IssuanceMixin
    from tests.protocol_approval_support import approval_policy, requests_of
    account, ca_id, domain = served
    with approval_policy(app, ca_id, f'acme-outcome-held-{uuid.uuid4().hex[:6]}') as pid:
        order_id = _order(app, account, domain)
        held = _finalize(client, account, order_id, domain)
        assert held.get_json()['status'] == 'processing', held.get_json()
        (approval_id, *_), = requests_of(app, pid, 'acme_order')

        def offline(self, order, csr_pem, ca_refid):
            self._last_signing_exception = ValueError('No CA available for signing')
            return False, None, 'No CA available for signing'
        monkeypatch.setattr(IssuanceMixin, '_sign_certificate_with_ca', offline)
        r = auth_client.post(f'/api/v2/approvals/{approval_id}/approve', json={'comment': 'ok'})
        assert r.status_code == 200, r.get_json()
        assert r.get_json()['message'] == 'Request closed'
        assert requests_of(app, pid, 'acme_order')[0][1] == 'rejected'
        read = _read(client, account, order_id)
        assert read['status'] == 'invalid'
        assert read['error'] == {'type': SERVER, 'detail': GENERIC}


def test_the_issued_certificate_is_readable(app, client, served):
    """Sanity of the helpers: a plain finalize issues from the domain's CA."""
    account, ca_id, domain = served
    order_id = _order(app, account, domain)
    _assert_issued(client, account, order_id, _finalize(client, account, order_id, domain))
    with app.app_context():
        order = AcmeOrder.query.filter_by(order_id=order_id).one()
        row = db.session.get(Certificate, order.certificate_id)
        assert row.caref == db.session.get(CA, ca_id).refid
        x509.load_pem_x509_certificate(base64.b64decode(row.crt))
