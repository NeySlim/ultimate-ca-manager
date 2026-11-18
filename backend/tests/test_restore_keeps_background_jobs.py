"""A restore leaves background_jobs as it is, in replacement and in merge, on SQLite and on
PostgreSQL: the table is runtime state, out of the archives, and a restore run as a job
must find its own row afterwards."""
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from models import db
from services.jobs import store
from tests.test_restore_replace_dependents import ENGINES, PASSWORD, _service, _target, _user
from utils.datetime_utils import utc_now

T = store.T


@pytest.fixture(params=ENGINES)
def target(request, app, tmp_path):
    with _target(app, request.param, tmp_path, f'jobs_kept_{uuid.uuid4().hex[:8]}'):
        yield request.param


def _job(slot, now, user):
    return store.create_job(db.session, kind=f'test_{slot}', slot=slot, exclusive=False,
                            exclusive_slots=frozenset(), now=now, params={'n': 1},
                            requester=(user.id, user.username, '192.0.2.7'),
                            file_name=store.file_name_for(str(uuid.uuid4()), '.upload'))


def _rows():
    rows = {r['id']: dict(r) for r in db.session.execute(select(T)).mappings()}
    db.session.rollback()
    return rows


@pytest.mark.parametrize('mode', ['replace', 'merge'])
def test_a_restore_leaves_the_jobs_table_as_it_is(target, mode):
    now = utc_now()
    # A replacement refuses an archive without accounts; the jobs name their requester
    user = _user(f'jobs-kept-{uuid.uuid4().hex[:8]}')
    db.session.commit()
    before_archive = _job('backup', now - timedelta(minutes=5), user)
    blob = _service().create_backup(PASSWORD)
    # After the archive: one job concluded, another taken and running
    assert store.conclude_job(db.session, before_archive, state=store.FAILED,
                              reason=store.NOT_TAKEN, from_states=(store.PENDING,), now=now)
    running = _job('audit_verify', now, user)
    assert store.claim_job(db.session, running, 'node-a/1/x', now) is not None
    expected = _rows()
    assert {before_archive, running} <= set(expected)

    _service().restore_backup(blob, PASSWORD, mode=mode)

    assert _rows() == expected
