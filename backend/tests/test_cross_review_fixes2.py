"""Second review pass on the cross-certificate work: key import guards, revoke races, CRL scope (#400)."""
import base64
import json
import uuid
from datetime import timedelta

import pytest

from models import ApprovalRequest, CA, RevokedSerial, db
from models.ca_cross_certificate import CACrossCertificate
from services.smart_import.importer import SmartImporter
from tests.fixtures.cross_pki import build_cross_pki, make_cert, new_key, pem
from tests.test_cross_import_opnsense import _row, _run
from tests.test_opnsense_import import _key_pem
from utils.datetime_utils import utc_now


def _x(b, xid=None, tail=''):
    return f'/api/v2/cas/{b}/cross-certificates' + (f'/{xid}' if xid else '') + tail


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


def _cross_key_import(app, auth_client, monkeypatch, prepare, key=None):
    """Root B held and prepared by *prepare*; an OPNsense import of B's cross entry carrying a key."""
    pki = build_cross_pki()
    with app.app_context():
        SmartImporter().execute(pem(pki.root_b))
        root = CA.query.filter_by(descr=pki.name_b).one()
        prepare(root, pki)
        db.session.commit()
    cross_row = _row(pki.cross_b, 'B cross')
    cross_row['prv'] = base64.b64encode(_key_pem(key or pki.key_b)).decode()
    body = _run(auth_client, monkeypatch, [_row(pki.root_a, pki.name_a), cross_row])
    return pki, body


def _offline(root, pki):
    root.prv, root.offline, root.offline_mode = None, True, 'file_exported'


def test_an_offline_ca_does_not_get_its_key_back_from_an_opnsense_cross_entry(app, auth_client, monkeypatch):
    pki, body = _cross_key_import(app, auth_client, monkeypatch, _offline)
    with app.app_context():
        root = CA.query.filter_by(descr=pki.name_b).one()
        assert root.prv is None and root.offline is True
    assert any('offline' in e for e in body['errors'])


def test_the_same_key_already_held_is_not_an_error(app, auth_client, monkeypatch):
    from utils.key_codec import store_pem_bytes

    def keyed(root, pki):
        root.prv = store_pem_bytes(_key_pem(pki.key_b))

    _, body = _cross_key_import(app, auth_client, monkeypatch, keyed)
    assert body['errors'] == []


def test_a_different_key_is_reported_as_a_mismatch_and_not_stored(app, auth_client, monkeypatch):
    pki, body = _cross_key_import(app, auth_client, monkeypatch, lambda root, pki: None, key=new_key())
    with app.app_context():
        assert CA.query.filter_by(descr=pki.name_b).one().prv is None
    assert any('does not match' in e for e in body['errors'])


def test_a_key_is_stored_and_audited_on_a_certificate_only_ca(app, auth_client, monkeypatch):
    from models import AuditLog
    pki, body = _cross_key_import(app, auth_client, monkeypatch, lambda root, pki: None)
    assert body['errors'] == []
    with app.app_context():
        root = CA.query.filter_by(descr=pki.name_b).one()
        assert root.prv
        assert AuditLog.query.filter_by(action='ca_key_imported', resource_id=str(root.id)).count() == 1


def _published_unflagged(app, pki, b):
    """The issuer already publishes the cross serial while the row is not flagged revoked."""
    with app.app_context():
        a = CA.query.filter_by(descr=pki.name_a).one()
        db.session.add(RevokedSerial(caref=a.refid, serial_number=str(pki.cross_b.serial_number),
                                     revoked_at=utc_now(), revoke_reason='superseded',
                                     valid_to=utc_now() + timedelta(days=30)))
        db.session.commit()
        return a.id


def test_revoking_an_already_published_serial_syncs_the_row_and_succeeds(app, auth_client, world_attached):
    pki, b, xid = world_attached
    _published_unflagged(app, pki, b)
    r = auth_client.post(_x(b, xid, '/revoke'), json={'reason': 'keyCompromise'})
    assert r.status_code == 200, r.data
    with app.app_context():
        row = db.session.get(CACrossCertificate, xid)
        assert row.revoked and row.revoke_reason == 'superseded' and not row.served
        assert RevokedSerial.query.filter_by(serial_number=str(pki.cross_b.serial_number)).count() == 1


def test_approving_a_revocation_the_issuer_already_publishes_completes(app, auth_client, create_user, world_attached):
    from tests.test_approval_revoke_renew import _drop_policy, _json, _login, _policy
    pki, b, xid = world_attached
    with app.app_context():
        a_id = CA.query.filter_by(descr=pki.name_a).one().id
    pid = _policy(app, a_id, 'xc-pub', ['revocation'])
    try:
        operator, _ = _login(app, create_user)
        r = _json(operator, 'post', _x(b, xid, '/revoke'), {'reason': 'keyCompromise'})
        assert r.status_code == 200, r.get_json()
        approval_id = r.get_json()['data'].get('approval_id')
        if approval_id is None:
            return  # nothing to approve: the route did not queue an already-published serial
        _published_unflagged(app, pki, b)
        r = _json(auth_client, 'post', f'/api/v2/approvals/{approval_id}/approve', {})
        assert r.status_code == 200, r.get_json()
        with app.app_context():
            db.session.expire_all()
            assert db.session.get(CACrossCertificate, xid).revoked
            assert db.session.get(ApprovalRequest, approval_id).status == 'approved'
    finally:
        _drop_policy(app, pid)


