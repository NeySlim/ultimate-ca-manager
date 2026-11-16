"""PUT /policies/{id}: a field absent from the body is kept; ``rules``, when
sent, replaces the rules as a whole (keys left out are removed)."""
import json
import uuid

from models import db
from models.policy import CertificatePolicy
from tests.conftest import get_json

CONTENT_JSON = 'application/json'


def _create(auth_client, rules):
    r = auth_client.post('/api/v2/policies', data=json.dumps({
        'name': f'partial-{uuid.uuid4().hex[:8]}', 'is_active': False, 'rules': rules}),
        content_type=CONTENT_JSON)
    assert r.status_code in (200, 201), r.data
    return get_json(r)['data']['id']


def _rules(app, policy_id):
    with app.app_context():
        return db.session.get(CertificatePolicy, policy_id).get_rules()


def _drop(app, policy_id):
    with app.app_context():
        db.session.delete(db.session.get(CertificatePolicy, policy_id))
        db.session.commit()


def test_a_put_without_rules_keeps_them(app, auth_client):
    pid = _create(auth_client, {'allowed_signature_schemes': ['ml_dsa'], 'allowed_digests': ['sha384']})
    try:
        r = auth_client.put(f'/api/v2/policies/{pid}', data=json.dumps({'description': 'x'}),
                            content_type=CONTENT_JSON)
        assert r.status_code == 200, r.data
        assert _rules(app, pid) == {'allowed_signature_schemes': ['ml_dsa'], 'allowed_digests': ['sha384']}
    finally:
        _drop(app, pid)


def test_a_put_with_rules_replaces_them_whole(app, auth_client):
    pid = _create(auth_client, {'allowed_signature_schemes': ['ml_dsa'], 'allowed_digests': ['sha384']})
    try:
        r = auth_client.put(f'/api/v2/policies/{pid}', data=json.dumps({'rules': {'allowed_digests': ['sha512']}}),
                            content_type=CONTENT_JSON)
        assert r.status_code == 200, r.data
        assert _rules(app, pid) == {'allowed_digests': ['sha512']}
    finally:
        _drop(app, pid)
