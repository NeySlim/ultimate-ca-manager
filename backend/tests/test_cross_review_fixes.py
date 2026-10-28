"""Review fixes on the cross-certificate work: legacy two-record status, lazy issuer, gates, inputs (#400)."""
import base64
import json
import uuid
from datetime import timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes

from models import CA, Certificate, RevokedSerial, db
from models.ca_cross_certificate import CACrossCertificate
from services.ocsp_service import OCSPService
from services.smart_import.importer import SmartImporter
from tests.fixtures.cross_pki import build_cross_pki, make_cert, new_key, pem
from utils.datetime_utils import utc_now


def _x(b, xid=None, tail=''):
    return f'/api/v2/cas/{b}/cross-certificates' + (f'/{xid}' if xid else '') + tail


def _b64(cert):
    return base64.b64encode(pem(cert).encode()).decode()


def _leaf_row(pki, caref, revoked):
    leaf = make_cert(f'leg-{uuid.uuid4().hex[:6]}.example', new_key(), pki.name_b, pki.key_b, ca=False, days=30)
    row = Certificate(refid=uuid.uuid4().hex, descr='legacy leaf', caref=caref, crt=_b64(leaf),
                      serial_number=str(leaf.serial_number), subject=leaf.subject.rfc4514_string(),
                      issuer=leaf.issuer.rfc4514_string(), revoked=revoked,
                      revoked_at=utc_now() if revoked else None, revoke_reason='keyCompromise' if revoked else None,
                      valid_from=utc_now(), valid_to=utc_now() + timedelta(days=30))
    db.session.add(row)
    db.session.commit()
    return leaf, row


@pytest.fixture
def legacy(app):
    """Root A, then B's cross-certificate (lower id) and Root B stored as two records."""
    pki = build_cross_pki()
    with app.app_context():
        for cert in (pki.root_a, pki.cross_b, pki.root_b):
            SmartImporter().execute(pem(cert))
        records = CA.query.filter(CA.subject.contains(f'Root B {pki.tag}')).order_by(CA.id).all()
        assert len(records) == 2, 'the legacy setup stores two records'
        cross_rec, root = records
        assert cross_rec.subject != cross_rec.issuer and root.subject == root.issuer
        yield pki, root.id, cross_rec.id


def test_ocsp_finds_a_revoked_leaf_linked_to_the_cross_certificate_record(app, legacy):
    pki, root_id, cross_id = legacy
    with app.app_context():
        root, cross_rec = db.session.get(CA, root_id), db.session.get(CA, cross_id)
        leaf, _ = _leaf_row(pki, cross_rec.refid, revoked=True)
        good, _ = _leaf_row(pki, cross_rec.refid, revoked=False)
        assert OCSPService._status_for_serial(root, leaf.serial_number)[1] == 'revoked'
        assert OCSPService._status_for_serial(root, good.serial_number)[1] == 'good'


def test_a_deleted_revoked_leaf_stays_revoked_through_the_sibling_record(app, legacy):
    from services.cert.issued_lookup import REVOKED, issued_certificate_status
    pki, root_id, cross_id = legacy
    with app.app_context():
        root, cross_rec = db.session.get(CA, root_id), db.session.get(CA, cross_id)
        leaf, row = _leaf_row(pki, cross_rec.refid, revoked=False)
        db.session.add(RevokedSerial(caref=cross_rec.refid, serial_number=str(leaf.serial_number),
                                     revoked_at=utc_now(), revoke_reason='keyCompromise',
                                     valid_to=utc_now() + timedelta(days=30)))
        db.session.delete(row)
        db.session.commit()
        assert issued_certificate_status(root, leaf)[1] == REVOKED
        assert OCSPService._status_for_serial(root, leaf.serial_number)[1] == 'revoked'


@pytest.fixture
def b_with_cross_before_a(app, auth_client):
    """Root B held; B's cross-certificate by A attached while A is not held."""
    pki = build_cross_pki()
    with app.app_context():
        SmartImporter().execute(pem(pki.root_b))
        b = CA.query.filter_by(descr=pki.name_b).one().id
    r = auth_client.post(_x(b), json={'certificate': pem(pki.cross_b)})
    assert r.status_code == 201, r.data
    assert r.get_json()['data']['issuer_caref'] is None
    return pki, b, r.get_json()['data']['id']


def test_issuer_imported_after_the_attach_answers_ocsp_and_takes_the_revocation(app, auth_client,
                                                                               b_with_cross_before_a):
    pki, b, xid = b_with_cross_before_a
    with app.app_context():
        SmartImporter().execute(pem(pki.root_a))
        a = CA.query.filter_by(descr=pki.name_a).one()
        assert OCSPService._status_for_serial(a, pki.cross_b.serial_number)[1] == 'good'
        a_refid = a.refid
    r = auth_client.post(_x(b, xid, '/revoke'), json={'reason': 'keyCompromise'})
    assert r.status_code == 200, r.data
    with app.app_context():
        a = CA.query.filter_by(refid=a_refid).one()
        assert OCSPService._status_for_serial(a, pki.cross_b.serial_number)[1] == 'revoked'
        assert RevokedSerial.query.filter_by(caref=a_refid).count() == 1


