"""archive-leftovers.sh: a 3.0 package installed over what a removed UCM left archives it, or nothing.

Everything runs in a temporary root: the data, configuration, archive and log paths are
arguments, and the commands that move files can be wrapped to fail at any call. Every
item is renamed once, never copied or removed: a guard fails the run at the first cp, mv
or rm that names a path of the earlier installation or of its archives.
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
# Where an item rename(2) cannot take out of its filesystem goes, beside it
LOCAL = f'.ucm-archive-{STAMP}'
FIPS = 'UCM_FIPS_BUILD=1\n'
REAL = {name: shutil.which(name) for name in ('mv', 'cp', 'rm', 'mkdir', 'rmdir', 'chmod', 'tee')}
KEPT = ['backups', 'ca', 'certs', 'crl', 'private', 'scep', 'sessions']
COMMANDS = ('mkdir', 'rmdir', 'mv', 'rm', 'chmod', 'rename', 'tee')


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
        for d in KEPT:
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
        (self.data / 'updates' / 'manifest.json').write_text('{}')
        os.symlink('nested', self.data / 'updates' / 'latest')
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

    def _guard(self, name, allowed=(), arms=''):
        """`name` fails, and records the call in state/forbidden, when an argument is a path
        of the earlier installation or of its archives that `allowed` (case patterns) and
        `arms` (case arms of their own) leave out."""
        mine = '|'.join(f'"{self.tmp}/{d}"/*' for d in ('opt', 'etc', 'srv'))
        ok = f'        {"|".join(allowed)}) continue ;;\n' if allowed else ''
        return (f'#!/bin/sh\nno() {{ printf "%s\\n" "{name} $*" >> {self.state}/forbidden; exit 1; }}\n'
                f'for a; do\n    case $a in\n{ok}{arms}        {mine}) no "$@" ;;\n'
                f'    esac\ndone\nexec {REAL[name]} "$@"\n')

    def wrap(self, fail=None, at=0, other_fs=(), other_mount=(), fstype='testfs', refused=()):
        """Wrappers first in PATH: `fail` fails at its `at`-th call; `findmnt` reports each
        prefix of other_fs on a mount of its own, and of other_mount (a bind mount of the
        same filesystem) too. `rename`, the interpreter the script renames with, is refused
        (EXDEV) across those mounts, for a directory on overlayfs, and for the paths in
        `refused` wherever they go; cp, mv and rm are guarded (Box._guard)."""
        (self.state / 'count').write_text('0')
        (self.state / 'refused').write_text(''.join(f'{p}\n' for p in refused))
        mounts = sorted((*other_fs, *other_mount), key=lambda p: -len(str(p)))
        fs = ''.join(f'    "{p}"|"{p}"/*) echo {700 + i}; return 0 ;;\n' for i, p in enumerate(mounts))
        # A directory of the lower layer, as every directory the earlier installation left is
        overlay = '[ ! -d "$src" ] || [ -L "$src" ] || refuse\n' if fstype == 'overlay' else ''
        self.inner.mkdir(exist_ok=True)
        (self.inner / 'rename').write_text(
            f'#!/bin/sh\n# Called as: rename -I -c <code> <from> <to>\nsrc=$4 dst=$5\n'
            f'fs() {{ case $1 in\n{fs}    esac; echo 0; }}\n'
            f'refuse() {{ echo "OSError: [Errno 18] Invalid cross-device link" >&2; exit 1; }}\n'
            f'[ "$(fs "${{src%/*}}")" = "$(fs "${{dst%/*}}")" ] || refuse\n{overlay}'
            f'! grep -qxF -- "$src" {self.state}/refused || refuse\n'
            f'exec {sys.executable} "$@"\n')
        journal = (f'"{self.parent}"/*/.journal', f'"{self.parent}"/*/.journal.new')
        # The ucm.env the script wrote (UCM_FIPS_BUILD=1, or the start of it), absent or whole
        fips = (f'        "{self.config}/ucm.env") case {FIPS.strip()} in "$(cat -- "$a" 2>/dev/null)"*) continue ;; esac\n'
                f'            no "$@" ;;\n')
        (self.inner / 'mv').write_text(self._guard('mv', journal))
        (self.inner / 'cp').write_text(self._guard('cp'))
        (self.inner / 'rm').write_text(self._guard('rm', (*journal, f'"{self.parent}"/*/README.txt'), fips))
        for f in self.inner.iterdir():
            f.chmod(0o755)
        for name in ('mv', 'cp', 'rm', 'mkdir', 'rmdir', 'chmod', 'rename', 'tee'):
            check = ''
            if name == fail:
                check = (f'n=$(( $(cat {self.state}/count) + 1 )); echo $n > {self.state}/count\n'
                         f'[ "$n" != {at} ] || {{ echo "{name}: injected failure" >&2; exit 1; }}\n')
            (self.bin / name).write_text(f'#!/bin/sh\n{check}exec {self.real(name)} "$@"\n')
        # Asked for the target only: the mount holding a path
        table = ''.join(f'    "{p}"|"{p}"/*) echo "{p}"; exit 0 ;;\n' for p in mounts)
        (self.bin / 'findmnt').write_text(
            f'#!/bin/sh\nfor last; do :; done\ncase $last in\n{table}esac\necho /\n')
        (self.bin / 'date').write_text(
            f'#!/bin/sh\ncase "$*" in *%Y%m%dT*) echo {STAMP} ;; *) exec {shutil.which("date")} "$@" ;; esac\n')
        for f in self.bin.iterdir():
            f.chmod(0o755)

    def real(self, name):
        """What a wrapper of `name` runs in the end: the guard for cp, mv, rm and rename."""
        return self.inner / name if name in ('mv', 'cp', 'rm', 'rename') else REAL[name]

    def run(self, default_parent=False, timeout=60, interpreter=None):
        """interpreter: what UCM_PYTHON names (default: the `rename` wrapper). Fails the test
        when a guarded command was handed a path of the installation or of its archives."""
        if not any(self.bin.iterdir()):
            self.wrap()
        env = {'PATH': f'{self.bin}:/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C',
               'UCM_PYTHON': str(self.bin / 'rename') if interpreter is None else interpreter}
        # A session of its own: a wrapper that kills the run kills its process group only
        out = subprocess.run(
            [POSIX_SH, str(SCRIPT), str(self.home), str(self.data), str(self.config),
             '' if default_parent else str(self.parent), str(self.log)],
            capture_output=True, text=True, timeout=timeout, env=env, start_new_session=True)
        forbidden = self.state / 'forbidden'
        assert not forbidden.exists(), forbidden.read_text()
        return out

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


def reported(stdout):
    """{path: what failed} of a run that exits 2: one line each under the header, no
    reference to a cause printed elsewhere."""
    assert 'shown above' not in stdout and '—' not in stdout
    lines = stdout.splitlines()
    heads = [i for i, line in enumerate(lines) if line.startswith('Some files could not be put back or cleared')]
    out = {}
    for i in heads:
        for line in lines[i + 1:]:
            if not line.startswith('  '):
                break
            path, what = line[2:].split(': ', 1)
            out[path] = what
    return out


def named(stdout):
    """The paths a run that exits 2 names as not put back or cleared."""
    return list(reported(stdout))


def files(top):
    return {k: v for k, v in tree(top).items() if v[0] != 'dir'}


def snapshot(box, *extra):
    return {str(p): tree(p) for p in (box.data, box.config, *extra)}


# A group the files can be given that is not theirs: any as root, else a secondary one
OTHER_GID = 1 if os.getuid() == 0 else next(iter(set(os.getgroups()) - {os.getgid()}), None)


def plain(rel):
    """`rel` without the local archive directories it may sit in: the path it had."""
    return '/'.join(p for p in rel.split('/') if not p.startswith('.ucm-archive-'))


def places(box, sub):
    """{path it had: [(where it is, entry)]} of every entry under the data (sub 'data') or
    the configuration, local archives included, and under `sub` in every central archive."""
    top = box.data if sub == 'data' else box.config
    archives = sorted(box.parent.iterdir()) if box.parent.exists() else []
    out = {}
    for base in (top, *(a / sub for a in archives)):
        for rel, entry in tree(base).items():
            if plain(rel):
                out.setdefault(plain(rel), []).append((base / rel, entry))
    return out


def _fips_written(path):
    return path.is_file() and not path.is_symlink() and FIPS.startswith(path.read_text())


def exactly_once(box, data, config, why='', skip=()):
    """Every original file, link and special file is whole at exactly one path: its own,
    a central archive or a local one (never none, never two); every original directory
    whole at one at least. The ucm.env the script wrote does not count; nor does `skip`."""
    for sub, originals in (('data', data), ('config', config)):
        found = places(box, sub)
        for rel, entry in originals.items():
            if rel in skip or not plain(rel):
                continue
            at = found.get(plain(rel), [])
            if entry[0] == 'dir':
                assert any(e == entry for _p, e in at), (why, sub, rel, at)
                continue
            if sub == 'config' and plain(rel) == 'ucm.env' and len(at) > 1:
                at = [(p, e) for p, e in at if not (p == box.config / 'ucm.env' and _fips_written(p))]
            assert [e for _p, e in at] == [entry], (why, sub, rel, at)


def archived(box, out, data, config, why=''):
    """A finished archive: exit 0, one archive with its README and no journal, every
    original exactly once and none at its own path, local archives root only."""
    assert out.returncode == 0, (why, out.stdout, out.stderr)
    assert [a.name for a in box.parent.iterdir()] == [STAMP], (why, out.stdout)
    assert (box.archive / 'README.txt').is_file() and not (box.archive / '.journal').exists(), why
    exactly_once(box, data, config, why)
    for sub, top in (('data', box.data), ('config', box.config)):
        for rel, entry in tree(top).items():
            if rel == plain(rel) and entry[0] != 'dir':
                assert sub == 'config' and rel == 'ucm.env' and _fips_written(top / rel), (why, rel)
    for local in locals_of(box):
        assert local.name == LOCAL and stat.S_IMODE(local.stat().st_mode) == 0o700, (why, local)


def locals_of(box):
    """The local archive directories under the data and the configuration."""
    return sorted(p for top in (box.data, box.config) if top.exists()
                  for p in top.rglob('.ucm-archive-*') if p.is_dir())


def originals(box):
    return tree(box.data), tree(box.config)


# -- what is archived, and how -------------------------------------------------------

def test_a_refused_database_and_everything_beside_it_are_moved_intact(tmp_path):
    box = Box(tmp_path)
    data, config = originals(box)
    kept_modes = {d: stat.S_IMODE((box.data / d).stat().st_mode) for d in KEPT}

    out = box.run()

    archived(box, out, data, config)
    assert files(box.archive / 'data') == {k: v for k, v in data.items() if v[0] != 'dir'}
    assert files(box.archive / 'config') == {k: v for k, v in config.items() if v[0] != 'dir'}
    # The directories stay, with their modes; nothing else is left, no local archive
    assert sorted(p.name for p in box.data.iterdir()) == KEPT
    assert all(not any((box.data / d).iterdir()) for d in KEPT)
    assert {d: stat.S_IMODE((box.data / d).stat().st_mode) for d in KEPT} == kept_modes
    assert box.config.is_dir() and list(box.config.iterdir()) == []
    assert locals_of(box) == []


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
    flat = ' '.join(readme.split())
    assert 'renamed, never copied' in flat and 'copied, then checked' not in flat
    # Nothing went beside its directory: no section for it
    assert 'could not be renamed out of its filesystem' not in flat
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


def _elsewhere(box, tmp_path):
    elsewhere = tmp_path / 'srv'
    elsewhere.mkdir()
    shutil.move(box.data / 'ucm.db', elsewhere / 'pki.db')
    (elsewhere / 'pki.db-wal').write_bytes(b'wal')
    (elsewhere / 'unrelated').write_text('stays')
    env = box.config / 'ucm.env'
    env.write_text(env.read_text().replace(f'{box.data}/ucm.db', f'"{elsewhere}/pki.db"'))
    return elsewhere


@pytest.mark.parametrize('where', ['one filesystem', 'another filesystem'])
def test_a_database_placed_elsewhere_goes_with_its_journal_files(tmp_path, where):
    box = Box(tmp_path)
    elsewhere = _elsewhere(box, tmp_path)
    box.wrap(other_fs=(elsewhere,) if where == 'another filesystem' else ())
    before = files(elsewhere)

    out = box.run()

    assert out.returncode == 0, out.stdout + out.stderr
    went = box.archive / 'database' if where == 'one filesystem' else elsewhere / LOCAL
    assert files(went) == {k: v for k, v in before.items() if k != 'unrelated'}
    assert sorted(p.name for p in elsewhere.iterdir()) == sorted(
        ['unrelated'] + ([LOCAL] if where != 'one filesystem' else []))
    readme = (box.archive / 'README.txt').read_text()
    assert f'{elsewhere}/pki.db' in readme
    assert (f'{elsewhere}/{LOCAL}' in readme) == (where != 'one filesystem')


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
@pytest.mark.parametrize('where', ['one filesystem', 'another filesystem'])
def test_a_fips_build_request_is_carried_into_the_new_configuration(tmp_path, line, kept, where):
    """The venv was built from the archived ucm.env: the new one keeps that install choice."""
    box = Box(tmp_path)
    env = box.config / 'ucm.env'
    env.write_text(env.read_text() + line + '\n')
    box.wrap(other_fs=(box.config,) if where == 'another filesystem' else ())
    data, config = originals(box)
    out = box.run()
    archived(box, out, data, config)
    went = box.archive / 'config' if where == 'one filesystem' else box.config / LOCAL
    assert files(went) == {k: v for k, v in config.items() if v[0] != 'dir'}
    if kept:
        assert env.read_text() == FIPS
        assert stat.S_IMODE(env.stat().st_mode) == 0o600
        assert 'UCM_FIPS_BUILD=1' in out.stdout
        assert SECRET not in out.stdout
    else:
        assert not env.exists()
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


# -- where each item goes, by layout -------------------------------------------------

def _layout(box, layout):
    """Wraps the box for `layout`; returns what stays in place among the data's directories
    besides the kept ones."""
    kept = {d: box.data / d for d in KEPT}
    box.wrap(**{
        'one filesystem': {},
        'data on another filesystem': {'other_fs': (box.data,)},
        'data on a bind mount': {'other_mount': (box.data,)},
        'config on another filesystem': {'other_fs': (box.config,)},
        'each kept directory a mount point': {'other_fs': tuple(kept.values())},
        'a mount point inside the data': {'other_mount': (box.data / 'updates',)},
        'overlayfs': {'fstype': 'overlay'},
    }[layout])


# Where each item of the box ends, by layout: central (c), beside itself (l), or, for a
# directory nothing renames, in place with its entries placed the same way (a dict)
WHERE = {
    'one filesystem': {},
    'data on another filesystem': {'data': 'l', 'kept': 'l'},
    'data on a bind mount': {'data': 'l', 'kept': 'l'},
    'config on another filesystem': {'config': 'l'},
    'each kept directory a mount point': {'kept': 'l'},
    'a mount point inside the data': {'updates': 'l'},
    'overlayfs': {'updates': 'c', 'nested': 'c'},
}


@pytest.mark.parametrize('layout', list(WHERE))
def test_each_item_is_renamed_into_the_archive_or_beside_itself(tmp_path, layout):
    """Out of its filesystem rename(2) refuses an item: it goes beside it, into a local
    archive in its own directory; a directory neither can take stays, its entries placed
    the same way. Every original is then at exactly one path."""
    box = Box(tmp_path, python='stub')
    _layout(box, layout)
    data, config = originals(box)
    out = box.run()
    archived(box, out, data, config, layout)
    where = WHERE[layout]
    local = lambda rel: box.data / pathlib.Path(rel).parent / LOCAL / pathlib.Path(rel).name
    central = lambda rel: box.archive / 'data' / rel
    expect = {
        'ucm.db': where.get('data', 'c'), 'https_key.pem': where.get('data', 'c'),
        'current.key': where.get('data', 'c'), 'ca/root.key': where.get('kept', 'c'),
        'sessions/abc': where.get('kept', 'c'), 'updates/manifest.json': where.get('updates'),
        'updates/nested/f': where.get('nested'), 'updates': None if 'updates' in where else where.get('data', 'c'),
    }
    for rel, w in expect.items():
        if w is None:
            continue
        at = local(rel) if w == 'l' else central(rel)
        assert os.path.lexists(at), (layout, rel, at, tree(box.tmp / 'opt'))
    config_at = box.config / LOCAL if where.get('config') == 'l' else box.archive / 'config'
    assert (config_at / 'master.key').is_file(), layout
    if layout == 'overlayfs':
        # The directories stay, empty; their files went into the archive
        assert (box.data / 'updates' / 'nested').is_dir() and not os.path.lexists(box.data / 'updates' / 'nested' / 'f')
        assert locals_of(box) == []
    expected_locals = {
        'one filesystem': [], 'overlayfs': [],
        'data on another filesystem': [box.data / LOCAL, box.data / 'backups' / LOCAL, box.data / 'ca' / LOCAL,
                                       box.data / 'private' / LOCAL, box.data / 'sessions' / LOCAL],
        'config on another filesystem': [box.config / LOCAL],
        'each kept directory a mount point': [box.data / d / LOCAL for d in ('backups', 'ca', 'private', 'sessions')],
        'a mount point inside the data': [box.data / 'updates' / LOCAL],
    }.get(layout, None)
    if layout == 'data on a bind mount':
        expected_locals = [box.data / LOCAL] + [box.data / d / LOCAL for d in ('backups', 'ca', 'private', 'sessions')]
    assert locals_of(box) == sorted(expected_locals), locals_of(box)
    # The README names each of them with what it holds, and why
    readme = ' '.join((box.archive / 'README.txt').read_text().split())
    for d in expected_locals:
        assert f'{d}/: ' + ' '.join(sorted(p.name for p in d.iterdir())) in readme, (d, readme)
    assert ('could not be renamed out of its filesystem' in readme) == bool(expected_locals)
    if expected_locals:
        assert 'Nothing in them is used or removed by UCM' in readme
        assert str(box.data / LOCAL if 'data' in where else expected_locals[0]) in out.stdout


def test_a_file_nothing_can_rename_puts_everything_back(tmp_path):
    """Refused into the archive and beside itself: the archiving fails, everything is put
    back, and the file is named."""
    box = Box(tmp_path, python='stub')
    before = snapshot(box)
    box.wrap(other_fs=(box.data,), refused=(f'{box.data}/https_key.pem',))
    out = box.run()
    assert out.returncode == 1, (out.stdout, out.stderr)
    assert f'{box.data}/https_key.pem could not be renamed' in out.stdout
    assert 'Everything was put back in place' in out.stdout and 'was not started' in out.stdout
    assert snapshot(box) == before
    assert not box.parent.exists() or not any(box.parent.iterdir())


def test_a_fifo_is_renamed_never_read(tmp_path):
    """Reading a FIFO left in the data would block the installation."""
    box = Box(tmp_path, python='stub')
    os.mkfifo(box.data / 'ucm.sock', 0o600)
    data, config = originals(box)
    box.wrap(other_fs=(box.data,))
    out = box.run(timeout=20)
    archived(box, out, data, config)
    assert tree(box.data / LOCAL)['ucm.sock'][0] == 'special'


@pytest.mark.parametrize('where', ['data', 'kept directory', 'config'])
def test_a_local_archive_an_earlier_pass_left_stays_where_it_is(tmp_path, where):
    """Not an item: it is neither moved nor walked, and the README names it."""
    box = Box(tmp_path, python='stub')
    top = {'data': box.data, 'kept directory': box.data / 'ca', 'config': box.config}[where]
    earlier = top / '.ucm-archive-20250101T000000Z'
    earlier.mkdir(mode=0o700)
    (earlier / 'old.key').write_text('an earlier archive')
    held = tree(earlier)
    data, config = originals(box)
    box.wrap(other_fs=(box.data,))
    out = box.run()
    assert out.returncode == 0, (out.stdout, out.stderr)
    assert tree(earlier) == held
    exactly_once(box, data, config)
    readme = ' '.join((box.archive / 'README.txt').read_text().split())
    assert f'{earlier}' in readme and 'an earlier archiving' in readme


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


# -- without an interpreter, nothing moves -------------------------------------------

@pytest.mark.parametrize('interpreter', ['', 'missing', 'failing'])
def test_without_a_working_interpreter_nothing_moves(tmp_path, interpreter):
    """No interpreter to call rename(2) with, or one that fails: the run stops before
    anything is created or moved."""
    box = Box(tmp_path, python='stub')
    box.wrap()
    before = snapshot(box)
    path = {'': '', 'missing': str(tmp_path / 'no-python'), 'failing': '/bin/false'}[interpreter]
    out = box.run(interpreter=path)
    assert out.returncode == 1, (out.stdout, out.stderr)
    assert 'no interpreter to rename files with' in out.stdout and 'nothing was moved' in out.stdout
    assert 'was not started' in out.stdout
    assert snapshot(box) == before
    assert not box.parent.exists()
    assert 'could not be renamed' not in out.stdout


def test_without_an_interpreter_an_unfinished_attempt_is_left_as_it_is(tmp_path):
    """Killed right after a rename; then no interpreter: nothing is touched, exit 2."""
    box = Box(tmp_path, python='stub')
    data, config = originals(box)
    _killed_after_renaming(box, 'ucm.db')
    left = snapshot(box, box.parent)
    out = box.run(interpreter='')
    assert out.returncode == 2 and out.stderr == '', (out.stdout, out.stderr)
    assert 'no interpreter to rename files with' in out.stdout
    assert snapshot(box, box.parent) == left
    archived(box, box.run(), data, config)


# -- idempotent ----------------------------------------------------------------------

def test_a_second_run_finds_nothing_to_archive(tmp_path):
    box = Box(tmp_path)
    assert box.run().returncode == 0
    archived_tree = tree(box.parent)
    _database(box.data / 'ucm.db', _pivot_registry() + ['300_upgrade_from_2_254'])
    out = box.run()
    assert (out.returncode, out.stdout) == (0, '')
    assert tree(box.parent) == archived_tree


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
    for command in COMMANDS:
        for at in range(1, 200):
            box = Box(tmp_path / f'{command}-{at}', python='stub')
            box.wrap(fail=command, at=at, **_layout_args(box, layout))
            before = snapshot(box)
            data, config = originals(box)
            out = box.run()
            if int((box.state / 'count').read_text()) < at:
                archived(box, out, data, config, (command, at))
                break
            if out.returncode == 0:
                archived(box, out, data, config, (command, at))
                continue
            failed += 1
            assert out.returncode == 1, (command, at, out.stdout, out.stderr)
            assert snapshot(box) == before, (command, at, out.stdout)
            assert not box.parent.exists() or not any(box.parent.iterdir()), (command, at)
            assert 'was not started' in out.stdout, (command, at)
        else:
            pytest.fail(f'{command} never stopped failing')
    return failed


def _layout_args(box, layout):
    return {
        'one filesystem': {},
        'data and config on other filesystems': {'other_fs': (box.data, box.config)},
        'each kept directory a mount point': {'other_fs': tuple(box.data / d for d in KEPT)},
        'overlayfs': {'fstype': 'overlay'},
    }[layout]


@pytest.mark.parametrize('layout', ['one filesystem', 'data and config on other filesystems',
                                    'each kept directory a mount point', 'overlayfs'])
def test_a_failure_at_any_step_puts_everything_back(tmp_path, layout):
    assert _fail_everywhere(tmp_path, layout) > 5


def _killed_after_renaming(box, name, **wrap):
    """The run is killed right after rename(2) moved data/<name> into the archive."""
    box.wrap(**wrap)
    (box.bin / 'rename').write_text(
        f'#!/bin/sh\n{box.inner}/rename "$@" || exit 1\n'
        f'[ "$4" != {box.data}/{name} ] || kill -9 0\n')
    out = box.run()
    assert out.returncode == -9, (out.stdout, out.stderr)
    assert not os.path.lexists(box.data / name)
    box.wrap(**wrap)


ITEMS = {'file': 'ucm.db', 'directory': 'updates', 'link': 'current.key'}
BOTH = 'not put back to {src}, which exists again: keep one of the two, remove the other, then retry'


def _shape(path):
    """What `path` holds, whatever its kind: compared before and after."""
    if path.is_symlink():
        return ('link', os.readlink(path))
    if path.is_dir():
        return tree(path)
    return path.read_bytes()


def _remake(path, kind):
    """A new item of `kind` at `path`, unlike the archived one."""
    if kind == 'file':
        path.write_bytes(b'made again')
    elif kind == 'directory':
        path.mkdir()
        (path / 'g').write_text('made again')
    else:
        os.symlink('elsewhere', path)


def _gone(path):
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


LAYOUT_OF = {'one filesystem': {}, 'data on another filesystem': {'other_fs': ('data',)}}


def _wrap_of(box, layout):
    return {k: tuple(getattr(box, p) for p in v) for k, v in LAYOUT_OF[layout].items()}


@pytest.mark.parametrize('layout', list(LAYOUT_OF))
@pytest.mark.parametrize('kind', ITEMS)
@pytest.mark.parametrize('keep', ['source', 'archived'])
def test_a_source_made_again_between_two_attempts_keeps_both_until_one_is_chosen(tmp_path, layout, kind, keep):
    """Killed right after a rename, then the source made again (a service started by hand
    creates ucm.db): the retry keeps both sides whole, names the archived one, and exits 2;
    each of the two ways out the text gives ends in a finished archive."""
    box = Box(tmp_path, python='stub')
    wrap = _wrap_of(box, layout)
    name = ITEMS[kind]
    src = box.data / name
    dst = box.archive / 'data' / name if layout == 'one filesystem' else box.data / LOCAL / name
    data, config = originals(box)
    original = _shape(src)
    _killed_after_renaming(box, name, **wrap)
    _remake(src, kind)
    again = _shape(src)

    for _ in range(2):
        out = box.run()
        assert out.returncode == 2, (out.stdout, out.stderr)
        assert reported(out.stdout)[str(dst)] == BOTH.format(src=src), out.stdout
        # The directories holding it are not named: removing them loses that item
        assert named(out.stdout) == [str(dst)], out.stdout
        assert 'wait for your choice' in out.stdout or 'retrying alone will not' in out.stdout
        assert _shape(src) == again and _shape(dst) == original
        exactly_once(box, data, config, skip=(name,) + tuple(k for k in data if k.startswith(f'{name}/')))

    if keep == 'source':
        _gone(dst)
    else:
        _gone(src)
    out = box.run()
    assert out.returncode == 0, (out.stdout, out.stderr)
    assert _shape(box.archive / 'data' / name if layout == 'one filesystem' else box.data / LOCAL / name) == (
        again if keep == 'source' else original)
    assert not os.path.lexists(src)


@pytest.mark.parametrize('kind', ITEMS)
def test_a_source_made_again_during_an_attempt_keeps_both(tmp_path, kind):
    """The source is made again while a later step fails: the roll-back finds both sides,
    touches neither, and names the archived one."""
    box = Box(tmp_path, python='stub')
    name = ITEMS[kind]
    src, dst = box.data / name, box.archive / 'data' / name
    original = _shape(src)
    box.wrap()
    once = box.state / 'once'
    remake = {'file': f'printf "made again" > "{src}"',
              'directory': f'{REAL["mkdir"]} "{src}" && printf "made again" > "{src}/g"',
              'link': f'ln -s elsewhere "{src}"'}[kind]
    # The journal line of the configuration: every data item has been renamed by then
    (box.bin / 'tee').write_text(
        f'#!/bin/sh\nline=$(cat)\ncase $line in *"{box.archive}/config"*)\n'
        f'    [ -e {once} ] || {{ : > {once}; {remake}; exit 1; }} ;;\nesac\n'
        f'printf "%s\\n" "$line" | {REAL["tee"]} "$@"\n')
    out = box.run()
    assert out.returncode == 2, (out.stdout, out.stderr)
    assert reported(out.stdout)[str(dst)] == BOTH.format(src=src), out.stdout
    assert _shape(dst) == original and os.path.lexists(src)


@pytest.mark.parametrize('layout', list(LAYOUT_OF))
def test_an_item_archived_then_removed_by_hand_is_named_and_nothing_else_goes(tmp_path, layout):
    """Killed right after a rename, then the archived item removed by hand: the retry puts
    the others back, archives them, and says which one is at neither path."""
    box = Box(tmp_path, python='stub')
    wrap = _wrap_of(box, layout)
    data, config = originals(box)
    _killed_after_renaming(box, 'https_key.pem', **wrap)
    dst = box.archive / 'data' / 'https_key.pem' if layout == 'one filesystem' else box.data / LOCAL / 'https_key.pem'
    dst.unlink()
    out = box.run()
    assert out.returncode == 0, (out.stdout, out.stderr)
    assert f'{box.data}/https_key.pem is missing: an earlier attempt moved it to {dst}' in out.stdout
    exactly_once(box, data, config, skip=('https_key.pem',))
    assert not os.path.lexists(box.data / 'https_key.pem')


def test_a_rename_back_that_is_refused_is_named_with_where_it_goes(tmp_path):
    """The last step fails once every item is renamed; renaming ucm.db back is refused."""
    box = Box(tmp_path / 'count', python='stub')
    box.wrap(fail='rm', at=10 ** 6)
    assert box.run().returncode == 0
    last_rm = int((box.state / 'count').read_text())
    box = Box(tmp_path / 'box', python='stub')
    data, config = originals(box)
    box.wrap(fail='rm', at=last_rm, refused=(f'{box.archive}/data/ucm.db',))
    out = box.run()
    assert out.returncode == 2, (out.stdout, out.stderr)
    assert reported(out.stdout)[f'{box.archive}/data/ucm.db'] == f'not put back to {box.data}/ucm.db', out.stdout
    exactly_once(box, data, config)


def test_a_put_back_refused_twice_the_same_way_says_a_retry_will_not_help(tmp_path):
    """The first refusal says the next attempt tries again, the second one that retrying
    alone will not do; then, the cause gone, the retry converges."""
    box = Box(tmp_path / 'count', python='stub')
    box.wrap(fail='rm', at=10 ** 6, other_fs=(box.data,))
    assert box.run().returncode == 0
    last_rm = int((box.state / 'count').read_text())
    box = Box(tmp_path / 'box', python='stub')
    data, config = originals(box)
    stuck = f'{box.data}/{LOCAL}/updates'
    box.wrap(fail='rm', at=last_rm, other_fs=(box.data,), refused=(stuck,))
    first = box.run()
    assert first.returncode == 2, first.stdout
    assert 'next attempt tries again' in first.stdout and 'will not' not in first.stdout
    lines = reported(first.stdout)
    assert lines[stuck] == f'not put back to {box.data}/updates'
    box.wrap(other_fs=(box.data,), refused=(stuck,))
    second = box.run()
    assert second.returncode == 2, second.stdout
    assert 'same way at the previous attempt' in second.stdout and 'retrying alone will not' in second.stdout
    assert reported(second.stdout) == lines
    assert 'tries again' not in second.stdout
    exactly_once(box, data, config)
    box.wrap(other_fs=(box.data,))
    archived(box, box.run(), data, config)


def test_the_next_attempt_after_a_complete_roll_back_starts_over(tmp_path):
    box = Box(tmp_path, python='stub')
    data, config = originals(box)
    box.wrap(fail='tee', at=5, other_fs=(box.data,))
    assert box.run().returncode == 1
    box.wrap(other_fs=(box.data,))
    out = box.run()
    archived(box, out, data, config)
    assert 'did not complete' not in out.stdout


@pytest.mark.parametrize('edited', [False, True])
def test_a_fips_line_stuck_in_the_journal_says_whether_the_new_configuration_went(tmp_path, edited):
    """Killed on removing the journal; then the fips line cannot leave it. The new ucm.env
    went first, unless it was edited since: the text says which."""
    box = Box(tmp_path, python='stub')
    env = box.config / 'ucm.env'
    env.write_text(env.read_text() + 'UCM_FIPS_BUILD=1\n')
    box.wrap()
    (box.bin / 'rm').write_text(
        f'#!/bin/sh\nfor last; do :; done\ncase $last in */.journal) kill -9 0 ;; esac\n'
        f'exec {box.real("rm")} "$@"\n')
    assert box.run().returncode == -9
    if edited:
        env.write_text('UCM_FIPS_BUILD=1\nEDITED=1\n')
    box.wrap()
    (box.bin / 'mv').write_text('#!/bin/sh\nexit 1\n')
    out = box.run()
    assert out.returncode == 2, (out.stdout, out.stderr)
    said = reported(out.stdout)[f'{box.archive}/.journal']
    if edited:
        assert said == 'could not be updated, so nothing it lists was put back'
        assert env.read_text() == 'UCM_FIPS_BUILD=1\nEDITED=1\n'
    else:
        assert said == f'could not be updated once {env} was removed, so nothing it lists was put back'
        assert not env.exists()


# -- the guard itself ----------------------------------------------------------------

@pytest.mark.parametrize('command, args', [
    ('cp', '-a -- {data}/ucm.db {archive}/data/ucm.db'),
    ('mv', '-- {data}/ucm.db {archive}/data/ucm.db'),
    ('rm', '-rf -- {data}/updates'),
    ('rm', '-f -- {config}/ucm.env'),
])
def test_the_guard_fails_at_the_first_copy_move_or_removal_of_an_item(tmp_path, command, args):
    """What every test runs through: a cp, mv or rm naming an item fails the test."""
    box = Box(tmp_path, python='stub')
    box.wrap()
    call = f'{command} ' + args.format(data=box.data, config=box.config, archive=box.archive)
    out = subprocess.run([str(box.bin / command), *call.split()[1:]], capture_output=True)
    assert out.returncode == 1
    assert (box.state / 'forbidden').read_text() == call + '\n'
    with pytest.raises(AssertionError, match=command):
        box.run()


def test_the_guard_lets_the_journal_the_readme_and_the_written_ucm_env_go(tmp_path):
    box = Box(tmp_path, python='stub')
    box.wrap()
    box.archive.mkdir(parents=True)
    for name in ('.journal', '.journal.new', 'README.txt'):
        (box.archive / name).write_text('x')
    (box.config / 'ucm.env').write_text(FIPS)
    for call in (['mv', '--', f'{box.archive}/.journal.new', f'{box.archive}/.journal'],
                 ['rm', '-f', '--', f'{box.archive}/.journal', f'{box.archive}/README.txt'],
                 ['rm', '-f', '--', f'{box.config}/ucm.env']):
        assert subprocess.run([str(box.bin / call[0]), *call[1:]]).returncode == 0, call
    assert not (box.state / 'forbidden').exists()


# -- the packages --------------------------------------------------------------------

def _requires(spec, kind='Requires'):
    return {line.split(':', 1)[1].strip() for line in spec.splitlines() if line.startswith(f'{kind}:')}


def test_the_rpm_requires_what_the_archiving_and_post_run():
    """findmnt tells a mount point kept in place; %post walks the data with find to keep the
    local archives root's. On Debian these are essential packages, never named."""
    spec = (ROOT / 'packaging' / 'rpm' / 'ucm.spec').read_text()
    assert {'findutils', 'coreutils', '/usr/bin/findmnt'} <= {r.split()[0] for r in _requires(spec)}


