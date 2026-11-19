"""content_disposition(): a download name that is not ASCII reaches the client and the header stays ASCII.

The real server (gevent pywsgi) refuses a header that is not Latin-1; the Flask test client does not,
so the last class runs a real WSGIServer on an ephemeral port.
"""
import http.client
import re
import threading
from urllib.parse import unquote

import pytest
from gevent import pywsgi

from tests.header_guard import Latin1HeaderGuard
from utils.sanitize import content_disposition, sanitize_filename

_EXT = re.compile(r'''^(?P<disp>[a-z]+); filename="(?P<plain>[^"]*)"(?:; filename\*=UTF-8''(?P<star>[A-Za-z0-9!#$&+\-.^_`|~%]+))?$''')


def parse(value):
    match = _EXT.match(value)
    assert match, value
    star = match.group('star')
    return match.group('disp'), match.group('plain'), (unquote(star, errors='strict') if star else None)


class TestAscii:
    def test_ascii_name_keeps_the_historical_header(self):
        assert content_disposition('web server', '.p12') == 'attachment; filename="web server.p12"'

    def test_inline(self):
        assert content_disposition('ca', '_ca.pub', disposition='inline') == 'inline; filename="ca_ca.pub"'

    def test_no_extended_form_for_ascii(self):
        assert 'filename*' not in content_disposition('plain', '.crt')

    def test_percent_in_ascii_name_is_left_alone(self):
        assert content_disposition('100%', '.crt') == 'attachment; filename="100%.crt"'


class TestNotAscii:
    def test_japanese_name_with_fallback(self):
        value = content_disposition('テスト用', '.p12', fallback='abc123')
        assert value.isascii()
        disp, plain, star = parse(value)
        assert (disp, plain, star) == ('attachment', 'abc123.p12', 'テスト用.p12')

    def test_japanese_without_fallback_is_never_blank(self):
        _, plain, star = parse(content_disposition('テスト用', '.p12'))
        assert plain == 'download.p12' and star == 'テスト用.p12'

    def test_accented_latin_is_folded_in_the_plain_form(self):
        _, plain, star = parse(content_disposition('Café', '.crt', fallback='r1'))
        assert (plain, star) == ('Cafe.crt', 'Café.crt')

    def test_mixed_keeps_the_ascii_part(self):
        _, plain, star = parse(content_disposition('テストCA', '.pem', fallback='r1'))
        assert (plain, star) == ('CA.pem', 'テストCA.pem')

    def test_unreadable_fold_uses_the_fallback(self):
        _, plain, _ = parse(content_disposition('(テスト)', '.pem', fallback='r1'))
        assert plain == 'r1.pem'

    def test_a_non_ascii_fallback_is_folded_too(self):
        _, plain, star = parse(content_disposition('テスト', '.pem', fallback='Café'))
        assert plain == 'Cafe.pem' and star == 'テスト.pem'

    def test_space_and_percent_are_percent_encoded(self):
        value = content_disposition('テ 100%', '.crt', fallback='r1')
        assert '%20' in value and '%25' in value
        assert parse(value)[2] == 'テ 100%.crt'

    def test_astral_character(self):
        assert parse(content_disposition('🔐key', '.pem', fallback='r1'))[2] == '🔐key.pem'

    def test_lone_surrogate_does_not_raise(self):
        assert content_disposition('テ\ud800', '.pem', fallback='r1').isascii()


class TestInjection:
    @pytest.mark.parametrize('name', ['a\r\nSet-Cookie: x=1', 'テ\r\nX: y', 'a"b', 'テ"; filename="evil', 'a\x00b', 'a\x7fb'])
    def test_no_control_or_quote_survives(self, name):
        value = content_disposition(name, '.crt', fallback='r1')
        assert value.isascii()
        assert not re.search(r'[\x00-\x1f\x7f]', value)
        _, plain, star = parse(value)
        assert '"' not in plain
        assert star is None or not re.search(r'[\x00-\x1f\x7f"]', star)

    @pytest.mark.parametrize('name', ['a＂; filename＝evil.exe; x＝＂テ', '..／..／etc／passwd テ', 'a＼b テ', 'a℀b ℅ テ', 'a﹨b；テ'])
    def test_compatibility_forms_fold_to_no_injection(self, name):
        value = content_disposition(name, '.p12', fallback='r1')
        assert value.isascii() and value.count('"') == 2
        _, plain, _ = parse(value)
        assert not re.search(r'[/\\"]', plain)

    def test_separators_become_underscores(self):
        _, plain, star = parse(content_disposition('テ/..\\x', '.crt', fallback='r1'))
        assert '/' not in star and '\\' not in star and star == 'テ_.._x.crt'

    @pytest.mark.parametrize('name', [None, '', '"', '\r\n', '"\r\n"'])
    def test_empty_or_fully_stripped_name_uses_fallback(self, name):
        assert content_disposition(name, '.crt', fallback='r1') == 'attachment; filename="r1.crt"'
        assert content_disposition(name, '.crt') == 'attachment; filename="download.crt"'


