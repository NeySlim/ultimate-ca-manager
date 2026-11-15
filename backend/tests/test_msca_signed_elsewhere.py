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
    from models import AuditLog
    with app.app_context():
        entry = (AuditLog.query.filter_by(action='msca.request_superseded')
                 .order_by(AuditLog.id.desc()).first())
        assert 'RequestId=7008' in entry.details and entry.username == 'admin'


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


# Races between two real sessions: the other side runs in its own app context
# (its own session and connection) and commits while this side is mid-flight.

def _external_cert_for(app, csr_id, cn):
    """A certificate another CA issued for the CSR's key, as an operator would import it."""
    import datetime
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    from models import Certificate, db
    with app.app_context():
        csr = x509.load_pem_x509_csr(base64.b64decode(db.session.get(Certificate, csr_id).csr))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(csr.subject)
            .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f'Other CA {cn}')]))
            .public_key(csr.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now).not_valid_after(now + datetime.timedelta(days=30))
            .sign(key, hashes.SHA256()))
    return cert, cert.public_bytes(serialization.Encoding.PEM)


def _complete_msca(app, msca_id, req_id, pem):
    from models import MicrosoftCA, MSCARequest, db
    from services.msca.ca_control import MicrosoftCACAControlMixin
    with app.app_context():
        return MicrosoftCACAControlMixin.complete_request(
            db.session.get(MicrosoftCA, msca_id), db.session.get(MSCARequest, req_id), pem)


def _once(fn):
    done = []

    def run():
        if not done:
            done.append(fn())
    return run, done


def test_an_import_into_the_csr_loses_to_a_microsoft_ca_completion(app, adcs, monkeypatch):
    import services.cert.mixins.csr as csr_mod
    from models import Certificate, db
    from services.cert_service import CertificateService
    msca_id = _make_msca(app, 'MSE race import')
    csr_id, req_id = _csr_with_request(app, msca_id, 7020, 'mse-race-import.test.local')
    adcs.add(7020, 'mse-race-import.test.local')
    ms_pem = adcs.rows[-1]['pem']
    cert, pem = _external_cert_for(app, csr_id, 'race-import')
    other, done = _once(lambda: _complete_msca(app, msca_id, req_id, ms_pem))
    real_cn = csr_mod.subject_common_name
    monkeypatch.setattr(csr_mod, 'subject_common_name', lambda s: (other(), real_cn(s))[1])
    with app.app_context():
        row = db.session.get(Certificate, csr_id)
        with pytest.raises(ValueError):
            CertificateService.complete_external_csr(row, cert, pem, username='admin')
    assert done == [('imported', csr_id)]
    serial, crt, source = _row(app, csr_id)
    assert source == 'msca' and b'BEGIN' in base64.b64decode(crt)
    assert base64.b64decode(crt).strip() != pem.strip()
    assert _req(app, req_id) == ('issued', csr_id)


def test_a_microsoft_ca_completion_loses_to_an_import_into_the_csr(app, adcs, monkeypatch):
    import services.approval_gate as gate
    from models import Certificate, db
    from services.cert_service import CertificateService
    msca_id = _make_msca(app, 'MSE race msca')
    csr_id, req_id = _csr_with_request(app, msca_id, 7021, 'mse-race-msca.test.local')
    adcs.add(7021, 'mse-race-msca.test.local')
    ms_pem = adcs.rows[-1]['pem']
    cert, pem = _external_cert_for(app, csr_id, 'race-msca')
    # Between the import's commit and the closure of its requests
    other, done = _once(lambda: _complete_msca(app, msca_id, req_id, ms_pem))
    real_resolve = gate.resolve_moot_requests
    monkeypatch.setattr(gate, 'resolve_moot_requests', lambda *a, **k: (other(), real_resolve(*a, **k))[1])
    with app.app_context():
        CertificateService.complete_external_csr(db.session.get(Certificate, csr_id), cert, pem,
                                                 username='admin')
    assert done == [('superseded', None)]
    serial, crt, source = _row(app, csr_id)
    assert source == 'import' and int(serial) == cert.serial_number
    assert _req(app, req_id) == ('superseded', None)


