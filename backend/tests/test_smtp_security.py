"""
SMTP transport security: implicit TLS (port 465) is selectable through the API
and reaches the sender, STARTTLS and plain stay as before.
"""
import json
from unittest.mock import MagicMock

import pytest

import services.email_service as email_service_module
from models import db
from models.email_notification import SMTPConfig
from services.email_service import _smtp_connect

URL = '/api/v2/settings/email'
_COLUMNS = ('enabled', 'smtp_host', 'smtp_port', 'smtp_from', 'smtp_use_tls',
            'smtp_use_ssl', 'smtp_auth')


def _patch(client, data):
    return client.patch(URL, data=json.dumps(data), content_type='application/json')


@pytest.fixture
def restore_smtp(app):
    """The suite shares one database: put the SMTP row back as it was."""
    with app.app_context():
        row = SMTPConfig.query.first()
        saved = {c: getattr(row, c) for c in _COLUMNS} if row else None
    yield
    with app.app_context():
        row = SMTPConfig.query.first()
        if saved is None:
            if row:
                db.session.delete(row)
        else:
            for c, v in saved.items():
                setattr(row, c, v)
        db.session.commit()


@pytest.fixture
def smtp_spies(monkeypatch):
    plain, implicit = MagicMock(name='SMTP'), MagicMock(name='SMTP_SSL')
    monkeypatch.setattr(email_service_module.smtplib, 'SMTP', plain)
    monkeypatch.setattr(email_service_module.smtplib, 'SMTP_SSL', implicit)
    return plain, implicit


class _Config:
    smtp_host = 'smtp.example.com'
    smtp_port = 465
    smtp_use_ssl = False
    smtp_use_tls = False


class TestSmtpConnect:
    def test_ssl_opens_implicit_tls(self, smtp_spies):
        plain, implicit = smtp_spies
        cfg = _Config()
        cfg.smtp_use_ssl = True
        cfg.smtp_use_tls = True  # implicit TLS wins, no STARTTLS on top
        _smtp_connect(cfg, timeout=10)
        implicit.assert_called_once_with('smtp.example.com', 465, timeout=10)
        plain.assert_not_called()

    def test_starttls_upgrades_plain_session(self, smtp_spies):
        plain, implicit = smtp_spies
        cfg = _Config()
        cfg.smtp_port, cfg.smtp_use_tls = 587, True
        server = _smtp_connect(cfg, timeout=10)
        server.starttls.assert_called_once_with()
        implicit.assert_not_called()

    def test_none_stays_plain(self, smtp_spies):
        plain, _ = smtp_spies
        cfg = _Config()
        cfg.smtp_port = 25
        _smtp_connect(cfg, timeout=10).starttls.assert_not_called()

    def test_failed_starttls_closes_socket(self, smtp_spies):
        plain, _ = smtp_spies
        plain.return_value.starttls.side_effect = OSError('handshake')
        cfg = _Config()
        cfg.smtp_use_tls = True
        with pytest.raises(OSError):
            _smtp_connect(cfg, timeout=10)
        plain.return_value.close.assert_called_once_with()


class TestSmtpSecurityApi:
    @pytest.mark.parametrize('mode, tls, ssl', [
        ('ssl', False, True), ('starttls', True, False), ('none', False, False),
    ])
    def test_round_trip(self, auth_client, restore_smtp, mode, tls, ssl):
        assert _patch(auth_client, {'smtp_security': mode}).status_code == 200
        data = auth_client.get(URL).get_json()['data']
        assert (data['smtp_security'], data['smtp_tls'], data['smtp_ssl']) == (mode, tls, ssl)

    def test_unknown_mode_rejected_before_any_write(self, auth_client, restore_smtp):
        assert _patch(auth_client, {'smtp_security': 'starttls'}).status_code == 200
        r = _patch(auth_client, {'smtp_security': 'tls', 'smtp_host': 'other.example'})
        assert r.status_code == 400
        data = auth_client.get(URL).get_json()['data']
        assert data['smtp_security'] == 'starttls'
        assert data['smtp_host'] != 'other.example'

    def test_legacy_smtp_tls_still_accepted(self, auth_client, restore_smtp):
        assert _patch(auth_client, {'smtp_security': 'none'}).status_code == 200
        assert _patch(auth_client, {'smtp_tls': True}).status_code == 200
        assert auth_client.get(URL).get_json()['data']['smtp_security'] == 'starttls'

    def test_test_email_uses_implicit_tls_on_465(self, auth_client, restore_smtp, smtp_spies):
        plain, implicit = smtp_spies
        assert _patch(auth_client, {
            'enabled': True, 'smtp_host': 'smtp.example.com', 'smtp_port': 465,
            'from_email': 'ucm@example.com', 'smtp_auth_method': 'none',
            'smtp_security': 'ssl',
        }).status_code == 200
        r = auth_client.post(URL + '/test', data=json.dumps({'email': 'admin@example.com'}),
                             content_type='application/json')
        assert r.status_code == 200, r.data[:300]
        implicit.assert_called_once_with('smtp.example.com', 465, timeout=30)
        plain.assert_not_called()