class TestSpoofing:
    @pytest.mark.parametrize('mark', ['\u202e', '\u0085', '\u2028', '\u2029', '\u200e'],
                             ids=['bidi-override', 'c1-next-line', 'line-sep', 'para-sep', 'lrm'])
    def test_format_and_separator_characters_are_dropped(self, mark):
        assert content_disposition(f'n{mark}b', '.crt', fallback='r1') == 'attachment; filename="nb.crt"'
        _, plain, star = parse(content_disposition(f'テ{mark}b', '.crt', fallback='r1'))
        assert (plain, star) == ('b.crt', 'テb.crt')


class TestFallbackShape:
    def test_no_leading_dot_in_the_plain_form(self):
        _, plain, star = parse(content_disposition('テスト.CA', '.p12', fallback='r1'))
        assert (plain, star) == ('CA.p12', 'テスト.CA.p12')

    def test_no_percent_escape_in_the_plain_form(self):
        _, plain, star = parse(content_disposition('テスト%41', '.p12', fallback='r1'))
        assert (plain, star) == ('r1.p12', 'テスト%41.p12')

    def test_a_lone_percent_stays(self):
        assert parse(content_disposition('テ 100%', '.p12', fallback='r1'))[1] == '100%.p12'


class TestLength:
    def test_long_name_is_bounded_as_before(self):
        assert content_disposition('a' * 300, '.crt') == f'attachment; filename="{"a" * 200}.crt"'

    def test_long_japanese_name_keeps_extension_and_bound(self):
        _, plain, star = parse(content_disposition('あ' * 300, '.crt', fallback='r1'))
        assert star == 'あ' * 66 + '.crt' and plain == 'r1.crt'
        assert len(('あ' * 66).encode()) <= 200

    def test_sanitize_filename_is_unchanged(self):
        assert sanitize_filename('a"b/c\r\n') == 'ab_c'
        assert sanitize_filename('') == 'download' and sanitize_filename(None) == 'download'
        assert sanitize_filename('x' * 300) == 'x' * 200


class _Served:
    """A gevent WSGIServer in a thread of its own (greenlets would not run under a blocking client)."""

    def __init__(self, application):
        self.application = application
        self.ready = threading.Event()
        self.port = None
        self.server = None
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        self.server = pywsgi.WSGIServer(('127.0.0.1', 0), self.application, log=None)
        self.server.start()
        self.port = self.server.server_port
        self.ready.set()
        self.server.serve_forever()

    def __enter__(self):
        self.thread.start()
        assert self.ready.wait(5)
        return self

    def __exit__(self, *exc):
        self.server.stop(timeout=1)
        self.thread.join(5)


def _get(server):
    conn = http.client.HTTPConnection('127.0.0.1', server.port, timeout=5)
    try:
        conn.request('GET', '/')
        response = conn.getresponse()
        return response.status, response.getheader('Content-Disposition'), response.read()
    finally:
        conn.close()


def _app_returning(value):
    def application(environ, start_response):
        start_response('200 OK', [('Content-Type', 'text/plain'), ('Content-Disposition', value)])
        return [b'ok']
    return application


class TestRealServer:
    """The guard is pinned on gevent's own behaviour, not on a belief about it."""

    def test_real_server_refuses_a_non_latin1_header(self):
        with _Served(_app_returning('attachment; filename="テスト用.p12"')) as server:
            status, received, _ = _get(server)
        assert status == 500 and received is None

    def test_guard_fails_the_same_header_with_the_same_exception(self):
        guarded = Latin1HeaderGuard(_app_returning('attachment; filename="テスト用.p12"'))
        with pytest.raises(UnicodeError, match='Content-Disposition'):
            guarded({'REQUEST_METHOD': 'GET'}, lambda *a, **k: None)

    def test_the_helper_header_passes_and_comes_back_verbatim(self):
        value = content_disposition('テスト用', '.p12', fallback='abc')
        with _Served(Latin1HeaderGuard(_app_returning(value))) as server:
            status, received, body = _get(server)
        assert (status, received, body) == (200, value, b'ok')
        assert parse(received)[2] == 'テスト用.p12'


class TestAlignedWithTheInterface:
    """Leading dots, Windows device names and the byte budget follow frontend/src/lib/filename.js."""

    def test_leading_dots_are_dropped(self):
        assert content_disposition('..hidden', '.crt') == 'attachment; filename="hidden.crt"'
        assert content_disposition('...', '.crt', fallback='r1') == 'attachment; filename="r1.crt"'

    @pytest.mark.parametrize('name', ['CON', 'nul', 'Lpt3', 'com1'])
    def test_windows_device_names_get_an_underscore(self, name):
        assert content_disposition(name, '.crt') == f'attachment; filename="{name}_.crt"'
        assert content_disposition('console', '.crt') == 'attachment; filename="console.crt"'

    def test_the_cut_counts_bytes_of_whole_characters(self):
        star = parse(content_disposition('\U00020000' * 100, '.crt', fallback='r1'))[2]
        stem = star[:-len('.crt')]
        assert stem == '\U00020000' * 50 and len(stem.encode()) == 200

    @pytest.mark.parametrize('name', ['web server', 'a' * 300, 'example.com', 'CA 2026-11', 'x.y.z'])
    def test_an_ascii_label_is_unchanged_and_stable(self, name):
        once = sanitize_filename(name)
        assert sanitize_filename(once) == once
        assert content_disposition(once, '.p12') == content_disposition(name, '.p12')
        if len(name) <= 200:
            assert once == name
