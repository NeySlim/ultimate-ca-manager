"""
Runtime ACME/DNS debug logging toggle (GUI: acme.client.debug_logging).

When enabled, diagnostic messages that normally log at DEBUG are emitted at INFO
so they appear in default production log levels without changing LOG_LEVEL globally.
"""
import logging

from flask import has_app_context

from models import SystemConfig

CONFIG_KEY = 'acme.client.debug_logging'


def acme_debug_logging_enabled() -> bool:
    """True when the operator enabled ACME debug logging in client settings."""
    if not has_app_context():
        return False
    cfg = SystemConfig.query.filter_by(key=CONFIG_KEY).first()
    if not cfg or cfg.value is None:
        return False
    return str(cfg.value).strip().lower() in ('true', '1', 'yes', 'on')


def acme_log(logger: logging.Logger, msg: str, *args, **kwargs) -> None:
    """Log at INFO when GUI debug is on, otherwise DEBUG."""
    if acme_debug_logging_enabled():
        logger.info(msg, *args, **kwargs)
    else:
        logger.debug(msg, *args, **kwargs)