def test_the_rpm_has_the_interpreter_while_post_runs():
    """%post renames with %{ucm_python}: Requires(post) makes it installed by then, on EL9
    (python3.12) as elsewhere (python3)."""
    spec = (ROOT / 'packaging' / 'rpm' / 'ucm.spec').read_text()
    for branch in spec.split('%endif', 1)[0].split('%else'):
        python = next(line.split()[2] for line in branch.splitlines() if line.startswith('%global ucm_python'))
        assert any(r.split()[0] == python for r in _requires(branch, 'Requires(post)')), python


def test_the_deb_has_the_interpreter_while_postinst_runs():
    """dpkg configures a package's Depends before running its postinst configure: python3
    is a Depends of the package, not a Recommends."""
    import re
    control = (ROOT / 'packaging' / 'debian' / 'control').read_text()
    depends = re.search(r'^Depends:(.*?)^\S', control, re.M | re.S).group(1)
    assert 'python3 (>= 3.12)' in depends


def test_the_kept_directories_are_those_the_packages_create():
    """RPM owns these directories and the DEB postinst creates them: the archive leaves them."""
    import re
    spec = (ROOT / 'packaging' / 'rpm' / 'ucm.spec').read_text()
    postinst = (ROOT / 'packaging' / 'debian' / 'postinst').read_text()
    assert {frozenset(m.split()) for m in re.findall(r'for d in ([a-z ]+); do', spec)} == {frozenset(KEPT)}
    assert re.findall(r'"\$UCM_DATA"/\{([a-z,]+)\}', postinst) and all(
        set(m.split(',')) == set(KEPT) for m in re.findall(r'"\$UCM_DATA"/\{([a-z,]+)\}', postinst))


