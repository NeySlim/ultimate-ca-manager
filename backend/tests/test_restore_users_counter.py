"""A restore that brings back user ids another installation handed out moves the counter above them."""
import json

import pytest
from sqlalchemy import text

from models import db
from tests.fresh_app import fresh_app_fixtures

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()

PASSWORD = 'Correct-Horse-Battery-9'
FOREIGN_ID = 7000


def _service():
    from services.backup_service import BackupService
    return BackupService()


def _only(*names):
    from services.backup import manifest
    return {name: name in names for name in manifest.SECTIONS}


def _plant_audit():
    db.session.execute(text(
        "INSERT INTO audit_logs (action, resource_type, resource_id, details, timestamp) "
        f"VALUES ('zzcounter-audit', 'user', '{FOREIGN_ID}', 'deleted elsewhere', '2026-01-01 00:00:00')"))


def _plant_approval():
    db.session.execute(text(
        "INSERT INTO approval_requests (request_type, status, approvals, created_at) "
        "VALUES ('certificate', 'approved', :a, '2026-01-01 00:00:00')"),
        {'a': json.dumps([{'user_id': FOREIGN_ID, 'decision': 'approve'}])})


def _unplant():
    db.session.execute(text("DELETE FROM audit_logs WHERE action = 'zzcounter-audit'"))
    db.session.execute(text("DELETE FROM approval_requests WHERE approvals LIKE :p"),
                       {'p': f'%{FOREIGN_ID}%'})
    db.session.commit()


@pytest.mark.parametrize('section,plant', [('audit_logs', _plant_audit),
                                          ('approval_requests', _plant_approval)])
def test_the_next_account_gets_an_id_above_the_restored_ones(app, create_user, section, plant):
    from models import User
    made = []
    with app.app_context():
        plant()
        db.session.commit()
        blob = _service().create_backup(PASSWORD, include=_only(section))
        _unplant()
        try:
            _service().restore_backup(blob, PASSWORD, mode='merge')
            user = create_user(username=f'counter_{section}', role='viewer')
            made.append(user['id'])
            assert user['id'] > FOREIGN_ID
        finally:
            _unplant()
            for user_id in made:
                row = db.session.get(User, user_id)
                if row is not None:
                    db.session.delete(row)
            db.session.commit()
