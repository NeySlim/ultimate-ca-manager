"""The custom_command DNS provider runs local programs: only an administrator writes one."""
import hashlib
import json
import secrets
import sys
import uuid

import pytest

from models import DnsProvider, User, db
from models.api_key import APIKey

BASE = '/api/v2/dns-providers'


def _uniq(prefix):
    return f'{prefix}-{uuid.uuid4().hex[:8]}'


def _post(client, body, headers=None):
    return client.post(BASE, data=json.dumps(body), content_type='application/json',
                       headers=headers or {})


def _patch(client, pid, body, headers=None):
    return client.patch(f'{BASE}/{pid}', data=json.dumps(body),
                        content_type='application/json', headers=headers or {})


def _command_body(command=None):
    return {'name': _uniq('cmd'), 'provider_type': 'custom_command',
            'credentials': {'create_command': command or f'{sys.executable} -c pass'}}


_USERS = ('op_dns_custom_command', 'dns_custom_command_key_owner')


@pytest.fixture(scope='module', autouse=True)
def _drop_users(app):
    yield
    with app.app_context():
        for user in User.query.filter(User.username.in_(_USERS)).all():
            APIKey.query.filter_by(user_id=user.id).delete()
            db.session.delete(user)
        db.session.commit()


@pytest.fixture(scope='module')
def operator_client(app, create_user):
    create_user(username='op_dns_custom_command', role='operator')
    client = app.test_client()
    r = client.post('/api/v2/auth/login',
                    data=json.dumps({'username': 'op_dns_custom_command',
                                     'password': 'TestPass123!'}),
                    content_type='application/json')
    assert r.status_code == 200, r.data
    return client


@pytest.fixture(scope='module')
def acme_key(app):
    """An administrator's API key scoped to the ACME permissions only."""
    username = 'dns_custom_command_key_owner'
    with app.app_context():
        owner = User.query.filter_by(username=username).first()
        if not owner:
            owner = User(username=username, email=f'{username}@test.local',
                         password_hash='!', role='admin', active=True)
            db.session.add(owner)
            db.session.commit()
        raw = f'ucm_ak_{secrets.token_urlsafe(32)}'
        db.session.add(APIKey(user_id=owner.id,
                              key_hash=hashlib.sha256(raw.encode()).hexdigest(),
                              key_prefix=raw[:12], name=_uniq('dns-acme-only'),
                              permissions=json.dumps(['read:acme', 'write:acme'])))
        db.session.commit()
    return {'X-API-Key': raw}


def _count(app, provider_type='custom_command'):
    with app.app_context():
        return DnsProvider.query.filter_by(provider_type=provider_type).count()


def _stored(app, pid):
    with app.app_context():
        db.session.expire_all()
        p = db.session.get(DnsProvider, pid)
        return p.provider_type, json.loads(p.credentials or '{}'), p.name


def _admin_created(auth_client, command=None):
    r = _post(auth_client, _command_body(command))
    assert r.status_code == 201, r.data
    return r.get_json()['data']['id']


def test_operator_cannot_create(app, operator_client):
    before = _count(app)
    r = _post(operator_client, _command_body())
    assert r.status_code == 403, r.data
    assert _count(app) == before


def test_acme_scoped_api_key_cannot_create(app, acme_key):
    before = _count(app)
    r = _post(app.test_client(), _command_body(), headers=acme_key)
    assert r.status_code == 403, r.data
    assert _count(app) == before


def test_admin_creates_and_updates(app, auth_client):
    pid = _admin_created(auth_client)
    r = _patch(auth_client, pid, {'credentials': {'create_command': f'{sys.executable} -V'}})
    assert r.status_code == 200, r.data
    assert _stored(app, pid)[1]['create_command'].endswith(' -V')


def test_operator_cannot_update(app, auth_client, operator_client):
    pid = _admin_created(auth_client)
    before = _stored(app, pid)
    r = _patch(operator_client, pid,
               {'name': _uniq('renamed'), 'credentials': {'create_command': '/bin/sh -c id'}})
    assert r.status_code == 403, r.data
    assert _stored(app, pid) == before


def test_acme_scoped_api_key_cannot_update(app, auth_client, acme_key):
    pid = _admin_created(auth_client)
    before = _stored(app, pid)
    r = _patch(app.test_client(), pid,
               {'credentials': {'create_command': '/bin/sh -c id'}}, headers=acme_key)
    assert r.status_code == 403, r.data
    assert _stored(app, pid) == before


def test_patch_never_changes_the_type(app, operator_client):
    r = _post(operator_client, {'name': _uniq('manual'), 'provider_type': 'manual'})
    assert r.status_code == 201, r.data
    pid = r.get_json()['data']['id']
    r = _patch(operator_client, pid, {'provider_type': 'custom_command',
                                      'credentials': {'create_command': '/bin/sh -c id'}})
    assert r.status_code in (200, 403), r.data
    assert _stored(app, pid)[0] == 'manual'


def test_other_types_unchanged_for_operator(app, operator_client):
    r = _post(operator_client, {'name': _uniq('manual'), 'provider_type': 'manual'})
    assert r.status_code == 201, r.data
    pid = r.get_json()['data']['id']
    r = _patch(operator_client, pid, {'name': _uniq('manual-renamed')})
    assert r.status_code == 200, r.data


def test_existing_provider_still_used_by_domain_test(app, auth_client, operator_client, tmp_path):
    marker = tmp_path / 'ran'
    script = tmp_path / 'hook.py'
    script.write_text(f'open({str(marker)!r}, "a").write("x")\n')
    pid = _admin_created(auth_client, f'{sys.executable} {script}')
    r = operator_client.post('/api/v2/acme/domains/test',
                             data=json.dumps({'domain': 'example.test', 'dns_provider_id': pid}),
                             content_type='application/json')
    assert r.status_code == 200, r.data
    assert marker.exists()
    r = operator_client.post(f'{BASE}/{pid}/test')
    assert r.status_code == 200, r.data
