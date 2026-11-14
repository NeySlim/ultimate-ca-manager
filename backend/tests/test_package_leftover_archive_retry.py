"""archive-leftovers.sh: from any state an interrupted or failed attempt leaves, a retry
without fault converges to one complete archive, no file lost or duplicated, no journal.

Every file command the script runs is wrapped: one sequence numbers all their calls, and
a plan fails or kills the run (SIGKILL to its process group, no clean-up) at given calls,
or kills it in the middle of a copy ('torn': the target exists with other content).
"""
import os
import random
import shutil

import pytest

from tests.test_package_leftover_archive import KEPT, STAMP, Box, files, snapshot


CHAOS = ('mv', 'cp', 'rm', 'mkdir', 'rmdir', 'chmod')
LAYOUTS = {
    'one filesystem': lambda box: (),
    'data and config are mount points': lambda box: (box.data, box.config),
    'a mount point inside the data': lambda box: (box.data / 'updates',),
}
# Pairs drawn per layout from every (fault i while archiving, fault j while putting back)
SEED, PAIRS, TORN_PAIRS = 20261114, 120, 60


def _chaos(box, layout):
    """Every file command counts its calls in one sequence; the plan fails ('fail') or
    kills the whole run without any clean-up ('kill') at the calls it names."""
    box.wrap(other_fs=LAYOUTS[layout](box))
    s = box.state
    for name in CHAOS:
        (box.bin / name).write_text(
            f'#!/bin/sh\nn=$(( $(cat {s}/count) + 1 )); echo $n > {s}/count\n'
            f'case $(grep -x "$n [a-z]*" {s}/plan) in\n'
            f'    *" fail") echo "{name}: injected failure" >&2; exit 1 ;;\n'
            f'    *" kill") kill -9 0 ;;\n'
            # A copy cut short while it writes: its target is there, with other content
            f'    *" torn") [ {name} = cp ] && {{ {shutil.which(name)} "$@"; for last; do :; done\n'
            f'        torn=$({shutil.which("find")} "$last" -type f | {shutil.which("sort")} | {shutil.which("head")} -n 1)\n'
            f'        [ -z "$torn" ] || printf torn > "$torn"; }}; kill -9 0 ;;\n'
            f'esac\nexec {shutil.which(name)} "$@"\n')
        (box.bin / name).chmod(0o755)


def _chaos_run(box, plan=()):
    (box.state / 'count').write_text('0')
    (box.state / 'plan').write_text(''.join(f'{n} {mode}\n' for n, mode in plan))
    out = box.run()
    return out, int((box.state / 'count').read_text())


def _chaos_box(tmp_path, layout):
    box = Box(tmp_path, python='stub')
    env = box.config / 'ucm.env'
    env.write_text(env.read_text() + 'UCM_FIPS_BUILD=1\n')
    _chaos(box, layout)
    return box, files(box.data), files(box.config)


def _nothing_lost(box, data, config, why):
    """Every original file is whole in its place or in an archive, and what the output
    names as still in the archive is there."""
    archives = [a for a in box.parent.iterdir()] if box.parent.exists() else []
    for top, originals, sub in ((box.data, data, 'data'), (box.config, config, 'config')):
        here = files(top)
        there = [files(a / sub) for a in archives]
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


def _converged(box, data, config, layout, why):
    out, _ = _chaos_run(box)
    assert out.returncode == 0, (why, out.stdout, out.stderr)
    assert [a.name for a in box.parent.iterdir()] == [STAMP], (why, out.stdout)
    assert files(box.archive / 'data') == data, why
    assert files(box.archive / 'config') == config, why
    assert sorted(a.name for a in box.archive.iterdir()) == ['README.txt', 'config', 'data'], why
    kept = KEPT + (['updates'] if layout == 'a mount point inside the data' else [])
    assert sorted(p.name for p in box.data.iterdir()) == sorted(kept), why
    assert all(not any((box.data / d).iterdir()) for d in kept), why
    assert files(box.config) == {'ucm.env': files(box.config)['ucm.env']}, why
    assert (box.config / 'ucm.env').read_text() == 'UCM_FIPS_BUILD=1\n', why


