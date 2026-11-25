"""A layout's retry suite runs in one file or in two (ConvergeSuite, AbsentSuite): the files together
hold every test of ChaosSuite, and NothingRenamesSuite, once each, so a split loses none."""
import collections
import importlib
import inspect
import os
import pathlib

import pytest

from tests.package_leftover_chaos import (
    CHAOS, LAYOUTS, ChaosSuite, NothingRenamesSuite, _chaos_box, _chaos_run, _ChaosBase)

# Named in the fips_env files: they do not depend on ucm.env
NOT_RUN = {('data and config are mount points', 'fips only'): {
    'test_a_retry_converges_after_a_kill_right_after_any_rename',
    'test_only_the_journal_is_ever_moved_and_nothing_copied'}}
# This layout's database sits outside the data: it has no suite of its own for a file nothing renames
NO_NOTHING_RENAMES = {'a database outside the data'}


def _tests(cls):
    return {name for name in dir(cls) if name.startswith('test_') and callable(getattr(cls, name))}


def _classes():
    found = []
    for path in sorted(pathlib.Path(__file__).parent.glob('test_package_leftover_retry_*.py')):
        module = importlib.import_module(f'tests.{path.stem}')
        found += [c for _n, c in inspect.getmembers(module, inspect.isclass) if c.__module__ == module.__name__]
    return found


def _extras(key):
    """The tests only the fips_env file has."""
    return ({'test_the_new_configuration_is_taken_back_once_never_the_old_one',
             'test_a_put_back_stops_where_the_new_configuration_could_not_be_cleared_from_it'}
            if key in NOT_RUN else set())


def test_the_files_of_a_layout_hold_every_test_once():
    held = collections.defaultdict(list)
    for cls in _classes():
        if issubclass(cls, _ChaosBase):
            held[(cls.layout, cls.env)] += sorted(_tests(cls))
    assert set(held) == {(layout, 'full') for layout in LAYOUTS} | set(NOT_RUN)
    for key, names in held.items():
        assert sorted(names) == sorted(_tests(ChaosSuite) - NOT_RUN.get(key, set()) | _extras(key)), key


def test_every_layout_but_one_keeps_its_nothing_renames_suite():
    layouts = [c.layout for c in _classes() if issubclass(c, NothingRenamesSuite)]
    assert sorted(layouts) == sorted(set(LAYOUTS) - NO_NOTHING_RENAMES)


@pytest.mark.skipif(not os.path.exists('/proc/self/stat'), reason='reads /proc')
def test_a_chaos_kill_never_reaches_the_process_group_of_the_test(tmp_path):
    """Every command a plan can kill (`kill -9 0`) runs in a session and process group of its
    own: the kill ends the run, never the pytest worker that started it."""
    box, _data, _config = _chaos_box(tmp_path / 'whole', 'one filesystem')
    groups = box.state / 'groups'
    for name in CHAOS:
        head, rest = (box.bin / name).read_text().split('\n', 1)
        # In a subshell: "set --" there leaves the wrapper's own arguments alone
        (box.bin / name).write_text(
            f'{head}\n( read -r st < /proc/$$/stat; set -- ${{st##*) }}; echo "$3 $4" >> {groups} )\n{rest}')
    out, count = _chaos_run(box)
    assert out.returncode == 0, (out.stdout, out.stderr)
    seen = [tuple(map(int, line.split())) for line in groups.read_text().splitlines()]
    assert len(seen) == count > 20
    assert all(pgrp != os.getpgrp() and sid != os.getsid(0) for pgrp, sid in seen), seen[:3]
    box, _data, _config = _chaos_box(tmp_path / 'killed', 'one filesystem')
    out, _count = _chaos_run(box, [(count // 2, 'kill')])
    assert out.returncode == -9, (out.stdout, out.stderr)
