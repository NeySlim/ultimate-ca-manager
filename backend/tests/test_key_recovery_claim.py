"""An approved key recovery hands the key out once: the download claims the request in one
conditional update committed before the PKCS#12 is built, and a build that fails gives the claim
back. Requester and approver are compared by account id, so a later account that reuses a
deleted requester's name is somebody else."""
import json

import pytest

import api.v2.key_recovery as key_recovery
from models import db, SystemConfig, KeyRecoveryRequest, User

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates', 'drop_new_users')

PASSWORD = 'TestPass123!'
PW = {'password': 'recover-pw-123'}


@pytest.fixture(autouse=True)
def _dual_control_off(app):
    with app.app_context():
        db.session.add(SystemConfig(key='key_recovery_dual_control', value='false'))
        db.session.commit()
    yield
    with app.app_context():
        SystemConfig.query.filter_by(key='key_recovery_dual_control').delete()
        db.session.commit()


def _post(client, url, body=None):
    return client.post(url, data=json.dumps(body or {}), content_type='application/json')


def _approved(auth_client, cert_id, client=None):
    r = _post(client or auth_client, f'/api/v2/certificates/{cert_id}/key-recovery', {'reason': 'lost laptop'})
    assert r.status_code == 201, r.data
    rid = r.get_json()['data']['id']
    assert _post(auth_client, f'/api/v2/key-recovery/{rid}/approve').status_code == 200
    return rid


def _status(app, rid):
    with app.app_context():
        db.session.expire_all()
        return db.session.get(KeyRecoveryRequest, rid).status


def _signed_in(app, username):
    client = app.test_client()
    assert _post(client, '/api/v2/auth/login', {'username': username, 'password': PASSWORD}).status_code == 200
    return client


def test_a_second_download_while_the_first_builds_gets_nothing(app, auth_client, create_cert, monkeypatch):
    rid = _approved(auth_client, create_cert(cn='claim-race.example.test')['id'])
    real, inner, other = key_recovery.pkcs12.serialize_key_and_certificates, [], _admin(app)

    def build_while_another_asks(**kw):
        if not inner:
            inner.append(None)  # the second download builds without asking again
            inner[0] = _post(other, f'/api/v2/key-recovery/{rid}/recover', PW)
        return real(**kw)
    monkeypatch.setattr(key_recovery.pkcs12, 'serialize_key_and_certificates', build_while_another_asks)
    first = _post(auth_client, f'/api/v2/key-recovery/{rid}/recover', PW)
    assert first.status_code == 200, first.data
    assert inner[0].status_code == 409, 'two downloads of one approval both received the key'
    assert _status(app, rid) == 'recovered'


def test_two_downloads_past_the_status_check_hand_the_key_out_once(app, auth_client, create_cert, monkeypatch):
    rid = _approved(auth_client, create_cert(cn='claim-both.example.test')['id'])
    real, inner, other = key_recovery._requested_certificate, [], _admin(app)

    def both_read_approved(req):
        # Both requests read "approved" before either claims: only the conditional UPDATE decides
        if not inner:
            inner.append(None)
            inner[0] = _post(other, f'/api/v2/key-recovery/{rid}/recover', PW)
        return real(req)
    monkeypatch.setattr(key_recovery, '_requested_certificate', both_read_approved)
    first = _post(auth_client, f'/api/v2/key-recovery/{rid}/recover', PW)
    assert sorted([first.status_code, inner[0].status_code]) == [200, 409], (first.data, inner[0].data)
    assert _status(app, rid) == 'recovered'


def _admin(app):
    client = app.test_client()
    assert _post(client, '/api/v2/auth/login', {'username': 'admin', 'password': 'changeme123'}).status_code == 200
    return client


def test_a_build_that_fails_gives_the_approval_back(app, auth_client, create_cert, monkeypatch):
    rid = _approved(auth_client, create_cert(cn='claim-undo.example.test')['id'])

    def broken(**kw):
        assert _status(app, rid) == 'recovered', 'the bundle is built before the request is claimed'
        raise ValueError('no bundle')
    monkeypatch.setattr(key_recovery.pkcs12, 'serialize_key_and_certificates', broken)
    assert _post(auth_client, f'/api/v2/key-recovery/{rid}/recover', PW).status_code == 500
    assert _status(app, rid) == 'approved'
    monkeypatch.undo()
    assert _post(auth_client, f'/api/v2/key-recovery/{rid}/recover', PW).status_code == 200


def test_an_account_reusing_a_deleted_requesters_name_cannot_collect(app, auth_client, create_user, create_cert):
    create_user(username='kr_reused', role='operator', email='kr-first@test.local')
    first = _signed_in(app, 'kr_reused')
    rid = _approved(auth_client, create_cert(cn='claim-reuse.example.test')['id'], client=first)
    with app.app_context():
        old_id = User.query.filter_by(username='kr_reused').one().id
    assert auth_client.delete(f'/api/v2/users/{old_id}').status_code in (200, 204)
    create_user(username='kr_reused', role='operator', email='kr-second@test.local')
    with app.app_context():
        assert User.query.filter_by(username='kr_reused').one().id != old_id
    r = _post(_signed_in(app, 'kr_reused'), f'/api/v2/key-recovery/{rid}/recover', PW)
    assert r.status_code == 403, r.data
    assert _status(app, rid) == 'approved'


def test_the_requester_collects_and_both_ids_are_kept(app, auth_client, create_user, create_cert):
    create_user(username='kr_owner', role='operator', email='kr-owner@test.local')
    owner = _signed_in(app, 'kr_owner')
    rid = _approved(auth_client, create_cert(cn='claim-owner.example.test')['id'], client=owner)
    assert _post(owner, f'/api/v2/key-recovery/{rid}/recover', PW).status_code == 200
    with app.app_context():
        row = db.session.get(KeyRecoveryRequest, rid)
        assert row.requested_by_id == User.query.filter_by(username='kr_owner').one().id
        assert row.decided_by_id == User.query.filter_by(username='admin').one().id


def test_dual_control_refuses_the_requesters_account_whatever_its_name(app, auth_client, create_cert):
    with app.app_context():
        SystemConfig.query.filter_by(key='key_recovery_dual_control').one().value = 'true'
        db.session.commit()
    r = _post(auth_client, f"/api/v2/certificates/{create_cert(cn='claim-dual.example.test')['id']}/key-recovery",
              {'reason': 'x'})
    rid = r.get_json()['data']['id']
    with app.app_context():
        db.session.get(KeyRecoveryRequest, rid).requested_by = 'a-name-since-changed'
        db.session.commit()
    assert _post(auth_client, f'/api/v2/key-recovery/{rid}/approve').status_code == 403