def _scenario(tmp_path, layout, first, second):
    """`first` = (call, mode) of the archiving run; `second` = (call, mode) of the same run
    after a failure (its roll-back), or of the next run after a kill. Then a clean run."""
    box, data, config = _chaos_box(tmp_path, layout)
    before = snapshot(box)
    why = (layout, first, second)
    plan = [first] + ([second] if second and first[1] == 'fail' else [])
    out, _ = _chaos_run(box, plan)
    _while_failing(box, out, before, data, config, why)
    if second and first[1] == 'kill':
        out, _ = _chaos_run(box, [second])
        _while_failing(box, out, before, data, config, why)
    _converged(box, data, config, layout, why)


def _calls(tmp_path, layout, plan=()):
    box, *_ = _chaos_box(tmp_path, layout)
    out, count = _chaos_run(box, plan)
    return count


@pytest.mark.parametrize('layout', list(LAYOUTS))
def test_a_retry_converges_after_one_fault_at_any_call(tmp_path, layout):
    """Each call of the archiving run fails, or kills it, in turn; then a run without fault."""
    calls = _calls(tmp_path / 'count', layout)
    assert calls > 20
    for at in range(1, calls + 1):
        for mode in ('fail', 'kill'):
            _scenario(tmp_path / f'{at}-{mode}', layout, (at, mode), None)


@pytest.mark.parametrize('layout', list(LAYOUTS))
def test_a_retry_converges_after_a_fault_while_putting_back(tmp_path, layout):
    """Pairs (fault i while archiving, fault j while putting back or in the next run), drawn
    from the full product with a fixed seed, then a run without fault."""
    calls = _calls(tmp_path / 'count', layout)
    product = []
    for at in range(1, calls + 1):
        after_fail = _calls(tmp_path / f'f{at}', layout, [(at, 'fail')])
        product += [((at, 'fail'), (j, m)) for j in range(at + 1, after_fail + 1)
                    for m in ('fail', 'kill')]
    for at in range(1, calls + 1):
        box, *_ = _chaos_box(tmp_path / f'k{at}', layout)
        _chaos_run(box, [(at, 'kill')])
        _, again = _chaos_run(box, [(10 ** 6, 'fail')])
        product += [((at, 'kill'), (j, m)) for j in range(1, again + 1) for m in ('fail', 'kill')]
    assert len(product) > PAIRS
    draw = random.Random(f'{SEED}-{layout}')  # noqa: S311 - a fixed seed, a replayable draw
    pairs = draw.sample(product, PAIRS)
    for n, (first, second) in enumerate(pairs):
        _scenario(tmp_path / f'p{n}', layout, first, second)


@pytest.mark.parametrize('layout', list(LAYOUTS))
def test_a_retry_converges_after_a_copy_cut_short_at_any_call(tmp_path, layout):
    """Each call of the archiving run is killed in turn, a copy in the middle of its write."""
    for at in range(1, _calls(tmp_path / 'count', layout) + 1):
        _scenario(tmp_path / f'{at}', layout, (at, 'torn'), None)


@pytest.mark.parametrize('layout', list(LAYOUTS))
def test_a_retry_converges_after_a_put_back_cut_short_in_a_copy(tmp_path, layout):
    """Pairs (fault i while archiving, the put-back killed at call j, a copy in the middle
    of its write), drawn with a fixed seed, then a run without fault."""
    product = []
    for at in range(1, _calls(tmp_path / 'count', layout) + 1):
        after_fail = _calls(tmp_path / f'f{at}', layout, [(at, 'fail')])
        product += [((at, 'fail'), (j, 'torn')) for j in range(at + 1, after_fail + 1)]
    draw = random.Random(f'{SEED}-torn-{layout}')  # noqa: S311 - a fixed seed, a replayable draw
    for n, (first, second) in enumerate(draw.sample(product, min(TORN_PAIRS, len(product)))):
        _scenario(tmp_path / f'p{n}', layout, first, second)
