"""In HA, a scheduled pass that sends outside acts once per due date, even when two nodes
believe they lead: expiry e-mails and webhooks, the scheduled CRL, the Microsoft CA CRL sync.

The pass holds a lease on a ``system_config`` row taken by compare-and-set; a node that
dies holding it frees it once the lease is over. Outside HA nothing is reserved.
"""
import base64
import os
import uuid
from datetime import datetime, timedelta

import pytest

from models import Certificate, SystemConfig, db
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

_EXPIRY_KEYS = (notification_scheduler.EXPIRY_LEASE_KEY, notification_scheduler.EXPIRY_WEBHOOKS_MARK_KEY)


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


@pytest.fixture(autouse=True, scope='module')
def _rows_of_this_file_removed(app):
    """The CAs, certificates and Microsoft CA connections this file creates, deleted after it."""
    from models import CA
    from models.msca import MicrosoftCA, MSCARequest
    from tests import seeded_rows

    def _top(model):
        return db.session.query(db.func.max(model.id)).scalar() or 0
    with app.app_context():
        tops = {model: _top(model) for model in (CA, Certificate, MicrosoftCA)}
        db.session.remove()
    yield
    with app.app_context():
        msca_ids = [row.id for row in MicrosoftCA.query.filter(MicrosoftCA.id > tops[MicrosoftCA])]
        MSCARequest.query.filter(MSCARequest.msca_id.in_(msca_ids)).delete(synchronize_session=False)
        MicrosoftCA.query.filter(MicrosoftCA.id.in_(msca_ids)).delete(synchronize_session=False)
        seeded_rows.delete_cas(CA.query.filter(CA.id > tops[CA]))
        db.session.commit()
        for (cert_id,) in db.session.query(Certificate.id).filter(Certificate.id > tops[Certificate]):
            seeded_rows._SEEDED.append((app, 'certificates', 'id', cert_id))
        db.session.remove()
    seeded_rows.remove_seeded()


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



def test_a_lease_stamped_far_in_the_future_does_not_hold_forever(app):
    # A clock stepped back, or a stamp from elsewhere: live for one duration at most
    key = f'lease-test-{uuid.uuid4().hex[:8]}'
    with app.app_context():
        try:
            _set(key, f"{(utc_now() + timedelta(hours=1)).isoformat()}|other-node")
            assert config_cas.ConfigLease(key, timedelta(minutes=10)).take()
            _set(key, f"{(utc_now() + timedelta(minutes=1)).isoformat()}|other-node")
            assert not config_cas.ConfigLease(key, timedelta(minutes=10)).take()
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
    monkeypatch.setattr(expiry_alert_service, '_emit_expiry_webhooks', lambda **_: passes.append(1) or True)
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
        result = NotificationService.run_scheduled_checks()
    assert len(sent) == 1
    assert passes == []
    # Recorded as a run with something to see, not as a complete one
    from services.scheduler_service import SchedulerService
    assert SchedulerService._outcome_of(result)[0] == 'warning'
    assert result['cert_expiring']['notified'] == 1


def test_expiring_reminders_fire_once_per_day_in_ha(app, ha, monkeypatch):
    passes = []
    monkeypatch.setattr(expiry_alert_service, '_emit_expiry_webhooks',
                        lambda expiring=True, **_: passes.append(expiring) or True)
    first = datetime(2026, 11, 11, 1, 0)
    instants = iter([first, first + timedelta(hours=20), first + timedelta(hours=24)])
    monkeypatch.setattr(notification_scheduler, '_cluster_now', lambda: next(instants))
    with app.app_context():
        _set(notification_scheduler.EXPIRY_WEBHOOKS_MARK_KEY, None)
        for _ in range(3):
            NotificationService.run_scheduled_checks()
        assert _value(notification_scheduler.EXPIRY_WEBHOOKS_MARK_KEY) == (first + timedelta(hours=24)).isoformat()
    assert passes == [True, False, True]


