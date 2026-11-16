"""The reconciliation: the managed directories follow the rows, and touch nothing else.

Written only where a row names a file; removed only from the list a restore wrote;
never through a symbolic link; the mode and owner of a replaced file kept; never
while another reconciliation holds the directories, nor when the lock cannot be taken.
"""
import base64
import errno
import os
import stat
import uuid
from pathlib import Path

import pytest

from tests.fresh_app import fresh_app_fixtures

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()


@pytest.fixture
def regen():
    from services import file_regen_service
    return file_regen_service


@pytest.fixture
def writes(monkeypatch, regen):
    done = []
    real = regen._replace

    def counted(directory, name, data, previous, default_mode, durable=False):
        real(directory, name, data, previous, default_mode, durable)
        if name != regen.MARKER_NAME:
            done.append(name)

    monkeypatch.setattr(regen, '_replace', counted)
    return done


@pytest.fixture
def issued(app, create_cert):
    """One certificate, its row and its file, the directories reconciled."""
    from models import Certificate, db
    from services.file_regen_service import reconcile_files
    from utils.file_naming import cert_cert_path, cert_key_path
    made = create_cert(cn=f'reconcile-{uuid.uuid4().hex[:8]}.example.com')
    with app.app_context():
        reconcile_files(full=True)
        row = db.session.get(Certificate, made['id'])
        return {'id': row.id, 'crt': cert_cert_path(row), 'key': cert_key_path(row),
                'pem': base64.b64decode(row.crt)}


def _behind(regen):
    """A restore committed elsewhere: the generation moves, every node is behind."""
    from models import db
    regen.advance_generation()
    db.session.commit()


def test_a_reconciled_disk_gets_no_write(app, issued, writes, regen):
    with app.app_context():
        assert regen.reconcile_files(full=True)['status'] == 'done'
        assert regen.reconcile_if_behind()['status'] == 'current'
        assert writes == []


def test_an_ordinary_start_only_writes_what_is_absent(app, issued, writes, regen):
    with app.app_context():
        issued['crt'].write_bytes(b'changed by an operator')
        issued['key'].unlink()
        regen.reconcile_files()
        assert writes == [issued['key'].name]
        assert issued['crt'].read_bytes() == b'changed by an operator'


def test_a_node_behind_rewrites_a_file_that_differs_keeping_its_mode_and_owner(
        app, issued, writes, regen):
    with app.app_context():
        issued['crt'].write_bytes(b'stale')
        os.chmod(issued['crt'], 0o640)
        owner = (65534, 65534) if os.geteuid() == 0 else (os.geteuid(), os.getegid())
        os.chown(issued['crt'], *owner)
        _behind(regen)
        regen.reconcile_files()
        st = os.stat(issued['crt'])
        assert issued['crt'].read_bytes() == issued['pem']
        assert stat.S_IMODE(st.st_mode) == 0o640 and (st.st_uid, st.st_gid) == owner
        assert writes == [issued['crt'].name]


def test_an_owner_that_cannot_be_kept_leaves_the_file_as_it_was(app, issued, regen,
                                                              monkeypatch):
    with app.app_context():
        issued['crt'].write_bytes(b'owned by another account')
        before = os.stat(issued['crt'])
        monkeypatch.setattr(os, 'geteuid', lambda: before.st_uid + 1)
        monkeypatch.setattr(os, 'fchown', lambda *a: (_ for _ in ()).throw(
            PermissionError(errno.EPERM, 'Operation not permitted')))
        _behind(regen)
        stats = regen.reconcile_files()
        assert stats['failed'] == 1 and stats['status'] == 'incomplete'
        assert issued['crt'].read_bytes() == b'owned by another account'
        assert [p.name for p in issued['crt'].parent.iterdir()
                if p.name.startswith('.ucm-files-') and p.name.endswith('.tmp')] == []


def test_a_link_at_the_path_of_a_row_is_never_followed(app, issued, regen, tmp_path):
    with app.app_context():
        outside = tmp_path / 'outside.pem'
        outside.write_bytes(b'not ours')
        os.chmod(outside, 0o600)
        issued['crt'].unlink()
        issued['crt'].symlink_to(outside)
        _behind(regen)
        stats = regen.reconcile_files()
        assert stats['refused'] == 1
        assert issued['crt'].is_symlink()
        assert outside.read_bytes() == b'not ours'
        assert stat.S_IMODE(os.stat(outside).st_mode) == 0o600


