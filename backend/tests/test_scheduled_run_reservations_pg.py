"""A scheduled run executed twice (two nodes during a leader change) acts once.

Scheduled reports and the scheduled backup reserve their slot by compare-and-set on
``system_config`` before sending or writing; the ACME proxy starts one dns-01 automation
per upstream challenge even when two sibling orders are served by two nodes at once.
"""
import json
import os
import threading
import uuid
from datetime import datetime, timedelta

import pytest

from models import AcmeClientOrder, SystemConfig, db
from services import report_service
from services.backup import schedule
from tests.test_scheduled_claims_pg import _pg, _twice_at_once

_PG_URL = os.environ.get('UCM_TEST_PG_URL')
_NOW = datetime(2026, 11, 11, 8, 0)


def _set(key, value):
    SystemConfig.query.filter_by(key=key).delete()
    if value is not None:
        db.session.add(SystemConfig(key=key, value=value))
    db.session.commit()


# ------------------------------------------------------------------ reports

def _report_schedule(app, monkeypatch):
    """One daily report due now; send_report records instead of mailing."""
    sent = []
    key = 'ca_hierarchy'
    monkeypatch.setattr(report_service, 'utc_now', lambda: _NOW)
    monkeypatch.setattr(report_service, 'send_report', lambda k, r, f='csv': sent.append(k) or True)
    with app.app_context():
        _set(f'report_schedule_{key}', json.dumps({
            'enabled': True, 'frequency': 'daily', 'time': '08:00',
            'recipients': ['ops@example.test'], 'format': 'csv'}))
        _set(f'report_last_sent_{key}', None)
        db.session.remove()
    return key, sent


def _drop_report(app, key):
    with app.app_context():
        _set(f'report_schedule_{key}', None)
        _set(f'report_last_sent_{key}', None)
        db.session.remove()


def test_a_report_runs_once_per_slot_on_sqlite(app, monkeypatch):
    key, sent = _report_schedule(app, monkeypatch)
    try:
        with app.app_context():
            report_service.run_scheduled_reports()
            report_service.run_scheduled_reports()
            assert SystemConfig.query.filter_by(key=f'report_last_sent_{key}').one().value \
                == '2026-11-11T08:00'
        assert sent.count(key) == 1
    finally:
        _drop_report(app, key)


def test_the_next_slot_is_sent_again(app, monkeypatch):
    key, sent = _report_schedule(app, monkeypatch)
    try:
        with app.app_context():
            report_service.run_scheduled_reports()
            monkeypatch.setattr(report_service, 'utc_now', lambda: datetime(2026, 11, 12, 8, 0))
            report_service.run_scheduled_reports()
        assert sent.count(key) == 2
    finally:
        _drop_report(app, key)


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
def test_two_report_runners_send_once_on_postgresql(app, monkeypatch):
    with _pg(app):
        key, sent = _report_schedule(app, monkeypatch)
        _twice_at_once(app, report_service.run_scheduled_reports,
                       report_service, 'config_compare_and_set')
    assert sent.count(key) == 1


# ------------------------------------------------------------------ backup

def _backup_schedule(app, monkeypatch, tmp_path, last_run=None):
    """Automatic backups on and due; the archive write is recorded, not performed."""
    from config.settings import Config
    import contextlib
    exported = []

    def export(service, password, kdf=None):
        exported.append(password)
        return 3, str(tmp_path / 'x.ucmbkp'), f'ucm_backup_{len(exported)}.ucmbkp'

    monkeypatch.setattr(Config, 'BACKUP_DIR', tmp_path, raising=False)
    monkeypatch.setattr(schedule.storage, 'export_archive', export)
    monkeypatch.setattr(schedule, '_apply_retention', lambda days: 0)
    monkeypatch.setattr(schedule, '_audit_scheduled_backup', lambda *a, **k: None)
    # Two nodes: the process-local operation lock does not order them
    monkeypatch.setattr(schedule, 'backup_operation_lock',
                        lambda **k: contextlib.nullcontext())
    with app.app_context():
        _set('auto_backup_enabled', 'true')
        _set('backup_frequency', 'daily')
        _set('backup_password', 'Correct-Horse-Battery-9')
        _set('backup.last_run', last_run)
        db.session.remove()
    return exported


