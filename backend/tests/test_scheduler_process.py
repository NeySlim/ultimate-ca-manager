"""The scheduled tasks run in a process of their own, which the gunicorn master
starts, restarts and stops (a blocking task there delays no request)."""
import os
import signal
import subprocess
import sys
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

    class Thread:
        def join(self, timeout):
            calls.append(('join', timeout))

        def is_alive(self):
            return False

    class Scheduler:
        _thread = Thread()

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
    assert scheduler_main.main() == 0
    assert calls == [('create_app', '1'), ('housekeeping', 'the-app'), 'rearm', ('start', 'the-app'),
                     'relinquish', ('join', 7.0)]


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


def test_a_stop_cut_short_by_a_long_task_still_exits_0(monkeypatch):
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
        _thread = types.SimpleNamespace(join=lambda timeout: None, is_alive=lambda: True)

        def rearm_grace(self):
            pass

        def start(self, app):
            handlers[signal.SIGTERM]()

        def relinquish(self):
            pass
    monkeypatch.setattr(app_module, 'create_app', lambda: 'the-app')
    monkeypatch.setattr(app_module, 'run_startup_housekeeping', lambda a: None)
    monkeypatch.setattr(scheduler_service, 'get_scheduler', lambda: Scheduler())
    with pytest.raises(Exit):
        scheduler_main.main()
    assert exits == [0]
