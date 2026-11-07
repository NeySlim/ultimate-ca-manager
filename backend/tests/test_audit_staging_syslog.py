"""A staged audit entry reaches syslog once the outermost transaction commits,
with the configured system name, and only if its own savepoint was kept."""
import uuid

import pytest

from models import db, SystemConfig
from services.audit.staging import stage_audit_entry
from services.syslog_service import syslog_forwarder
from tests.test_syslog_forwarding_scope import _received, collector, forwarding  # noqa: F401


def _stage(tag):
    assert stage_audit_entry(action=f'stg_{tag}', resource_type='certificate',
                             username='tester', details=tag) is not None


def _actions(sock, run):
    return sorted(a for a in run if any(f'stg_{a}' in p for p in _received(sock)))


def test_a_rolled_back_savepoint_keeps_the_entries_staged_before_it(app, collector, forwarding):
    run = uuid.uuid4().hex[:8]
    with app.app_context():
        _stage(f'{run}a')
        sp = db.session.begin_nested()
        _stage(f'{run}b')
        sp.rollback()
        db.session.commit()
    packets = _received(collector)
    assert any(f'stg_{run}a' in p for p in packets), packets
    assert not any(f'stg_{run}b' in p for p in packets), packets


def test_a_released_savepoint_waits_for_the_outer_commit(app, collector, forwarding):
    run = uuid.uuid4().hex[:8]
    with app.app_context():
        _stage(f'{run}a')
        with db.session.begin_nested():
            _stage(f'{run}b')
        assert not any(run in p for p in _received(collector))
        db.session.rollback()
        db.session.commit()
    assert not any(run in p for p in _received(collector))


@pytest.fixture
def system_name(app):
    with app.app_context():
        row = SystemConfig.query.filter_by(key='system_name').first()
        previous = row.value if row else None
        if row is None:
            row = SystemConfig(key='system_name', value='')
            db.session.add(row)
        row.value = 'stagedhost'
        db.session.commit()
    yield 'stagedhost'
    with app.app_context():
        row = SystemConfig.query.filter_by(key='system_name').first()
        if previous is None:
            db.session.delete(row)
        else:
            row.value = previous
        db.session.commit()


def test_a_staged_entry_carries_the_system_name(app, collector, forwarding, system_name):
    run = uuid.uuid4().hex[:8]
    with app.app_context():
        _stage(run)
        syslog_forwarder._hostname, syslog_forwarder._hostname_resolved_at = '', 0.0
        db.session.commit()
    packets = [p for p in _received(collector) if f'stg_{run}' in p]
    assert len(packets) == 1 and f' {system_name} UCM ' in packets[0], packets


def test_a_failed_name_lookup_is_not_cached(app, forwarding, system_name, monkeypatch):
    with app.app_context():
        syslog_forwarder._hostname, syslog_forwarder._hostname_resolved_at = '', 0.0

        class Broken:
            def filter_by(self, **kw):
                raise RuntimeError('no SQL here')
        monkeypatch.setattr(SystemConfig, 'query', Broken())
        assert syslog_forwarder._resolve_hostname() != system_name
        monkeypatch.undo()
        assert syslog_forwarder._resolve_hostname() == system_name


def test_an_entry_staged_before_a_close_is_never_sent(app, collector, forwarding):
    run = uuid.uuid4().hex[:8]
    with app.app_context():
        _stage(f'{run}ghost')
        db.session.close()
        _stage(f'{run}kept')
        db.session.commit()
    packets = _received(collector)
    assert any(f'stg_{run}kept' in p for p in packets), packets
    assert not any(f'stg_{run}ghost' in p for p in packets), packets
