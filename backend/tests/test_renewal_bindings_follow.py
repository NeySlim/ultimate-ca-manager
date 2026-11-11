"""A protocol renewal that archives the old row moves its deploy bindings onto the new
row, and its renewal event deploys the new certificate. The new row holds no key: a
binding that pushes the key and the HTTPS listener binding stay on the old row."""
import base64
import uuid

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from models import CA, Certificate, SCEPRequest, SystemConfig, db
from models.deploy import DeployBinding, DeployDelivery, DeployTarget
from tests.deploy_leftovers import delete_leftovers

_cleanup = pytest.fixture(autouse=True)(delete_leftovers)


@pytest.fixture
def https(app, monkeypatch, tmp_path):
    """The HTTPS binding row restored afterwards; files and restart never touch the host."""
    from services import https_binding
    monkeypatch.setenv('HTTPS_CERT_PATH', str(tmp_path / 'c.pem'))
    monkeypatch.setenv('HTTPS_KEY_PATH', str(tmp_path / 'k.pem'))
    written = []
    monkeypatch.setattr(https_binding, 'materialize_https_cert', lambda cert: written.append(cert.refid))
    monkeypatch.setattr('utils.service_manager.restart_service', lambda *a, **k: None)
    from services.events import event_bus
    handlers = [h for h in event_bus._handlers.get('certificate.renewed', [])
                if h is not https_binding.on_certificate_renewed]
    monkeypatch.setitem(event_bus._handlers, 'certificate.renewed',
                        handlers + [https_binding.on_certificate_renewed])
    with app.app_context():
        previous = https_binding.get_bound_refid()
    yield written
    with app.app_context():
        row = SystemConfig.query.filter_by(key=https_binding.BOUND_REFID_KEY).first()
        if row is not None:
            row.value = previous
            db.session.commit()


def _bound_row(app, ca_id, cn):
    """An issued row, a deploy binding on it, one pushing its key, and the HTTPS listener
    bound to it. Returns (row id, binding id, key binding id)."""
    from services.cert_service import CertificateService
    from services.https_binding import set_bound_refid
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        row = CertificateService.create_certificate(
            descr=cn, caref=ca.refid, dn={'CN': cn}, cert_type='server_cert',
            key_type='prime256v1', validity_days=30, username='admin')
        target = DeployTarget(name=f'follow-{uuid.uuid4().hex[:8]}', host='h.example.test',
                              username='u', private_key='k')
        db.session.add(target)
        db.session.flush()
        keyed_target = DeployTarget(name=f'follow-key-{uuid.uuid4().hex[:8]}', host='h.example.test',
                                    username='u', private_key='k')
        db.session.add(keyed_target)
        db.session.flush()
        binding = DeployBinding(target_id=target.id, certificate_id=row.id, cert_path='/srv/c.pem')
        keyed = DeployBinding(target_id=keyed_target.id, certificate_id=row.id,
                              cert_path='/srv/c.pem', key_path='/srv/k.pem')
        db.session.add_all([binding, keyed])
        db.session.commit()
        set_bound_refid(row.refid)
        return row.id, binding.id, keyed.id


def _csr(cn):
    key = ec.generate_private_key(ec.SECP256R1())
    return (x509.CertificateSigningRequestBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
            .sign(key, hashes.SHA256()))


def _assert_followed(app, old_id, binding_id, keyed_id, written, caplog):
    from services.https_binding import get_bound_refid
    with app.app_context():
        old = db.session.get(Certificate, old_id)
        binding = db.session.get(DeployBinding, binding_id)
        new = db.session.get(Certificate, binding.certificate_id)
        assert old.archived is True
        assert new.id != old_id and not new.archived
        queued = [d.event_type for d in DeployDelivery.query.filter_by(binding_id=binding_id)]
        assert queued == ['certificate.renewed']
        # The client holds the key: what needs it stays on the old row, no file is written
        assert not new.prv and written == []
        assert db.session.get(DeployBinding, keyed_id).certificate_id == old_id
        assert DeployDelivery.query.filter_by(binding_id=keyed_id).count() == 0
        assert get_bound_refid() == old.refid
    warnings = [r for r in caplog.records
                if r.levelname == 'WARNING' and 'has no private key in UCM' in r.getMessage()]
    assert len(warnings) == 1
    assert f'deploy binding {keyed_id}' in warnings[0].getMessage()
    assert 'HTTPS listener binding' in warnings[0].getMessage()