def _drop_backup(app):
    with app.app_context():
        for key in ('auto_backup_enabled', 'backup_password', 'backup.last_run',
                    'backup.last_outcome', 'backup.last_reason', 'backup.last_outcome_at',
                    'backup.concluded_run'):
            _set(key, None)
        db.session.remove()


def test_a_node_that_read_the_schedule_before_the_other_wrote_does_not_back_up(
        app, monkeypatch, tmp_path):
    exported = _backup_schedule(app, monkeypatch, tmp_path)
    try:
        with app.app_context():
            stale = schedule.get_schedule()
            now = schedule.utc_now()
            assert schedule._create_scheduled_backup(stale, now, 'Correct-Horse-Battery-9')['status'] == 'ok'
            assert schedule._create_scheduled_backup(stale, now, 'Correct-Horse-Battery-9') == {
                'status': 'skipped', 'reason': 'claimed by another node'}
        assert len(exported) == 1
    finally:
        _drop_backup(app)


def test_a_failed_export_gives_the_slot_back(app, monkeypatch, tmp_path):
    _backup_schedule(app, monkeypatch, tmp_path)
    monkeypatch.setattr(schedule.storage, 'export_archive',
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError('disk full')))
    try:
        with app.app_context():
            _set('backup.last_run', '2026-01-01T00:00:00Z')
            with pytest.raises(RuntimeError):
                schedule.run_scheduled_backup()
            assert schedule._get('backup.last_run') == '2026-01-01T00:00:00Z'
    finally:
        _drop_backup(app)


class _Killed(BaseException):
    """What os._exit, an OOM kill or a SIGTERM past the grace period look like to the
    code after the claim: nothing below the export runs."""


def _interrupted_then_retried(app, monkeypatch, tmp_path):
    """Claim a run, die inside the export, then tick within and past the lease."""
    exported = _backup_schedule(app, monkeypatch, tmp_path, last_run='2026-01-01T00:00:00Z')
    real_export = schedule.storage.export_archive

    def die(*a, **k):
        raise _Killed()

    clock = {'now': _NOW}
    monkeypatch.setattr(schedule, 'utc_now', lambda: clock['now'])
    with app.app_context():
        _set('backup.last_outcome', 'ok')
        _set('backup.last_outcome_at', '2026-01-01T00:05:00Z')
        monkeypatch.setattr(schedule.storage, 'export_archive', die)
        with pytest.raises(_Killed):
            schedule.run_scheduled_backup()
        db.session.remove()
        monkeypatch.setattr(schedule.storage, 'export_archive', real_export)

        clock['now'] = _NOW + timedelta(minutes=10)
        within = schedule.run_scheduled_backup()
        clock['now'] = _NOW + timedelta(seconds=schedule._CLAIM_LEASE_SECONDS + 60)
        after = schedule.run_scheduled_backup()
        db.session.remove()
    return within, after, exported


def test_a_run_killed_during_the_export_is_retried_after_the_lease(app, monkeypatch, tmp_path):
    try:
        within, after, exported = _interrupted_then_retried(app, monkeypatch, tmp_path)
        # Still in flight on another node for all this one knows; then abandoned
        assert within == {'status': 'skipped', 'reason': 'not_due'}
        assert after['status'] == 'ok'
        assert len(exported) == 1
    finally:
        _drop_backup(app)


def test_a_concluded_run_is_not_retried_after_the_lease(app, monkeypatch, tmp_path):
    exported = _backup_schedule(app, monkeypatch, tmp_path, last_run='2026-01-01T00:00:00Z')
    clock = {'now': _NOW}
    monkeypatch.setattr(schedule, 'utc_now', lambda: clock['now'])
    try:
        with app.app_context():
            assert schedule.run_scheduled_backup()['status'] == 'ok'
            clock['now'] = _NOW + timedelta(seconds=schedule._CLAIM_LEASE_SECONDS + 60)
            assert schedule.run_scheduled_backup() == {'status': 'skipped', 'reason': 'not_due'}
        assert len(exported) == 1
    finally:
        _drop_backup(app)


