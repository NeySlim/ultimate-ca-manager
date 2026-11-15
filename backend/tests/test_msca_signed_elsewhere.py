"""A CSR signed by UCM while its Microsoft CA request waits: the request is closed
as superseded, and no path writes the Microsoft CA certificate over UCM's."""
import base64
import json
import re

import pytest

from tests.deploy_leftovers import delete_leftovers
from tests.test_msca_inventory import _make_msca
from tests.test_msca_pending_completion import PanelADCS

_cleanup = pytest.fixture(autouse=True)(delete_leftovers)


@pytest.fixture
def adcs(monkeypatch):
    from services.msca.admin_channel import MicrosoftCAAdminChannelMixin
    fake = PanelADCS()
    monkeypatch.setattr(MicrosoftCAAdminChannelMixin, '_run_ps', staticmethod(fake.run_ps))
    return fake


def _csr_with_request(app, msca_id, rid, cn):
    from models import MSCARequest, db
    from services.cert_service import CertificateService
    with app.app_context():
        row = CertificateService.generate_csr(descr=cn, dn={'CN': cn}, key_type='2048')
        db.session.flush()
        req = MSCARequest(msca_id=msca_id, csr_id=row.id, template='WebServer',
                          status='pending', request_id=rid)
        db.session.add(req)
        db.session.commit()
        return row.id, req.id


def _sign_locally(auth_client, csr_id, ca_id):
    r = auth_client.post(f'/api/v2/csrs/{csr_id}/sign', data=json.dumps({'ca_id': ca_id, 'validity_days': 30}),
                         content_type='application/json')
    assert r.status_code == 200, r.data


def _row(app, cert_id):
    from models import Certificate, db
    with app.app_context():
        c = db.session.get(Certificate, cert_id)
        return str(c.serial_number), c.crt, c.source


def _req(app, req_id):
    from models import MSCARequest, db
    with app.app_context():
        r = db.session.get(MSCARequest, req_id)
        return r.status, r.cert_id


def _sync(app, msca_id, full=True):
    from services.msca_service import MicrosoftCAService
    with app.app_context():
        return MicrosoftCAService.inventory_sync(msca_id, full=full)


def _starts(fake):
    return [int(m.group(1)) for s in fake.scripts
            for m in [re.search(r'Disposition=20,RequestId>=(\d+)', s)] if m]


def _high_water(app, msca_id, value):
    from models import MicrosoftCA, db
    with app.app_context():
        db.session.get(MicrosoftCA, msca_id).last_synced_request_id = value
        db.session.commit()


class _Client:
    def __init__(self, pem):
        self.pem = pem

    def get_existing_cert(self, request_id, encoding='b64'):
        return self.pem


def _check(auth_client, monkeypatch, msca_id, req_id, pem):
    from services.msca.connection import MicrosoftCAConnectionMixin
    monkeypatch.setattr(MicrosoftCAConnectionMixin, '_get_client', staticmethod(lambda m: _Client(pem)))
    monkeypatch.setattr(MicrosoftCAConnectionMixin, '_cleanup_client', staticmethod(lambda c: None))
    return auth_client.get(f'/api/v2/microsoft-cas/{msca_id}/requests/{req_id}')


def _foreign_cert(app, csr_id):
    """Give the CSR row a certificate UCM issued, without closing its request
    (the state a request left by an earlier version is in)."""
    from models import Certificate, db
    from tests.test_msca_inventory import _make_cert
    serial, pem = _make_cert('legacy.test.local')
    with app.app_context():
        row = db.session.get(Certificate, csr_id)
        row.crt = base64.b64encode(pem.encode()).decode()
        row.serial_number = str(int(serial, 16))
        row.source = 'csr'
        db.session.commit()


