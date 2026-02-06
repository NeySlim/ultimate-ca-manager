"""
UCM Utility Functions
"""
from .service_manager import (
    restart_service,
    reload_service,
    is_service_running,
    get_service_status,
    schedule_restart,
    cancel_scheduled_restart,
    # Aliases
    restart,
    reload,
    is_running,
    get_status
)

__all__ = [
    'restart_service',
    'reload_service',
    'is_service_running',
    'get_service_status',
    'schedule_restart',
    'cancel_scheduled_restart',
    'restart',
    'reload',
    'is_running',
    'get_status'
]
