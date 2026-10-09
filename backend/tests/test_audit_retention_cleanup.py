"""Audit retention is opt-in and stored; the purge removes the oldest rows as a
contiguous prefix of the hash chain, in batches.

The rows under test take negative ids so they sit in front of everything the
shared session database already holds, as old history would."""
import json
from datetime import timedelta

import pytest

from models import AuditLog, SystemConfig, db
from services import retention_service
from services.audit_service import AuditService
from services.retention_service import RetentionPolicy, scheduled_audit_cleanup
from utils.datetime_utils import utc_now


def _row(row_id, age_days):
    db.session.add(AuditLog(id=row_id, username='retention-test',
                            action='retention_test',
                            timestamp=utc_now() - timedelta(days=age_days)))
    db.session.commit()


def _alive(ids):
    return {i for (i,) in db.session.query(AuditLog.id).filter(AuditLog.id.in_(ids))}


@pytest.fixture
def history(app):
    """Clean slate for the policy and the test rows, before and after."""
    def reset():
        AuditLog.query.filter(AuditLog.id < 0).delete(synchronize_session=False)
        SystemConfig.query.filter_by(key=RetentionPolicy.CONFIG_KEY).delete()
        AuditLog.query.filter_by(action='audit_cleanup', username='system').delete()
        db.session.commit()
    with app.app_context():
        reset()
        yield
        reset()


def test_nothing_is_purged_until_a_retention_is_chosen(app, history):
    with app.app_context():
        _row(-1, 4000)
        scheduled_audit_cleanup()
        assert _alive([-1]) == {-1}
        assert RetentionPolicy.get_settings()['auto_cleanup'] is False


def test_the_purge_removes_the_old_prefix_in_batches(app, history, monkeypatch):
    monkeypatch.setattr(retention_service, 'CLEANUP_BATCH_SIZE', 2)
    with app.app_context():
        for i in range(-5, 0):
            _row(i, 400)
        RetentionPolicy.update_settings(retention_days=365)
        before = db.session.query(db.func.count(AuditLog.id)).filter(AuditLog.id > 0).scalar()
        commits = []
        real_commit = db.session.commit
        monkeypatch.setattr(db.session, 'commit', lambda: commits.append(1) or real_commit())

        result = retention_service.cleanup_audit_logs()

        assert result['deleted'] == 5, result
        assert len(commits) == 3  # 2 + 2 + 1
        assert _alive(range(-5, 0)) == set()
        after = db.session.query(db.func.count(AuditLog.id)).filter(AuditLog.id > 0).scalar()
        assert after == before
        assert AuditService.verify_integrity()['valid']


def test_the_scheduled_purge_leaves_an_audit_entry(app, history):
    with app.app_context():
        _row(-1, 400)
        RetentionPolicy.update_settings(retention_days=365)
        scheduled_audit_cleanup()
        assert _alive([-1]) == set()
        entry = AuditLog.query.filter_by(action='audit_cleanup', username='system').one()
        assert 'Deleted 1 audit logs' in entry.details


def test_an_old_row_behind_a_recent_one_waits(app, history):
    """Only a prefix goes: removing a row from the middle would break the chain."""
    with app.app_context():
        _row(-3, 400)
        _row(-2, 1)
        _row(-1, 400)
        RetentionPolicy.update_settings(retention_days=365)
        result = retention_service.cleanup_audit_logs()
        assert 'error' not in result, result
        assert _alive([-3, -2, -1]) == {-2, -1}


def test_the_settings_screen_stores_the_retention(app, auth_client, history):
    r = auth_client.patch('/api/v2/settings/general', data=json.dumps(
        {'audit_retention_days': 3}), content_type='application/json')
    assert r.status_code == 400
    r = auth_client.patch('/api/v2/settings/general', data=json.dumps(
        {'audit_retention_days': 400}), content_type='application/json')
    assert r.status_code == 200, r.get_json()
    data = auth_client.get('/api/v2/settings/general').get_json()['data']
    assert data['audit_retention_days'] == 400
    with app.app_context():
        assert RetentionPolicy.get_retention_days() == 400


def test_unsupported_or_unsafe_requests_are_refused(auth_client, history):
    r = auth_client.put('/api/v2/system/audit/retention', data=json.dumps(
        {'archive_before_delete': True}), content_type='application/json')
    assert r.status_code == 400
    r = auth_client.post('/api/v2/system/audit/cleanup', data=json.dumps(
        {'retention_days': 0}), content_type='application/json')
    assert r.status_code == 400


def test_a_failed_purge_is_reported_as_failed(app, history, monkeypatch):
    def boom(cutoff):
        raise RuntimeError('purge exploded')
    monkeypatch.setattr(retention_service, '_purge_boundary', boom)
    with app.app_context():
        _row(-1, 400)
        RetentionPolicy.update_settings(retention_days=365)
        before = RetentionPolicy.get_settings()['last_cleanup']
        assert scheduled_audit_cleanup() == {'status': 'failed', 'reason': 'purge exploded'}
        assert RetentionPolicy.get_settings()['last_cleanup'] == before


def test_the_error_names_the_field_that_was_sent(auth_client, history):
    r = auth_client.patch('/api/v2/settings/general', data=json.dumps(
        {'audit_retention_days': 3}), content_type='application/json')
    assert 'audit_retention_days must be between 7 and 1825' in r.get_data(as_text=True)


def test_an_operator_cannot_change_the_retention(app, history, create_user):
    create_user(username='retention-operator', password='Operator-Pass-123!', role='operator')
    client = app.test_client()
    login = client.post('/api/v2/auth/login', json={'username': 'retention-operator',
                                                    'password': 'Operator-Pass-123!'})
    assert login.status_code == 200, login.get_json()
    r = client.patch('/api/v2/settings/general', data=json.dumps(
        {'audit_retention_days': 400}), content_type='application/json')
    assert r.status_code == 403
    with app.app_context():
        assert RetentionPolicy.get_retention_days() == 0
