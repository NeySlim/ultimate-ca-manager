"""An audit entry is kept whatever the length of its free-text fields, on
SQLite and on PostgreSQL (run with UCM_TEST_APP_PG_URL for the latter)."""
import json
import logging
import uuid

from models import AuditLog, db
from models.rbac import CustomRole
from services.audit_service import AuditService


def test_long_user_agent_keeps_the_entry_of_the_real_route(app, auth_client):
    name = f'ua-{uuid.uuid4().hex[:8]}'
    agent = 'probe/' + 'x' * 294
    r = auth_client.post('/api/v2/rbac/roles', content_type='application/json',
                         headers={'User-Agent': agent},
                         data=json.dumps({'name': name, 'permissions': ['read:certificates']}))
    assert r.status_code in (200, 201), r.get_json()
    with app.app_context():
        try:
            entries = AuditLog.query.filter(AuditLog.resource_type == 'rbac_role',
                                            AuditLog.details.contains(name)).all()
            assert len(entries) == 1
            assert entries[0].user_agent == agent
        finally:
            CustomRole.query.filter_by(name=name).delete()
            db.session.commit()


def test_long_resource_id_keeps_the_entry(app):
    ids = ','.join(str(1000 + i) for i in range(30))
    assert len(ids) == 149
    with app.app_context():
        entry = AuditService.log_action('oversized_probe', resource_type='certificate',
                                        resource_id=ids, resource_name='n' * 300,
                                        username='u' * 120)
        assert entry is not None
        stored = db.session.get(AuditLog, entry.id)
        assert stored.resource_id == ids
        assert stored.resource_name == 'n' * 300
        assert stored.username == 'u' * 120
        assert AuditService.verify_integrity(start_id=entry.id)['valid']


def test_fields_past_the_guard_are_cut_and_the_full_ids_kept_in_details(app):
    ids = ','.join(str(i) for i in range(2000))
    with app.app_context():
        entry = AuditService.log_action('a' * 150, resource_type='r' * 80,
                                        resource_id=ids, details='bulk')
        assert entry is not None
        stored = db.session.get(AuditLog, entry.id)
        assert len(stored.action) == AuditLog.__table__.c.action.type.length
        assert len(stored.resource_type) == AuditLog.__table__.c.resource_type.type.length
        assert ids.startswith(stored.resource_id) and len(stored.resource_id) < len(ids)
        assert ids in stored.details
        assert AuditService.verify_integrity(start_id=entry.id)['valid']


def test_an_entry_that_cannot_be_written_goes_to_the_log_and_syslog(app, monkeypatch, caplog):
    from services.syslog_service import syslog_forwarder
    sent = []
    monkeypatch.setattr(type(syslog_forwarder), 'is_enabled', property(lambda self: True))
    monkeypatch.setattr(syslog_forwarder, 'send', lambda entry: sent.append(entry) or True)
    real_commit = db.session.commit
    calls = []

    def failing_commit():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError('database refused the row')
        return real_commit()

    with app.app_context():
        monkeypatch.setattr(db.session, 'commit', failing_commit)
        with caplog.at_level(logging.ERROR):
            AuditService.log_action('unwritable_probe', resource_type='system', details='lost?')
        monkeypatch.setattr(db.session, 'commit', real_commit)
    assert any(r.levelno == logging.ERROR and 'unwritable_probe' in r.getMessage()
               for r in caplog.records)
    assert [e.action for e in sent] == ['unwritable_probe']