def test_expiry_checks_reserve_nothing_outside_ha(app, monkeypatch):
    passes = _record_webhook_passes(monkeypatch)
    instant = datetime(2031, 3, 4, 0, 30)
    monkeypatch.setattr(notification_scheduler, '_cluster_now', lambda: instant)
    with app.app_context():
        _set(notification_scheduler.EXPIRY_LEASE_KEY, _held_elsewhere(1))
        _set(notification_scheduler.EXPIRY_WEBHOOKS_MARK_KEY, None)
        NotificationService.run_scheduled_checks()
        NotificationService.run_scheduled_checks()
        # The lease held elsewhere is ignored; the mark follows the single-node passes
        assert _value(notification_scheduler.EXPIRY_WEBHOOKS_MARK_KEY) == instant.isoformat()
    assert passes == [1, 1]


def test_ha_turned_back_on_does_not_announce_again_what_single_node_passes_did(
        app, create_cert, monkeypatch):
    # HA pass at t0, single-node passes daily, HA back at t0+10d: the expiry at t0+5d is announced once
    cert_id = create_cert(cn='expired-ha-back.example.com')['id']
    t0 = datetime(2031, 3, 4, 0, 30)
    _expires_at(app, cert_id, t0 + timedelta(days=5, hours=1))
    emitted = _record_expiry_webhooks(monkeypatch, cert_id)
    state = {'ha': True, 'now': t0}
    monkeypatch.setattr('utils.ha.ha_enabled', lambda: state['ha'])
    monkeypatch.setattr(notification_scheduler, '_cluster_now', lambda: state['now'])
    monkeypatch.setattr(expiry_alert_service, 'utc_now', lambda: state['now'])
    with app.app_context():
        _set(notification_scheduler.EXPIRY_LEASE_KEY, None)
        _set(notification_scheduler.EXPIRY_WEBHOOKS_MARK_KEY, None)
        NotificationService.run_scheduled_checks()
        state['ha'] = False
        for day in range(1, 10):
            state['now'] = t0 + timedelta(days=day)
            NotificationService.run_scheduled_checks()
        state['ha'], state['now'] = True, t0 + timedelta(days=10)
        NotificationService.run_scheduled_checks()
    assert emitted['expired'] == 1


def test_the_manual_check_reports_a_run_held_elsewhere(app, ha, auth_client, monkeypatch):
    _record_webhook_passes(monkeypatch)
    with app.app_context():
        _set(notification_scheduler.EXPIRY_LEASE_KEY, _held_elsewhere(1))
        db.session.remove()
    response = auth_client.post('/api/v2/system/alerts/expiry/check')
    assert response.status_code == 200, response.data
    assert 'another node' in response.get_json()['message']


def _record_expiry_webhooks(monkeypatch, cert_id):
    emitted = {'expiring': 0, 'expired': 0}

    def recorder(kind):
        def emit(cert, *args, **kwargs):
            if cert.get('id') == cert_id:
                emitted[kind] += 1
        return emit
    monkeypatch.setattr('services.webhook_service.emit_cert_expiring', recorder('expiring'))
    monkeypatch.setattr('services.webhook_service.emit_cert_expired', recorder('expired'))
    return emitted


def _passes_at(app, monkeypatch, instants):
    clock = iter(instants)
    monkeypatch.setattr(notification_scheduler, '_cluster_now', lambda: next(clock))
    with app.app_context():
        for _ in instants:
            NotificationService.run_scheduled_checks()


def _expires_at(app, cert_id, valid_to):
    with app.app_context():
        cert = db.session.get(Certificate, cert_id)
        cert.valid_from, cert.valid_to = valid_to - timedelta(days=365), valid_to
        db.session.commit()


def test_a_certificate_expired_before_a_same_day_leader_change_is_announced_once(
        app, ha, create_cert, monkeypatch):
    # Old leader at 00:30, certificate expired at 10:30, new leader at 23:00 then 23:00 the day after
    cert_id = create_cert(cn='expired-leader-change.example.com')['id']
    day = datetime(2031, 3, 4, 0, 30)
    _expires_at(app, cert_id, day + timedelta(hours=10))
    emitted = _record_expiry_webhooks(monkeypatch, cert_id)
    with app.app_context():
        _set(notification_scheduler.EXPIRY_WEBHOOKS_MARK_KEY, None)
    _passes_at(app, monkeypatch, [day, day + timedelta(hours=22, minutes=30),
                                  day + timedelta(hours=46, minutes=30)])
    assert emitted == {'expiring': 1, 'expired': 1}


