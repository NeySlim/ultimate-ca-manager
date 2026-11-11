"""A protocol renewal whose successor has no key in UCM leaves the bindings that push
the key, and the HTTPS listener binding, on the previous certificate. They carry a
state the API reads, one bus event each after the commit, and a work-queue item; the
state clears on reattachment, removal, or when the successor receives its key."""
import base64
import json
import uuid

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from sqlalchemy import text

from models import CA, Certificate, SCEPRequest, SystemConfig, db
from models.deploy import DeployBinding, DeployDelivery
from services.events import event_bus
from tests.deploy_leftovers import delete_leftovers
from tests.test_renewal_bindings_follow import _bound_row, _csr, _protocol_renewal, https  # noqa: F401

EVENT = 'certificate.binding_left_behind'
REASON = 'successor_without_key'

_cleanup = pytest.fixture(autouse=True)(delete_leftovers)


@pytest.fixture(autouse=True)
def _no_https_flag_left(app):
    yield
    from services.binding_attention import HTTPS_LEFT_BEHIND_KEY
    with app.app_context():
        SystemConfig.query.filter_by(key=HTTPS_LEFT_BEHIND_KEY).delete()
        db.session.commit()


@pytest.fixture
def seen(app, monkeypatch):
    """Events of EVENT, each with what another connection reads at that moment (committed)."""
    events = []
    real = event_bus.emit

    def capture(event_type, payload, ca_refid=None, meta=None):
        if event_type == EVENT:
            binding = payload.get('binding') or {}
            with db.engine.connect() as conn:
                if binding.get('type') == 'deploy':
                    stored = conn.execute(text(
                        'SELECT attention_successor_id FROM deploy_bindings WHERE id = :i'),
                        {'i': binding['id']}).scalar()
                else:
                    from services.binding_attention import HTTPS_LEFT_BEHIND_KEY
                    stored = conn.execute(text(
                        'SELECT value FROM system_config WHERE key = :k'),
                        {'k': HTTPS_LEFT_BEHIND_KEY}).scalar()
            events.append((payload, stored))
        return real(event_type, payload, ca_refid, meta)

    monkeypatch.setattr(event_bus, 'emit', capture)
    return events


def _write_listener_cert(app, cert_id):
    """The HTTPS file the listener serves: the bound row's certificate."""
    import os
    with app.app_context():
        pem = base64.b64decode(db.session.get(Certificate, cert_id).crt)
    with open(os.environ['HTTPS_CERT_PATH'], 'wb') as f:
        f.write(pem)


def _assert_flagged(app, auth_client, old_id, binding_id, keyed_id, seen):
    from services.dashboard_aggregates import work_queue
    with app.app_context():
        db.session.expire_all()
        new_id = db.session.get(DeployBinding, binding_id).certificate_id
        new = db.session.get(Certificate, new_id)
        keyed = db.session.get(DeployBinding, keyed_id)
        assert keyed.certificate_id == old_id
        assert (keyed.attention_reason, keyed.attention_successor_id) == (REASON, new_id)
        moved = db.session.get(DeployBinding, binding_id)
        assert (moved.attention_reason, moved.attention_successor_id) == (None, None)
        new_refid = new.refid
        queue = work_queue(db.session, 50, kinds=['deploy_binding_left_behind', 'https_binding_left_behind'])

    listed = {b['id']: b for b in auth_client.get(
        f'/api/v2/deploy/bindings?certificate_id={old_id}').get_json()['data']}
    assert listed[keyed_id]['needs_attention'] == {
        'reason': REASON, 'successor_id': new_id, 'successor_refid': new_refid,
        'successor_has_key': False, 'can_reattach': False}
    _write_listener_cert(app, old_id)
    bound = auth_client.get('/api/v2/system/https/cert-info').get_json()['data']['bound_certificate']
    assert bound['needs_attention']['successor_refid'] == new_refid
    assert bound['needs_attention']['reason'] == REASON

    # One event per binding left behind, emitted once its state is committed
    deploy = [(p, s) for p, s in seen if p['binding']['type'] == 'deploy']
    listener = [(p, s) for p, s in seen if p['binding']['type'] == 'https']
    assert [(p['binding']['id'], s) for p, s in deploy] == [(keyed_id, new_id)]
    assert [s for _, s in listener] == [new_refid]
    for payload, _ in seen:
        assert payload['certificate']['id'] == new_id
        assert payload['previous_certificate']['id'] == old_id
        assert payload['reason'] == REASON

    items = {(i['kind'], i['id']): i for i in queue['items']}
    item = items[('deploy_binding_left_behind', keyed_id)]
    assert item['tier'] == 'critical'
    assert item['href_hint'] == f'/certificates/{old_id}?binding={keyed_id}'
    assert [i['href_hint'] for i in queue['items'] if i['kind'] == 'https_binding_left_behind'] == [
        '/settings?tab=https']
    return new_id