def test_only_listed_regular_files_inside_the_directories_are_removed(app, issued, regen,
                                                                     tmp_path):
    from config.settings import Config
    from models import FileRemoval, db
    with app.app_context():
        outside = tmp_path / 'outside.crt'
        outside.write_bytes(b'not in a managed directory')
        target = tmp_path / 'link-target'
        target.write_bytes(b'kept')
        link = Config.CERT_DIR / f'listed-link-{uuid.uuid4().hex[:6]}.crt'
        link.symlink_to(target)
        listed = Config.CERT_DIR / f'listed-{uuid.uuid4().hex[:6]}.crt'
        listed.write_bytes(b'a row a restore removed')
        lookalike = Config.CERT_DIR / f'{listed.stem}-copy.crt'
        lookalike.write_bytes(b'an operator file named like ours')
        generation = regen.advance_generation()
        for path in (outside, link, listed, Config.CERT_DIR / 'never-there.crt'):
            db.session.add(FileRemoval(generation=generation, path=str(path)))
        db.session.commit()
        stats = regen.reconcile_files()
        assert stats['status'] == 'done' and stats['removed'] == 1
        assert not listed.exists()
        assert link.is_symlink() and target.read_bytes() == b'kept'
        assert outside.exists() and lookalike.exists()


def test_the_lock_never_fails_open(app, issued, writes, regen, monkeypatch):
    import fcntl
    with app.app_context():
        issued['crt'].unlink()
        monkeypatch.setattr(fcntl, 'flock', lambda *a: (_ for _ in ()).throw(
            OSError(errno.ENOLCK, 'No locks available')))
        assert regen.reconcile_files(full=True) == {'status': 'busy'}
        assert writes == [] and not issued['crt'].exists()


def test_a_reconciliation_already_running_is_left_alone(app, issued, writes, regen):
    import fcntl
    from config.settings import Config
    with app.app_context():
        issued['crt'].unlink()
        holder = os.open(Path(Config.DATA_DIR) / regen.LOCK_NAME, os.O_RDWR | os.O_CREAT)
        # Another process's lock: a second descriptor of our own conflicts with it too
        fcntl.flock(holder, fcntl.LOCK_EX)
        try:
            assert regen.reconcile_files(full=True) == {'status': 'busy'}
        finally:
            os.close(holder)
        assert writes == [] and not issued['crt'].exists()


def test_a_stale_reconciliation_never_leaves_the_old_files_under_the_new_marker(
        app, issued, regen, monkeypatch):
    """Rows read at G1, a restore to G2 then reconciled in full, the G1 writes land after."""
    from models import Certificate, db
    with app.app_context():
        other = Certificate.query.filter(Certificate.id != issued['id'],
                                         Certificate.crt.isnot(None)).first()
        issued['crt'].write_bytes(b'stale')
        _behind(regen)
        g1 = regen.current_generation()
        real = regen._replace
        nested = []

        def restore_meanwhile(directory, name, data, *args, **kwargs):
            if name == issued['crt'].name and not nested:
                nested.append(True)
                row = db.session.get(Certificate, issued['id'])
                row.crt = other.crt
                regen.advance_generation()
                db.session.commit()
                regen.reconcile_files(full=True)    # G2, done while the G1 pass is paused
            return real(directory, name, data, *args, **kwargs)

        monkeypatch.setattr(regen, '_replace', restore_meanwhile)
        regen.reconcile_files()
        monkeypatch.setattr(regen, '_replace', real)
        g2 = regen.current_generation()
        assert regen.generation_number(g2) == regen.generation_number(g1) + 1
        fd = os.open(issued['crt'].parent, os.O_RDONLY)
        try:
            marker = regen._read_marker(fd)
        finally:
            os.close(fd)
        wanted = base64.b64decode(other.crt)
        assert marker != g2 or issued['crt'].read_bytes() == wanted
        regen.reconcile_if_behind()
        assert issued['crt'].read_bytes() == wanted


def test_a_renewal_between_the_read_and_the_rename_wins(app, issued, regen, monkeypatch):
    from models import Certificate, db
    with app.app_context():
        other = Certificate.query.filter(Certificate.id != issued['id'],
                                         Certificate.crt.isnot(None)).first()
        renewed = base64.b64decode(other.crt)
        issued['crt'].write_bytes(b'stale')
        _behind(regen)
        real = regen._replace
        done = []

        def renewal_meanwhile(directory, name, data, *args, **kwargs):
            if name == issued['crt'].name and not done:
                done.append(True)
                row = db.session.get(Certificate, issued['id'])
                row.crt = other.crt
                db.session.commit()                       # the renewal commits,
                issued['crt'].write_bytes(renewed)        # then writes its file
            return real(directory, name, data, *args, **kwargs)

        monkeypatch.setattr(regen, '_replace', renewal_meanwhile)
        regen.reconcile_files()
        assert done and issued['crt'].read_bytes() == renewed


