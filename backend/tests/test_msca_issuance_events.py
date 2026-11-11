"""A certificate AD CS signs for UCM fires the issuance or the renewal event, once;
the inventory catalogues without any."""
import base64

import pytest

from tests.deploy_leftovers import delete_leftovers
from tests.event_recorder import events, cert_events  # noqa: F401
from tests.test_msca_lifecycle import _create_msca_cert, _make_key_csr_cert, post_json

_cleanup = pytest.fixture(autouse=True)(delete_leftovers)


def _fake_submit(monkeypatch, cert_pem):
    from services.msca_service import MicrosoftCAService

    def submit(msca_id, csr_pem, template, csr_id=None, submitted_by=None,
               enrollee_name=None, enrollee_upn=None):
        return {'status': 'issued', 'request_id': None, 'cert_pem': cert_pem}
    monkeypatch.setattr(MicrosoftCAService, 'submit_csr', staticmethod(submit))


def _csr_row(app, cn):
    from models import Certificate, MicrosoftCA, db
    _, csr_pem, cert_pem = _make_key_csr_cert(cn)
    with app.app_context():
        msca = MicrosoftCA(name=f'ev-{cn}', server='adcs.test.local', auth_method='basic', enabled=True)
        row = Certificate(refid=f'ev-{cn[:20]}', descr=cn,
                          csr=base64.b64encode(csr_pem.encode()).decode())
        db.session.add_all([msca, row])
        db.session.commit()
        return row.id, msca.id, cert_pem


def test_signed_csr_fires_certificate_issued(app, auth_client, monkeypatch, events):
    csr_id, msca_id, cert_pem = _csr_row(app, 'ev-sign.test.local')
    _fake_submit(monkeypatch, cert_pem)
    r = post_json(auth_client, f'/api/v2/microsoft-cas/{msca_id}/sign/{csr_id}', {'template': 'WebServer'})
    assert r.status_code == 200, r.data
    assert cert_events(events, csr_id) == [('certificate.issued', csr_id)]


def test_renewal_fires_certificate_renewed(app, auth_client, monkeypatch, events):
    cert_id, _msca_id, _req_id = _create_msca_cert(app, 'ev-renew.test.local')
    _, _, new_pem = _make_key_csr_cert('ev-renew.test.local', days=730)
    _fake_submit(monkeypatch, new_pem)
    r = post_json(auth_client, f'/api/v2/certificates/{cert_id}/renew', {})
    assert r.status_code == 200, r.data
    assert cert_events(events, cert_id) == [('certificate.renewed', cert_id)]


def test_inventory_import_fires_nothing(app, events):
    from models import MicrosoftCA, db
    from services.msca.inventory import MicrosoftCAInventoryMixin
    _, _, pem = _make_key_csr_cert('ev-inventory.test.local')
    with app.app_context():
        msca = MicrosoftCA(name='ev-inventory', server='adcs.test.local', auth_method='basic', enabled=True)
        db.session.add(msca)
        db.session.commit()
        cert = MicrosoftCAInventoryMixin._import_inventory_cert(msca, 4242, 'WebServer', pem)
        db.session.commit()
        cert_id = cert.id
    assert cert_events(events, cert_id) == []
