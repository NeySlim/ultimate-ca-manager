"""A finalization that fails on a database error or a refused import says so on the order."""
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from models import Certificate, db
from models.acme_models import AcmeClientOrder
from services.acme.acme_client_service import AcmeClientService


@pytest.fixture(autouse=True)
def _no_order_left(app):
    yield
    with app.app_context():
        db.session.rollback()
        AcmeClientOrder.query.filter_by(order_url='https://ca.example/order/flush').delete()
        db.session.commit()


def _order():
    order = AcmeClientOrder(
        domains=json.dumps(['flush.example.com']), challenge_type='http-01', environment='staging',
        status='ready', order_url='https://ca.example/order/flush',
        finalize_url='https://ca.example/order/flush/finalize')
    db.session.add(order)
    db.session.commit()
    return order


def _failed_flush(*_args, **_kwargs):
    db.session.add(Certificate())  # refid is required
    db.session.flush()


def _stored(order_id):
    db.session.expire_all()
    return db.session.get(AcmeClientOrder, order_id)


def test_a_failed_flush_does_not_lose_the_error(app):
    with app.app_context():
        order = _order()
        order_id = order.id
        svc = object.__new__(AcmeClientService)
        svc.check_order_status = _failed_flush
        ok, msg, cert_id = svc.finalize_order(order)
        assert not ok and cert_id is None
        stored = _stored(order_id)
        assert stored.status == 'error' and stored.error_message == msg
        # Neither the API answer nor the order keeps the statement and its values
        assert msg == 'Database error during finalization'


def _service_that_imports_with(import_certificate):
    svc = object.__new__(AcmeClientService)
    svc.check_order_status = lambda _order: ('ready', {})
    svc._generate_cert_key = lambda _order: (ec.generate_private_key(ec.SECP256R1()), None)
    svc._build_csr_b64 = lambda *_args: 'csr'
    svc._post = lambda *_args: SimpleNamespace(
        status_code=200, json=lambda: {'status': 'valid', 'certificate': 'https://ca.example/cert'})
    svc._select_certificate_chain = lambda _resp: 'pem'
    svc._import_certificate = import_certificate
    return svc


def test_a_refused_import_is_recorded_and_the_order_can_be_renewed(app, auth_client):
    def import_swallows_its_failed_flush(**_kwargs):
        try:
            _failed_flush()
        except Exception:
            return None

    with app.app_context():
        order = _order()
        order_id = order.id
        ok, msg, cert_id = _service_that_imports_with(import_swallows_its_failed_flush).finalize_order(order)
        assert not ok and cert_id is None
        stored = _stored(order_id)
        assert stored.status == 'valid' and stored.error_message == msg == 'Certificate obtained but import failed'
    with patch('services.acme_renewal_service.renew_certificate', return_value=(True, 'renewed')):
        renewed = auth_client.post(f'/api/v2/acme/client/orders/{order_id}/renew')
    assert renewed.status_code == 200


def test_a_later_success_clears_the_old_error(app):
    with app.app_context():
        order = _order()
        order_id = order.id
        order.error_message = 'Certificate obtained but import failed'
        db.session.commit()
        ok, _msg, cert_id = _service_that_imports_with(lambda **_kwargs: 4242).finalize_order(order)
        assert ok and cert_id == 4242
        stored = _stored(order_id)
        assert stored.status == 'issued' and stored.error_message is None
