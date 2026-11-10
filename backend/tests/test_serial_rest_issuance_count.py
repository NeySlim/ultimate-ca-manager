"""POST /api/v2/certificates counts each certificate in the CA's issuance counter, as every other issuance path does."""
import json

from models import CA, db


def test_rest_issuance_counts_each_certificate(app, auth_client, create_ca):
    ca = create_ca(cn='REST issuance count CA')
    for i in range(2):
        r = auth_client.post('/api/v2/certificates', data=json.dumps(
            {'cn': f'count-{i}.example.test', 'ca_id': ca['id'], 'validity_days': 30}),
            content_type='application/json')
        assert r.status_code in (200, 201), r.data
    with app.app_context():
        assert db.session.get(CA, ca['id']).serial == 2
    assert json.loads(auth_client.get(f"/api/v2/cas/{ca['id']}").data)['data']['serial'] == 2
