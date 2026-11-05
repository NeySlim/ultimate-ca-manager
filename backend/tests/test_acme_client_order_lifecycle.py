"""ACME client orders: a compromised CSR stops before the CA, a failed manual renewal is counted,
an order the CA no longer has stops being polled."""
import json
import uuid
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization

from models import Certificate, WebhookDelivery, db
from models.acme_models import AcmeClientOrder
from models.audit_log import AuditLog
from services import acme_renewal_service as renew_mod
from services.acme.acme_client_service import ORDER_GONE
from services.acme.compromised_keys import COMPROMISED_CSR, CompromisedKey
from services.acme.order_lease import OrderLease
from services.cert_service import CertificateService
from services.webhook_service import WebhookEndpoint
from tests.acme_fake_ca import key_pem
from tests.test_acme_renewal_in_place import Bench, _restore_config, _set_config


@pytest.fixture
def bench(app):
    with app.app_context():
        email = _set_config('acme.client.email', 'lifecycle@example.com')
        b = Bench(f'lifecycle-{uuid.uuid4().hex[:8]}.example.com')
        yield b
        b.cleanup()
        _restore_config('acme.client.email', email)


@pytest.fixture
def endpoint(app):
    row = WebhookEndpoint(name=f'lifecycle-{uuid.uuid4().hex[:8]}', url='https://hooks.example/x',
                          events=json.dumps(['acme_order.renewal_failed']), enabled=True)
    db.session.add(row)
    db.session.commit()
    yield row
    db.session.rollback()
    WebhookDelivery.query.filter_by(endpoint_id=row.id).delete()
    db.session.delete(db.session.get(WebhookEndpoint, row.id))
    db.session.commit()


@contextmanager
def _routed(bench):
    """The routes reach the bench's CA and DNS, as Bench.renew does."""
    dns = MagicMock()
    dns.create_txt_record.return_value = (True, 'ok')
    with patch('services.acme.dns_providers.create_provider', return_value=dns), \
            patch('services.acme.acme_client_service.AcmeClientService.for_order', return_value=bench.client), \
            patch('services.acme.acme_client_service.time.sleep', return_value=None), \
            patch.object(renew_mod, 'wait_for_challenges', return_value={'ok': True, 'missing': [], 'waited': 0}):
        yield dns


def _csr(key, name):
    return (x509.CertificateSigningRequestBuilder()
            .subject_name(x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, name)]))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]), critical=False)
            .sign(key, hashes.SHA256()).public_bytes(serialization.Encoding.PEM).decode())


def _compromised_twin(bench):
    """Another row holding the bench key, revoked as compromised."""
    pem = bench.ca.issue(bench.key.public_key(), [bench.name])
    leaf_pem = pem.split('-----END CERTIFICATE-----\n', 1)[0] + '-----END CERTIFICATE-----\n'
    row = CertificateService.import_certificate(descr=bench.name, cert_pem=leaf_pem,
                                                key_pem=key_pem(bench.key), username='system',
                                                source='acme_client')
    row.revoked, row.revoke_reason = True, 'keyCompromise'
    db.session.commit()
    bench.extra_certs.append(row.id)
    return row


def _csr_parent(bench):
    parent = bench.parent()
    parent.key_source, parent.csr_pem = 'csr', _csr(bench.key, bench.name)
    db.session.commit()
    return parent


# ---- a compromised CSR never reaches the CA ----------------------------------------------

def test_a_request_with_a_compromised_csr_is_refused_before_any_order(app, auth_client, bench):
    _compromised_twin(bench)
    client = MagicMock()
    with patch('services.acme.acme_client_service.AcmeClientService.for_issuance', return_value=client):
        answer = auth_client.post('/api/v2/acme/client/request', json={
            'domains': [bench.name], 'email': 'x@example.com', 'challenge_type': 'http-01',
            'key_source': 'csr', 'csr_pem': _csr(bench.key, bench.name)})
    assert answer.status_code == 409 and answer.get_json()['message'] == COMPROMISED_CSR
    client.create_order.assert_not_called()


