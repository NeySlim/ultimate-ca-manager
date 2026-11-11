"""A pending MS CA renewal issued later replaces the certificate and fires the renewal event."""
from unittest.mock import patch

import pytest

from tests.deploy_leftovers import delete_leftovers
from tests.test_deploy_hooks import _create_target, _create_binding
from tests.test_import_review import _cert, _gen, _ca_from_fixture, _store_cert, _pem
from tests.test_import_triggers_deploy import _deliveries


_cleanup = pytest.fixture(autouse=True)(delete_leftovers)

def _pending(app, cert_id):
    with app.app_context():
        from models import db, MicrosoftCA, MSCARequest
        msca = MicrosoftCA(name=f'r7-status-ca-{cert_id}', server='ca.example.test', ca_name='x')
        db.session.add(msca); db.session.flush()
        req = MSCARequest(msca_id=msca.id, csr_id=cert_id, template='WebServer', status='pending',
                          request_id=7)
        db.session.add(req); db.session.commit()
        return msca.id, req.id


def _poll(app, auth_client, new, ids):
    msca_id, req_id = ids
    answer = {'status': 'issued', 'cert_pem': _pem(new)}
    with patch('api.v2.msca.MicrosoftCAService.check_request', return_value=answer):
        with app.app_context():
            from models import db, MSCARequest
            db.session.get(MSCARequest, req_id).cert_pem = _pem(new)
            db.session.commit()
        return auth_client.get(f'/api/v2/microsoft-cas/{msca_id}/requests/{req_id}')


def _setup(app, auth_client, create_ca, cn, bound=True):
    ca = create_ca(cn=f'{cn} CA')
    ca_cert, ca_key, caref, _ = _ca_from_fixture(app, ca)
    key = _gen()
    old = _cert(cn, key, issuer_cert=ca_cert, signer=ca_key)
    cert_id = _store_cert(app, old, key, caref=caref)
    if bound:
        _create_binding(auth_client, _create_target(auth_client)['id'], cert_id)
    return ca_cert, ca_key, key, cert_id


def test_late_issuance_replacing_a_certificate_queues_its_deliveries(app, auth_client, create_ca):
    ca_cert, ca_key, key, cert_id = _setup(app, auth_client, create_ca, 'r7-late.example.com')
    new = _cert('r7-late.example.com', key, issuer_cert=ca_cert, signer=ca_key)
    r = _poll(app, auth_client, new, _pending(app, cert_id))
    assert r.status_code == 200, r.data
    assert _deliveries(app, cert_id) == [('certificate.renewed', 'pending')]


def test_first_issuance_of_a_csr_stays_silent(app, auth_client, create_ca):
    ca = create_ca(cn='r7-csr CA')
    ca_cert, ca_key, caref, _ = _ca_from_fixture(app, ca)
    key = _gen()
    new = _cert('r7-csr.example.com', key, issuer_cert=ca_cert, signer=ca_key)
    with app.app_context():
        from models import db, Certificate
        row = Certificate(refid='r7csr001', descr='csr', csr='Y3Ny')
        db.session.add(row); db.session.commit()
        cert_id = row.id
    with patch('services.webhook_service.emit_cert_renewed') as emitted:
        r = _poll(app, auth_client, new, _pending(app, cert_id))
    assert r.status_code == 200, r.data
    emitted.assert_not_called()


def test_row_without_readable_certificate_is_a_first_issuance(app, auth_client, create_ca):
    ca_cert, ca_key, key, cert_id = _setup(app, auth_client, create_ca, 'r7-unreadable.example.com',
                                           bound=False)
    with app.app_context():
        from models import db, Certificate
        from sqlalchemy import update
        # Unreadable certificate and no serial column, as an interrupted import leaves it
        db.session.execute(update(Certificate).where(Certificate.id == cert_id)
                           .values(crt='bm90IGEgY2VydGlmaWNhdGU=', serial_number=None))
        db.session.commit()
    new = _cert('r7-unreadable.example.com', key, issuer_cert=ca_cert, signer=ca_key)
    with patch('services.webhook_service.emit_cert_renewed') as emitted:
        r = _poll(app, auth_client, new, _pending(app, cert_id))
    assert r.status_code == 200, r.data
    emitted.assert_not_called()
