"""The two CRL housekeeping flags on the general settings route.

The GET reads them as CRL generation does, the PATCH stores 'true'/'false',
and only admin:settings may change them.
"""
import json

import pytest

from models import db, SystemConfig

URL = '/api/v2/settings/general'
FLAGS = {
    'crl_auto_delete_expired_revoked': 'is_auto_delete_enabled',
    'crl_auto_purge_stale_serials': 'is_purge_stale_serials_enabled',
}


def _rows():
    db.session.expire_all()
    return {row.key: row.value for row in SystemConfig.query.all()}


def _store(key, value):
    row = SystemConfig.query.filter_by(key=key).first()
    if value is None:
        if row is not None:
            db.session.delete(row)
    elif row is None:
        db.session.add(SystemConfig(key=key, value=value))
    else:
        row.value = value
    db.session.commit()


def _patch(client, body):
    return client.patch(URL, data=json.dumps(body), content_type='application/json')


def _get(client):
    r = client.get(URL)
    assert r.status_code == 200, r.data
    return r.get_json()['data']


@pytest.fixture
def restore(app):
    """Puts back the flags and the timezone as they were."""
    keys = list(FLAGS) + ['timezone']
    with app.app_context():
        before = {k: v for k, v in _rows().items() if k in keys}
    yield
    with app.app_context():
        for key in keys:
            _store(key, before.get(key))


@pytest.fixture(scope='module')
def operator_client(app, create_user):
    create_user(username='op_crl_flags', role='operator')
    client = app.test_client()
    r = client.post('/api/v2/auth/login',
                    data=json.dumps({'username': 'op_crl_flags', 'password': 'TestPass123!'}),
                    content_type='application/json')
    assert r.status_code == 200, r.data
    return client


@pytest.mark.parametrize('key', sorted(FLAGS))
@pytest.mark.parametrize('stored,expected', [
    ('yes', True), ('on', True), ('1', True), ('TRUE', True), ('true', True),
    ('false', False), ('no', False), ('', False), (None, False),
])
def test_get_is_a_json_boolean_equal_to_the_crl_reading(
        app, auth_client, operator_client, restore, key, stored, expected):
    from services.crl.query import CRLQueryMixin
    with app.app_context():
        _store(key, stored)
        runtime = getattr(CRLQueryMixin, FLAGS[key])()
    assert runtime is expected
    assert _get(auth_client)[key] is expected
    # Read-only for an operator, but the value is still shown
    assert _get(operator_client)[key] is expected


@pytest.mark.parametrize('key', sorted(FLAGS))
def test_an_administrator_stores_true_then_false(app, auth_client, restore, key):
    for value, word in ((True, 'true'), (False, 'false')):
        r = _patch(auth_client, {key: value})
        assert r.status_code == 200, r.data
        with app.app_context():
            assert _rows()[key] == word
        assert _get(auth_client)[key] is value


@pytest.mark.parametrize('key', sorted(FLAGS))
def test_an_operator_cannot_change_a_flag(app, operator_client, restore, key):
    with app.app_context():
        _store(key, 'false')
    r = _patch(operator_client, {key: True})
    assert r.status_code == 403, r.data
    assert key in r.get_data(as_text=True)
    with app.app_context():
        assert _rows()[key] == 'false'


def test_an_operator_mixed_body_saves_the_timezone_only(app, operator_client, restore):
    with app.app_context():
        for key in FLAGS:
            _store(key, None)
    body = {key: True for key in FLAGS}
    body['timezone'] = 'Europe/Paris'
    r = _patch(operator_client, body)
    assert r.status_code == 200, r.data
    with app.app_context():
        rows = _rows()
    assert rows['timezone'] == 'Europe/Paris'
    for key in FLAGS:
        assert key not in rows
