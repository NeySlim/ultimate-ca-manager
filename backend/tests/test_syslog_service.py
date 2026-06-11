"""Tests for the remote syslog forwarder (services/syslog_service.py).

Covers #135: HOSTNAME field populated from system_name (fallback machine
hostname), plus RFC 5424 structured-data escaping and TCP framing safety.
"""
import re
import pytest
from unittest.mock import Mock

from services.syslog_service import (
    SyslogForwarder,
    _sd_escape,
    _sanitize_hostname,
)


def make_audit_log(**overrides):
    log = Mock()
    log.timestamp = None
    log.action = overrides.get('action', 'login')
    log.username = overrides.get('username', 'admin')
    log.ip_address = overrides.get('ip_address', '10.0.0.1')
    log.resource_type = overrides.get('resource_type', 'user')
    log.resource_id = overrides.get('resource_id', '42')
    log.resource_name = overrides.get('resource_name', 'admin')
    log.success = overrides.get('success', True)
    log.details = overrides.get('details', 'User logged in')
    return log


@pytest.fixture
def forwarder():
    fwd = SyslogForwarder()
    fwd._initialize()
    fwd._protocol = 'udp'
    return fwd


class TestSdEscape:
    def test_escapes_rfc5424_special_chars(self):
        assert _sd_escape('a"b') == 'a\\"b'
        assert _sd_escape('a\\b') == 'a\\\\b'
        assert _sd_escape('a]b') == 'a\\]b'

    def test_plain_value_unchanged(self):
        assert _sd_escape('cert-01.example.com') == 'cert-01.example.com'


class TestSanitizeHostname:
    def test_empty_and_none(self):
        assert _sanitize_hostname(None) == ''
        assert _sanitize_hostname('') == ''

    def test_spaces_and_non_ascii_replaced(self):
        assert _sanitize_hostname('My UCM Server') == 'My-UCM-Server'
        assert _sanitize_hostname('pki-héberge') == 'pki-h-berge'

    def test_valid_fqdn_unchanged(self):
        assert _sanitize_hostname('pki.example.com') == 'pki.example.com'

    def test_truncated_to_255(self):
        assert len(_sanitize_hostname('a' * 300)) == 255


class TestBuildMessage:
    def test_hostname_from_system_name(self, app, forwarder):
        with app.app_context():
            from models import db
            from models.system_config import SystemConfig
            cfg = SystemConfig.query.filter_by(key='system_name').first()
            created = cfg is None
            if created:
                cfg = SystemConfig(key='system_name', value='My PKI Box')
                db.session.add(cfg)
            else:
                old = cfg.value
                cfg.value = 'My PKI Box'
            db.session.commit()
            try:
                msg = forwarder._build_message(make_audit_log()).decode()
                # HOSTNAME is the 4th token of the RFC 5424 header
                assert msg.split(' ')[2] == 'My-PKI-Box'
            finally:
                if created:
                    db.session.delete(cfg)
                else:
                    cfg.value = old
                db.session.commit()

    def test_hostname_falls_back_to_machine_hostname(self, app, forwarder):
        import socket
        with app.app_context():
            from models import db
            from models.system_config import SystemConfig
            cfg = SystemConfig.query.filter_by(key='system_name').first()
            assert cfg is None or not cfg.value, 'test expects no system_name set'
            msg = forwarder._build_message(make_audit_log()).decode()
            assert msg.split(' ')[2] == _sanitize_hostname(socket.gethostname())

    def test_hostname_never_nilvalue_blank(self, app, forwarder):
        with app.app_context():
            msg = forwarder._build_message(make_audit_log()).decode()
            hostname = msg.split(' ')[2]
            assert hostname  # never empty

    def test_structured_data_escaped(self, app, forwarder):
        with app.app_context():
            log = make_audit_log(resource_name='evil"] [fake@0 x="y')
            msg = forwarder._build_message(log).decode()
            # The raw injection must not appear unescaped (would close the SD element)
            assert 'evil"] [fake@0' not in msg
            assert re.search(r'resource_name="evil\\"\\\] \[fake@0 x=\\"y"', msg)

    def test_multiline_details_flattened(self, app, forwarder):
        with app.app_context():
            forwarder._protocol = 'tcp'
            log = make_audit_log(details='line one\nline two')
            msg = forwarder._build_message(log).decode()
            # Only the trailing TCP frame delimiter remains
            assert msg.count('\n') == 1 and msg.endswith('\n')
            assert 'line one line two' in msg

    def test_message_is_rfc5424_shaped(self, app, forwarder):
        with app.app_context():
            msg = forwarder._build_message(make_audit_log()).decode()
            assert re.match(
                r'^<\d{1,3}>1 \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z \S+ UCM - - \[ucm@0 .+\] .+',
                msg
            )

    def test_hostname_cache_reset_on_configure(self, app, forwarder):
        with app.app_context():
            forwarder._build_message(make_audit_log())
            assert forwarder._hostname
            forwarder.configure(enabled=False)
            assert forwarder._hostname == ''


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
