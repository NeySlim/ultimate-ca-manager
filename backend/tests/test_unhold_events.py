"""Lifting a hold tells the bus, and takes the other member of a pair with it."""
import json

import pytest

from models import Certificate, RevokedSerial, db
from tests.deploy_leftovers import delete_leftovers
from services.events import event_bus

UNHELD = 'certificate.unheld'


def _post(client, url, payload=None):
    return client.post(url, data=json.dumps({} if payload is None else payload),
                       content_type='application/json')


# FK-aware purge: crl_metadata and other children go with their CA.
_cleanup = pytest.fixture(autouse=True)(delete_leftovers)


@pytest.fixture
def seen(monkeypatch):
    """Events emitted on the bus, with the stored state at the moment of emission."""
    events = []
    real = event_bus.emit

    def capture(event_type, payload, ca_refid=None, meta=None):
        row = None
        if event_type == UNHELD:
            db.session.expire_all()
            row = db.session.get(Certificate, payload['certificate']['id'])
        events.append((event_type, payload, meta, row.revoked if row else None))
        return real(event_type, payload, ca_refid, meta)

    monkeypatch.setattr(event_bus, 'emit', capture)
    return events


def _link(app, a_id, b_id):
    with app.app_context():
        a, b = db.session.get(Certificate, a_id), db.session.get(Certificate, b_id)
        a.related_certificate_id, b.related_certificate_id = b.id, a.id
        db.session.commit()


def _state(app, cert_id):
    with app.app_context():
        db.session.expire_all()
        c = db.session.get(Certificate, cert_id)
        return c.revoked, c.revoke_reason


def _unheld(events):
    return [e for e in events if e[0] == UNHELD]


def test_unhold_emits_one_event_after_the_commit(app, auth_client, create_ca, create_cert, seen):
    ca = create_ca(cn='Unhold Event CA')
    cert = create_cert(cn='unhold-event.example.test', ca_id=ca['id'])
    url = f"/api/v2/certificates/{cert['id']}"
    assert _post(auth_client, f'{url}/revoke', {'reason': 'certificateHold'}).status_code == 200
    assert _post(auth_client, f'{url}/unhold').status_code == 200
    events = _unheld(seen)
    assert len(events) == 1
    _, payload, meta, revoked_at_emit = events[0]
    assert payload['certificate']['id'] == cert['id']
    assert meta.get('actor')
    assert revoked_at_emit is False


def test_unhold_lifts_the_partner_hold_too(app, auth_client, create_ca, create_cert, seen):
    ca = create_ca(cn='Unhold Pair CA')
    a = create_cert(cn='unhold-pair-a.example.test', ca_id=ca['id'])
    b = create_cert(cn='unhold-pair-b.example.test', ca_id=ca['id'])
    _link(app, a['id'], b['id'])
    assert _post(auth_client, f"/api/v2/certificates/{a['id']}/revoke",
                 {'reason': 'certificateHold'}).status_code == 200
    assert _state(app, b['id']) == (True, 'certificateHold')
    r = _post(auth_client, f"/api/v2/certificates/{a['id']}/unhold")
    assert r.status_code == 200, r.data
    assert _state(app, a['id'])[0] is False and _state(app, b['id'])[0] is False
    with app.app_context():
        assert RevokedSerial.query.filter(
            RevokedSerial.certificate_id.in_([a['id'], b['id']])).count() == 0
    assert sorted(e[1]['certificate']['id'] for e in _unheld(seen)) == sorted([a['id'], b['id']])


def test_a_partner_revoked_for_cause_stays_revoked(app, auth_client, create_ca, create_cert, seen):
    ca = create_ca(cn='Unhold Cause CA')
    a = create_cert(cn='unhold-cause-a.example.test', ca_id=ca['id'])
    b = create_cert(cn='unhold-cause-b.example.test', ca_id=ca['id'])
    _link(app, a['id'], b['id'])
    base = '/api/v2/certificates'
    assert _post(auth_client, f"{base}/{a['id']}/revoke",
                 {'reason': 'certificateHold', 'revoke_related': False}).status_code == 200
    assert _post(auth_client, f"{base}/{b['id']}/revoke",
                 {'reason': 'keyCompromise', 'revoke_related': False}).status_code == 200
    assert _post(auth_client, f"{base}/{a['id']}/unhold").status_code == 200
    assert _state(app, b['id']) == (True, 'keyCompromise')
    assert [e[1]['certificate']['id'] for e in _unheld(seen)] == [a['id']]


