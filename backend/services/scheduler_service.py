"""
Scheduler Service - Background Task Scheduling
Uses standard Python threading and time modules (no external dependencies like APScheduler)
Safe for Docker, systemd, and development environments
"""
import threading
import time
import logging
from datetime import datetime
from typing import Dict, Callable, Optional, Any
from threading import Lock

logger = logging.getLogger(__name__)


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
    
    def should_run(self) -> bool:
        """Check if task should run based on interval"""
        if not self.enabled:
            return False
        if self.last_run is None:
            return True
        elapsed = (datetime.utcnow() - self.last_run).total_seconds()
        return elapsed >= self.interval
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "name": self.name,
            "description": self.description,
            "interval": self.interval,
            "enabled": self.enabled,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "run_count": self.run_count,
            "last_error": self.last_error,
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
                    task.func()
            else:
                task.func()
                
            duration_ms = (time.time() - start_time) * 1000
            task.last_duration_ms = duration_ms
            task.last_error = None
            task.run_count += 1
            task.last_run = datetime.utcnow()
            task.next_run = datetime.utcnow() + __import__('datetime').timedelta(seconds=task.interval)
            logger.info(
                f"Task '{task.name}' completed successfully "
                f"(duration: {duration_ms:.1f}ms, runs: {task.run_count})"
            )
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            task.last_duration_ms = duration_ms
            error_msg = f"{type(e).__name__}: {str(e)}"
            task.last_error = error_msg
            task.last_run = datetime.utcnow()
            logger.error(
                f"Task '{task.name}' failed: {error_msg} (duration: {duration_ms:.1f}ms)",
                exc_info=True
            )
    
    def _scheduler_loop(self) -> None:
        """Main scheduler loop - runs in background thread"""
        logger.info("Scheduler thread started")
        
        while self._running:
            try:
                # Make a snapshot of tasks to avoid holding lock during execution
                with self.tasks_lock:
                    tasks_to_run = [
                        task for task in self.tasks.values()
                        if task.should_run()
                    ]
                
                # Execute tasks outside of lock
                for task in tasks_to_run:
                    try:
                        self._run_task(task)
                    except Exception as e:
                        logger.error(
                            f"Unexpected error running task '{task.name}': {e}",
                            exc_info=True
                        )
                
                # Sleep for wake_interval before checking again
                time.sleep(self.wake_interval)
            
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}", exc_info=True)
                time.sleep(self.wake_interval)
    
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
        self._thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._thread.name = "SchedulerService"
        self._thread.start()
        logger.info("Scheduler started")
    
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
        self._running = False
        
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning(f"Scheduler thread did not stop within {timeout}s")
                return False
        
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


def init_scheduler(app=None, wake_interval: int = 60) -> SchedulerService:
    """
    Initialize and start the scheduler
    
    Args:
        app: Flask app instance
        wake_interval: Wake interval in seconds (default 60s, must be > 0)
        
    Returns:
        SchedulerService instance
    """
    global _scheduler
    
    if wake_interval <= 0:
        raise ValueError("wake_interval must be > 0")
    
    _scheduler = SchedulerService(wake_interval=wake_interval)
    _scheduler.start(app=app)
    
    return _scheduler