def test_local_signing_closes_the_pending_request_with_an_audit(app, auth_client, create_ca):
    from models import AuditLog
    ca = create_ca(cn='MSE sign CA')
    msca_id = _make_msca(app, 'MSE sign')
    csr_id, req_id = _csr_with_request(app, msca_id, 7001, 'mse-sign.test.local')
    _sign_locally(auth_client, csr_id, ca['id'])
    assert _req(app, req_id) == ('superseded', None)
    with app.app_context():
        entry = (AuditLog.query.filter_by(action='msca.request_superseded')
                 .order_by(AuditLog.id.desc()).first())
        assert entry is not None and 'RequestId=7001' in entry.details


def test_importing_a_certificate_into_the_csr_closes_the_request(app, create_ca):
    import datetime
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    from models import Certificate, db
    from services.cert_service import CertificateService
    msca_id = _make_msca(app, 'MSE import')
    csr_id, req_id = _csr_with_request(app, msca_id, 7002, 'mse-import.test.local')
    with app.app_context():
        row = db.session.get(Certificate, csr_id)
        csr = x509.load_pem_x509_csr(base64.b64decode(row.csr))
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(csr.subject)
                .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Other CA')]))
                .public_key(csr.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now).not_valid_after(now + datetime.timedelta(days=30))
                .sign(key, hashes.SHA256()))
        CertificateService.complete_external_csr(
            row, cert, cert.public_bytes(serialization.Encoding.PEM), username='admin')
    assert _req(app, req_id) == ('superseded', None)


def test_no_path_overwrites_the_local_certificate(app, auth_client, create_ca, adcs, monkeypatch):
    from models import Certificate, MSCARequest
    from services.msca_service import MicrosoftCAService
    ca = create_ca(cn='MSE flow CA')
    msca_id = _make_msca(app, 'MSE flow')
    csr_id, req_id = _csr_with_request(app, msca_id, 7003, 'mse-flow.test.local')
    _sign_locally(auth_client, csr_id, ca['id'])
    local = _row(app, csr_id)
    ms_serial = adcs.add(7003, 'mse-flow.test.local')
    ms_pem = adcs.rows[-1]['pem']

    s = _sync(app, msca_id)
    assert (s['imported'], s['completed']) == (1, 0)
    assert _row(app, csr_id) == local
    assert _req(app, req_id) == ('superseded', None)
    with app.app_context():
        other = (MSCARequest.query.filter(MSCARequest.msca_id == msca_id, MSCARequest.request_id == 7003,
                                          MSCARequest.id != req_id).one())
        assert other.cert_id and other.cert_id != csr_id
        ms_row = Certificate.query.get(other.cert_id)
        assert int(str(ms_row.serial_number)) == int(ms_serial, 16) and ms_row.source == 'msca'
        ms_row_id = ms_row.id

    r = _check(auth_client, monkeypatch, msca_id, req_id, ms_pem)
    assert r.status_code == 200, r.data
    body = r.get_json()
    assert body['data']['status'] == 'superseded' and 'signed elsewhere' in body['message']
    assert _row(app, csr_id) == local

    with app.app_context():
        result = MicrosoftCAService.approve_request(msca_id, 7003)
    assert result['imported_cert_id'] in (None, ms_row_id)
    assert _row(app, csr_id) == local
    assert _req(app, req_id) == ('superseded', None)
    with app.app_context():
        assert Certificate.query.filter(Certificate.subject_cn == 'mse-flow.test.local').count() == 2

    _high_water(app, msca_id, 9000)
    adcs.scripts.clear()
    _sync(app, msca_id, full=False)
    assert _starts(adcs) == [9000]


def test_the_common_completion_refuses_a_row_signed_elsewhere(app, adcs):
    from models import MicrosoftCA, MSCARequest, db
    from services.msca.ca_control import MicrosoftCACAControlMixin
    msca_id = _make_msca(app, 'MSE guard')
    csr_id, req_id = _csr_with_request(app, msca_id, 7004, 'mse-guard.test.local')
    _foreign_cert(app, csr_id)
    local = _row(app, csr_id)
    adcs.add(7004, 'mse-guard.test.local')
    with app.app_context():
        msca = db.session.get(MicrosoftCA, msca_id)
        MicrosoftCACAControlMixin.complete_request(msca, db.session.get(MSCARequest, req_id),
                                                   adcs.rows[-1]['pem'])
    assert _row(app, csr_id) == local
    assert _req(app, req_id) == ('superseded', None)


