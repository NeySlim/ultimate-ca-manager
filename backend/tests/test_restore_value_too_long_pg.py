"""A value longer than its column is refused on PostgreSQL with the row it is in.

SQLite stores it; PostgreSQL raised StringDataRightTruncation from the flush and
the route answered 500 without naming the table, the row or the column.
"""
import os
import uuid

import pytest

from models import User, db
from services.backup.restore.conflict import RestoreConflictError
from tests.test_backup_restore_failfast import _reseal
from tests.test_restore_replace_dependents import PASSWORD, _only, _service, _target

_PG_URL = os.environ.get('UCM_TEST_PG_URL')

pytestmark = [pytest.mark.postgres,
              pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')]


@pytest.fixture
def postgresql(app, tmp_path):
    with _target(app, 'postgresql', tmp_path, f'too_long_{uuid.uuid4().hex[:12]}'):
        yield


def test_the_refusal_names_the_row_and_the_column(postgresql):
    db.session.add(User(username='lot7-long', email='lot7@example.test', role='viewer',
                        password_hash='x', full_name='short'))
    db.session.commit()
    svc = _service()
    blob = svc.create_backup(PASSWORD, include=_only('users'))
    _key, data = svc._decrypt_framed(blob, PASSWORD)
    row = next(r for r in data['users'] if r['username'] == 'lot7-long')
    row['full_name'] = 'x' * 300

    with pytest.raises(RestoreConflictError) as refusal:
        svc.restore_backup(_reseal(blob, data), PASSWORD, mode='merge')

    message = str(refusal.value)
    assert "table 'users'" in message and 'username=lot7-long' in message
    assert 'full_name is 300 characters long, the column holds 255' in message
    db.session.rollback()
    assert User.query.filter_by(username='lot7-long').one().full_name == 'short'