# -- the journal holds whole lines only ----------------------------------------------

def _full_disk(box, target, cut):
    """tee writes the journal: from line `target` on, as on a full disk, each write stores
    the start of its line only (`cut` for the target, half of any other) and fails."""
    full, t, c = box.state / 'full', box.state / 'target', box.state / 'cut'
    t.write_text(target)
    c.write_text(cut)
    (box.bin / 'tee').write_text(
        f'#!/bin/sh\nline=$(cat)\nfor last; do :; done\n'
        f'if [ -e {full} ] || [ "$line" = "$(cat {t})" ]; then\n'
        f'    if [ -e {full} ]; then part=$(printf "%s" "$line" | head -c $((${{#line}} / 2)))\n'
        f'    else part=$(cat {c}); : > {full}; fi\n'
        f'    printf "%s" "$part" >> "$last"; echo "tee: No space left on device" >&2; exit 1\n'
        f'fi\nprintf "%s\\n" "$line" | {REAL["tee"]} "$@"\n')
    (box.bin / 'tee').chmod(0o755)


def _torn(box):
    return {
        'a rename cut at the data': (
            {'other_fs': (box.data,)},
            f'rename\t{box.data}/ucm.db\t{box.data}/{LOCAL}/ucm.db', f'rename\t{box.data}/ucm.db\t{box.data}'),
        'a local mkdir cut at the data': (
            {'other_fs': (box.data,)},
            f'mkdir\t{box.data}\t{box.data}/{LOCAL}', f'mkdir\t{box.data}\t{box.data}'),
        'a central mkdir cut at the archive': (
            {}, f'mkdir\t{box.data}/ca\t{box.archive}/data/ca', f'mkdir\t{box.data}/ca\t{box.archive}'),
        'a rename cut in its source': (
            {}, f'rename\t{box.data}/https_key.pem\t{box.archive}/data/https_key.pem', f'rename\t{box.data}/https_k'),
    }


