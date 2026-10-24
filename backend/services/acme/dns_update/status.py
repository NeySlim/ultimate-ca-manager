"""Port, bind host and run state of the DNS UPDATE listener.

The port comes from the ``UCM_DNS_UPDATE_PORT`` environment variable first,
then from the ``acme.proxy.dns_update_port`` setting. 0 means disabled.
"""
import logging
import os

logger = logging.getLogger(__name__)

PORT_CONFIG_KEY = 'acme.proxy.dns_update_port'
PORT_ENV = 'UCM_DNS_UPDATE_PORT'
HOST_ENV = 'UCM_DNS_UPDATE_HOST'

_listening = False
_listening_port = 0


def get_dns_update_port_env():
    """Env value (stripped), or None when the variable is unset, empty or blank."""
    value = os.getenv(PORT_ENV)
    if value is None:
        return None
    value = value.strip()
    return value or None


def get_stored_dns_update_port() -> int:
    """Port from the DB setting. 0 when missing, invalid or out of range."""
    try:
        from models import SystemConfig
        cfg = SystemConfig.query.filter_by(key=PORT_CONFIG_KEY).first()
        if cfg and cfg.value:
            port = int(cfg.value)
            return port if 0 <= port <= 65535 else 0
    except Exception:
        pass
    return 0


def get_dns_update_port() -> int:
    """Resolve the listener port from env var or DB setting. 0 = disabled."""
    env_val = get_dns_update_port_env()
    if env_val is not None:
        try:
            port = int(env_val)
        except (ValueError, TypeError):
            logger.warning("Invalid %s env var: %s", PORT_ENV, env_val)
            return 0
        if not 0 <= port <= 65535:
            logger.warning("%s=%s is out of range 0..65535, listener disabled", PORT_ENV, env_val)
            return 0
        if 0 < port < 1024:
            logger.warning(
                "%s=%d is a privileged port: the process needs CAP_NET_BIND_SERVICE "
                "(the API and the Docker entrypoint refuse it)", PORT_ENV, port)
        return port
    return get_stored_dns_update_port()


def get_dns_update_host() -> str:
    """Bind host: ``UCM_DNS_UPDATE_HOST``, else the HTTP protocol server host."""
    host = (os.getenv(HOST_ENV) or '').strip()
    if host:
        return host
    from listen_address import get_bind_host
    return get_bind_host()


def set_listening(value: bool, port: int = 0) -> None:
    global _listening, _listening_port
    _listening = bool(value)
    _listening_port = int(port) if value else 0


def listening_port() -> int:
    """Port the listener is bound to now, 0 when it is not listening."""
    return _listening_port if _listening else 0


def is_listening() -> bool:
    return _listening
