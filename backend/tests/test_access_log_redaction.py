"""The access log never holds a reset token or an OAuth code from a URL."""
from datetime import timedelta
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
])
def test_redact_url(url, expected):
    assert redact_url(url) == expected


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


def test_gunicorn_config_uses_the_redacting_logger():
    import gunicorn_config
    assert gunicorn_config.logger_class is RedactingLogger
    cfg = Config()
    cfg.set('logger_class', gunicorn_config.logger_class)
    assert cfg.logger_class is RedactingLogger
