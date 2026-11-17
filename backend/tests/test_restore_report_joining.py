"""The two warnings an archive carries read as sentences, whatever precedes.

There are two ways to ask for a restore and each writes its own message, so
the joining lives in one place. It has to survive punctuation neither caller
writes today, because the next caller is the one that will.
"""
import pytest

from services.backup.restore_report import with_restore_warnings


ONE = {'key_mismatches': ['issuing-ca']}
TWO = {'key_mismatches': ['issuing-ca', 'ocsp-responder']}
SECTIONS = {'sections_not_restored': ['hsm_providers']}


class TestNothingToWarnAbout:
    @pytest.mark.parametrize("message,expected", [
        ('Restore completed.', 'Restore completed.'),
        ('Restore completed', 'Restore completed.'),
        # `rstrip('.')` ate every trailing stop, so an ellipsis became a dot.
        ('Restoring...', 'Restoring...'),
        # And a full stop was added regardless, giving `Did it work?.`
        ('Did it work?', 'Did it work?'),
        ('Done!', 'Done!'),
        ('', ''),
    ])
    def test_the_message_comes_back_punctuated_as_it_was(
            self, message, expected):
        assert with_restore_warnings(message, {}) == expected


class TestTheClausesReadAsSentences:
    def test_a_message_ending_in_a_question_is_not_given_a_full_stop(self):
        answer = with_restore_warnings('Did it work?', ONE)
        assert answer.startswith('Did it work? '), answer
        assert '?.' not in answer, answer

    def test_a_message_ending_in_a_full_stop_gains_exactly_one(self):
        answer = with_restore_warnings('Restore completed.', ONE)
        assert '..' not in answer, answer
        assert answer.startswith('Restore completed. '), answer

    def test_a_message_without_punctuation_gains_one(self):
        answer = with_restore_warnings('Restore completed', ONE)
        assert answer.startswith('Restore completed. '), answer

    def test_an_empty_message_does_not_start_with_a_full_stop(self):
        answer = with_restore_warnings('', ONE)
        assert not answer.startswith('.'), answer
        assert answer.endswith('.'), answer

    def test_both_clauses_are_separated(self):
        answer = with_restore_warnings(
            'Restore completed.', {**SECTIONS, **TWO})
        assert '..' not in answer, answer
        assert 'hsm_providers' in answer and 'ocsp-responder' in answer


class TestTheCountIsSaidCorrectly:
    def test_one_record_is_singular(self):
        answer = with_restore_warnings('Restore completed.', ONE)
        assert '1 record carries' in answer, answer

    def test_several_records_are_plural(self):
        answer = with_restore_warnings('Restore completed.', TWO)
        assert '2 records carry' in answer, answer

    def test_a_truncated_list_says_how_many_it_left_out(self):
        many = {'key_mismatches': [f'ca-{n}' for n in range(8)]}
        answer = with_restore_warnings('Restore completed.', many)
        assert '8 records carry' in answer, answer
        assert 'and 3 more' in answer, (
            f'five are listed and three are dropped in silence: {answer}')


class TestTheTwoRoutesFinishTheSameWay:
    """Everything after the archive is read, not just the warnings.

    The joining of the warnings was shared first; the steps around it were
    not. One route recorded the restore in a way that could turn a success
    into a 500, one asked the service to restart and the other told the
    operator to do it by hand, and only one handed back what the archive had
    said about itself. The page an operator happened to use decided all three.
    """

    def test_both_routes_call_the_same_completion(self):
        """Read from the source: neither route may keep its own copy."""
        import ast
        import os

        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for route in ('api/v2/system/backup.py', 'api/v2/settings/backup.py'):
            tree = ast.parse(open(os.path.join(here, route)).read())
            imported = {
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
                and node.module == 'services.backup.restore_completion'
                for alias in node.names
            }
            # The restore job records, words and restarts: both routes only start it
            assert {'preflight_v4', 'start_restore'} <= imported, (
                f'{route} does not go through the shared completion: '
                f'{imported}')

    def test_the_restart_is_reported_as_it_happened(self, monkeypatch):
        """`restart_service` returns a pair. Read as one truth value, it was
        always true, so the answer said "sign in again" for a restart nobody
        had asked for."""
        from services.backup import restore_completion

        monkeypatch.setattr(
            'utils.service_manager.restart_service',
            lambda: (False, 'no service manager here'))
        requested, detail = restore_completion.request_restart()
        assert requested is False, (
            'a refused restart is reported as requested')
        assert detail == 'no service manager here'

        monkeypatch.setattr(
            'utils.service_manager.restart_service',
            lambda: (True, 'restart requested'))
        assert restore_completion.request_restart() == (
            True, 'restart requested')

    def test_the_message_says_which_of_the_two_happened(self):
        from services.backup.restore_completion import restore_message

        asked = restore_message({'restart_requested': True})
        assert 'Sign in again' in asked, asked

        refused = restore_message(
            {'restart_requested': False,
             'restart_detail': 'restart the service manually'})
        assert 'Restart the service to finish' in refused, refused
        assert 'restart the service manually' in refused, refused

    def test_a_failing_audit_does_not_fail_the_restore(self, monkeypatch):
        """The entry records the restore; it does not decide it."""
        from services.backup import restore_completion

        def _refuse(**_fields):
            raise RuntimeError('audit table is being rewritten')

        monkeypatch.setattr(
            restore_completion.AuditService, 'log_action', _refuse)
        # Must not raise: the restore has already happened.
        restore_completion.record_restore(action='system_restore')


class TestTheSectionsListIsBounded:
    """An archive from a newer version can name every section it has.

    The neighbouring list of key mismatches stops at five and says how many
    it left; this one joined everything it was given.
    """

    def test_one_section_reads_as_one(self):
        answer = with_restore_warnings('Restore completed.', SECTIONS)
        assert 'holds a section this version does not restore' in answer, answer

    def test_two_sections_read_as_several(self):
        answer = with_restore_warnings('Restore completed.', {
            'sections_not_restored': ['hsm_providers', 'sso_providers']})
        assert 'holds sections this version does not restore' in answer, answer

    def test_a_long_list_is_cut_at_five(self):
        sections = [f'section_{index}' for index in range(9)]
        answer = with_restore_warnings('Restore completed.', {
            'sections_not_restored': sections})
        assert 'section_4' in answer, answer
        assert 'section_5' not in answer, answer
        assert 'and 4 more' in answer, answer
