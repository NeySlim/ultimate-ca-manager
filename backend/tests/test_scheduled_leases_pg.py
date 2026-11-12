"""In HA, a scheduled pass that sends outside acts once per due date, even when two nodes
believe they lead: expiry e-mails and webhooks, the scheduled CRL, the Microsoft CA CRL sync.

The pass holds a lease on a ``system_config`` row taken by compare-and-set; a node that
dies holding it frees it once the lease is over. Outside HA nothing is reserved.
"""
import base64
import os
import uuid
from datetime import timedelta

import pytest

from models import SystemConfig, db
from models.email_notification import NotificationLog
from services import expiry_alert_service
from services.crl_scheduler_task import CRLSchedulerTask
from services.notification import scheduler as notification_scheduler
from services.notification.sender import NotificationSenderMixin
from services.notification_service import NotificationService
from tests.test_crl_number_monotonic import _authority, _ca_row
from tests.test_expiry_alert_thresholds import (  # noqa: F401  (fixtures)
    _set_validity, expiry_config, smtp_spy)
from tests.test_scheduled_claims_pg import _pg, _twice_at_once
from utils import config_cas
from utils.datetime_utils import utc_now

_PG_URL = os.environ.get('UCM_TEST_PG_URL')
_on_pg = [pytest.mark.postgres, pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')]

_EXPIRY_KEYS = (notification_scheduler.EXPIRY_LEASE_KEY, notification_scheduler.EXPIRY_WEBHOOKS_DAY_KEY)


def _set(key, value):
    SystemConfig.query.filter_by(key=key).delete()
    if value is not None:
        db.session.add(SystemConfig(key=key, value=value))
    db.session.commit()


def _value(key):
    return SystemConfig.query.filter_by(key=key).with_entities(SystemConfig.value).scalar()


def _held_elsewhere(minutes_ago):
    return f"{(utc_now() - timedelta(minutes=minutes_ago)).isoformat()}|other-node"


@pytest.fixture
def ha(monkeypatch):
    monkeypatch.setattr('utils.ha.ha_enabled', lambda: True)


@pytest.fixture(autouse=True)
def _expiry_keys_put_back(app):
    with app.app_context():
        saved = {key: _value(key) for key in _EXPIRY_KEYS}
        db.session.remove()
    yield
    with app.app_context():
        for key, value in saved.items():
            _set(key, value)
        db.session.remove()


# ------------------------------------------------------------------ the lease itself

def test_a_fresh_lease_is_refused_and_an_old_one_taken_over(app):
    key = f'lease-test-{uuid.uuid4().hex[:8]}'
    with app.app_context():
        try:
            mine = config_cas.ConfigLease(key, timedelta(minutes=10))
            assert mine.take()
            assert not config_cas.ConfigLease(key, timedelta(minutes=10)).take()
            # The holder died: its lease is older than the duration
            _set(key, _held_elsewhere(11))
            successor = config_cas.ConfigLease(key, timedelta(minutes=10))
            assert successor.take()
            assert not mine.renew()
            assert successor.renew()
            successor.end()
            assert config_cas.ConfigLease(key, timedelta(minutes=10)).take()
        finally:
            _set(key, None)


# ------------------------------------------------------------------ expiry e-mails and webhooks

def _record_sends(monkeypatch):
    sent = []

    def send(cert, days, recipients, threshold_days=None):
        sent.append(cert.refid)
        return True, 'sent'
    monkeypatch.setattr(NotificationSenderMixin, 'send_cert_expiring_notification', staticmethod(send))
    return sent


def _record_webhook_passes(monkeypatch):
    passes = []
    monkeypatch.setattr(expiry_alert_service, '_emit_expiry_webhooks', lambda: passes.append(1))
    return passes


def test_expiry_checks_held_by_a_live_node_send_nothing(
        app, ha, create_cert, expiry_config, smtp_spy, monkeypatch):  # noqa: F811
    refid = _set_validity(app, create_cert(cn='lease-live.example.com')['id'], days_left=20)
    sent, passes = _record_sends(monkeypatch), _record_webhook_passes(monkeypatch)
    with app.app_context():
        _set(notification_scheduler.EXPIRY_LEASE_KEY, _held_elsewhere(1))
        result = NotificationService.run_scheduled_checks()
    assert refid not in sent and passes == []
    assert result['status'] == 'skipped'


def test_expiry_checks_of_a_dead_node_resume_after_the_lease(
        app, ha, create_cert, expiry_config, smtp_spy, monkeypatch):  # noqa: F811
    refid = _set_validity(app, create_cert(cn='lease-dead.example.com')['id'], days_left=20)
    sent, passes = _record_sends(monkeypatch), _record_webhook_passes(monkeypatch)
    with app.app_context():
        _set(notification_scheduler.EXPIRY_LEASE_KEY, _held_elsewhere(11))
        NotificationService.run_scheduled_checks()
        assert _value(notification_scheduler.EXPIRY_LEASE_KEY) == ''
    assert sent.count(refid) == 1 and passes == [1]


def test_a_pass_whose_lease_was_taken_over_stops_sending(
        app, ha, create_cert, expiry_config, smtp_spy, monkeypatch):  # noqa: F811
    # Two due at least: the first send loses the lease, the second is not made
    _set_validity(app, create_cert(cn='lease-a.example.com')['id'], days_left=20)
    _set_validity(app, create_cert(cn='lease-b.example.com')['id'], days_left=20)
    sent, passes = [], _record_webhook_passes(monkeypatch)

    def send(cert, days, recipients, threshold_days=None):
        sent.append(cert.refid)
        # Stuck past the lease: another node took the run over
        with db.engine.begin() as other:
            other.execute(SystemConfig.__table__.update()
                          .where(SystemConfig.key == notification_scheduler.EXPIRY_LEASE_KEY)
                          .values(value=_held_elsewhere(0)))
        return True, 'sent'
    monkeypatch.setattr(NotificationSenderMixin, 'send_cert_expiring_notification', staticmethod(send))
    with app.app_context():
        NotificationService.run_scheduled_checks()
    assert len(sent) == 1
    assert passes == []


def test_expiry_webhooks_fire_once_per_day_in_ha(app, ha, monkeypatch):
    passes = _record_webhook_passes(monkeypatch)
    days = iter(['2026-11-11', '2026-11-11', '2026-11-12'])
    monkeypatch.setattr(notification_scheduler, '_cluster_day', lambda: next(days))
    with app.app_context():
        _set(notification_scheduler.EXPIRY_WEBHOOKS_DAY_KEY, None)
        for _ in range(3):
            NotificationService.run_scheduled_checks()
        assert _value(notification_scheduler.EXPIRY_WEBHOOKS_DAY_KEY) == '2026-11-12'
    assert passes == [1, 1]


def test_expiry_checks_reserve_nothing_outside_ha(app, monkeypatch):
    passes = _record_webhook_passes(monkeypatch)
    with app.app_context():
        _set(notification_scheduler.EXPIRY_LEASE_KEY, _held_elsewhere(1))
        _set(notification_scheduler.EXPIRY_WEBHOOKS_DAY_KEY, None)
        NotificationService.run_scheduled_checks()
        NotificationService.run_scheduled_checks()
        assert _value(notification_scheduler.EXPIRY_WEBHOOKS_DAY_KEY) is None
    assert passes == [1, 1]


def test_the_manual_check_reports_a_run_held_elsewhere(app, ha, auth_client, monkeypatch):
    _record_webhook_passes(monkeypatch)
    with app.app_context():
        _set(notification_scheduler.EXPIRY_LEASE_KEY, _held_elsewhere(1))
        db.session.remove()
    response = auth_client.post('/api/v2/system/alerts/expiry/check')
    assert response.status_code == 200, response.data
    assert 'another node' in response.get_json()['message']


@pytest.mark.parametrize('_backend', [pytest.param('pg', marks=_on_pg)])
def test_two_nodes_checking_expiry_at_once_emit_once_on_postgresql(app, ha, monkeypatch, _backend):
    passes = _record_webhook_passes(monkeypatch)
    with _pg(app):
        _twice_at_once(app, NotificationService.run_scheduled_checks, config_cas, '_held_value')
        with app.app_context():
            assert _value(notification_scheduler.EXPIRY_WEBHOOKS_DAY_KEY) is not None
            db.session.remove()
    assert passes == [1]


# ------------------------------------------------------------------ scheduled CRL

def _a_ca_due(app):
    with app.app_context():
        key, cert = _authority()
        ca = _ca_row(key, cert)
        return ca.id


def _drop_ca(app, ca_id):
    from models import CA
    from models.crl import CRLMetadata
    with app.app_context():
        CRLMetadata.query.filter_by(ca_id=ca_id).delete()
        CA.query.filter_by(id=ca_id).delete()
        _set(f'crl_schedule_lease_{ca_id}', None)
        db.session.remove()


def _record_regenerations(monkeypatch):
    regenerated = []
    monkeypatch.setattr(CRLSchedulerTask, 'regenerate_crl',
                        staticmethod(lambda ca_id, username='scheduler': regenerated.append(ca_id) or True))
    return regenerated


def test_a_crl_another_node_is_generating_is_left_to_it(app, ha, monkeypatch):
    ca_id = _a_ca_due(app)
    regenerated = _record_regenerations(monkeypatch)
    try:
        with app.app_context():
            _set(f'crl_schedule_lease_{ca_id}', _held_elsewhere(1))
            CRLSchedulerTask.execute()
        assert ca_id not in regenerated
    finally:
        _drop_ca(app, ca_id)


def test_a_crl_left_by_a_dead_node_is_generated_after_the_lease(app, ha, monkeypatch):
    ca_id = _a_ca_due(app)
    regenerated = _record_regenerations(monkeypatch)
    try:
        with app.app_context():
            _set(f'crl_schedule_lease_{ca_id}', _held_elsewhere(16))
            CRLSchedulerTask.execute()
            assert _value(f'crl_schedule_lease_{ca_id}') == ''
        assert regenerated.count(ca_id) == 1
    finally:
        _drop_ca(app, ca_id)


def test_a_crl_generated_elsewhere_before_the_lease_is_not_generated_again(app, ha, monkeypatch):
    ca_id = _a_ca_due(app)
    regenerated = _record_regenerations(monkeypatch)
    real = CRLSchedulerTask.should_regenerate_crl
    seen = []

    def due_once(cid):
        # Due when first read; the other node's CRL is committed before this one holds the lease
        if cid == ca_id:
            seen.append(cid)
            return (True, 'due') if len(seen) == 1 else (False, None)
        return real(cid)
    monkeypatch.setattr(CRLSchedulerTask, 'should_regenerate_crl', staticmethod(due_once))
    try:
        with app.app_context():
            CRLSchedulerTask.execute()
        assert ca_id not in regenerated and len(seen) == 2
    finally:
        _drop_ca(app, ca_id)


def test_the_scheduled_crl_reserves_nothing_outside_ha(app, monkeypatch):
    ca_id = _a_ca_due(app)
    regenerated = _record_regenerations(monkeypatch)
    try:
        with app.app_context():
            _set(f'crl_schedule_lease_{ca_id}', _held_elsewhere(1))
            CRLSchedulerTask.execute()
        assert regenerated.count(ca_id) == 1
    finally:
        _drop_ca(app, ca_id)


def test_a_delta_crl_another_node_is_generating_is_left_to_it(app, ha, monkeypatch):
    from models import CA
    from services.crl_service import CRLService
    ca_id = _a_ca_due(app)
    deltas = []
    monkeypatch.setattr(CRLService, 'generate_delta_crl',
                        staticmethod(lambda cid, **kw: deltas.append(cid)))
    try:
        with app.app_context():
            CRLService.generate_crl(ca_id, username='test')
            ca = db.session.get(CA, ca_id)
            ca.delta_crl_enabled = True
            db.session.commit()
            _set(f'crl_schedule_lease_{ca_id}', _held_elsewhere(1))
            deltas.clear()
            CRLSchedulerTask.execute()
        assert ca_id not in deltas
    finally:
        _drop_ca(app, ca_id)


@pytest.mark.parametrize('_backend', [pytest.param('pg', marks=_on_pg)])
def test_two_nodes_publishing_a_crl_at_once_publish_once_on_postgresql(app, ha, monkeypatch, _backend):
    regenerated = _record_regenerations(monkeypatch)
    with _pg(app):
        ca_id = _a_ca_due(app)
        _twice_at_once(app, CRLSchedulerTask.execute, config_cas, '_held_value')
    assert regenerated.count(ca_id) == 1


# ------------------------------------------------------------------ Microsoft CA CRL sync

def test_a_certificate_revoked_elsewhere_meanwhile_is_not_announced_again(
        app, auth_client, fake_adcs, patched_network, monkeypatch):
    from models import Certificate
    from services.msca.crl_sync import MicrosoftCACRLSyncMixin
    from tests.test_msca_crl_sync import _add_connection_with_certs
    msca_id, ids = _add_connection_with_certs(app, f'CRL lease {uuid.uuid4().hex[:8]}', fake_adcs)
    announced = []
    monkeypatch.setattr('services.webhook_service.emit_cert_revoked',
                        lambda cert, **kw: announced.append(cert['id']))
    real = MicrosoftCACRLSyncMixin._connection_certificates

    def read_then_revoked_elsewhere(msca):
        candidates = real(msca)
        # The other node's sync commits the revocation after this one's read
        with db.engine.begin() as other:
            other.execute(Certificate.__table__.update().where(Certificate.id == ids['revoked'])
                          .values(revoked=True, revoke_reason='keyCompromise', revoked_at=utc_now()))
        return candidates
    monkeypatch.setattr(MicrosoftCACRLSyncMixin, '_connection_certificates',
                        staticmethod(read_then_revoked_elsewhere))
    with app.app_context():
        summary = MicrosoftCACRLSyncMixin.sync_crl(msca_id, username='scheduler')
    assert summary['revoked'] == 0
    assert ids['revoked'] not in announced


from tests.test_msca_crl_sync import fake_adcs, patched_network  # noqa: E402,F401  (fixtures)
