"""A finalization that fails on a database error or a refused import says so on the order."""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import text

from api.v2.acme_client import orders as orders_module
from models import Certificate, db
from tests.acme_rows import placeholder_certificate_id
from models.acme_models import AcmeClientOrder
from services.acme.acme_client_service import AcmeClientService
from tests.db_write_probe import watching_writes


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


def import_swallows_its_failed_flush(**_kwargs):
    try:
        _failed_flush()
    except Exception:
        return None


def _renew_answer(auth_client, order_id):
    with patch('services.acme_renewal_service.renew_certificate', return_value=(True, 'renewed')):
        return auth_client.post(f'/api/v2/acme/client/orders/{order_id}/renew').status_code


def test_a_refused_import_is_recorded_and_the_order_can_be_renewed(app, auth_client):
    with app.app_context():
        order = _order()
        order_id = order.id
        ok, msg, cert_id = _service_that_imports_with(import_swallows_its_failed_flush).finalize_order(order)
        assert not ok and cert_id is None
        stored = _stored(order_id)
        assert stored.status == 'valid' and stored.error_message == msg == 'Certificate obtained but import failed'
    assert _renew_answer(auth_client, order_id) == 200


def test_the_automatic_path_keeps_the_order_renewable(app, auth_client, monkeypatch):
    # A DNS-01 request finalizes in the background, then writes its own status over the result
    monkeypatch.setattr(orders_module, '_dns_propagation_timeout', lambda: 0)
    monkeypatch.setattr(orders_module.time, 'sleep', lambda _seconds: None)
    with app.app_context():
        order = _order()
        order.set_challenges_dict({'flush.example.com': {'dns_txt_value': 'token'}})
        db.session.commit()
        order_id = order.id
        svc = _service_that_imports_with(import_swallows_its_failed_flush)
        svc.verify_challenge = lambda _order, _domain: (True, 'submitted')
        svc.get_poll_settings = lambda: {'order_poll_timeout_sec': 30, 'order_poll_interval_sec': 3}
        svc.find_invalid_authorization = lambda _order: None
        result = orders_module._auto_poll_and_finalize(svc, order)
        assert result['error'] == 'Certificate obtained but import failed'
        stored = _stored(order_id)
        assert stored.status == 'valid' and stored.error_message == result['error']
    assert _renew_answer(auth_client, order_id) == 200


def _download_fails(*_args):
    raise ConnectionError('CA unreachable')


def test_a_failure_after_the_ca_said_valid_keeps_the_order_renewable(app, auth_client):
    with app.app_context():
        order = _order()
        order_id = order.id
        svc = _service_that_imports_with(lambda **_kwargs: placeholder_certificate_id())
        svc._select_certificate_chain = _download_fails
        ok, msg, _cert_id = svc.finalize_order(order)
        assert not ok and msg == 'CA unreachable'
        stored = _stored(order_id)
        assert stored.status == 'valid' and stored.error_message == msg
    assert _renew_answer(auth_client, order_id) == 200


def test_the_automatic_path_keeps_an_invalid_order_invalid(app, monkeypatch):
    monkeypatch.setattr(orders_module, '_dns_propagation_timeout', lambda: 0)
    monkeypatch.setattr(orders_module.time, 'sleep', lambda _seconds: None)
    with app.app_context():
        order = _order()
        order.set_challenges_dict({'flush.example.com': {'dns_txt_value': 'token'}})
        db.session.commit()
        order_id = order.id

        def finalize_sees_invalid(target, **_kwargs):
            target.status = 'invalid'
            db.session.commit()
            return False, 'Order became invalid during finalization', None

        client = SimpleNamespace(
            verify_challenge=lambda _order, _domain: (True, 'submitted'),
            get_poll_settings=lambda: {'order_poll_timeout_sec': 30, 'order_poll_interval_sec': 3},
            find_invalid_authorization=lambda _order: None,
            check_order_status=lambda _order: ('ready', {}),
            finalize_order=finalize_sees_invalid)
        orders_module._auto_poll_and_finalize(client, order)
        assert _stored(order_id).status == 'invalid'


@pytest.mark.parametrize('before, after', [('issued', 'issued'), ('validating', 'valid')])
def test_a_status_check_does_not_undo_an_import(app, before, after):
    with app.app_context():
        order = _order()
        order.status = before
        db.session.commit()
        order_id = order.id
        svc = object.__new__(AcmeClientService)
        svc._post = lambda *_args: SimpleNamespace(status_code=200, headers={}, json=lambda: {'status': 'valid'})
        status, _data = svc.check_order_status(order)
        assert status == 'valid'
        assert _stored(order_id).status == after


def test_a_download_the_ca_refuses_is_recorded(app):
    with app.app_context():
        order = _order()
        order_id = order.id
        svc = _service_that_imports_with(lambda **_kwargs: placeholder_certificate_id())
        responses = iter([
            SimpleNamespace(status_code=200, headers={}, json=lambda: {'status': 'valid', 'certificate': 'https://ca.example/c'}),
            SimpleNamespace(status_code=500, headers={}),
        ])
        svc._post = lambda *_args: next(responses)
        ok, msg, _cert_id = svc.finalize_order(order)
        assert not ok and msg == 'Failed to download certificate'
        stored = _stored(order_id)
        assert stored.status == 'valid' and stored.error_message == msg


