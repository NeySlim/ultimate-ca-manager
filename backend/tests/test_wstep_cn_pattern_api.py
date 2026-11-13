"""The common name pattern of a template through the templates API (SQLite, and PostgreSQL with
UCM_TEST_APP_PG_URL): refused when saved for a variable unknown or of the other kind, or for a
template whose requester supplies the subject; kept by duplicate, export and import."""
import json
import uuid

import pytest

from models import db
from models.certificate_template import CertificateTemplate
from tests.fixtures.templates import delete_templates

BASE = {'key_type': 'RSA-2048', 'validity_days': 30, 'digest': 'sha256',
        'extensions_template': {'extended_key_usage': ['clientAuth']}}


@pytest.fixture
def made(app):
    names = []
    yield names
    with app.app_context():
        delete_templates([t.id for t in CertificateTemplate.query.filter(CertificateTemplate.name.in_(names))])
        db.session.commit()


def _name(made, label):
    name = f'cn-pattern-{label}-{uuid.uuid4().hex[:8]}'
    made.append(name)
    return name


def _create(auth_client, made, label, **fields):
    body = {**BASE, 'name': _name(made, label), **fields}
    return auth_client.post('/api/v2/templates', data=json.dumps(body), content_type='application/json')


def _error(r):
    body = r.get_json()
    return r.status_code, body.get('message') or body.get('error')


def test_a_pattern_round_trips_on_create_update_and_duplicate(auth_client, made):
    r = _create(auth_client, made, 'machine', template_type='web_server', subject_cn_pattern=' {hostname}-WiFi ',
                subject_cn_keep_path=True)
    assert r.status_code == 201, r.data
    data = r.get_json()['data']
    assert (data['subject_cn_pattern'], data['subject_cn_keep_path']) == ('{hostname}-WiFi', True)
    r = auth_client.put(f"/api/v2/templates/{data['id']}", data=json.dumps({'subject_cn_pattern': ''}),
                        content_type='application/json')
    assert r.get_json()['data']['subject_cn_pattern'] is None
    auth_client.put(f"/api/v2/templates/{data['id']}", data=json.dumps({'subject_cn_pattern': '{fqdn}'}),
                    content_type='application/json')
    r = auth_client.post(f"/api/v2/templates/{data['id']}/duplicate")
    copy = r.get_json()['data']
    made.append(copy['name'])
    assert (copy['subject_cn_pattern'], copy['subject_cn_keep_path']) == ('{fqdn}', True)


@pytest.mark.parametrize('fields', [
    {'template_type': 'web_server', 'subject_cn_pattern': '{hostname}-WiFi'},
    {'template_type': 'client_auth', 'ad_derived_subject': True, 'subject_cn_pattern': '{username}'},
    {'template_type': 'client_auth', 'ad_derived_subject': True, 'subject_cn_pattern': '{displayName}'},
], ids=['hostname', 'username', 'displayName'])
def test_a_simple_pattern_is_saved(auth_client, made, fields):
    """Uniqueness is checked when a certificate is issued, not when the pattern is saved."""
    r = _create(auth_client, made, 'simple', **fields)
    assert r.status_code == 201, r.data
    assert r.get_json()['data']['subject_cn_pattern'] == fields['subject_cn_pattern']


def test_a_template_without_a_pattern_keeps_none(auth_client, made):
    data = _create(auth_client, made, 'none', template_type='web_server').get_json()['data']
    assert (data['subject_cn_pattern'], data['subject_cn_keep_path']) == (None, False)


@pytest.mark.parametrize('fields,message', [
    ({'template_type': 'web_server', 'subject_cn_pattern': '{nickname}'},
     'Unknown variable {nickname} in the common name pattern'),
    ({'template_type': 'web_server', 'subject_cn_pattern': '{displayName}'},
     'Variable {displayName} is for user templates; this is a computer template'),
    ({'template_type': 'client_auth', 'ad_derived_subject': True, 'subject_cn_pattern': '{hostname}'},
     'Variable {hostname} is for computer templates; this is a user template'),
    ({'template_type': 'client_auth', 'subject_cn_pattern': '{username}'},
     'A common name pattern needs a template whose subject the CA builds: a computer template, '
     'or a user template with "Build subject from Active Directory" on'),
    ({'template_type': 'web_server', 'subject_cn_pattern': 7}, 'subject_cn_pattern must be text'),
    ({'template_type': 'web_server', 'subject_cn_keep_path': 'yes'}, 'subject_cn_keep_path must be true or false'),
], ids=['unknown', 'user-variable-on-machine', 'machine-variable-on-user', 'requester-subject', 'not-text',
        'keep-path-not-bool'])
def test_a_pattern_that_cannot_serve_is_refused_when_saved(app, auth_client, made, fields, message):
    r = _create(auth_client, made, 'refused', **fields)
    assert _error(r) == (400, message)
    with app.app_context():
        assert CertificateTemplate.query.filter_by(name=made[-1]).first() is None


@pytest.mark.parametrize('change', [{'template_type': 'client_auth'}, {'ad_derived_subject': False}],
                         ids=['type', 'subject-source'])
def test_a_change_that_invalidates_the_pattern_is_refused(app, auth_client, made, change):
    """Judged on the template the update leaves, whichever field moves."""
    fields = ({'template_type': 'web_server', 'subject_cn_pattern': '{hostname}'} if 'template_type' in change
              else {'template_type': 'client_auth', 'ad_derived_subject': True, 'subject_cn_pattern': '{username}'})
    data = _create(auth_client, made, 'change', **fields).get_json()['data']
    r = auth_client.put(f"/api/v2/templates/{data['id']}", data=json.dumps(change), content_type='application/json')
    assert r.status_code == 400
    with app.app_context():
        row = db.session.get(CertificateTemplate, data['id'])
        assert (row.template_type, row.subject_cn_pattern) == (fields['template_type'], fields['subject_cn_pattern'])


def test_export_then_import_carries_the_pattern_and_refuses_a_bad_one(app, auth_client, made):
    data = _create(auth_client, made, 'export', template_type='client_auth', ad_derived_subject=True,
                   subject_cn_pattern='{displayName}', subject_cn_keep_path=True).get_json()['data']
    exported = json.loads(auth_client.get(f"/api/v2/templates/{data['id']}/export").data)
    assert (exported['subject_cn_pattern'], exported['subject_cn_keep_path']) == ('{displayName}', True)
    good = {**exported, 'name': _name(made, 'imported')}
    bad = {**exported, 'name': _name(made, 'imported-bad'), 'subject_cn_pattern': '{fqdn}'}
    r = auth_client.post('/api/v2/templates/import', data={'json_content': json.dumps([good, bad])})
    assert r.status_code == 200, r.data
    with app.app_context():
        row = CertificateTemplate.query.filter_by(name=good['name']).one()
        assert (row.subject_cn_pattern, row.subject_cn_keep_path) == ('{displayName}', True)
        assert CertificateTemplate.query.filter_by(name=bad['name']).first() is None
    # Updating an existing template is judged the same way
    r = auth_client.post('/api/v2/templates/import', data={
        'json_content': json.dumps({**exported, 'name': good['name'], 'subject_cn_pattern': '{hostname}'}),
        'update_existing': 'true'})
    assert 'Variable {hostname} is for computer templates' in r.get_json()['message']
    with app.app_context():
        assert CertificateTemplate.query.filter_by(name=good['name']).one().subject_cn_pattern == '{displayName}'