def _killed(app, monkeypatch, tmp_path, last_run='2026-01-01T00:00:00Z'):
    """A run claimed at _NOW that died inside the export; returns the export log and clock."""
    exported = _backup_schedule(app, monkeypatch, tmp_path, last_run=last_run)
    real_export = schedule.storage.export_archive
    clock = {'now': _NOW}
    monkeypatch.setattr(schedule, 'utc_now', lambda: clock['now'])
    monkeypatch.setattr(schedule.storage, 'export_archive',
                        lambda *a, **k: (_ for _ in ()).throw(_Killed()))
    with app.app_context():
        with pytest.raises(_Killed):
            schedule.run_scheduled_backup()
        db.session.remove()
    monkeypatch.setattr(schedule.storage, 'export_archive', real_export)
    return exported, clock


_PAST_LEASE = timedelta(seconds=schedule._CLAIM_LEASE_SECONDS + 60)


def test_a_failed_resumption_is_retried_on_the_next_tick(app, monkeypatch, tmp_path):
    exported, clock = _killed(app, monkeypatch, tmp_path)
    real_export = schedule.storage.export_archive
    try:
        with app.app_context():
            clock['now'] = _NOW + _PAST_LEASE
            monkeypatch.setattr(schedule.storage, 'export_archive',
                                lambda *a, **k: (_ for _ in ()).throw(OSError('disk full')))
            with pytest.raises(OSError):
                schedule.run_scheduled_backup()
            monkeypatch.setattr(schedule.storage, 'export_archive', real_export)
            clock['now'] += timedelta(minutes=1)
            assert schedule.run_scheduled_backup()['status'] == 'ok'
        assert len(exported) == 1
    finally:
        _drop_backup(app)


def test_a_killed_run_is_retried_after_being_disabled_and_enabled(app, monkeypatch, tmp_path):
    exported, clock = _killed(app, monkeypatch, tmp_path)
    try:
        with app.app_context():
            _set('auto_backup_enabled', 'false')
            clock['now'] = _NOW + timedelta(minutes=30)
            assert schedule.run_scheduled_backup()['status'] == 'skipped'
            _set('auto_backup_enabled', 'true')
            clock['now'] = _NOW + timedelta(hours=1)
            assert schedule.run_scheduled_backup() == {'status': 'skipped', 'reason': 'not_due'}
            clock['now'] = _NOW + _PAST_LEASE
            assert schedule.run_scheduled_backup()['status'] == 'ok'
        assert len(exported) == 1
    finally:
        _drop_backup(app)


def test_a_resumption_refused_for_its_password_runs_once_it_is_fixed(app, monkeypatch, tmp_path):
    from services.backup.errors import ScheduledBackupError
    exported, clock = _killed(app, monkeypatch, tmp_path)
    try:
        with app.app_context():
            _set('backup_password', 'short')
            clock['now'] = _NOW + _PAST_LEASE
            with pytest.raises(ScheduledBackupError):
                schedule.run_scheduled_backup()
            _set('backup_password', 'Correct-Horse-Battery-9')
            clock['now'] += timedelta(minutes=1)
            assert schedule.run_scheduled_backup()['status'] == 'ok'
        assert len(exported) == 1
    finally:
        _drop_backup(app)


def test_a_first_run_killed_is_retried_after_the_lease(app, monkeypatch, tmp_path):
    exported, clock = _killed(app, monkeypatch, tmp_path, last_run=None)
    try:
        with app.app_context():
            clock['now'] = _NOW + _PAST_LEASE
            assert schedule.run_scheduled_backup()['status'] == 'ok'
        assert len(exported) == 1
    finally:
        _drop_backup(app)


