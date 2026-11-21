"""A restored HTTPS pair is stored for the next start: served after a bound certificate,
before a regenerated pair; outside HA applied once, then the disk is the truth again."""
import json
from pathlib import Path
from collections import defaultdict

import pytest

from services import shared_files
from services.backup.restore_extended import RestoreExtendedMixin

CERT, KEY = 'RESTORED-CERT\n', 'RESTORED-KEY\n'


@pytest.fixture
def clean(app):
    from models import db
    yield
    with app.app_context():
        db.session.rollback()
        for name in (shared_files.HTTPS_GENERATED, shared_files.HTTPS_RESTORED):
            shared_files.drop_file(name)
        db.session.commit()


def _store(name, crt='c', key='k'):
    from models import db
    shared_files.store_file(name, json.dumps({'crt': crt, 'key': key}).encode())
    db.session.commit()


def _stored(name):
    from models import SharedFile, db
    db.session.rollback()
    return db.session.get(SharedFile, name) is not None


def _restore_pair(data):
    from models import db
    RestoreExtendedMixin()._restore_https_files(data, defaultdict(int))
    db.session.commit()


def test_restoring_an_https_pair_stores_it_and_drops_the_regenerated_one(app, clean):
    with app.app_context():
        _store(shared_files.HTTPS_GENERATED)
        _restore_pair({'https_server': {'cert_pem': CERT, 'key_pem': KEY}})
        assert not _stored(shared_files.HTTPS_GENERATED)
        assert json.loads(shared_files.read_file(shared_files.HTTPS_RESTORED)) == {
            'crt': CERT, 'key': KEY}


def test_an_archive_without_an_https_pair_keeps_what_is_stored(app, clean):
    with app.app_context():
        _store(shared_files.HTTPS_GENERATED)
        _restore_pair({})
        assert _stored(shared_files.HTTPS_GENERATED)
        assert not _stored(shared_files.HTTPS_RESTORED)


@pytest.mark.parametrize('half', [{'cert_pem': CERT}, {'key_pem': KEY}])
def test_half_a_pair_is_left_out_with_a_warning(app, clean, half):
    """The export skips a file it cannot read: the rest of such an archive still restores."""
    from types import SimpleNamespace
    from models import db
    plan = SimpleNamespace(warnings=[])
    with app.app_context():
        _store(shared_files.HTTPS_GENERATED)
        results = defaultdict(int)
        RestoreExtendedMixin()._restore_https_files({'https_server': half}, results, plan)
        db.session.commit()
        assert not _stored(shared_files.HTTPS_RESTORED)
        assert _stored(shared_files.HTTPS_GENERATED)
        assert results['https_server'] == 0
        assert len(plan.warnings) == 1 and 'HTTPS' in plan.warnings[0]
        missing, carried = ('key', 'certificate') if 'cert_pem' in half else ('certificate', 'key')
        assert f'its {carried} without its {missing}' in plan.warnings[0]


def test_a_pair_of_two_empty_files_is_said_to_carry_neither(app, clean):
    from types import SimpleNamespace
    plan = SimpleNamespace(warnings=[])
    with app.app_context():
        RestoreExtendedMixin()._restore_https_files(
            {'https_server': {'cert_pem': '', 'key_pem': ''}}, defaultdict(int), plan)
        assert len(plan.warnings) == 1 and 'neither' in plan.warnings[0]
        assert 'without its' not in plan.warnings[0]


