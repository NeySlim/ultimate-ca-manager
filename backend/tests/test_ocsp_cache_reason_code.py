"""The OCSP cache records the revocation reason as its CRLReason code.

The column is an integer and the responder stored the reason's name
('keyCompromise'): SQLite kept the text, PostgreSQL refused the insert, so a
revoked certificate with a reason was never cached there.
"""
from sqlalchemy import text

from models import OCSPResponse, db
from tests.test_ca_revocation import CAS, _intermediate, _ocsp_status, _post, _serial_int


def test_the_cached_reason_is_the_crlreason_code(app, auth_client, create_ca):
    with app.app_context():
        root = create_ca(cn='OCSP reason code Root')
        sub = _intermediate(auth_client, root, 'OCSP reason code Sub')
        serial = _serial_int(sub['id'])
        r = _post(auth_client, f'{CAS}/{sub["id"]}/revoke', {'reason': 'keyCompromise'})
        assert r.status_code == 200, r.data
        status, _resp = _ocsp_status(root['id'], serial)
        assert status == 'revoked'
        row = OCSPResponse.query.filter(OCSPResponse.ca_id == root['id'],
                                        OCSPResponse.cert_serial.like(f'{serial:x}%')).first()
        assert row is not None
        stored = db.session.execute(text('SELECT revocation_reason FROM ocsp_responses WHERE id = :i'),
                                    {'i': row.id}).scalar()
        assert stored == 1 and isinstance(stored, int)