def test_issuer_deleted_and_imported_again_is_found_under_its_new_refid(app, auth_client, world_attached):
    pki, b, xid = world_attached
    with app.app_context():
        old = CA.query.filter_by(descr=pki.name_a).one()
        db.session.delete(old)
        db.session.commit()
        SmartImporter().execute(pem(pki.root_a))
        new = CA.query.filter_by(descr=pki.name_a).one()
        assert OCSPService._status_for_serial(new, pki.cross_b.serial_number)[1] == 'good'
    assert auth_client.post(_x(b, xid, '/revoke'), json={}).status_code == 200


@pytest.fixture
def world_attached(app, auth_client):
    pki = build_cross_pki()
    with app.app_context():
        SmartImporter().execute(pem(pki.root_a))
        SmartImporter().execute(pem(pki.root_b))
        b = CA.query.filter_by(descr=pki.name_b).one().id
    r = auth_client.post(_x(b), json={'certificate': pem(pki.cross_b)})
    assert r.status_code == 201, r.data
    return pki, b, r.get_json()['data']['id']


def test_revoking_a_cross_certificate_goes_through_the_approval_gate(app, auth_client, create_user, world_attached):
    from tests.test_approval_revoke_renew import _drop_policy, _json, _login, _policy
    pki, b, xid = world_attached
    with app.app_context():
        a_id = CA.query.filter_by(descr=pki.name_a).one().id
    pid = _policy(app, a_id, 'xc-rev', ['revocation'])
    try:
        operator, _ = _login(app, create_user)
        r = _json(operator, 'post', _x(b, xid, '/revoke'), {'reason': 'keyCompromise'})
        assert r.status_code == 200, r.get_json()
        body = r.get_json()['data']
        assert body['approval_required'] is True
        with app.app_context():
            assert db.session.get(CACrossCertificate, xid).revoked is False
            assert RevokedSerial.query.filter_by(serial_number=str(pki.cross_b.serial_number)).count() == 0
        r = _json(auth_client, 'post', f"/api/v2/approvals/{body['approval_id']}/approve", {})
        assert r.status_code == 200, r.get_json()
        with app.app_context():
            db.session.expire_all()
            row = db.session.get(CACrossCertificate, xid)
            assert row.revoked and row.revoke_reason == 'keyCompromise'
            assert RevokedSerial.query.filter_by(serial_number=str(pki.cross_b.serial_number)).count() == 1
            assert db.session.get(CA, b).revoked is False
    finally:
        _drop_policy(app, pid)


def test_malformed_json_never_becomes_an_unspecified_revocation(app, auth_client, world_attached):
    _, b, xid = world_attached
    r = auth_client.post(_x(b, xid, '/revoke'), data='{reason: keyCompromise', content_type='application/json')
    assert r.status_code == 400
    with app.app_context():
        assert db.session.get(CACrossCertificate, xid).revoked is False
    assert auth_client.post(_x(b, xid, '/revoke'), json={}).status_code == 200


def test_attach_input_types(app, auth_client, world_attached):
    pki, b, _ = world_attached
    other = make_cert(pki.name_b, pki.key_b, pki.name_a, pki.key_a, days=100)
    for bad in (['x'], 10000000000, {'a': 1}, True):
        assert auth_client.post(_x(b), json={'certificate': bad}).status_code == 400, bad
    assert auth_client.post(_x(b), json={'certificate': pem(other), 'served': 'false'}).status_code == 400
    r = auth_client.post(_x(b), json={'certificate': pem(other), 'served': False})
    assert r.status_code == 201 and r.get_json()['data']['served'] is False


def test_revoking_keeps_the_record_the_issuer_already_holds(app, auth_client, world_attached):
    pki, b, xid = world_attached
    earlier = utc_now() - timedelta(days=3)
    with app.app_context():
        a = CA.query.filter_by(descr=pki.name_a).one()
        db.session.add(RevokedSerial(caref=a.refid, serial_number=str(pki.cross_b.serial_number),
                                     revoked_at=earlier, revoke_reason='keyCompromise',
                                     valid_to=utc_now() + timedelta(days=30)))
        db.session.commit()
    r = auth_client.post(_x(b, xid, '/revoke'), json={'reason': 'superseded'})
    assert r.status_code == 409
    with app.app_context():
        record = RevokedSerial.query.filter_by(serial_number=str(pki.cross_b.serial_number)).one()
        assert record.revoke_reason == 'keyCompromise' and record.revoked_at == earlier
        row = db.session.get(CACrossCertificate, xid)
        assert row.revoked and row.revoke_reason == 'keyCompromise' and row.served is False