def _protocol_renewal(app, old_id, source):
    from services.ca import CAService
    with app.app_context():
        old = db.session.get(Certificate, old_id)
        held = x509.load_pem_x509_certificate(base64.b64decode(old.crt))
        ca = CA.query.filter_by(refid=old.caref).one()
        if source == 'est':
            from api.est_protocol import sign_est_csr
            sign_est_csr(ca, _csr(old.descr), renewal_of=held, supersedes=old)
        else:
            CAService.sign_csr_from_crypto(ca=ca, csr=_csr(old.descr), validity_days=30,
                                           source=source, renewal_of=held, supersedes=old)


@pytest.mark.parametrize('source', ['est', 'wstep-renewal'])
def test_est_and_wstep_renewal_moves_the_bindings(app, create_ca, https, caplog, source):
    ca = create_ca(cn=f'follow {source} CA')
    old_id, binding_id, keyed_id = _bound_row(app, ca['id'], f'follow-{source}.example.test')
    _protocol_renewal(app, old_id, source)
    _assert_followed(app, old_id, binding_id, keyed_id, https, caplog)


@pytest.mark.parametrize('queue', ['scep', 'approvals'])
def test_scep_approved_renewal_moves_the_bindings(app, auth_client, create_ca, https, caplog, queue):
    ca = create_ca(cn=f'follow scep {queue} CA')
    old_id, binding_id, keyed_id = _bound_row(app, ca['id'], f'follow-scep-{queue}.example.test')
    with app.app_context():
        old = db.session.get(Certificate, old_id)
        req = SCEPRequest(transaction_id=f'txn-follow-{uuid.uuid4().hex[:8]}', ca_refid=old.caref,
                          csr=base64.b64encode(_csr(old.descr).public_bytes(serialization.Encoding.DER)).decode(),
                          status='pending', subject=f'CN={old.descr}', renewal_of=old.crt)
        db.session.add(req)
        db.session.commit()
        req_id = req.id
    try:
        if queue == 'scep':
            r = auth_client.post(f'/api/v2/scep/{req_id}/approve', data='{}', content_type='application/json')
            assert r.status_code == 200, r.get_json()
        else:
            from types import SimpleNamespace
            from services.scep import approval
            with app.app_context():
                approval._issue(SimpleNamespace(get_approvals=lambda: []), {'scep_request_id': req_id})
        _assert_followed(app, old_id, binding_id, keyed_id, https, caplog)
    finally:
        with app.app_context():
            SCEPRequest.query.filter_by(id=req_id).delete()
            db.session.commit()


def test_a_target_already_bound_to_the_new_row_keeps_one_binding(app, create_ca, https):
    """Two archived twins bound to the same target: the new row gets one binding for it."""
    ca = create_ca(cn='follow twin CA')
    old_id, binding_id, _ = _bound_row(app, ca['id'], 'follow-twin.example.test')
    with app.app_context():
        old = db.session.get(Certificate, old_id)
        columns = {c.name: getattr(old, c.name) for c in Certificate.__table__.columns
                   if c.name not in ('id', 'refid', 'serial_number', 'caref')}
        twin = Certificate(refid=str(uuid.uuid4()), serial_number=old.serial_number, caref=None, **columns)
        db.session.add(twin)
        db.session.flush()
        target_id = db.session.get(DeployBinding, binding_id).target_id
        db.session.add(DeployBinding(target_id=target_id, certificate_id=twin.id, cert_path='/srv/t.pem'))
        db.session.commit()
        twin_id = twin.id
    _protocol_renewal(app, old_id, 'est')
    with app.app_context():
        new_id = db.session.get(DeployBinding, binding_id).certificate_id
        assert db.session.get(Certificate, twin_id).archived is True
        assert DeployBinding.query.filter_by(certificate_id=new_id, target_id=target_id).count() == 1


def test_a_successor_holding_a_key_takes_every_binding(app, create_ca, https, caplog):
    """The rule's other side: with a key in UCM, the key binding and the HTTPS binding follow."""
    from services.ca.ca_signing import _bindings_follow
    from services.cert_service import CertificateService
    from services.https_binding import get_bound_refid
    ca = create_ca(cn='follow keyed CA')
    old_id, binding_id, keyed_id = _bound_row(app, ca['id'], 'follow-keyed.example.test')
    with app.app_context():
        successor = CertificateService.create_certificate(
            descr='follow-keyed.example.test', caref=db.session.get(CA, ca['id']).refid,
            dn={'CN': 'follow-keyed.example.test'}, cert_type='server_cert',
            key_type='prime256v1', validity_days=30, username='admin')
        assert successor.has_private_key
        _bindings_follow([old_id], successor)
        db.session.commit()
        assert db.session.get(DeployBinding, binding_id).certificate_id == successor.id
        assert db.session.get(DeployBinding, keyed_id).certificate_id == successor.id
        assert get_bound_refid() == successor.refid
    assert not [r for r in caplog.records if 'has no private key in UCM' in r.getMessage()]
