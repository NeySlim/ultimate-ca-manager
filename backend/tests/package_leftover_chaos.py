"""archive-leftovers.sh: from any state an interrupted or failed attempt leaves, a retry
without fault converges to one complete archive, every item at exactly one path, no journal.

Every file command the script runs is wrapped: one sequence numbers all their calls, and
a plan fails ('fail'), kills the run (SIGKILL to its process group, no clean-up: 'kill'),
or kills it right after the call ('done') at the calls it names. The journal is written
through tee and drop_line's mv, so its writes are calls like the others. The suite runs
once per layout, one test file each (test_package_leftover_retry_*.py), in parallel.
"""
import os
import random
import shutil

import pytest

from tests.test_package_leftover_archive import (
    FIPS, KEPT, Box, archived, exactly_once, named, snapshot)


CHAOS = ('mv', 'cp', 'rm', 'mkdir', 'rmdir', 'chmod', 'rename', 'tee')
LAYOUTS = {
    'one filesystem': lambda box: {},
    # The data on another disk, reached through a symbolic link
    'the data a symbolic link': lambda box: box.link(box.data) or {},
    'data and config are mount points': lambda box: {'other_fs': (box.data, box.config)},
    'a mount point inside the data': lambda box: {'other_fs': (box.data / 'updates',)},
    'each kept directory a mount point': lambda box: {'other_fs': tuple(box.data / d for d in KEPT)},
    'overlayfs': lambda box: {'fstype': 'overlay'},
    # DATABASE_PATH outside the data, on a filesystem of its own (the database/ branch)
    'a database outside the data': lambda box: {'other_fs': (box.place_database_outside(),)},
}
# The steps whose every call meets every fault: the archiving run's, and the put-back's
STEPS = {'rename', 'mkdir', 'rmdir', 'journal'}
FAULTS = ('fail', 'kill')
# A journal write stores half its line, then fails (a full disk) or the run is killed
TORN = ('short', 'torn')
# Pairs drawn per layout from every (fault i while archiving, fault j while putting back)
SEED, PAIRS = 20261114, 120


def _chaos(box, layout, refused=()):
    """Every file command counts its calls in one sequence and names them; the plan fails,
    kills, or kills right after the calls it names. A database placed outside the data is
    on a filesystem of its own."""
    wrap = LAYOUTS[layout](box)
    if box.outside is not None:
        wrap['other_fs'] = (*wrap.get('other_fs', ()), box.outside)
    box.wrap(refused=refused, **wrap)
    s = box.state
    for name in CHAOS:
        # Builtins only up to the command the wrapper ran: a run makes hundreds of these calls
        (box.bin / name).write_text(
            f'#!/bin/sh\nread n < {s}/count; n=$((n + 1)); echo $n > {s}/count\n'
            f'ifs=$IFS; IFS="\t"; echo "$n\t{name}\t$*" >> {s}/names; IFS=$ifs\n'
            f'mode=; while read -r k m; do [ "$k" != "$n" ] || mode=$m; done < {s}/plan\n'
            f'case $mode in\n'
            f'    fail) echo "{name}: injected failure" >&2; exit 1 ;;\n'
            f'    kill) kill -9 0 ;;\n'
            f'    done) {box.real(name)} "$@"; kill -9 0 ;;\n'
            f'    short|torn) line=$(cat); for last; do :; done\n'
            f'        printf "%s" "$line" | head -c $((${{#line}} / 2)) >> "$last"\n'
            f'        [ "$mode" = torn ] && kill -9 0; echo "{name}: No space left on device" >&2; exit 1 ;;\n'
            f'esac\nexec {box.real(name)} "$@"\n')
        (box.bin / name).chmod(0o755)


def _chaos_run(box, plan=()):
    (box.state / 'count').write_text('0')
    (box.state / 'names').write_text('')
    (box.state / 'plan').write_text(''.join(f'{n} {mode}\n' for n, mode in plan))
    out = box.run()
    return out, int((box.state / 'count').read_text())


