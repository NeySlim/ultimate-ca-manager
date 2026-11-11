"""A scheduled run executed twice (two nodes during a leader change) acts once.

Scheduled reports and the scheduled backup reserve their slot by compare-and-set on
``system_config`` before sending or writing; the ACME proxy starts one dns-01 automation
per upstream challenge even when two sibling orders are served by two nodes at once.
"""
import json
import os
import threading
import uuid
from datetime import datetime

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
