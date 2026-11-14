"""archive-leftovers.sh: from any state an interrupted or failed attempt leaves, a retry
without fault converges to one complete archive, no file lost or duplicated, no journal.

Every file command the script runs is wrapped: one sequence numbers all their calls, and
a plan fails or kills the run (SIGKILL to its process group, no clean-up) at given calls,
or kills a copy as if cut short ('torn', 'trunc', 'meta': see _chaos). The suite runs once
per layout, one test file each (test_package_leftover_retry_*.py), so they run in parallel.
"""
import os
import random
import shutil

import pytest

from tests.test_package_leftover_archive import KEPT, PART, STAMP, Box, files, named, snapshot, tree, whole


CHAOS = ('mv', 'cp', 'rm', 'mkdir', 'rmdir', 'chmod', 'rename')
LAYOUTS = {
    'one filesystem': lambda box: (),
    'data and config are mount points': lambda box: (box.data, box.config),
    'a mount point inside the data': lambda box: (box.data / 'updates',),
}
# Pairs drawn per layout from every (fault i while archiving, fault j while putting back)
SEED, PAIRS = 20261114, 120


def _chaos(box, layout):
    """Every file command counts its calls in one sequence and names them; the plan fails
    ('fail') or kills the whole run without any clean-up ('kill') at the calls it names.
    On a cp, 'torn', 'trunc', 'meta' and 'mode' kill it as a copy cut short would leave its
    target: other content, part of the content, or the whole content before its date or its
    mode, of the first file in it; 'top' before the mode of the copied directory itself.
    'alone' leaves the date wrong and fails that cp only, the run goes on; 'late' fails a
    cp that copied everything; 'done' kills the run right after the call."""
    box.wrap(other_fs=LAYOUTS[layout](box))
    s = box.state
    find, sort, head = (shutil.which(t) for t in ('find', 'sort', 'head'))
    for name in CHAOS:
        # mv and rename run what Box.wrap set: the journal-only mv, the rename(2) that
        # refuses to cross a mount; every other command the real one
        target = box.inner / name if name in ('mv', 'rename') else shutil.which(name)
        # Builtins only up to the real command: a run makes hundreds of these calls
        (box.bin / name).write_text(
            f'#!/bin/sh\nread n < {s}/count; n=$((n + 1)); echo $n > {s}/count\n'
            f'ifs=$IFS; IFS="\t"; echo "$n\t{name}\t$*" >> {s}/names; IFS=$ifs\n'
            f'mode=; while read -r k m; do [ "$k" != "$n" ] || mode=$m; done < {s}/plan\n'
            f'case $mode in\n'
            f'    fail) echo "{name}: injected failure" >&2; exit 1 ;;\n'
            f'    kill) kill -9 0 ;;\n'
            f'    done) {target} "$@"; kill -9 0 ;;\n'
            f'    torn|trunc|meta|mode|top|alone|late)\n'
            f'        if [ {name} = cp ]; then\n'
            f'            {shutil.which(name)} "$@"; for last; do :; done\n'
            f'            cut=$({find} "$last" -type f | {sort} | {head} -n 1)\n'
            f'            case $mode in\n'
            f'                torn) [ -z "$cut" ] || printf torn > "$cut" ;;\n'
            f'                trunc) [ -z "$cut" ] || {shutil.which("truncate")} -s 1 "$cut" ;;\n'
            f'                meta|alone) [ -z "$cut" ] || {shutil.which("touch")} -d @5 "$cut" ;;\n'
            f'                mode) [ -z "$cut" ] || {shutil.which("chmod")} 0604 "$cut" ;;\n'
            f'                top) [ -L "$last" ] || [ ! -d "$last" ] || {shutil.which("chmod")} 0705 "$last" ;;\n'
            f'            esac\n'
            f'        fi\n'
            f'        case $mode in alone|late) exit 1 ;; esac\n'
            f'        kill -9 0 ;;\n'
            f'esac\nexec {target} "$@"\n')
        (box.bin / name).chmod(0o755)


def _chaos_run(box, plan=()):
    (box.state / 'count').write_text('0')
    (box.state / 'names').write_text('')
    (box.state / 'plan').write_text(''.join(f'{n} {mode}\n' for n, mode in plan))
    out = box.run()
    return out, int((box.state / 'count').read_text())


