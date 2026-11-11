"""Lifting a hold tells the bus, and takes the other member of a pair with it."""
import json

import pytest

from models import Certificate, RevokedSerial, db
from tests.deploy_leftovers import delete_leftovers
from services.events import event_bus

UNHELD = 'certificate.unheld'


def _post(client, url, payload=None):
    return client.post(url, data=json.dumps(payload or {}), content_type='application/json')


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
