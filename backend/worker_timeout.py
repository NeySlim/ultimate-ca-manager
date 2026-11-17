"""The gunicorn worker timeout, from UCM_WORKER_TIMEOUT (seconds).

Read by gunicorn_config.py for every deployment; a value gunicorn would take but nobody
meant (0 disables the timeout, a typo) stops the start with a message and exit 78
(EX_CONFIG), which the systemd unit does not restart.
"""
import os
import sys

from startup_refusal import EXIT_CODE

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
        print(f"{ENV} must be a whole number of seconds from {MINIMUM} to {MAXIMUM} "
              f"(default {DEFAULT}); UCM does not start with {raw!r}", file=sys.stderr, flush=True)
        raise SystemExit(EXIT_CODE)
    return value
