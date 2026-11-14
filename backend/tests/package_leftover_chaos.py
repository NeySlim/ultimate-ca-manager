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

from tests.test_package_leftover_archive import KEPT, STAMP, Box, files, snapshot, tree, whole


CHAOS = ('mv', 'cp', 'rm', 'mkdir', 'rmdir', 'chmod')
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
    mode, of the first file in it; 'top' before the mode of the copied directory itself. 'alone' leaves the date wrong and fails that cp only, the run goes on; 'late' fails
    a cp that copied everything."""
    box.wrap(other_fs=LAYOUTS[layout](box))
    s = box.state
    find, sort, head = (shutil.which(t) for t in ('find', 'sort', 'head'))
    for name in CHAOS:
        # Builtins only up to the real command: a run makes hundreds of these calls
        (box.bin / name).write_text(
            f'#!/bin/sh\nread n < {s}/count; n=$((n + 1)); echo $n > {s}/count\n'
            f'ifs=$IFS; IFS="\t"; echo "$n\t{name}\t$*" >> {s}/names; IFS=$ifs\n'
            f'mode=; while read -r k m; do [ "$k" != "$n" ] || mode=$m; done < {s}/plan\n'
            f'case $mode in\n'
            f'    fail) echo "{name}: injected failure" >&2; exit 1 ;;\n'
            f'    kill) kill -9 0 ;;\n'
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
            f'    xcopy|xremove)\n'
            # A mv falling back on a copy, as across filesystems, is cut short while it
            # copies (a file short, the last one missing) or while it removes its source
            f'        if [ {name} = mv ]; then\n'
            f'            {shutil.which("cp")} -a -- "$2" "$3"\n'
            f'            if [ $mode = xcopy ] && [ ! -L "$3" ]; then\n'
            f'                set -- $({find} "$3" -type f | {sort})\n'
            f'                [ $# = 0 ] || {shutil.which("truncate")} -s 0 "$1"\n'
            f'                for last; do :; done; [ $# -lt 2 ] || {shutil.which("rm")} -f -- "$last"\n'
            f'            elif [ $mode = xremove ] && [ -d "$2" ] && [ ! -L "$2" ]; then\n'
            f'                set -- $({find} "$2" -type f | {sort})\n'
            f'                [ $# = 0 ] || {shutil.which("rm")} -f -- "$1"\n'
            f'            fi\n'
            f'        fi\n'
            f'        kill -9 0 ;;\n'
            f'esac\nexec {shutil.which(name)} "$@"\n')
        (box.bin / name).chmod(0o755)


def _chaos_run(box, plan=()):
    (box.state / 'count').write_text('0')
    (box.state / 'names').write_text('')
    (box.state / 'plan').write_text(''.join(f'{n} {mode}\n' for n, mode in plan))
    out = box.run()
    return out, int((box.state / 'count').read_text())


def _chaos_box(tmp_path, layout, env='full'):
    """env 'full': the ucm.env of an install, with UCM_FIPS_BUILD=1; 'fips only': that
    line alone, the very file the new configuration is."""
    box = Box(tmp_path, python='stub')
    path = box.config / 'ucm.env'
    path.write_text('UCM_FIPS_BUILD=1\n' if env == 'fips only' else path.read_text() + 'UCM_FIPS_BUILD=1\n')
    # A file, a directory and a link in updates: each kind of copy in every layout that copies
    (box.data / 'updates' / 'manifest.json').write_text('{}')
    os.symlink('nested', box.data / 'updates' / 'latest')
    _chaos(box, layout)
    return box, whole(box.data, _kept(layout)), whole(box.config)


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
        """(top, path relative to it) of a path in the data or the configuration."""
        for top, prefix in self.tops.items():
            if path.startswith(prefix):
                return top, path[len(prefix):].rstrip('/').removesuffix('/.')
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

    def __init__(self, root, layout, env='full'):
        self.root, self.layout, self.env = root, layout, env
        self.first = {}
        self.n = 0

    def _new(self):
        self.n += 1
        box, data, config = _chaos_box(self.root / f'b{self.n}', self.layout, self.env)
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
    if out.returncode == -9:
        _nothing_lost(box, data, config, why)
        return
    assert out.returncode in (0, 1, 2), (why, out.stdout, out.stderr)
    _nothing_lost(box, data, config, why)
    if out.returncode == 1:
        assert snapshot(box) == before, (why, out.stdout)
        assert not box.parent.exists() or not any(box.parent.iterdir()), (why, out.stdout)
    if out.returncode == 2:
        lines = [line for line in out.stdout.splitlines() if 'are still in ' in line]
        assert lines, (why, out.stdout)
        for line in lines:
            for path in line.split(':', 1)[1].split():
                assert os.path.lexists(path), (why, path, out.stdout)
    if out.returncode:
        assert 'was not started' in out.stdout, (why, out.stdout)


def _converged(box, out, data, config, layout, why):
    assert out.returncode == 0, (why, out.stdout, out.stderr)
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


FELL_BACK = ('xcopy', 'xremove')


def _moves(run, put_back=False):
    """The calls of `run` that were a mv of an item, not of the journal; with put_back,
    those out of the archive."""
    return [n for n, name, args in run.calls if name == 'mv' and '.journal' not in args[1]
            and (not put_back or args[1].startswith(f'{run.parent}/'))]


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
        for at in range(1, calls + 1):
            for mode in ('fail', 'kill'):
                self._scenario(lab, (at, mode), None)

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

    def test_a_retry_converges_after_a_move_that_fell_back_on_a_copy_is_cut_short(self, lab):
        """A rename refused by the kernel (an overlayfs directory, a mount the table does not
        show) makes GNU mv copy then remove, unjournalled: cut short there, either way."""
        for at in _moves(lab.first_run()):
            for mode in FELL_BACK:
                self._scenario(lab, (at, mode), None)

    def test_a_retry_converges_after_a_put_back_move_that_fell_back_is_cut_short(self, lab):
        """Each item's put-back by mv is cut short each way, after the first and the last
        archiving fault that has it put back."""
        by_item = {}
        for at in range(1, self._calls(lab) + 1):
            run = lab.first_run([(at, 'fail')])
            moves = _moves(run, put_back=True)
            for n, _name, args in run.calls:
                if n in moves:
                    by_item.setdefault(args[1].replace(str(run.parent), ''), []).append((at, n))
        assert by_item or not _moves(lab.first_run())
        for pairs in by_item.values():
            for at, back in {pairs[0], pairs[-1]}:
                for mode in FELL_BACK:
                    self._scenario(lab, (at, 'fail'), (back, mode))