def _chaos_box(tmp_path, layout, env='full', refused=False, outside=False):
    """env 'full': the ucm.env of an install, with UCM_FIPS_BUILD=1; 'fips only': that
    line alone, the very file the new configuration is. refused: a file nothing renames.
    outside: DATABASE_PATH places the database outside the data, on a mount of its own."""
    box = Box(tmp_path, python='stub')
    if outside:
        box.place_database_outside()
    path = box.config / 'ucm.env'
    path.write_text(FIPS if env == 'fips only' else path.read_text() + FIPS)
    _chaos(box, layout, refused=(f'{box.data}/https_key.pem',) if refused else ())
    data, config = tree_of(box)
    return box, data, config


def tree_of(box):
    from tests.test_package_leftover_archive import originals
    return originals(box)


def step(name, args):
    """The step a call is: a rename of an item, a mkdir, a rmdir, a journal write, or None."""
    if name == 'rename' and len(args) == 5:
        return 'rename'
    if name in ('mkdir', 'rmdir'):
        return name
    if name == 'tee' or (name == 'mv' and args[-1].endswith('/.journal')):
        return 'journal'
    return None


def received(run, n, mode):
    """{(step, mode)} of call `n` if `run` made it (its wrapper logs it before the fault):
    a fault planned at a call the run never reached is never counted."""
    return {(step(name, args), mode) for k, name, args in run.calls if k == n and step(name, args)}


class Run:
    """One run of the script: its output, how many file commands it called, and each
    call as (number, command, arguments)."""

    def __init__(self, box, out, count):
        self.out, self.count, self.parent = out, count, box.parent
        self.calls = []
        for line in (box.state / 'names').read_text().splitlines():
            n, name, *args = line.split('\t')
            self.calls.append((int(n), name, args))

    def steps(self, after=0):
        """{step: [call numbers]} of the calls after call `after`."""
        out = {}
        for n, name, args in self.calls:
            kind = step(name, args)
            if kind and n > after:
                out.setdefault(kind, []).append(n)
        return out


class Lab:
    """The boxes of one layout. A chain of runs (a plan per run, on one box) is replayed
    from the state its first run left, saved once: the runs that open each scenario
    ('fault at call i') are the same across the tests of a layout."""

    def __init__(self, root, layout, env='full', refused=False, outside=False):
        self.root, self.layout, self.env, self.refused, self.outside = root, layout, env, refused, outside
        self.first = {}
        self.n = 0

    def _first(self, plan):
        key = tuple(plan)
        if key not in self.first:
            self.n += 1
            box, data, config = _chaos_box(self.root / f'b{self.n}', self.layout, self.env, self.refused, self.outside)
            before = snapshot(box)
            run = Run(box, *_chaos_run(box, plan))
            saved = self.root / f's{self.n}'
            shutil.copytree(box.tmp, saved, symlinks=True)
            self.first[key] = (box, data, config, before, run, saved)
            return box, data, config, before, run
        box, data, config, before, run, saved = self.first[key]
        shutil.rmtree(box.tmp)
        shutil.copytree(saved, box.tmp, symlinks=True)
        return box, data, config, before, run

    def first_run(self, plan=()):
        """The run of `plan` on a new box (saved, never run twice)."""
        return self._first(plan)[4]

    def chain(self, *plans, check=None):
        """Runs each plan in turn on one box, `check(box, data, config, before, run)` after
        each but the last; returns (box, data, config, before, runs)."""
        box, data, config, before, run = self._first(plans[0])
        runs = [run]
        for plan in plans[1:]:
            if check:
                check(box, data, config, before, runs[-1])
            runs.append(Run(box, *_chaos_run(box, plan)))
        return box, data, config, before, runs


def while_failing(box, out, before, data, config, why):
    """Whatever a faulty run left: every original at exactly one path; exit 1 puts all back;
    exit 2 names real paths only."""
    exactly_once(box, data, config, why)
    if out.returncode == -9:
        return
    assert out.returncode in (0, 1, 2), (why, out.stdout, out.stderr)
    if out.returncode == 1:
        assert snapshot(box) == before, (why, out.stdout)
        assert not box.parent.exists() or not any(box.parent.iterdir()), (why, out.stdout)
    if out.returncode == 2:
        # Never an empty list: each path named is really there
        paths = named(out.stdout)
        assert paths, (why, out.stdout)
        for path in paths:
            assert os.path.lexists(path), (why, path, out.stdout)
    if out.returncode:
        assert 'was not started' in out.stdout, (why, out.stdout)