@pytest.mark.parametrize('form', [
    'a rename cut at the data', 'a local mkdir cut at the data', 'a central mkdir cut at the archive',
    'a rename cut in its source'])
def test_a_journal_write_cut_short_by_a_full_disk_is_never_undone(tmp_path, form):
    """A full disk stores the start of a journal line: that line is no step. Each attempt
    while the disk stays full puts everything back and says so, touching nothing else;
    once space is freed, one attempt archives everything."""
    box = Box(tmp_path, python='stub')
    wrap, target, cut = _torn(box)[form]
    box.wrap(**wrap)
    _full_disk(box, target, cut)
    data, config = originals(box)
    before = snapshot(box)
    outs = []
    for _ in range(3):
        out = box.run()
        outs.append(out.stdout)
        assert out.returncode == 1, (form, out.stdout, out.stderr)
        assert 'Everything was put back in place' in out.stdout, out.stdout
        for wrong in ('exists again', 'could not be removed', 'is missing', 'not put back'):
            assert wrong not in out.stdout, (form, out.stdout)
        assert snapshot(box) == before, form
        assert not box.parent.exists() or not any(box.parent.iterdir()), form
    assert outs[1] == outs[2], outs
    box.wrap(**wrap)
    archived(box, box.run(), data, config, form)


