"""A restore killed at any step: a start then a reconciliation give the files the rows name.

A restore writes no file: its rows commit with a new files generation and the
list of paths they no longer name, and `reconcile_files` makes the disk follow.
A kill is an exception no handler catches (BaseException), the connection's
uncommitted work then gone; a commit whose outcome is unknown is a commit that
raises after, or instead of, reaching the database.
"""
import base64
import os
import uuid
import stat
from pathlib import Path

import pytest

from tests.fresh_app import fresh_app_fixtures

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()

PASSWORD = 'Killed-Restore-Pass-53'


class Killed(BaseException):
    """What `kill -9` looks like from inside: nothing after this point runs."""


def _tree(*roots):
    """Every entry under the roots: bytes and mode of a file, target of a link."""
    seen = {}
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        for path in sorted(root.rglob('*')):
            st = os.lstat(path)
            if stat.S_ISLNK(st.st_mode):
                seen[str(path)] = ('link', os.readlink(path))
            elif stat.S_ISREG(st.st_mode):
                seen[str(path)] = (path.read_bytes(), stat.S_IMODE(st.st_mode))
    return seen


def _managed():
    from config.settings import Config
    return (Config.CA_DIR, Config.CERT_DIR, Config.PRIVATE_DIR)


def _expected():
    """What the rows say the managed directories hold (keys mirrored: encryption is off)."""
    from models import CA, Certificate
    from utils.file_naming import ca_cert_path, ca_key_path, cert_cert_path, cert_key_path
    from utils.key_codec import load_pem_bytes
    files = {}
    for ca in CA.query.all():
        files[str(ca_cert_path(ca))] = base64.b64decode(ca.crt)
        if ca.prv:
            files[str(ca_key_path(ca))] = load_pem_bytes(ca.prv)
    for cert in Certificate.query.all():
        if cert.crt:
            files[str(cert_cert_path(cert))] = base64.b64decode(cert.crt)
        if cert.prv:
            files[str(cert_key_path(cert))] = load_pem_bytes(cert.prv)
    return files


def _app_files():
    """The managed files, without the reconciliation's markers and ids."""
    from services.file_regen_service import DIR_ID_NAME, MARKER_NAME
    return {path: entry[0] for path, entry in _tree(*_managed()).items()
            if Path(path).name not in (MARKER_NAME, DIR_ID_NAME) and entry[0] != 'link'}


@pytest.fixture
def writes(monkeypatch):
    """Every file the reconciliation renames into place, by path."""
    from services import file_regen_service as regen
    done = []
    real = regen._replace

    def counted(directory, name, data, previous, default_mode, durable=False):
        real(directory, name, data, previous, default_mode, durable)
        if name != regen.MARKER_NAME:
            done.append(str(directory.path / name))

    monkeypatch.setattr(regen, '_replace', counted)
    return done


@pytest.fixture
def diverged(app, create_ca, create_cert, tmp_path):
    """An archive; then the database moved on: C1 holds another certificate, C3 and C4
    were added (C4 without a key, beside an operator's copy), operator files sit beside."""
    from config.settings import Config
    from models import Certificate, db
    from services.backup_service import BackupService
    from utils.file_naming import cert_cert_path, cert_key_path
    tag = uuid.uuid4().hex[:6]
    ca = create_ca(cn=f'Killed Restore CA {tag}')
    first = create_cert(cn=f'killed-restore-1-{tag}.example.com', ca_id=ca['id'])
    other = create_cert(cn=f'killed-restore-2-{tag}.example.com', ca_id=ca['id'])
    with app.app_context():
        from services.file_regen_service import reconcile_files
        reconcile_files(full=True)
        archive = tmp_path / 'archive.ucmbkp'
        archive.write_bytes(b''.join(BackupService().iter_backup(PASSWORD, kdf='pbkdf2')))
    added = create_cert(cn=f'killed-restore-3-{tag}.example.com', ca_id=ca['id'])
    keyless = create_cert(cn=f'killed-restore-4-{tag}.example.com', ca_id=ca['id'])
    with app.app_context():
        row = db.session.get(Certificate, first['id'])
        archived_pem = base64.b64decode(row.crt)
        row.crt = db.session.get(Certificate, other['id']).crt
        no_key = db.session.get(Certificate, keyless['id'])
        no_key.prv = None
        db.session.commit()
        path = cert_cert_path(row)
        path.write_bytes(base64.b64decode(row.crt))
        operator_key = cert_key_path(no_key)
        operator_key.write_bytes(b'an operator copy of a key the row does not hold')
        lookalike = Config.CERT_DIR / f'killed-restore-1-{tag}.example.com-{row.refid[:7]}x.crt'
        lookalike.write_bytes(b'an operator file named like ours')
        outside = tmp_path / 'outside-secret'
        outside.write_bytes(b'outside the managed directories')
        os.chmod(outside, 0o600)
        (Config.CERT_DIR / f'a-link-{tag}.crt').symlink_to(outside)
        added_path = cert_cert_path(db.session.get(Certificate, added['id']))
        assert added_path.exists()
        return {'archive': archive, 'refid': row.refid, 'path': path, 'archived': archived_pem,
                'added': added_path, 'operator_key': operator_key, 'lookalike': lookalike,
                'outside': outside}


