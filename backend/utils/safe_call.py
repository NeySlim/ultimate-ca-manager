"""
safe_call — call a function while suppressing exceptions.

Intended for non-blocking side effects (audit logging, cache invalidation,
webhook notifications) where a failure must not abort the main request flow.
"""

import logging

_logger = logging.getLogger(__name__)


def safe_call(fn, *args, log_errors=True, **kwargs):
    """
    Call *fn* with the given arguments, suppressing any raised exception.

    Returns the function's return value on success, or ``None`` on failure.

    :param fn:         Callable to invoke.
    :param log_errors: When ``True`` (default), log suppressed exceptions at
                       DEBUG level so they remain visible in verbose logs
                       without disrupting callers.

    Usage::

        # Audit log must not abort a delete operation
        safe_call(AuditService.log_action, 'delete', 'certificate', cert_id)

        # Cache invalidation — best-effort only
        safe_call(cache.delete, cache_key)
    """
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        if log_errors:
            name = fn.__name__ if hasattr(fn, '__name__') else repr(fn)
            _logger.debug("safe_call suppressed error in %s: %s", name, e)
        return None
