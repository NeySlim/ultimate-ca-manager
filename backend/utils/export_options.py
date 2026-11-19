"""Strict parsers for certificate-export options."""
import logging

logger = logging.getLogger(__name__)


def json_boolean(data, name, default=False):
    """Return a JSON boolean without treating non-empty strings as true."""
    if name not in data:
        return default
    value = data[name]
    if not isinstance(value, bool):
        raise ValueError(f'{name} must be a boolean')
    return value


def query_boolean(args, name, default=False):
    """Parse an HTTP query boolean and reject ambiguous values."""
    value = args.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized == 'true':
        return True
    if normalized == 'false':
        return False
    raise ValueError(f'{name} must be true or false')


def export_body(log_name):
    """Return ``(data, refusal)`` for an export request.

    ``data`` is the JSON object of a POST, or None when the options are in the
    query string. A password is read from a JSON body only, so a body in any
    other form and a ``password`` in the URL are refused rather than ignored.
    """
    from flask import request
    from utils.response import error_response

    if 'password' in request.args:
        logger.warning('Rejected %s export with a password in the query string', log_name)
        return None, error_response(
            'Password must be sent in a POST JSON body, not the query string', 400)
    if request.method != 'POST':
        return None, None
    if request.is_json:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return None, error_response('The export JSON body must be an object', 400)
        return data, None
    if request.content_length or request.form or request.files or request.get_data(cache=True):
        return None, error_response(
            'Export options in a POST must be a JSON body (Content-Type: application/json)', 400)
    return None, None
