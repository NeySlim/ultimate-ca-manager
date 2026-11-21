"""A slow check run once at a time, its result shared by every caller that arrives meanwhile."""
import threading
import time


class _Run:
    def __init__(self, check, name):
        self.started = time.monotonic()
        self.done = threading.Event()
        self.error = None
        self.thread = threading.Thread(target=self._target, args=(check,), name=name, daemon=True)
        self.thread.start()

    def _target(self, check):
        try:
            check()
        except Exception as e:
            self.error = e
        finally:
            self.done.set()


class SharedCheck:
    """At most one run of a check in flight. A caller that arrives while it runs waits for it until
    `timeout` after it started and gets its result; past that it gives up without starting another."""

    def __init__(self, name):
        self._name = name
        self._lock = threading.Lock()
        self._run = None

    def __call__(self, check, timeout):
        """('ok', None), ('error', exception) or ('timeout', None)."""
        with self._lock:
            run = self._run
            if run is None or run.done.is_set():
                run = self._run = _Run(check, self._name)
        run.done.wait(max(0.0, run.started + timeout - time.monotonic()))
        if not run.done.is_set():
            return 'timeout', None
        if run.error is not None:
            return 'error', run.error
        return 'ok', None

    def wait(self, timeout):
        """Tests: let a run still in flight end."""
        run = self._run
        if run is not None:
            run.thread.join(timeout)
