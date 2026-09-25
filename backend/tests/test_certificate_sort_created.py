"""The certificate list sorts by the date a certificate reached UCM (#368),
not by the start of its validity, which an imported certificate has long past."""
import uuid
from datetime import datetime, timedelta

from models import db, Certificate


def _listed(client, prefix, order):
    response = client.get(
        f'/api/v2/certificates?search={prefix}&sort_by=created_at'
        f'&sort_order={order}&per_page=50')
    assert response.status_code == 200, response.data
    return [row['id'] for row in response.get_json()['data']]


def test_the_list_sorts_by_creation_date(app, auth_client, create_cert):
    prefix = f'sortcreated-{uuid.uuid4().hex[:8]}'
    # Names in the reverse of their creation order, so a sort by name fails
    ids = [create_cert(cn=f'{prefix}-{name}.example.com')['id'] for name in 'cba']
    start = datetime(2026, 1, 1)
    with app.app_context():
        for offset, cert_id in enumerate(ids):
            cert = db.session.get(Certificate, cert_id)
            cert.created_at = start + timedelta(days=offset)
            # A validity that disagrees with the creation date
            cert.valid_from = start - timedelta(days=offset)
        db.session.commit()

    assert _listed(auth_client, prefix, 'asc') == ids
    assert _listed(auth_client, prefix, 'desc') == ids[::-1]
