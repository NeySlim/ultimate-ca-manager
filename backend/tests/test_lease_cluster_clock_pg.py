"""In HA, a lease or a reservation is written and compared on the cluster clock: a node whose
own clock runs ahead of the others by more than the lease neither takes over a live lease nor
does the work again, and one running behind still sees a lease expire at the database's hour.

Each test binds the application to a schema of its own and skews this host's clock only.
"""
import os
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import text

from models import AcmeClientOrder, ScanProfile, SystemConfig, db
from models.deploy import DeployDelivery
from models.email_notification import NotificationLog
from models.webhook_delivery import WebhookDelivery
from services import policy_notifications
from services.acme import order_housekeeping, order_lease
from services.acme.order_lease import LEASE_DURATION, OrderLease
from services.backup import schedule
from services.deploy.service import DeployService
from services.discovery import DiscoveryService
from services.discovery_scheduler_task import DiscoverySchedulerTask
from services.webhook_service import WebhookEndpoint, WebhookService
from tests.test_scheduled_claims_pg import _pg
from tests.test_scheduled_run_reservations_pg import _backup_schedule
from utils import datetime_utils
from utils.datetime_utils import utc_isoformat

_PG_URL = os.environ.get('UCM_TEST_PG_URL')
pytestmark = [pytest.mark.postgres, pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')]

# Every module that read this host's clock for a lease or a reservation
_LOCAL_CLOCK_READERS = (order_lease, order_housekeeping, schedule, DeployService.__module__,
                        WebhookService.__module__, DiscoverySchedulerTask.__module__, datetime_utils)


def _db_now():
    return db.session.execute(text("SELECT clock_timestamp() AT TIME ZONE 'UTC'")).scalar()


@pytest.fixture
def cluster(app, monkeypatch):
    """HA on a PostgreSQL schema of this test's own; returns a function skewing this host's clock."""
    import importlib
    monkeypatch.setattr('utils.ha.ha_enabled', lambda: True)
    real = datetime_utils.utc_now

    def skew(offset):
        for module in _LOCAL_CLOCK_READERS:
            module = importlib.import_module(module) if isinstance(module, str) else module
            monkeypatch.setattr(module, 'utc_now', lambda: real() + offset, raising=False)
    with _pg(app), app.app_context():
        yield skew
        db.session.remove()


def _close(a, b, seconds=60):
    return abs((a - b).total_seconds()) < seconds


# ------------------------------------------------------------------ ACME order lease

def _order(**fields):
    order = AcmeClientOrder(domains='["clock.example"]', **fields)
    db.session.add(order)
    db.session.commit()
    return order.id


def _claimed_at(order_id):
    db.session.expire_all()
    return db.session.get(AcmeClientOrder, order_id).renewal_claimed_at


def test_a_node_ahead_does_not_take_a_live_acme_lease(cluster):
    order_id = _order(renewal_claimed_at=_db_now())
    cluster(LEASE_DURATION + timedelta(minutes=5))
    assert OrderLease.take(order_id) is None


def test_an_acme_lease_expires_and_restarts_on_the_database_clock(cluster):
    order_id = _order(renewal_claimed_at=_db_now() - LEASE_DURATION - timedelta(seconds=30))
    cluster(-timedelta(hours=1))
    lease = OrderLease.take(order_id)
    assert lease is not None
    assert _close(_claimed_at(order_id), _db_now())
    assert lease.refresh() is True
    assert _close(_claimed_at(order_id), _db_now())


def test_the_restart_recovery_leaves_an_order_leased_elsewhere(cluster):
    now = _db_now()
    order_id = _order(status='processing', renewal_claimed_at=now)
    AcmeClientOrder.query.filter_by(id=order_id).update({'updated_at': now - timedelta(minutes=20)})
    db.session.commit()
    cluster(LEASE_DURATION + timedelta(minutes=5))
    order_housekeeping.recover_interrupted_orders()
    db.session.expire_all()
    assert db.session.get(AcmeClientOrder, order_id).status == 'processing'


def test_the_purge_leaves_a_stale_order_leased_elsewhere(cluster):
    now = _db_now()
    order_id = _order(status='pending', renewal_claimed_at=now)
    AcmeClientOrder.query.filter_by(id=order_id).update({'created_at': now - timedelta(days=8)})
    db.session.commit()
    cluster(LEASE_DURATION + timedelta(minutes=5))
    order_housekeeping.purge_stale_pending_orders()
    db.session.expire_all()
    assert db.session.get(AcmeClientOrder, order_id) is not None


# ------------------------------------------------------------------ scheduled backup

def _reservation_elsewhere(app, monkeypatch, tmp_path, taken_at):
    exported = _backup_schedule(app, monkeypatch, tmp_path)
    for key, value in (('backup.last_run', utc_isoformat(taken_at)),
                       ('backup.concluded_run', '2026-01-01T00:00:00Z')):
        SystemConfig.query.filter_by(key=key).delete()
        db.session.add(SystemConfig(key=key, value=value))
    db.session.commit()
    return exported


def test_a_node_ahead_does_not_run_a_backup_reserved_elsewhere(cluster, app, monkeypatch, tmp_path):
    exported = _reservation_elsewhere(app, monkeypatch, tmp_path, _db_now())
    cluster(timedelta(seconds=schedule._CLAIM_LEASE_SECONDS + 300))
    assert schedule.run_scheduled_backup() == {'status': 'skipped', 'reason': 'not_due'}
    assert schedule.get_schedule()['in_progress'] is True
    assert exported == []


def test_an_abandoned_backup_reservation_expires_on_the_database_clock(cluster, app, monkeypatch, tmp_path):
    lease = timedelta(seconds=schedule._CLAIM_LEASE_SECONDS)
    exported = _reservation_elsewhere(app, monkeypatch, tmp_path, _db_now() - lease - timedelta(minutes=1))
    cluster(-timedelta(hours=3))
    assert schedule.run_scheduled_backup()['status'] == 'ok'
    assert len(exported) == 1
    assert _close(schedule._parse(schedule._get('backup.last_run')), _db_now())


# ------------------------------------------------------------------ webhook and deploy deliveries

def _webhook(next_attempt_at, monkeypatch):
    sent = []
    monkeypatch.setattr(WebhookService, '_perform_delivery',
                        staticmethod(lambda endpoint, event, body: sent.append(event) or (True, 200, None)))
    endpoint = WebhookEndpoint(name=f'clock-{uuid.uuid4().hex[:6]}', url='https://hook.invalid/x')
    db.session.add(endpoint)
    db.session.flush()
    delivery = WebhookDelivery(endpoint_id=endpoint.id, event_type='certificate.issued', payload='{}',
                               event_timestamp='2026-11-15T00:00:00Z', next_attempt_at=next_attempt_at)
    db.session.add(delivery)
    db.session.commit()
    return delivery.id, sent


def test_a_node_ahead_does_not_send_a_webhook_claimed_elsewhere(cluster, monkeypatch):
    _id, sent = _webhook(_db_now() + timedelta(seconds=WebhookService._CLAIM_LEASE_SECONDS), monkeypatch)
    cluster(timedelta(minutes=5))
    WebhookService.process_pending_deliveries()
    assert sent == []


def test_a_webhook_claim_expires_on_the_database_clock(cluster, monkeypatch):
    delivery_id, sent = _webhook(_db_now() - timedelta(seconds=1), monkeypatch)
    cluster(-timedelta(hours=1))
    WebhookService.process_pending_deliveries()
    assert sent == ['certificate.issued']
    db.session.expire_all()
    assert _close(db.session.get(WebhookDelivery, delivery_id).delivered_at, _db_now())


def test_a_webhook_is_queued_due_on_the_database_clock(cluster):
    endpoint = WebhookEndpoint(name=f'clock-{uuid.uuid4().hex[:6]}', url='https://hook.invalid/x',
                               events='["certificate.issued"]')
    db.session.add(endpoint)
    db.session.commit()
    cluster(timedelta(hours=1))
    WebhookService.enqueue_deliveries('certificate.issued', {'serial': '01'})
    queued = WebhookDelivery.query.filter_by(endpoint_id=endpoint.id).one()
    assert _close(queued.next_attempt_at, _db_now())


def _deploy(next_attempt_at, monkeypatch):
    run = []
    monkeypatch.setattr(DeployService, 'execute_delivery', staticmethod(lambda d: run.append(d.id) or True))
    delivery = DeployDelivery(binding_id=1, event_type='certificate.renewed', next_attempt_at=next_attempt_at)
    db.session.add(delivery)
    db.session.commit()
    return delivery.id, run


def test_a_node_ahead_does_not_run_a_deployment_claimed_elsewhere(cluster, monkeypatch):
    _id, run = _deploy(_db_now() + timedelta(seconds=DeployService._CLAIM_LEASE_SECONDS), monkeypatch)
    cluster(timedelta(minutes=5))
    DeployService.process_pending_deliveries()
    assert run == []


def test_a_deployment_claim_is_written_on_the_database_clock(cluster, monkeypatch):
    delivery_id, run = _deploy(_db_now() - timedelta(seconds=1), monkeypatch)
    cluster(-timedelta(hours=1))
    DeployService.process_pending_deliveries()
    assert run == [delivery_id]
    db.session.expire_all()
    lease_end = _db_now() + timedelta(seconds=DeployService._CLAIM_LEASE_SECONDS)
    assert _close(db.session.get(DeployDelivery, delivery_id).next_attempt_at, lease_end)


# ------------------------------------------------------------------ policy notification window

def test_a_node_ahead_does_not_notify_again_within_the_window(cluster):
    resource_id = f'clock-{uuid.uuid4().hex[:8]}'
    db.session.add(NotificationLog(type='policy_violation', recipient='a@x.invalid', status='sent',
                                   resource_type='policy', resource_id=resource_id, sent_at=_db_now()))
    db.session.commit()
    cluster(policy_notifications.DEDUP_WINDOW + timedelta(minutes=5))
    assert policy_notifications._claim_in_db('policy_violation', resource_id, 'a@x.invalid') is None


def test_a_notification_sent_by_a_node_behind_still_closes_the_window(cluster):
    resource_id = f'clock-{uuid.uuid4().hex[:8]}'
    cluster(-policy_notifications.DEDUP_WINDOW - timedelta(minutes=5))
    assert policy_notifications._claim_in_db('policy_violation', resource_id, 'a@x.invalid') is not None
    cluster(timedelta(0))
    assert policy_notifications._claim_in_db('policy_violation', resource_id, 'a@x.invalid') is None


def test_a_node_behind_notifies_once_through_the_real_mail_log(cluster, monkeypatch):
    import json as _json
    from models.email_notification import SMTPConfig
    from models.policy import CertificatePolicy
    from services import email_service

    class FakeServer:
        def sendmail(self, *a):
            pass

        def quit(self):
            pass
    monkeypatch.setattr(email_service, '_smtp_connect', lambda cfg, timeout: FakeServer())
    monkeypatch.setattr(email_service, '_smtp_authenticate', lambda server, cfg: None)
    db.session.add(SMTPConfig(enabled=True, smtp_host='smtp.example.test', smtp_port=25,
                              smtp_from='ucm@example.test', smtp_auth=False, smtp_use_tls=False))
    policy = CertificatePolicy(name=f'clock-{uuid.uuid4().hex[:8]}', rules='{}',
                               notification_emails=_json.dumps(['ops@example.test']))
    db.session.add(policy)
    db.session.commit()
    policy_id, resource_id = policy.id, f'clock-{uuid.uuid4().hex[:8]}'
    # The per-recipient 'sent' rows keep the window closed once the claim is gone
    cluster(-2 * policy_notifications.DEDUP_WINDOW)
    monkeypatch.setattr(email_service, 'utc_now', lambda: datetime_utils.utc_now(), raising=False)
    for _ in range(2):
        assert policy_notifications._send(policy_id, policy_notifications.VIOLATION, resource_id,
                                          {'operation': 'issue'}, own_session=True)
    sent = NotificationLog.query.filter_by(resource_type='policy', resource_id=resource_id,
                                           status='sent').all()
    assert len(sent) == 1, f'notified {len(sent)} times within the window'
    assert _close(sent[0].sent_at, _db_now())


# ------------------------------------------------------------------ discovery schedule

def test_a_node_ahead_does_not_scan_a_profile_claimed_elsewhere(cluster, monkeypatch):
    started = []
    monkeypatch.setattr(DiscoveryService, 'start_scan', lambda self, **kw: started.append(kw) or 1)
    profile = ScanProfile(name=f'clock-{uuid.uuid4().hex[:6]}', targets='["192.0.2.10"]', ports='[443]',
                          schedule_enabled=True, schedule_interval_minutes=60,
                          next_scan_at=_db_now() + timedelta(minutes=60))
    db.session.add(profile)
    db.session.commit()
    cluster(timedelta(minutes=65))
    DiscoverySchedulerTask.execute()
    assert started == []


# ------------------------------------------------------------------ event notification cooldown

_EVENT_COOLDOWN = timedelta(hours=1)


@pytest.fixture
def event_mail(cluster, monkeypatch):
    """Event alerts with a one-hour cooldown, a fake SMTP server, and every mail-log clock skewed."""
    import json as _json
    from models.email_notification import NotificationConfig, SMTPConfig
    from models import email_notification
    from services import email_service
    from services.notification import NotificationService
    from services.notification.templates import NotificationTemplatesMixin
    from services.notification._constants import (
        CA_CREATED, CERT_ISSUED, CERT_REVOKED, CRL_EXPIRING, SECURITY_ALERT)

    class FakeServer:
        def sendmail(self, *a):
            pass

        def quit(self):
            pass
    monkeypatch.setattr(email_service, '_smtp_connect', lambda cfg, timeout: FakeServer())
    monkeypatch.setattr(email_service, '_smtp_authenticate', lambda server, cfg: None)
    db.session.add(SMTPConfig(enabled=True, smtp_host='smtp.example.test', smtp_port=25,
                              smtp_from='ucm@example.test', smtp_auth=False, smtp_use_tls=False))
    for kind in (CA_CREATED, CERT_ISSUED, CERT_REVOKED, CRL_EXPIRING, SECURITY_ALERT):
        config = NotificationConfig.query.filter_by(type=kind).first() or NotificationConfig(type=kind)
        config.enabled, config.cooldown_hours = True, int(_EVENT_COOLDOWN.total_seconds() // 3600)
        config.recipients = _json.dumps(['ops@example.test'])
        db.session.add(config)
    db.session.commit()
    for name in ('_render_cert_issued_template', '_render_cert_revoked_template',
                 '_render_ca_created_template', '_render_security_alert_template'):
        monkeypatch.setattr(NotificationTemplatesMixin, name, staticmethod(lambda *a, **k: '<p>x</p>'))
    real = datetime_utils.utc_now

    def skew(offset):
        cluster(offset)
        for module in (email_notification, email_service):
            monkeypatch.setattr(module, 'utc_now', lambda: real() + offset)
    return NotificationService, skew


def _event_sent(resource_type, resource_id):
    db.session.expire_all()
    return NotificationLog.query.filter_by(resource_type=resource_type, resource_id=resource_id,
                                           status='sent').all()


def _event_logged(kind, resource_type, resource_id, sent_at):
    db.session.add(NotificationLog(type=kind, recipient='ops@example.test', status='sent',
                                   resource_type=resource_type, resource_id=resource_id,
                                   sent_at=sent_at))
    db.session.commit()


def test_a_node_ahead_does_not_resend_an_event_alert_within_its_cooldown(event_mail):
    service, skew = event_mail
    resource_id = f'clock-{uuid.uuid4().hex[:8]}'
    _event_logged('cert_revoked', 'certificate', resource_id, _db_now())
    skew(2 * _EVENT_COOLDOWN)
    assert service.should_send('cert_revoked', 'certificate', resource_id) is False


def test_an_event_alert_cooldown_ends_at_the_database_hour_on_a_node_behind(event_mail):
    service, skew = event_mail
    resource_id = f'clock-{uuid.uuid4().hex[:8]}'
    _event_logged('cert_revoked', 'certificate', resource_id, _db_now() - 2 * _EVENT_COOLDOWN)
    skew(-2 * _EVENT_COOLDOWN)
    assert service.should_send('cert_revoked', 'certificate', resource_id) is True


def test_a_node_two_hours_behind_does_not_send_a_security_alert_twice(event_mail):
    service, skew = event_mail
    username = f'clock-{uuid.uuid4().hex[:8]}'
    skew(-timedelta(hours=2))
    assert service.on_security_alert('login_failed', username)[0] is True
    skew(timedelta(0))
    assert service.on_security_alert('login_failed', username) == (
        True, 'Notification skipped (disabled or cooldown)')
    sent = _event_sent('security', f'login_failed:{username}')
    assert len(sent) == 1 and _close(sent[0].sent_at, _db_now())


@pytest.mark.parametrize('event', ['cert_issued', 'cert_revoked', 'ca_created', 'crl_expiring'])
def test_every_event_alert_is_logged_on_the_database_clock(event_mail, event):
    from types import SimpleNamespace
    service, skew = event_mail
    refid = f'clock-{uuid.uuid4().hex[:8]}'
    obj = SimpleNamespace(refid=refid, descr='d', subject='CN=clock', id=refid, ca_id=-1,
                          next_update=_db_now() + timedelta(days=1))
    send, resource_type = {
        'cert_issued': (lambda: service.on_certificate_issued(obj), 'certificate'),
        'cert_revoked': (lambda: service.on_certificate_revoked(obj), 'certificate'),
        'ca_created': (lambda: service.on_ca_created(obj), 'ca'),
        'crl_expiring': (lambda: service.send_crl_expiring_notification(
            obj, 1, ['ops@example.test']), 'crl'),
    }[event]
    skew(-timedelta(hours=2))
    assert send()[0] is True
    sent = _event_sent(resource_type, refid)
    assert len(sent) == 1 and _close(sent[0].sent_at, _db_now())


def test_a_failing_cluster_clock_leaves_the_mail_senders_transaction(event_mail, monkeypatch):
    """The cluster clock of the mail log reads on a connection of its own: a failed read there
    never aborts the transaction the sender still holds on PostgreSQL."""
    from services import email_service, scheduler_leader
    service, skew = event_mail
    key, resource_id = f'test.clock.{uuid.uuid4().hex[:8]}', f'clock-{uuid.uuid4().hex[:8]}'
    monkeypatch.setattr(scheduler_leader, '_SERVER_NOW_SQL', text('SELECT 1/0'))
    db.session.add(SystemConfig(key=key, value='kept'))
    db.session.flush()
    ok, _ = email_service.EmailService.send_email(
        recipients=['ops@example.test'], subject='s', body_html='<p>x</p>', resource_type='clock',
        resource_id=resource_id, log_clock=scheduler_leader.cluster_utc_now)
    assert ok is True
    db.session.expire_all()
    assert SystemConfig.query.filter_by(key=key).one().value == 'kept'
    assert len(_event_sent('clock', resource_id)) == 1
