"""archive-leftovers.sh: a 3.0 package installed over what a removed UCM left archives it, or nothing.

Everything runs in a temporary root: the data, configuration, archive and log paths are
arguments, and the commands that move files can be wrapped to fail at any call.
"""
import hashlib
import os
import pathlib
import shutil
import sqlite3
import stat
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'packaging' / 'scripts' / 'archive-leftovers.sh'
POSIX_SH = shutil.which('dash') or '/bin/sh'
STAMP = '20261114T120000Z'
SECRET = 'f00dfeedf00dfeedf00dfeedf00dfeed'
REAL = {name: shutil.which(name) for name in ('mv', 'cp', 'rm', 'mkdir', 'chmod', 'stat')}


def _pivot_registry(missing=None):
    sys.path.insert(0, str(ROOT / 'backend'))
    from migrations._from_2_254 import PIVOT_NAMES
    return sorted(set(PIVOT_NAMES) - {missing})


def _database(path, registry):
    conn = sqlite3.connect(path)
    conn.execute('CREATE TABLE users (id INTEGER PRIMARY KEY)')
    conn.execute('CREATE TABLE _migrations (id INTEGER PRIMARY KEY, name TEXT UNIQUE)')
    conn.executemany('INSERT INTO _migrations (name) VALUES (?)', [(n,) for n in registry])
    conn.commit()
    conn.close()


