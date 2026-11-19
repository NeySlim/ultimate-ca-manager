"""Sanitization utilities for user-controlled input."""

import re
import unicodedata
from urllib.parse import quote


def _clean_filename(name):
    """*name* without control characters, quotes and separators, at most 200 characters; '' if nothing is left."""
    if not name:
        return ''
    name = re.sub(r'[\x00-\x1f\x7f\r\n]', '', name)
    name = re.sub(r'[/\\]', '_', name)
    return name.replace('"', '')[:200]


def sanitize_filename(name):
    """Sanitize a string for safe use in Content-Disposition headers.

    Removes/replaces characters that could cause header injection or
    filesystem issues.
    """
    return _clean_filename(name) or 'download'


def _ascii_fallback(text):
    """The ASCII reading of *text* (accents folded), or '' when nothing readable is left."""
    folded = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    return folded if any(c.isalnum() for c in folded) else ''


def content_disposition(name, ext='', fallback=None, disposition='attachment', prefix=''):
    """Complete Content-Disposition value for a download named *prefix* + *name* + *ext*.

    An ASCII name gives ``attachment; filename="name.ext"``; any other gives that form with an
    ASCII fallback plus ``filename*=UTF-8''...`` (RFC 6266 4.3, RFC 8187 3.2.3). The header is
    always ASCII, since the server refuses one that is not Latin-1. *fallback* (e.g. a refid)
    stands in when the name has no readable ASCII left; *prefix* is a constant ASCII lead-in.
    """
    stem = _clean_filename(name) or _clean_filename(fallback) or 'download'
    full = f'{prefix}{stem}{ext}'
    if full.isascii():
        return f'{disposition}; filename="{full}"'
    simple = _ascii_fallback(stem) or _ascii_fallback(_clean_filename(fallback)) or 'download'
    encoded = quote(full, safe="!#$&+-.^_`|~", errors='replace')
    return f'{disposition}; filename="{prefix}{simple}{ext}"; filename*=UTF-8\'\'{encoded}'


def client_filename(name, limit=255):
    """A client-supplied file name as one audit line: its base name (either separator),
    without control, format (bidi marks) or line-separator characters, at most *limit* characters."""
    import unicodedata
    base = re.split(r'[/\\]', name or '')[-1]
    base = ''.join(c for c in base if unicodedata.category(c) not in ('Cc', 'Cf', 'Zl', 'Zp'))
    base = base[:limit].strip('. ')
    return base or 'upload'


def ca_url_slug(name):
    """URL-safe slug from a CA name for named protocol URLs (#207)."""
    return re.sub(r'[^a-z0-9]+', '-', (name or '').lower()).strip('-')[:48]


def crl_download_filename(ca, delta=False):
    """Readable CRL filename for Content-Disposition (#207).

    URLs keep the refid (they are embedded in issued certificates); only the
    suggested download name uses the CA description, e.g. ``lan-ca-6382320a.crl``.
    """
    slug = re.sub(r'[^a-z0-9]+', '-', (ca.descr or '').lower()).strip('-')[:40]
    ref = (ca.refid or '')[:8]
    base = f"{slug}-{ref}" if slug else (ref or 'ca')
    return f"{base}-delta.crl" if delta else f"{base}.crl"