def _chaos_box(tmp_path, layout, env='full', refused=False):
    """env 'full': the ucm.env of an install, with UCM_FIPS_BUILD=1; 'fips only': that
    line alone, the very file the new configuration is. refused: the kernel refuses to
    rename a file, a directory and a link that would be renamed (REFUSED)."""
    box = Box(tmp_path, python='stub')
    path = box.config / 'ucm.env'
    path.write_text('UCM_FIPS_BUILD=1\n' if env == 'fips only' else path.read_text() + 'UCM_FIPS_BUILD=1\n')
    # A file, a directory and a link in updates: each kind of copy in every layout that copies
    (box.data / 'updates' / 'manifest.json').write_text('{}')
    os.symlink('nested', box.data / 'updates' / 'latest')
    _chaos(box, layout)
    if refused:
        (box.state / 'refused').write_text(''.join(f'{box.data}/{name}\n' for name in _refused(layout)))
    return box, whole(box.data, _kept(layout)), whole(box.config)


def _refused(layout):
    """A file, a directory and a link moved as items in `layout`."""
    if layout == 'a mount point inside the data':
        return ('https_key.pem', 'updates/nested', 'updates/latest')
    return ('https_key.pem', 'updates', 'current.key')


def _kept(layout):
    """The directories that stay in place, recreated empty in the archive."""
    return KEPT + (['updates'] if layout == 'a mount point inside the data' else [])


class Run:
    """One run of the script: its output, how many file commands it called, and each
    call as (number, command, arguments)."""

    def __init__(self, box, out, count):
        self.out, self.count, self.parent = out, count, box.parent
        self.tops = {'data': f'{box.data}/', 'config': f'{box.config}/'}
        self.calls = []
        for line in (box.state / 'names').read_text().splitlines():
            n, name, *args = line.split('\t')
            self.calls.append((int(n), name, args))

    def item(self, path):
        """(top, path relative to it) of a path in the data or the configuration, or of the
        temporary the script names beside it."""
        for top, prefix in self.tops.items():
            if path.startswith(prefix):
                return top, path[len(prefix):].rstrip('/').removesuffix('/.').removesuffix(PART)
        return None, path

    def kind(self, n):
        """What cp call n copies: 'file', 'dir' or 'link' (its arguments: -a -- from to)."""
        args = dict((c[0], c[2]) for c in self.calls)[n]
        top, rel = next(self.item(a) for a in args[2:] if self.item(a)[0])
        return self.shape[top][rel][0], (top, rel)


class Lab:
    """The boxes of one layout. A chain of runs (a plan per run, on one box) is replayed
    from the state its first run left, saved once: the runs that open each scenario
    ('fault at call i') are the same across the tests of a layout."""

    def __init__(self, root, layout, env='full', refused=False):
        self.root, self.layout, self.env, self.refused = root, layout, env, refused
        self.first = {}
        self.n = 0

    def _new(self):
        self.n += 1
        box, data, config = _chaos_box(self.root / f'b{self.n}', self.layout, self.env, self.refused)
        return box, data, config, snapshot(box)

    def _first(self, plan):
        key = tuple(plan)
        if key not in self.first:
            box, data, config, before = self._new()
            out, count = _chaos_run(box, plan)
            run = Run(box, out, count)
            run.shape = {'data': before[str(box.data)], 'config': before[str(box.config)]}
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
            runs[-1].shape = run.shape
        return box, data, config, before, runs


def _nothing_lost(box, data, config, why):
    """Every original file, link and moved directory is whole (attributes included) in its
    place or in an archive."""
    archives = [a for a in box.parent.iterdir()] if box.parent.exists() else []
    for top, originals, sub in ((box.data, data, 'data'), (box.config, config, 'config')):
        here = tree(top)
        there = [tree(a / sub) for a in archives]
        for rel, entry in originals.items():
            assert here.get(rel) == entry or any(t.get(rel) == entry for t in there), (why, sub, rel)


