"""The gunicorn master's side of the scheduler process: start it, watch it, restart it."""
import logging
import os
import signal
import subprocess
import sys
import threading
import time

BACKEND = os.path.dirname(os.path.abspath(__file__))
BACKOFF_MAX = 60
# A process that ran this long before exiting resets the backoff
HEALTHY_AFTER = 60
# How often the watcher looks for the master stopping while the process runs
STOP_POLL = 0.5


def _gone(proc) -> bool:
    """The process exited. The gunicorn arbiter reaps every child with waitpid(-1): when it
    collects this one first, gevent's Popen in the master never learns of the exit."""
    if proc.poll() is not None:
        return True
    try:
        os.kill(proc.pid, 0)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    try:  # exited, not reaped yet
        with open(f'/proc/{proc.pid}/stat') as handle:
            return handle.read().rsplit(')', 1)[1].split()[0] == 'Z'
    except (OSError, IndexError):
        return False


def _wait_gone(proc, timeout, step=0.1) -> bool:
    deadline = time.monotonic() + timeout
    while not _gone(proc):
        if time.monotonic() >= deadline:
            return False
        time.sleep(step)
    return True


class SchedulerSupervisor:
    def __init__(self, command=None):
        self.command = command or [sys.executable, '-m', 'scheduler_main']
        self.graceful_timeout = 30.0
        self.log = logging.getLogger('ucm.scheduler_supervisor')
        self._proc = None
        self._owner_pid = None
        self._server = None
        self._thread = None
        self._stopping = False
        self._restarting = False
        self._wake = threading.Event()
        # restart() or stop() while the process runs: the watcher looks at once
        self._nudge = threading.Event()
        self._on_stopped = None
        self._stopped_lock = threading.Lock()
        self._stopped_said = False

    @property
    def pid(self):
        return self._proc.pid if self._proc is not None else None

    def start(self, server=None, on_stopped=None) -> None:
        """``on_stopped`` runs once, after the process exited for the master's stop."""
        if on_stopped is not None:
            self._on_stopped = on_stopped
        if server is not None:
            self._server = server
            self.log = server.log
            self.graceful_timeout = float(server.cfg.graceful_timeout)
        if self._thread is not None:
            return
        self._owner_pid = os.getpid()
        self._stopping = False
        self._thread = threading.Thread(target=self._watch, name='scheduler-supervisor', daemon=True)
        self._thread.start()

    def _spawn(self):
        from scheduler_main import GRACE_ENV, MASTER_ENV
        env = dict(os.environ, UCM_SCHEDULER_PROCESS='1',
                   **{GRACE_ENV: str(self.graceful_timeout), MASTER_ENV: str(os.getpid())})
        return subprocess.Popen(self.command, cwd=BACKEND, env=env)

    def _mine(self) -> bool:
        # A worker forked from the master inherits this object and its greenlets:
        # there they must neither signal nor start anything
        return self._owner_pid == os.getpid()

    def _park(self) -> None:
        # The inherited copy must never return: under gevent, Thread._bootstrap's
        # cleanup raises KeyError in a forked child. It idles instead.
        while True:
            time.sleep(3600)

    def _master_stopping(self) -> bool:
        # Arbiter.stop() empties LISTENERS first, before on_exit, while workers drain
        return self._stopping or (self._server is not None and not self._server.LISTENERS)

    def _watch(self) -> None:
        delay = 1
        if not self._mine():
            self._park()
        while self._mine() and not self._master_stopping():
            started = time.monotonic()
            try:
                self._proc = proc = self._spawn()
            except OSError as e:
                self.log.error("Scheduler process not started: %s", e)
                proc = None
            if not self._mine():
                self._park()
            if proc is not None:
                self.log.info("Scheduler process started (pid %s)", proc.pid)
                code = self._wait(proc)
                if not self._mine():
                    self._park()
                if self._master_stopping():
                    break
                if self._restarting:
                    self._restarting, delay = False, 1
                    self.log.info("Scheduler process %s stopped for a reload", proc.pid)
                    continue
                if time.monotonic() - started >= HEALTHY_AFTER:
                    delay = 1
                self.log.warning("Scheduler process %s exited (%s): restarting in %ss",
                                 proc.pid, code, delay)
            self._wake.wait(delay)
            self._wake.clear()
            if self._restarting:  # a reload during the backoff starts one at once
                self._restarting, delay = False, 1
            else:
                delay = min(delay * 2, BACKOFF_MAX)

    def _wait(self, proc):
        """The process's exit code. The master stopping stops it at once, beside the workers'
        drain: an orchestrator's kill at the end of its grace then finds the node released.
        A reload stops it from here too: this watcher is the only thread a worker inherits."""
        stopped_for_reload = False
        while True:
            if _gone(proc):
                return proc.returncode
            if self._nudge.wait(STOP_POLL):
                self._nudge.clear()
            if _gone(proc):
                return proc.returncode
            if self._mine() and self._master_stopping():
                self._stopping = True
                self._terminate()
                self._say_stopped()
            elif self._mine() and self._restarting and not stopped_for_reload:
                stopped_for_reload = True
                self._terminate()

    def _say_stopped(self) -> None:
        # Under the lock: on_exit, coming second, waits for the watcher's call to end
        with self._stopped_lock:
            if self._stopped_said or self._on_stopped is None or not self._mine():
                return
            self._stopped_said = True
            try:
                self._on_stopped()
            except Exception as e:  # the stop goes on; atexit releases the row again
                self.log.warning("Node stop not recorded: %s", type(e).__name__)

    def _terminate(self) -> None:
        """SIGTERM, graceful_timeout for the running task to end, then SIGKILL."""
        proc = self._proc
        if proc is None or not self._mine() or proc.poll() is not None:
            return
        try:
            proc.send_signal(signal.SIGTERM)
        except OSError:
            return
        if _wait_gone(proc, self.graceful_timeout + 5) or not self._mine():
            return
        self.log.warning("Scheduler process %s killed after %ss", proc.pid, self.graceful_timeout)
        try:
            proc.kill()
        except OSError:
            return
        _wait_gone(proc, 5)

    def restart(self) -> None:
        """New code and configuration on HUP: the watcher stops the process and starts another.
        No thread of its own: under gevent, one running as the arbiter forks dies in the worker."""
        if self._thread is None or self._stopping:
            return
        self._restarting = True
        self._wake.set()
        self._nudge.set()

    def stop(self, on_stopped=None) -> None:
        """``on_stopped``: used when start() was given none (the master stops before ready)."""
        if self._on_stopped is None:
            self._on_stopped = on_stopped
        self._stopping = True
        self._wake.set()
        self._nudge.set()
        self._terminate()
        self._say_stopped()


supervisor = SchedulerSupervisor()
