"""A syslog change saved by one process reaches the forwarder of another (the scheduler)
without a restart or an HA command, at a bounded cost."""
import uuid

import pytest

from models import db, SystemConfig
from services import syslog_service
from services.syslog_service import SyslogForwarder
from tests.test_syslog_forwarding_scope import _received, collector  # noqa: F401

KEYS = SyslogForwarder.SETTING_KEYS


def _process():
    """An independent forwarder, as the scheduler process holds its own copy."""
    forwarder = object.__new__(SyslogForwarder)
    forwarder._initialize()
    return forwarder


def _entry(tag):
    from types import SimpleNamespace
    return SimpleNamespace(timestamp=None, action=f'xp_{tag}', username='tester', ip_address=None,
                           resource_type='certificate', resource_id=None, resource_name=None,
                           success=True, details=tag)


@pytest.fixture
def stored_syslog(app):
    """Writes the syslog rows as another process would, restored afterwards."""
    with app.app_context():
        saved = {r.key: r.value for r in SystemConfig.query.filter(SystemConfig.key.in_(KEYS))}

    def write(**values):
        with app.app_context():
            for key, value in values.items():
                row = SystemConfig.query.filter_by(key=f'syslog_{key}').first()
                if row is None:
                    db.session.add(SystemConfig(key=f'syslog_{key}', value=value))
                else:
                    row.value = value
            db.session.commit()
    yield write
    with app.app_context():
        for row in SystemConfig.query.filter(SystemConfig.key.in_(KEYS)):
            if row.key in saved:
                row.value = saved[row.key]
            else:
                db.session.delete(row)
        db.session.commit()


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(syslog_service.time, 'monotonic', lambda: now[0])
    return now


def test_a_change_saved_elsewhere_reaches_the_scheduler_copy(app, collector, stored_syslog, clock):
    port = collector.getsockname()[1]
    stored_syslog(enabled='true', host='127.0.0.1', port=str(port), protocol='udp')
    with app.app_context():
        scheduler = _process()
        scheduler.load_from_db()
        run = uuid.uuid4().hex[:8]
        assert scheduler.send(_entry(f'{run}a'))

        stored_syslog(enabled='false')  # saved by the web worker
        clock[0] += syslog_service.REFRESH_SECONDS + 1
        scheduler.reload_if_changed()
        assert not scheduler.is_enabled
        assert not scheduler.send(_entry(f'{run}b'))
        scheduler._close()
    packets = _received(collector)
    assert any(f'xp_{run}a' in p for p in packets), packets
    assert not any(f'xp_{run}b' in p for p in packets), packets


def test_a_forwarder_disabled_at_start_picks_up_an_enabled_target(app, collector, stored_syslog,
                                                                  clock, monkeypatch):
    stored_syslog(enabled='false', host='', port='514', protocol='udp')
    with app.app_context():
        scheduler = _process()
        scheduler.load_from_db()
        monkeypatch.setattr(syslog_service, 'syslog_forwarder', scheduler)
        stored_syslog(enabled='true', host='127.0.0.1', port=str(collector.getsockname()[1]))
        clock[0] += syslog_service.REFRESH_SECONDS + 1
        run = uuid.uuid4().hex[:8]
        from services.audit.staging import forward_to_syslog
        forward_to_syslog(_entry(run))  # the audit path, which skips a disabled forwarder
        scheduler._close()
    assert any(f'xp_{run}' in p for p in _received(collector))


def test_the_stored_settings_are_read_at_most_once_per_interval(app, stored_syslog, clock,
                                                                monkeypatch):
    stored_syslog(enabled='false')
    with app.app_context():
        scheduler = _process()
        scheduler.load_from_db()
        reads = []
        real = scheduler._read_stored
        monkeypatch.setattr(scheduler, '_read_stored', lambda: reads.append(1) or real())
        for _ in range(50):
            scheduler.reload_if_changed()
        assert reads == []
        clock[0] += syslog_service.REFRESH_SECONDS + 1
        for _ in range(50):
            scheduler.reload_if_changed()
        assert len(reads) == 1


def test_an_unchanged_store_leaves_a_local_configuration_alone(app, stored_syslog, clock):
    """Applied only on a change of the rows: the HA reload and the refresh never both reconnect."""
    stored_syslog(enabled='false')
    with app.app_context():
        worker = _process()
        worker.load_from_db()
        worker.configure(enabled=True, host='192.0.2.1', port=514)
        clock[0] += syslog_service.REFRESH_SECONDS + 1
        worker.reload_if_changed()
        assert worker.config['host'] == '192.0.2.1'
        worker.load_from_db()  # the HA command for a change this process already has
        assert worker.config['host'] == '192.0.2.1'


def test_an_unreadable_store_keeps_the_current_target(app, stored_syslog, clock, monkeypatch):
    stored_syslog(enabled='true', host='192.0.2.7', port='514', protocol='udp')
    with app.app_context():
        scheduler = _process()
        scheduler.load_from_db()

        def refused():
            raise RuntimeError('database unreachable')
        monkeypatch.setattr(scheduler, '_read_stored', refused)
        clock[0] += syslog_service.REFRESH_SECONDS + 1
        scheduler.reload_if_changed()
        assert scheduler.is_enabled and scheduler.config['host'] == '192.0.2.7'


def test_the_collector_being_turned_off_still_hears_of_it(app, auth_client, collector,
                                                          stored_syslog):
    """The saving worker logs the change before a refresh can apply it."""
    from services.syslog_service import syslog_forwarder
    from tests.test_syslog_forwarding_scope import _put_syslog
    saved = dict(syslog_forwarder.__dict__)
    try:
        stored_syslog(enabled='true', host='127.0.0.1', port=str(collector.getsockname()[1]),
                      protocol='udp')
        with app.app_context():
            syslog_forwarder.load_from_db()
        syslog_forwarder._checked_at = float('-inf')  # a refresh is due
        r = _put_syslog(auth_client, collector, enabled=False)
        assert r.status_code == 200, r.get_json()
        assert not syslog_forwarder.is_enabled
    finally:
        syslog_forwarder._close()
        syslog_forwarder.__dict__.clear()
        syslog_forwarder.__dict__.update(saved)
        syslog_forwarder._socket = None
    packets = [p for p in _received(collector) if 'syslog_config_updated' in p]
    assert len(packets) == 1 and 'disabled' in packets[0], packets
