"""RFC 8288 Link header parsing shared by the ACME client and proxy."""
import re

_LINK_PARAM_RE = re.compile(
    r';\s*([^\s=;,]+)\s*(?:=\s*("[^"]*"|\'[^\']*\'|[^;]*))?'
)


def link_values(header: str):
    """Yield (url, params) for each value of an RFC 8288 Link header, repeated
    headers joined by commas included."""
    position, length = 0, len(header)
    while position < length:
        start = header.find('<', position)
        if start < 0:
            return
        end = header.find('>', start + 1)
        if end < 0:
            return
        url = header[start + 1:end].strip()
        cursor, quote = end + 1, None
        while cursor < length:
            char = header[cursor]
            if quote:
                if char == quote:
                    quote = None
            elif char in '"\'':
                quote = char
            elif char == ',':
                break
            cursor += 1
        params = {}
        for match in _LINK_PARAM_RE.finditer(header[end + 1:cursor]):
            name = match.group(1).lower()
            value = (match.group(2) or '').strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
                value = value[1:-1]
            params.setdefault(name, value)
        yield url, params
        position = cursor + 1