class Box:
    """A removed 2.253 left /opt/ucm/data and /etc/ucm; the 3.0 package is unpacked beside them."""

    def __init__(self, tmp_path, registry='short', python='real'):
        self.tmp = tmp_path
        self.home = tmp_path / 'opt' / 'ucm'
        self.data = self.home / 'data'
        self.config = tmp_path / 'etc' / 'ucm'
        self.parent = tmp_path / 'opt' / 'ucm-archive'
        self.log = tmp_path / 'var' / 'log' / 'ucm' / 'leftover-archive.log'
        self.bin = tmp_path / 'bin'
        self.inner = tmp_path / 'inner'
        self.state = tmp_path / 'state'
        for d in (self.home / 'venv' / 'bin', self.config, self.bin, self.state):
            d.mkdir(parents=True)
        (self.home / 'VERSION').write_text('3.0\n')
        os.symlink(ROOT / 'backend', self.home / 'backend')
        self.python(python)
        for d in ('ca', 'certs', 'private', 'crl', 'scep', 'backups', 'sessions'):
            (self.data / d).mkdir(parents=True)
        if registry:
            _database(self.data / 'ucm.db', _pivot_registry('136_lifted_hold_leftovers')
                      if registry == 'short' else _pivot_registry())
        (self.data / 'ca' / 'root.key').write_bytes(b'-----BEGIN PRIVATE KEY-----\nAAAA\n')
        (self.data / 'private' / 'leaf.key').write_bytes(os.urandom(512))
        (self.data / 'backups' / 'ucm-2026.ucmbkp').write_bytes(os.urandom(2048))
        (self.data / 'sessions' / 'abc').write_text('session')
        (self.data / 'https_key.pem').write_text('key')
        (self.data / '.update_result.json').write_text('{}')
        (self.data / 'updates' / 'nested').mkdir(parents=True)
        (self.data / 'updates' / 'nested' / 'f').write_text('x')
        os.symlink('ca/root.key', self.data / 'current.key')
        (self.data / 'private' / 'leaf.key').chmod(0o600)
        os.utime(self.data / 'ca' / 'root.key', (1_000_000_000, 1_000_000_000))
        (self.config / 'ucm.env').write_text(
            f'SECRET_KEY={SECRET}\nDATABASE_PATH={self.data}/ucm.db\nDATA_DIR={self.data}\n')
        (self.config / 'master.key').write_bytes(os.urandom(32))

    def python(self, kind, code=4, first=None):
        """'real' runs the 3.0 runner; else a stub that answers *code*."""
        exe = self.home / 'venv' / 'bin' / 'python'
        if kind == 'real':
            body = f'exec {sys.executable} "$@"'
        elif kind == 'missing':
            exe.unlink(missing_ok=True)
            return
        else:
            line = first or f'sqlite {self.data}/ucm.db'
            reason = ('This database names 1 migration(s) this release does not know.' if code == 6
                      else 'This database was last started by a release older than 2.254.')
            body = f'echo "{line}"\necho "{reason}"\nexit {code}'
            if code == 4 and first is None:
                # Once archived, the database is gone: a new installation
                body = f'[ -e "{self.data}/ucm.db" ] || {{ echo "sqlite {self.data}/ucm.db"; exit 3; }}\n' + body
        exe.write_text(f'#!/bin/sh\n{body}\n')
        exe.chmod(0o755)

    def wrap(self, fail=None, at=0, other_fs=(), corrupt_copies=False, other_mount=(), fstype='testfs',
             corrupt_back=False, refused=()):
        """Wrappers first in PATH: `fail` fails at its `at`-th call; `findmnt` reports each
        prefix of other_fs on a mount of its own, and of other_mount (a bind mount of the
        same filesystem) too. `rename`, the interpreter the script renames with, is refused
        (EXDEV) across those mounts, for a directory on overlayfs, and for the paths in
        `refused`; `mv` fails the run (mv-items) on anything but the journal. corrupt_back
        harms only the copies out of the archive (the put-backs)."""
        (self.state / 'count').write_text('0')
        (self.state / 'refused').write_text(''.join(f'{p}\n' for p in refused))
        mounts = sorted((*other_fs, *other_mount), key=lambda p: -len(str(p)))
        fs = ''.join(f'    "{p}"|"{p}"/*) echo {700 + i}; return 0 ;;\n' for i, p in enumerate(mounts))
        overlay = ('[ ! -d "$src" ] || [ -L "$src" ] || refuse\n' if fstype == 'overlay' else '')
        self.inner.mkdir(exist_ok=True)
        (self.inner / 'rename').write_text(
            f'#!/bin/sh\n# Called as: rename -I -c <code> <from> <to>\nsrc=$4 dst=$5\n'
            f'fs() {{ case $1 in\n{fs}    esac; echo 0; }}\n'
            f'refuse() {{ echo "OSError: [Errno 18] Invalid cross-device link" >&2; exit 1; }}\n'
            f'[ "$(fs "${{src%/*}}")" = "$(fs "${{dst%/*}}")" ] || refuse\n{overlay}'
            f'! grep -qxF -- "$src" {self.state}/refused || refuse\n'
            f'exec {sys.executable} "$@"\n')
        (self.inner / 'mv').write_text(
            f'#!/bin/sh\ncase "$1 $2" in "-- "*/.journal.new) exec {REAL["mv"]} "$@" ;; esac\n'
            f'echo "$*" >> {self.state}/mv-items; exit 1\n')
        for f in self.inner.iterdir():
            f.chmod(0o755)
        inner = {'mv': self.inner / 'mv', 'rename': self.inner / 'rename'}
        for name in ('mv', 'cp', 'rm', 'mkdir', 'chmod', 'rename'):
            check = ''
            if name == fail:
                check = (f'n=$(( $(cat {self.state}/count) + 1 )); echo $n > {self.state}/count\n'
                         f'[ "$n" != {at} ] || {{ echo "{name}: injected failure" >&2; exit 1; }}\n')
            run = f'exec {inner.get(name, REAL.get(name))} "$@"'
            if name == 'cp' and corrupt_copies:
                # Reports success over a copy that differs from its source: in content, mode,
                # date, group or owner, of a key, of a file deep in a tree, or of the tree itself
                harm, where = (corrupt_copies.split(':') + ['key'])[:2]
                harm = {'mode': '[ -d "$1" ] && chmod 0705 "$1" || chmod 0604 "$1"',
                        'date': 'touch -d @5 "$1"', 'group': f'chgrp {OTHER_GID} "$1"',
                        'owner': 'chown 1 "$1"'}.get(harm, 'printf x >> "$1"')
                where = {'key': '-name "*.key" -type f', 'nested': '-path "*/updates/nested/f"',
                         'top': '-maxdepth 0 -type d -name updates'}[where]
                only = f'case $3 in {self.parent}/*) ;; *) exit 0 ;; esac\n' if corrupt_back else ''
                run = (f'{REAL[name]} "$@" || exit 1\nfor last; do :; done\n{only}'
                       f'find "${{last%/}}" {where} -exec sh -c \'{harm}\' sh {{}} \\;')
            (self.bin / name).write_text(f'#!/bin/sh\n{check}{run}\n')
        # Asked for the target only: the mount holding a path
        table = ''.join(f'    "{p}"|"{p}"/*) echo "{p}"; exit 0 ;;\n' for p in mounts)
        (self.bin / 'findmnt').write_text(
            f'#!/bin/sh\nfor last; do :; done\ncase $last in\n{table}esac\necho /\n')
        (self.bin / 'date').write_text(
            f'#!/bin/sh\ncase "$*" in *%Y%m%dT*) echo {STAMP} ;; *) exec {shutil.which("date")} "$@" ;; esac\n')
        for f in self.bin.iterdir():
            f.chmod(0o755)

    def run(self, default_parent=False, timeout=60, interpreter=None):
        """interpreter: what UCM_PYTHON names (default: the `rename` wrapper)."""
        if not any(self.bin.iterdir()):
            self.wrap()
        env = {'PATH': f'{self.bin}:/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C',
               'UCM_PYTHON': str(self.bin / 'rename') if interpreter is None else interpreter}
        # A session of its own: a wrapper that kills the run kills its process group only
        return subprocess.run(
            [POSIX_SH, str(SCRIPT), str(self.home), str(self.data), str(self.config),
             '' if default_parent else str(self.parent), str(self.log)],
            capture_output=True, text=True, timeout=timeout, env=env, start_new_session=True)

    @property
    def archive(self):
        return self.parent / STAMP


