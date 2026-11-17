"""Certificate expiry alerts: every selected threshold is stored (#323) and the
scheduled job reads the saved configuration and fires each threshold once per
validity period (#324)."""
import importlib
import json
import os
import sqlite3
from datetime import timedelta
from unittest.mock import MagicMock

import pytest

import services.email_service as email_service_module
from models import db, Certificate
from models.email_notification import NotificationConfig, NotificationLog
from services.email_service import EmailService
from services.notification_service import NotificationService
from utils.datetime_utils import utc_now


class _SmtpConfig:
    enabled = True
    smtp_host = 'smtp.example.com'
    smtp_port = 25
    smtp_use_ssl = False
    smtp_use_tls = False
    smtp_from = 'ucm@example.com'
    smtp_from_name = 'UCM'
    smtp_username = None
    smtp_user = None
    smtp_password = None
    smtp_content_type = 'html'
    smtp_auth_method = 'password'
    smtp_auth = False


@pytest.fixture
def smtp_spy(app, monkeypatch):
    monkeypatch.setattr(EmailService, 'get_smtp_config', staticmethod(lambda: _SmtpConfig()))
    server = MagicMock()
    factory = MagicMock(return_value=server)
    monkeypatch.setattr(email_service_module.smtplib, 'SMTP', factory)
    monkeypatch.setattr(email_service_module.smtplib, 'SMTP_SSL', factory)
    return server


@pytest.fixture
def expiry_config(app):
    """cert_expiring row with a 30/14/7/1 selection and one recipient; restored after."""
    with app.app_context():
        config = NotificationConfig.query.filter_by(type='cert_expiring').first()
        snapshot = None
        if config:
            snapshot = (config.enabled, config.days_before, config.alert_days,
                        config.include_revoked, config.exclude_acme, config.recipients)
        else:
            config = NotificationConfig(type='cert_expiring')
            db.session.add(config)
        config.enabled = True
        config.set_alert_days([30, 14, 7, 1])
        config.include_revoked = False
        config.exclude_acme = False
        config.recipients = json.dumps(['ops@example.com'])
        db.session.commit()
        config_id = config.id
    yield config_id
    with app.app_context():
        config = db.session.get(NotificationConfig, config_id)
        if snapshot:
            (config.enabled, config.days_before, config.alert_days,
             config.include_revoked, config.exclude_acme, config.recipients) = snapshot
            db.session.commit()
        else:
            db.session.delete(config)
            db.session.commit()


def _thresholds_sent(app, refid):
    with app.app_context():
        rows = NotificationLog.query.filter_by(
            type='cert_expiring', resource_type='certificate', resource_id=refid, status='sent'
        ).order_by(NotificationLog.id).all()
        return [r.threshold_days for r in rows]


def _set_validity(app, cert_id, *, days_left, valid_from=None):
    with app.app_context():
        cert = db.session.get(Certificate, cert_id)
        now = utc_now()
        cert.valid_to = now + timedelta(days=days_left)
        cert.valid_from = valid_from if valid_from is not None else now - timedelta(days=100)
        db.session.commit()
        return cert.refid


def _run(app):
    with app.app_context():
        return NotificationService.run_scheduled_checks()


class TestThresholdEscalation:
    def test_each_threshold_fires_once_per_validity_period(self, app, create_cert, expiry_config, smtp_spy):
        cert = create_cert(cn='expiry-thresholds.example.com')
        refid = _set_validity(app, cert['id'], days_left=20)

        _run(app)
        assert _thresholds_sent(app, refid) == [30]
        _run(app)
        assert _thresholds_sent(app, refid) == [30], 'no daily repeat inside the same window'

        _set_validity(app, cert['id'], days_left=10)
        _run(app)
        assert _thresholds_sent(app, refid) == [30, 14]

        _set_validity(app, cert['id'], days_left=5)
        _run(app)
        assert _thresholds_sent(app, refid) == [30, 14, 7]

        with app.app_context():
            c = db.session.get(Certificate, cert['id'])
            c.valid_to = utc_now() + timedelta(hours=12)
            db.session.commit()
        _run(app)
        assert _thresholds_sent(app, refid) == [30, 14, 7, 1]
        _run(app)
        assert _thresholds_sent(app, refid) == [30, 14, 7, 1]

    def test_renewal_starts_a_new_alert_cycle(self, app, create_cert, expiry_config, smtp_spy):
        cert = create_cert(cn='expiry-renewed.example.com')
        refid = _set_validity(app, cert['id'], days_left=20)
        _run(app)
        assert _thresholds_sent(app, refid) == [30]

        # Renewed: new validity period starting after the alert went out
        _set_validity(app, cert['id'], days_left=20, valid_from=utc_now() + timedelta(seconds=2))
        _run(app)
        assert _thresholds_sent(app, refid) == [30, 30]

    def test_revoked_certificates_follow_the_toggle(self, app, create_cert, expiry_config, smtp_spy):
        cert = create_cert(cn='expiry-revoked.example.com')
        refid = _set_validity(app, cert['id'], days_left=10)
        with app.app_context():
            c = db.session.get(Certificate, cert['id'])
            c.revoked = True
            db.session.commit()

        _run(app)
        assert _thresholds_sent(app, refid) == []

        with app.app_context():
            db.session.get(NotificationConfig, expiry_config).include_revoked = True
            db.session.commit()
        _run(app)
        assert _thresholds_sent(app, refid) == [14]

    def test_acme_certificates_follow_the_toggle(self, app, create_cert, expiry_config, smtp_spy):
        """#386: ACME clients renew their own certificates."""
        refids = {}
        for source in ('acme', 'manual', None):
            cert = create_cert(cn=f'expiry-source-{source}.example.com')
            refids[source] = _set_validity(app, cert['id'], days_left=10)
            with app.app_context():
                db.session.get(Certificate, cert['id']).source = source
                db.session.commit()

        with app.app_context():
            db.session.get(NotificationConfig, expiry_config).exclude_acme = True
            db.session.commit()
        _run(app)
        assert _thresholds_sent(app, refids['acme']) == []
        assert _thresholds_sent(app, refids['manual']) == [14]
        assert _thresholds_sent(app, refids[None]) == [14]

        with app.app_context():
            db.session.get(NotificationConfig, expiry_config).exclude_acme = False
            db.session.commit()
        _run(app)
        assert _thresholds_sent(app, refids['acme']) == [14]

    def test_disabled_or_without_recipients_sends_nothing(self, app, create_cert, expiry_config, smtp_spy):
        cert = create_cert(cn='expiry-disabled.example.com')
        refid = _set_validity(app, cert['id'], days_left=3)

        with app.app_context():
            db.session.get(NotificationConfig, expiry_config).enabled = False
            db.session.commit()
        _run(app)
        assert _thresholds_sent(app, refid) == []

        with app.app_context():
            config = db.session.get(NotificationConfig, expiry_config)
            config.enabled = True
            config.recipients = '[]'
            db.session.commit()
        _run(app)
        assert _thresholds_sent(app, refid) == []

    def test_configured_recipients_are_used(self, app, create_cert, expiry_config, smtp_spy):
        cert = create_cert(cn='expiry-recipients.example.com')
        _set_validity(app, cert['id'], days_left=2)
        _run(app)
        sent_to = [call.args[1] for call in smtp_spy.sendmail.call_args_list]
        assert any('ops@example.com' in rcpts for rcpts in sent_to)
        assert all('ucm@example.com' not in rcpts for rcpts in sent_to), \
            'the From address is not appended as a recipient'


