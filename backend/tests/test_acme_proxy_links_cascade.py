"""Deleting a proxy order takes its challenge links with it on every backend (SQLite does
not enforce the declared ON DELETE CASCADE)."""
import json
import uuid

from models import db
from models.acme_models import AcmeClientOrder, AcmeProxyChallengeLink


def test_deleting_an_order_removes_its_challenge_links(app):
    with app.app_context():
        order = AcmeClientOrder(domains=json.dumps(['links.example']), challenge_type='http-01',
                                environment='staging', status='ready', is_proxy_order=True,
                                order_url=f'https://up.example/order/{uuid.uuid4().hex}',
                                finalize_url='https://up.example/finalize')
        db.session.add(order)
        db.session.flush()
        for n in range(2):
            db.session.add(AcmeProxyChallengeLink(key_sha256=uuid.uuid4().hex + uuid.uuid4().hex,
                                                  order_id=order.id, identifier='links.example',
                                                  authz_url=f'https://up.example/authz/{n}'))
        db.session.commit()
        order_id = order.id
        assert AcmeProxyChallengeLink.query.filter_by(order_id=order_id).count() == 2

        db.session.delete(db.session.get(AcmeClientOrder, order_id))
        db.session.commit()
        assert AcmeProxyChallengeLink.query.filter_by(order_id=order_id).count() == 0
