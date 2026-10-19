"""Policy rules that no evaluation read are dropped.

`required_extensions` and `san_restrictions.require_approval_for_external`
were seeded, saved and echoed back by the form, and enforced nowhere.
"""
import json
import uuid

from models import db
from models.policy import CertificatePolicy


def test_the_api_drops_them_on_save(app, auth_client):
    r = auth_client.post('/api/v2/policies', data=json.dumps({
        'name': f'dead-rules-{uuid.uuid4().hex[:8]}', 'policy_type': 'issuance', 'is_active': False,
        'rules': {'max_validity_days': 90, 'required_extensions': ['keyUsage'],
                  'san_restrictions': {'max_dns_names': 5, 'require_approval_for_external': True}},
    }), content_type='application/json')
    assert r.status_code in (200, 201), r.data
    pid = r.get_json()['data']['id']
    with app.app_context():
        rules = db.session.get(CertificatePolicy, pid).get_rules()
        assert rules == {'max_validity_days': 90, 'san_restrictions': {'max_dns_names': 5}}
        db.session.delete(db.session.get(CertificatePolicy, pid))
        db.session.commit()
