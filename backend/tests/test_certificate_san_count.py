"""The certificate listing counts the SANs the picker shows (#365 follow-up)."""
import json


def _listed(auth_client, cn):
    r = auth_client.get(f'/api/v2/certificates?search={cn}')
    assert r.status_code == 200
    rows = [c for c in json.loads(r.data)['data'] if c['common_name'] == cn]
    assert len(rows) == 1
    return rows[0]


def test_listing_counts_every_san(app, auth_client, create_cert):
    cert = create_cert(cn='san-count.example.com')
    with app.app_context():
        from models import Certificate, db
        row = db.session.get(Certificate, cert['id'])
        row.san_dns = json.dumps(['san-count.example.com', 'alt.example.com'])
        row.san_ip = json.dumps(['192.0.2.10'])
        row.san_email = json.dumps(['ops@example.com'])
        row.san_uri = json.dumps(['https://example.com/id'])
        row.san_upn = json.dumps(['svc@corp.example.com'])
        db.session.commit()

    listed = _listed(auth_client, 'san-count.example.com')
    assert listed['san_count'] == 6
    assert listed['san_combined'] == (
        'DNS:san-count.example.com, DNS:alt.example.com, IP:192.0.2.10, '
        'Email:ops@example.com, URI:https://example.com/id, UPN:svc@corp.example.com'
    )


def test_listing_counts_zero_without_san(app, auth_client, create_cert):
    cert = create_cert(cn='no-san.example.com')
    with app.app_context():
        from models import Certificate, db
        row = db.session.get(Certificate, cert['id'])
        row.san_dns = row.san_ip = row.san_email = row.san_uri = row.san_upn = None
        db.session.commit()

    assert _listed(auth_client, 'no-san.example.com')['san_count'] == 0