def test_a_renewal_with_a_compromised_csr_opens_no_order(bench):
    _csr_parent(bench)
    _compromised_twin(bench)
    with pytest.raises(CompromisedKey):
        bench.renew()
    bench.client.create_order.assert_not_called()


def test_a_manual_renewal_with_a_compromised_csr_answers_409_and_counts(app, auth_client, bench):
    _csr_parent(bench)
    _compromised_twin(bench)
    with _routed(bench):
        answer = auth_client.post(f'/api/v2/acme/client/orders/{bench.parent_id}/renew')
    assert answer.status_code == 409 and answer.get_json()['message'] == COMPROMISED_CSR
    db.session.expire_all()
    assert bench.parent().renewal_failures == 1 and bench.parent().error_message == COMPROMISED_CSR


# ---- a failed manual renewal is counted, audited and announced --------------------------

def test_a_failed_manual_renewal_answers_422_with_the_reason_and_counts(app, auth_client, bench, endpoint):
    bench.client.create_order = MagicMock(return_value=(False, 'rate limited by the CA', None))
    before = AcmeClientOrder.query.count()
    with _routed(bench):
        answer = auth_client.post(f'/api/v2/acme/client/orders/{bench.parent_id}/renew')
    assert answer.status_code == 422
    assert answer.get_json()['message'] == 'Order creation failed: rate limited by the CA'
    db.session.expire_all()
    parent = bench.parent()
    assert parent.renewal_failures == 1 and parent.last_error_at is not None
    assert 'rate limited' in parent.error_message
    entry = AuditLog.query.filter_by(action='acme_renew', resource_name=bench.name).one()
    assert entry.success is False and 'rate limited' in entry.details and entry.username != 'system'
    delivery = WebhookDelivery.query.filter_by(endpoint_id=endpoint.id).one()
    assert json.loads(delivery.payload)['renewal_failures'] == 1
    assert AcmeClientOrder.query.count() == before  # nothing left pending


def test_a_failed_renewal_that_opened_an_order_leaves_none(app, auth_client, bench):
    bench.client.verify_challenge = lambda *_a: (True, 'ok')
    bench.client.wait_for_order = lambda _order: ('invalid', {'error': {'detail': 'TXT not found'}})
    with _routed(bench):
        answer = auth_client.post(f'/api/v2/acme/client/orders/{bench.parent_id}/renew')
    assert answer.status_code == 422 and 'TXT not found' in answer.get_json()['message']
    assert bench.client.create_order.call_count == 1
    assert AcmeClientOrder.query.filter(AcmeClientOrder.id.in_(bench.extra_orders)).count() == 0


def test_a_renewal_refused_for_a_running_one_is_not_a_failure(app, auth_client, bench):
    OrderLease.take(bench.parent_id)
    assert auth_client.post(f'/api/v2/acme/client/orders/{bench.parent_id}/renew').status_code == 409
    db.session.expire_all()
    assert bench.parent().renewal_failures == 0


def test_a_database_error_is_not_quoted(bench):
    from sqlalchemy.exc import OperationalError
    error = OperationalError('UPDATE certificates SET prv=?', {'prv': 'secret'}, Exception('locked'))
    assert renew_mod.record_renewal_failure(bench.parent(), error, manual=True) == 'Database error during renewal'


# ---- an order the CA no longer has ------------------------------------------------------

def _gone_on_creation(bench):
    def create(**_kwargs):
        child = bench.child(status='pending')
        bench.ca.orders[child.order_url]['status'] = 'gone'
        return True, 'ok', child
    bench.client.create_order = MagicMock(side_effect=create)