def _while_failing(box, out, before, data, config, why):
    """_nothing_lost compares real paths only: an original kept under a temporary alone
    counts as lost."""
    if out.returncode == -9:
        _nothing_lost(box, data, config, why)
        return
    assert out.returncode in (0, 1, 2), (why, out.stdout, out.stderr)
    _nothing_lost(box, data, config, why)
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


def _temporaries(box):
    """The script's temporaries left anywhere it writes."""
    return [str(p) for top in (box.data, box.config, box.parent) if top.exists()
            for p in top.rglob('*') if p.name.endswith(PART)]


def _converged(box, out, data, config, layout, why):
    assert out.returncode == 0, (why, out.stdout, out.stderr)
    assert _temporaries(box) == [], why
    assert [a.name for a in box.parent.iterdir()] == [STAMP], (why, out.stdout)
    assert whole(box.archive / 'data', _kept(layout)) == data, why
    assert whole(box.archive / 'config') == config, why
    assert sorted(a.name for a in box.archive.iterdir()) == ['README.txt', 'config', 'data'], why
    kept = _kept(layout)
    assert sorted(p.name for p in box.data.iterdir()) == sorted(kept), why
    assert all(not any((box.data / d).iterdir()) for d in kept), why
    assert files(box.config) == {'ucm.env': files(box.config)['ucm.env']}, why
    assert (box.config / 'ucm.env').read_text() == 'UCM_FIPS_BUILD=1\n', why


CUT_SHORT = ('torn', 'trunc', 'meta', 'mode', 'top', 'alone')


def _copies(run, put_back=False):
    """The calls of `run` that were a cp; with put_back, those out of the archive."""
    out = []
    for n, name, args in run.calls:
        source = args[args.index('--') + 1] if '--' in args else ''
        if name == 'cp' and (not put_back or source.startswith(f'{run.parent}/')):
            out.append(n)
    return out


def _renames(run, put_back=False):
    """The calls of `run` that were a rename; with put_back, those out of the archive (a copy
    renamed aside within it is not one)."""
    return [n for n, name, args in run.calls if name == 'rename' and len(args) == 5
            and (not put_back or (args[3].startswith(f'{run.parent}/')
                                  and not args[4].startswith(f'{run.parent}/')))]


def _steps(run):
    """The calls of `run` through a temporary, by kind: a copy renamed into the archive, a
    path renamed aside before it goes, a put-back renamed into place, a temporary removed."""
    out = {}
    for n, name, args in run.calls:
        if name == 'rename' and len(args) == 5 and args[4].endswith(PART):
            kind = 'aside'
        elif name == 'rename' and len(args) == 5 and args[3].endswith(PART):
            kind = 'into archive' if args[3].startswith(f'{run.parent}/') else 'put back'
        elif name == 'rm' and args[-1].endswith(PART):
            kind = 'temporary removed'
        else:
            continue
        out.setdefault(kind, []).append(n)
    return out


