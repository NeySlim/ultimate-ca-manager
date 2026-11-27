"""conftest's check that a file's job threads end with it follows UCM_TEST_LEAK_MODE:
a failure in `fail`, a warning otherwise, as the database key check does."""
import pytest

from services.jobs import runner
from tests import conftest


class _Request:
    fspath = 'test_some_module.py'


class _NeverDone:
    def wait(self, timeout=None):
        return False


def _finish_with_a_job_left(monkeypatch):
    monkeypatch.setitem(runner._local_done, 'job-left-running', _NeverDone())
    module = conftest._jobs_end_in_their_module._get_wrapped_function()(_Request())
    next(module)
    with pytest.raises(StopIteration):
        next(module)


def test_a_job_left_running_fails_the_file_in_fail_mode(monkeypatch):
    monkeypatch.setenv('UCM_TEST_LEAK_MODE', 'fail')
    with pytest.raises(pytest.fail.Exception, match='job-left-running'):
        _finish_with_a_job_left(monkeypatch)


def test_a_job_left_running_warns_otherwise(monkeypatch):
    monkeypatch.delenv('UCM_TEST_LEAK_MODE', raising=False)
    with pytest.warns(UserWarning, match='job-left-running'):
        _finish_with_a_job_left(monkeypatch)
