"""Policy notification dedup against a real database of each backend: only a
sent or in-flight mail holds back a repeat, and creation times keep their
microseconds (they tell a reused id apart)."""
import os
from contextlib import contextmanager
from datetime import datetime

import pytest

from models import db
from models.email_notification import NotificationLog
from models.policy import ApprovalRequest, CertificatePolicy
from services import policy_notifications
from tests.test_backup_cross_installation import _bound_to
from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own

_PG_URL = os.environ.get('UCM_TEST_PG_URL')
KIND, KEY = policy_notifications.VIOLATION, '7:dedup'


@contextmanager
def _database(backend, tmp_path):
    if backend == 'sqlite':
        yield f"sqlite:///{tmp_path / 'notify.db'}"
    else:
        with _a_schema_of_our_own('policy_notify_dedup') as url:
            yield url


@pytest.fixture(params=[
    'sqlite',
    pytest.param('postgresql', marks=[
        pytest.mark.postgres,
        pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')]),
])
def database(app, request, tmp_path):
    with _database(request.param, tmp_path) as url, \
            _bound_to(app, url, is_postgresql=request.param == 'postgresql'):
        with app.app_context():
            assert db.engine.dialect.name == request.param
            yield
            db.session.remove()


def _log(status):
    db.session.add(NotificationLog(type=KIND, recipient='pki@example.test', status=status,
                                   resource_type='policy', resource_id=KEY))
    db.session.commit()


def _claim():
    return policy_notifications._claim_in_db(KIND, KEY, 'pki@example.test')


def test_a_failed_mail_does_not_hold_back_a_new_attempt(database):
    _log('failed')
    assert not policy_notifications._recently_logged(KIND, KEY)
    assert _claim() is not None


def test_a_mail_in_flight_holds_back_a_second_one(database):
    assert _claim() is not None
    assert policy_notifications._recently_logged(KIND, KEY)
    assert _claim() is None


def test_a_sent_mail_holds_back_a_repeat(database):
    _log('sent')
    assert policy_notifications._recently_logged(KIND, KEY)
    assert _claim() is None


def test_creation_times_keep_their_microseconds(database):
    born = datetime(2026, 10, 20, 9, 30, 15, 123456)
    pol = CertificatePolicy(name='notify-born', rules='{}', created_at=born)
    db.session.add(pol)
    db.session.flush()
    approval = ApprovalRequest(request_type='certificate', policy_id=pol.id, created_at=born)
    db.session.add(approval)
    db.session.commit()
    ids = pol.id, approval.id
    db.session.remove()
    assert db.session.get(CertificatePolicy, ids[0]).created_at == born
    assert db.session.get(ApprovalRequest, ids[1]).created_at == born