def test_a_certificate_expired_during_a_long_pause_is_announced_once(
        app, ha, create_cert, monkeypatch):
    cert_id = create_cert(cn='expired-pause.example.com')['id']
    last = datetime(2031, 3, 4, 0, 30)
    _expires_at(app, cert_id, last + timedelta(hours=2))
    emitted = _record_expiry_webhooks(monkeypatch, cert_id)
    with app.app_context():
        _set(notification_scheduler.EXPIRY_WEBHOOKS_MARK_KEY, None)
    _passes_at(app, monkeypatch, [last, last + timedelta(hours=30), last + timedelta(hours=54)])
    assert emitted == {'expiring': 1, 'expired': 1}


@pytest.mark.parametrize('_backend', [pytest.param('pg', marks=_on_pg)])
def test_two_nodes_checking_expiry_at_once_emit_once_on_postgresql(app, ha, monkeypatch, _backend):
    passes = _record_webhook_passes(monkeypatch)
    with _pg(app):
        _twice_at_once(app, NotificationService.run_scheduled_checks, config_cas, '_held_value')
        with app.app_context():
            assert _value(notification_scheduler.EXPIRY_WEBHOOKS_MARK_KEY) is not None
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


@pytest.mark.parametrize('in_ha', [True, False])
def test_the_webhook_mark_never_moves_back_with_the_clock(app, monkeypatch, in_ha):
    # A cluster clock stepping back (NTP, PostgreSQL failover) would announce the same expiries again
    _record_webhook_passes(monkeypatch)
    monkeypatch.setattr('utils.ha.ha_enabled', lambda: in_ha)
    later = datetime(2031, 3, 4, 12, 0)
    monkeypatch.setattr(notification_scheduler, '_cluster_now', lambda: later - timedelta(minutes=5))
    with app.app_context():
        _set(notification_scheduler.EXPIRY_LEASE_KEY, None)
        _set(notification_scheduler.EXPIRY_WEBHOOKS_MARK_KEY, later.isoformat())
        NotificationService.run_scheduled_checks()
        assert _value(notification_scheduler.EXPIRY_WEBHOOKS_MARK_KEY) == later.isoformat()


@pytest.mark.parametrize('in_ha', [True, False])
def test_a_failed_webhook_pass_leaves_the_mark_for_the_next_one(app, monkeypatch, in_ha):
    # The expiries of the failed pass are announced by the next one, not lost
    def fail(**_):
        raise RuntimeError('webhook store down')
    monkeypatch.setattr('services.ca.cross_certs.expiring_alerts', fail)
    monkeypatch.setattr('utils.ha.ha_enabled', lambda: in_ha)
    before = datetime(2031, 3, 4, 0, 30)
    monkeypatch.setattr(notification_scheduler, '_cluster_now', lambda: before + timedelta(days=1))
    with app.app_context():
        _set(notification_scheduler.EXPIRY_LEASE_KEY, None)
        _set(notification_scheduler.EXPIRY_WEBHOOKS_MARK_KEY, before.isoformat())
        NotificationService.run_scheduled_checks()
        assert _value(notification_scheduler.EXPIRY_WEBHOOKS_MARK_KEY) == before.isoformat()


def test_a_mark_not_stored_is_not_logged_as_a_failed_pass(app, ha, monkeypatch, caplog):
    _record_webhook_passes(monkeypatch)

    real = config_cas.config_compare_and_set

    def fail(key, *a, **k):
        if key == notification_scheduler.EXPIRY_WEBHOOKS_MARK_KEY:
            raise RuntimeError('database down')
        return real(key, *a, **k)
    monkeypatch.setattr(config_cas, 'config_compare_and_set', fail)
    with app.app_context():
        _set(notification_scheduler.EXPIRY_LEASE_KEY, None)
        with caplog.at_level('WARNING'):
            NotificationService.run_scheduled_checks()
    messages = [r.getMessage() for r in caplog.records]
    assert not any('webhook pass failed' in m for m in messages), messages
    assert any('mark not stored' in m for m in messages), messages


