"""A job started by a test request runs once that request has answered.

The tests' SQLite is one in-memory connection shared by every thread (StaticPool): a job
thread and the request that started it reading at once break it. In production each
thread has its own connection, and nothing here applies.
"""
from services.jobs import runner, store


class DeferredDispatch:
    """runner.dispatch_job notes the job; it starts at the route's bounded wait (the request
    reads nothing until the end), at release(), or at the test's join_local()."""

    def __init__(self, app, monkeypatch):
        self.app = app
        self.noted = []
        self._dispatch, self._join = runner.dispatch_job, runner.join_local
        real_wait = runner.wait_for_job
        self._monkeypatch = monkeypatch

        def wait(job_id, seconds):
            self._start_noted()
            return real_wait(job_id, seconds)

        def join(job_id, timeout=30):
            self.release()
            return self._join(job_id, timeout)
        monkeypatch.setattr(runner, 'dispatch_job', self.noted.append)
        monkeypatch.setattr(runner, 'wait_for_job', wait)
        monkeypatch.setattr(runner, 'join_local', join)

    def _start_noted(self):
        while self.noted:
            self._dispatch(self.noted.pop(0))

    def release(self):
        """Start the noted jobs now, from the test (outside any request)."""
        if self.noted:
            with self.app.app_context():
                self._start_noted()

    def off(self):
        """Jobs start at once again, as without this helper."""
        self.release()
        self._monkeypatch.setattr(runner, 'dispatch_job', self._dispatch)

    def conclude_leftovers(self):
        """A job a failed test left active ends here: the next test's start is no 409."""
        from models import db
        from services import jobs
        self.release()
        with self.app.app_context():
            for row in store.active_jobs(db.session):
                self._join(row['id'], 30)
            db.session.rollback()
            for row in store.active_jobs(db.session):
                store.conclude_job(db.session, row['id'], state=store.FAILED, reason=store.ERROR,
                                   from_states=(store.PENDING, store.RUNNING), now=jobs._now())
            db.session.rollback()