def converged(box, out, data, config, why):
    archived(box, out, data, config, why)
    assert (box.config / 'ucm.env').read_text() == FIPS, why


class ChaosSuite:
    """Subclassed once per layout, which sets `layout`."""

    # Every fault at every step: minutes per layout, left to the suites
    pytestmark = pytest.mark.slow
    layout = None
    env = 'full'

    @pytest.fixture(scope='class')
    def lab(self, tmp_path_factory):
        return Lab(tmp_path_factory.mktemp('lab'), self.layout, self.env)

    @pytest.fixture(scope='class')
    def outside_lab(self, tmp_path_factory):
        return Lab(tmp_path_factory.mktemp('outside'), self.layout, self.env, outside=True)

    def _scenario(self, lab, first, second=None):
        """`first` = (call, mode) of the archiving run; `second` = (call, mode) of the same
        run after a failure (its roll-back), or of the next run after a kill. Then a clean run."""
        why = (self.layout, first, second)
        if second and first[1] == 'fail':
            plans = ([first, second], ())
        elif second:
            plans = ([first], [second], ())
        else:
            plans = ([first], ())
        box, data, config, before, runs = lab.chain(*plans, check=lambda box, data, config, before, run:
                                                    while_failing(box, run.out, before, data, config, why))
        converged(box, runs[-1].out, data, config, why)
        return runs

    def _calls(self, lab, plan=()):
        return lab.first_run(plan).count

    def test_a_retry_converges_after_one_fault_at_any_call(self, lab):
        """Each call of the archiving run fails, or kills it, in turn; then a run without fault."""
        calls = self._calls(lab)
        assert calls > 20
        # Its renames, directories made and journal writes are among these calls
        assert {'rename', 'mkdir', 'journal'} <= set(lab.first_run().steps()), lab.first_run().steps()
        tees = {n for n, name, _a in lab.first_run().calls if name == 'tee'}
        assert tees
        for at in range(1, calls + 1):
            for mode in FAULTS + (TORN if at in tees else ()):
                self._scenario(lab, (at, mode))

    def test_every_step_of_a_put_back_meets_every_fault(self, lab):
        """Each kind of step a roll-back takes (renames back, directories removed, the
        journal updated) fails, kills, or kills right after, once at least, a journal write
        is also cut short; counted on the calls the faulty runs really made."""
        backs = {}
        for at in range(1, self._calls(lab) + 1):
            run = lab.first_run([(at, 'fail')])
            for n, name, args in run.calls:
                if n > at and step(name, args):
                    backs.setdefault(step(name, args), []).append((at, n, name))
        assert {'rename', 'rmdir', 'journal'} <= set(backs), set(backs)
        covered = set()
        for kind, pairs in backs.items():
            for i, mode in enumerate(('fail', 'kill', 'done') + (TORN if kind == 'journal' else ())):
                fit = [p for p in pairs if mode not in TORN or p[2] == 'tee']
                at, n, _name = fit[(i * 7) % len(fit)]
                covered |= received(self._scenario(lab, (at, 'fail'), (n, mode))[0], n, mode)
        assert {(k, m) for k in ('rename', 'rmdir', 'journal') for m in ('fail', 'kill', 'done')} <= covered, covered
        assert {('journal', m) for m in TORN} <= covered, covered

    def test_a_mount_point_is_never_renamed_nor_removed(self, lab):
        """A mount point kept in place is a directory of the archiving, never an item: no
        rename or removal ever names it, at the archiving or at a put-back."""
        lab.first_run()
        box = lab.first[()][0]
        mounts = {str(p) for p in LAYOUTS[self.layout](box).get('other_fs', ())}
        runs = [lab.first_run()] + [lab.first_run([(at, 'fail')]) for at in range(1, self._calls(lab) + 1)]
        touched = [(n, name, args) for r in runs for n, name, args in r.calls
                   if name in ('rename', 'rm', 'mv', 'cp', 'rmdir')
                   and any(a.rstrip('/') in mounts for a in args)]
        assert touched == []

    def test_a_retry_converges_after_a_fault_while_putting_back(self, lab):
        """Pairs (fault i while archiving, fault j while putting back or in the next run), drawn
        from the full product with a fixed seed, then a run without fault."""
        calls = self._calls(lab)
        product = []
        for at in range(1, calls + 1):
            after_fail = self._calls(lab, [(at, 'fail')])
            product += [((at, 'fail'), (j, m)) for j in range(at + 1, after_fail + 1) for m in FAULTS]
        for at in range(1, calls + 1):
            again = lab.chain([(at, 'kill')], ())[4][1].count
            product += [((at, 'kill'), (j, m)) for j in range(1, again + 1) for m in FAULTS]
        assert len(product) > PAIRS
        draw = random.Random(f'{SEED}-{self.layout}')  # noqa: S311 - a fixed seed, a replayable draw
        for first, second in draw.sample(product, PAIRS):
            self._scenario(lab, first, second)

    def test_a_retry_converges_after_a_kill_right_after_any_rename(self, lab):
        """Killed once rename(2) moved an item into an archive, or back out of it."""
        for at in lab.first_run().steps().get('rename', []):
            self._scenario(lab, (at, 'done'))
        backs = set()
        for at in range(1, self._calls(lab) + 1):
            for back in lab.first_run([(at, 'fail')]).steps(after=at).get('rename', []):
                backs.add((at, back))
        assert backs
        for at, back in sorted(backs)[::4]:
            self._scenario(lab, (at, 'fail'), (back, 'done'))

    def test_a_retry_converges_after_any_fault_once_an_archived_item_was_removed(self, lab):
        """Killed right after data/https_key.pem was renamed, then the archived one removed by
        hand: each call of the next attempt fails, or kills it, in turn; then a run without fault."""
        # The last rename of it is the one that moved it: the one before, if any, was refused
        kill = [n for n, name, args in lab.first_run().calls
                if step(name, args) == 'rename' and args[3].endswith('/data/https_key.pem')][-1]

        def start():
            box, data, config, before, _run = lab._first([(kill, 'done')])
            src = f'{box.data}/https_key.pem'
            line = [l for l in (box.archive / '.journal').read_text().splitlines()
                    if l.startswith(f'rename\t{src}\t')][-1]
            os.unlink(line.split('\t')[2])
            data = {k: v for k, v in data.items() if k != 'https_key.pem'}
            before = {p: dict(t) for p, t in before.items()}
            del before[str(box.data)]['https_key.pem']
            return box, data, config, before

        box = start()[0]
        calls = Run(box, *_chaos_run(box)).count
        assert calls > 20
        for at in range(1, calls + 1):
            for mode in FAULTS:
                why = (self.layout, 'removed', at, mode)
                box, data, config, before = start()
                run = Run(box, *_chaos_run(box, [(at, mode)]))
                while_failing(box, run.out, before, data, config, why)
                converged(box, Run(box, *_chaos_run(box)).out, data, config, why)

    def _absent_data_then_any_fault(self, lab, empty):
        """Killed once the journal names the first rename of data/https_key.pem, before it ran;
        then the data not mounted (gone, or its mount point left empty): each attempt exits 2,
        calls nothing missing, removes no line, writes nothing there. The data back, each call
        of the next attempt fails, or kills it, in turn; then a run without fault."""
        kill = [n for n, name, args in lab.first_run().calls
                if step(name, args) == 'rename' and args[3].endswith('/data/https_key.pem')][0]

        def absent(box):
            aside = box.tmp / 'unmounted'
            os.rename(box.data, aside)
            if empty:
                box.data.mkdir()
            journal = box.archive / '.journal'
            lines = set(journal.read_text().splitlines())
            out = Run(box, *_chaos_run(box)).out
            assert out.returncode == 2 and 'is missing' not in out.stdout, (self.layout, out.stdout)
            assert 'mount what holds it' in out.stdout, (self.layout, out.stdout)
            assert lines <= set(journal.read_text().splitlines()), self.layout
            if empty:
                assert list(box.data.iterdir()) == [], self.layout
                box.data.rmdir()
            os.rename(aside, box.data)

        box = lab._first([(kill, 'kill')])[0]
        absent(box)
        absent(box)
        calls = Run(box, *_chaos_run(box)).count
        assert calls > 20
        for at in range(1, calls + 1):
            for mode in FAULTS:
                why = (self.layout, 'empty' if empty else 'absent', at, mode)
                box, data, config, before, _run = lab._first([(kill, 'kill')])
                absent(box)
                run = Run(box, *_chaos_run(box, [(at, mode)]))
                while_failing(box, run.out, before, data, config, why)
                converged(box, Run(box, *_chaos_run(box)).out, data, config, why)

    def test_a_retry_waits_for_absent_data_then_converges_after_any_fault(self, lab):
        self._absent_data_then_any_fault(lab, empty=False)

    def test_a_retry_waits_for_an_empty_mount_point_then_converges_after_any_fault(self, lab):
        self._absent_data_then_any_fault(lab, empty=True)

    def test_a_retry_waits_for_a_database_outside_left_unmounted_then_converges_after_any_fault(self, outside_lab):
        """The database on a mount of its own, killed once the journal names its first rename,
        before it ran; then unmounted, its mount point left empty: each attempt exits 2, says to
        mount it, calls nothing missing, removes no line, writes nothing there. Mounted again,
        each call of the next attempt fails, or kills it, in turn; then a run without fault."""
        lab = outside_lab
        kill = [n for n, name, args in lab.first_run().calls
                if step(name, args) == 'rename' and args[3].endswith('/srv/db/pki.db')][0]

        def unmounted(box):
            aside = box.unmount(box.outside)
            journal = box.archive / '.journal'
            lines = set(journal.read_text().splitlines())
            out = Run(box, *_chaos_run(box)).out
            assert out.returncode == 2 and 'is missing' not in out.stdout, (self.layout, out.stdout)
            assert f'{box.outside}: not mounted: mount it again' in out.stdout, (self.layout, out.stdout)
            assert lines <= set(journal.read_text().splitlines()), self.layout
            assert list(box.outside.iterdir()) == [], self.layout
            box.remount(box.outside, aside)

        box = lab._first([(kill, 'kill')])[0]
        unmounted(box)
        unmounted(box)
        calls = Run(box, *_chaos_run(box)).count
        assert calls > 20
        for at in range(1, calls + 1):
            for mode in FAULTS:
                why = (self.layout, 'outside unmounted', at, mode)
                box, data, config, before, _run = lab._first([(kill, 'kill')])
                unmounted(box)
                run = Run(box, *_chaos_run(box, [(at, mode)]))
                while_failing(box, run.out, before, data, config, why)
                converged(box, Run(box, *_chaos_run(box)).out, data, config, why)

    def test_only_the_journal_is_ever_moved_and_nothing_copied(self, lab):
        """cp never runs; mv only renames the journal or the README into place (the guard of
        Box fails any other call that names an item, whatever the run)."""
        runs = [lab.first_run()] + [lab.chain([(at, 'fail')], ())[4][-1]
                                    for at in range(1, self._calls(lab) + 1, 3)]
        assert all(r.out.returncode in (0, 1, 2) for r in runs)
        assert not any(name == 'cp' for r in runs for _n, name, _a in r.calls)
        moves = [args[-2:] for r in runs for _n, name, args in r.calls if name == 'mv']
        assert all(dst.endswith('/.journal') and src == f'{dst}.new'
                   or dst.endswith('/README.txt') and src == f'{dst[:-len("README.txt")]}.README.txt.new'
                   for src, dst in moves), moves


class NothingRenamesSuite:
    """Subclassed once per layout: data/https_key.pem is refused rename(2) into the archive
    and beside itself, so every attempt fails and puts everything back."""

    pytestmark = pytest.mark.slow
    layout = None

    @pytest.fixture(scope='class')
    def lab(self, tmp_path_factory):
        return Lab(tmp_path_factory.mktemp('lab'), self.layout, refused=True)

    def test_every_fault_still_puts_everything_back(self, lab):
        """Failed or killed at any call, the next attempt puts everything back (exit 1); once
        the file can be renamed, a run archives everything."""
        run = lab.first_run()
        assert run.out.returncode == 1 and 'https_key.pem could not be renamed' in run.out.stdout, run.out.stdout
        for at in range(1, run.count + 1):
            for mode in FAULTS:
                why = (self.layout, at, mode)
                box, data, config, before, runs = lab.chain([(at, mode)], (), check=lambda box, data, config, before, r:
                                                            while_failing(box, r.out, before, data, config, why))
                assert runs[1].out.returncode == 1, (why, runs[1].out.stdout)
                assert snapshot(box) == before, why
        (box.state / 'refused').write_text('')
        converged(box, box.run(), data, config, 'renamed at last')
