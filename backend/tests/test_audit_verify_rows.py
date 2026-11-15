"""The chain verification reads the journal as plain rows: no ORM object per entry,
whatever the size of the journal, and the same verdict as before."""
from sqlalchemy import event

from models import AuditLog, db
from services.audit_service import AuditService


def test_the_verification_loads_no_object_per_entry(app):
    with app.app_context():
        for i in range(30):
            AuditService.log_action(action='verify_rows', resource_type='test', details=f'entry {i}')
        loaded = []
        listener = lambda target, context: loaded.append(target.id)  # noqa: E731
        event.listen(AuditLog, 'load', listener)
        try:
            result = AuditService.verify_integrity()
        finally:
            event.remove(AuditLog, 'load', listener)
        assert result['checked'] >= 30
        assert loaded == []


def test_an_edited_entry_is_still_found(app):
    with app.app_context():
        for i in range(5):
            AuditService.log_action(action='verify_rows_edit', resource_type='test', details=f'entry {i}')
        row = AuditLog.query.filter_by(action='verify_rows_edit').order_by(AuditLog.id.desc()).first()
        row.details = 'rewritten'
        db.session.commit()
        try:
            result = AuditService.verify_integrity()
            assert result['valid'] is False
            assert row.id in [e['id'] for e in result['errors']]
        finally:
            row.details = 'entry 4'
            db.session.commit()
