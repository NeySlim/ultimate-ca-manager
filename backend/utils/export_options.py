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



# Kinds of option an export route declares (read_export_options)
FORMAT, BOOL, PASSWORD, TEXT = 'format', 'bool', 'password', 'text'
# Never in a URL: a password, and the PKCS#12 profile that only goes with one
_POST_ONLY = frozenset({'password', 'legacy'})
_NAME_SHOWN = 64


def _request_has_body(request) -> bool:
    """Whether the request carries a body, a chunked one included."""
    return bool(request.get_data(cache=True) or request.form or request.files)


def _shown(name) -> str:
    return str(name)[:_NAME_SHOWN]


class _RepeatedName(ValueError):
    def __init__(self, name):
        super().__init__(name)
        self.name = name


def _unique_pairs(pairs):
    """object_pairs_hook: a name given twice in one object is refused, at any depth."""
    seen = {}
    for name, value in pairs:
        if name in seen:
            raise _RepeatedName(name)
        seen[name] = value
    return seen


def _json_object(request):
    """``(object, None)`` or ``(None, message)`` for the raw JSON body of a POST.

    Read from the request stream, which MAX_CONTENT_LENGTH bounds (413 past it).
    """
    if not request.is_json:
        return None, None
    raw = request.get_data(cache=True)
    if not raw:
        return None, None
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        return None, 'The JSON body must be encoded in UTF-8'
    try:
        data = json.loads(text, object_pairs_hook=_unique_pairs)
    except _RepeatedName as exc:
        return None, f'{_shown(exc.name) or "An empty name"} is given more than once'
    except ValueError:
        return None, 'The body is not valid JSON'
    return data, None


def _option_value(name, kind, value, from_query, formats):
    """``(value, None)`` or ``(None, message)`` for one declared option."""
    if kind == BOOL:
        if from_query:
            normalized = value.lower()
            if normalized in ('true', 'false'):
                return normalized == 'true', None
            return None, f'{name} must be true or false'
        if isinstance(value, bool):
            return value, None
        return None, f'{name} must be a boolean'
    if kind == PASSWORD:
        if value is None or isinstance(value, str):
            return value, None
        return None, f'{name} must be a string'
    if not isinstance(value, str):
        return None, f'{name} must be a string'
    if kind == FORMAT:
        value = value.lower()
        if not value:
            return None, f'format is empty: it must be one of: {", ".join(formats)}'
        if value not in formats:
            return None, (f'Unsupported format {value[:_NAME_SHOWN]}: '
                          f'format must be one of: {", ".join(formats)}')
    return value, None


def read_export_options(options, formats=(), log_name='export'):
    """Read the options of an export that may return a private key.

    ``options`` maps each name the route reads to its kind. A GET takes them
    from the query string and carries no body; a POST from a JSON object body
    and nothing in the query string. Any other name, place or type answers 400.
    Returns ``(options read, None)`` or ``(None, 400 response)``.
    """
    from flask import request
    from utils.response import error_response

    if 'password' in request.args:
        logger.warning('Rejected %s export with a password in the query string (%s)',
                       log_name, request.path)
        return None, error_response(
            'Password must be sent in a POST JSON body, not the query string', 400)
    if request.method == 'POST':
        if request.args:
            return None, error_response(
                'A POST export takes its options in its JSON body, not the query string '
                f'({", ".join(sorted(_shown(n) for n in request.args))})', 400)
        data, message = _json_object(request)
        if message:
            return None, error_response(message, 400)
        if not isinstance(data, dict):
            return None, error_response(
                'A POST export takes a JSON body holding an object (Content-Type: application/json)', 400)
        source, from_query = data, False
    else:
        if _request_has_body(request):
            return None, error_response(
                'A GET export carries no body: send its options in the query string, '
                'or POST them in a JSON body', 400)
        source, from_query = request.args, True

    read = {}
    for name in source:
        kind = options.get(name)
        if kind is None:
            if not name:
                return None, error_response('An export option has an empty name', 400)
            return None, error_response(f'Unknown export option: {_shown(name)}', 400)
        if from_query and name in _POST_ONLY:
            return None, error_response(f'{name} is read from a POST JSON body only', 400)
        if from_query and len(source.getlist(name)) > 1:
            return None, error_response(f'{name} is given more than once', 400)
        value, message = _option_value(name, kind, source[name], from_query, formats)
        if message:
            return None, error_response(message, 400)
        read[name] = value
    return read, None
