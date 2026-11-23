"""The TLS listener of this node: the certificate it serves, and its reload by the gunicorn master.

SIGHUP to the master re-reads gunicorn_config.py (HTTPS pair, mTLS trust, WSTEP cap) and replaces
the workers, whose ssl_context hook loads the files again; the master and its socket stay (#452).
"""
import logging
import os
import signal
import time
from pathlib import Path

logger = logging.getLogger(__name__)

RELOADING = 'reloading'    # the master was sent SIGHUP
RESTARTING = 'restarting'  # DEB/RPM without a gunicorn master to signal: the watcher's restart
ROLLING = 'rolling'        # HA: every node restarts in turn and writes the files from the database
FAILED = 'failed'

# Written beside the SIGHUP: the master then keeps the scheduler process, which holds no TLS state
RELOAD_MARKER = '.listener_reload'
MARKER_FRESH_SECONDS = 120

_state = {'master': None, 'served': None}


def note_master(pid):
    """A web worker records the arbiter that forked it (gunicorn's worker.ppid)."""
    _state['master'] = int(pid) if pid else None


def gunicorn_master():
    """The pid of the gunicorn master that started this process, while it is still its parent."""
    pid = _state['master']
    if pid is None:
        from scheduler_main import MASTER_ENV  # the scheduler process: named by its supervisor
        raw = os.environ.get(MASTER_ENV, '')
        pid = int(raw) if raw.isdigit() else None
    # A master that died leaves its children to another parent: never signal a stale pid
    if not pid or pid != os.getppid():
        return None
    return pid


def _marker(data_dir=None) -> Path:
    if data_dir is None:
        from config import settings
        data_dir = settings.DATA_DIR
    return Path(data_dir) / RELOAD_MARKER


def request_reload():
    """``(True, message)`` once the master was sent SIGHUP, else ``(False, reason)``."""
    master = gunicorn_master()
    if master is None:
        return False, "no gunicorn master is the parent of this process"
    marker = _marker()
    try:
        marker.write_text(str(os.getpid()), encoding='utf-8')
    except OSError as e:
        logger.warning("TLS listener reload: the scheduler process restarts with it (%s)", e)
    try:
        os.kill(master, signal.SIGHUP)
    except OSError as e:
        marker.unlink(missing_ok=True)
        return False, f"the gunicorn master (pid {master}) could not be signalled: {e}"
    logger.info("TLS listener reload asked of the gunicorn master (pid %s)", master)
    return True, "The TLS listener reloads: new connections get the new configuration in a few seconds"


def take_reload_request(data_dir) -> bool:
    """Master, on SIGHUP: whether the product asked it for the TLS listener (a fresh marker, consumed)."""
    marker = _marker(data_dir)
    try:
        age = time.time() - marker.stat().st_mtime
    except OSError:
        return False
    try:
        marker.unlink()
    except OSError:
        pass
    return age <= MARKER_FRESH_SECONDS


def reload_or_restart():
    """Outside HA: ``(outcome, message)`` of serving a new listener configuration on this node;
    the message of FAILED is the reason, logged as an error.

    SIGHUP to the master, in a container as under systemd (whose ExecReload is that signal);
    a native install without a master to signal falls back on the watcher's restart.
    """
    reloaded, message = request_reload()
    if reloaded:
        return RELOADING, message
    from config import settings
    if not settings.is_docker():
        from utils.service_manager import restart_service
        restarted, detail = restart_service()
        if restarted:
            return RESTARTING, detail
        message = f"{message}; {detail}"
    logger.error("The TLS listener was not reloaded: %s", message)
    return FAILED, message


def serve_listener_change():
    """``(outcome, message)``: HA keeps its rolling restart, otherwise reload_or_restart()."""
    from utils.ha import ha_enabled
    if ha_enabled():
        from utils.service_manager import restart_service
        started, message = restart_service()
        if not started:
            logger.error("TLS listener: the rolling restart was not requested: %s", message)
        return (ROLLING if started else FAILED), message
    return reload_or_restart()


def _leaf_sha256(pem):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    try:
        return x509.load_pem_x509_certificate(pem).fingerprint(hashes.SHA256()).hex()
    except ValueError:
        return None


def pin_served_certificate(path, build, attempts=3):
    """Build the TLS context with *build* (it loads *path*) and record the leaf it serves: the file
    read before and after must match, else what this worker serves is unknown."""
    def read():
        try:
            with open(path, 'rb') as handle:
                return handle.read()
        except OSError:
            return None
    for _ in range(attempts):
        before = read()
        ctx = build()
        if before is not None and before == read():
            _state['served'] = _leaf_sha256(before)
            return ctx
    _state['served'] = None
    return ctx


def served_fingerprint():
    """SHA-256 hex of the certificate this worker's listener presents; None outside a web worker."""
    return _state['served']
