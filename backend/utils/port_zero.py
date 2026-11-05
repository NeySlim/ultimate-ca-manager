"""Port 0 in a protocol URL stored on a CA: it reaches nothing, and every certificate copies it.

UCM once built such URLs with the built-in HTTP listener disabled. Dropping it gives the default
port, which is what the URL builder now produces. An archive can still bring one back.
"""
import json
import re

_PORT_ZERO = re.compile(r'^(https?://(?:\[[^\]]*\]|[^/:?#@\[\]]+)):0(?=[/?#]|$)', re.IGNORECASE)


def strip_port_zero(url):
    return _PORT_ZERO.sub(r'\1', url) if isinstance(url, str) else url


def strip_port_zero_from_stored(value):
    """The column value without port 0, in the form it was stored: one URL or a JSON list."""
    if not value or not isinstance(value, str):
        return value
    if value.startswith('['):
        try:
            urls = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            urls = None
        if isinstance(urls, list):
            fixed = []
            for url in urls:
                url = strip_port_zero(url)
                if url not in fixed:
                    fixed.append(url)
            return json.dumps(fixed) if fixed != urls else value
    return strip_port_zero(value)