def test_local_signing_loses_to_a_microsoft_ca_completion(app, auth_client, create_ca, adcs, monkeypatch):
    import services.hsm.ca_key_loader as loader
    ca = create_ca(cn='MSE race sign CA')
    msca_id = _make_msca(app, 'MSE race sign')
    csr_id, req_id = _csr_with_request(app, msca_id, 7022, 'mse-race-sign.test.local')
    adcs.add(7022, 'mse-race-sign.test.local')
    ms_pem = adcs.rows[-1]['pem']
    other, done = _once(lambda: _complete_msca(app, msca_id, req_id, ms_pem))
    real_key = loader.get_ca_signing_key
    monkeypatch.setattr(loader, 'get_ca_signing_key', lambda c: (other(), real_key(c))[1])
    r = auth_client.post(f'/api/v2/csrs/{csr_id}/sign', data=json.dumps({'ca_id': ca['id'], 'validity_days': 30}),
                         content_type='application/json')
    assert r.status_code >= 400, r.data
    assert done == [('imported', csr_id)]
    assert _row(app, csr_id)[2] == 'msca'
    assert _req(app, req_id) == ('issued', csr_id)


def test_direct_microsoft_ca_signing_loses_to_a_local_signing(app, auth_client, create_ca, adcs, monkeypatch):
    """The CA issues at once, but a local CA signed the CSR meanwhile: the request is
    closed superseded with a 409, and a full sync brings the CA's certificate in."""
    from models import CA, Certificate, MSCARequest, db
    from services.cert_service import CertificateService
    from services.msca.connection import MicrosoftCAConnectionMixin
    from tests.test_msca_inventory import _make_cert
    ca = create_ca(cn='MSE race direct CA')
    msca_id = _make_msca(app, 'MSE race direct')
    with app.app_context():
        row = CertificateService.generate_csr(descr='mse-race-direct', dn={'CN': 'mse-race-direct.test.local'},
                                              key_type='2048')
        db.session.commit()
        csr_id, caref = row.id, db.session.get(CA, ca['id']).refid
    ms_serial, ms_pem = _make_cert('mse-race-direct.test.local')

    def sign_locally():
        with app.app_context():
            CertificateService.sign_csr(csr_id, caref, validity_days=30, username='admin')

    class _Issuing:
        def get_cert(self, csr_pem, template, encoding='b64', attributes=None):
            sign_locally()
            return ms_pem

    monkeypatch.setattr(MicrosoftCAConnectionMixin, '_get_client', staticmethod(lambda m: _Issuing()))
    monkeypatch.setattr(MicrosoftCAConnectionMixin, '_cleanup_client', staticmethod(lambda c: None))
    r = auth_client.post(f'/api/v2/microsoft-cas/{msca_id}/sign/{csr_id}',
                         data=json.dumps({'template': 'WebServer'}), content_type='application/json')
    assert r.status_code == 409, r.data
    assert 'signed elsewhere' in r.get_json()['message'] and 'full inventory sync' in r.get_json()['message']
    local = _row(app, csr_id)
    assert local[1] and local[2] != 'msca'
    with app.app_context():
        req = MSCARequest.query.filter_by(msca_id=msca_id, csr_id=csr_id).one()
        assert (req.status, req.cert_id) == ('superseded', None)
    adcs.rows.append({'request_id': 7023, 'serial': ms_serial, 'template': 'WebServer',
                      'cn': 'mse-race-direct.test.local', 'pem': ms_pem})
    assert _sync(app, msca_id)['imported'] == 1
    assert _row(app, csr_id) == local
    with app.app_context():
        ms_row = Certificate.query.filter(Certificate.source == 'msca',
                                          Certificate.subject_cn == 'mse-race-direct.test.local').one()
        assert int(str(ms_row.serial_number)) == int(ms_serial, 16)