def _database_pem(refid):
    from models import Certificate
    return base64.b64decode(Certificate.query.filter_by(refid=refid).one().crt)


def _restore(archive):
    from services.backup_service import BackupService
    return BackupService().restore_backup_from_path(archive, PASSWORD, mode='replace')


def _converges(writes, case):
    """A start, then: the disk is what the rows name, operator files kept, and a
    second reconciliation writes nothing."""
    from services.file_regen_service import reconcile_files
    reconcile_files()
    expected = _expected()
    found = _app_files()
    for path, data in expected.items():
        assert found.get(path) == data, path
    assert not case['added'].exists() or str(case['added']) in expected
    assert case['operator_key'].read_bytes() == b'an operator copy of a key the row does not hold'
    assert case['lookalike'].read_bytes() == b'an operator file named like ours'
    assert case['outside'].read_bytes() == b'outside the managed directories'
    assert stat.S_IMODE(os.stat(case['outside']).st_mode) == 0o600
    del writes[:]
    reconcile_files()
    reconcile_files(full=True)
    assert writes == []


def test_killed_before_the_commit_the_disk_has_not_moved(app, diverged, writes, monkeypatch):
    from models import db
    from services import cluster_maintenance
    with app.app_context():
        before = _database_pem(diverged['refid'])
        tree = _tree(app.config['DATA_DIR'], diverged['outside'].parent)
        monkeypatch.setattr(cluster_maintenance, 'before_restore_commit',
                            lambda session: (_ for _ in ()).throw(Killed()))
        with pytest.raises(Killed):
            _restore(diverged['archive'])
        db.session.rollback()    # the connection dies with the process
        monkeypatch.undo()
        assert _tree(app.config['DATA_DIR'], diverged['outside'].parent) == tree
        assert _database_pem(diverged['refid']) == before
        _converges(writes, diverged)
        assert diverged['path'].read_bytes() == before
        assert diverged['added'].exists()


def test_killed_after_the_commit_before_any_write_the_start_writes_them(app, diverged, writes):
    with app.app_context():
        tree = _tree(app.config['DATA_DIR'])
        _restore(diverged['archive'])    # the process dies here: nothing after the commit runs
        assert _tree(app.config['DATA_DIR']) == tree, 'the restore wrote to the disk'
        assert _database_pem(diverged['refid']) == diverged['archived']
        _converges(writes, diverged)
        assert diverged['path'].read_bytes() == diverged['archived']
        assert not diverged['added'].exists(), 'the file of a row the restore removed stayed'


@pytest.mark.parametrize('after_writes', [0, 1, 3])
def test_killed_in_the_middle_of_the_reconciliation(app, diverged, writes, monkeypatch,
                                                    after_writes):
    from services import file_regen_service as regen
    with app.app_context():
        _restore(diverged['archive'])
        for path in _expected():    # a node whose directories are empty: several writes
            if Path(path) != diverged['path']:
                Path(path).unlink(missing_ok=True)
        counted = regen._replace

        def dies(*args, **kwargs):
            if len(writes) >= after_writes:
                raise Killed()
            return counted(*args, **kwargs)

        monkeypatch.setattr(regen, '_replace', dies)
        with pytest.raises(Killed):
            regen.reconcile_files()
        monkeypatch.setattr(regen, '_replace', counted)
        _converges(writes, diverged)
        assert diverged['path'].read_bytes() == diverged['archived']


def test_killed_before_the_marker_the_next_start_does_it_again(app, diverged, writes,
                                                               monkeypatch):
    from services import file_regen_service as regen
    with app.app_context():
        _restore(diverged['archive'])
        with monkeypatch.context() as patched:
            patched.setattr(regen, '_write_marker', lambda *a: (_ for _ in ()).throw(Killed()))
            with pytest.raises(Killed):
                regen.reconcile_files()
        assert diverged['path'].read_bytes() == diverged['archived']
        diverged['path'].write_bytes(b'changed by hand before the marker was written')
        _converges(writes, diverged)
        assert diverged['path'].read_bytes() == diverged['archived']