def test_a_journal_line_torn_by_a_kill_is_ignored_by_the_next_attempt(tmp_path):
    """Killed while the line of a rename was half written (that rename never ran): the next
    attempt ignores that line, puts the rest back and archives everything."""
    box = Box(tmp_path, python='stub')
    box.wrap(other_fs=(box.data,))
    data, config = originals(box)
    target = f'rename\t{box.data}/ucm.db\t{box.data}/{LOCAL}/ucm.db'
    (box.bin / 'tee').write_text(
        f'#!/bin/sh\nline=$(cat)\nfor last; do :; done\n'
        f'[ "$line" != "{target}" ] || {{ printf "%s" "rename\t{box.data}/ucm.db\t{box.data}" >> "$last"; kill -9 0; }}\n'
        f'printf "%s\\n" "$line" | {REAL["tee"]} "$@"\n')
    out = box.run()
    assert out.returncode == -9, (out.stdout, out.stderr)
    assert not (box.archive / '.journal').read_text().endswith('\n')
    box.wrap(other_fs=(box.data,))
    out = box.run()
    for wrong in ('exists again', 'could not be removed', 'is missing'):
        assert wrong not in out.stdout, out.stdout
    archived(box, out, data, config)


@pytest.mark.parametrize('line', ['rename\t{data}/ucm.db', 'rename\t{data}/a\t{archive}/data/a\textra',
                                  'move\t{data}/a\t{archive}/data/a', 'mkdir\t\t{archive}/data',
                                  'failed\t{data}/a\tb'])
