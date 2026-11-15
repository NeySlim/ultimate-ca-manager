"""Two key synchronizations of one provider at once: both answer, the second as if run after.

The first one pauses after adding its rows, before its commit; without the provider lock the
second inserts the same key identifiers and its commit breaks uq_hsm_key_provider_identifier.
"""
import json
import os
import threading
import time
import uuid
from unittest.mock import patch

import pytest

from models import db
from models.hsm import HsmKey, HsmProvider
from services.hsm.base_provider import HsmKeyInfo

_PG_URL = os.environ.get('UCM_TEST_PG_URL')
PAUSE = 1.5


class _Token:
    def __init__(self, keys):
        self.keys = keys

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def list_keys(self):
        return list(self.keys)


def _provider(app):
    tag = uuid.uuid4().hex[:8]
    with app.app_context():
        provider = HsmProvider(type='pkcs11', name=f'sync-race-{tag}',
                               config=json.dumps({'module_path': '/opt/vendor/lib/libvendor.so'}))
        db.session.add(provider)
        db.session.commit()
        pid = provider.id
        db.session.remove()
    keys = [HsmKeyInfo(key_identifier=f'k{i}-{tag}', label=f'k{i}-{tag}', algorithm='EC-P256',
                       key_type='asymmetric', purpose='signing') for i in range(3)]
    return pid, keys


def _race(app, provider_id, keys):
    """Two syncs of *provider_id*, the first pausing before its commit; outcomes and a later sync."""
    from services.hsm import HsmService
    paused, outcome = threading.Event(), {}
    real_referenced = HsmService._referenced_hsm_key_ids

    def referenced():
        ids = real_referenced()
        if threading.current_thread().name == 'first':
            paused.set()
            time.sleep(PAUSE)
        return ids

    def run(name):
        with app.app_context():
            if name == 'second':
                paused.wait(10)
            try:
                outcome[name] = ('ok', HsmService.sync_keys(provider_id))
            except Exception as e:  # noqa: BLE001 - the outcome is what the test reads
                db.session.rollback()
                outcome[name] = ('error', repr(e))
            db.session.remove()

    with patch.object(HsmService, '_get_provider_instance', return_value=_Token(keys)), \
            patch.object(HsmService, '_referenced_hsm_key_ids', side_effect=referenced):
        threads = [threading.Thread(target=run, name=n, args=(n,)) for n in ('first', 'second')]
        for t in threads:
            t.start()
        for t in threads:
            t.join(60)
    with patch.object(HsmService, '_get_provider_instance', return_value=_Token(keys)), app.app_context():
        after = HsmService.sync_keys(provider_id)
        rows = HsmKey.query.filter_by(provider_id=provider_id).count()
        db.session.remove()
    return outcome, after, rows


def _assert_serialized(outcome, after, rows):
    assert outcome['first'] == ('ok', {**after, 'added': 3, 'unchanged': 0}), outcome
    assert outcome['second'] == ('ok', after), outcome
    assert after['added'] == 0 and after['unchanged'] == 3 and rows == 3


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
def test_two_syncs_of_one_provider_at_once_on_postgresql(app):
    from tests.test_backup_cross_installation import _bound_to
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own

    with _a_schema_of_our_own(f'hsm_sync_race_{uuid.uuid4().hex[:6]}') as url, \
            _bound_to(app, url, is_postgresql=True):
        pid, keys = _provider(app)
        _assert_serialized(*_race(app, pid, keys))


def test_two_syncs_of_one_provider_at_once_on_sqlite(app, tmp_path):
    from tests.test_backup_cross_installation import _bound_to

    with _bound_to(app, f"sqlite:///{tmp_path / 'sync-race.db'}"):
        pid, keys = _provider(app)
        _assert_serialized(*_race(app, pid, keys))


def _updated_at_after_a_sync(app):
    from datetime import datetime
    from services.hsm import HsmService
    pid, keys = _provider(app)
    stamp = datetime(2020, 1, 1)
    with app.app_context():
        HsmProvider.query.filter_by(id=pid).update({'updated_at': stamp})
        db.session.commit()
        with patch.object(HsmService, '_get_provider_instance', return_value=_Token(keys)):
            HsmService.sync_keys(pid)
        found = db.session.get(HsmProvider, pid).updated_at
        db.session.remove()
    return found, stamp


def test_a_sync_leaves_the_provider_date_alone_on_sqlite(app, tmp_path):
    from tests.test_backup_cross_installation import _bound_to

    with _bound_to(app, f"sqlite:///{tmp_path / 'sync-date.db'}"):
        found, stamp = _updated_at_after_a_sync(app)
    assert found == stamp


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
def test_a_sync_leaves_the_provider_date_alone_on_postgresql(app):
    from tests.test_backup_cross_installation import _bound_to
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own

    with _a_schema_of_our_own(f'hsm_sync_date_{uuid.uuid4().hex[:6]}') as url, \
            _bound_to(app, url, is_postgresql=True):
        found, stamp = _updated_at_after_a_sync(app)
    assert found == stamp
