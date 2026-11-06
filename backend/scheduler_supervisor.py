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

    @property
    def pid(self):
        return self._proc.pid if self._proc is not None else None

    def start(self, server=None) -> None:
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
        from scheduler_main import GRACE_ENV
        env = dict(os.environ, UCM_SCHEDULER_PROCESS='1', **{GRACE_ENV: str(self.graceful_timeout)})
        return subprocess.Popen(self.command, cwd=BACKEND, env=env)

    def _mine(self) -> bool:
        # A worker forked from the master inherits this object and its greenlets:
        # there they must neither signal nor start anything
        return self._owner_pid == os.getpid()

    def _master_stopping(self) -> bool:
        # Arbiter.stop() empties LISTENERS first, before on_exit, while workers drain
        return self._stopping or (self._server is not None and not self._server.LISTENERS)

    def _watch(self) -> None:
        delay = 1
        while self._mine() and not self._master_stopping():
            started = time.monotonic()
            try:
                self._proc = proc = self._spawn()
            except OSError as e:
                self.log.error("Scheduler process not started: %s", e)
                proc = None
            if not self._mine():
                return
            if proc is not None:
                self.log.info("Scheduler process started (pid %s)", proc.pid)
                code = proc.wait()
                if not self._mine() or self._master_stopping():
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

    def _terminate(self) -> None:
        """SIGTERM, graceful_timeout for the running task to end, then SIGKILL."""
        proc = self._proc
        if proc is None or not self._mine() or proc.poll() is not None:
            return
        try:
            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=self.graceful_timeout + 5)
        except subprocess.TimeoutExpired:
            if not self._mine():
                return
            self.log.warning("Scheduler process %s killed after %ss", proc.pid, self.graceful_timeout)
            proc.kill()
            proc.wait(timeout=5)
        except OSError:
            pass

    def restart(self) -> None:
        """New code and configuration on HUP: stop the process, the watcher starts another."""
        if self._thread is None or self._stopping:
            return
        self._restarting = True
        self._wake.set()
        threading.Thread(target=self._terminate, name='scheduler-restart', daemon=True).start()

    def stop(self) -> None:
        self._stopping = True
        self._wake.set()
        self._terminate()


supervisor = SchedulerSupervisor()
