"""A CA has no "active" flag to set.

PATCH /api/v2/cas/<id> took `is_active`, set an attribute with no column
and logged it to the audit trail as a change: nothing was stored.
"""
import json

from models import AuditLog


def test_is_active_is_not_reported_as_a_change(app, auth_client, create_ca):
    ca = create_ca(cn='Flagless CA')
    r = auth_client.patch(f"/api/v2/cas/{ca['id']}", data=json.dumps({'is_active': True}),
                          content_type='application/json')
    assert r.status_code == 200, r.data
    with app.app_context():
        details = [r.details or '' for r in AuditLog.query.all()]
        assert not any('is_active' in d for d in details)