def test_the_manual_check_counts_what_a_pass_taken_over_sent(app, auth_client, monkeypatch):
    counts = {'cert_expiring': {'checked': 2, 'notified': 2, 'failed': 0},
              'crl_expiring': {'checked': 0, 'notified': 0, 'failed': 0}}
    monkeypatch.setattr(NotificationService, 'run_scheduled_checks',
                        staticmethod(lambda: notification_scheduler.NotificationSchedulerMixin._taken_over(counts)))
    response = auth_client.post('/api/v2/system/alerts/expiry/check')
    assert response.status_code == 200, response.data
    assert '2 alerts sent' in response.get_json()['message']


def test_a_crl_sync_revokes_in_id_order(app, fake_adcs, patched_network, monkeypatch):
    # Two syncs locking the same rows in one order cannot deadlock on PostgreSQL
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from sqlalchemy import event
    from models import Certificate
    from models.msca import MicrosoftCA, MSCARequest
    from services.msca.crl_sync import MicrosoftCACRLSyncMixin
    from tests.test_msca_crl_sync import _add_connection_with_certs
    msca_id, ids = _add_connection_with_certs(app, f'CRL order {uuid.uuid4().hex[:8]}', fake_adcs)
    now = utc_now()
    builder = (x509.CertificateRevocationListBuilder().issuer_name(fake_adcs['crl'].issuer)
               .last_update(now - timedelta(minutes=10)).next_update(now + timedelta(days=7)))
    for cert in (fake_adcs['revoked_cert'], fake_adcs['valid_cert']):
        builder = builder.add_revoked_certificate(
            x509.RevokedCertificateBuilder().serial_number(cert.serial_number)
            .revocation_date(now - timedelta(minutes=30)).build())
    crl = builder.sign(fake_adcs['ca_key'], hashes.SHA256())
    monkeypatch.setattr(MicrosoftCACRLSyncMixin, '_fetch_crl', staticmethod(lambda msca, url: crl))
    real = MicrosoftCACRLSyncMixin._connection_certificates
    monkeypatch.setattr(MicrosoftCACRLSyncMixin, '_connection_certificates',
                        staticmethod(lambda msca: sorted(real(msca), key=lambda c: -c.id)))
    updated = []

    def witness(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith('UPDATE CERTIFICATES'):
            updated.append((statement, params))
    try:
        with app.app_context():
            event.listen(db.engine, 'before_cursor_execute', witness)
            try:
                summary = MicrosoftCACRLSyncMixin.sync_crl(msca_id, username='scheduler')
            finally:
                event.remove(db.engine, 'before_cursor_execute', witness)
        assert summary['revoked'] == 2
        # The row id is the WHERE clause's parameter: last positional, or the named id_1
        order = [next(v for k, v in p.items() if k.startswith('id')) if isinstance(p, dict) else p[-1]
                 for _, p in updated]
        assert order == sorted(ids.values()), updated
    finally:
        with app.app_context():
            MSCARequest.query.filter_by(msca_id=msca_id).delete()
            Certificate.query.filter(Certificate.id.in_(list(ids.values()))).delete(synchronize_session=False)
            MicrosoftCA.query.filter_by(id=msca_id).delete()
            db.session.commit()


# ------------------------------------------------------------------ catch-up bounded after an outage

@pytest.mark.parametrize('in_ha', [True, False])
def test_a_90_day_outage_announces_only_the_last_30_days_of_expiries(
        app, create_cert, monkeypatch, caplog, in_ha):
    # A year no other test uses: the count of what is left aside is this test's own
    now = datetime(2044 if in_ha else 2045, 6, 1, 12, 0)
    old_id = create_cert(cn=f'outage-old-{in_ha}.example.com')['id']
    recent_id = create_cert(cn=f'outage-recent-{in_ha}.example.com')['id']
    _expires_at(app, old_id, now - timedelta(days=60))
    _expires_at(app, recent_id, now - timedelta(days=10))
    announced = []
    monkeypatch.setattr('services.webhook_service.emit_cert_expiring', lambda *a, **k: None)
    monkeypatch.setattr('services.webhook_service.emit_cert_expired',
                        lambda cert, **k: announced.append(cert.get('id')))
    monkeypatch.setattr('utils.ha.ha_enabled', lambda: in_ha)
    monkeypatch.setattr(notification_scheduler, '_cluster_now', lambda: now)
    monkeypatch.setattr(expiry_alert_service, 'utc_now', lambda: now)
    with app.app_context():
        _set(notification_scheduler.EXPIRY_LEASE_KEY, None)
        _set(notification_scheduler.EXPIRY_WEBHOOKS_MARK_KEY, (now - timedelta(days=90)).isoformat())
        with caplog.at_level('WARNING'):
            NotificationService.run_scheduled_checks()
        assert _value(notification_scheduler.EXPIRY_WEBHOOKS_MARK_KEY) == now.isoformat()
    assert recent_id in announced and old_id not in announced
    assert any('1 certificate(s)' in r.getMessage() and '30 days' in r.getMessage()
               for r in caplog.records), [r.getMessage() for r in caplog.records]


@pytest.mark.parametrize('in_ha', [True, False])
def test_a_first_pass_without_a_mark_announces_the_last_day_only(
        app, create_cert, monkeypatch, in_ha):
    now = datetime(2046 if in_ha else 2047, 7, 1, 12, 0)
    day_old_id = create_cert(cn=f'first-pass-old-{in_ha}.example.com')['id']
    hour_old_id = create_cert(cn=f'first-pass-new-{in_ha}.example.com')['id']
    _expires_at(app, day_old_id, now - timedelta(days=2))
    _expires_at(app, hour_old_id, now - timedelta(hours=1))
    announced = []
    monkeypatch.setattr('services.webhook_service.emit_cert_expiring', lambda *a, **k: None)
    monkeypatch.setattr('services.webhook_service.emit_cert_expired',
                        lambda cert, **k: announced.append(cert.get('id')))
    monkeypatch.setattr('utils.ha.ha_enabled', lambda: in_ha)
    monkeypatch.setattr(notification_scheduler, '_cluster_now', lambda: now)
    monkeypatch.setattr(expiry_alert_service, 'utc_now', lambda: now)
    with app.app_context():
        _set(notification_scheduler.EXPIRY_LEASE_KEY, None)
        _set(notification_scheduler.EXPIRY_WEBHOOKS_MARK_KEY, None)
        NotificationService.run_scheduled_checks()
    assert hour_old_id in announced and day_old_id not in announced


# ------------------------------------------------------------------ a skipped pass is retried

def _cluster_clock(monkeypatch, instant):
    monkeypatch.setattr('services.scheduler_leader.cluster_utc_now', lambda *a, **k: instant)


def test_a_refused_lease_tells_when_it_frees(app, monkeypatch):
    key = f'lease-test-{uuid.uuid4().hex[:8]}'
    now = datetime(2044, 1, 1, 12, 0)
    _cluster_clock(monkeypatch, now)
    with app.app_context():
        try:
            _set(key, f"{(now - timedelta(minutes=4)).isoformat()}|other-node")
            lease = config_cas.ConfigLease(key, timedelta(minutes=10))
            assert not lease.take()
            assert lease.retry_in() == 6 * 60 + config_cas.LEASE_RETRY_MARGIN.total_seconds()
        finally:
            _set(key, None)


def test_expiry_checks_held_elsewhere_ask_a_retry_when_the_lease_ends(app, ha, monkeypatch):
    passes = _record_webhook_passes(monkeypatch)
    now = datetime(2044, 1, 1, 12, 0)
    _cluster_clock(monkeypatch, now)
    with app.app_context():
        _set(notification_scheduler.EXPIRY_LEASE_KEY, f"{(now - timedelta(minutes=3)).isoformat()}|other-node")
        result = NotificationService.run_scheduled_checks()
    assert result['status'] == 'skipped' and passes == []
    assert result['retry_in'] == 7 * 60 + config_cas.LEASE_RETRY_MARGIN.total_seconds()


def test_the_retried_expiry_pass_announces_nothing_the_holder_did(app, ha, create_cert, monkeypatch):
    """Regression lock, not a proof: it also passes without the retry code (the mark alone covers it)."""
    # The holder finished meanwhile: its mark covers the expiry, the retry announces it no more
    cert_id = create_cert(cn='retry-after-holder.example.com')['id']
    now = datetime(2044, 2, 1, 12, 0)
    _expires_at(app, cert_id, now - timedelta(hours=2))
    emitted = _record_expiry_webhooks(monkeypatch, cert_id)
    monkeypatch.setattr(expiry_alert_service, 'utc_now', lambda: now)
    with app.app_context():
        _set(notification_scheduler.EXPIRY_LEASE_KEY, None)
        _set(notification_scheduler.EXPIRY_WEBHOOKS_MARK_KEY, (now - timedelta(days=1)).isoformat())
    _passes_at(app, monkeypatch, [now, now + timedelta(minutes=10, seconds=30)])
    assert emitted == {'expiring': 0, 'expired': 1}


def test_a_crl_held_elsewhere_asks_a_retry_when_its_lease_ends(app, ha, monkeypatch):
    ca_id, other_id = _a_ca_due(app), _a_ca_due(app)
    regenerated = _record_regenerations(monkeypatch)
    now = datetime(2044, 1, 1, 12, 0)
    _cluster_clock(monkeypatch, now)
    try:
        with app.app_context():
            _set(f'crl_schedule_lease_{ca_id}', f"{(now - timedelta(minutes=5)).isoformat()}|other-node")
            _set(f'crl_schedule_lease_{other_id}', f"{(now - timedelta(minutes=10)).isoformat()}|other-node")
            result = CRLSchedulerTask.execute()
        assert ca_id not in regenerated and other_id not in regenerated
        # One retry, once the later of the two leases is over
        assert result['retry_in'] == 10 * 60 + config_cas.LEASE_RETRY_MARGIN.total_seconds()
    finally:
        _drop_ca(app, ca_id)
        _drop_ca(app, other_id)


def test_a_crl_pass_with_nothing_held_asks_no_retry(app, ha, monkeypatch):
    """Regression lock, not a proof: it also passes without the retry code (nothing asks a retry)."""
    ca_id = _a_ca_due(app)
    _record_regenerations(monkeypatch)
    try:
        with app.app_context():
            result = CRLSchedulerTask.execute()
        assert not (result or {}).get('retry_in')
    finally:
        _drop_ca(app, ca_id)


def test_the_scheduler_reruns_the_skipped_expiry_pass_once_the_lease_is_over(app, ha, monkeypatch):
    from services import scheduler_service
    passes = _record_webhook_passes(monkeypatch)
    now = datetime(2044, 3, 1, 12, 0)
    clock = {'now': now}
    monkeypatch.setattr('services.scheduler_leader.cluster_utc_now', lambda *a, **k: clock['now'])
    monkeypatch.setattr(scheduler_service, 'utc_now', lambda: clock['now'])
    s = scheduler_service.SchedulerService(wake_interval=60, node_id='retry-node')
    s._app = app
    s.register_task('cert_expiry_alerts', NotificationService.run_scheduled_checks, interval=86400)
    task = s.tasks['cert_expiry_alerts']
    with app.app_context():
        _set(notification_scheduler.EXPIRY_LEASE_KEY, f"{(now - timedelta(minutes=2)).isoformat()}|other-node")
    s._run_task(task)
    assert task.last_status == 'skipped' and passes == []
    clock['now'] = now + timedelta(minutes=8)
    assert not task.should_run()
    clock['now'] = now + timedelta(minutes=8, seconds=30)
    assert task.should_run()
    s._run_task(task)
    assert task.last_status == 'ok' and passes == [1] and task.retry_at is None
