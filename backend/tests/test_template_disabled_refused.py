"""A disabled template can no longer issue.

`is_active` was honoured by XCEP/WSTEP only: the issue form, CSR signing,
approvals and the SCEP/ACME profile bindings took a disabled template as
if it were active.
"""
import json
import uuid

import pytest

from models import CertificateTemplate, SystemConfig, db
from services.acme import profiles as acme_profiles
from tests.test_csr_sign_extra_names import _csr, _upload

CONTENT_JSON = 'application/json'


@pytest.fixture
def disabled_template(app):
    with app.app_context():
        tpl = CertificateTemplate(
            name=f'disabled-{uuid.uuid4().hex[:8]}', template_type='custom', key_type='RSA-2048',
            validity_days=30, digest='sha256', dn_template=json.dumps({'CN': '{cn}'}),
            extensions_template=json.dumps({'key_usage': ['digitalSignature'],
                                            'extended_key_usage': ['serverAuth']}),
            is_active=False)
        db.session.add(tpl)
        db.session.commit()
        tid = tpl.id
    yield tid
    with app.app_context():
        row = db.session.get(CertificateTemplate, tid)
        if row is not None:
            db.session.delete(row)
            db.session.commit()


def test_issue_form_refuses_it(auth_client, create_ca, disabled_template):
    ca = create_ca(cn='Disabled tpl issue CA')
    r = auth_client.post('/api/v2/certificates', data=json.dumps(
        {'cn': 'disabled.tpl.test', 'ca_id': ca['id'], 'template_id': disabled_template}),
        content_type=CONTENT_JSON)
    assert r.status_code == 400
    assert 'disabled' in r.get_json()['message']


def test_csr_signing_refuses_it(auth_client, create_ca, disabled_template):
    ca = create_ca(cn='Disabled tpl CSR CA')
    csr_id = _upload(auth_client, _csr('csr.disabled.test'))
    r = auth_client.post(f'/api/v2/csrs/{csr_id}/sign', json={
        'ca_id': ca['id'], 'validity_days': 30, 'template_id': disabled_template})
    assert r.status_code == 400
    r = auth_client.post('/api/v2/csrs/bulk/sign', json={
        'ids': [csr_id], 'ca_id': ca['id'], 'validity_days': 30, 'template_id': disabled_template})
    assert r.status_code == 400


def test_scep_profile_cannot_bind_it(auth_client, create_ca, disabled_template):
    ca = create_ca(cn='Disabled tpl SCEP CA')
    r = auth_client.post('/api/v2/scep/profiles', data=json.dumps({
        'name': f'disabled-{uuid.uuid4().hex[:6]}', 'ca_id': ca['id'], 'template_id': disabled_template}),
        content_type=CONTENT_JSON)
    assert r.status_code == 400
    assert 'disabled' in r.get_json()['message']


def test_acme_profile_cannot_newly_bind_it(app, disabled_template):
    with app.app_context():
        ok, err = acme_profiles.validate_config({'tls': {'template_id': disabled_template}})
        assert not ok and 'disabled' in err
        # A binding made while the template was active is kept on later saves.
        row = SystemConfig(key=acme_profiles.CONFIG_KEY,
                           value=json.dumps({'tls': {'template_id': disabled_template}}))
        db.session.add(row)
        db.session.commit()
        try:
            assert acme_profiles.validate_config({'tls': {'template_id': disabled_template}}) == (True, None)
        finally:
            db.session.delete(row)
            db.session.commit()


def test_approval_refuses_it(app, create_ca, disabled_template):
    from api.v2.policies import _issue_approved_certificate
    from models import ApprovalRequest
    from tests.test_approval_template_issuance import _mk_approval_id, _requester_id
    ca = create_ca(cn='Disabled tpl approval CA')
    approval_id = _mk_approval_id(app, _requester_id(app), {
        'cn': 'approval.disabled.test', 'ca_id': ca['id'], 'template_id': disabled_template})
    with app.app_context():
        with pytest.raises(ValueError, match='disabled'):
            _issue_approved_certificate(db.session.get(ApprovalRequest, approval_id))


