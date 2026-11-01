"""A system template can be switched off and on (#430 follow-up), and nothing
else: its definition stays UCM's to update, a copy is edited instead."""
import json

import pytest

from models import AuditLog, db
from models.certificate_template import CertificateTemplate


def _put(auth_client, template_id, body):
    return auth_client.put(f'/api/v2/templates/{template_id}', data=json.dumps(body),
                           content_type='application/json')


@pytest.fixture
def system_template(app, auth_client):
    data = auth_client.get('/api/v2/templates').get_json()['data']
    template = next(t for t in data if t['is_system'] and t['is_active'])
    yield template
    with app.app_context():
        row = db.session.get(CertificateTemplate, template['id'])
        row.is_active = True
        db.session.commit()


def test_a_system_template_is_deactivated_and_reactivated(app, auth_client, system_template):
    r = _put(auth_client, system_template['id'], {'is_active': False})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['data']['is_active'] is False
    r = _put(auth_client, system_template['id'], {'is_active': True})
    assert r.get_json()['data']['is_active'] is True
    with app.app_context():
        details = [a.details for a in AuditLog.query.filter_by(
            action='template_update', resource_id=str(system_template['id']))]
    assert f"Deactivated template: {system_template['name']}" in details
    assert f"Activated template: {system_template['name']}" in details


@pytest.mark.parametrize('body', [
    {'is_active': False, 'validity_days': 30},
    {'validity_days': 30},
    {'is_active': 'false'},
    {'description': 'mine now'},
])
def test_anything_else_on_a_system_template_is_refused(app, auth_client, system_template, body):
    r = _put(auth_client, system_template['id'], body)
    assert r.status_code == 403
    assert r.get_json()['message'] == 'Cannot modify system templates; duplicate one to change it'
    with app.app_context():
        row = db.session.get(CertificateTemplate, system_template['id'])
        assert (row.is_active, row.validity_days, row.description) == (
            True, system_template['validity_days'], system_template['description'])


def test_a_viewer_cannot_deactivate_one(app, viewer_client, system_template):
    r = _put(viewer_client, system_template['id'], {'is_active': False})
    assert r.status_code == 403
    with app.app_context():
        assert db.session.get(CertificateTemplate, system_template['id']).is_active is True