def test_panel_approval_of_a_legacy_request_imports_into_another_row(app, adcs):
    from models import Certificate
    from services.msca_service import MicrosoftCAService
    msca_id = _make_msca(app, 'MSE panel')
    csr_id, req_id = _csr_with_request(app, msca_id, 7005, 'mse-panel.test.local')
    _foreign_cert(app, csr_id)
    local = _row(app, csr_id)
    adcs.add(7005, 'mse-panel.test.local')
    with app.app_context():
        result = MicrosoftCAService.approve_request(msca_id, 7005)
    assert result['imported_cert_id'] and result['imported_cert_id'] != csr_id
    assert _row(app, csr_id) == local
    assert _req(app, req_id) == ('superseded', None)
    with app.app_context():
        assert Certificate.query.get(result['imported_cert_id']).source == 'msca'


def test_check_of_a_legacy_request_answers_superseded(app, auth_client, adcs, monkeypatch):
    msca_id = _make_msca(app, 'MSE check')
    csr_id, req_id = _csr_with_request(app, msca_id, 7006, 'mse-check.test.local')
    _foreign_cert(app, csr_id)
    local = _row(app, csr_id)
    adcs.add(7006, 'mse-check.test.local')
    r = _check(auth_client, monkeypatch, msca_id, req_id, adcs.rows[-1]['pem'])
    assert r.status_code == 200, r.data
    assert r.get_json()['data']['status'] == 'superseded'
    assert _row(app, csr_id) == local
    assert _req(app, req_id) == ('superseded', None)


def test_a_legacy_request_signed_elsewhere_no_longer_pins_the_scan(app, adcs):
    msca_id = _make_msca(app, 'MSE pin')
    csr_id, req_id = _csr_with_request(app, msca_id, 7007, 'mse-pin.test.local')
    _foreign_cert(app, csr_id)
    _high_water(app, msca_id, 9000)
    adcs.scripts.clear()
    _sync(app, msca_id, full=False)
    assert _starts(adcs) == [9000]
    assert _req(app, req_id) == ('superseded', None)


def test_check_closes_a_legacy_request_the_ca_still_holds(app, auth_client, monkeypatch):
    from services.msca.connection import MicrosoftCAConnectionMixin

    class _Pending:
        def get_existing_cert(self, request_id, encoding='b64'):
            raise RuntimeError('Certificate request is pending')

    msca_id = _make_msca(app, 'MSE check held')
    csr_id, req_id = _csr_with_request(app, msca_id, 7008, 'mse-held.test.local')
    _foreign_cert(app, csr_id)
    monkeypatch.setattr(MicrosoftCAConnectionMixin, '_get_client', staticmethod(lambda m: _Pending()))
    monkeypatch.setattr(MicrosoftCAConnectionMixin, '_cleanup_client', staticmethod(lambda c: None))
    r = auth_client.get(f'/api/v2/microsoft-cas/{msca_id}/requests/{req_id}')
    assert r.status_code == 200, r.data
    assert r.get_json()['data']['status'] == 'superseded'
    assert _req(app, req_id) == ('superseded', None)


def test_a_superseded_request_stays_closed_once_its_csr_is_gone(app, adcs):
    from models import MSCARequest, db
    from services.msca_service import MicrosoftCAService
    msca_id = _make_msca(app, 'MSE closed')
    with app.app_context():
        req = MSCARequest(msca_id=msca_id, template='WebServer', status='superseded', request_id=7010)
        db.session.add(req)
        db.session.commit()
        req_id = req.id
    adcs.add(7010, 'mse-closed.test.local')
    with app.app_context():
        result = MicrosoftCAService.approve_request(msca_id, 7010)
        assert result['imported_cert_id']
        other = MSCARequest.query.filter(MSCARequest.request_id == 7010, MSCARequest.id != req_id).one()
        assert other.cert_id == result['imported_cert_id']
    assert _req(app, req_id) == ('superseded', None)