def test_a_key_mirror_whose_row_holds_no_key_is_never_removed(app, issued, regen):
    from models import Certificate, db
    with app.app_context():
        row = db.session.get(Certificate, issued['id'])
        generation = regen.advance_generation()
        regen.record_removal_candidates(generation)
        row.prv = None
        regen.keep_named_paths()
        db.session.commit()
        assert issued['key'].exists()
        regen.reconcile_files()
        assert issued['key'].exists(), 'the only copy of a key went with its row'


def test_the_files_task_runs_on_every_node(app):
    from services.scheduler_service import get_scheduler
    task = get_scheduler().tasks['files_reconcile']
    assert task.per_node and task.interval == 60


def test_an_unreadable_marker_means_a_full_pass(app, issued, writes, regen):
    with app.app_context():
        regen.reconcile_files(full=True)
        issued['crt'].write_bytes(b'differs from the row')
        (issued['crt'].parent / regen.MARKER_NAME).write_bytes(b'\xff\xfe truncated')
        assert regen.reconcile_if_behind()['status'] == 'done'
        assert issued['crt'].read_bytes() == issued['pem']


def test_a_listed_path_a_row_names_again_is_kept_by_a_full_pass(app, issued, regen):
    """A row recreated on a path a restore listed (same refid): no later pass removes it."""
    from models import FileRemoval, db
    with app.app_context():
        generation = regen.advance_generation()
        db.session.add(FileRemoval(generation=generation, path=str(issued['crt'])))
        db.session.commit()
        stats = regen.reconcile_files()
        assert stats['full'] and stats['removed'] == 0
        assert issued['crt'].read_bytes() == issued['pem']
        assert FileRemoval.query.filter_by(path=str(issued['crt'])).count() == 0


def test_a_key_mirror_whose_row_holds_an_empty_key_is_never_removed(app, issued, regen):
    from models import Certificate, db
    with app.app_context():
        row = db.session.get(Certificate, issued['id'])
        row.prv = ''
        db.session.commit()
        issued['key'].write_bytes(b'an operator copy of the key')
        generation = regen.advance_generation()
        regen.record_removal_candidates(generation)
        db.session.delete(row)
        regen.keep_named_paths()
        db.session.commit()
        regen.reconcile_files()
        assert issued['key'].read_bytes() == b'an operator copy of the key'


@pytest.fixture
def empty_authority(app):
    """A CA row whose certificate and key are '' (no content), with operator files at its
    paths; the row and the files are removed after the test."""
    from models import CA, db
    from utils.file_naming import ca_cert_path, ca_key_path
    with app.app_context():
        ca = CA(refid=str(uuid.uuid4()), descr=f'empty-{uuid.uuid4().hex[:8]}',
                subject='CN=empty authority', crt='', prv='')
        db.session.add(ca)
        db.session.commit()
        paths = {'id': ca.id, 'crt': ca_cert_path(ca), 'key': ca_key_path(ca)}
    for name in ('crt', 'key'):
        paths[name].parent.mkdir(parents=True, exist_ok=True)
        paths[name].write_bytes(f'operator {name}'.encode())
    yield paths
    for name in ('crt', 'key'):
        paths[name].unlink(missing_ok=True)
    with app.app_context():
        CA.query.filter_by(id=paths['id']).delete()
        db.session.commit()


def test_an_authority_restored_away_without_content_leaves_its_paths_alone(
        app, empty_authority, regen):
    """'' is no content: its paths are not listed, so the files there are not the restore's."""
    from models import CA, db
    with app.app_context():
        generation = regen.advance_generation()
        regen.record_removal_candidates(generation)
        db.session.delete(db.session.get(CA, empty_authority['id']))
        regen.keep_named_paths()
        db.session.commit()
        regen.reconcile_files()
    assert empty_authority['crt'].read_bytes() == b'operator crt'
    assert empty_authority['key'].read_bytes() == b'operator key'


def test_the_purge_keeps_the_key_copy_of_an_authority_whose_key_is_empty(
        app, empty_authority, regen, encryption_enabled):
    with app.app_context():
        stats = regen.purge_private_key_files()
    assert empty_authority['key'].read_bytes() == b'operator key'
    assert stats['kept_no_db_key'] >= 1


def test_a_full_pass_with_nothing_listed_reads_no_row_to_strike(app, issued, regen,
                                                                 monkeypatch):
    """Striking reads every row's paths: only worth it when the list holds something."""
    from models import FileRemoval, db
    struck = []
    real = regen.keep_named_paths
    monkeypatch.setattr(regen, 'keep_named_paths', lambda: struck.append(1) or real())
    with app.app_context():
        FileRemoval.query.delete()
        db.session.commit()
        assert regen.reconcile_files(full=True)['status'] == 'done'
        assert struck == []
        db.session.add(FileRemoval(generation=1, path=str(issued['crt'])))
        db.session.commit()
        assert regen.reconcile_files(full=True)['status'] == 'done'
        assert struck == [1] and issued['crt'].exists()