def test_a_renewal_stops_at_the_first_404_on_its_order(bench):
    _gone_on_creation(bench)
    with patch('services.acme.acme_client_service.AcmeClientService._sleep_before_next_poll',
               side_effect=AssertionError('polled on')):
        with pytest.raises(Exception, match='no longer has this order'):
            bench.renew()
    assert AcmeClientOrder.query.filter(AcmeClientOrder.id.in_(bench.extra_orders)).count() == 0


def test_a_finalization_stops_when_the_order_disappears(bench):
    order = bench.child(status='ready', renewal_enabled=True)
    bench.ca.finalize_status = 'processing'
    bench.ca.on_finalize = lambda url: bench.ca.orders[url].update(status='gone')
    sleeps = []
    with patch('services.acme.acme_client_service.time.sleep', side_effect=sleeps.append):
        ok, message, _cert = bench.client.finalize_order(order)
    assert not ok and message == ORDER_GONE and len(sleeps) == 1
    db.session.expire_all()
    order = db.session.get(AcmeClientOrder, order.id)
    assert order.status == 'invalid' and order.error_message == ORDER_GONE


def test_the_automatic_path_stops_when_the_order_disappears(app, bench, monkeypatch):
    from api.v2.acme_client import orders as orders_module
    monkeypatch.setattr(orders_module, '_dns_propagation_timeout', lambda: 0)
    sleeps = []
    monkeypatch.setattr(orders_module.time, 'sleep', sleeps.append)
    order = bench.child(status='processing', renewal_enabled=True)
    bench.ca.orders[order.order_url]['status'] = 'gone'
    bench.client.find_invalid_authorization = lambda _order: None
    result = orders_module._auto_poll_and_finalize(bench.client, order)
    assert result['error'] == ORDER_GONE and len(sleeps) == 1
    db.session.expire_all()
    order = db.session.get(AcmeClientOrder, order.id)
    assert order.status == 'invalid' and order.error_message == ORDER_GONE


def test_a_status_check_of_a_gone_order_says_invalid(app, auth_client, bench):
    order = bench.child(status='pending', renewal_enabled=True)
    bench.ca.orders[order.order_url]['status'] = 'gone'
    with patch('services.acme.acme_client_service.AcmeClientService.for_order', return_value=bench.client):
        data = auth_client.get(f'/api/v2/acme/client/orders/{order.id}/status').get_json()['data']
    assert data['status'] == 'invalid' and data['order']['error_message'] == ORDER_GONE


def test_an_issued_order_stays_issued_when_the_ca_forgot_its_order(app, bench):
    bench.ca.orders[bench.old_url]['status'] = 'gone'
    status, _data = bench.client.check_order_status(bench.parent())
    db.session.expire_all()
    assert status == 'gone' and bench.parent().status == 'issued' and bench.parent().error_message is None


def test_a_second_finalize_or_renew_answers_409_while_one_runs(app, auth_client, bench):
    # The lease of the order (services/acme/order_lease.py) is the guard: each names the other
    order = bench.child(renewal_enabled=True)
    OrderLease.take(order.id)
    OrderLease.take(bench.parent_id)
    for url in (f'/api/v2/acme/client/orders/{order.id}/finalize',
                f'/api/v2/acme/client/orders/{bench.parent_id}/renew'):
        answer = auth_client.post(url)
        assert answer.status_code == 409 and 'already running' in answer.get_json()['message']
    assert Certificate.query.filter_by(descr=bench.name).count() == 1


def test_a_verification_of_a_gone_order_leaves_it_invalid(app, auth_client, bench):
    order = bench.child(status='pending', renewal_enabled=True)
    bench.ca.orders[order.order_url]['status'] = 'gone'
    with patch('services.acme.acme_client_service.AcmeClientService.for_order', return_value=bench.client):
        answer = auth_client.post(f'/api/v2/acme/client/orders/{order.id}/verify', json={'force': True})
    assert answer.status_code == 200
    db.session.expire_all()
    order = db.session.get(AcmeClientOrder, order.id)
    assert order.status == 'invalid' and order.error_message == ORDER_GONE
