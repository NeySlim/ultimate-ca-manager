"""Discovery scan notifications reach someone.

The digest looked for a `smtp_config` SystemConfig row that never exists
(SMTP lives in its own table) and returned in silence, and the profile's
"Notification Email" was dropped by the API for want of a column.
"""
import json
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from models import ScanProfile, db

SUMMARY = {'total_targets': 1, 'certs_found': 1, 'errors': 0}


def _profile(app, **extra):
    with app.app_context():
        row = ScanProfile(name=f'notify-{uuid.uuid4().hex[:8]}', targets='["example.test"]', **extra)
        db.session.add(row)
        db.session.commit()
        return row.id


def _sent_to(app, profile_id, smtp_from='ucm@example.test'):
    from services.discovery_service import DiscoveryService
    with app.app_context(), \
            patch('services.email_service.EmailService.get_smtp_config',
                  return_value=SimpleNamespace(smtp_from=smtp_from)), \
            patch('services.email_service.EmailService.send_email', return_value=(True, 'ok')) as send:
        DiscoveryService()._send_notifications(profile_id, SUMMARY, 1, 0, 0)
        db.session.delete(db.session.get(ScanProfile, profile_id))
        db.session.commit()
    return send.call_args.kwargs['recipients'] if send.called else None


def test_the_profile_address_receives_the_digest(app):
    assert _sent_to(app, _profile(app, notify_email='pki@example.test')) == ['pki@example.test']


def test_without_one_the_smtp_sender_does(app):
    assert _sent_to(app, _profile(app)) == ['ucm@example.test']


def test_the_api_keeps_and_checks_the_address(auth_client):
    body = {'name': f'notify-api-{uuid.uuid4().hex[:8]}', 'targets': ['example.test'],
            'notify_email': 'pki@example.test'}
    r = auth_client.post('/api/v2/discovery/profiles', data=json.dumps(body), content_type='application/json')
    assert r.status_code == 201, r.data
    pid = r.get_json()['data']['id']
    assert r.get_json()['data']['notify_email'] == 'pki@example.test'
    r = auth_client.put(f'/api/v2/discovery/profiles/{pid}', data=json.dumps({'notify_email': 'not an address'}),
                        content_type='application/json')
    assert r.status_code == 400
    r = auth_client.put(f'/api/v2/discovery/profiles/{pid}', data=json.dumps({'notify_email': ''}),
                        content_type='application/json')
    assert r.status_code == 200 and r.get_json()['data']['notify_email'] is None
    auth_client.delete(f'/api/v2/discovery/profiles/{pid}')
