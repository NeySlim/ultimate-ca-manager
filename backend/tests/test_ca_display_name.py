"""Issue #459: a CA's display name and free-text description change after creation through
PATCH /api/v2/cas/<id>, the certificate untouched, each change audited with both values."""
import json

import pytest

from models import AuditLog, CA, SystemConfig, db
from tests.fresh_app import fresh_app_fixtures

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()


def _patch(auth_client, ca_id, **body):
    return auth_client.patch(f'/api/v2/cas/{ca_id}', data=json.dumps(body), content_type='application/json')


def _row(app, ca_id):
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        return ca.descr, ca.description, ca.crt


def _audits(app, ca_id):
    with app.app_context():
        return [a.details for a in AuditLog.query.filter_by(action='ca_updated', resource_id=str(ca_id)).order_by(AuditLog.id)]


def test_the_name_changes_trimmed_and_the_certificate_stays(app, auth_client, create_ca):
    ca = create_ca(cn='Label CN one')
    _name, _descr, crt = _row(app, ca['id'])
    r = _patch(auth_client, ca['id'], name='  Corporate Root  ')
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['data']['name'] == 'Corporate Root'
    assert _row(app, ca['id']) == ('Corporate Root', None, crt)
    assert r.get_json()['data']['common_name'] == 'Label CN one'


@pytest.mark.parametrize('value', ['', '   ', None, 42, ['x'], 'n' * 256, 'tab\tname'],
                         ids=['empty', 'blank', 'null', 'number', 'list', 'too-long', 'control'])
def test_an_unusable_name_is_refused_and_nothing_changes(app, auth_client, create_ca, value):
    ca = create_ca(cn=f'Label refused {type(value).__name__} {len(str(value))}')
    r = _patch(auth_client, ca['id'], name=value, description='kept out')
    assert r.status_code == 400, r.get_json()
    assert 'name' in r.get_json()['message']
    assert _row(app, ca['id'])[:2] == (ca['descr'], None)


def test_the_description_is_set_kept_with_line_breaks_and_cleared(app, auth_client, create_ca):
    ca = create_ca(cn='Label description CA')
    text = 'Issues the VPN gateways\n\tOwner: PKI team'
    r = _patch(auth_client, ca['id'], description=text)
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['data']['description'] == text
    assert auth_client.get(f"/api/v2/cas/{ca['id']}").get_json()['data']['description'] == text
    for empty in ('', None):
        _patch(auth_client, ca['id'], description=text)
        r = _patch(auth_client, ca['id'], description=empty)
        assert r.status_code == 200 and r.get_json()['data']['description'] == ''
        assert _row(app, ca['id'])[1] is None


@pytest.mark.parametrize('value', [7, {'a': 1}, 'd' * 1001, 'bell\x07'],
                         ids=['number', 'object', 'too-long', 'control'])
def test_an_unusable_description_is_refused_and_nothing_changes(app, auth_client, create_ca, value):
    ca = create_ca(cn=f'Label bad description {type(value).__name__} {len(str(value))}')
    r = _patch(auth_client, ca['id'], name='Must not be applied', description=value)
    assert r.status_code == 400, r.get_json()
    assert 'description' in r.get_json()['message']
    assert _row(app, ca['id'])[:2] == (ca['descr'], None)


def test_the_audit_names_the_old_and_the_new_values(app, auth_client, create_ca):
    ca = create_ca(cn='Label audited CA')
    assert _patch(auth_client, ca['id'], name='Audited Root', description='First').status_code == 200
    assert _patch(auth_client, ca['id'], description='Second').status_code == 200
    details = _audits(app, ca['id'])
    assert any('name "Label audited CA" -> "Audited Root"' in d and 'description "" -> "First"' in d
               for d in details), details
    assert any('description "First" -> "Second"' in d for d in details), details
    # The same name again changes nothing and logs no rename
    _patch(auth_client, ca['id'], name='Audited Root')
    assert sum('name "' in d for d in _audits(app, ca['id'])) == 1


def test_the_renamed_ca_is_shown_by_its_new_name_elsewhere(app, auth_client, create_ca):
    ca = create_ca(cn='Label shown CA')
    with app.app_context():
        db.session.add(SystemConfig(key='est_ca_refid', value=ca['refid']))
        db.session.commit()
    try:
        assert _patch(auth_client, ca['id'], name='Shown Everywhere').status_code == 200
        listed = auth_client.get('/api/v2/cas?search=Shown').get_json()['data']
        assert [c['name'] for c in listed if c['id'] == ca['id']] == ['Shown Everywhere']
        assert auth_client.get('/api/v2/est/config').get_json()['data']['ca_name'] == 'Shown Everywhere'
    finally:
        with app.app_context():
            SystemConfig.query.filter_by(key='est_ca_refid').delete()
            db.session.commit()