def tree(top):
    """Every entry under *top*: type, mode, owner and group, and for files contents and
    mtime, for links targets, for other files their kind."""
    out = {}
    if not top.exists():
        return out
    for path in sorted(top.rglob('*')):
        st = path.lstat()
        rel = str(path.relative_to(top))
        attrs = (stat.S_IMODE(st.st_mode), st.st_uid, st.st_gid)
        if stat.S_ISLNK(st.st_mode):
            out[rel] = ('link', os.readlink(path))
        elif stat.S_ISDIR(st.st_mode):
            out[rel] = ('dir', *attrs)
        elif stat.S_ISREG(st.st_mode):
            out[rel] = ('file', *attrs, st.st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
        else:
            out[rel] = ('special', stat.S_IFMT(st.st_mode), *attrs)
    return out


def named(stdout):
    """The paths a run that exits 2 names as not put back or cleared."""
    lines = [line for line in stdout.splitlines() if 'are still in ' in line]
    return [path for line in lines for path in line.split(':', 1)[1].split()]


def files(top):
    return {k: v for k, v in tree(top).items() if v[0] != 'dir'}


def snapshot(box, *extra):
    return {str(p): tree(p) for p in (box.data, box.config, *extra)}


KEPT = ['backups', 'ca', 'certs', 'crl', 'private', 'scep', 'sessions']
# A group the files can be given that is not theirs: any as root, else a secondary one
OTHER_GID = 1 if os.getuid() == 0 else next(iter(set(os.getgroups()) - {os.getgid()}), None)


def whole(top, kept=()):
    """tree(top) without the directories `kept`, which the archive recreates: every file,
    link and directory moved or copied whole, with its attributes."""
    return {rel: entry for rel, entry in tree(top).items() if rel not in kept}


# -- what is archived, and how -------------------------------------------------------

def test_a_refused_database_and_everything_beside_it_are_moved_intact(tmp_path):
    box = Box(tmp_path)
    data, config = files(box.data), files(box.config)
    kept_modes = {d: stat.S_IMODE((box.data / d).stat().st_mode) for d in KEPT}

    out = box.run()

    assert out.returncode == 0, out.stdout + out.stderr
    assert files(box.archive / 'data') == data
    assert files(box.archive / 'config') == config
    # The directories stay, with their modes; nothing else is left
    assert sorted(p.name for p in box.data.iterdir()) == KEPT
    assert all(not any((box.data / d).iterdir()) for d in KEPT)
    assert {d: stat.S_IMODE((box.data / d).stat().st_mode) for d in KEPT} == kept_modes
    assert box.config.is_dir() and list(box.config.iterdir()) == []


def test_the_archive_is_root_only_and_says_how_to_restore(tmp_path):
    box = Box(tmp_path)
    out = box.run()
    assert out.returncode == 0, out.stderr
    for d in (box.parent, box.archive):
        assert stat.S_IMODE(d.stat().st_mode) == 0o700
        assert d.stat().st_uid == os.getuid()
    readme = (box.archive / 'README.txt').read_text()
    readme.encode('ascii')
    assert '—' not in readme and '–' not in readme
    assert STAMP in readme and str(box.data) in readme and str(box.config) in readme
    assert '136_lifted_hold_leftovers' in readme
    for step in ('Install UCM 2.254', 'systemctl stop ucm', 'systemctl start ucm',
                 'Install this release again'):
        assert step in readme
    assert not (box.archive / '.journal').exists()


def test_the_archive_lies_beside_the_home_outside_what_the_service_writes(tmp_path):
    """By default <home>/../ucm-archive: not under the data, its backups or /var/lib/ucm, nor
    under the home the package scripts chown to the service account, nor writable by the unit."""
    box = Box(tmp_path)
    out = box.run(default_parent=True)
    assert out.returncode == 0, out.stdout + out.stderr
    assert (box.home.parent / 'ucm-archive' / STAMP / 'data' / 'ucm.db').is_file()
    for unit in ('packaging/debian/ucm.service', 'packaging/rpm/ucm.service'):
        rw = [l.split('=', 1)[1].split() for l in (ROOT / unit).read_text().splitlines()
              if l.startswith('ReadWritePaths')]
        assert rw
        for paths in rw:
            assert all(not '/opt/ucm-archive'.startswith(p.rstrip('/') + '/') and p != '/opt'
                       for p in paths), unit


def test_it_reports_what_it_found_where_it_went_and_that_ucm_starts_empty(tmp_path):
    box = Box(tmp_path)
    out = box.run()
    assert out.returncode == 0, out.stderr
    assert str(box.data / 'ucm.db') in out.stdout
    assert str(box.archive) in out.stdout
    assert 'starts empty' in out.stdout
    logged = [line.split(' ', 1)[1] for line in box.log.read_text().splitlines()]
    assert logged == out.stdout.splitlines()
    for text in (out.stdout, box.log.read_text(), (box.archive / 'README.txt').read_text()):
        assert SECRET not in text


def test_a_database_placed_elsewhere_goes_with_its_journal_files(tmp_path):
    box = Box(tmp_path)
    elsewhere = tmp_path / 'srv'
    elsewhere.mkdir()
    shutil.move(box.data / 'ucm.db', elsewhere / 'pki.db')
    (elsewhere / 'pki.db-wal').write_bytes(b'wal')
    (elsewhere / 'unrelated').write_text('stays')
    env = box.config / 'ucm.env'
    env.write_text(env.read_text().replace(f'{box.data}/ucm.db', f'"{elsewhere}/pki.db"'))
    before = files(elsewhere)

    out = box.run()

    assert out.returncode == 0, out.stdout + out.stderr
    assert files(box.archive / 'database') == {k: v for k, v in before.items() if k != 'unrelated'}
    assert sorted(p.name for p in elsewhere.iterdir()) == ['unrelated']
    assert f'{elsewhere}/pki.db' in (box.archive / 'README.txt').read_text()


@pytest.mark.parametrize('spelling', ['{data}/./ucm.db', '{data}//ucm.db', '{home}/../ucm/data/ucm.db'])
def test_a_database_path_spelled_otherwise_under_the_data_goes_with_the_data(tmp_path, spelling):
    box = Box(tmp_path)
    data = files(box.data)
    env = box.config / 'ucm.env'
    env.write_text(env.read_text().replace(f'DATABASE_PATH={box.data}/ucm.db',
                                           'DATABASE_PATH=' + spelling.format(data=box.data, home=box.home)))
    out = box.run()
    assert out.returncode == 0, out.stdout + out.stderr
    assert files(box.archive / 'data') == data
    assert not (box.archive / 'database').exists()
    assert 'placed outside' not in (box.archive / 'README.txt').read_text()


def test_the_readme_puts_each_file_where_the_packages_write_it(tmp_path):
    """The packages write the HTTPS key and certificate into the data directory."""
    box = Box(tmp_path)
    assert box.run().returncode == 0
    lines = (box.archive / 'README.txt').read_text().splitlines()
    data_line = next(line for line in lines if line.lstrip().startswith('data/'))
    config_line = next(line for line in lines if line.lstrip().startswith('config/'))
    assert 'HTTPS' in data_line and 'HTTPS' not in config_line
    postinst = (ROOT / 'packaging' / 'debian' / 'postinst').read_text()
    assert '-keyout "$UCM_DATA/https_key.pem"' in postinst


@pytest.mark.parametrize('line, kept', [('UCM_FIPS_BUILD=1', True), ('export UCM_FIPS_BUILD="yes"', True),
                                        ('UCM_FIPS_BUILD=True', True), ('UCM_FIPS_BUILD=0', False)])
def test_a_fips_build_request_is_carried_into_the_new_configuration(tmp_path, line, kept):
    """The venv was built from the archived ucm.env: the new one keeps that install choice."""
    box = Box(tmp_path)
    env = box.config / 'ucm.env'
    env.write_text(env.read_text() + line + '\n')
    config = files(box.config)
    out = box.run()
    assert out.returncode == 0, out.stdout + out.stderr
    assert files(box.archive / 'config') == config
    if kept:
        assert env.read_text() == 'UCM_FIPS_BUILD=1\n'
        assert stat.S_IMODE(env.stat().st_mode) == 0o600
        assert 'UCM_FIPS_BUILD=1' in out.stdout
        assert SECRET not in out.stdout
    else:
        assert list(box.config.iterdir()) == []
        assert 'UCM_FIPS_BUILD' not in out.stdout


def test_a_purged_install_without_configuration_is_archived_too(tmp_path):
    """apt purge removes /etc/ucm and leaves /opt/ucm/data: the default database path applies."""
    box = Box(tmp_path)
    shutil.rmtree(box.config)
    data = files(box.data)
    out = box.run()
    assert out.returncode == 0, out.stdout + out.stderr
    assert files(box.archive / 'data') == data
    assert not (box.archive / 'config').exists()


# -- nothing happens anywhere else ---------------------------------------------------

@pytest.mark.parametrize('registry', [None, 'pivot'])
def test_fresh_or_startable_data_is_left_alone(tmp_path, registry):
    box = Box(tmp_path, registry=registry)
    before = snapshot(box)
    out = box.run()
    assert (out.returncode, out.stdout) == (0, '')
    assert snapshot(box) == before
    assert not box.parent.exists() and not box.log.exists()


def test_a_new_machine_creates_nothing(tmp_path):
    box = Box(tmp_path, registry=None)
    shutil.rmtree(box.data)
    shutil.rmtree(box.config)
    out = box.run()
    assert (out.returncode, out.stdout) == (0, '')
    assert not box.parent.exists() and not box.data.exists() and not box.config.exists()


@pytest.mark.parametrize('leftovers', ['none', 'empty directories'])
def test_without_a_database_or_a_configuration_nothing_is_probed(tmp_path, leftovers):
    """A new host whose venv could not be built: no answer to ask for, nothing to announce."""
    box = Box(tmp_path, registry=None, python='missing')
    shutil.rmtree(box.config)
    shutil.rmtree(box.data)
    if leftovers == 'empty directories':
        box.config.mkdir()
        for d in KEPT:
            (box.data / d).mkdir(parents=True)
    before = snapshot(box)
    out = box.run()
    assert (out.returncode, out.stdout, out.stderr) == (0, '', '')
    assert snapshot(box) == before
    assert not box.parent.exists() and not box.log.exists()


@pytest.mark.parametrize('python, code, first, says', [
    ('stub', 4, 'postgresql', 'not a SQLite file'),
    ('stub', 5, 'sqlite /x/ucm.db', 'could not read'),
    ('stub', 1, 'Traceback (most recent call last):', 'could not read'),
    ('missing', None, None, 'could not read'),
])
def test_a_database_it_cannot_archive_is_left_and_named(tmp_path, python, code, first, says):
    """PostgreSQL, unreadable, or no answer: nothing moves, the operator is told what to do."""
    box = Box(tmp_path)
    box.python(python, code=code, first=first)
    before = snapshot(box)
    out = box.run()
    assert out.returncode == 3, out.stdout
    assert says in out.stdout and '2.254' in out.stdout
    # Which database: the SQLite file, or the backend alone (never a URL)
    assert (first if python == 'stub' and code != 1 else 'could not read') in out.stdout
    assert snapshot(box) == before
    assert not box.parent.exists()


@pytest.mark.parametrize('python', ['real', 'stub'])
def test_a_database_a_later_release_wrote_is_left_and_never_called_older(tmp_path, python):
    """A registry naming migrations this release lacks is a downgrade: nothing moves, and the
    output sends back to the release that wrote it, never to 2.254."""
    box = Box(tmp_path, registry=None)
    _database(box.data / 'ucm.db', _pivot_registry() + ['300_upgrade_from_2_254', '999_later'])
    if python == 'stub':
        box.python('stub', code=6)
    before = snapshot(box)
    out = box.run()
    assert out.returncode == 3, out.stderr
    assert snapshot(box) == before
    assert not box.parent.exists()
    assert 'release that wrote' in out.stdout
    assert '2.254' not in out.stdout


# -- idempotent ----------------------------------------------------------------------

def test_a_second_run_finds_nothing_to_archive(tmp_path):
    box = Box(tmp_path)
    assert box.run().returncode == 0
    archived = tree(box.parent)
    _database(box.data / 'ucm.db', _pivot_registry() + ['300_upgrade_from_2_254'])
    out = box.run()
    assert (out.returncode, out.stdout) == (0, '')
    assert tree(box.parent) == archived


def test_an_existing_archive_is_never_overwritten(tmp_path):
    box = Box(tmp_path)
    box.archive.mkdir(parents=True)
    (box.archive / 'data').mkdir()
    (box.archive / 'data' / 'ucm.db').write_text('an earlier archive')
    earlier = tree(box.archive)
    data = files(box.data)

    out = box.run()

    assert out.returncode == 0, out.stdout + out.stderr
    assert tree(box.archive) == earlier
    assert files(box.parent / f'{STAMP}-2' / 'data') == data


# -- all or nothing ------------------------------------------------------------------

def _fail_everywhere(tmp_path, layout):
    """Fails each wrapped command at each of its calls in turn, on a new box each time: a
    failure puts back everything and starts nothing; a call whose failure is tolerated
    (the log) still archives everything. Returns how many runs failed."""
    failed = 0
    for command in ('mkdir', 'mv', 'cp', 'rm', 'chmod', 'rename'):
        for at in range(1, 200):
            box = Box(tmp_path / f'{command}-{at}', python='stub')
            box.wrap(fail=command, at=at, other_fs=layout(box))
            before, data, config = snapshot(box), files(box.data), files(box.config)
            out = box.run()
            if int((box.state / 'count').read_text()) < at:
                assert out.returncode == 0, (command, at, out.stdout, out.stderr)
                break
            if out.returncode == 0:
                assert files(box.archive / 'data') == data, (command, at)
                assert files(box.archive / 'config') == config, (command, at)
                continue
            failed += 1
            assert out.returncode == 1, (command, at, out.stdout, out.stderr)
            assert snapshot(box) == before, (command, at, out.stdout)
            assert not box.parent.exists() or not any(box.parent.iterdir()), (command, at)
            assert 'was not started' in out.stdout, (command, at)
        else:
            pytest.fail(f'{command} never stopped failing')
    return failed


@pytest.mark.parametrize('layout', ['one filesystem', 'data and config are mount points',
                                    'a mount point inside the data'])
def test_a_failure_at_any_step_puts_everything_back(tmp_path, layout):
    other_fs = {
        'one filesystem': lambda box: (),
        'data and config are mount points': lambda box: (box.data, box.config),
        'a mount point inside the data': lambda box: (box.data / 'updates',),
    }[layout]
    assert _fail_everywhere(tmp_path, other_fs) > 5


def test_mount_points_are_kept_and_their_contents_copied(tmp_path):
    box = Box(tmp_path, python='stub')
    box.wrap(other_fs=(box.data, box.config, box.data / 'updates'))
    data, config = files(box.data), files(box.config)
    out = box.run()
    assert out.returncode == 0, out.stdout + out.stderr
    assert files(box.archive / 'data') == data
    assert files(box.archive / 'config') == config
    assert sorted(p.name for p in box.data.iterdir()) == sorted(KEPT + ['updates'])
    assert list((box.data / 'updates').iterdir()) == []


def test_a_copy_whose_source_removal_failed_is_restored_before_it_goes(tmp_path):
    """Across filesystems the sources go last; one that fails midway is completed again."""
    box = Box(tmp_path, python='stub')
    before = snapshot(box)
    box.wrap(fail='rm', at=2, other_fs=(box.data,))
    out = box.run()
    assert out.returncode == 1, out.stdout
    assert snapshot(box) == before
    assert 'Everything was put back' in out.stdout


def _copied(box, *names):
    """Runs the archiving; asserts it succeeded and that each of `names` (relative to the
    data) was copied, none renamed."""
    (box.state / 'cp-args').unlink(missing_ok=True)
    (box.bin / 'cp').write_text(f'#!/bin/sh\necho "$*" >> {box.state}/cp-args\nexec {REAL["cp"]} "$@"\n')
    out = box.run()
    assert out.returncode == 0, (out.returncode, out.stdout, out.stderr)
    copied = (box.state / 'cp-args').read_text() if (box.state / 'cp-args').exists() else ''
    for name in names:
        assert f'-a -- {box.data}/{name} {box.archive}/data/{name}' in copied.splitlines(), (name, copied)
    return out


def test_a_bind_mount_of_the_same_filesystem_is_crossed_by_a_verified_copy(tmp_path):
    """rename(2) cannot cross a bind mount even on one device: refused, the move is a copy."""
    box = Box(tmp_path, python='stub')
    data, config = files(box.data), files(box.config)
    box.wrap(other_mount=(box.data,))
    _copied(box, 'ucm.db', 'updates', 'current.key')
    assert files(box.archive / 'data') == data
    assert files(box.archive / 'config') == config
    assert sorted(p.name for p in box.data.iterdir()) == KEPT


def test_a_directory_on_overlayfs_is_copied_and_a_file_renamed(tmp_path):
    """rename(2) refuses a directory of an overlayfs lower layer (EXDEV)."""
    box = Box(tmp_path, python='stub')
    data = files(box.data)
    box.wrap(fstype='overlay')
    _copied(box, 'updates')
    copied = (box.state / 'cp-args').read_text()
    assert 'ucm.db' not in copied and 'https_key.pem' not in copied
    assert files(box.archive / 'data') == data


@pytest.mark.parametrize('kind', ['file', 'directory', 'link'])
def test_an_item_whose_rename_is_refused_is_archived_by_a_verified_copy(tmp_path, kind):
    """Whatever the kernel refuses to rename (EXDEV) is copied, compared, then removed."""
    box = Box(tmp_path, python='stub')
    data, config = files(box.data), files(box.config)
    name = {'file': 'https_key.pem', 'directory': 'updates', 'link': 'current.key'}[kind]
    box.wrap(refused=(f'{box.data}/{name}',))
    _copied(box, name)
    assert files(box.archive / 'data') == data
    assert files(box.archive / 'config') == config
    assert sorted(p.name for p in box.data.iterdir()) == KEPT


@pytest.mark.parametrize('interpreter', ['', 'missing', 'failing'])
def test_without_a_working_interpreter_everything_is_copied_never_left(tmp_path, interpreter):
    """No interpreter to call rename(2) with, or one that fails: every move is a copy."""
    box = Box(tmp_path, python='stub')
    data, config = files(box.data), files(box.config)
    box.wrap()
    path = {'': '', 'missing': str(tmp_path / 'no-python'), 'failing': '/bin/false'}[interpreter]
    (box.state / 'cp-args').unlink(missing_ok=True)
    (box.bin / 'cp').write_text(f'#!/bin/sh\necho "$*" >> {box.state}/cp-args\nexec {REAL["cp"]} "$@"\n')
    out = box.run(interpreter=path)
    assert out.returncode == 0, (out.stdout, out.stderr)
    assert files(box.archive / 'data') == data
    assert files(box.archive / 'config') == config
    assert sorted(p.name for p in box.data.iterdir()) == KEPT
    assert f'-a -- {box.data}/ucm.db {box.archive}/data/ucm.db' in (box.state / 'cp-args').read_text()


def test_a_bind_mount_inside_the_data_is_kept_and_its_contents_moved(tmp_path):
    """A mount point cannot be renamed (EBUSY), on one device too."""
    box = Box(tmp_path, python='stub')
    data = files(box.data)
    box.wrap(other_mount=(box.data / 'updates',))
    out = box.run()
    assert out.returncode == 0, (out.returncode, out.stdout, out.stderr)
    assert files(box.archive / 'data') == data
    assert list((box.data / 'updates').iterdir()) == []


def _killed_after_renaming(box, name):
    """The run is killed right after rename(2) moved data/<name> into the archive."""
    box.wrap()
    (box.bin / 'rename').write_text(
        f'#!/bin/sh\n{box.inner}/rename "$@" || exit 1\n'
        f'[ "$4" != {box.data}/{name} ] || kill -9 0\n')
    out = box.run()
    assert out.returncode == -9, (out.stdout, out.stderr)
    assert not os.path.lexists(box.data / name) and os.path.lexists(box.archive / 'data' / name)
    box.wrap()


@pytest.mark.parametrize('name, made_again', [('ucm.db', 'a file'), ('updates', 'a file'),
                                               ('updates', 'a directory')])
def test_a_source_made_again_after_its_rename_is_never_removed_nor_its_archive(tmp_path, name, made_again):
    """Killed right after a rename, then the source made again (a service started by hand
    creates ucm.db): the retry keeps both sides whole, names both, and exits 2."""
    box = Box(tmp_path, python='stub')
    archived = tree(box.data / name) if (box.data / name).is_dir() else None
    original = (box.data / name).read_bytes() if archived is None else None
    _killed_after_renaming(box, name)
    if made_again == 'a file':
        (box.data / name).write_bytes(b'made again')
    else:
        (box.data / name).mkdir()
        (box.data / name / 'g').write_text('made again')
    again = tree(box.data / name) if made_again == 'a directory' else None

    for _ in range(2):
        out = box.run()
        assert out.returncode == 2, (out.stdout, out.stderr)
        assert str(box.data / name) in out.stdout and f'{box.archive}/data/{name}' in out.stdout
        if made_again == 'a file':
            assert (box.data / name).read_bytes() == b'made again'
        else:
            assert tree(box.data / name) == again
        if archived is None:
            assert (box.archive / 'data' / name).read_bytes() == original
        else:
            assert tree(box.archive / 'data' / name) == archived


def test_a_refused_rename_leaves_the_journal_before_its_copy(tmp_path):
    """A rename refused once (not across filesystems) makes the item a copy, whose source is
    then removed; its put-back failing, the retry puts it back from the copy and converges:
    no rename line left to move the copy back behind the journal's back."""
    box = Box(tmp_path / 'count', python='stub')
    box.wrap(fail='rename', at=10 ** 6)
    assert box.run().returncode == 0
    box = Box(tmp_path / 'box', python='stub')
    data, config = files(box.data), files(box.config)
    box.wrap(fail='rename', at=1)
    first = box.state / 'first'
    # Every source removed, the journal cannot go: the put-back of the copy fails once
    (box.bin / 'rm').write_text(
        f'#!/bin/sh\nfor last; do :; done\ncase $last in */.journal) exit 1 ;; esac\n'
        f'exec {REAL["rm"]} "$@"\n')
    (box.bin / 'cp').write_text(
        f'#!/bin/sh\ncase $3 in {box.parent}/*) [ -e {first} ] || {{ : > {first}; exit 1; }} ;; esac\n'
        f'exec {REAL["cp"]} "$@"\n')
    out = box.run()
    assert out.returncode == 2, (out.stdout, out.stderr)
    assert first.exists() and 'ucm-2026.ucmbkp' in out.stdout
    box.wrap()
    out = box.run()
    assert out.returncode == 0, (out.stdout, out.stderr)
    assert files(box.archive / 'data') == data
    assert files(box.archive / 'config') == config


def _all_files(*tops):
    """The files under several trees, by path relative to each, whichever tree holds them."""
    out = {}
    for top in tops:
        for rel, entry in files(top).items():
            assert rel not in out, rel
            out[rel] = entry
    return out


def _stuck(box):
    """Removing a copied source fails halfway, then every later copy fails: what was copied
    cannot be put back. Returns the marker the failed removal leaves."""
    box.wrap(other_fs=(box.data,))
    failed = box.state / 'rm-failed'
    (box.bin / 'rm').write_text(
        f'#!/bin/sh\nfor last; do :; done\ncase $last in */updates)\n'
        f'    {REAL["rm"]} -f -- "$last/nested/f"; : > {failed}; exit 1 ;;\nesac\n'
        f'exec {REAL["rm"]} "$@"\n')
    (box.bin / 'cp').write_text(f'#!/bin/sh\n[ ! -e {failed} ] || exit 1\nexec {REAL["cp"]} "$@"\n')
    return failed


def test_a_copy_is_kept_while_its_source_cannot_be_completed_again(tmp_path):
    """Removing a copied source fails halfway, then putting it back fails too: the archive
    keeps every copy whose source is not whole again, so no file is lost."""
    box = Box(tmp_path, python='stub')
    data = files(box.data)
    failed = _stuck(box)

    out = box.run()

    assert out.returncode == 2, out.stdout
    assert failed.exists()
    assert not (box.data / 'updates' / 'nested' / 'f').exists()
    assert 'could not be put back' in out.stdout and str(box.archive) in out.stdout
    assert 'Everything was put back' not in out.stdout
    assert _all_files(box.data, box.archive / 'data') == data


def test_the_next_attempt_puts_back_what_was_stuck_then_archives_it_whole(tmp_path):
    """A retry after a partial roll-back finishes it first: one archive, nothing mixed or lost."""
    box = Box(tmp_path, python='stub')
    data, config = files(box.data), files(box.config)
    _stuck(box)
    assert box.run().returncode == 2

    # Still failing: no file is lost or archived a second time, and it says so again
    out = box.run()
    assert out.returncode == 2, out.stdout
    assert 'could not be put back' in out.stdout
    assert [p.name for p in box.parent.iterdir()] == [STAMP]
    assert _all_files(box.data, box.archive / 'data') == data
    assert files(box.config) == config

    # Cause fixed: the roll-back completes, then one archive takes everything
    box.wrap(other_fs=(box.data,))
    out = box.run()
    assert out.returncode == 0, out.stdout + out.stderr
    assert 'put back' in out.stdout
    assert [p.name for p in box.parent.iterdir()] == [STAMP]
    assert files(box.archive / 'data') == data
    assert files(box.archive / 'config') == config
    assert not (box.archive / '.journal').exists()


def test_the_next_attempt_after_a_complete_roll_back_starts_over(tmp_path):
    box = Box(tmp_path, python='stub')
    data = files(box.data)
    box.wrap(fail='rm', at=3, other_fs=(box.data,))
    assert box.run().returncode == 1
    box.wrap()
    out = box.run()
    assert out.returncode == 0, out.stdout + out.stderr
    assert 'did not complete' not in out.stdout
    assert files(box.archive / 'data') == data


@pytest.mark.parametrize('differs', [
    f'{harm}:{where}' for where in ('key', 'nested', 'top')
    for harm in ('content', 'mode', 'date', 'group', 'owner')
    if where != 'top' or harm not in ('content', 'date')])
def test_a_copy_that_differs_from_its_source_is_never_kept_in_its_place(tmp_path, differs):
    """Each attribute digest compares, on a file copied alone and in a copied tree."""
    if differs.startswith('owner') and os.getuid() != 0:
        pytest.skip('only root can give a file another owner')
    if differs.startswith('group') and OTHER_GID is None:
        pytest.skip('no secondary group to give a file')
    box = Box(tmp_path, python='stub')
    before = snapshot(box)
    box.wrap(other_fs=(box.data,), corrupt_copies=differs)
    out = box.run()
    assert out.returncode == 1, out.stdout
    assert snapshot(box) == before
    assert not box.parent.exists() or not any(box.parent.iterdir())



@pytest.mark.parametrize('differs', [
    f'{harm}:{where}' for where in ('key', 'nested', 'top')
    for harm in ('content', 'mode', 'date', 'group', 'owner')
    if where != 'top' or harm not in ('content', 'date')])
def test_a_put_back_that_differs_from_the_archive_is_never_taken_for_whole(tmp_path, differs):
    """The last step fails once every source is gone; each put-back then reports success
    over a copy that differs: the archive keeps it, and the retry puts it back whole."""
    if differs.startswith('owner') and os.getuid() != 0:
        pytest.skip('only root can give a file another owner')
    if differs.startswith('group') and OTHER_GID is None:
        pytest.skip('no secondary group to give a file')
    box = Box(tmp_path / 'count', python='stub')
    box.wrap(fail='rm', at=10 ** 6, other_fs=(box.data,))
    assert box.run().returncode == 0
    last_rm = int((box.state / 'count').read_text())
    box = Box(tmp_path / 'box', python='stub')
    data, config = tree(box.data), tree(box.config)
    box.wrap(fail='rm', at=last_rm, other_fs=(box.data,), corrupt_copies=differs, corrupt_back=True)
    out = box.run()
    assert out.returncode == 2, (out.stdout, out.stderr)
    box.wrap(other_fs=(box.data,))
    out = box.run()
    assert out.returncode == 0, (out.stdout, out.stderr)
    assert whole(box.archive / 'data', KEPT) == {k: v for k, v in data.items() if k not in KEPT}
    assert tree(box.archive / 'config') == config

@pytest.mark.parametrize('tool', ['find', 'find dates', 'cksum', 'stat'])
def test_a_digest_that_cannot_be_taken_never_passes_for_a_match(tmp_path, tool):
    """find missing (a minimal image), failing on its last question only, cksum or stat
    failing: no copy is taken for whole."""
    box = Box(tmp_path, python='stub')
    before = snapshot(box)
    box.wrap(other_fs=(box.data,))
    fails = ''
    if tool == 'find dates':
        tool, fails = 'find', f'case "$*" in *"date "*) ;; *) exec {shutil.which("find")} "$@" ;; esac\n'
    (box.bin / tool).write_text(f'#!/bin/sh\n{fails}echo "{tool}: not found" >&2; exit 127\n')
    (box.bin / tool).chmod(0o755)
    out = box.run()
    assert out.returncode == 1, (out.stdout, out.stderr)
    assert snapshot(box) == before
    assert 'Everything was put back' in out.stdout


def test_a_fifo_is_compared_by_its_kind_never_read(tmp_path):
    """Reading a FIFO left in the data would block the installation."""
    box = Box(tmp_path, python='stub')
    os.mkfifo(box.data / 'ucm.sock', 0o600)
    data = files(box.data)
    box.wrap(other_fs=(box.data,))
    out = box.run(timeout=20)
    assert out.returncode == 0, (out.stdout, out.stderr)
    assert files(box.archive / 'data') == data
    assert files(box.archive / 'data')['ucm.sock'][0] == 'special'


def test_a_put_back_refused_twice_the_same_way_says_a_retry_will_not_help(tmp_path):
    """The source filesystem refuses what a put-back sets (an owner, as root on a share):
    the first failure says the next attempt tries again, the second one that it will not
    succeed before the cause is fixed. Then, fixed, the retry converges."""
    box = Box(tmp_path / 'count', python='stub')
    box.wrap(fail='rm', at=10 ** 6, other_fs=(box.data,))
    assert box.run().returncode == 0
    last_rm = int((box.state / 'count').read_text())
    box = Box(tmp_path / 'box', python='stub')
    data, config = files(box.data), files(box.config)
    box.wrap(fail='rm', at=last_rm, other_fs=(box.data,))
    (box.bin / 'cp').write_text(
        f'#!/bin/sh\ncase $3 in {box.parent}/*) echo "cp: failed to preserve ownership" >&2; exit 1 ;; esac\n'
        f'exec {REAL["cp"]} "$@"\n')
    first = box.run()
    assert first.returncode == 2, first.stdout
    assert 'next attempt tries again' in first.stdout and 'will not' not in first.stdout
    second = box.run()
    assert second.returncode == 2, second.stdout
    assert 'previous attempt too' in second.stdout and 'until the cause' in second.stdout
    assert 'tries again' not in second.stdout
    assert _all_files(box.data, box.archive / 'data') == data
    box.wrap(other_fs=(box.data,))
    out = box.run()
    assert out.returncode == 0, out.stdout + out.stderr
    assert files(box.archive / 'data') == data and files(box.archive / 'config') == config


def test_the_rpm_requires_what_the_archiving_runs():
    """find, cksum and stat compare the copies (a minimal RHEL image lacks find); findmnt
    tells a bind mount. On Debian these are essential packages, never named."""
    spec = (ROOT / 'packaging' / 'rpm' / 'ucm.spec').read_text()
    requires = {line.split(':', 1)[1].split()[0] for line in spec.splitlines()
                if line.startswith('Requires:')}
    assert {'findutils', 'coreutils', '/usr/bin/findmnt'} <= requires

def test_the_kept_directories_are_those_the_packages_create():
    """RPM owns these directories and the DEB postinst creates them: the archive leaves them."""
    import re
    spec = (ROOT / 'packaging' / 'rpm' / 'ucm.spec').read_text()
    postinst = (ROOT / 'packaging' / 'debian' / 'postinst').read_text()
    assert {frozenset(m.split()) for m in re.findall(r'for d in ([a-z ]+); do', spec)} == {frozenset(KEPT)}
    assert re.findall(r'"\$UCM_DATA"/\{([a-z,]+)\}', postinst) and all(
        set(m.split(',')) == set(KEPT) for m in re.findall(r'"\$UCM_DATA"/\{([a-z,]+)\}', postinst))


def test_a_copy_half_removed_while_putting_back_is_removed_on_the_retry(tmp_path):
    """A copy whose source is whole again leaves the journal's remove line first: when
    removing that copy stops halfway, the retry finishes it instead of comparing the
    source with what is left of the copy."""
    box = Box(tmp_path, python='stub')
    data, config = files(box.data), files(box.config)
    box.wrap(other_fs=(box.data,))
    once = box.state / 'once'
    (box.bin / 'rm').write_text(
        f'#!/bin/sh\nfor last; do :; done\ncase $last in\n'
        f'    {box.data}/updates) exit 1 ;;\n'
        f'    {box.archive}/data/updates) [ -e {once} ] || {{ : > {once}; '
        f'{REAL["rm"]} -f -- "$last/nested/f"; exit 1; }} ;;\nesac\n'
        f'exec {REAL["rm"]} "$@"\n')
    out = box.run()
    assert out.returncode == 2, out.stdout
    assert f'{box.archive}/data/updates' in out.stdout
    assert files(box.data) == data
    box.wrap(other_fs=(box.data,))
    out = box.run()
    assert out.returncode == 0, out.stdout + out.stderr
    assert [p.name for p in box.parent.iterdir()] == [STAMP]
    assert files(box.archive / 'data') == data
    assert files(box.archive / 'config') == config
