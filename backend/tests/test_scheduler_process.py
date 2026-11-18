"""The scheduled tasks run in a process of their own, which the gunicorn master
starts, restarts and stops (a blocking task there delays no request)."""
import os
import signal
import subprocess
import sys
import threading
import time
import types

import pytest

import scheduler_supervisor
from scheduler_supervisor import SchedulerSupervisor

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _wait(predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:  # reaped by its parent or not, a zombie is gone
        with open(f'/proc/{pid}/stat') as handle:
            return handle.read().split(') ')[1][0] != 'Z'
    except OSError:
        return False


@pytest.fixture
def supervisor(tmp_path):
    made = []

    def make(script='import time\nwhile True: time.sleep(1)\n', graceful=1.0):
        path = tmp_path / f'child{len(made)}.py'
        path.write_text(script)
        s = SchedulerSupervisor(command=[sys.executable, str(path)])
        s.graceful_timeout = graceful
        made.append(s)
        return s
    yield make
    for s in made:
        s.stop()


def test_a_killed_scheduler_process_is_started_again(supervisor, monkeypatch):
    s = supervisor()
    s.start()
    assert _wait(lambda: s.pid is not None)
    first = s.pid
    os.kill(first, signal.SIGKILL)
    assert _wait(lambda: s.pid not in (None, first), timeout=5)
    assert _alive(s.pid)


def test_restarts_back_off(supervisor, monkeypatch):
    waits = []
    s = supervisor(script='raise SystemExit(3)\n')
    real_wait = s._wake.wait
    s._wake.wait = lambda delay: (waits.append(delay), real_wait(0.01))[1]
    s.start()
    assert _wait(lambda: len(waits) >= 4)
    s.stop()
    assert waits[:4] == [1, 2, 4, 8]


def test_a_reload_replaces_the_process_at_once(supervisor):
    s = supervisor()
    s.start()
    assert _wait(lambda: s.pid is not None)
    first = s.pid
    asked = time.monotonic()
    s.restart()
    assert _wait(lambda: s.pid not in (None, first), timeout=3)
    assert time.monotonic() - asked < 0.8  # no backoff for a reload
    assert not _alive(first)


def test_stop_terminates_then_kills(supervisor):
    s = supervisor(script='import signal, time\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\n'
                          'open(__file__ + ".up", "w").close()\nwhile True: time.sleep(1)\n',
                   graceful=0.5)
    s.start()
    assert _wait(lambda: s.pid is not None and os.path.exists(s.command[1] + '.up'))
    pid = s.pid
    started = time.monotonic()
    s.stop()
    assert not _alive(pid)
    assert time.monotonic() - started >= 0.5  # SIGTERM first, SIGKILL past the graceful timeout


def test_no_new_process_once_the_master_stops(supervisor):
    s = supervisor()
    s.start(types.SimpleNamespace(log=s.log, LISTENERS=['listener'],
                                  cfg=types.SimpleNamespace(graceful_timeout=1)))
    assert _wait(lambda: s.pid is not None)
    first = s.pid
    s._server.LISTENERS = []  # Arbiter.stop() empties them before on_exit
    os.kill(first, signal.SIGKILL)
    time.sleep(1.5)
    assert s.pid == first


def test_the_inherited_watcher_parks_instead_of_returning(supervisor, monkeypatch):
    # Returning from the thread raises KeyError under gevent after a fork
    s = supervisor()
    s._owner_pid = os.getpid() + 1
    parked = []

    class _Parked(Exception):
        pass

    def _park():
        parked.append(True)
        raise _Parked

    monkeypatch.setattr(s, '_park', _park)
    with pytest.raises(_Parked):
        s._watch()
    assert parked and s.pid is None


def test_a_forked_worker_never_signals_the_scheduler_process(supervisor):
    s = supervisor()
    s.start()
    assert _wait(lambda: s.pid is not None)
    s._owner_pid = os.getpid() + 1  # the copy a worker inherits
    s._terminate()
    assert _alive(s.pid)
    s._owner_pid = os.getpid()


def _scheduler_env(tmp_path):
    data = tmp_path / 'data'
    data.mkdir()
    env = dict(os.environ)
    for name in ('PYTEST_XDIST_WORKER', 'PYTEST_CURRENT_TEST', 'UCM_TEST_PG_URL', 'UCM_TEST_APP_PG_URL'):
        env.pop(name, None)
    env.update({
        'DATA_DIR': str(data), 'DATABASE_PATH': str(data / 'ucm.db'), 'DATABASE_URL': '',
        'UCM_LOG_FILE': str(tmp_path / 'ucm.log'), 'LOG_FILE': str(tmp_path / 'ucm.log'),
        'AUDIT_LOG_FILE': str(tmp_path / 'audit.log'),
        'HTTPS_CERT_PATH': str(data / 'https_cert.pem'), 'HTTPS_KEY_PATH': str(data / 'https_key.pem'),
        'UCM_SCHEDULER_GRACEFUL_TIMEOUT': '5', 'UCM_SCHEDULER_SUPERVISED': '1',
    })
    return env, data


def test_the_scheduler_process_runs_the_loop_and_stops_on_sigterm(tmp_path):
    env, data = _scheduler_env(tmp_path)
    proc = subprocess.Popen([sys.executable, '-m', 'scheduler_main'], cwd=BACKEND, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert _wait(lambda: (data / 'scheduler_state.json').exists(), timeout=60)
        assert (data / 'scheduler.lock').read_text() == str(proc.pid)
        # The loop thread publishes its state before main() logs the start
        assert _wait(lambda: f'Scheduler process {proc.pid} started' in (tmp_path / 'ucm.log').read_text())
        proc.send_signal(signal.SIGTERM)
        assert proc.wait(timeout=15) == 0
        assert f'Scheduler process {proc.pid} stopped' in (tmp_path / 'ucm.log').read_text()
    finally:
        proc.kill()
        proc.wait()


def test_the_scheduler_process_stops_when_its_master_dies(tmp_path):
    env, data = _scheduler_env(tmp_path)
    pidfile = tmp_path / 'scheduler.pid'
    # A stand-in master: a shell that starts the scheduler process and waits
    master = subprocess.Popen(['sh', '-c', f'{sys.executable} -m scheduler_main & echo $! > {pidfile}; wait'],
                              cwd=BACKEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert _wait(lambda: (data / 'scheduler_state.json').exists(), timeout=60)
        child = int(pidfile.read_text())
        master.kill()
        master.wait()
        assert _wait(lambda: not _alive(child), timeout=15)
        assert 'The gunicorn master is gone' in (tmp_path / 'ucm.log').read_text()
    finally:
        master.kill()
        if pidfile.exists():
            try:
                os.kill(int(pidfile.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_the_scheduler_process_prepares_then_runs_then_hands_over(monkeypatch):
    import app as app_module
    import scheduler_main
    from services import scheduler_service

    calls, handlers = [], {}
    monkeypatch.setenv('UCM_SCHEDULER_GRACEFUL_TIMEOUT', '7')
    monkeypatch.setenv(scheduler_service.SUPERVISED_ENV, '')  # main() sets it: undone after
    monkeypatch.setattr(scheduler_main.signal, 'signal', lambda sig, h: handlers.__setitem__(sig, h))

    class Scheduler:
        def join(self, timeout):
            calls.append(('join', timeout))
            return True

        def rearm_grace(self):
            calls.append('rearm')

        def start(self, app):
            calls.append(('start', app))
            handlers[signal.SIGTERM]()  # the master asks it to stop

        def relinquish(self):
            calls.append('relinquish')

    def create_app():
        calls.append(('create_app', os.environ.get(scheduler_service.SUPERVISED_ENV)))
        return 'the-app'
    monkeypatch.setattr(app_module, 'create_app', create_app)
    monkeypatch.setattr(app_module, 'run_startup_housekeeping', lambda a: calls.append(('housekeeping', a)))
    monkeypatch.setattr(scheduler_service, 'get_scheduler', lambda: Scheduler())
    monkeypatch.setattr('services.ws_relay.start_publisher', lambda a: calls.append(('relay', a)))
    monkeypatch.setattr('services.ws_relay.stop_publisher', lambda **kw: calls.append('relay stop'))

    class Runner:
        def __init__(self, app, scheduler):
            calls.append(('jobs', app))

        def start(self):
            return self

        def stop(self):
            calls.append('jobs stop')

        def join(self, timeout):
            calls.append('jobs join')
            return True
    monkeypatch.setattr('services.jobs.runner.JobRunner', Runner)
    assert scheduler_main.main() == 0
    assert calls == [('create_app', '1'), ('relay', 'the-app'), ('housekeeping', 'the-app'), 'rearm',
                     ('start', 'the-app'), ('jobs', 'the-app'), 'jobs stop', 'relinquish',
                     ('join', 7.0), 'jobs join', 'relay stop']


def test_under_gunicorn_the_master_skips_the_startup_housekeeping(monkeypatch):
    import app as app_module
    from services import scheduler_service

    ran = []
    monkeypatch.setattr(app_module, 'run_startup_housekeeping', lambda a: ran.append(a))
    monkeypatch.setenv(scheduler_service.SUPERVISED_ENV, '1')
    app_module.create_app('testing')
    assert ran == []
    monkeypatch.setenv(scheduler_service.SUPERVISED_ENV, '')
    application = app_module.create_app('testing')
    assert ran == [application]


@pytest.mark.parametrize('outcome, expected', [
    (lambda: 0, 0), (lambda: None, 0), (lambda: sys.exit(0), 0),
    (lambda: 1, 1), (lambda: sys.exit(3), 1), (lambda: sys.exit(4), 1), (lambda: 4, 1),
    (lambda: 1 / 0, 1), (lambda: (_ for _ in ()).throw(KeyboardInterrupt), 1),
])
def test_the_scheduler_process_never_exits_with_a_code_that_halts_gunicorn(outcome, expected):
    import scheduler_main
    assert scheduler_main.exit_code(outcome) == expected


@pytest.mark.parametrize('task_ends, job_ends', [(False, True), (True, False)])
def test_a_stop_cut_short_by_a_long_task_still_exits_0(monkeypatch, caplog, task_ends, job_ends):
    import app as app_module
    import scheduler_main
    from services import scheduler_service

    handlers, exits = {}, []
    monkeypatch.setenv(scheduler_service.SUPERVISED_ENV, '')
    monkeypatch.setattr(scheduler_main.signal, 'signal', lambda sig, h: handlers.__setitem__(sig, h))

    class Exit(Exception):
        pass

    def fake_exit(code):
        exits.append(code)
        raise Exit
    monkeypatch.setattr(scheduler_main.os, '_exit', fake_exit)

    class Scheduler:
        def join(self, timeout):
            return task_ends

        def rearm_grace(self):
            pass

        def start(self, app):
            handlers[signal.SIGTERM]()

        def relinquish(self):
            pass
    monkeypatch.setattr(app_module, 'create_app', lambda: 'the-app')
    monkeypatch.setattr(app_module, 'run_startup_housekeeping', lambda a: None)
    monkeypatch.setattr(scheduler_service, 'get_scheduler', lambda: Scheduler())
    monkeypatch.setattr('services.ws_relay.start_publisher', lambda a: None)
    monkeypatch.setattr('services.ws_relay.stop_publisher', lambda **kw: exits.append('relay stop'))

    class Runner:
        def __init__(self, app, scheduler):
            pass

        def start(self):
            return self

        def stop(self):
            pass

        def join(self, timeout):
            return job_ends
    monkeypatch.setattr('services.jobs.runner.JobRunner', Runner)
    with caplog.at_level('WARNING', logger='ucm.scheduler_main'), pytest.raises(Exit):
        scheduler_main.main()
    assert exits == ['relay stop', 0]
    assert 'A scheduled task or a background job outlasted 30.0s' in caplog.text


def test_the_master_stopping_stops_the_process_then_releases_the_node(supervisor):
    """SIGTERM to the master: the scheduler process stops beside the workers' drain, and the
    node's row is released at once, not after graceful_timeout of open connections."""
    s = supervisor()
    calls = []
    server = types.SimpleNamespace(log=s.log, LISTENERS=['listener'],
                                   cfg=types.SimpleNamespace(graceful_timeout=1))
    s.start(server, on_stopped=lambda: calls.append(s._proc.poll()))
    assert _wait(lambda: s.pid is not None)
    pid = s.pid
    server.LISTENERS = []  # Arbiter.stop() empties them, then drains the workers
    assert _wait(lambda: not _alive(pid), timeout=3)
    assert _wait(lambda: calls, timeout=3)
    assert calls[0] is not None  # after the process exited: its last heartbeat is written
    s.stop()
    assert len(calls) == 1


def test_stop_releases_the_node_once(supervisor):
    s = supervisor()
    calls = []
    s.start(on_stopped=lambda: calls.append(1))
    assert _wait(lambda: s.pid is not None)
    s.stop()
    s.stop()
    assert calls == [1]


class _UnseenExit:
    """The process as gevent's Popen sees it in the master once the arbiter's waitpid(-1)
    reaped it first: its child watcher never fires, poll() stays None, wait() times out."""

    def __init__(self, proc):
        self._proc, self.pid, self.returncode = proc, proc.pid, None

    def poll(self):
        return None

    def wait(self, timeout=None):
        time.sleep(timeout or 0)
        raise subprocess.TimeoutExpired('scheduler', timeout)

    def send_signal(self, signum):
        os.kill(self.pid, signum)

    def kill(self):
        self.send_signal(signal.SIGKILL)


def test_a_process_another_reaper_collected_counts_as_stopped(supervisor):
    s = supervisor(graceful=3.0)
    calls = []
    s._owner_pid, s._on_stopped = os.getpid(), lambda: calls.append(1)
    real = s._spawn()
    s._proc = _UnseenExit(real)
    # The arbiter's reap_workers collects the exit, so the Popen object never sees it
    reaper = threading.Thread(target=os.waitpid, args=(real.pid, 0), daemon=True)
    reaper.start()
    started = time.monotonic()
    s.stop()
    assert time.monotonic() - started < 1.5, 'waited for an exit nobody would report'
    assert calls == [1]
    reaper.join(5)
    real.returncode = 0


def test_on_exit_waits_for_the_stop_the_watcher_is_recording(supervisor):
    s = supervisor()
    entered, release, calls = threading.Event(), threading.Event(), []

    def slow():
        entered.set()
        release.wait(5)
        calls.append('recorded')
    s._owner_pid, s._on_stopped = os.getpid(), slow
    watcher = threading.Thread(target=s._say_stopped)
    watcher.start()
    assert entered.wait(5)
    threading.Timer(0.3, release.set).start()
    s.stop()  # on_exit: returns only once the row is recorded, or the exit would cut it off
    assert calls == ['recorded']
    watcher.join(5)


@pytest.mark.parametrize('named', [False, True])
def test_a_master_that_dies_while_the_scheduler_process_starts_is_noticed(monkeypatch, caplog, named):
    """The parent is read before the application loads, or named by the master: an orphan stops."""
    import app as app_module
    import scheduler_main
    from services import scheduler_service

    handlers, started, asked = {}, [], []
    monkeypatch.setenv('UCM_SCHEDULER_GRACEFUL_TIMEOUT', '1')
    monkeypatch.setenv(scheduler_service.SUPERVISED_ENV, '')
    monkeypatch.setattr(scheduler_main.signal, 'signal', lambda sig, h: handlers.__setitem__(sig, h))

    def getppid():
        asked.append(1)
        if len(asked) > 5:  # a process that never notices is stopped, and the test fails below
            handlers[signal.SIGTERM]()
        # Not named: the master dies once the loop runs. Named: it was gone before main() ran
        return 1 if started or named else 4242
    monkeypatch.setattr(scheduler_main.os, 'getppid', getppid)
    if named:
        monkeypatch.setenv(scheduler_main.MASTER_ENV, '4242')
    else:
        monkeypatch.delenv(scheduler_main.MASTER_ENV, raising=False)

    class Scheduler:
        join = staticmethod(lambda timeout: True)
        rearm_grace = relinquish = staticmethod(lambda: None)
        start = staticmethod(lambda app: started.append(app))

    class Runner:
        def __init__(self, app, scheduler):
            pass
        start = lambda self: self  # noqa: E731
        stop = lambda self: None  # noqa: E731
        join = lambda self, timeout: True  # noqa: E731

    monkeypatch.setattr(app_module, 'create_app', lambda: 'the-app')
    monkeypatch.setattr(app_module, 'run_startup_housekeeping', lambda a: None)
    monkeypatch.setattr(scheduler_service, 'get_scheduler', lambda: Scheduler())
    monkeypatch.setattr('services.ws_relay.start_publisher', lambda a: None)
    monkeypatch.setattr('services.ws_relay.stop_publisher', lambda **kw: None)
    monkeypatch.setattr('services.jobs.runner.JobRunner', Runner)
    with caplog.at_level('WARNING', logger='ucm.scheduler_main'):
        assert scheduler_main.main() == 0
    assert 'The gunicorn master is gone' in caplog.text


def test_the_supervisor_names_itself_to_the_scheduler_process(monkeypatch):
    import scheduler_main
    import scheduler_supervisor

    seen = {}
    monkeypatch.setattr(scheduler_supervisor.subprocess, 'Popen', lambda cmd, cwd, env: seen.update(env) or None)
    scheduler_supervisor.SchedulerSupervisor()._spawn()
    assert seen[scheduler_main.MASTER_ENV] == str(os.getpid())
