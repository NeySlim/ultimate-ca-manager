"""SMTP "No authentication" after OAuth2: the method is stored and the sender does not authenticate."""
import json
from unittest.mock import MagicMock

import pytest

import services.email_service as email_service_module
from models import db
from models.email_notification import SMTPConfig

URL = '/api/v2/settings/email'
_COLUMNS = ('enabled', 'smtp_host', 'smtp_port', 'smtp_from', 'smtp_use_tls', 'smtp_use_ssl',
            'smtp_auth', 'smtp_auth_method', 'smtp_user', 'smtp_oauth_provider',
            'smtp_oauth_client_id')


def _patch(client, data):
    return client.patch(URL, data=json.dumps(data), content_type='application/json')


@pytest.fixture
def restore_smtp(app):
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
def smtp_server(monkeypatch):
    plain = MagicMock(name='SMTP')
    monkeypatch.setattr(email_service_module.smtplib, 'SMTP', plain)
    return plain.return_value


def _oauth_then_none(client):
    assert _patch(client, {
        'enabled': True, 'smtp_host': 'smtp.example.com', 'smtp_port': 25,
        'from_email': 'ucm@example.com', 'smtp_security': 'none',
        'smtp_auth_method': 'oauth2', 'smtp_username': 'box@example.com',
        'smtp_oauth_provider': 'google', 'smtp_oauth_client_id': 'cid',
        'smtp_oauth_client_secret': 'secret-value',
    }).status_code == 200
    assert _patch(client, {'smtp_auth_method': 'none'}).status_code == 200


def test_none_after_oauth2_leaves_no_oauth2_method_behind(app, auth_client, restore_smtp):
    _oauth_then_none(auth_client)
    with app.app_context():
        row = SMTPConfig.query.first()
        assert row.smtp_auth is False
        assert row.smtp_auth_method != 'oauth2'
    assert auth_client.get(URL).get_json()['data']['smtp_auth_method'] == 'none'


def test_the_test_email_does_not_authenticate_after_none(auth_client, restore_smtp, smtp_server):
    _oauth_then_none(auth_client)
    r = auth_client.post(URL + '/test', data=json.dumps({'email': 'admin@example.com'}),
                         content_type='application/json')
    assert r.status_code == 200, r.data[:300]
    smtp_server.docmd.assert_not_called()
    smtp_server.login.assert_not_called()


def test_authentication_is_still_attempted_when_it_is_on(app, auth_client, restore_smtp, smtp_server):
    assert _patch(auth_client, {
        'enabled': True, 'smtp_host': 'smtp.example.com', 'smtp_port': 25,
        'from_email': 'ucm@example.com', 'smtp_security': 'none',
        'smtp_auth_method': 'password', 'smtp_username': 'u@example.com',
        'smtp_password': 'pw-value-1',
    }).status_code == 200
    r = auth_client.post(URL + '/test', data=json.dumps({'email': 'admin@example.com'}),
                         content_type='application/json')
    assert r.status_code == 200, r.data[:300]
    smtp_server.login.assert_called_once()
