"""An HSM key attached while a key synchronization of its provider adds the same key (#458).

The sync pauses after adding its rows, before its commit; without the provider lock the attachment
inserts the same key identifier and breaks uq_hsm_key_provider_identifier.
"""
import os
import threading
import time
import uuid
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from models import CA, db
from models.hsm import HsmKey, HsmProvider
from tests.test_ca_hsm_key_attach import _keyless_ca, _Token

_PG_URL = os.environ.get('UCM_TEST_PG_URL')
PAUSE = 1.5


def _race(app):
    from services.hsm import HsmService
    from services.hsm.ca_key_attach import attach
    key = ec.generate_private_key(ec.SECP256R1())
    ca_id, _ = _keyless_ca(app, key, f'Attach Race CA {uuid.uuid4().hex[:6]}')
    with app.app_context():
        provider = HsmProvider(type='pkcs11', name=f'attach-race-{uuid.uuid4().hex[:8]}', config='{}')
        db.session.add(provider)
        db.session.commit()
        provider_id = provider.id
        db.session.remove()
    token = _Token({'ours': key})
    paused, outcome = threading.Event(), {}
    real_referenced = HsmService._referenced_hsm_key_ids

    def referenced():
        ids = real_referenced()
        if threading.current_thread().name == 'sync':
            paused.set()
            time.sleep(PAUSE)
        return ids

    def run(name):
        with app.app_context():
            try:
                if name == 'sync':
                    outcome[name] = ('ok', HsmService.sync_keys(provider_id)['added'])
                else:
                    paused.wait(10)
                    ca, row = attach(ca_id, provider_id, 'ours')
                    outcome[name] = ('ok', ca.hsm_key_id == row.id)
            except Exception as e:  # noqa: BLE001 - the outcome is what the test reads
                db.session.rollback()
                outcome[name] = ('error', repr(e))
            db.session.remove()

    with patch.object(HsmService, '_get_provider_instance', return_value=token), \
            patch.object(HsmService, '_referenced_hsm_key_ids', side_effect=referenced):
        threads = [threading.Thread(target=run, name=n, args=(n,)) for n in ('sync', 'attach')]
        for t in threads:
            t.start()
        for t in threads:
            t.join(60)
    with app.app_context():
        rows = HsmKey.query.filter_by(provider_id=provider_id).count()
        bound = db.session.get(CA, ca_id).hsm_key_id
        db.session.remove()
    return outcome, rows, bound


def _assert_serialized(outcome, rows, bound):
    assert outcome == {'sync': ('ok', 1), 'attach': ('ok', True)}, outcome
    assert rows == 1 and bound is not None


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
def test_an_attachment_during_a_sync_of_its_provider_on_postgresql(app):
    from tests.test_backup_cross_installation import _bound_to
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own

    with _a_schema_of_our_own(f'hsm_attach_race_{uuid.uuid4().hex[:6]}') as url, \
            _bound_to(app, url, is_postgresql=True):
        _assert_serialized(*_race(app))


def test_an_attachment_during_a_sync_of_its_provider_on_sqlite(app, tmp_path):
    from tests.test_backup_cross_installation import _bound_to

    with _bound_to(app, f"sqlite:///{tmp_path / 'attach-race.db'}"):
        _assert_serialized(*_race(app))