class ChaosSuite:
    """Subclassed once per layout, which sets `layout`."""

    layout = None
    env = 'full'

    @pytest.fixture(scope='class')
    def lab(self, tmp_path_factory):
        return Lab(tmp_path_factory.mktemp('lab'), self.layout, self.env)

    def _scenario(self, lab, first, second):
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
                                                    _while_failing(box, run.out, before, data, config, why))
        _converged(box, runs[-1].out, data, config, self.layout, why)

    def _calls(self, lab, plan=()):
        return lab.first_run(plan).count

    def test_a_retry_converges_after_one_fault_at_any_call(self, lab):
        """Each call of the archiving run fails, or kills it, in turn; then a run without fault."""
        calls = self._calls(lab)
        assert calls > 20
        # Every step through a temporary is among these calls, wherever items are copied
        steps = set(_steps(lab.first_run()))
        assert steps == (set() if self.layout == 'one filesystem' else
                         {'into archive', 'aside', 'temporary removed'}), steps
        for at in range(1, calls + 1):
            for mode in ('fail', 'kill'):
                self._scenario(lab, (at, mode), None)

    def test_every_step_through_a_temporary_of_a_put_back_meets_every_fault(self, lab):
        """Fails, kills, or kills right after, each kind of step through a temporary that a
        roll-back takes (test_a_retry_converges_after_one_fault_at_any_call covers the
        archiving run's)."""
        if self.layout == 'one filesystem':
            assert not _copies(lab.first_run())
            return
        backs = {}
        for at in range(1, self._calls(lab) + 1):
            for kind, calls in _steps(lab.first_run([(at, 'fail')])).items():
                backs.setdefault(kind, []).extend((at, n) for n in calls if n > at)
        assert {'put back', 'aside', 'temporary removed'} <= set(backs), set(backs)
        covered = set()
        for kind, pairs in backs.items():
            for i, mode in enumerate(('fail', 'kill', 'done')):
                at, n = pairs[(i * 7) % len(pairs)]
                self._scenario(lab, (at, 'fail'), (n, mode))
                covered.add((kind, mode))
        assert covered == {(k, m) for k in backs for m in ('fail', 'kill', 'done')}

    def test_a_mount_point_is_never_renamed_nor_removed(self, lab):
        """A mount point kept in place is a directory of the archiving, never an item: no
        rename, removal or temporary ever names it, at the archiving or at a put-back."""
        lab.first_run()
        box = lab.first[()][0]
        mounts = {str(p) for p in LAYOUTS[self.layout](box)}
        assert bool(mounts) == (self.layout != 'one filesystem')
        runs = [lab.first_run()] + [lab.first_run([(at, 'fail')]) for at in range(1, self._calls(lab) + 1)]
        touched = [(n, name, args) for r in runs for n, name, args in r.calls
                   if name in ('rename', 'rm', 'mv', 'cp')
                   and any(a.rstrip('/').removesuffix(PART) in mounts for a in args)]
        assert touched == []

    def test_a_retry_converges_after_a_fault_while_putting_back(self, lab):
        """Pairs (fault i while archiving, fault j while putting back or in the next run), drawn
        from the full product with a fixed seed, then a run without fault."""
        calls = self._calls(lab)
        product = []
        for at in range(1, calls + 1):
            after_fail = self._calls(lab, [(at, 'fail')])
            product += [((at, 'fail'), (j, m)) for j in range(at + 1, after_fail + 1)
                        for m in ('fail', 'kill')]
        for at in range(1, calls + 1):
            again = lab.chain([(at, 'kill')], ())[4][1].count
            product += [((at, 'kill'), (j, m)) for j in range(1, again + 1) for m in ('fail', 'kill')]
        assert len(product) > PAIRS
        draw = random.Random(f'{SEED}-{self.layout}')  # noqa: S311 - a fixed seed, a replayable draw
        for first, second in draw.sample(product, PAIRS):
            self._scenario(lab, first, second)

    def test_a_retry_converges_after_any_copy_of_the_archiving_is_cut_short(self, lab):
        run = lab.first_run()
        kinds = {run.kind(at)[0] for at in _copies(run)}
        assert kinds == ({'file', 'dir', 'link'} if self.layout != 'one filesystem' else set())
        for at in _copies(run):
            for mode in CUT_SHORT:
                self._scenario(lab, (at, mode), None)

    def _put_backs(self, lab):
        """Every (fault i of the archiving run, cp its put-back then runs, what it copies:
        (kind, item))."""
        if not _copies(lab.first_run()):
            # No copy in the archiving run: no copy line, so no put-back ever copies
            assert self.layout == 'one filesystem'
            return []
        pairs = []
        for at in range(1, self._calls(lab) + 1):
            run = lab.first_run([(at, 'fail')])
            pairs += [(at, back, *run.kind(back)) for back in _copies(run, put_back=True)]
        assert pairs
        return pairs

    def test_a_retry_converges_after_any_copy_of_the_put_back_is_cut_short(self, lab):
        """Every cp of every put-back is cut short, the ways in turn along the pairs of each
        kind of copy (file, directory, link), as many times as it takes for every way to
        meet every kind; then a run without fault."""
        pairs = self._put_backs(lab)
        by_kind, covered = {}, set()
        for at, back, kind, _item in pairs:
            by_kind.setdefault(kind, []).append((at, back))
        for kind, of_kind in by_kind.items():
            for n in range(max(len(of_kind), len(CUT_SHORT))):
                at, back = of_kind[n % len(of_kind)]
                mode = CUT_SHORT[n % len(CUT_SHORT)]
                covered.add((kind, mode))
                self._scenario(lab, (at, 'fail'), (back, mode))
        kinds = {'file', 'dir', 'link'} if pairs else set()
        assert covered == {(kind, mode) for kind in kinds for mode in CUT_SHORT}, covered

    def test_a_put_back_whose_copy_failed_is_never_reported_as_done(self, lab):
        for at, back, *_ in self._put_backs(lab)[::3]:
            why = (self.layout, at, back)

            def check(box, data, config, before, run, why=why):
                assert run.out.returncode == 2, (why, run.out.stdout, run.out.stderr)
                _while_failing(box, run.out, before, data, config, why)
            box, data, config, before, runs = lab.chain([(at, 'fail'), (back, 'late')], (), check=check)
            _converged(box, runs[1].out, data, config, self.layout, why)

    def test_a_retry_converges_after_a_kill_right_after_any_rename(self, lab):
        """Killed once rename(2) moved an item into the archive, or back out of it."""
        for at in _renames(lab.first_run()):
            self._scenario(lab, (at, 'done'), None)
        backs = set()
        for at in range(1, self._calls(lab) + 1):
            for back in _renames(lab.first_run([(at, 'fail')]), put_back=True):
                backs.add((at, back))
        # Every rename is refused when the data and configuration are mounts of their own
        assert bool(backs) == (self.layout != 'data and config are mount points')
        for at, back in sorted(backs)[::4]:
            self._scenario(lab, (at, 'fail'), (back, 'done'))

    def test_mv_never_moves_an_item(self, lab):
        """mv falls back on a copy outside the journal: only the journal is ever mv'd (the
        mv of Box.wrap fails and records any other call)."""
        runs = [lab.first_run()] + [lab.chain([(at, 'fail')], ())[4][-1]
                                    for at in range(1, self._calls(lab) + 1, 3)]
        assert all(r.out.returncode in (0, 1, 2) for r in runs)
        assert not any(name == 'mv' and not args[1].endswith('/.journal.new')
                       for r in runs for _n, name, args in r.calls)
        assert not (lab.first[()][0].state / 'mv-items').exists()