class TestThresholdRounding:
    def test_threshold_fires_only_once_whole_days_remain(self, app, create_cert, expiry_config, smtp_spy):
        """14 days and 23 hours left is still 15 days away: the 14-day threshold
        must not fire almost a day early."""
        with app.app_context():
            config = db.session.get(NotificationConfig, expiry_config)
            config.set_alert_days([14])
            db.session.commit()
        cert = create_cert(cn='expiry-rounding.example.com')
        with app.app_context():
            c = db.session.get(Certificate, cert['id'])
            c.valid_from = utc_now() - timedelta(days=100)
            c.valid_to = utc_now() + timedelta(days=14, hours=23)
            db.session.commit()
            refid = c.refid
        _run(app)
        assert _thresholds_sent(app, refid) == []

        with app.app_context():
            c = db.session.get(Certificate, cert['id'])
            c.valid_to = utc_now() + timedelta(days=13, hours=23)
            db.session.commit()
        _run(app)
        assert _thresholds_sent(app, refid) == [14]


class TestGenericNotificationsEndpointStaysInSync:
    def test_threshold_days_replaces_the_alert_days_list(self, app, auth_client, expiry_config):
        r = auth_client.patch('/api/v2/settings/notifications',
                              data=json.dumps({'notification_type': 'cert_expiring', 'threshold_days': 21}),
                              content_type='application/json')
        assert r.status_code == 200, r.data
        r = auth_client.get('/api/v2/system/alerts/expiry')
        assert r.get_json()['data']['alert_days'] == [21]
        r = auth_client.get('/api/v2/settings/notifications')
        row = next(c for c in r.get_json()['data']['configs'] if c['notification_type'] == 'cert_expiring')
        assert row['threshold_days'] == 21 and row['alert_days'] == [21]

    def test_threshold_days_is_validated(self, auth_client, expiry_config):
        for bad in ('x', 0, -3, True, 4000, 999999999, 7.5):
            r = auth_client.patch('/api/v2/settings/notifications',
                                  data=json.dumps({'notification_type': 'cert_expiring', 'threshold_days': bad}),
                                  content_type='application/json')
            assert r.status_code == 400, bad

    def test_cooldown_hours_is_validated(self, auth_client, expiry_config):
        for bad in ('x', True, -1, 100000):
            r = auth_client.patch('/api/v2/settings/notifications',
                                  data=json.dumps({'notification_type': 'cert_expiring', 'cooldown_hours': bad}),
                                  content_type='application/json')
            assert r.status_code == 400, bad


class TestModelIgnoresOutOfRangeThresholds:
    def test_restored_extreme_values_never_reach_the_scheduler(self, app, expiry_config):
        with app.app_context():
            config = db.session.get(NotificationConfig, expiry_config)
            config.alert_days = json.dumps([999999999, 14, 0, -1])
            assert config.get_alert_days() == [14]
            config.alert_days = json.dumps([999999999])
            config.days_before = 999999999
            assert config.get_alert_days() == list(NotificationConfig.DEFAULT_ALERT_DAYS)
            with pytest.raises(ValueError):
                config.set_alert_days([999999999])
            db.session.rollback()


def test_exclude_acme_is_saved_and_validated(app, auth_client, expiry_config):
    url = '/api/v2/system/alerts/expiry'
    r = auth_client.put(url, json={'exclude_acme': 'yes'})
    assert r.status_code == 400
    r = auth_client.put(url, json={'exclude_acme': True})
    assert r.status_code == 200, r.get_json()
    assert auth_client.get(url).get_json()['data']['exclude_acme'] is True
    with app.app_context():
        assert db.session.get(NotificationConfig, expiry_config).exclude_acme is True
