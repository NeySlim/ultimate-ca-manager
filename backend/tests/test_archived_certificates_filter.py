"""Archived rows (superseded by a protocol re-enrolment) are visible as such:
the list exposes the flag and offers a status filter for them."""
from models import CA, Certificate, db


def _cert(app, ca_id, cn, archived=False):
    from services.cert_service import CertificateService
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        row = CertificateService.create_certificate(
            descr=cn, caref=ca.refid, dn={'CN': cn}, cert_type='server_cert',
            key_type='2048', validity_days=30, username='admin')
        row.archived = archived
        db.session.commit()
        return row.id


def test_archived_rows_are_flagged_and_filterable(app, auth_client, create_ca):
    ca = create_ca(cn='Archived filter CA')
    live_id = _cert(app, ca['id'], 'live.example.test')
    old_id = _cert(app, ca['id'], 'old.example.test', archived=True)
    try:
        r = auth_client.get(f'/api/v2/certificates?status=archived&ca_id={ca["id"]}&per_page=100')
        assert r.status_code == 200
        rows = r.get_json()['data']
        assert [c['id'] for c in rows] == [old_id]
        assert rows[0]['archived'] is True
        r = auth_client.get(f'/api/v2/certificates?ca_id={ca["id"]}&per_page=100')
        ids = {c['id']: c['archived'] for c in r.get_json()['data']}
        assert ids[live_id] is False and ids[old_id] is True
    finally:
        with app.app_context():
            for rid in (live_id, old_id):
                row = db.session.get(Certificate, rid)
                if row:
                    db.session.delete(row)
            db.session.commit()