def test_an_outcome_lost_once_brings_no_second_archive(app, monkeypatch, tmp_path):
    exported = _backup_schedule(app, monkeypatch, tmp_path, last_run='2026-01-01T00:00:00Z')
    clock = {'now': _NOW}
    monkeypatch.setattr(schedule, 'utc_now', lambda: clock['now'])
    record, failures = schedule._record_outcome, []

    def record_with_a_failing_commit(*a, **k):
        if failures:
            return record(*a, **k)
        failures.append(1)
        with monkeypatch.context() as m:
            m.setattr(db.session, 'commit', lambda: (_ for _ in ()).throw(RuntimeError('db')))
            return record(*a, **k)

    monkeypatch.setattr(schedule, '_record_outcome', record_with_a_failing_commit)
    try:
        with app.app_context():
            assert schedule.run_scheduled_backup()['status'] == 'ok'
            clock['now'] = _NOW + _PAST_LEASE
            assert schedule.run_scheduled_backup() == {'status': 'skipped', 'reason': 'not_due'}
        assert failures == [1] and len(exported) == 1
    finally:
        _drop_backup(app)


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
def test_a_run_killed_during_the_export_is_retried_on_postgresql(app, monkeypatch, tmp_path):
    with _pg(app):
        within, after, exported = _interrupted_then_retried(app, monkeypatch, tmp_path)
    assert within == {'status': 'skipped', 'reason': 'not_due'}
    assert after['status'] == 'ok'
    assert len(exported) == 1


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
def test_an_export_failing_after_a_sql_error_gives_the_slot_back_on_postgresql(
        app, monkeypatch, tmp_path):
    from sqlalchemy import text

    def export(*a, **k):
        # Leaves the PostgreSQL transaction aborted, as a failed export query does
        try:
            db.session.execute(text('SELECT * FROM no_such_table_for_this_test'))
        except Exception:  # noqa: BLE001
            pass
        raise RuntimeError('export failed')

    with _pg(app):
        _backup_schedule(app, monkeypatch, tmp_path, last_run='2026-01-01T00:00:00Z')
        monkeypatch.setattr(schedule.storage, 'export_archive', export)
        with app.app_context():
            with pytest.raises(RuntimeError):
                schedule.run_scheduled_backup()
            db.session.remove()
            assert schedule._get('backup.last_run') == '2026-01-01T00:00:00Z'
            db.session.remove()


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
def test_two_backup_runners_write_one_archive_on_postgresql(app, monkeypatch, tmp_path):
    with _pg(app):
        # A previous run on record: the reservation is the conditional update, not the insert
        exported = _backup_schedule(app, monkeypatch, tmp_path, last_run='2026-01-01T00:00:00Z')
        results = _twice_at_once(app, schedule.run_scheduled_backup,
                                 schedule, 'config_compare_and_set')
    assert len(exported) == 1, results
    assert sorted(r['status'] for r in results) == ['ok', 'skipped']


# ------------------------------------------------------------------ ACME proxy

def _sibling_orders(app):
    """Two local orders sharing one upstream authorization and challenge (#307)."""
    from tests.test_acme_proxy_resolution import _order
    authz = f'https://ca-reserve.example/authz/{uuid.uuid4().hex[:8]}'
    chall = f'{authz}/chall'
    with app.app_context():
        ids = [_order(order_url=f'{authz}/order-{n}', upstream_order_url=f'{authz}/order-{n}',
                      upstream_authz_urls=json.dumps([authz])).id for n in range(2)]
        db.session.remove()
    return ids, authz, chall


def _drop_orders(app, ids):
    with app.app_context():
        AcmeClientOrder.query.filter(AcmeClientOrder.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()
        db.session.remove()


def _mark_both_at_once(app, ids, authz, chall):
    from services.acme.acme_proxy_service import AcmeProxyService
    both, results, errors = threading.Barrier(2, timeout=10), [], []

    def mark(order_id):
        try:
            with app.app_context():
                order = db.session.get(AcmeClientOrder, order_id)
                both.wait()
                results.append(AcmeProxyService._mark_initiated(order, chall, authz))
                db.session.remove()
        except Exception as exc:  # noqa: BLE001
            errors.append(repr(exc))

    threads = [threading.Thread(target=mark, args=(i,)) for i in ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert errors == []
    return results


def test_a_sibling_order_already_initiated_is_not_initiated_again(app):
    from services.acme.acme_proxy_service import AcmeProxyService
    ids, authz, chall = _sibling_orders(app)
    try:
        with app.app_context():
            first, second = (db.session.get(AcmeClientOrder, i) for i in ids)
            svc = AcmeProxyService('https://ucm.example/acme/proxy')
            assert svc._mark_initiated(first, chall, authz) is True
            assert svc._mark_initiated(second, chall, authz) is False
            db.session.remove()
    finally:
        _drop_orders(app, ids)


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
def test_two_nodes_on_sibling_orders_start_one_automation_on_postgresql(app):
    with _pg(app):
        ids, authz, chall = _sibling_orders(app)
        results = _mark_both_at_once(app, ids, authz, chall)
    assert sorted(results) == [False, True]
