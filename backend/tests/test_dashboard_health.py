"""GET /api/v2/dashboard/health: per protocol, one ok/failed entry per UTC day,
each protocol saying what it measures; the scheduler from its published state."""
import json
import time
import uuid
from datetime import timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from models import Certificate, db
from models.audit_log import AuditLog
from models.scep import SCEPRequest
from services import scheduler_service
from tests.conftest import get_json
from tests.dashboard_pem import self_signed
from utils.datetime_utils import utc_now

URL = '/api/v2/dashboard/health'
USER = 'dashboard-health-test'


def _health(client, days=7):
    r = client.get(f'{URL}?days={days}')
    assert r.status_code == 200, r.data
    return get_json(r)['data']


def _by_date(periods):
    return {p['date']: (p['ok'], p['failed']) for p in periods}


def _delta(before, after):
    b, a = _by_date(before), _by_date(after)
    return {d: (a[d][0] - b[d][0], a[d][1] - b[d][1]) for d in a if a[d] != b[d]}


@pytest.mark.parametrize('days', ['0', '31', '-1', 'x', '7.5'])
def test_days_out_of_bounds_is_refused(auth_client, days):
    assert auth_client.get(f'{URL}?days={days}').status_code == 400


@pytest.mark.parametrize('days', [1, 7, 30])
def test_series_have_one_entry_per_day(auth_client, days):
    data = _health(auth_client, days)
    today = utc_now().date()
    expected = [(today - timedelta(days=days - 1 - i)).isoformat() for i in range(days)]
    for name in ('acme', 'scep', 'est'):
        periods = data['protocols'][name]['periods']
        assert [p['date'] for p in periods] == expected
        assert all(isinstance(p['ok'], int) and isinstance(p['failed'], int) for p in periods)
    assert data['protocols']['scheduler']['periods'] is None


@pytest.fixture
def events(app):
    """Audit, SCEP and EST rows at known times, removed afterwards."""
    now = utc_now()
    times = {'ok': now - timedelta(seconds=30), 'old_fail': now - timedelta(days=2),
             'outside': now - timedelta(days=10), 'last': now - timedelta(seconds=5)}
    with app.app_context():
        audit = [
            AuditLog(username=USER, action='acme.order.create', success=True, timestamp=times['ok']),
            AuditLog(username=USER, action='acme.order.finalize', success=True, timestamp=times['ok']),
            AuditLog(username=USER, action='acme.order.finalize', success=False, timestamp=times['old_fail']),
            AuditLog(username=USER, action='acme.challenge.respond', success=False, timestamp=times['outside']),
            AuditLog(username=USER, action='acme.order.create', success=False, timestamp=times['last']),
            AuditLog(username=USER, action='est_serverkeygen_denied', success=False, timestamp=times['old_fail']),
            # the underscore of est_ is literal: estimate_* is not EST
            AuditLog(username=USER, action='estimate_refresh', success=False, timestamp=times['old_fail']),
            AuditLog(username=USER, action='acmeX', success=False, timestamp=times['old_fail']),
        ]
        scep = [SCEPRequest(transaction_id=f'health-{uuid.uuid4()}', csr='-', status=s, created_at=t)
                for s, t in (('approved', times['ok']), ('rejected', times['old_fail']),
                             ('pending', times['ok']), ('approved', times['last']))]
        est = Certificate(refid=str(uuid.uuid4()), descr='health-est', source='est', created_at=times['last'],
                          crt=self_signed(ec.generate_private_key(ec.SECP256R1())))
        db.session.add_all(audit + scep + [est])
        db.session.commit()
        ids = {'scep': [r.id for r in scep], 'est': est.id}
    yield times
    with app.app_context():
        AuditLog.query.filter_by(username=USER).delete()
        SCEPRequest.query.filter(SCEPRequest.id.in_(ids['scep'])).delete(synchronize_session=False)
        db.session.delete(db.session.get(Certificate, ids['est']))
        db.session.commit()


@pytest.fixture
def baseline(app, auth_client):
    return _health(auth_client)['protocols']


def _day(t):
    return t.date().isoformat()


def _expected(*entries):
    out = {}
    for t, ok, failed in entries:
        o, f = out.get(_day(t), (0, 0))
        out[_day(t)] = (o + ok, f + failed)
    return out


def test_acme_counts_its_audit_entries(auth_client, baseline, events):
    acme = _health(auth_client)['protocols']['acme']
    assert acme['basis'] == 'audit'
    assert _delta(baseline['acme']['periods'], acme['periods']) == _expected(
        (events['ok'], 2, 0), (events['old_fail'], 0, 1), (events['last'], 0, 1))
    assert acme['last_status'] == 'failed'
    assert acme['last_operation_at'].startswith(events['last'].isoformat()[:19])


def test_scep_counts_its_requests(auth_client, baseline, events):
    scep = _health(auth_client)['protocols']['scep']
    assert scep['basis'] == 'requests'
    assert _delta(baseline['scep']['periods'], scep['periods']) == _expected(
        (events['ok'], 1, 0), (events['old_fail'], 0, 1), (events['last'], 1, 0))
    assert scep['last_status'] == 'ok'


def test_est_counts_issued_certificates_and_audited_failures(auth_client, baseline, events):
    est = _health(auth_client)['protocols']['est']
    assert (est['basis'], est['failed_basis']) == ('issued', 'audit')
    assert _delta(baseline['est']['periods'], est['periods']) == _expected(
        (events['last'], 1, 0), (events['old_fail'], 0, 1))
    assert est['last_status'] == 'ok'


def test_a_window_reaches_older_days(auth_client, events):
    days = _by_date(_health(auth_client, 30)['protocols']['acme']['periods'])
    assert days[_day(events['outside'])][1] >= 1


def test_scheduler_reads_the_published_state(app, auth_client, monkeypatch, tmp_path):
    names = list(scheduler_service.get_scheduler().tasks)
    monkeypatch.setenv(scheduler_service.SUPERVISED_ENV, '1')
    monkeypatch.setattr(scheduler_service, '_data_path', lambda name: str(tmp_path / name))

    def publish(published_at):
        tasks = {names[0]: {'last_status': 'ok', 'last_run': '2026-01-01T10:00:00Z'},
                 names[1]: {'last_status': 'failed', 'last_run': '2026-01-01T11:00:00Z', 'last_error': 'x'}}
        (tmp_path / scheduler_service.STATE_FILE).write_text(
            json.dumps({'pid': 1, 'published_at': published_at, 'tasks': tasks}))

    publish(time.time())
    sched = _health(auth_client)['protocols']['scheduler']
    assert sched['basis'] == 'scheduler' and sched['tasks'] == len(names)
    assert sched['by_status']['ok'] == 1 and sched['by_status']['failed'] == 1
    assert sum(sched['by_status'].values()) == len(names)
    assert (sched['last_status'], sched['last_operation_at']) == ('failed', '2026-01-01T11:00:00Z')
    assert sched['stale'] is False
    publish(time.time() - 3600)
    assert _health(auth_client)['protocols']['scheduler']['stale'] is True


def test_requires_auth(client):
    assert client.get(URL).status_code == 401