def test_a_journal_line_no_step_writes_stops_the_put_back_touching_nothing(tmp_path, line):
    """A whole line that is not a step with all its fields: the put-back stops before
    anything, exit 2, and names the journal."""
    box = Box(tmp_path, python='stub')
    data, config = originals(box)
    _killed_after_renaming(box, 'https_key.pem')
    journal = box.archive / '.journal'
    journal.write_text(journal.read_text() + line.format(data=box.data, archive=box.archive) + '\n')
    left, held = snapshot(box, box.parent), journal.read_text()
    out = box.run()
    assert out.returncode == 2, (out.stdout, out.stderr)
    assert 'not a whole step' in reported(out.stdout)[str(journal)], out.stdout
    assert 'retrying alone will not: do what the line says' in out.stdout
    assert snapshot(box, box.parent) == left and journal.read_text() == held
    journal.write_text(held.replace(line.format(data=box.data, archive=box.archive) + '\n', ''))
    archived(box, box.run(), data, config)


def test_a_journal_write_cut_short_once_leaves_the_journal_whole_for_what_follows(tmp_path):
    """One write is cut short (the disk full for a moment), then a put-back is refused: its
    failure is still recorded, so the next attempt says retrying alone will not help."""
    box = Box(tmp_path, python='stub')
    data, config = originals(box)
    stuck = f'{box.data}/{LOCAL}/updates'
    wrap = {'other_fs': (box.data,), 'refused': (stuck,)}
    box.wrap(**wrap)
    once = box.state / 'once'
    (box.bin / 'tee').write_text(
        f'#!/bin/sh\nline=$(cat)\nfor last; do :; done\n'
        f'if [ "$line" = "mkdir\t{box.config}\t{box.archive}/config" ] && [ ! -e {once} ]; then\n'
        f'    : > {once}; printf "%s" "mkdir\t{box.config}" >> "$last"; exit 1\nfi\n'
        f'printf "%s\\n" "$line" | {REAL["tee"]} "$@"\n')
    first = box.run()
    assert first.returncode == 2, (first.stdout, first.stderr)
    assert reported(first.stdout)[stuck] == f'not put back to {box.data}/updates'
    assert (box.archive / '.journal').read_text().endswith('\n')
    box.wrap(**wrap)
    second = box.run()
    assert second.returncode == 2 and 'same way at the previous attempt' in second.stdout, second.stdout
    box.wrap(other_fs=(box.data,))
    archived(box, box.run(), data, config)