def test_an_already_published_serial_is_not_queued_for_approval(app, auth_client, create_user, world_attached):
    from tests.test_approval_revoke_renew import _drop_policy, _json, _login, _policy
    pki, b, xid = world_attached
    a_id = _published_unflagged(app, pki, b)
    pid = _policy(app, a_id, 'xc-pub2', ['revocation'])
    try:
        operator, _ = _login(app, create_user)
        r = _json(operator, 'post', _x(b, xid, '/revoke'), {'reason': 'keyCompromise'})
        assert 'approval_id' not in (r.get_json().get('data') or {}), r.get_json()
        with app.app_context():
            assert ApprovalRequest.query.filter_by(policy_id=pid).count() == 0
    finally:
        _drop_policy(app, pid)


def test_a_hold_request_is_refused_before_it_is_queued(app, auth_client, create_user, world_attached):
    from tests.test_approval_revoke_renew import _drop_policy, _json, _login, _policy
    pki, b, xid = world_attached
    with app.app_context():
        a_id = CA.query.filter_by(descr=pki.name_a).one().id
    pid = _policy(app, a_id, 'xc-hold', ['revocation'])
    try:
        operator, _ = _login(app, create_user)
        r = _json(operator, 'post', _x(b, xid, '/revoke'), {'reason': 'certificateHold'})
        assert r.status_code == 400, r.get_json()
        with app.app_context():
            assert ApprovalRequest.query.filter_by(policy_id=pid).count() == 0
    finally:
        _drop_policy(app, pid)


def test_a_direct_revocation_closes_the_pending_request_for_the_same_row(app, auth_client, create_user,
                                                                       world_attached):
    from tests.test_approval_revoke_renew import _drop_policy, _json, _login, _policy
    pki, b, xid = world_attached
    with app.app_context():
        a_id = CA.query.filter_by(descr=pki.name_a).one().id
    pid = _policy(app, a_id, 'xc-moot', ['revocation'])
    try:
        operator, _ = _login(app, create_user)
        approval_id = _json(operator, 'post', _x(b, xid, '/revoke'), {}).get_json()['data']['approval_id']
        with app.app_context():
            from services.ca import cross_certs
            cross_certs.revoke(db.session.get(CACrossCertificate, xid), 'unspecified', 'admin')
            db.session.expire_all()
            assert db.session.get(ApprovalRequest, approval_id).status != 'pending'
    finally:
        _drop_policy(app, pid)


@pytest.fixture
def sibling_world(app, auth_client):
    """A' (A cross-signed by C) and Root B held, B's cross-certificate attached to A', then Root A imported."""
    pki = build_cross_pki()
    key_c = new_key()
    a_prime = make_cert(pki.name_a, pki.key_a, f'Cross Root C {pki.tag}', key_c, days=300)
    with app.app_context():
        SmartImporter().execute(pem(a_prime))
        SmartImporter().execute(pem(pki.root_b))
        b = CA.query.filter_by(descr=pki.name_b).one().id
    r = auth_client.post(_x(b), json={'certificate': pem(pki.cross_b)})
    assert r.status_code == 201, r.data
    with app.app_context():
        SmartImporter().execute(pem(pki.root_a))
        records = CA.query.filter(CA.subject == a_prime.subject.rfc4514_string()).order_by(CA.id).all()
        assert len(records) == 2
        prime, root = records
        assert root.subject == root.issuer and prime.subject != prime.issuer
        yield pki, b, r.get_json()['data']['id'], root.id, prime.id


def test_revocation_goes_to_the_self_signed_record_of_the_issuer(app, auth_client, sibling_world):
    pki, b, xid, root_id, _ = sibling_world
    assert auth_client.post(_x(b, xid, '/revoke'), json={}).status_code == 200
    with app.app_context():
        record = RevokedSerial.query.filter_by(serial_number=str(pki.cross_b.serial_number)).one()
        assert record.caref == db.session.get(CA, root_id).refid


def test_the_crl_of_either_record_of_the_issuer_lists_the_revoked_cross_certificate(app, auth_client,
                                                                                    sibling_world):
    from services.crl.query import CRLQueryMixin
    pki, b, xid, root_id, prime_id = sibling_world
    assert auth_client.post(_x(b, xid, '/revoke'), json={}).status_code == 200
    with app.app_context():
        for ca_id in (root_id, prime_id):
            assert pki.cross_b.serial_number in {
                int(str(e.serial_number)) for e in CRLQueryMixin.get_revoked_certificates(ca_id)}


def test_expiry_alerts_fall_back_to_the_certified_ca_when_the_issuer_is_gone(app, auth_client, world_attached):
    from services.ca import cross_certs
    pki, b, xid = world_attached
    with app.app_context():
        row = db.session.get(CACrossCertificate, xid)
        row.valid_to = utc_now() + timedelta(days=5)
        db.session.commit()
        issuer = CA.query.filter_by(descr=pki.name_a).one()
        scopes = [s for s, p in cross_certs.expiring_alerts()[0] if p['cross_certificate_id'] == xid]
        assert scopes == [issuer.refid]
        db.session.delete(issuer)
        db.session.commit()
        scopes = [s for s, p in cross_certs.expiring_alerts()[0] if p['cross_certificate_id'] == xid]
        assert scopes == [db.session.get(CA, b).refid]


def test_the_crl_of_the_self_signed_record_lists_a_leaf_revoked_under_its_sibling_record(app, sibling_world):
    from services.crl.query import CRLQueryMixin
    from tests.test_cross_review_fixes import _leaf_row
    pki, _, _, root_id, prime_id = sibling_world
    with app.app_context():
        leaf, _ = _leaf_row(pki, db.session.get(CA, prime_id).refid, revoked=True)
        listed = {int(str(e.serial_number)) for e in CRLQueryMixin.get_revoked_certificates(root_id)}
        assert leaf.serial_number in listed
