"""Which stored copy an ACME order names, and the wording of the related-certificate answers."""
import base64
import uuid

import pytest
from cryptography import x509

from models import db, Certificate, AcmeClientOrder
from services.acme import upstream_revocation
from services.cert import issued_lookup


@pytest.fixture
def twin_rows(app, create_cert):
    """The row an order will name, and an imported copy of the same certificate stored before it."""
    made = create_cert()
    with app.app_context():
        named = db.session.get(Certificate, made['id'])
        copy = Certificate(refid=str(uuid.uuid4()), descr='imported copy', crt=named.crt,
                           serial_number=named.serial_number, caref=None)
        db.session.add(copy)
        db.session.commit()
        ids = (named.id, copy.id)
        orders = []
        yield ids, orders
        for order_id in orders:
            order = db.session.get(AcmeClientOrder, order_id)
            if order is not None:
                db.session.delete(order)
        for cert_id in (copy.id, named.id):
            db.session.delete(db.session.get(Certificate, cert_id))
        db.session.commit()


def _order(**kw):
    order = AcmeClientOrder(domains='["a.example.com"]', status='valid', **kw)
    db.session.add(order)
    db.session.commit()
    return order


def test_a_certificate_a_renewal_moved_off_still_counts_as_ordered(twin_rows):
    (named_id, copy_id), orders = twin_rows
    named, copy = db.session.get(Certificate, named_id), db.session.get(Certificate, copy_id)
    # The order now names another row: the renewal moved off ``copy`` into it
    order = _order(certificate_id=named_id)
    order.add_replaced(copy)
    db.session.commit()
    orders.append(order.id)
    assert issued_lookup.acme_ordered_first([named, copy])[0].id == named_id
    order.certificate_id = None
    db.session.commit()
    assert issued_lookup.acme_ordered_first([named, copy])[0].id == copy_id


def test_the_proxy_certificate_is_the_row_an_order_names(twin_rows):
    from api.acme import acme_proxy_api
    (named_id, copy_id), orders = twin_rows
    # The order names the later row: the first copy found must not stand in for it
    named = db.session.get(Certificate, named_id)
    order = _order(certificate_id=copy_id, is_proxy_order=True)
    orders.append(order.id)
    cert_obj = x509.load_pem_x509_certificate(base64.b64decode(named.crt))
    assert acme_proxy_api._resolve_proxy_certificate(cert_obj).id == copy_id


def test_a_proxy_certificate_prefers_the_row_a_proxy_order_names(twin_rows):
    """A proxy whose upstream is UCM itself: the server order's row must not hide the proxy's."""
    from api.acme import acme_proxy_api
    from models import AcmeAccount, AcmeOrder
    (named_id, copy_id), orders = twin_rows
    named = db.session.get(Certificate, named_id)
    suffix = uuid.uuid4().hex
    account = AcmeAccount(jwk='{}', jwk_thumbprint=suffix)
    db.session.add(account)
    db.session.commit()
    server_order = AcmeOrder(account_id=account.account_id, identifiers='[]', certificate_id=named_id)
    db.session.add(server_order)
    db.session.commit()
    proxy_order = _order(certificate_id=copy_id, is_proxy_order=True)
    orders.append(proxy_order.id)
    try:
        cert_obj = x509.load_pem_x509_certificate(base64.b64decode(named.crt))
        assert acme_proxy_api._resolve_proxy_certificate(cert_obj, None).id == copy_id
    finally:
        db.session.delete(server_order)
        db.session.delete(account)
        db.session.commit()


def test_the_related_answer_is_a_new_sentence():
    answer = {'message': 'Certificate revoked in UCM and at the ACME CA', 'meta': {}}
    out = upstream_revocation.with_related_answer(
        answer, [(7, upstream_revocation.UNRESOLVED, 'no order')])
    assert '. Related certificate #7: ' in out['message']
    dotted = {'message': 'Certificate revoked in UCM and at the ACME CA.', 'meta': {}}
    out = upstream_revocation.with_related_answer(
        dotted, [(7, upstream_revocation.UNRESOLVED, 'no order')])
    assert '..' not in out['message'] and '. Related certificate #7: ' in out['message']


def test_only_the_related_member_raises_the_local_only_warning():
    answer = {'message': 'Certificate revoked in UCM and at the ACME CA',
              'meta': {'acme_ca_revoked': True}}
    meta = upstream_revocation.with_related_answer(
        answer, [(7, upstream_revocation.UNRESOLVED, 'no order')])['meta']
    assert meta['related_acme_local_only'] == 7
    assert 'acme_local_only' not in meta and meta['acme_ca_revoked'] is True


def test_a_user_deleted_with_a_certificate_left_valid_ends_its_message_before_the_acme_note(
        auth_client, create_user, monkeypatch):
    from api.v2.users import crud
    user = create_user()

    def withdraw(user_id, actor, upstream=None):
        upstream.append((5, upstream_revocation.UNRESOLVED, 'no order'))
        return [5], [{'id': 6, 'serial_number': '0A', 'name': 'left'}], [], None

    monkeypatch.setattr(crud, '_withdraw_enrolled_certificates', withdraw)
    response = auth_client.delete(f"/api/v2/users/{user['id']}")
    assert response.status_code == 200
    body = response.get_json()
    assert body['meta']['acme_local_only'] == [5]
    assert body['data']['unrevoked_certificates'][0]['id'] == 6
    assert 'revoke them under Certificates. Certificate #5:' in body['message']