def test_unhold_related_false_keeps_the_partner_on_hold(app, auth_client, create_ca, create_cert, seen):
    ca = create_ca(cn='Unhold Opt CA')
    a = create_cert(cn='unhold-opt-a.example.test', ca_id=ca['id'])
    b = create_cert(cn='unhold-opt-b.example.test', ca_id=ca['id'])
    _link(app, a['id'], b['id'])
    base = '/api/v2/certificates'
    for c in (a, b):
        assert _post(auth_client, f"{base}/{c['id']}/revoke",
                     {'reason': 'certificateHold', 'revoke_related': False}).status_code == 200
    r = _post(auth_client, f"{base}/{a['id']}/unhold", {'unhold_related': False})
    assert r.status_code == 200, r.data
    assert _state(app, a['id'])[0] is False
    assert _state(app, b['id']) == (True, 'certificateHold')
    assert 'related_unheld' not in r.get_json()['data']


def test_unhold_reports_the_partner_it_lifted(app, auth_client, create_ca, create_cert, seen):
    ca = create_ca(cn='Unhold Rep CA')
    a = create_cert(cn='unhold-rep-a.example.test', ca_id=ca['id'])
    b = create_cert(cn='unhold-rep-b.example.test', ca_id=ca['id'])
    _link(app, a['id'], b['id'])
    base = '/api/v2/certificates'
    assert _post(auth_client, f"{base}/{a['id']}/revoke",
                 {'reason': 'certificateHold'}).status_code == 200
    r = _post(auth_client, f"{base}/{a['id']}/unhold")
    assert r.get_json()['data']['related_unheld'] == b['id']


def _delta_on(app, *ca_ids):
    from models import CA
    with app.app_context():
        for ca_id in ca_ids:
            ca = db.session.get(CA, ca_id)
            ca.delta_crl_enabled = ca.cdp_enabled = True
        db.session.commit()


def _hold_pair(app, auth_client, a, b):
    _link(app, a['id'], b['id'])
    r = _post(auth_client, f"/api/v2/certificates/{a['id']}/revoke", {'reason': 'certificateHold'})
    assert r.status_code == 200, r.data


def test_a_pair_on_one_ca_gets_a_single_delta_listing_both(
        app, auth_client, create_ca, create_cert, monkeypatch):
    from services.crl_service import CRLService
    ca = create_ca(cn='Unhold Delta CA')
    a = create_cert(cn='unhold-delta-a.example.test', ca_id=ca['id'])
    b = create_cert(cn='unhold-delta-b.example.test', ca_id=ca['id'])
    _delta_on(app, ca['id'])
    _hold_pair(app, auth_client, a, b)
    seen_at_delta = []

    def delta(ca_id, username=None):
        seen_at_delta.append((ca_id, _state(app, a['id'])[1], _state(app, b['id'])[1]))

    monkeypatch.setattr(CRLService, 'generate_delta_crl', staticmethod(delta))
    r = _post(auth_client, f"/api/v2/certificates/{a['id']}/unhold")
    assert r.status_code == 200, r.data
    assert seen_at_delta == [(ca['id'], 'removeFromCRL', 'removeFromCRL')]
    assert _state(app, a['id'])[0] is False and _state(app, b['id'])[0] is False


def test_a_failed_delta_does_not_stop_the_partner(
        app, auth_client, create_ca, create_cert, monkeypatch):
    from services.crl_service import CRLService
    ca1 = create_ca(cn='Unhold Delta CA 1')
    ca2 = create_ca(cn='Unhold Delta CA 2')
    a = create_cert(cn='unhold-fail-a.example.test', ca_id=ca1['id'])
    b = create_cert(cn='unhold-fail-b.example.test', ca_id=ca2['id'])
    _delta_on(app, ca1['id'], ca2['id'])
    _hold_pair(app, auth_client, a, b)
    calls = []

    def delta(ca_id, username=None):
        calls.append(ca_id)
        if len(calls) == 1:
            raise RuntimeError('delta failed')

    monkeypatch.setattr(CRLService, 'generate_delta_crl', staticmethod(delta))
    r = _post(auth_client, f"/api/v2/certificates/{a['id']}/unhold")
    assert r.status_code == 200, r.data
    assert sorted(calls) == sorted([ca1['id'], ca2['id']])
    assert _state(app, a['id'])[0] is False and _state(app, b['id'])[0] is False


