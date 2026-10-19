"""A saved secret never follows a changed target.

A configuration update keeps the stored secret when the field comes back
blank or masked. Changing where that secret is sent (host, URL, port, TLS,
account) in the same request would hand the saved secret to the new target,
so such an update must carry the secret again. Checked before any mutation.
"""
from utils.response import error_response

SECRET_TARGET_MESSAGE = 'Re-enter the secret to change the target'
MASKS = ('***', '********')
_MISSING = object()


def _norm(value):
    if isinstance(value, str):
        value = value.strip()
        if value == '':
            return None
        if value.lower() in ('true', 'false'):
            return value.lower() == 'true'
        if value.isdigit():
            return int(value)
    if isinstance(value, (list, tuple)):
        return tuple(_norm(v) for v in value)
    return value


def keeps_saved_secret(data, key, stored, *, blank_clears=False):
    """True when ``data`` leaves the saved secret ``stored`` in place."""
    if not stored:
        return False
    value = data.get(key, _MISSING) if isinstance(data, dict) else _MISSING
    if value is _MISSING:
        return True
    if value is None or (isinstance(value, str) and not value.strip()):
        return not blank_clears
    return isinstance(value, str) and value.strip() in MASKS


def changed_targets(current, data):
    """Keys of ``current`` that ``data`` sets to another value."""
    return sorted(key for key, value in current.items()
                  if key in data and _norm(data[key]) != _norm(value))


def retarget_error(current, data, keeping_secret):
    """400 when ``data`` keeps a saved secret but changes where it goes."""
    if not keeping_secret:
        return None
    changed = changed_targets(current, data)
    if not changed:
        return None
    return error_response(SECRET_TARGET_MESSAGE, 400,
                          details={'code': 'secret_required_for_target', 'fields': changed})
