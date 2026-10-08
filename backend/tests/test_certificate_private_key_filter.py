"""The certificate picker asks for certificates holding a private key: the
server filters, so pagination and the total count only those."""
from models import CA, Certificate, db


def _cert(app, ca_id, cn, keep_key=True):
    from services.cert_service import CertificateService
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        row = CertificateService.create_certificate(
            descr=cn, caref=ca.refid, dn={'CN': cn}, cert_type='server_cert',
            key_type='2048', validity_days=30, username='admin')
        if not keep_key:
            row.prv = None
        db.session.commit()
        return row.id


def test_has_private_key_filters_rows_and_total(app, auth_client, create_ca):
    ca = create_ca(cn='Private key filter CA')
    keyed = _cert(app, ca['id'], 'keyed.example.test')
    keyless = _cert(app, ca['id'], 'keyless.example.test', keep_key=False)
    try:
        r = auth_client.get(f'/api/v2/certificates?has_private_key=true&ca_id={ca["id"]}&per_page=100')
        assert r.status_code == 200
        body = r.get_json()
        assert [c['id'] for c in body['data']] == [keyed]
        assert body['meta']['total'] == 1
        r = auth_client.get(f'/api/v2/certificates?ca_id={ca["id"]}&per_page=100')
        assert {c['id'] for c in r.get_json()['data']} == {keyed, keyless}
    finally:
        with app.app_context():
            for rid in (keyed, keyless):
                row = db.session.get(Certificate, rid)
                if row:
                    db.session.delete(row)
            db.session.commit()
