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


def _self_signed(key, like):
    from datetime import timedelta
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    builder = (x509.CertificateBuilder().subject_name(like.subject).issuer_name(like.subject)
               .public_key(key.public_key()).serial_number(x509.random_serial_number())
               .not_valid_before(like.not_valid_before_utc).not_valid_after(like.not_valid_after_utc + timedelta(days=1)))
    for ext in like.extensions:
        builder = builder.add_extension(ext.value, ext.critical)
    return builder.sign(key, hashes.SHA256())


def _import_over_an_attachment(app, with_key):
    """A CA re-imported after an HSM key was attached by another session to the copy the import had read.

    With its key, the import replaces the HSM key; without it, a re-keyed certificate must not keep it."""
    from services.hsm.ca_key_attach import attach
    from services.import_service import ImportConflict, extract_cert_info, update_ca_from_import
    from cryptography.hazmat.primitives import serialization
    key = ec.generate_private_key(ec.SECP256R1())
    cn = f'Import Race CA {uuid.uuid4().hex[:6]}'
    ca_id, old_cert = _keyless_ca(app, key, cn)
    new_key = key if with_key else ec.generate_private_key(ec.SECP256R1())
    new_cert = _self_signed(new_key, old_cert)
    with app.app_context():
        provider = HsmProvider(type='pkcs11', name=f'import-race-{uuid.uuid4().hex[:8]}', config='{}')
        db.session.add(provider)
        db.session.commit()
        provider_id = provider.id
        db.session.remove()
    outcome = {}
    with patch('services.hsm.HsmService._get_provider_instance', return_value=_Token({'ours': key})), \
            app.app_context():
        existing = db.session.get(CA, ca_id)
        assert existing.hsm_key_id is None

        def other_session():
            with app.app_context():
                outcome['attached'] = attach(ca_id, provider_id, 'ours')[0].hsm_key_id
                db.session.remove()
        worker = threading.Thread(target=other_session)
        worker.start()
        worker.join(60)
        pem = new_cert.public_bytes(serialization.Encoding.PEM)
        key_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption()) if with_key else None
        try:
            update_ca_from_import(existing, new_cert, pem, extract_cert_info(new_cert),
                                  key_pem=key_pem, encrypted_prv='stored-key' if with_key else None)
            db.session.commit()
            outcome['import'] = 'ok'
        except ImportConflict:
            db.session.rollback()
            outcome['import'] = 'conflict'
        db.session.remove()
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        outcome['stored'] = (ca.prv, ca.hsm_key_id)
        db.session.remove()
    return outcome


def _assert_coherent(outcome, with_key):
    assert outcome['attached'] is not None, outcome
    if with_key:
        assert outcome['import'] == 'ok' and outcome['stored'] == ('stored-key', None), outcome
    else:
        assert outcome['import'] == 'conflict' and outcome['stored'] == (None, outcome['attached']), outcome


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
@pytest.mark.parametrize('with_key', [True, False])
def test_an_import_over_an_attachment_on_postgresql(app, with_key):
    from tests.test_backup_cross_installation import _bound_to
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own

    with _a_schema_of_our_own(f'hsm_import_race_{uuid.uuid4().hex[:6]}') as url, \
            _bound_to(app, url, is_postgresql=True):
        _assert_coherent(_import_over_an_attachment(app, with_key), with_key)


@pytest.mark.parametrize('with_key', [True, False])
def test_an_import_over_an_attachment_on_sqlite(app, tmp_path, with_key):
    from tests.test_backup_cross_installation import _bound_to

    with _bound_to(app, f"sqlite:///{tmp_path / 'import-race.db'}"):
        _assert_coherent(_import_over_an_attachment(app, with_key), with_key)


def _import_over_a_deletion(app):
    """A CA re-imported after its row was deleted under the copy the import had read: refused, nothing written."""
    from sqlalchemy import delete
    from services.import_service import ImportConflict, extract_cert_info, update_ca_from_import
    from cryptography.hazmat.primitives import serialization
    key = ec.generate_private_key(ec.SECP256R1())
    ca_id, old_cert = _keyless_ca(app, key, f'Import Gone CA {uuid.uuid4().hex[:6]}')
    new_cert = _self_signed(key, old_cert)
    with app.app_context():
        existing = db.session.get(CA, ca_id)
        db.session.execute(delete(CA.__table__).where(CA.__table__.c.id == ca_id))
        with pytest.raises(ImportConflict, match='deleted'):
            update_ca_from_import(existing, new_cert, new_cert.public_bytes(serialization.Encoding.PEM),
                                  extract_cert_info(new_cert))
        db.session.rollback()
        db.session.remove()


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
def test_an_import_over_a_deleted_ca_on_postgresql(app):
    from tests.test_backup_cross_installation import _bound_to
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own

    with _a_schema_of_our_own(f'hsm_import_gone_{uuid.uuid4().hex[:6]}') as url, \
            _bound_to(app, url, is_postgresql=True):
        _import_over_a_deletion(app)


def test_an_import_over_a_deleted_ca_on_sqlite(app, tmp_path):
    from tests.test_backup_cross_installation import _bound_to

    with _bound_to(app, f"sqlite:///{tmp_path / 'import-gone.db'}"):
        _import_over_a_deletion(app)