def test_export_filename_is_sanitised(app, auth_client, world_attached):
    pki, b, xid = world_attached
    with app.app_context():
        db.session.get(CA, b).descr = 'Bad "name"/x'
        db.session.commit()
    disposition = auth_client.get(_x(b, xid, '/export')).headers['Content-Disposition']
    assert disposition.count('"') == 2 and '/' not in disposition


def test_expiry_alert_payload_does_not_pose_as_a_certificate(app, auth_client, world_attached):
    from services.ca.cross_certs import expiring_alerts
    pki, b, xid = world_attached
    with app.app_context():
        row = db.session.get(CACrossCertificate, xid)
        row.valid_to = utc_now() + timedelta(days=5)
        db.session.commit()
        soon, _ = expiring_alerts(days=30)
        scope, payload = next(item for item in soon if item[1]['cross_certificate_id'] == xid)
        assert 'id' not in payload and payload['ca_refid'] == db.session.get(CA, b).refid
        assert scope == row.issuer_caref


def test_self_signed_first_ranks_a_rollover_certificate_below_the_root(app):
    from utils.cert_issuer import self_signed_first
    tag = uuid.uuid4().hex[:6]
    key1, key2 = new_key(), new_key()
    name = f'Roll {tag}'
    new_with_old = make_cert(name, key2, name, key1)
    own = make_cert(name, key2)
    with app.app_context():
        rows = []
        for descr, cert in (('rollover', new_with_old), ('root', own)):
            ca = CA(refid=uuid.uuid4().hex, descr=f'{descr} {tag}', crt=_b64(cert), serial=0,
                    subject=cert.subject.rfc4514_string(), issuer=cert.issuer.rfc4514_string())
            db.session.add(ca)
            rows.append(ca)
        db.session.commit()
        assert [c.descr for c in self_signed_first(rows)] == [f'root {tag}', f'rollover {tag}']


def test_importing_a_ca_certificate_through_the_certificate_route_needs_write_cas(app, auth_client, create_user,
                                                                                 world_attached):
    from models.rbac import CustomRole
    from models import User
    from tests.test_approval_revoke_renew import _json
    pki, b, _ = world_attached
    extra = make_cert(pki.name_b, pki.key_b, pki.name_a, pki.key_a, days=100)
    user = create_user(role='viewer')
    with app.app_context():
        role = CustomRole(name=f'certs-only-{uuid.uuid4().hex[:6]}',
                          permissions=['read:certificates', 'write:certificates'])
        db.session.add(role)
        db.session.flush()
        User.query.filter_by(username=user['username']).update({'custom_role_id': role.id})
        db.session.commit()
    client = app.test_client()
    assert _json(client, 'post', '/api/v2/auth/login',
                 {'username': user['username'], 'password': 'TestPass123!'}).status_code == 200
    r = client.post('/api/v2/certificates/import', data={'pem_content': pem(extra)},
                    content_type='multipart/form-data')
    assert r.status_code == 403, r.data
    with app.app_context():
        assert CACrossCertificate.query.filter_by(ca_id=b).count() == 1


def test_the_issuer_of_a_cross_certificate_is_the_self_signed_record_of_its_key(app, auth_client):
    pki = build_cross_pki()
    name_c, key_c = f'Cross Root C {pki.tag}', new_key()
    cross_a = make_cert(pki.name_a, pki.key_a, name_c, key_c)
    with app.app_context():
        for cert in (cross_a, pki.root_a, pki.root_b):
            SmartImporter().execute(pem(cert))
        records = CA.query.filter(CA.subject.contains(f'Root A {pki.tag}')).order_by(CA.id).all()
        assert len(records) == 2 and records[0].subject != records[0].issuer
        root_a, b = records[1], CA.query.filter_by(descr=pki.name_b).one()
    r = auth_client.post(_x(b.id), json={'certificate': pem(pki.cross_b)})
    assert r.status_code == 201, r.data
    assert r.get_json()['data']['issuer_caref'] == root_a.refid



def test_revoke_finds_an_issuer_imported_after_the_attach_without_any_ocsp_call(app, auth_client,
                                                                                b_with_cross_before_a):
    pki, b, xid = b_with_cross_before_a
    from services.ca import cross_certs
    with app.app_context():
        SmartImporter().execute(pem(pki.root_a))
        cross_certs.revoke(db.session.get(CACrossCertificate, xid), 'unspecified', 'tester')
        assert RevokedSerial.query.filter_by(serial_number=str(pki.cross_b.serial_number)).count() == 1