@pytest.mark.parametrize('source', ['est', 'wstep-renewal'])
def test_est_and_wstep_keyless_renewal_flags_what_stayed(app, auth_client, create_ca, https, seen, source):
    ca = create_ca(cn=f'left behind {source} CA')
    old_id, binding_id, keyed_id = _bound_row(app, ca['id'], f'left-{source}.example.test')
    _protocol_renewal(app, old_id, source)
    _assert_flagged(app, auth_client, old_id, binding_id, keyed_id, seen)


@pytest.mark.parametrize('queue', ['scep', 'approvals'])
def test_scep_approved_keyless_renewal_flags_what_stayed(app, auth_client, create_ca, https, seen, queue):
    ca = create_ca(cn=f'left behind scep {queue} CA')
    old_id, binding_id, keyed_id = _bound_row(app, ca['id'], f'left-scep-{queue}.example.test')
    with app.app_context():
        old = db.session.get(Certificate, old_id)
        req = SCEPRequest(transaction_id=f'txn-left-{uuid.uuid4().hex[:8]}', ca_refid=old.caref,
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
        _assert_flagged(app, auth_client, old_id, binding_id, keyed_id, seen)
    finally:
        with app.app_context():
            SCEPRequest.query.filter_by(id=req_id).delete()
            db.session.commit()


def test_scep_auto_approved_renewal_flags_what_stayed(app, auth_client, create_ca, https, seen):
    """A RenewalReq signed by the issued certificate, approved on arrival."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    from services.https_binding import set_bound_refid
    from services.scep.scep_service import SCEPService
    from tests.test_scep_renewal_challenge import ORIGINAL, _csr as scep_csr, _enroll, _message
    from tests.test_scep_rfc8894_operations import PKI_STATUS_OID, _load_ca_material, _response_attributes
    from models.deploy import DeployTarget
    ca_data = create_ca(cn=f'left behind scep auto CA {uuid.uuid4().hex[:6]}')
    cn = 'left-scep-auto.example.test'
    with app.app_context():
        ca, ca_cert = _load_ca_material(ca_data['id'])[:2]
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        issued = _enroll(ca, ca_cert, key, cn)
        old = Certificate.query.filter_by(serial_number=str(issued.serial_number), caref=ca.refid).one()
        target = DeployTarget(name=f'left-auto-{uuid.uuid4().hex[:8]}', host='h.example.test',
                              username='u', private_key='k')
        db.session.add(target)
        db.session.flush()
        keyed = DeployBinding(target_id=target.id, certificate_id=old.id,
                              cert_path='/srv/c.pem', key_path='/srv/k.pem')
        db.session.add(keyed)
        db.session.commit()
        old_id, keyed_id = old.id, keyed.id
        set_bound_refid(old.refid)
        request = _message(ca_cert, issued, key, 17, scep_csr(
            rsa.generate_private_key(public_exponent=65537, key_size=2048), cn, ORIGINAL))
        response, _ = SCEPService(ca.refid, challenge_password=ORIGINAL,
                                  auto_approve=True).process_pkcs_req(request, '127.0.0.1')
        assert _response_attributes(response)[PKI_STATUS_OID] == '0'
        db.session.expire_all()
        flagged = db.session.get(DeployBinding, keyed_id)
        assert flagged.certificate_id == old_id and flagged.attention_reason == REASON
        new_id = flagged.attention_successor_id
        new_refid = db.session.get(Certificate, new_id).refid
    assert [(p['binding']['id'], s) for p, s in seen if p['binding']['type'] == 'deploy'] == [(keyed_id, new_id)]
    assert [s for p, s in seen if p['binding']['type'] == 'https'] == [new_refid]


def _renew_with_known_key(app, old_id):
    """An EST renewal whose new key the test keeps; returns (successor id, key PEM)."""
    from api.est_protocol import sign_est_csr
    key = ec.generate_private_key(ec.SECP256R1())
    with app.app_context():
        old = db.session.get(Certificate, old_id)
        csr = (x509.CertificateSigningRequestBuilder()
               .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, old.descr)]))
               .sign(key, hashes.SHA256()))
        held = x509.load_pem_x509_certificate(base64.b64decode(old.crt))
        sign_est_csr(CA.query.filter_by(refid=old.caref).one(), csr, renewal_of=held, supersedes=old)
        new_id = Certificate.query.filter(Certificate.id > old_id, Certificate.descr == old.descr).one().id
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    return new_id, pem


def test_the_successor_receiving_its_key_takes_the_bindings_left_behind(app, auth_client, create_ca, https, seen):
    from services.binding_attention import HTTPS_LEFT_BEHIND_KEY
    from services.https_binding import get_bound_refid
    ca = create_ca(cn='left behind key upload CA')
    old_id, _, keyed_id = _bound_row(app, ca['id'], 'left-key-upload.example.test')
    new_id, key_pem = _renew_with_known_key(app, old_id)
    r = auth_client.post(f'/api/v2/certificates/{new_id}/key', data=json.dumps({'key': key_pem}),
                         content_type='application/json')
    assert r.status_code == 200, r.get_json()
    with app.app_context():
        keyed = db.session.get(DeployBinding, keyed_id)
        assert keyed.certificate_id == new_id
        assert (keyed.attention_reason, keyed.attention_successor_id) == (None, None)
        assert [d.event_type for d in DeployDelivery.query.filter_by(binding_id=keyed_id)] == ['binding.updated']
        new_refid = db.session.get(Certificate, new_id).refid
        assert get_bound_refid() == new_refid
        assert SystemConfig.query.filter_by(key=HTTPS_LEFT_BEHIND_KEY).first() is None
    assert https == [new_refid]


def test_reattaching_needs_the_key_or_no_key_push_and_clears_the_state(app, auth_client, create_ca, https, seen):
    ca = create_ca(cn='left behind reattach CA')
    old_id, _, keyed_id = _bound_row(app, ca['id'], 'left-reattach.example.test')
    _protocol_renewal(app, old_id, 'est')
    url = f'/api/v2/deploy/bindings/{keyed_id}/reattach'
    refused = auth_client.post(url, data='{}', content_type='application/json')
    assert refused.status_code == 409
    with app.app_context():
        assert db.session.get(DeployBinding, keyed_id).certificate_id == old_id
    # The operator stops sending the key: the binding can now follow the successor
    r = auth_client.patch(f'/api/v2/deploy/bindings/{keyed_id}', data=json.dumps({'key_path': None}),
                          content_type='application/json')
    assert r.status_code == 200, r.get_json()
    listed = auth_client.get(f'/api/v2/deploy/bindings?certificate_id={old_id}').get_json()['data']
    assert next(b for b in listed if b['id'] == keyed_id)['needs_attention']['can_reattach'] is True
    r = auth_client.post(url, data='{}', content_type='application/json')
    assert r.status_code == 200, r.get_json()
    with app.app_context():
        keyed = db.session.get(DeployBinding, keyed_id)
        assert keyed.certificate_id != old_id
        assert (keyed.attention_reason, keyed.attention_successor_id) == (None, None)
        assert r.get_json()['data']['needs_attention'] is None
    assert auth_client.post(url, data='{}', content_type='application/json').status_code == 409


def test_a_keyless_renewal_flags_nothing_when_no_binding_pushes_the_key(app, create_ca, https, seen):
    from services.https_binding import set_bound_refid
    ca = create_ca(cn='left behind nothing CA')
    old_id, binding_id, keyed_id = _bound_row(app, ca['id'], 'left-nothing.example.test')
    with app.app_context():
        db.session.delete(db.session.get(DeployBinding, keyed_id))
        db.session.commit()
        set_bound_refid('')
    _protocol_renewal(app, old_id, 'est')
    with app.app_context():
        moved = db.session.get(DeployBinding, binding_id)
        assert moved.certificate_id != old_id
        assert (moved.attention_reason, moved.attention_successor_id) == (None, None)
    assert seen == []


def test_rebinding_https_or_deleting_the_successor_clears_the_states(app, auth_client, create_ca, https, seen):
    from services.binding_attention import HTTPS_LEFT_BEHIND_KEY
    from services.cert_service import CertificateService
    from services.https_binding import set_bound_refid
    ca = create_ca(cn='left behind clear CA')
    old_id, _, keyed_id = _bound_row(app, ca['id'], 'left-clear.example.test')
    _protocol_renewal(app, old_id, 'est')
    with app.app_context():
        new_id = db.session.get(DeployBinding, keyed_id).attention_successor_id
        assert SystemConfig.query.filter_by(key=HTTPS_LEFT_BEHIND_KEY).first().value
        set_bound_refid('')  # "stop following renewals"
        assert SystemConfig.query.filter_by(key=HTTPS_LEFT_BEHIND_KEY).first() is None
        assert CertificateService.delete_certificate(new_id, username='admin')
        keyed = db.session.get(DeployBinding, keyed_id)
        assert (keyed.attention_reason, keyed.attention_successor_id) == (None, None)
    # Removing a flagged binding takes its state with it
    assert auth_client.delete(f'/api/v2/deploy/bindings/{keyed_id}').status_code == 200


def test_a_renewal_rolled_back_announces_nothing(app, create_ca, https, seen):
    """Marks of a rolled-back renewal never reach the bus, even when a later renewal in the
    same session reuses the successor's id."""
    from api.est_protocol import sign_est_csr
    ca = create_ca(cn='left behind rollback CA')
    failed_id, _, failed_keyed = _bound_row(app, ca['id'], 'left-rollback-a.example.test')
    ok_id, _, ok_keyed = _bound_row(app, ca['id'], 'left-rollback-b.example.test')

    def refuse(_row):
        raise RuntimeError('refused after the bindings moved')

    with app.app_context():
        old = db.session.get(Certificate, failed_id)
        held = x509.load_pem_x509_certificate(base64.b64decode(old.crt))
        with pytest.raises(RuntimeError):
            sign_est_csr(CA.query.filter_by(refid=old.caref).one(), _csr(old.descr),
                         renewal_of=held, supersedes=old, on_stored=refuse)
        assert db.session.get(DeployBinding, failed_keyed).attention_reason is None
        old = db.session.get(Certificate, ok_id)
        held = x509.load_pem_x509_certificate(base64.b64decode(old.crt))
        sign_est_csr(CA.query.filter_by(refid=old.caref).one(), _csr(old.descr),
                     renewal_of=held, supersedes=old)
    assert [p['binding']['id'] for p, _ in seen if p['binding']['type'] == 'deploy'] == [ok_keyed]


def test_a_second_keyless_renewal_retargets_what_was_left_behind(app, auth_client, create_ca, https, seen):
    """O renewed to S1 without a key, then S1 to S2: the flags name S2, never the superseded S1."""
    from services.binding_attention import https_left_behind_for
    from services.https_binding import get_bound_refid
    ca = create_ca(cn='left behind twice CA')
    old_id, _, keyed_id = _bound_row(app, ca['id'], 'left-twice.example.test')
    _protocol_renewal(app, old_id, 'est')
    with app.app_context():
        first_id = db.session.get(DeployBinding, keyed_id).attention_successor_id
    del seen[:]
    second_id, key_pem = _renew_with_known_key(app, first_id)
    with app.app_context():
        keyed = db.session.get(DeployBinding, keyed_id)
        assert keyed.certificate_id == old_id
        assert (keyed.attention_reason, keyed.attention_successor_id) == (REASON, second_id)
        second_refid = db.session.get(Certificate, second_id).refid
        assert https_left_behind_for() == second_refid
        assert get_bound_refid() == db.session.get(Certificate, old_id).refid
    assert [(p['binding']['id'], s) for p, s in seen if p['binding']['type'] == 'deploy'] == [
        (keyed_id, second_id)]
    assert [s for p, s in seen if p['binding']['type'] == 'https'] == [second_refid]
    r = auth_client.post(f'/api/v2/certificates/{second_id}/key', data=json.dumps({'key': key_pem}),
                         content_type='application/json')
    assert r.status_code == 200, r.get_json()
    with app.app_context():
        keyed = db.session.get(DeployBinding, keyed_id)
        assert keyed.certificate_id == second_id
        assert (keyed.attention_reason, keyed.attention_successor_id) == (None, None)
        assert get_bound_refid() == second_refid
        assert https_left_behind_for() == ''


def test_a_keyed_successor_of_the_awaited_row_takes_what_was_left_behind(app, create_ca, https, seen):
    from services.binding_attention import https_left_behind_for
    from services.ca.ca_signing import _bindings_follow
    from services.cert_service import CertificateService
    from services.https_binding import get_bound_refid
    ca = create_ca(cn='left behind keyed next CA')
    old_id, _, keyed_id = _bound_row(app, ca['id'], 'left-keyed-next.example.test')
    _protocol_renewal(app, old_id, 'est')
    with app.app_context():
        first_id = db.session.get(DeployBinding, keyed_id).attention_successor_id
        ca_row = db.session.get(CA, ca['id'])
        nxt = CertificateService.create_certificate(
            descr='left-keyed-next.example.test', caref=ca_row.refid,
            dn={'CN': 'left-keyed-next.example.test'}, cert_type='server_cert',
            key_type='prime256v1', validity_days=30, username='admin')
        assert nxt.has_private_key
        _bindings_follow([first_id], nxt)
        db.session.commit()
        keyed = db.session.get(DeployBinding, keyed_id)
        assert keyed.certificate_id == nxt.id
        assert (keyed.attention_reason, keyed.attention_successor_id) == (None, None)
        assert get_bound_refid() == nxt.refid
        assert https_left_behind_for() == ''

