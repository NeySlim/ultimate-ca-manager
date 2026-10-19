"""Discovery scan notifications reach someone.

The digest looked for a `smtp_config` SystemConfig row that never exists
(SMTP lives in its own table) and returned in silence, and the profile's
"Notification Email" was dropped by the API for want of a column.
"""
import json
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from datetime import datetime, timedelta, timezone

from models import DiscoveredCertificate, ScanProfile, db

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
        DiscoveryService()._send_notifications(profile_id, SUMMARY, 1, 0)
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


def _scan_alerts(app, profile_id, rows, sent=True):
    """Run the end-of-scan expiry selection and digest, as the scanner does; returns the subjects mailed."""
    from services.discovery_service import DiscoveryService
    with app.app_context(), \
            patch('services.email_service.EmailService.get_smtp_config',
                  return_value=SimpleNamespace(smtp_from='ucm@example.test')), \
            patch('services.email_service.EmailService.send_email', return_value=(sent, 'ok')) as send:
        _total, newly = DiscoveryService._expiring_in_window(profile_id)
        DiscoveryService()._send_notifications(profile_id, SUMMARY, 0, 0, newly)
        return [c.kwargs['subject'] for c in send.call_args_list]


def test_an_expiring_certificate_is_reported_once(app):
    pid = _profile(app, notify_on_new=False, notify_on_change=False)
    with app.app_context():
        row = DiscoveredCertificate(scan_profile_id=pid, target='a.example.test', fingerprint_sha256='f' * 64,
                                    not_after=datetime.now(timezone.utc) + timedelta(days=5))
        db.session.add(row)
        db.session.commit()
    try:
        assert len(_scan_alerts(app, pid, None)) == 1
        assert _scan_alerts(app, pid, None) == []
        # A new certificate entering the window is reported, the old one is not again
        with app.app_context():
            db.session.add(DiscoveredCertificate(
                scan_profile_id=pid, target='b.example.test', fingerprint_sha256='e' * 64,
                not_after=datetime.now(timezone.utc) - timedelta(days=1)))
            db.session.commit()
        subjects = _scan_alerts(app, pid, None)
        assert len(subjects) == 1 and '1 certificate(s) newly expiring' in subjects[0]
        # A renewed certificate on the same target is a new fingerprint
        with app.app_context():
            renewed = DiscoveredCertificate.query.filter_by(scan_profile_id=pid, target='a.example.test').one()
            renewed.fingerprint_sha256 = 'd' * 64
            db.session.commit()
        assert len(_scan_alerts(app, pid, None)) == 1
    finally:
        with app.app_context():
            DiscoveredCertificate.query.filter_by(scan_profile_id=pid).delete()
            db.session.delete(db.session.get(ScanProfile, pid))
            db.session.commit()


def test_an_alert_that_failed_to_send_is_retried(app):
    pid = _profile(app, notify_on_new=False, notify_on_change=False)
    with app.app_context():
        db.session.add(DiscoveredCertificate(scan_profile_id=pid, target='c.example.test', fingerprint_sha256='c' * 64,
                                             not_after=datetime.now(timezone.utc) + timedelta(days=5)))
        db.session.commit()
    try:
        assert len(_scan_alerts(app, pid, None, sent=False)) == 1
        assert len(_scan_alerts(app, pid, None)) == 1
    finally:
        with app.app_context():
            DiscoveredCertificate.query.filter_by(scan_profile_id=pid).delete()
            db.session.delete(db.session.get(ScanProfile, pid))
            db.session.commit()
