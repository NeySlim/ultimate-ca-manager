"""The gunicorn worker timeout, from UCM_WORKER_TIMEOUT (seconds).

Read by gunicorn_config.py for every deployment; a value gunicorn would take but nobody
meant (0 disables the timeout, a typo) stops the start with a message instead.
"""
import os

ENV = 'UCM_WORKER_TIMEOUT'
DEFAULT = 120
MINIMUM = 30
MAXIMUM = 3600


def worker_timeout(environ=None):
    raw = (os.environ if environ is None else environ).get(ENV, '').strip()
    if not raw:
        return DEFAULT
    try:
        value = int(raw)
    except ValueError:
        value = None
    if value is None or not MINIMUM <= value <= MAXIMUM:
        raise SystemExit(f"{ENV} must be a whole number of seconds from {MINIMUM} to {MAXIMUM} "
                         f"(default {DEFAULT}); UCM does not start with {raw!r}")
    return value