def _commit_outcome(monkeypatch, *, reaches_the_database):
    """The restore's own commit raises: after the database has it, or instead."""
    from sqlalchemy.orm import Session
    real_commit = Session.commit
    raised = []

    def commit(self):
        if not raised and self.info.pop('restore_commit', False):
            raised.append(True)
            if reaches_the_database:
                real_commit(self)
            raise RuntimeError('connection lost while committing')
        return real_commit(self)

    monkeypatch.setattr(Session, 'commit', commit)
    return raised


@pytest.mark.parametrize('reaches_the_database', [True, False])
def test_a_commit_whose_outcome_is_unknown_still_ends_as_the_database_says(
        app, diverged, writes, monkeypatch, reaches_the_database):
    from models import db
    from services import cluster_maintenance
    with app.app_context():
        before = _database_pem(diverged['refid'])
        tree = _tree(app.config['DATA_DIR'])
        raised = _commit_outcome(monkeypatch, reaches_the_database=reaches_the_database)
        real_before = cluster_maintenance.before_restore_commit

        def mark(session):
            real_before(session)
            session.info['restore_commit'] = True

        monkeypatch.setattr(cluster_maintenance, 'before_restore_commit', mark)
        with pytest.raises(RuntimeError, match='connection lost'):
            _restore(diverged['archive'])
        monkeypatch.undo()
        db.session.rollback()
        assert raised == [True]
        assert _tree(app.config['DATA_DIR']) == tree, 'a restore that raised moved files'
        assert _database_pem(diverged['refid']) == (
            diverged['archived'] if reaches_the_database else before)
        _converges(writes, diverged)
        assert diverged['path'].read_bytes() == _database_pem(diverged['refid'])


def test_two_restores_without_a_reconciliation_between_reach_the_last(app, diverged, writes):
    from services.file_regen_service import current_generation, generation_number
    with app.app_context():
        start = generation_number(current_generation())
        _restore(diverged['archive'])
        _restore(diverged['archive'])
        assert generation_number(current_generation()) == start + 2
        _converges(writes, diverged)
        assert not diverged['added'].exists()


def test_a_file_that_cannot_be_written_after_the_commit_is_retried(app, diverged, writes,
                                                                   monkeypatch):
    from services import file_regen_service as regen
    with app.app_context():
        _restore(diverged['archive'])
        counted = regen._replace

        def refused(directory, name, *args, **kwargs):
            if name == diverged['path'].name:
                raise OSError(28, 'No space left on device')
            return counted(directory, name, *args, **kwargs)

        monkeypatch.setattr(regen, '_replace', refused)
        stats = regen.reconcile_files()
        assert stats['status'] == 'incomplete' and stats['failed'] == 1
        monkeypatch.setattr(regen, '_replace', counted)
        assert regen.reconcile_if_behind()['status'] == 'waiting', 'retried at once, not later'
        regen._RETRY['after'] = 0.0
        assert regen.reconcile_if_behind()['status'] == 'done'
        _converges(writes, diverged)
        assert diverged['path'].read_bytes() == diverged['archived']


def test_a_restore_leaves_its_generation_and_its_list_and_nothing_on_disk(app, diverged):
    from models import FileRemoval
    from services.file_regen_service import current_generation, generation_number, reconcile_files
    with app.app_context():
        tree = _tree(app.config['DATA_DIR'])
        results = _restore(diverged['archive'])
        assert _tree(app.config['DATA_DIR']) == tree
        generation = generation_number(current_generation())
        listed = {row.path for row in FileRemoval.query.filter_by(generation=generation)}
        assert str(diverged['added']) in listed
        assert str(diverged['operator_key']) not in listed, 'a key the row does not hold'
        assert str(diverged['lookalike']) not in listed
        assert results['files'] == {'generation': generation, 'removals': len(listed)}
        reconcile_files()
        assert FileRemoval.query.count() == 0, 'a single node consumes the list'


def test_a_restore_is_refused_when_a_directory_cannot_be_written(app, diverged, monkeypatch):
    from config.settings import Config
    from services.backup.errors import RestoreFilesUnwritable
    real_access = os.access
    with app.app_context():
        before = _database_pem(diverged['refid'])
        tree = _tree(app.config['DATA_DIR'])
        monkeypatch.setattr(os, 'access', lambda path, mode: False if Path(path) == Path(
            Config.PRIVATE_DIR) else real_access(path, mode))
        with pytest.raises(RestoreFilesUnwritable, match='private'):
            _restore(diverged['archive'])
        assert _database_pem(diverged['refid']) == before
        assert _tree(app.config['DATA_DIR']) == tree
