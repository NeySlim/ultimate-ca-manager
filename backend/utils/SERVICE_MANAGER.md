# UCM Service Management

## Overview

Centralized service restart/reload functionality for UCM. All service-related operations should use this module instead of calling systemctl directly.

## Location

`/opt/ucm/backend/utils/service_manager.py`

## Usage

### Simple Import

```python
from utils import restart_service

# Restart the service
success, message = restart_service()
if success:
    return jsonify({'message': message}), 200
else:
    return jsonify({'error': message}), 500
```

### All Available Functions

```python
from utils import (
    restart_service,      # Restart UCM service
    reload_service,       # Reload configuration (currently = restart)
    is_service_running,   # Check if service is running
    get_service_status,   # Get detailed status info
    schedule_restart,     # Schedule restart with delay
    cancel_scheduled_restart  # Cancel scheduled restart
)
```

### Using Aliases

```python
from utils import restart, reload, is_running, get_status

# Short aliases available
success, msg = restart()
running = is_running()
status = get_status()
```

## Functions

### restart_service()

Restart UCM service using signal file mechanism (no sudo required).

**Returns:** `Tuple[bool, str]` - (success, message)

**Example:**
```python
success, message = restart_service()
# success: True
# message: "✅ Service restart initiated. Please wait 5 seconds..."
```

### reload_service()

Reload service configuration. Currently implemented as full restart.

**Returns:** `Tuple[bool, str]` - (success, message)

### is_service_running()

Check if UCM service is currently running.

**Returns:** `bool` - True if running, False otherwise

**Example:**
```python
if is_service_running():
    print("Service is active")
```

### get_service_status()

Get detailed service status information.

**Returns:** `dict` with keys:
- `running` (bool): Is service running
- `status` (str): Service status (active/inactive/etc)
- `pid` (int): Process ID
- `memory` (str): Memory usage in MB
- `uptime` (str): Service uptime

**Example:**
```python
status = get_service_status()
print(f"Service PID: {status['pid']}")
print(f"Memory: {status['memory']}")
```

### schedule_restart(delay_seconds=1)

Schedule a service restart after a delay.

**Args:**
- `delay_seconds` (int): Seconds to wait before restarting

**Returns:** `Tuple[bool, str]` - (success, message)

**Example:**
```python
success, msg = schedule_restart(delay_seconds=5)
```

### cancel_scheduled_restart()

Cancel a previously scheduled restart.

**Returns:** `Tuple[bool, str]` - (success, message)

## How It Works

### Signal File Mechanism

1. Function creates `/opt/ucm/backend/data/.restart_requested`
2. Next HTTP request detects the file via middleware
3. Middleware initiates graceful shutdown (`os._exit(0)`)
4. Systemd detects shutdown and automatically restarts
5. New process loads with updated configuration

### Multi-Distribution Compatible

- **No sudo required** - uses file-based signaling
- **Systemd support** - automatic restart via `Restart=always`
- **SysV support** - fallback mechanisms
- **Docker support** - detects container environment

## Migration Guide

### Before (Old Code)

```python
# ❌ Don't do this anymore
import subprocess
subprocess.Popen(['systemctl', 'restart', 'ucm'])

# ❌ Or this
from config.settings import restart_ucm_service
success, message = restart_ucm_service()
```

### After (New Code)

```python
# ✅ Use this instead
from utils import restart_service
success, message = restart_service()
```

## Where to Use

Use `restart_service()` after:
- Applying HTTPS certificate changes
- Updating system configuration
- Modifying mTLS settings
- Changing SCEP/ACME configuration
- Any operation requiring service reload

## Examples in Code

### API Route Example

```python
@app.route('/api/config/update', methods=['POST'])
@admin_required
def update_config():
    # Update configuration
    config.save()
    
    # Restart to apply changes
    from utils import restart_service
    success, message = restart_service()
    
    return jsonify({
        'success': success,
        'message': message
    })
```

### UI Route Example

```python
@ui_bp.route('/api/ui/settings/apply', methods=['POST'])
@login_required
def apply_settings_ui():
    # Apply settings
    save_settings(request.form)
    
    # Restart service
    from utils import restart_service
    success, message = restart_service()
    
    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')
    
    return redirect('/settings')
```

## Testing

```python
# Test restart
from utils import restart_service
success, message = restart_service()
print(f"Success: {success}")
print(f"Message: {message}")

# Test status check
from utils import is_service_running, get_service_status
print(f"Running: {is_service_running()}")
print(f"Status: {get_service_status()}")
```

## Troubleshooting

### Service doesn't restart

1. Check signal file was created:
   ```bash
   ls -la /opt/ucm/backend/data/.restart_requested
   ```

2. Check systemd configuration:
   ```bash
   systemctl show ucm | grep Restart
   # Should show: Restart=always
   ```

3. Check service logs:
   ```bash
   journalctl -u ucm -n 50
   ```

### Permission errors

The signal file method doesn't require special permissions. If you get permission errors, check:

```bash
# Data directory should be writable by ucm user
ls -ld /opt/ucm/backend/data
# Should show: drwxr-xr-x ucm ucm
```

## Performance

- **Restart time:** ~3-5 seconds
- **Downtime:** ~2-3 seconds (graceful shutdown + startup)
- **No sudo overhead:** Direct process signaling
- **No authentication delays:** File-based mechanism

## Best Practices

1. **Always use the utils module** - Don't call systemctl directly
2. **Check return values** - Handle both success and failure cases
3. **Inform users** - Display the returned message to users
4. **Use appropriate delays** - Schedule restart if user needs time to save work
5. **Test in development** - Verify restart completes successfully

## See Also

- `/opt/ucm/backend/config/settings.py` - Original restart_ucm_service()
- `/opt/ucm/backend/app.py` - Restart signal middleware
- `/etc/systemd/system/ucm.service` - Service configuration
