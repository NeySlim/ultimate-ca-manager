"""The scheduled tasks in a process of their own, started and watched by the gunicorn master.

A task may hold the CPU or a database connection for minutes: here it delays no
request and no worker heartbeat, and nothing forks while it runs. No gevent here.
"""
import logging
import os
import signal
import threading

GRACE_ENV = 'UCM_SCHEDULER_GRACEFUL_TIMEOUT'

logger = logging.getLogger('ucm.scheduler_main')


def main() -> int:
    from services.scheduler_service import SUPERVISED_ENV, get_scheduler
    os.environ[SUPERVISED_ENV] = '1'  # create_app registers the tasks, the loop starts below

    stop = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stop.set())
    signal.signal(signal.SIGHUP, signal.SIG_IGN)  # the master restarts this process itself

    from app import create_app, run_startup_housekeeping
    app = create_app()
    run_startup_housekeeping(app)
    scheduler = get_scheduler()
    scheduler.rearm_grace()
    scheduler.start(app=app)
    logger.info("Scheduler process %s started", os.getpid())

    parent = os.getppid()
    while not stop.wait(1):
        if os.getppid() != parent:
            logger.warning("The gunicorn master is gone: the scheduler process stops")
            break

    grace = float(os.environ.get(GRACE_ENV, '30'))
    scheduler.relinquish()
    thread = scheduler._thread
    if thread is not None:
        thread.join(grace)
        if thread.is_alive():
            # A stop that was asked for: 0, or the arbiter logs "Worker exited with code 1"
            logger.warning("A scheduled task outlasted %ss: the scheduler process exits anyway", grace)
            logging.shutdown()
            os._exit(0)
    logger.info("Scheduler process %s stopped", os.getpid())
    return 0


def exit_code(run) -> int:
    """0 or 1, whatever ``run`` returns or raises.

    The gunicorn arbiter reaps every child with waitpid(-1) and halts the whole
    service on 3 or 4 (worker boot / app load error); a SIGKILL here still logs
    "Worker (pid) was sent SIGKILL", which nothing in this process can prevent.
    """
    try:
        code = run()
    except SystemExit as e:
        code = e.code
    except BaseException:
        logger.exception("The scheduler process failed")
        code = 1
    return 0 if code in (0, None) else 1


if __name__ == '__main__':
    code = exit_code(main)
    logging.shutdown()
    os._exit(code)
