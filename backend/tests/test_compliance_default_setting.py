"""Global default compliance profile (compliance_profile_default) in the general settings."""
import json

import pytest

import compliance_profiles
from models import AuditLog, SystemConfig, db

URL = '/api/v2/settings/general'


def _patch(client, body):
    return client.patch(URL, data=json.dumps(body), content_type='application/json')


def _stored(app):
    with app.app_context():
        db.session.expire_all()
        row = SystemConfig.query.filter_by(key=compliance_profiles.DEFAULT_SETTING).first()
        return row.value if row else None


@pytest.fixture(autouse=True)
def clean_default(app):
    def wipe():
        with app.app_context():
            SystemConfig.query.filter_by(key=compliance_profiles.DEFAULT_SETTING).delete()
            db.session.commit()
    wipe()
    yield
    wipe()


@pytest.fixture(scope='module')
def operator_client(app, create_user):
    create_user(username='op_compliance_default', role='operator')
    client = app.test_client()
    r = client.post('/api/v2/auth/login',
                    data=json.dumps({'username': 'op_compliance_default', 'password': 'TestPass123!'}),
                    content_type='application/json')
    assert r.status_code == 200, r.data
    return client


def test_unset_default_reads_empty(auth_client):
    assert auth_client.get(URL).get_json()['data']['compliance_profile_default'] == ''


@pytest.mark.parametrize('name', compliance_profiles.PROFILE_NAMES)
def test_a_listed_profile_is_stored_and_read_back(app, auth_client, name):
    assert _patch(auth_client, {'compliance_profile_default': name}).status_code == 200
    assert _stored(app) == name
    assert auth_client.get(URL).get_json()['data']['compliance_profile_default'] == name
    with app.app_context():
        assert compliance_profiles.default_profile() == name


def test_value_is_normalised(app, auth_client):
    assert _patch(auth_client, {'compliance_profile_default': ' BSI '}).status_code == 200
    assert _stored(app) == 'bsi'


def test_blank_clears_the_default(app, auth_client):
    _patch(auth_client, {'compliance_profile_default': 'anssi'})
    assert _patch(auth_client, {'compliance_profile_default': ''}).status_code == 200
    assert auth_client.get(URL).get_json()['data']['compliance_profile_default'] == ''
    with app.app_context():
        assert compliance_profiles.default_profile() is None


@pytest.mark.parametrize('bad', ['etsi', 'nist', 42, ['bsi']])
def test_an_unlisted_profile_is_refused(app, auth_client, bad):
    r = _patch(auth_client, {'compliance_profile_default': bad})
    assert r.status_code == 400
    assert 'compliance_profile_default' in r.get_json()['message']
    assert _stored(app) is None


def test_change_is_audited(app, auth_client):
    _patch(auth_client, {'compliance_profile_default': 'eu-acm'})
    with app.app_context():
        entry = AuditLog.query.filter_by(action='compliance_profile_default_update') \
            .order_by(AuditLog.id.desc()).first()
        assert entry is not None and 'eu-acm' in entry.details


def test_an_unchanged_value_is_not_audited(app, auth_client):
    _patch(auth_client, {'compliance_profile_default': 'bsi'})
    with app.app_context():
        before = AuditLog.query.filter_by(action='compliance_profile_default_update').count()
    _patch(auth_client, {'compliance_profile_default': 'bsi'})
    with app.app_context():
        assert AuditLog.query.filter_by(action='compliance_profile_default_update').count() == before


def test_write_settings_alone_cannot_set_it(app, operator_client):
    r = _patch(operator_client, {'compliance_profile_default': 'bsi'})
    assert r.status_code == 403
    assert _stored(app) is None
