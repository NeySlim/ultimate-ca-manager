"""A certificate the ACME client or proxy brings in fires the issuance or renewal event, once."""
import json
import threading
import uuid
from types import SimpleNamespace

from cryptography.hazmat.primitives.asymmetric import ec

from models import Certificate, db
from models.acme_models import AcmeClientOrder
from tests.acme_fake_ca import key_pem
from tests.event_recorder import events, cert_events  # noqa: F401
from tests.test_acme_proxy_issue_fixes import UPSTREAM, _b64, _make_service, _self_signed_pem
from tests.test_acme_renewal_in_place import bench  # noqa: F401
from tests.seeded_rows import ensure_acme_account


def test_a_new_order_fires_certificate_issued_once(bench, events):
    order = bench.child()
    order.pending_key = key_pem(ec.generate_private_key(ec.SECP256R1()))
    db.session.commit()
    ok, message, cert_id = bench.client.finalize_order(order)
    assert ok, message
    bench.extra_certs.append(cert_id)
    assert cert_events(events, cert_id) == [('certificate.issued', cert_id)]


def test_an_order_finalized_again_on_its_own_certificate_fires_nothing(bench, events):
    key = ec.generate_private_key(ec.SECP256R1())
    order = bench.child()
    order.pending_key = key_pem(key)
    db.session.commit()
    pem = bench.ca.issue(key.public_key(), [bench.name])
    bench.ca.orders[order.order_url].update(status='valid', pem=pem)
    held = bench.client._import_certificate(cert_pem=pem, key_pem=key_pem(key), domains=[bench.name])
    bench.extra_certs.append(held)
    order.certificate_id = held
    db.session.commit()
    ok, message, cert_id = bench.client.finalize_order(order)
    assert ok, message
    assert cert_id == held
    assert cert_events(events, held) == []


def test_a_renewal_into_a_new_row_fires_certificate_renewed(bench, events):
    row = bench.row()
    row.revoked, row.revoke_reason = True, 'keyCompromise'
    db.session.commit()
    ok, _message = bench.renew()
    assert ok
    new_id = bench.parent().certificate_id
    bench.extra_certs.append(new_id)
    assert new_id != bench.cert_id
    assert cert_events(events, new_id, bench.cert_id) == [('certificate.renewed', new_id)]


def test_a_renewal_in_place_fires_certificate_renewed_once(bench, events):
    ok, _message = bench.renew()
    assert ok
    assert cert_events(events, bench.cert_id) == [('certificate.renewed', bench.cert_id)]


def _proxy_download(app, monkeypatch, svc, cert_url, pem):
    upstream = SimpleNamespace(status_code=200, content=pem.encode(),
                               headers={'Content-Type': 'application/pem-certificate-chain'})
    monkeypatch.setattr(svc, '_post_with_account', lambda *_a, **_k: upstream)
    monkeypatch.setattr(threading, 'Thread', lambda *a, **k: SimpleNamespace(start=lambda: None))
    svc.get_certificate(_b64(cert_url))


def test_the_proxy_fires_issued_once_and_not_on_a_second_download(app, monkeypatch, events):
    with app.app_context():
        ensure_acme_account(None)
        cert_url = f'{UPSTREAM}/cert/ev-{uuid.uuid4().hex[:8]}'
        order = AcmeClientOrder(domains=json.dumps(['proxy-fix.test']), status='valid',
                                is_proxy_order=True, upstream_order_url=f'{cert_url}/order',
                                certificate_url=cert_url)
        db.session.add(order)
        db.session.commit()
        order_id = order.id
        svc = _make_service(app)
        pem = _self_signed_pem()
        try:
            _proxy_download(app, monkeypatch, svc, cert_url, pem)
            cert_id = db.session.get(AcmeClientOrder, order_id).certificate_id
            assert cert_id is not None
            _proxy_download(app, monkeypatch, svc, cert_url, pem)
            assert db.session.get(AcmeClientOrder, order_id).certificate_id == cert_id
            serial = Certificate.query.get(cert_id).serial_number
            assert Certificate.query.filter_by(serial_number=serial).count() == 1
            assert [e for e in events if e[0].startswith('certificate.')] == [('certificate.issued', cert_id)]
        finally:
            db.session.rollback()
            AcmeClientOrder.query.filter_by(id=order_id).delete()
            db.session.commit()
            from services.cert_service import CertificateService
            for row in Certificate.query.filter_by(descr='proxy-fix.test', source='acme_client').all():
                CertificateService.delete_certificate(row.id)
