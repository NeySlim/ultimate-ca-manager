"""Gunicorn access log that keeps secrets carried in a URL out of the file."""
import re
from urllib.parse import unquote_plus

from gunicorn.glogging import Logger

# Query parameters that carry a credential: password reset and OAuth/OIDC callbacks.
SECRET_PARAMS = ('token', 'code', 'state', 'access_token', 'id_token', 'refresh_token')

# Any parameter whose name holds one of these: a password refused in a URL still reaches the log
SECRET_NAME_PARTS = ('password', 'passphrase')

# A name stops at "?": "?a=1?token=x" and "?a?token=x" still show the parameter behind the second "?".
# A quote ends neither a name nor a value: the server reads both through it.
_NAME = re.compile(r'[?&;]([^=&;#\s?]*)=')
_VALUE = re.compile(r'[^&;#\s]*')


def _secret_name(raw):
    """Judged on the name the server decodes, so `pass%77ord` or `password[]` is a password."""
    name = unquote_plus(raw).lower()
    return name in SECRET_PARAMS or any(part in name for part in SECRET_NAME_PARTS)


def redact_url(value):
    """``value`` with the secret query values replaced; anything else unchanged."""
    if not isinstance(value, str) or '=' not in value:
        return value
    out, pos = [], 0
    # One pass, no recursion: a secret value is skipped whole, any other is scanned for more names
    while True:
        name = _NAME.search(value, pos)
        if name is None:
            break
        out.append(value[pos:name.end()])
        pos = name.end()
        if _secret_name(name[1]):
            out.append('[REDACTED]')
            pos = _VALUE.match(value, pos).end()
    out.append(value[pos:])
    return ''.join(out)


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