def test_scep_profile_keeps_a_binding_made_while_active(app, auth_client, create_ca, disabled_template):
    """The form sends template_id back on every save: an existing binding is not a new one."""
    ca = create_ca(cn='Disabled tpl SCEP keep CA')
    with app.app_context():
        db.session.get(CertificateTemplate, disabled_template).is_active = True
        db.session.commit()
    r = auth_client.post('/api/v2/scep/profiles', json={
        'name': f'keep-{uuid.uuid4().hex[:6]}', 'ca_id': ca['id'], 'template_id': disabled_template})
    assert r.status_code in (200, 201), r.get_json()
    profile_id = r.get_json()['data']['id']
    with app.app_context():
        db.session.get(CertificateTemplate, disabled_template).is_active = False
        db.session.commit()
    try:
        r = auth_client.put(f'/api/v2/scep/profiles/{profile_id}', json={
            'name': f'kept-{uuid.uuid4().hex[:6]}', 'template_id': disabled_template})
        assert r.status_code == 200, r.get_json()
    finally:
        auth_client.delete(f'/api/v2/scep/profiles/{profile_id}')


def test_acme_profile_rename_keeps_the_binding_but_a_copy_is_new(app, disabled_template):
    with app.app_context():
        row = SystemConfig(key=acme_profiles.CONFIG_KEY,
                           value=json.dumps({'tls': {'template_id': disabled_template}}))
        db.session.add(row)
        db.session.commit()
        try:
            renamed = {'server': {'template_id': disabled_template}}
            assert acme_profiles.validate_config(renamed) == (True, None)
            copied = {'tls': {'template_id': disabled_template},
                      'server': {'template_id': disabled_template}}
            ok, err = acme_profiles.validate_config(copied)
            assert not ok and 'disabled' in err
        finally:
            db.session.delete(row)
            db.session.commit()


@pytest.mark.parametrize('update_existing', [False, True])
@pytest.mark.parametrize('value', ['false', 0, None, []])
def test_import_refuses_an_is_active_that_is_not_a_boolean(app, auth_client, update_existing, value):
    name = f'import-active-{uuid.uuid4().hex[:8]}'
    if update_existing:
        with app.app_context():
            db.session.add(CertificateTemplate(name=name, template_type='custom', key_type='RSA-2048',
                                               validity_days=30, digest='sha256', is_active=True,
                                               dn_template='{}', extensions_template='{}'))
            db.session.commit()
    try:
        r = auth_client.post('/api/v2/templates/import', data={
            'json_content': json.dumps([{'name': name, 'template_type': 'custom', 'is_active': value}]),
            'update_existing': str(update_existing).lower()}, content_type='multipart/form-data')
        assert r.status_code in (200, 201), r.data
        assert any('is_active' in entry for entry in r.get_json()['data']['skipped_items'])
        with app.app_context():
            row = CertificateTemplate.query.filter_by(name=name).first()
            assert (row is not None and row.is_active is True) if update_existing else row is None
    finally:
        with app.app_context():
            CertificateTemplate.query.filter_by(name=name).delete()
            db.session.commit()


def test_import_keeps_a_boolean_is_active(app, auth_client):
    name = f'import-active-{uuid.uuid4().hex[:8]}'
    try:
        r = auth_client.post('/api/v2/templates/import', data={
            'json_content': json.dumps([{'name': name, 'template_type': 'custom', 'is_active': False}])},
            content_type='multipart/form-data')
        assert r.status_code in (200, 201), r.data
        with app.app_context():
            assert CertificateTemplate.query.filter_by(name=name).one().is_active is False
    finally:
        with app.app_context():
            CertificateTemplate.query.filter_by(name=name).delete()
            db.session.commit()