class _Database:
    """BootDatabase over the app's own connection."""

    def __init__(self, session):
        self.session = session

    def rows(self, sql, params=()):
        from sqlalchemy import text
        names = {f'p{i}': value for i, value in enumerate(params)}
        for i in range(len(params)):
            sql = sql.replace('?', f':p{i}', 1)
        return self.session.execute(text(sql), names).fetchall()

    def one(self, sql, params=()):
        found = self.rows(sql, params)
        return found[0] if found else None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_the_restored_pair_comes_after_a_bound_certificate_and_before_a_regenerated_one(
        app, clean):
    from boot_config import RESTORED_LABEL, https_material
    from models import db
    with app.app_context():
        _store(shared_files.HTTPS_GENERATED, 'gen-c', 'gen-k')
        assert https_material(_Database(db.session))[:2] == ('gen-c', 'gen-k')
        _store(shared_files.HTTPS_RESTORED, CERT, KEY)
        assert https_material(_Database(db.session)) == (CERT, KEY, RESTORED_LABEL, True)


def _attempt(tmp_path, monkeypatch, error=None, crt=CERT, key=KEY):
    """What this start's master did with the pair, and the files it wrote."""
    from boot_config import _record_restored_attempt
    from config.settings import Config
    monkeypatch.setattr(Config, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(Config, 'HTTPS_CERT_PATH', tmp_path / 'https_cert.pem')
    monkeypatch.setattr(Config, 'HTTPS_KEY_PATH', tmp_path / 'https_key.pem')
    if error is None:
        (tmp_path / 'https_cert.pem').write_text(crt)
        (tmp_path / 'https_key.pem').write_text(key)
    _record_restored_attempt(str(tmp_path), crt, key, error)


def test_outside_ha_the_pair_waits_for_the_master_then_is_consumed(app, clean, tmp_path,
                                                                    monkeypatch):
    from config.settings import Config
    from services.https_binding import settle_restored_https
    monkeypatch.setattr(Config, 'DATA_DIR', tmp_path)
    with app.app_context():
        _store(shared_files.HTTPS_RESTORED, CERT, KEY)
        assert settle_restored_https() == 'pending'
        assert _stored(shared_files.HTTPS_RESTORED)
        _attempt(tmp_path, monkeypatch)
        assert settle_restored_https() == 'applied'
        assert not _stored(shared_files.HTTPS_RESTORED)


def test_outside_ha_a_pair_the_master_could_not_write_is_reported_once(app, clean, tmp_path,
                                                                       monkeypatch, caplog):
    from services.https_binding import settle_restored_https
    with app.app_context():
        _store(shared_files.HTTPS_RESTORED, CERT, KEY)
        _attempt(tmp_path, monkeypatch, error='PermissionError: read-only file system')
        assert settle_restored_https() == 'not applied'
        assert 'read-only file system' in caplog.text
        assert not _stored(shared_files.HTTPS_RESTORED)
        assert settle_restored_https() is None


def test_in_ha_the_pair_stays_for_every_node(app, clean, tmp_path, monkeypatch):
    from services.https_binding import settle_restored_https
    from utils import ha
    with app.app_context():
        _store(shared_files.HTTPS_RESTORED, CERT, KEY)
        _attempt(tmp_path, monkeypatch)
        monkeypatch.setattr(ha, 'ha_enabled', lambda: True)
        assert settle_restored_https() is None
        assert _stored(shared_files.HTTPS_RESTORED)


def test_binding_a_certificate_drops_the_restored_pair(app, clean):
    from services.https_binding import set_bound_refid
    with app.app_context():
        _store(shared_files.HTTPS_RESTORED, CERT, KEY)
        set_bound_refid('some-refid')
        assert not _stored(shared_files.HTTPS_RESTORED)
        set_bound_refid('')


def test_the_master_writes_the_restored_pair_and_records_it(app, clean, tmp_path,
                                                            monkeypatch):
    import boot_config
    from models import db
    with app.app_context():
        _store(shared_files.HTTPS_RESTORED, CERT, KEY)
        database = _Database(db.session)
        monkeypatch.setattr(boot_config, 'open_boot_database', lambda path: database)
        cert, key = tmp_path / 'c.pem', tmp_path / 'k.pem'
        done = boot_config.materialize_https(str(tmp_path), cert, key)
        assert done == f'{boot_config.RESTORED_LABEL} written from the database'
        assert cert.read_text() == CERT and key.read_text() == KEY
        attempt = json.loads((tmp_path / boot_config.HTTPS_RESTORED_ATTEMPT).read_text())
        assert attempt == {'digest': boot_config.restored_pair_digest(CERT, KEY), 'error': None}

        monkeypatch.setattr(boot_config, 'write_https_pair', lambda *a, **k: (_ for _ in ()).throw(
            PermissionError(13, 'Read-only file system')))
        with pytest.raises(PermissionError):
            boot_config.materialize_https(str(tmp_path), cert, key)
        attempt = json.loads((tmp_path / boot_config.HTTPS_RESTORED_ATTEMPT).read_text())
        assert 'Read-only file system' in attempt['error']



def test_regenerating_the_certificate_drops_the_restored_pair(app, auth_client, clean, tmp_path,
                                                               monkeypatch):
    import api.v2.system.https as route
    from config.settings import Config
    monkeypatch.setenv('HTTPS_CERT_PATH', str(tmp_path / 'https_cert.pem'))
    monkeypatch.setenv('HTTPS_KEY_PATH', str(tmp_path / 'https_key.pem'))
    monkeypatch.setattr(Config, 'HA_MODE', False)
    monkeypatch.setattr(route, 'restart_to_serve', lambda: (True, ''))
    with app.app_context():
        _store(shared_files.HTTPS_RESTORED, CERT, KEY)
    r = auth_client.post('/api/v2/system/https/regenerate', json={'common_name': 'regen.test'})
    assert r.status_code == 200, r.data
    with app.app_context():
        assert not _stored(shared_files.HTTPS_RESTORED)


def test_an_archive_written_without_the_https_key_restores_and_says_so(app, clean,
                                                                        monkeypatch):
    """A key file the export could not find: every other section restores, the todo says why
    the HTTPS certificate did not."""
    from config.settings import Config
    from services.backup import manifest
    from services.backup.restore_completion import attach_restore_todo
    from services.backup_service import BackupService
    password = 'Correct-Horse-Battery-436'
    cert_path, key_path = Path(Config.HTTPS_CERT_PATH), Path(Config.HTTPS_KEY_PATH)
    saved = {p: p.read_bytes() for p in (cert_path, key_path) if p.exists()}
    try:
        cert_path.write_text(CERT)
        key_path.unlink(missing_ok=True)
        with app.app_context():
            service = BackupService()
            blob = service.create_backup(password, include={
                n: n == 'groups' for n in manifest.SECTIONS})
            results = service.restore_backup(blob, password)
            attach_restore_todo(results)
            assert not _stored(shared_files.HTTPS_RESTORED)
            assert any('HTTPS certificate of the archive was not restored' in line
                       for line in results['todo']), results['todo']
    finally:
        for path in (cert_path, key_path):
            path.unlink(missing_ok=True)
        for path, content in saved.items():
            path.write_bytes(content)


def test_a_second_restore_of_the_same_pair_waits_for_its_own_attempt(app, clean, tmp_path,
                                                                     monkeypatch):
    """The attempt is settled with the pair: restoring the same archive again after the
    certificate was replaced by hand is not read as already tried."""
    from boot_config import HTTPS_RESTORED_ATTEMPT
    from services.https_binding import settle_restored_https
    with app.app_context():
        _store(shared_files.HTTPS_RESTORED, CERT, KEY)
        _attempt(tmp_path, monkeypatch)
        assert settle_restored_https() == 'applied'
        assert not (tmp_path / HTTPS_RESTORED_ATTEMPT).exists()

        (tmp_path / 'https_cert.pem').write_text('REPLACED BY HAND\n')
        _store(shared_files.HTTPS_RESTORED, CERT, KEY)
        assert settle_restored_https() == 'pending'
        assert _stored(shared_files.HTTPS_RESTORED)
