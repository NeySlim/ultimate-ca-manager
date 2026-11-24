"""archive-leftovers.sh retried after any fault, the left ucm.env being exactly the line the
new one is (UCM_FIPS_BUILD=1), on another filesystem (see package_leftover_chaos)."""
from tests.test_package_leftover_archive import LOCAL, exactly_once, named
from tests.package_leftover_chaos import ConvergeSuite, converged, while_failing


class TestTheLeftConfigurationIsTheFipsLine(ConvergeSuite):
    layout = 'data and config are mount points'
    env = 'fips only'
    # The renames killed right after and the journal-only mv do not depend on ucm.env
    test_a_retry_converges_after_a_kill_right_after_any_rename = None
    test_only_the_journal_is_ever_moved_and_nothing_copied = None

    def _journal_removed(self, lab):
        return next(n for n, name, args in lab.first_run().calls
                    if name == 'rm' and args[-1].endswith('/.journal'))

    def test_the_new_configuration_is_taken_back_once_never_the_old_one(self, lab):
        """Killed on removing the journal, then killed right after the old ucm.env is renamed
        back: the retry must not take that old file for the new one."""
        journal = self._journal_removed(lab)
        box, *_ = lab.chain([(journal, 'kill')])
        again = lab.chain([(journal, 'kill')], ())[4][1]
        archived_env = f'{box.config}/{LOCAL}/ucm.env'
        back = next(n for n, name, args in again.calls if name == 'rename' and args[3:] == [archived_env, f'{box.config}/ucm.env'])
        box, data, config, before, runs = lab.chain([(journal, 'kill')], [(back, 'done')], ())
        assert runs[1].out.returncode == -9
        exactly_once(box, data, config, 'last run')
        converged(box, runs[-1].out, data, config, 'last run')

    def test_a_put_back_stops_where_the_new_configuration_could_not_be_cleared_from_it(self, lab):
        """Taking the fips line out of the journal fails: the roll-back stops there, so no
        later kill can leave the old ucm.env back with that line still to undo."""
        journal = self._journal_removed(lab)
        run = lab.first_run([(journal, 'fail')])
        new_env_goes = next(n for n, name, args in run.calls
                            if n > journal and name == 'rm' and args[-1].endswith('/etc/ucm/ucm.env'))
        line_goes = next(n for n, name, args in run.calls if n > new_env_goes and name == 'mv')
        back = next(n for n, name, args in run.calls
                    if n > line_goes and name == 'rename' and args[-1].endswith('/etc/ucm/ucm.env'))
        box, data, config, before, runs = lab.chain(
            [(journal, 'fail'), (line_goes, 'fail'), (back, 'kill')], ())
        converged(box, runs[-1].out, data, config, 'last run')

        # Stopped there, it names what is left: the journal still holding the fips line
        def check(box, data, config, before, run):
            assert run.out.returncode == 2, run.out.stdout
            assert f'{box.archive}/.journal' in named(run.out.stdout), run.out.stdout
            while_failing(box, run.out, before, data, config, 'stopped')
        box, data, config, before, runs = lab.chain([(journal, 'fail'), (line_goes, 'fail')], (), check=check)
        converged(box, runs[-1].out, data, config, 'last run')
