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


def _custom_template(auth_client, name, **extra):
    body = {'name': name, 'template_type': 'web_server', 'key_type': 'RSA-2048', 'validity_days': 30,
            'digest': 'sha256', **extra}
    r = auth_client.post('/api/v2/templates', data=json.dumps(body), content_type='application/json')
    assert r.status_code in (200, 201), r.get_json()
    return r.get_json()['data']


def test_deactivating_the_only_pinned_template_does_not_widen_a_ca(app, auth_client, create_ca):
    """A CA pinned to one template offers nothing over XCEP/WSTEP once it is off, not every template."""
    from models import CA, CATemplatePin
    from services.wstep import wstep_service
    ca = create_ca(cn='Pinned deactivation CA')
    tpl = _custom_template(auth_client, 'Pinned only template')
    with app.app_context():
        db.session.add(CATemplatePin(ca_id=ca['id'], template_id=tpl['id']))
        db.session.commit()
        assert [t.id for t in wstep_service._ca_templates(db.session.get(CA, ca['id']))] == [tpl['id']]
    assert _put(auth_client, tpl['id'], {'is_active': False}).status_code == 200
    try:
        with app.app_context():
            assert wstep_service._ca_templates(db.session.get(CA, ca['id'])) == []
    finally:
        with app.app_context():
            CATemplatePin.query.filter_by(ca_id=ca['id']).delete()
            db.session.commit()


def test_a_custom_template_takes_a_boolean_only(app, auth_client):
    tpl = _custom_template(auth_client, 'Strict active template')
    r = _put(auth_client, tpl['id'], {'is_active': 'false'})
    assert r.status_code == 400
    assert r.get_json()['message'] == 'is_active must be true or false'
    with app.app_context():
        assert db.session.get(CertificateTemplate, tpl['id']).is_active is True


def test_a_copy_of_a_deactivated_template_is_active(app, auth_client, system_template):
    assert _put(auth_client, system_template['id'], {'is_active': False}).status_code == 200
    r = auth_client.post(f"/api/v2/templates/{system_template['id']}/duplicate")
    assert r.status_code in (200, 201), r.get_json()
    copy = r.get_json()['data']
    assert (copy['is_system'], copy['is_active']) == (False, True)
    auth_client.delete(f"/api/v2/templates/{copy['id']}")
