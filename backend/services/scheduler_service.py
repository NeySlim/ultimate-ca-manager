"""
Scheduler Service - Background Task Scheduling
Uses standard Python threading and time modules (no external dependencies like APScheduler)
Safe for Docker, systemd, and development environments
"""
import threading
import time
import os
import atexit
import errno
import fcntl
import json
import logging
from datetime import datetime
from typing import Dict, Callable, Optional, Any
from threading import Lock
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

# Set by gunicorn_config: the loop runs in a process of its own (scheduler_main),
# the master and the web workers only register the tasks
SUPERVISED_ENV = 'UCM_SCHEDULER_SUPERVISED'
# How often a process waiting for the scheduler lock tries again
LOCK_RETRY_SECONDS = 5
# How often the loop wakes; a heartbeat is written at most once per wake
WAKE_INTERVAL_SECONDS = 60
# How soon the loop sees a "run now" asked by a web worker, and how long that worker waits
REQUEST_POLL_SECONDS = 1
RUN_NOW_WAIT_SECONDS = 30
STATE_FILE = 'scheduler_state.json'
REQUESTS_DIR = 'scheduler_requests'
# HA: the same state in system_config, and run-now requests in the scheduler_requests table
STATE_KEY = 'scheduler.state'
# flock's answers for "someone else holds it"; any other error means no flock here
_BUSY_ERRNOS = frozenset(filter(None, (errno.EACCES, errno.EAGAIN, getattr(errno, 'EWOULDBLOCK', None))))


def supervised() -> bool:
    return os.environ.get(SUPERVISED_ENV) == '1'


def _ha() -> bool:
    from utils.ha import ha_enabled
    return ha_enabled()


def _data_path(name: str) -> str:
    try:
        from config.settings import DATA_DIR
        return os.path.join(str(DATA_DIR), name)
    except Exception:
        return os.path.join('/tmp', f'ucm-{name}')


class TaskReportedFailure(RuntimeError):
    """A task returned {'status': 'failed'} instead of raising."""


class ScheduledTask:
    """Represents a scheduled task with metadata"""
    
    def __init__(
        self, 
        name: str, 
        func: Callable,
        interval: int,  # in seconds
        description: str = "",
        enabled: bool = True
    ):
        """
        Initialize a scheduled task
        
        Args:
            name: Unique task identifier
            func: Callable to execute
            interval: Interval in seconds between executions
            description: Human-readable description
            enabled: Whether task is enabled
            initial_delay: Seconds to wait before first execution (0 = run immediately)
        """
        self.name = name
        self.func = func
        self.interval = interval
        self.description = description
        self.enabled = enabled
        self.last_run: Optional[datetime] = None
        self.next_run: Optional[datetime] = None
        self.run_count = 0
        self.last_error: Optional[str] = None
        self.last_duration_ms = 0.0
        # Outcome of the last run: 'ok', 'warning', 'skipped' or 'failed'. A task that
        # returns a result dict says which one itself, so a run that produced
        # nothing (backup not due, no password) is no longer indistinguishable
        # from one that did the work.
        self.last_status: Optional[str] = None
        self.last_reason: Optional[str] = None
        self._created_at = utc_now()
    
    def should_run(self) -> bool:
        """Check if task should run based on interval"""
        if not self.enabled:
            return False
        if self.last_run is None:
            # Grace period: wait 30s after creation before first run
            # to let SSL/network stack initialize after worker fork
            age = (utc_now() - self._created_at).total_seconds()
            return age >= 30
        elapsed = (utc_now() - self.last_run).total_seconds()
        return elapsed >= self.interval
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "name": self.name,
            "description": self.description,
            "interval": self.interval,
            "enabled": self.enabled,
            "last_run": (self.last_run.isoformat() + 'Z') if self.last_run else None,
            "next_run": (self.next_run.isoformat() + 'Z') if self.next_run else None,
            "run_count": self.run_count,
            "last_error": self.last_error,
            "last_status": self.last_status,
            "last_reason": self.last_reason,
            "last_duration_ms": self.last_duration_ms,
        }


