"""Strict parsers for certificate-export options."""
import json
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


_SECRET_NAME_PARTS = ('password', 'passphrase')
_QUERY_MESSAGE = 'Password must be sent via POST body (JSON), not query string'
_BODY_MESSAGE = 'A request body is accepted only from a POST, as a JSON object (Content-Type: application/json)'


class _RepeatedName(ValueError):
    pass


def _unique_pairs(pairs):
    """object_pairs_hook: a name given twice in one object is refused, at any depth."""
    seen = {}
    for name, value in pairs:
        if name in seen:
            raise _RepeatedName(name)
        seen[name] = value
    return seen


def _looks_like_a_password(name):
    lowered = str(name).lower()
    return any(part in lowered for part in _SECRET_NAME_PARTS)


def _nested_secret_name(value):
    """Whether any object below ``value`` has a name that looks like a password (no recursion)."""
    todo = [value]
    while todo:
        item = todo.pop()
        if isinstance(item, dict):
            if any(_looks_like_a_password(name) for name in item):
                return True
            todo.extend(item.values())
        elif isinstance(item, list):
            todo.extend(item)
    return False


def check_export_request(query_message=_QUERY_MESSAGE):
    """Return a 400 response when the request is not shaped like an export call, else None.

    A password sent where the route does not read it would otherwise be
    ignored and the key returned in clear. Messages never repeat a request value.
    """
    from flask import request
    from utils.response import error_response

    if any(_looks_like_a_password(name) for name in request.args):
        logger.warning('Rejected export with a password in the query string (%s)', request.path)
        return error_response(query_message, 400)
    raw = request.get_data(cache=True)
    if not raw:
        return None
    if request.method != 'POST' or not request.is_json:
        return error_response(_BODY_MESSAGE, 400)
    try:
        text = raw.decode('utf-8-sig')      # a byte order mark is ignored (RFC 8259, 8.1)
    except UnicodeDecodeError:
        return error_response('The JSON body must be encoded in UTF-8', 400)
    try:
        data = json.loads(text, object_pairs_hook=_unique_pairs)
    except _RepeatedName:
        return error_response('A name is given more than once in the JSON body', 400)
    except (ValueError, RecursionError):
        return error_response('The body is not valid JSON', 400)
    if not isinstance(data, dict):
        return error_response(_BODY_MESSAGE, 400)
    password = data.get('password')
    if password is not None and not isinstance(password, str):
        return error_response('password must be a string', 400)
    if any(_looks_like_a_password(name) for name in data if name != 'password') or any(
            _nested_secret_name(value) for value in data.values()):
        return error_response('A password is read only from the "password" name of the JSON body', 400)
    return None
