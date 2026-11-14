"""archive-leftovers.sh retried after any fault, the left ucm.env being exactly the line the
new one is (UCM_FIPS_BUILD=1), on another filesystem (see package_leftover_chaos)."""
from tests.test_package_leftover_archive import named
from tests.package_leftover_chaos import ChaosSuite, _converged, _nothing_lost, _while_failing


class TestTheLeftConfigurationIsTheFipsLine(ChaosSuite):
    layout = 'data and config are mount points'
    env = 'fips only'
    # The copies and moves cut short do not depend on what ucm.env holds
    test_a_retry_converges_after_any_copy_of_the_archiving_is_cut_short = None
    test_a_retry_converges_after_any_copy_of_the_put_back_is_cut_short = None
    test_a_put_back_whose_copy_failed_is_never_reported_as_done = None
    test_a_retry_converges_after_a_kill_right_after_any_rename = None
    test_mv_never_moves_an_item = None

    def test_the_new_configuration_is_taken_back_once_never_the_old_one(self, lab):
        """Killed on removing the journal, then killed again once the old ucm.env is back
        but before its copy goes: the retry must not take that old file for the new one."""
        first = lab.first_run()
        journal = next(n for n, name, args in first.calls
                       if name == 'rm' and args[-1].endswith('/.journal'))
        box, data, config, before, runs = lab.chain([(journal, 'kill')])
        again = lab.chain([(journal, 'kill')], ())[4][1]
        archived_env = f'{again.parent}/{box.archive.name}/config/ucm.env'
        copy_goes = next(n for n, name, args in again.calls
                         if name == 'rm' and args[-1] == archived_env)
        box, data, config, before, runs = lab.chain([(journal, 'kill')], [(copy_goes, 'kill')], ())
        assert runs[1].out.returncode == -9
        _nothing_lost(box, data, config, 'last run')
        _converged(box, runs[-1].out, data, config, self.layout, 'last run')

    def test_a_put_back_stops_where_the_new_configuration_could_not_be_cleared_from_it(self, lab):
        """Taking the fips line out of the journal fails: the roll-back stops there, so no
        later kill can leave the old ucm.env back with that line still to undo."""
        first = lab.first_run()
        journal = next(n for n, name, args in first.calls
                       if name == 'rm' and args[-1].endswith('/.journal'))
        run = lab.first_run([(journal, 'fail')])
        new_env_goes = next(n for n, name, args in run.calls
                            if n > journal and name == 'rm' and args[-1].endswith('/etc/ucm/ucm.env'))
        line_goes = next(n for n, name, args in run.calls if n > new_env_goes and name == 'mv')
        copy_goes = next(n for n, name, args in run.calls
                         if name == 'rm' and args[-1].endswith('/config/ucm.env') and n > line_goes)
        box, data, config, before, runs = lab.chain(
            [(journal, 'fail'), (line_goes, 'fail'), (copy_goes, 'kill')], ())
        _converged(box, runs[-1].out, data, config, self.layout, 'last run')

        # Stopped there, it names what is left: the journal still holding the fips line
        def check(box, data, config, before, run):
            assert run.out.returncode == 2, run.out.stdout
            assert f'{box.archive}/.journal' in named(run.out.stdout), run.out.stdout
            _while_failing(box, run.out, before, data, config, 'stopped')
        box, data, config, before, runs = lab.chain([(journal, 'fail'), (line_goes, 'fail')], (), check=check)
        _converged(box, runs[-1].out, data, config, self.layout, 'last run')
