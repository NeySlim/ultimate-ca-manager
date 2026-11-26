"""The SMTP target receives every password-reset link: like base_url, only
admin:settings moves it. write:settings still saves the rest of the card."""
import json

import pytest

from models import db
from models.email_notification import SMTPConfig

pytestmark = pytest.mark.usefixtures('drop_new_users')

URL = '/api/v2/settings/email'
_COLUMNS = ('enabled', 'smtp_host', 'smtp_port', 'smtp_user', 'smtp_from', 'smtp_from_name',
            'smtp_use_tls', 'smtp_use_ssl', 'smtp_auth', 'smtp_auth_method',
            'smtp_oauth_provider', 'smtp_oauth_tenant_id', 'smtp_oauth_authorize_url',
            'smtp_oauth_token_url', 'smtp_oauth_redirect_uri', '_smtp_password',
            '_smtp_oauth_client_secret', '_smtp_oauth_refresh_token', 'smtp_content_type')

STORED = dict(enabled=True, smtp_host='relay.example.com', smtp_port=587, smtp_user=None,
              smtp_from='ucm@example.com', smtp_from_name='UCM', smtp_use_tls=True,
              smtp_use_ssl=False, smtp_auth=False, smtp_auth_method='password',
              smtp_oauth_provider=None, smtp_oauth_tenant_id=None,
              smtp_oauth_authorize_url=None, smtp_oauth_token_url=None,
              smtp_oauth_redirect_uri=None, _smtp_password=None,
              _smtp_oauth_client_secret=None, _smtp_oauth_refresh_token=None,
              smtp_content_type='html')

# The card as the interface saves it, unchanged
FORM = {'smtp_host': 'relay.example.com', 'smtp_port': 587, 'smtp_username': '',
        'smtp_password': '', 'smtp_security': 'starttls', 'smtp_auth': False,
        'smtp_content_type': 'html', 'from_email': 'ucm@example.com', 'from_name': 'UCM',
        'enabled': True, 'smtp_auth_method': 'none', 'smtp_oauth_provider': 'google',
        'smtp_oauth_tenant_id': '', 'smtp_oauth_client_id': '',
        'smtp_oauth_authorize_url': '', 'smtp_oauth_token_url': '', 'smtp_oauth_scope': '',
        'smtp_oauth_redirect_uri': ''}


def _login(app, create_user, username, role):
    create_user(username=username, role=role)
    client = app.test_client()
    r = client.post('/api/v2/auth/login',
                    data=json.dumps({'username': username, 'password': 'TestPass123!'}),
                    content_type='application/json')
    assert r.status_code == 200, r.data
    return client


@pytest.fixture(scope='module')
def operator_client(app, create_user):
    return _login(app, create_user, 'op_smtp_target', 'operator')


@pytest.fixture(scope='module')
def auditor_client(app, create_user):
    return _login(app, create_user, 'aud_smtp_target', 'auditor')


@pytest.fixture
def stored_smtp(app):
    """One SMTP row set to STORED, put back as it was afterwards."""
    with app.app_context():
        row = SMTPConfig.query.first()
        saved = {c: getattr(row, c) for c in _COLUMNS} if row else None
        if row is None:
            row = SMTPConfig()
            db.session.add(row)
        for c, v in STORED.items():
            setattr(row, c, v)
        db.session.commit()
    yield
    with app.app_context():
        row = SMTPConfig.query.first()
        if saved is None:
            db.session.delete(row)
        else:
            for c, v in saved.items():
                setattr(row, c, v)
        db.session.commit()


def _patch(client, body):
    return client.patch(URL, data=json.dumps(body), content_type='application/json')


def _row():
    db.session.expire_all()
    row = SMTPConfig.query.first()
    return {c: getattr(row, c) for c in STORED}


@pytest.mark.parametrize('body, named', [
    ({'smtp_host': 'mail.attacker.example'}, 'smtp_host'),
    ({'smtp_port': 2525}, 'smtp_port'),
    ({'smtp_security': 'none'}, 'smtp_security'),
    ({'smtp_tls': False}, 'smtp_security'),
    ({'from_email': 'x@attacker.example'}, 'from_email'),
    ({'smtp_auth': True}, 'smtp_auth_method'),
    ({'smtp_auth_method': 'oauth2'}, 'smtp_auth_method'),
    (dict(FORM, smtp_host='mail.attacker.example', smtp_port=2525, smtp_security='none',
          from_email='x@attacker.example'), 'smtp_host'),
])
def test_an_operator_cannot_move_the_smtp_target(app, operator_client, stored_smtp, body, named):
    r = _patch(operator_client, body)
    assert r.status_code == 403, r.data
    assert named in r.get_json()['message']
    with app.app_context():
        assert _row() == STORED


def test_an_operator_saves_the_card_with_the_target_unchanged(app, operator_client, stored_smtp):
    r = _patch(operator_client, dict(FORM, from_name='Certificates', smtp_content_type='text'))
    assert r.status_code == 200, r.data
    with app.app_context():
        row = _row()
    assert (row['smtp_from_name'], row['smtp_content_type']) == ('Certificates', 'text')
    assert row['smtp_host'] == 'relay.example.com'


def test_an_operator_cannot_move_the_oauth_endpoints(app, operator_client, stored_smtp):
    with app.app_context():
        row = SMTPConfig.query.first()
        row.smtp_auth, row.smtp_auth_method, row.smtp_oauth_provider = True, 'oauth2', 'custom'
        row.smtp_oauth_authorize_url = 'https://idp.example.com/authorize'
        row.smtp_oauth_token_url = 'https://idp.example.com/token'
        db.session.commit()
    r = _patch(operator_client, {'smtp_oauth_token_url': 'https://idp.attacker.example/token'})
    assert r.status_code == 403, r.data
    assert 'smtp_oauth_token_url' in r.get_json()['message']
    r = _patch(operator_client, {'smtp_oauth_redirect_uri': 'https://attacker.example/cb'})
    assert r.status_code == 403, r.data
    with app.app_context():
        assert SMTPConfig.query.first().smtp_oauth_token_url == 'https://idp.example.com/token'


def test_an_operator_cannot_redirect_the_oauth_consent(app, operator_client, stored_smtp):
    r = operator_client.post(f'{URL}/oauth/authorize-url',
                             data=json.dumps({'redirect_uri': 'https://attacker.example/cb'}),
                             content_type='application/json')
    assert r.status_code == 403, r.data
    assert 'redirect_uri' in r.get_json()['message']


def test_the_admin_moves_the_target(app, auth_client, stored_smtp):
    r = _patch(auth_client, {'smtp_host': 'relay2.example.com', 'smtp_port': 465,
                             'smtp_security': 'ssl'})
    assert r.status_code == 200, r.data
    with app.app_context():
        assert _row()['smtp_host'] == 'relay2.example.com'


def test_the_auditor_writes_nothing(app, auditor_client, stored_smtp):
    assert _patch(auditor_client, {'from_name': 'x'}).status_code == 403
    with app.app_context():
        assert _row() == STORED
