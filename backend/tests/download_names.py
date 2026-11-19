"""Shared checks for the download routes: a non-ASCII name must still answer 200 with an ASCII header."""
import re
from urllib.parse import unquote

JAPANESE = 'テスト用'
# Katakana, an emoji, a symbol and a script with combining marks: each must reach the client whole.
NAMES = [JAPANESE, '🔐🔐', '★CA', 'हिन्दी']
NAME_IDS = ['katakana', 'emoji', 'symbol', 'combining']
_ASCII_PART = {'★CA': 'CA'}


def plain_stem(name, fallback):
    """The plain ``filename`` stem a route gives *name*: its ASCII part, else the route's fallback."""
    return _ASCII_PART.get(name) or fallback
PARSE = re.compile(r'''^(?P<disp>attachment|inline); filename="(?P<plain>[^"]+)"; filename\*=UTF-8''(?P<star>[A-Za-z0-9!#$&+\-.^_`|~%]+)$''')


def disposition_of(response):
    assert response.status_code == 200, response.data[:300]
    value = response.headers['Content-Disposition']
    assert value.isascii(), value
    return value


def assert_named(response, stem, ext, fallback_stem=None, disposition='attachment', prefix=''):
    """200, ASCII header, ``filename*`` decoding to prefix+stem+ext, and a readable plain name."""
    value = disposition_of(response)
    match = PARSE.match(value)
    assert match, value
    assert match['disp'] == disposition
    assert unquote(match['star'], errors='strict') == f'{prefix}{stem}{ext}'
    plain = match['plain']
    assert plain.endswith(ext) and plain != ext
    assert plain[len(prefix):len(plain) - len(ext)].strip('_'), plain
    assert any(c.isalnum() for c in plain[:-len(ext)] if c not in prefix) or fallback_stem is None
    if fallback_stem is not None:
        assert plain == f'{prefix}{fallback_stem}{ext}', plain
    return plain
