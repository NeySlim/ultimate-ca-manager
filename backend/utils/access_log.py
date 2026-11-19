"""Gunicorn access log that keeps secrets carried in a URL out of the file."""
import re

from gunicorn.glogging import Logger

# Query parameters that carry a credential: password reset and OAuth/OIDC callbacks.
SECRET_PARAMS = ('token', 'code', 'state', 'access_token', 'id_token', 'refresh_token')

_SECRET_VALUE = re.compile(
    r'([?&;](?:%s)=)[^&;#\s"]*' % '|'.join(SECRET_PARAMS), re.IGNORECASE)


def redact_url(value):
    """``value`` with the secret query values replaced; anything else unchanged."""
    if not isinstance(value, str) or '=' not in value:
        return value
    return _SECRET_VALUE.sub(r'\1[REDACTED]', value)


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
