"""The by-id reads the overview's links resolve through (work queue deep links)."""
import json
import uuid

import pytest

from models import db
from models.acme_models import AcmeAccount, AcmeOrder
from models.scep import SCEPRequest


def _body(r):
    return json.loads(r.data)['data']


def test_scep_request_by_id_outside_the_listed_page(app, auth_client):
    with app.app_context():
        ids = []
        for n in range(55):
            row = SCEPRequest(transaction_id=f'link-{uuid.uuid4().hex}', csr='x', status='pending',
                              subject=f'CN=link-{n}', ca_refid='none')
            db.session.add(row)
            db.session.flush()
            ids.append(row.id)
        db.session.commit()
    listed = {r['id'] for r in _body(auth_client.get('/api/v2/scep/requests'))}
    oldest = ids[0]
    assert oldest not in listed
    r = auth_client.get(f'/api/v2/scep/requests/{oldest}')
    assert r.status_code == 200 and _body(r)['id'] == oldest


def test_scep_request_by_id_unknown_and_unauthenticated(client, auth_client):
    assert auth_client.get('/api/v2/scep/requests/99999999').status_code == 404
    assert client.get('/api/v2/scep/requests/1').status_code == 401


def test_key_recovery_by_id(auth_client, create_cert):
    cert = create_cert(cn='link-escrow.example.com', validity_days=365)['id']
    made = auth_client.post(f'/api/v2/certificates/{cert}/key-recovery',
                            data=json.dumps({'reason': 'link'}), content_type='application/json')
    rid = _body(made)['id']
    r = auth_client.get(f'/api/v2/key-recovery/{rid}')
    assert r.status_code == 200 and _body(r)['id'] == rid
    assert auth_client.get('/api/v2/key-recovery/99999999').status_code == 404


def test_key_recovery_by_id_requires_auth(client):
    assert client.get('/api/v2/key-recovery/1').status_code == 401


def test_local_acme_order_by_id_has_the_listed_shape(app, auth_client):
    with app.app_context():
        account = AcmeAccount(jwk='{}', jwk_thumbprint=f'link-{uuid.uuid4().hex[:12]}', status='valid')
        db.session.add(account)
        db.session.commit()
        order = AcmeOrder(account_id=account.account_id, status='invalid',
                          identifiers=json.dumps([{'type': 'dns', 'value': 'link.example.com'}]))
        db.session.add(order)
        db.session.commit()
        pk = order.id
    r = auth_client.get(f'/api/v2/acme/orders/{pk}')
    assert r.status_code == 200
    one = _body(r)
    assert one['id'] == pk and one['domain'] == 'link.example.com'
    listed = [i for i in _body(auth_client.get('/api/v2/acme/orders?per_page=200'))['items'] if i['id'] == pk]
    assert listed == [one]
    assert auth_client.get('/api/v2/acme/orders/99999999').status_code == 404