class RefusedRenameSuite:
    """Subclassed once per layout: a file, a directory and a link are refused rename(2)
    (EXDEV), at the archiving and at the put-back alike."""

    layout = None

    @pytest.fixture(scope='class')
    def lab(self, tmp_path_factory):
        return Lab(tmp_path_factory.mktemp('lab'), self.layout, refused=True)

    def test_each_refused_item_is_archived_by_a_verified_copy(self, lab):
        run = lab.first_run()
        box = lab.first[()][0]
        _converged(box, run.out, *lab.first[()][1:3], self.layout, 'refused')
        copied = {run.item(args[2])[1] for _n, name, args in run.calls if name == 'cp'}
        assert set(_refused(self.layout)) <= copied, copied

    def test_a_retry_converges_after_a_fault_around_a_refused_rename(self, lab):
        """Failed or killed before the rename, killed right after it refused, at each call
        that follows up to its copy."""
        run = lab.first_run()
        refused = {f'{lab.first[()][0].data}/{name}' for name in _refused(self.layout)}
        for at, name, args in run.calls:
            if name == 'rename' and len(args) == 5 and args[3] in refused:
                for k in range(at, at + 6):
                    for mode in ('fail', 'kill', 'done'):
                        ChaosSuite._scenario(self, lab, (k, mode), None)

    def test_a_retry_converges_after_a_fault_around_a_removal_in_place(self, lab):
        """A refused source is renamed aside neither: removed in place behind its inplace
        line. Failed, killed, or killed right after, from the refused rename aside to the
        line leaving the journal."""
        run = lab.first_run()
        refused = {f'{lab.first[()][0].data}/{name}' for name in _refused(self.layout)}
        removals = [n for n, name, args in run.calls if name == 'rm' and args[-1] in refused]
        assert len(removals) == len(refused), removals
        for at in removals:
            for k in range(at - 1, at + 2):
                for mode in ('fail', 'kill', 'done'):
                    ChaosSuite._scenario(self, lab, (k, mode), None)
