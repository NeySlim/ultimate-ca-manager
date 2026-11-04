"""A finalization that fails on a flush still records why on the order."""
import json

from models import Certificate, db
from models.acme_models import AcmeClientOrder
from services.acme.acme_client_service import AcmeClientService


def test_a_failed_flush_does_not_lose_the_error(app):
    with app.app_context():
        order = AcmeClientOrder(
            domains=json.dumps(['flush.example.com']), challenge_type='http-01', environment='staging',
            status='ready', order_url='https://ca.example/order/flush',
            finalize_url='https://ca.example/order/flush/finalize')
        db.session.add(order)
        db.session.commit()
        order_id = order.id
        svc = object.__new__(AcmeClientService)

        def flush_fails(_order):
            db.session.add(Certificate())  # refid is required
            db.session.flush()

        svc.check_order_status = flush_fails
        try:
            ok, msg, cert_id = svc.finalize_order(order)
            assert not ok and cert_id is None
            db.session.expire_all()
            stored = db.session.get(AcmeClientOrder, order_id)
            assert stored.status == 'error' and stored.error_message == msg
        finally:
            db.session.rollback()
            AcmeClientOrder.query.filter_by(id=order_id).delete()
            db.session.commit()
