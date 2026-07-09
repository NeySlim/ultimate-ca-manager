"""
Runtime ACME/DNS debug logging toggle (GUI: acme.client.debug_logging).

When enabled, diagnostic messages that normally log at DEBUG are emitted at INFO
so they appear in default production log levels without changing LOG_LEVEL globally.

The flag is memoized on ``flask.g`` for the current app context so hot DNS poll
loops do not issue a SystemConfig query on every log line.
"""
import logging

from flask import g, has_app_context

from models import SystemConfig

CONFIG_KEY = 'acme.client.debug_logging'
_G_ATTR = '_acme_debug_logging'


def clear_acme_debug_cache() -> None:
    """Drop the memoized flag (call after PATCH of debug_logging)."""
    if has_app_context():
        g.pop(_G_ATTR, None)


def acme_debug_logging_enabled() -> bool:
    """True when the operator enabled ACME debug logging in client settings."""
    if not has_app_context():
        return False
    cached = g.get(_G_ATTR)
    if cached is not None:
        return cached
    cfg = SystemConfig.query.filter_by(key=CONFIG_KEY).first()
    if not cfg or cfg.value is None:
        enabled = False
    else:
        enabled = str(cfg.value).strip().lower() in ('true', '1', 'yes', 'on')
    setattr(g, _G_ATTR, enabled)
    return enabled


def acme_log(logger: logging.Logger, msg: str, *args, **kwargs) -> None:
    """Log at INFO when GUI debug is on, otherwise DEBUG."""
    if acme_debug_logging_enabled():
        logger.info(msg, *args, **kwargs)
    else:
        logger.debug(msg, *args, **kwargs)
