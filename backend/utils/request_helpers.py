"""
Request validation decorators.
"""

import functools
import logging
from flask import request, g

from utils.response import error_response

logger = logging.getLogger(__name__)


def require_json_body(fn):
    """
    Decorator that ensures the request has a valid JSON body.

    Sets g.json_data with the parsed body. Returns HTTP 400 if
    Content-Type is not application/json or body cannot be parsed.

    Usage:
        @bp.route('/things', methods=['POST'])
        @require_auth(['write:things'])
        @require_json_body
        def create_thing():
            data = g.json_data
            ...
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        data = request.get_json(silent=True)
        if data is None:
            return error_response('Request body must be valid JSON', 400)
        g.json_data = data
        return fn(*args, **kwargs)
    return wrapper


def safe_call(fn, *args, **kwargs):
    """
    Call fn(*args, **kwargs) silently returning None on any Exception.

    Use for best-effort non-critical operations where failure should not
    propagate (e.g. cleanup, optional cache writes, resource release).
    Logs the exception at DEBUG level so it remains discoverable.

    Usage:
        safe_call(self._socket.close)
        safe_call(os.unlink, tmp_path)
        result = safe_call(parse_optional_field, raw)  # None on failure

    NOT appropriate for:
        - DB commits (use commit_or_rollback)
        - API responses (surface the error to the caller)
        - Mutations where partial failure corrupts state
    """
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        logger.debug("safe_call(%s) suppressed: %s", getattr(fn, '__name__', fn), e)
        return None