def test_a_status_check_loses_to_an_import_during_its_round_trip(app):
    with app.app_context():
        order = _order()
        order.status = 'processing'
        db.session.commit()
        order_id = order.id
        assert order.status == 'processing'

        def background_import_meanwhile(*_args):
            # This session's copy of the order still says processing
            db.session.execute(text(f"UPDATE {AcmeClientOrder.__tablename__} SET status = 'issued' "
                                    f"WHERE id = {order_id}"))
            return SimpleNamespace(status_code=200, headers={}, json=lambda: {'status': 'valid'})

        svc = object.__new__(AcmeClientService)
        svc._post = background_import_meanwhile
        status, _data = svc.check_order_status(order)
        assert status == 'valid'
        assert _stored(order_id).status == 'issued'


def test_a_database_error_in_a_status_check_leaves_the_session_usable(app):
    with app.app_context():
        order = _order()
        svc = object.__new__(AcmeClientService)
        svc._post = _failed_flush
        status, data = svc.check_order_status(order)
        assert (status, data) == ('ready', {})
        assert db.session.execute(text('SELECT 1')).scalar() == 1


def test_a_verification_loses_to_an_import_during_its_round_trip(app, auth_client):
    with app.app_context():
        order = _order()
        order.set_challenges_dict({'flush.example.com': {'status': 'pending'}})
        order.status = 'validating'
        db.session.commit()
        order_id = order.id

    def import_meanwhile(_order):
        db.session.execute(text(f"UPDATE {AcmeClientOrder.__tablename__} SET status = 'issued' "
                                f"WHERE id = {order_id}"))
        return 'valid', {}

    client = MagicMock()
    client.verify_challenge.return_value = (True, 'ok')
    client.check_order_status.side_effect = import_meanwhile
    with patch.object(AcmeClientService, 'for_order', return_value=client), \
            patch.object(orders_module, '_dns_propagation_timeout', lambda: 0):
        answer = auth_client.post(f'/api/v2/acme/client/orders/{order_id}/verify', json={'force': True})
    assert answer.status_code == 200, answer.get_json()
    with app.app_context():
        assert _stored(order_id).status == 'issued'


def test_the_automatic_path_loses_to_an_import_during_its_own_failure(app, monkeypatch):
    # Another finalize imported while this one failed: its pending must not undo the import
    monkeypatch.setattr(orders_module, '_dns_propagation_timeout', lambda: 0)
    monkeypatch.setattr(orders_module.time, 'sleep', lambda _seconds: None)
    with app.app_context():
        order = _order()
        order.set_challenges_dict({'flush.example.com': {'dns_txt_value': 'token'}})
        db.session.commit()
        order_id = order.id

        def finalize_fails_after_the_import(_order, **_kwargs):
            db.session.execute(text(f"UPDATE {AcmeClientOrder.__tablename__} SET status = 'issued' "
                                    f"WHERE id = {order_id}"))
            return False, 'Order not ready for finalization (status: processing)', None

        client = SimpleNamespace(
            verify_challenge=lambda _order, _domain: (True, 'submitted'),
            get_poll_settings=lambda: {'order_poll_timeout_sec': 30, 'order_poll_interval_sec': 3},
            find_invalid_authorization=lambda _order: None,
            check_order_status=lambda _order: ('ready', {}),
            finalize_order=finalize_fails_after_the_import)
        orders_module._auto_poll_and_finalize(client, order)
        stored = _stored(order_id)
        assert stored.status == 'issued' and stored.error_message is None


def test_no_write_is_pending_during_any_call_to_the_ca(app):
    # A pending write would hold the database's write lock for the whole network call
    with app.app_context(), watching_writes() as pending_writes:
        order = _order()
        svc = _service_that_imports_with(lambda **_kwargs: placeholder_certificate_id())
        seen = []
        responses = iter([
            SimpleNamespace(status_code=200, headers={}, json=lambda: {'status': 'valid', 'certificate': 'https://ca.example/c'}),
            SimpleNamespace(status_code=500, headers={}),
        ])

        def call_the_ca(*_args):
            seen.append(pending_writes())
            return next(responses)

        svc._post = call_the_ca
        svc.finalize_order(order)
        assert seen == [[], []]


def test_a_second_finalize_does_not_undo_the_first_ones_import(app):
    # Finalize clicked during the background one: the CA answers valid, the download then fails
    with app.app_context():
        order = _order()
        order_id = order.id

        def imported_meanwhile(*_args):
            db.session.execute(text(f"UPDATE {AcmeClientOrder.__tablename__} SET status = 'issued' "
                                    f"WHERE id = {order_id}"))
            db.session.commit()
            return SimpleNamespace(status_code=200, headers={},
                                   json=lambda: {'status': 'valid', 'certificate': 'https://ca.example/c'})

        svc = _service_that_imports_with(lambda **_kwargs: placeholder_certificate_id())
        responses = iter([imported_meanwhile, lambda *_args: SimpleNamespace(status_code=500, headers={})])
        svc._post = lambda *args: next(responses)(*args)
        ok, _msg, _cert_id = svc.finalize_order(order)
        assert not ok
        stored = _stored(order_id)
        assert stored.status == 'issued' and stored.error_message is None


def test_a_later_success_clears_the_old_error(app):
    with app.app_context():
        order = _order()
        order_id = order.id
        order.error_message = 'Certificate obtained but import failed'
        db.session.commit()
        ok, _msg, cert_id = _service_that_imports_with(lambda **_kwargs: placeholder_certificate_id()).finalize_order(order)
        assert ok and cert_id == placeholder_certificate_id()
        stored = _stored(order_id)
        assert stored.status == 'issued' and stored.error_message is None
        assert stored.certificate_url == 'https://ca.example/cert'
