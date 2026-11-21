"""Sanitization utilities for user-controlled input."""

import re
import unicodedata
from urllib.parse import quote


_UNSEEN = ('Cc', 'Cf', 'Zl', 'Zp')
_MAX_BYTES = 200
_PERCENT_ESCAPE = re.compile(r'%[0-9A-Fa-f]{2}')
# Device names Windows refuses whatever follows the first dot (same list as the interface).
_WINDOWS_DEVICE = re.compile(r'^(con|prn|aux|nul|com[0-9\u00b9\u00b2\u00b3]|lpt[0-9\u00b9\u00b2\u00b3])$', re.I)


def _clip(text):
    """The longest prefix of whole characters within 200 characters and 200 UTF-8 bytes."""
    out, size = [], 0
    for c in text[:200]:
        size += len(c.encode('utf-8', 'replace'))
        if size > _MAX_BYTES:
            break
        out.append(c)
    return ''.join(out)


def _clean_filename(name):
    """*name* without control, format (bidi), line-separator characters and quotes, separators
    replaced by '_', no leading dot, no Windows device name, at most 200 characters and bytes; '' if nothing is left."""
    if not name:
        return ''
    name = ''.join(c for c in name if unicodedata.category(c) not in _UNSEEN)
    name = re.sub(r'[/\\]', '_', name)
    name = _clip(name.replace('"', '').lstrip('.'))
    stem = name.split('.', 1)[0]
    # Windows drops trailing spaces before matching a device name (`COM1 .pem` is COM1)
    if _WINDOWS_DEVICE.match(stem.rstrip(' ')):
        name = f"{stem.rstrip(' ')}_{name[len(stem):]}"
    return name


def sanitize_filename(name):
    """*name* without the characters that inject a header or a path, 'download' if none is left.

    It keeps non-ASCII: only content_disposition() makes a header value of it.
    """
    return _clean_filename(name) or 'download'


def _ascii_fallback(text):
    """The ASCII reading of *text* (accents folded), or '' when nothing readable is left."""
    # NFKD turns compatibility forms (fullwidth quote, solidus) into ASCII: clean after folding.
    folded = _clean_filename(unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii'))
    # No hidden file and no %XX a client could decode (RFC 6266 appendix D).
    folded = folded.strip(' .')
    if _PERCENT_ESCAPE.search(folded):
        return ''
    return folded if any(c.isalnum() for c in folded) else ''


def content_disposition(name, ext='', fallback=None, disposition='attachment', prefix=''):
    """Complete Content-Disposition value for a download named *prefix* + *name* + *ext*.

    An ASCII name gives ``attachment; filename="name.ext"``; any other gives that form with an
    ASCII fallback plus ``filename*=UTF-8''...`` (RFC 6266 4.3, RFC 8187 3.2.1). The header is
    always ASCII, since the server refuses one that is not Latin-1. *fallback* (e.g. a refid)
    stands in when the name has no readable ASCII left; *prefix* is a constant ASCII lead-in.
    """
    stem = _clean_filename(name) or _clean_filename(fallback) or 'download'
    full = f'{prefix}{stem}{ext}'
    # A %XX in `filename` may be decoded by a client (RFC 6266 appendix D): filename* then
    if full.isascii() and not _PERCENT_ESCAPE.search(full):
        return f'{disposition}; filename="{full}"'
    simple = _ascii_fallback(stem) or _ascii_fallback(_clean_filename(fallback)) or 'download'
    encoded = quote(full, safe="!#$&+-.^_`|~", errors='replace')
    return f'{disposition}; filename="{prefix}{simple}{ext}"; filename*=UTF-8\'\'{encoded}'


def client_filename(name, limit=255):
    """A client-supplied file name as one audit line: its base name (either separator),
    without control, format (bidi marks) or line-separator characters, at most *limit* characters."""
    base = re.split(r'[/\\]', name or '')[-1]
    base = ''.join(c for c in base if unicodedata.category(c) not in _UNSEEN)
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
