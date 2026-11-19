"""Gunicorn access log that keeps secrets carried in a URL out of the file."""
import re
from urllib.parse import unquote_plus

from gunicorn.glogging import Logger

# Query parameters that carry a credential: password reset and OAuth/OIDC callbacks.
SECRET_PARAMS = ('token', 'code', 'state', 'access_token', 'id_token', 'refresh_token')

# Any parameter whose name holds one of these: a password refused in a URL still reaches the log
SECRET_NAME_PARTS = ('password', 'passphrase')

_PARAM = re.compile(r'([?&;])([^=&;#\s"]*)=([^&;#\s"]*)')


def _secret_name(raw):
    """Judged on the name the server decodes, so `pass%77ord` or `password[]` is a password."""
    name = unquote_plus(raw).lower()
    return name in SECRET_PARAMS or any(part in name for part in SECRET_NAME_PARTS)


def redact_url(value):
    """``value`` with the secret query values replaced; anything else unchanged."""
    if not isinstance(value, str) or '=' not in value:
        return value
    # A value is read again: "?a=1?token=x" hides a parameter behind a second "?"
    return _PARAM.sub(
        lambda m: f'{m[1]}{m[2]}=[REDACTED]' if _secret_name(m[2]) else f'{m[1]}{m[2]}={redact_url(m[3])}',
        value)


class RedactingLogger(Logger):
    """Every atom (request line, query string, Referer, environ) goes through redact_url()."""

    _QUERY_ATOMS = ('q', '{query_string}e')

    def atoms(self, resp, req, environ, request_time):
        atoms = super().atoms(resp, req, environ, request_time)
        for key, value in atoms.items():
            if not isinstance(value, str):
                continue
            if key in self._QUERY_ATOMS:
                atoms[key] = redact_url('?' + value)[1:]
            else:
                atoms[key] = redact_url(value)
        return atoms
