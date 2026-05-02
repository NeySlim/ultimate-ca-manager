"""
Request decorators for UCM API handlers.
"""

from functools import wraps
from flask import request, g
from utils.response import error_response


def require_json_body(f):
    """
    Decorator that returns 400 if the request body is missing or not valid JSON.

    On success, stores the parsed JSON in ``g.json_data`` for the handler to use.

    Usage::

        @bp.route('/api/v2/things', methods=['POST'])
        @require_auth(['write:things'])
        @require_json_body
        def create_thing():
            data = g.json_data
            ...
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not request.is_json or request.json is None:
            return error_response('Request body must be valid JSON', 400)
        g.json_data = request.json
        return f(*args, **kwargs)
    return decorated