@pytest.mark.parametrize('body', [[], 'yes', 3])
def test_a_body_that_is_not_an_object_is_refused(app, auth_client, create_ca, create_cert, body):
    ca = create_ca(cn='Unhold Body CA')
    cert = create_cert(cn='unhold-body.example.test', ca_id=ca['id'])
    base = f"/api/v2/certificates/{cert['id']}"
    r = _post(auth_client, f'{base}/revoke', body)
    assert r.status_code == 400, r.data
    assert _post(auth_client, f'{base}/revoke', {'reason': 'certificateHold'}).status_code == 200
    r = _post(auth_client, f'{base}/unhold', body)
    assert r.status_code == 400, r.data


def test_a_null_body_is_refused_like_any_other_non_object(app, auth_client, create_ca, create_cert):
    ca = create_ca(cn='Unhold Null CA')
    cert = create_cert(cn='unhold-null.example.test', ca_id=ca['id'])
    base = f"/api/v2/certificates/{cert['id']}"
    r = auth_client.post(f'{base}/revoke', data='null', content_type='application/json')
    assert r.status_code == 400, r.data
    assert _state(app, cert['id'])[0] is False
    assert _post(auth_client, f'{base}/revoke', {'reason': 'certificateHold'}).status_code == 200
    r = auth_client.post(f'{base}/unhold', data='null', content_type='application/json')
    assert r.status_code == 400, r.data
    assert _state(app, cert['id']) == (True, 'certificateHold')


@pytest.mark.parametrize('data,content_type', [
    ('{"unhold_related": false', 'application/json'),
    ('unhold_related=false', 'application/x-www-form-urlencoded'),
])
def test_an_unreadable_body_is_refused_and_the_partner_stays_held(
        app, auth_client, create_ca, create_cert, data, content_type):
    ca = create_ca(cn='Unhold Strict CA')
    a = create_cert(cn='unhold-strict-a.example.test', ca_id=ca['id'])
    b = create_cert(cn='unhold-strict-b.example.test', ca_id=ca['id'])
    _hold_pair(app, auth_client, a, b)
    r = auth_client.post(f"/api/v2/certificates/{a['id']}/unhold", data=data,
                         content_type=content_type)
    assert r.status_code in (400, 415), r.data
    assert _state(app, a['id']) == (True, 'certificateHold')
    assert _state(app, b['id']) == (True, 'certificateHold')


def test_an_empty_body_lifts_the_pair(app, auth_client, create_ca, create_cert):
    ca = create_ca(cn='Unhold Empty CA')
    a = create_cert(cn='unhold-empty-a.example.test', ca_id=ca['id'])
    b = create_cert(cn='unhold-empty-b.example.test', ca_id=ca['id'])
    _hold_pair(app, auth_client, a, b)
    r = auth_client.post(f"/api/v2/certificates/{a['id']}/unhold")
    assert r.status_code == 200, r.data
    assert _state(app, a['id'])[0] is False and _state(app, b['id'])[0] is False


def _detail(auth_client, cert_id):
    r = auth_client.get(f'/api/v2/certificates/{cert_id}')
    assert r.status_code == 200, r.data
    return r.get_json()['data']


@pytest.mark.parametrize('case', ['lifted', 'archived', 'not_mutual', 'not_held'])
def test_the_detail_names_the_partner_an_unhold_would_lift(app, auth_client, create_ca, create_cert, case):
    tag = case.replace('_', '-')
    ca = create_ca(cn=f'Unhold Detail CA {tag}')
    a = create_cert(cn=f'unhold-detail-a-{tag}.example.test', ca_id=ca['id'])
    b = create_cert(cn=f'unhold-detail-b-{tag}.example.test', ca_id=ca['id'])
    _link(app, a['id'], b['id'])
    held = {'reason': 'certificateHold', 'revoke_related': case != 'not_held'}
    assert _post(auth_client, f"/api/v2/certificates/{a['id']}/revoke", held).status_code == 200
    with app.app_context():
        row = db.session.get(Certificate, b['id'])
        if case == 'archived':
            row.archived = True
        if case == 'not_mutual':
            row.related_certificate_id = None
        db.session.commit()
    expected = b['id'] if case == 'lifted' else None
    assert _detail(auth_client, a['id'])['related_on_hold_id'] == expected


