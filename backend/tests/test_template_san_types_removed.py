"""Template "SAN types" and basic_constraints are not kept.

Neither was read by issuance: the SAN types filtered nothing and
basic_constraints was always {ca: false}. The API drops both on save.
"""
import json
import uuid

from models import CertificateTemplate, db


def test_create_and_update_drop_them(app, auth_client):
    r = auth_client.post('/api/v2/templates', data=json.dumps({
        'name': f'san-types-{uuid.uuid4().hex[:8]}', 'template_type': 'custom', 'key_type': 'RSA-2048',
        'validity_days': 30, 'digest': 'sha256',
        'extensions_template': {'key_usage': ['digitalSignature'], 'san_types': ['dns'],
                                'basic_constraints': {'ca': False}}}), content_type='application/json')
    assert r.status_code in (200, 201), r.data
    tid = r.get_json()['data']['id']
    r = auth_client.put(f'/api/v2/templates/{tid}', data=json.dumps({
        'extensions_template': {'key_usage': ['keyEncipherment'], 'san_types': ['ip']}}),
        content_type='application/json')
    assert r.status_code == 200, r.data
    with app.app_context():
        row = db.session.get(CertificateTemplate, tid)
        assert json.loads(row.extensions_template) == {'key_usage': ['keyEncipherment']}
        db.session.delete(row)
        db.session.commit()


def test_system_templates_carry_neither(app):
    with app.app_context():
        for row in CertificateTemplate.query.filter_by(is_system=True).all():
            ext = json.loads(row.extensions_template or '{}')
            assert 'san_types' not in ext and 'basic_constraints' not in ext, row.name
