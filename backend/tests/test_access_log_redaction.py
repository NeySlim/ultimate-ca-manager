"""The access log never holds a reset token or an OAuth code from a URL."""
import importlib.util
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from gunicorn.config import Config

from utils.access_log import RedactingLogger, redact_url


@pytest.mark.parametrize('url, expected', [
    ('/reset-password?token=abc123', '/reset-password?token=[REDACTED]'),
    ('/api/v2/sso/callback/oauth2?code=c0de&state=s7&x=1',
     '/api/v2/sso/callback/oauth2?code=[REDACTED]&state=[REDACTED]&x=1'),
    ('https://pki.example.test/reset-password?TOKEN=abc', 'https://pki.example.test/reset-password?TOKEN=[REDACTED]'),
    ('/scep?operation=GetCACert&message=ca', '/scep?operation=GetCACert&message=ca'),
    ('/api/v2/certificates?page=2', '/api/v2/certificates?page=2'),
    ('/api/v2/x?mytoken=keep', '/api/v2/x?mytoken=keep'),
    ('-', '-'),
    ('/api/v2/csrs/4/export?format=key&password=Pw1', '/api/v2/csrs/4/export?format=key&password=[REDACTED]'),
    ('/api/v2/certificates/4/export?Password=Pw1&format=pem',
     '/api/v2/certificates/4/export?Password=[REDACTED]&format=pem'),
    ('/api/v2/cas/4/export?PASSPHRASE=Pw1', '/api/v2/cas/4/export?PASSPHRASE=[REDACTED]'),
    ('/api/v2/x?pkcs12_password=Pw1&a=1', '/api/v2/x?pkcs12_password=[REDACTED]&a=1'),
    # The name as the server decodes it, however the URL spells it
    ('/api/v2/csrs/4/export?pass%77ord=Pw1&format=key', '/api/v2/csrs/4/export?pass%77ord=[REDACTED]&format=key'),
    ('/api/v2/csrs/4/export?password%5B%5D=Pw1', '/api/v2/csrs/4/export?password%5B%5D=[REDACTED]'),
    ('/api/v2/csrs/4/export?password+=Pw1', '/api/v2/csrs/4/export?password+=[REDACTED]'),
    ('/reset-password?%74oken=abc', '/reset-password?%74oken=[REDACTED]'),
    ('/api/v2/x?pass%2Bword=keep', '/api/v2/x?pass%2Bword=keep'),
    # A second "?" typed for "&": the secret parameter behind it is still one
    ('/reset-password?lang=fr?token=abc', '/reset-password?lang=fr?token=[REDACTED]'),
    ('/api/v2/certificates/4/export?format=key?password=S3cret',
     '/api/v2/certificates/4/export?format=key?password=[REDACTED]'),
    ('/cb?x=1?code=abc&state=s', '/cb?x=1?code=[REDACTED]&state=[REDACTED]'),
    ('/reset-password?token=ab?cd=ef', '/reset-password?token=[REDACTED]'),
])
def test_redact_url(url, expected):
    assert redact_url(url) == expected


def test_a_long_run_of_question_marks_is_still_read_to_its_end():
    """The line is masked whatever its length: a URL cannot make the log drop its own request."""
    url = '/x?x=1' + '?a=' * 1300 + '?token=abc&b=2'
    assert redact_url(url) == '/x?x=1' + '?a=' * 1300 + '?token=[REDACTED]&b=2'


def test_a_name_cut_by_a_question_mark_does_not_hide_the_parameter_behind_it():
    assert redact_url('/x?a?token=abc') == '/x?a?token=[REDACTED]'


def test_the_gunicorn_line_carries_no_token():
    cfg = Config()
    cfg.set('access_log_format', '%(h)s "%(r)s" %(q)s "%(f)s"')
    logger = RedactingLogger(cfg)
    environ = {'REQUEST_METHOD': 'GET', 'RAW_URI': '/reset-password?token=s3cret-tok',
               'SERVER_PROTOCOL': 'HTTP/1.1', 'PATH_INFO': '/reset-password',
               'QUERY_STRING': 'token=s3cret-tok', 'REMOTE_ADDR': '192.0.2.7',
               'HTTP_REFERER': 'https://pki.example.test/reset-password?token=s3cret-tok'}
    resp = SimpleNamespace(status='200 OK', sent=10, headers=[])
    req = SimpleNamespace(headers=[('REFERER', environ['HTTP_REFERER'])])
    atoms = logger.atoms(resp, req, environ, timedelta(seconds=0))
    line = cfg.access_log_format % atoms
    assert 's3cret-tok' not in line
    assert 's3cret-tok' not in str(atoms)
    assert '/reset-password?token=[REDACTED]' in line


def test_gunicorn_config_uses_the_redacting_logger(monkeypatch):
    import gevent.monkey

    # A plain import would monkey patch the whole test process for later tests
    monkeypatch.setattr(gevent.monkey, 'patch_all', lambda *a, **k: None)
    monkeypatch.setenv('UCM_SCHEDULER_SUPERVISED', '')
    path = Path(__file__).resolve().parent.parent / 'gunicorn_config.py'
    spec = importlib.util.spec_from_file_location('_ucm_gunicorn_config_log', path)
    gunicorn_config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gunicorn_config)
    assert gunicorn_config.logger_class is RedactingLogger
    cfg = Config()
    cfg.set('logger_class', gunicorn_config.logger_class)
    assert cfg.logger_class is RedactingLogger


@pytest.mark.parametrize('url, expected', [
    ('/x?my"password=secret', '/x?my"password=[REDACTED]'),
    ('/x?a=1&"Passphrase"=abc&b=2', '/x?a=1&"Passphrase"=[REDACTED]&b=2'),
    ('/x?password=se"cret&b=2', '/x?password=[REDACTED]&b=2'),
    ('/x?a="1"&b=2', '/x?a="1"&b=2'),
])
def test_a_quote_neither_hides_a_name_nor_cuts_a_value(url, expected):
    assert redact_url(url) == expected


@pytest.mark.parametrize('unit', ['&', '?a=', '"', '?"', '&"=', '?a"'])
def test_a_one_megabyte_url_is_redacted_in_linear_time(unit):
    import time
    url = '/x?' + unit * (1_000_000 // len(unit)) + '&password=secret'
    started = time.perf_counter()
    redacted = redact_url(url)
    assert time.perf_counter() - started < 2
    assert redacted.endswith('&password=[REDACTED]') and 'secret' not in redacted