def test_a_partner_held_by_its_record_alone_is_named_and_lifted(app, auth_client, create_ca, create_cert, seen):
    ca = create_ca(cn='Unhold Record Partner CA')
    a = create_cert(cn='unhold-record-a.example.test', ca_id=ca['id'])
    b = create_cert(cn='unhold-record-b.example.test', ca_id=ca['id'])
    _link(app, a['id'], b['id'])
    assert _post(auth_client, f"/api/v2/certificates/{a['id']}/revoke",
                 {'reason': 'certificateHold'}).status_code == 200
    with app.app_context():
        # The row not aligned yet: only the CA's record holds the partner
        row = db.session.get(Certificate, b['id'])
        row.revoked, row.revoke_reason, row.revoked_at = False, None, None
        db.session.commit()
    assert _detail(auth_client, a['id'])['related_on_hold_id'] == b['id']
    r = _post(auth_client, f"/api/v2/certificates/{a['id']}/unhold")
    assert r.status_code == 200, r.data
    assert r.get_json()['data']['related_unheld'] == b['id']
    with app.app_context():
        assert RevokedSerial.query.filter(
            RevokedSerial.certificate_id.in_([a['id'], b['id']])).count() == 0
    assert _state(app, b['id']) == (False, None)


def test_a_held_partner_its_record_revokes_for_good_refuses_the_pair(app, auth_client, create_ca, create_cert,
                                                                     seen):
    ca = create_ca(cn='Unhold Final Record Partner CA')
    a = create_cert(cn='unhold-final-record-a.example.test', ca_id=ca['id'])
    b = create_cert(cn='unhold-final-record-b.example.test', ca_id=ca['id'])
    _link(app, a['id'], b['id'])
    assert _post(auth_client, f"/api/v2/certificates/{a['id']}/revoke",
                 {'reason': 'certificateHold'}).status_code == 200
    with app.app_context():
        record = RevokedSerial.query.filter_by(certificate_id=b['id']).one()
        record.revoke_reason = 'keyCompromise'
        db.session.commit()
    r = _post(auth_client, f"/api/v2/certificates/{a['id']}/unhold")
    assert r.status_code == 409, r.data
    assert _state(app, a['id']) == (True, 'certificateHold')
    assert _unheld(seen) == []


def test_a_partner_left_in_remove_from_crl_is_lifted_with_the_pair(app, auth_client, create_ca, create_cert, seen):
    """Both members staged removeFromCRL, then the unhold stopped: lifting again completes both."""
    ca = create_ca(cn='Unhold Half Pair CA')
    a = create_cert(cn='unhold-half-a.example.test', ca_id=ca['id'])
    b = create_cert(cn='unhold-half-b.example.test', ca_id=ca['id'])
    _link(app, a['id'], b['id'])
    assert _post(auth_client, f"/api/v2/certificates/{a['id']}/revoke",
                 {'reason': 'certificateHold'}).status_code == 200
    with app.app_context():
        for cert_id in (a['id'], b['id']):
            db.session.get(Certificate, cert_id).revoke_reason = 'removeFromCRL'
        db.session.commit()
    r = _post(auth_client, f"/api/v2/certificates/{a['id']}/unhold")
    assert r.status_code == 200, r.data
    assert r.get_json()['data']['related_unheld'] == b['id']
    assert _state(app, a['id']) == (False, None) and _state(app, b['id']) == (False, None)


def test_a_partner_revoked_as_remove_from_crl_is_left_and_the_lift_goes_on(
        app, auth_client, create_ca, create_cert, seen):
    """A partner revoked with reason 8 (row and record, as ACME once wrote it) is no lift to finish."""
    ca = create_ca(cn='Unhold Reason Eight Partner CA')
    a = create_cert(cn='unhold-eight-a.example.test', ca_id=ca['id'])
    b = create_cert(cn='unhold-eight-b.example.test', ca_id=ca['id'])
    _link(app, a['id'], b['id'])
    assert _post(auth_client, f"/api/v2/certificates/{a['id']}/revoke",
                 {'reason': 'certificateHold'}).status_code == 200
    with app.app_context():
        db.session.get(Certificate, b['id']).revoke_reason = 'removeFromCRL'
        RevokedSerial.query.filter_by(certificate_id=b['id']).one().revoke_reason = 'removeFromCRL'
        db.session.commit()
    r = _post(auth_client, f"/api/v2/certificates/{a['id']}/unhold")
    assert r.status_code == 200, r.data
    assert 'related_unheld' not in r.get_json()['data']
    assert _state(app, a['id']) == (False, None) and _state(app, b['id']) == (True, 'removeFromCRL')
