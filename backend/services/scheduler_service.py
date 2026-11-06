"""
Scheduler Service - Background Task Scheduling
Uses standard Python threading and time modules (no external dependencies like APScheduler)
Safe for Docker, systemd, and development environments
"""
import threading
import time
import os
import atexit
import fcntl
import logging
from datetime import datetime
from typing import Dict, Callable, Optional, Any
from threading import Lock
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

# Set by gunicorn_config: the master only registers tasks, a worker runs the loop
IN_WORKER_ENV = 'UCM_SCHEDULER_IN_WORKER'
# How often a process waiting for the scheduler lock tries again
LOCK_RETRY_SECONDS = 5


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
    
    def __init__(self, wake_interval: int = 60):
        """
        Initialize scheduler
        
        Args:
            wake_interval: How often scheduler wakes up to check tasks (in seconds)
        """
        self.wake_interval = wake_interval
        self.tasks: Dict[str, ScheduledTask] = {}
        self.tasks_lock = Lock()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._app = None
        self._owns_lock = False
        self._owner_pid = None
        self._lock_path = None
        self._lock_fd = None
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
    
    def run_task_now(self, name: str) -> Optional[Dict[str, Any]]:
        """Trigger immediate execution of a task, returns task status after run"""
        with self.tasks_lock:
            task = self.tasks.get(name)
        if not task:
            return None
        self._run_task(task)
        with self.tasks_lock:
            return task.to_dict()
    
    def get_task_status(self, name: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific task"""
        with self.tasks_lock:
            if name in self.tasks:
                return self.tasks[name].to_dict()
            return None
    
    def get_all_tasks_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all registered tasks"""
        with self.tasks_lock:
            return {
                name: task.to_dict()
                for name, task in self.tasks.items()
            }
    
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
                if not self._owns_lock:
                    if not self._acquire_singleton_lock():
                        self._wake.wait(LOCK_RETRY_SECONDS)
                        continue
                    logger.info(f"Scheduler lock acquired: pid {os.getpid()} runs the scheduled tasks")
                try:
                    with self.tasks_lock:
                        tasks_to_run = [
                            task for task in self.tasks.values()
                            if task.should_run()
                        ]

                    # Execute tasks outside of lock
                    for task in tasks_to_run:
                        if not self._running:
                            break
                        try:
                            self._run_task(task)
                        except Exception as e:
                            logger.error(
                                f"Unexpected error running task '{task.name}': {e}",
                                exc_info=True
                            )
                except Exception as e:
                    logger.error(f"Error in scheduler loop: {e}", exc_info=True)
                self._wake.wait(self.wake_interval)
        finally:
            # The next process waiting for the lock takes over from here
            self._release_lock()

    def _acquire_singleton_lock(self) -> bool:
        """Take the host-wide scheduler lock, so only ONE process runs the loop.

        An flock held for as long as the loop runs: the kernel frees it when its
        holder dies, so a killed worker hands over at once and a stale pid never blocks.
        """
        try:
            from config.settings import DATA_DIR
            self._lock_path = os.path.join(str(DATA_DIR), 'scheduler.lock')
        except Exception:
            self._lock_path = '/tmp/ucm-scheduler.lock'
        try:
            fd = os.open(self._lock_path, os.O_CREAT | os.O_RDWR, 0o644)
        except OSError as e:
            logger.warning(f"Scheduler lock {self._lock_path} unavailable: {e}")
            return False
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            return False
        try:
            os.ftruncate(fd, 0)
            os.write(fd, str(os.getpid()).encode())  # who holds it, for an operator
        except OSError:
            pass
        self._lock_fd = fd
        self._owns_lock = True
        self._owner_pid = os.getpid()
        return True

    def _release_lock(self) -> None:
        # A forked copy shares the holder's open file: closing it there would not free
        # the lock, and must not touch the holder's state either
        if self._owns_lock and self._lock_fd is not None and self._owner_pid == os.getpid():
            fd, self._lock_fd = self._lock_fd, None
            self._owns_lock = False
            try:
                os.close(fd)
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
        """Stop after the running task and free the lock, without waiting."""
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


# Global scheduler instance
_scheduler: Optional[SchedulerService] = None


def get_scheduler() -> SchedulerService:
    """Get or create global scheduler instance"""
    global _scheduler
    if _scheduler is None:
        _scheduler = SchedulerService(wake_interval=60)
    return _scheduler


def init_scheduler(app=None, wake_interval: int = 60, autostart: bool = True) -> SchedulerService:
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


def start_scheduler(app, in_worker: bool = False) -> bool:
    """Start the loop in this process, unless gunicorn runs it in a worker.

    Under gunicorn the master forks workers at any time (timeout, HUP): a task
    of its own holding a database connection at that moment would share it.
    """
    if os.environ.get(IN_WORKER_ENV) == '1' and not in_worker:
        return False
    if app is not None and app.config.get('TESTING'):
        return False  # tests share one SQLite connection: a loop would race requests
    get_scheduler().start(app=app)
    return True