class SchedulerService:
    """
    Background scheduler using Python threading
    
    Features:
    - Daemon thread that wakes up every N seconds
    - Simple task registry (dict-based)
    - Thread-safe operations
    - Graceful shutdown
    - Task execution with error handling
    - Integration with Flask app context
    """
    
    def __init__(self, wake_interval: int = 60, node_id: Optional[str] = None):
        """
        Initialize scheduler
        
        Args:
            wake_interval: How often scheduler wakes up to check tasks (in seconds)
            node_id: This node's name in HA mode (default: Config.NODE_ID)
        """
        self.wake_interval = wake_interval
        self._node_id = node_id
        # HA: the PostgreSQL leader lock; None means the host lock (flock / pid file)
        self._leader_lock = None
        self._leader_lock_pid = None
        # Set when the lock goes away, mid-pass or not: the next pass waits instead of retaking it
        self._lost_lock = False
        self._started_at = utc_now()
        self._last_heartbeat = None
        self._heartbeat_error_logged = False
        self._claimed: Dict[str, list] = {}
        self._leadership_hooks: list = []
        self.tasks: Dict[str, ScheduledTask] = {}
        self.tasks_lock = Lock()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._app = None
        self._owns_lock = False
        self._owner_pid = None
        self._lock_path = None
        self._lock_fd = None
        self._pid_file = None
        self._flock_unsupported = False
        self._lock_error_logged = False
        self._publish_error_logged = False
        self._wake = threading.Event()
        logger.info(f"SchedulerService initialized (wake interval: {wake_interval}s)")
    
    def register_task(
        self, 
        name: str, 
        func: Callable,
        interval: int,
        description: str = "",
        enabled: bool = True
    ) -> None:
        """
        Register a new scheduled task
        
        Args:
            name: Unique task identifier
            func: Callable to execute
            interval: Interval in seconds
            description: Human-readable description
            enabled: Whether task starts enabled
        """
        with self.tasks_lock:
            if name in self.tasks:
                logger.warning(f"Task '{name}' already registered, replacing")
            
            task = ScheduledTask(
                name=name,
                func=func,
                interval=interval,
                description=description,
                enabled=enabled
            )
            self.tasks[name] = task
            logger.info(
                f"Registered task '{name}' (interval: {interval}s, "
                f"enabled: {enabled}, description: {description})"
            )
    
    def unregister_task(self, name: str) -> bool:
        """
        Remove a scheduled task
        
        Args:
            name: Task identifier
            
        Returns:
            True if task was removed, False if not found
        """
        with self.tasks_lock:
            if name in self.tasks:
                del self.tasks[name]
                logger.info(f"Unregistered task '{name}'")
                return True
            return False
    
    def enable_task(self, name: str) -> bool:
        """Enable a task by name"""
        with self.tasks_lock:
            if name in self.tasks:
                self.tasks[name].enabled = True
                logger.info(f"Enabled task '{name}'")
                return True
            return False
    
    def disable_task(self, name: str) -> bool:
        """Disable a task by name"""
        with self.tasks_lock:
            if name in self.tasks:
                self.tasks[name].enabled = False
                logger.info(f"Disabled task '{name}'")
                return True
            return False
    
    def _delegated(self) -> bool:
        """Whether the loop runs in the scheduler process rather than here.

        In HA mode any process but the leader's loop asks the leader, through the database.
        """
        if _ha():
            return not (self._running and self._owns_lock)
        return supervised() and not self._running

    def run_task_now(self, name: str) -> Optional[Dict[str, Any]]:
        """Run a task at once and return its status after the run.

        Where the scheduler process runs the loop, the run is asked of it and
        awaited up to RUN_NOW_WAIT_SECONDS; past that the status says ``queued``.
        """
        with self.tasks_lock:
            task = self.tasks.get(name)
        if not task:
            return None
        if self._delegated():
            return self._run_in_scheduler_process(name)
        self._run_task(task)
        with self.tasks_lock:
            return task.to_dict()

    def _run_in_scheduler_process(self, name: str) -> Dict[str, Any]:
        def marker(status):
            return status.get('run_count'), status.get('last_run')
        before = marker(self.get_task_status(name) or {})
        if _ha():
            from models import SchedulerRequest, db
            db.session.add(SchedulerRequest(task_name=name, requested_at=utc_now(),
                                            requested_by=self.node_id))
            db.session.commit()
        else:
            directory = _data_path(REQUESTS_DIR)
            os.makedirs(directory, exist_ok=True)
            with open(os.path.join(directory, name), 'w') as handle:
                handle.write(utc_now().isoformat())
        deadline = time.monotonic() + RUN_NOW_WAIT_SECONDS
        while True:
            status = self.get_task_status(name) or {}
            if marker(status) != before:
                return status
            if time.monotonic() >= deadline:
                return dict(status, queued=True)
            time.sleep(0.25)

    def get_task_status(self, name: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific task"""
        return self.get_all_tasks_status().get(name)

    def get_all_tasks_status(self) -> Dict[str, Dict[str, Any]]:
        """Status of every registered task, as the process running the loop last published it."""
        with self.tasks_lock:
            statuses = {
                name: task.to_dict()
                for name, task in self.tasks.items()
            }
        if self._delegated():
            state = self._published_state()
            published = state.get('tasks', {})
            statuses.update({name: published[name] for name in statuses if name in published})
            if self.state_is_stale(state):
                for status in statuses.values():
                    status['stale'] = True
        return statuses

    def state_is_stale(self, state=None) -> bool:
        """Whether the scheduler process stopped publishing (two passes missed)."""
        if not self._delegated():
            return False
        state = self._published_state() if state is None else state
        published_at = state.get('published_at')
        if not isinstance(published_at, (int, float)):
            return True
        return time.time() - published_at > 2 * self.wake_interval

    def rearm_grace(self) -> None:
        """First runs wait the grace period from now, not from registration."""
        now = utc_now()
        with self.tasks_lock:
            for task in self.tasks.values():
                task._created_at = now

    def _published_state(self) -> dict:
        if not _ha():
            return _read_state()
        try:
            from models import SystemConfig
            row = SystemConfig.query.filter_by(key=STATE_KEY).first()
            return json.loads(row.value) if row and row.value else {}
        except Exception as e:
            _rollback()
            logger.warning(f"Scheduler state not readable from the database: {type(e).__name__}")
            return {}

    def _publish_state(self) -> None:
        """Write the tasks' status where the web workers read it (atomic replace).

        In HA mode the leader also writes it to system_config, for every node.
        """
        ha = _ha() and self._owns_lock
        if not supervised() and not ha:
            return
        with self.tasks_lock:
            tasks = {name: task.to_dict() for name, task in self.tasks.items()}
        state = {'pid': os.getpid(), 'published_at': time.time(), 'tasks': tasks}
        if supervised():
            path = _data_path(STATE_FILE)
            temp = f'{path}.{os.getpid()}.tmp'
            try:
                with open(temp, 'w') as handle:
                    json.dump(state, handle)
                os.replace(temp, path)
            except OSError as e:
                if not self._publish_error_logged:  # once: the loop publishes every pass
                    logger.warning(f"Scheduler state not published to {path}: {e}")
                    self._publish_error_logged = True
        if ha:
            try:
                self._in_app(_store_state, state)
            except Exception as e:
                self._in_app(_rollback)
                logger.warning(f"Scheduler state not published to the database: {type(e).__name__}")

    def _take_requests(self) -> list:
        """The tasks a web worker asked to run now, each request consumed once."""
        if _ha():
            try:
                return self._in_app(self._claim_db_requests)
            except Exception as e:
                self._in_app(_rollback)
                logger.error(f"Scheduler requests not read: {type(e).__name__}: {e}")
                return []
        directory = _data_path(REQUESTS_DIR)
        try:
            names = os.listdir(directory)
        except OSError:
            return []
        taken = []
        for name in names:
            try:
                os.unlink(os.path.join(directory, name))
            except OSError:
                continue
            with self.tasks_lock:
                task = self.tasks.get(name)
            if task is not None and task not in taken:
                taken.append(task)
        return taken

    def _claim_db_requests(self) -> list:
        """Claim every unclaimed request: the conditional UPDATE gives each row to one leader only."""
        from sqlalchemy import update
        from models import SchedulerRequest, db
        rows = db.session.execute(
            update(SchedulerRequest).where(SchedulerRequest.taken_at.is_(None))
            .values(taken_at=utc_now())
            .returning(SchedulerRequest.id, SchedulerRequest.task_name),
            execution_options={'synchronize_session': False}).all()
        db.session.commit()
        taken, unknown = [], []
        for request_id, name in rows:
            with self.tasks_lock:
                task = self.tasks.get(name)
            if task is None:
                unknown.append(request_id)
                continue
            self._claimed.setdefault(name, []).append(request_id)
            if task not in taken:
                taken.append(task)
        if unknown:
            _delete_requests(unknown)
        return taken

    def _finish_request(self, task: ScheduledTask) -> None:
        ids = self._claimed.pop(task.name, None)
        if ids:
            try:
                self._in_app(_delete_requests, ids)
            except Exception as e:
                self._in_app(_rollback)
                logger.warning(f"Scheduler requests not deleted after the run: {type(e).__name__}")

    def _has_requests(self) -> bool:
        if _ha():
            try:
                return self._in_app(_db_requests_pending)
            except Exception:
                self._in_app(_rollback)
                return False
        try:
            return bool(os.listdir(_data_path(REQUESTS_DIR)))
        except OSError:
            return False

    def _wait_for_next_pass(self) -> None:
        deadline = time.monotonic() + self.wake_interval
        while self._running:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or ((supervised() or self._owns_lock and _ha()) and self._has_requests()):
                return
            self._wake.wait(min(REQUEST_POLL_SECONDS, remaining))
    
    def _run_task(self, task: ScheduledTask) -> None:
        """
        Execute a single task with error handling
        
        Args:
            task: ScheduledTask to execute
        """
        start_time = time.time()
        try:
            logger.debug(f"Running task '{task.name}'")
            
            # Run within app context if available (needed for DB access)
            if self._app:
                with self._app.app_context():
                    result = task.func()
            else:
                result = task.func()

            status, reason = self._outcome_of(result)
            if status == 'failed':
                # A task that reports its own failure is a failed run, not a
                # green one with a note attached.
                raise TaskReportedFailure(reason or 'task reported failure')

            duration_ms = (time.time() - start_time) * 1000
            task.last_duration_ms = duration_ms
            task.last_error = None
            task.last_status = status
            task.last_reason = reason
            task.run_count += 1
            task.last_run = utc_now()
            task.next_run = utc_now() + __import__('datetime').timedelta(seconds=task.interval)
            outcome = {'ok': 'completed successfully', 'warning': f'completed with a warning ({reason})'}
            log = logger.warning if status == 'warning' else logger.info
            log(
                f"Task '{task.name}' {outcome.get(status, f'skipped ({reason})')} "
                f"(duration: {duration_ms:.1f}ms, runs: {task.run_count})"
            )
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            task.last_duration_ms = duration_ms
            error_msg = (str(e) if isinstance(e, TaskReportedFailure)
                         else f"{type(e).__name__}: {str(e)}")
            task.last_error = error_msg
            task.last_status = 'failed'
            task.last_reason = None
            task.last_run = utc_now()
            logger.error(
                f"Task '{task.name}' failed: {error_msg} (duration: {duration_ms:.1f}ms)",
                exc_info=True
            )
    
    @staticmethod
    def _outcome_of(result) -> tuple:
        """Read a task's own report of what it did.

        Tasks that return nothing are treated as having done their work; one
        that returns {'status': 'skipped', 'reason': ...} says so instead, and
        'warning' is a run that did its work with something for the operator to see.
        """
        if isinstance(result, dict):
            status = result.get('status')
            if status in ('ok', 'warning', 'skipped', 'failed'):
                return status, result.get('reason')
        return 'ok', None

    @property
    def node_id(self) -> str:
        if self._node_id:
            return self._node_id
        from config.settings import Config
        return Config.NODE_ID

    def _singleton_lock(self):
        """SingletonLock: the PostgreSQL advisory lock in HA mode, the host lock otherwise."""
        from utils.ha import ha_enabled
        if not ha_enabled():
            return _HostLock(self)
        if self._leader_lock is None:
            from services.scheduler_leader import PgAdvisoryLock, application_url
            if self._app is not None:
                with self._app.app_context():
                    url = application_url()
            else:
                url = application_url()
            self._leader_lock = PgAdvisoryLock(url)
            self._leader_lock_pid = os.getpid()
        return self._leader_lock

    def _still_leader(self, lock) -> bool:
        """Checked before every task: once the lock is gone no task starts here."""
        if lock.still_held():
            return True
        if self._owns_lock:
            logger.error(f"Scheduler leadership lost on node {self.node_id}: no task starts here "
                         "until the lock is taken again")
            self._release_lock()
            self._lost_lock = True
        return False

    def _scheduler_loop(self) -> None:
        """Main scheduler loop - runs in background thread"""
        logger.info("Scheduler thread started")
        loop_pid = os.getpid()

        try:
            while self._running:
                if os.getpid() != loop_pid:
                    # A copy inherited through fork: only the process that started it runs it
                    logger.info("Scheduler loop detected in a forked process; exiting")
                    self._running = False
                    break
                lock = self._singleton_lock()
                # A node that just lost the lock waits a retry period: another one takes over first
                if self._owns_lock:
                    self._still_leader(lock)
                lost, self._lost_lock = self._lost_lock, False
                if not lost and not self._owns_lock and lock.acquire():
                    self._owns_lock, self._owner_pid = True, os.getpid()
                    logger.info(f"Scheduler lock acquired: pid {os.getpid()} on node {self.node_id} "
                                "runs the scheduled tasks")
                    self._heartbeat(force=True)
                    self._took_leadership()
                    self._publish_state()
                self._heartbeat(force=lost)
                if not self._owns_lock:
                    self._wake.wait(LOCK_RETRY_SECONDS)
                    continue
                try:
                    requested = self._take_requests() if supervised() or _ha() else []
                    with self.tasks_lock:
                        tasks_to_run = requested + [
                            task for task in self.tasks.values()
                            if task.should_run() and task not in requested
                        ]

                    # Execute tasks outside of lock
                    for task in tasks_to_run:
                        if not self._running or not self._still_leader(lock):
                            break
                        try:
                            self._run_task(task)
                        except Exception as e:
                            logger.error(
                                f"Unexpected error running task '{task.name}': {e}",
                                exc_info=True
                            )
                        if self._claimed:
                            self._finish_request(task)
                        self._publish_state()
                        # Throttled: a pass longer than the stale window keeps this row fresh
                        self._heartbeat()
                except Exception as e:
                    logger.error(f"Error in scheduler loop: {e}", exc_info=True)
                self._publish_state()  # every pass: the web workers judge staleness by it
                self._wait_for_next_pass()
        finally:
            # The next process waiting for the lock takes over from here
            self._release_lock()
            self._heartbeat(force=True)

    def on_leadership(self, hook: Callable[[], Any]) -> None:
        """HA: run ``hook`` in the app context each time this process becomes the leader."""
        self._leadership_hooks.append(hook)

    def _took_leadership(self) -> None:
        """HA: requests a former leader claimed and never finished are dropped, not replayed."""
        if not _ha():
            return
        self._claimed.clear()
        for hook in [_drop_abandoned_requests] + self._leadership_hooks:
            try:
                self._in_app(hook)
            except Exception as e:
                self._in_app(_rollback)
                logger.error(f"Leadership takeover step failed: {type(e).__name__}: {e}")

    def _heartbeat(self, force: bool = False) -> None:
        """HA: this node's row in cluster_nodes, at most once a pass unless leadership changed."""
        from utils.ha import ha_enabled
        if not ha_enabled():
            return
        now = time.monotonic()
        if not force and self._last_heartbeat is not None \
                and now - self._last_heartbeat < self.wake_interval:
            return
        from services.scheduler_leader import write_heartbeat
        try:
            self._in_app(write_heartbeat, self.node_id, self._owns_lock, self._started_at)
            self._last_heartbeat = now
            self._heartbeat_error_logged = False
        except Exception as e:
            self._in_app(_rollback)
            if not self._heartbeat_error_logged:
                logger.error(f"Node heartbeat not written: {type(e).__name__}: {e}")
                self._heartbeat_error_logged = True

    def _in_app(self, fn, *args):
        if self._app is not None:
            with self._app.app_context():
                return fn(*args)
        return fn(*args)

    def _acquire_singleton_lock(self) -> bool:
        """Take the host-wide scheduler lock, so only ONE process runs the loop.

        An flock held for as long as the loop runs: the kernel frees it when its
        holder dies. A filesystem without flock falls back to a pid file.
        """
        self._lock_path = _data_path('scheduler.lock')
        if self._flock_unsupported:
            return self._acquire_pid_file()
        try:
            fd = os.open(self._lock_path, os.O_CREAT | os.O_RDWR, 0o644)
        except OSError as e:
            if not self._lock_error_logged:
                logger.error(f"Scheduler lock {self._lock_path} cannot be opened: {e}")
                self._lock_error_logged = True
            return False
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            os.close(fd)
            if e.errno in _BUSY_ERRNOS:
                return False
            logger.error(f"No flock on {self._lock_path} ({e}): the scheduler falls back to a pid file")
            self._flock_unsupported = True
            return self._acquire_pid_file()
        try:
            os.ftruncate(fd, 0)
            os.write(fd, str(os.getpid()).encode())  # who holds it, for an operator
        except OSError:
            pass
        self._lock_fd = fd
        self._owns_lock = True
        self._owner_pid = os.getpid()
        return True

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True  # exists but owned by another user
        return True

    def _acquire_pid_file(self) -> bool:
        """Atomic O_EXCL pid file, reclaimed when its process is gone.

        Only on filesystems without flock: after a container restart a reused pid
        can make a stale file look held, until that process exits.
        """
        path = _data_path('scheduler.pid')
        for _ in range(2):
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            except FileExistsError:
                try:
                    with open(path) as handle:
                        other = int(handle.read().strip() or '0')
                except (OSError, ValueError):
                    other = 0
                if other and other != os.getpid() and self._pid_alive(other):
                    return False
                try:
                    os.unlink(path)  # stale: its process is gone
                except OSError:
                    pass
                continue
            except OSError as e:
                if not self._lock_error_logged:
                    logger.error(f"Scheduler pid file {path} cannot be created: {e}")
                    self._lock_error_logged = True
                return False
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            self._pid_file = path
            self._owns_lock = True
            self._owner_pid = os.getpid()
            return True
        return False

    def _release_lock(self) -> None:
        # A forked copy shares the holder's open file and lock session: closing them there
        # would not free the lock, and must not touch the holder's state either
        if self._owns_lock and self._owner_pid != os.getpid():
            return
        owned, self._owns_lock = self._owns_lock, False
        if self._leader_lock is not None and self._leader_lock_pid == os.getpid():
            self._leader_lock.release()  # a follower's kept session as well
        if not owned:
            return
        if self._lock_fd is not None:
            fd, self._lock_fd = self._lock_fd, None
            try:
                os.close(fd)
            except OSError:
                pass
        if self._pid_file is not None:
            path, self._pid_file = self._pid_file, None
            try:
                os.unlink(path)
            except OSError:
                pass

    def start(self, app=None) -> None:
        """
        Start the scheduler thread

        Args:
            app: Flask app for application context (optional)
        """
        if self._running:
            logger.warning("Scheduler already running")
            return

        self._app = app
        self._running = True
        self._wake.clear()
        # The loop waits for the lock if another process holds it, then takes over
        self._thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._thread.name = "SchedulerService"
        self._thread.start()
        atexit.register(self._release_lock)
        logger.info(f"Scheduler started in pid {os.getpid()}")

    def relinquish(self) -> None:
        """Ask the loop to stop after the task it is running, then free the lock.

        Returns at once; the caller bounds the wait (scheduler_main: graceful_timeout).
        """
        self._running = False
        self._wake.set()
    
    def stop(self, timeout: int = 10) -> bool:
        """
        Stop the scheduler thread gracefully
        
        Args:
            timeout: Maximum seconds to wait for thread to stop
            
        Returns:
            True if stopped successfully, False if timeout
        """
        if not self._running:
            logger.debug("Scheduler not running")
            return True
        
        logger.info("Stopping scheduler...")
        self.relinquish()
        
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning(f"Scheduler thread did not stop within {timeout}s")
                return False

        self._release_lock()
        logger.info("Scheduler stopped")
        return True


def _store_state(state: dict) -> None:
    from models import SystemConfig, db
    row = SystemConfig.query.filter_by(key=STATE_KEY).first()
    if row is None:
        row = SystemConfig(key=STATE_KEY, encrypted=False,
                           description='Scheduled tasks status published by the HA leader')
        db.session.add(row)
    row.value = json.dumps(state)
    db.session.commit()


def _delete_requests(ids) -> None:
    from models import SchedulerRequest, db
    SchedulerRequest.query.filter(SchedulerRequest.id.in_(ids)).delete(synchronize_session=False)
    db.session.commit()


def _drop_abandoned_requests() -> None:
    from models import SchedulerRequest, db
    dropped = SchedulerRequest.query.filter(SchedulerRequest.taken_at.isnot(None)) \
        .delete(synchronize_session=False)
    db.session.commit()
    if dropped:
        logger.warning(f"Dropped {dropped} run-now request(s) a former leader took and never finished")


def _db_requests_pending() -> bool:
    from models import SchedulerRequest, db
    found = db.session.query(SchedulerRequest.id).filter(SchedulerRequest.taken_at.is_(None)).first()
    db.session.rollback()  # no transaction left open between polls
    return found is not None


def _rollback() -> None:
    try:
        from models import db
        db.session.rollback()
    except Exception:
        pass


class _HostLock:
    """SingletonLock on this host: the scheduler's flock, or its pid file without flock."""

    def __init__(self, scheduler: SchedulerService):
        self._scheduler = scheduler

    def acquire(self) -> bool:
        return self._scheduler._acquire_singleton_lock()

    def still_held(self) -> bool:
        return self._scheduler._owns_lock  # the kernel keeps an flock for as long as the fd

    def release(self) -> None:
        self._scheduler._release_lock()


# Global scheduler instance
_scheduler: Optional[SchedulerService] = None


def get_scheduler() -> SchedulerService:
    """Get or create global scheduler instance"""
    global _scheduler
    if _scheduler is None:
        _scheduler = SchedulerService(wake_interval=WAKE_INTERVAL_SECONDS)
    return _scheduler


def init_scheduler(app=None, wake_interval: int = WAKE_INTERVAL_SECONDS, autostart: bool = True) -> SchedulerService:
    """
    Initialize and start the scheduler
    
    Args:
        app: Flask app instance
        wake_interval: Wake interval in seconds (default 60s, must be > 0)
        autostart: Whether to start the scheduler immediately (default True)
        
    Returns:
        SchedulerService instance
    """
    global _scheduler
    
    if wake_interval <= 0:
        raise ValueError("wake_interval must be > 0")
    
    _scheduler = SchedulerService(wake_interval=wake_interval)
    
    if autostart:
        _scheduler.start(app=app)
    elif app:
        # If not autostarting but app provided, store it for later start()
        _scheduler._app = app
    
    return _scheduler


def _read_state() -> dict:
    try:
        with open(_data_path(STATE_FILE)) as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def is_leader():
    """Whether this node's scheduler loop is live: True/False, None when unknown.

    HA: ``_owns_lock`` where the loop runs, else this node's row in cluster_nodes.
    Single node: under gunicorn the loop lives in another process, so its fresh state file is the evidence.
    """
    if _scheduler is None:
        return None
    from utils.ha import ha_enabled
    if ha_enabled() and getattr(_scheduler, '_running', False):
        # HA: the loop's own process knows; a fresh state may come from another node's leader
        return bool(_scheduler._owns_lock)
    if ha_enabled():
        # HA: the scheduler process of this node says in cluster_nodes whether it holds the lock
        from services.scheduler_leader import node_is_leader
        return node_is_leader(_scheduler.node_id, _scheduler.wake_interval)
    if _scheduler._delegated():
        return not _scheduler.state_is_stale()
    return bool(_scheduler._owns_lock)


def start_scheduler(app) -> bool:
    """Start the loop in this process, unless the scheduler process runs it.

    Under gunicorn the loop runs in a process of its own (scheduler_main): a task
    there blocks no request, and no fork happens while it holds a connection.
    """
    if supervised():
        return False
    if app is not None and app.config.get('TESTING'):
        return False  # tests share one SQLite connection: a loop would race requests
    get_scheduler().start(app=app)
    return True
