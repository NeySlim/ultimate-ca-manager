"""HA preview helpers: startup validation and the guard for host-local operations."""
import logging
import os
from functools import wraps

logger = logging.getLogger(__name__)


def ha_enabled():
    from config.settings import Config
    return bool(Config.HA_MODE)


def validate_ha_config(config=None):
    """Exit at startup when UCM_HA=1 meets a configuration that cannot span nodes."""
    from config.settings import Config, redis_url
    cfg = config or Config
    if not cfg.HA_MODE:
        return
    if cfg.DATABASE_TYPE != 'postgresql':
        raise SystemExit("UCM_HA=1 requires a PostgreSQL DATABASE_URL (SQLite is single-node)")
    if not os.getenv('SECRET_KEY'):
        raise SystemExit("UCM_HA=1 requires SECRET_KEY set in the environment, identical on every node")
    from security.encryption import MASTER_KEY_PATH
    if MASTER_KEY_PATH.exists():
        # The runtime reads master.key before KEY_ENCRYPTION_KEY. Identity between nodes:
        # the KEK fingerprint check at start (refuse_kek_mismatch_with_peers)
        if os.getenv('KEY_ENCRYPTION_KEY'):
            logger.warning("HA: the local master.key overrides KEY_ENCRYPTION_KEY on this node")
    elif not os.getenv('KEY_ENCRYPTION_KEY'):
        raise SystemExit("UCM_HA=1 requires KEY_ENCRYPTION_KEY set in the environment, identical on every node")
    if not redis_url():
        logger.warning("HA: filesystem sessions are not shared between nodes, see the sessions lot")


def ha_refusal(reason):
    """409 body for an operation that only writes to the local host."""
    from flask import jsonify
    from utils.response import build_problem, PROBLEM_CONTENT_TYPE
    body = build_problem(reason, 409)
    body['code'] = 'ha_mode'
    resp = jsonify(body)
    resp.mimetype = PROBLEM_CONTENT_TYPE
    return resp, 409


class HaRestricted(Exception):
    """Raised by a service for an operation HA mode refuses; the app answers 409 ha_mode."""


SOFTHSM_LOCAL = ("Not available in HA mode: a SoftHSM token lives on one node only, "
                 "use a network HSM or a KMS provider")


def refuse_softhsm_in_ha():
    if ha_enabled():
        raise HaRestricted(SOFTHSM_LOCAL)


LOCAL_ONLY = "Not available in HA mode: this operation only changes the local host"


def reject_in_ha(reason=LOCAL_ONLY):
    """Route decorator: answer 409 ha_mode when the node runs with UCM_HA=1."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if ha_enabled():
                return ha_refusal(reason)
            return fn(*args, **kwargs)
        return wrapper
    return deco