# -- an item at neither path ---------------------------------------------------------

def test_an_item_whose_filesystem_is_gone_waits_for_it_and_is_never_called_missing(tmp_path):
    """Data on another filesystem, killed right after a rename beside itself; then that
    filesystem is absent (an empty directory in its place): the retry calls nothing missing,
    names what to mount, keeps the journal and exits 2. Mounted again, a retry archives all."""
    box = Box(tmp_path, python='stub')
    data, config = originals(box)
    _killed_after_renaming(box, 'https_key.pem', other_fs=(box.data,))
    mounted = tmp_path / 'mounted'
    box.data.rename(mounted)
    box.data.mkdir()
    left = snapshot(box)
    for _ in range(2):
        out = box.run()
        assert out.returncode == 2, (out.stdout, out.stderr)
        assert 'is missing:' not in out.stdout and 'in place again' not in out.stdout, out.stdout
        lines = reported(out.stdout)
        assert lines[f'{box.data}/{LOCAL}/https_key.pem'] == (
            f'not put back to {box.data}/https_key.pem: neither is there, as {box.data}/{LOCAL} '
            f'is absent: mount what holds it, then retry'), out.stdout
        assert snapshot(box) == left
        assert (box.archive / '.journal').is_file()
    box.data.rmdir()
    mounted.rename(box.data)
    out = box.run()
    assert 'is missing' not in out.stdout, out.stdout
    archived(box, out, data, config)


def test_an_item_removed_by_hand_is_named_and_never_said_to_be_back(tmp_path):
    """Its directory is there, the item in neither place: removed by hand. The retry names
    it, says the rest is back, and goes on."""
    box = Box(tmp_path, python='stub')
    _killed_after_renaming(box, 'https_key.pem')
    (box.archive / 'data' / 'https_key.pem').unlink()
    out = box.run()
    assert out.returncode == 0, (out.stdout, out.stderr)
    assert 'are in place again.' not in out.stdout, out.stdout
    assert ('everything else it could not put back is in place again; at neither path:\n'
            f'  {box.data}/https_key.pem\n') in out.stdout, out.stdout
