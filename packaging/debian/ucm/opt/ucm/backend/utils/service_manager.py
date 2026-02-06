"""
UCM Service Management Utilities
Centralized service restart/reload functionality
"""
import subprocess
from pathlib import Path
from typing import Tuple


def restart_service() -> Tuple[bool, str]:
    """
    Restart UCM service using multi-distro compatible method.
    No sudo required - uses signal file mechanism.
    
    Returns:
        Tuple[bool, str]: (success, message)
    
    Examples:
        >>> success, message = restart_service()
        >>> if success:
        ...     print(f"Service restarting: {message}")
    """
    from config.settings import restart_ucm_service
    return restart_ucm_service()


def reload_service() -> Tuple[bool, str]:
    """
    Reload UCM service configuration without full restart.
    Currently implemented as full restart (Flask dev server limitation).
    
    Returns:
        Tuple[bool, str]: (success, message)
    """
    # For now, reload = restart since we use Flask dev server
    # In production with Gunicorn, this would send SIGHUP
    return restart_service()


def is_service_running() -> bool:
    """
    Check if UCM service is currently running.
    
    Returns:
        bool: True if service is running, False otherwise
    """
    try:
        result = subprocess.run(
            ['systemctl', 'is-active', 'ucm'],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.stdout.strip() == 'active'
    except (FileNotFoundError, subprocess.TimeoutExpired):
        # Fallback: check if process is running
        try:
            result = subprocess.run(
                ['pgrep', '-f', 'python.*app.py'],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except:
            return False


def get_service_status() -> dict:
    """
    Get detailed service status information.
    
    Returns:
        dict: Service status details (active, uptime, pid, etc.)
    """
    status = {
        'running': False,
        'status': 'unknown',
        'uptime': None,
        'pid': None,
        'memory': None
    }
    
    try:
        # Try systemctl status
        result = subprocess.run(
            ['systemctl', 'show', 'ucm', '--no-pager'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            lines = result.stdout.split('\n')
            for line in lines:
                if '=' in line:
                    key, value = line.split('=', 1)
                    if key == 'ActiveState':
                        status['status'] = value
                        status['running'] = (value == 'active')
                    elif key == 'MainPID':
                        status['pid'] = int(value) if value != '0' else None
                    elif key == 'MemoryCurrent':
                        try:
                            # Convert bytes to MB
                            status['memory'] = f"{int(value) / 1024 / 1024:.1f} MB"
                        except:
                            pass
    except (FileNotFoundError, subprocess.TimeoutExpired):
        # Fallback for non-systemd systems
        status['running'] = is_service_running()
        status['status'] = 'active' if status['running'] else 'inactive'
    
    return status


def schedule_restart(delay_seconds: int = 1) -> Tuple[bool, str]:
    """
    Schedule a service restart after a delay.
    Useful for applying changes that require restart.
    
    Args:
        delay_seconds: Seconds to wait before restarting (default: 1)
    
    Returns:
        Tuple[bool, str]: (success, message)
    """
    # Create restart signal file
    from config.settings import DATA_DIR
    
    try:
        restart_signal = DATA_DIR / '.restart_requested'
        restart_signal.write_text('restart')
        
        return True, f"✅ Service restart scheduled in {delay_seconds}s. Please reload the page after {delay_seconds + 3} seconds."
    except Exception as e:
        return False, f"Failed to schedule restart: {str(e)}"


def cancel_scheduled_restart() -> Tuple[bool, str]:
    """
    Cancel a previously scheduled restart.
    
    Returns:
        Tuple[bool, str]: (success, message)
    """
    from config.settings import DATA_DIR
    
    try:
        restart_signal = DATA_DIR / '.restart_requested'
        if restart_signal.exists():
            restart_signal.unlink()
            return True, "Scheduled restart cancelled"
        else:
            return True, "No restart was scheduled"
    except Exception as e:
        return False, f"Failed to cancel restart: {str(e)}"


# Convenience aliases
restart = restart_service
reload = reload_service
is_running = is_service_running
get_status = get_service_status
