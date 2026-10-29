"""mTLS subject fallbacks pick the self-signed root, and its revocations cover the cross-certificate's record (#400)."""
import uuid
from datetime import datetime, timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from models import db, CA
from models.auth_certificate import AuthCertificate
from models.revoked_serial import RevokedSerial
from tests.test_backfill_cross_dupes import _cert, _row


@pytest.fixture
def twin_records(app):
    """A cross-certificate record stored BEFORE the self-signed root of the same key."""
    key_a, key_b = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
    tag = uuid.uuid4().hex[:6]
    name_a, name_b = f'MTLS Root A {tag}', f'MTLS Root B {tag}'
    with app.app_context():
        root_a = db.session.get(CA, _row(_cert(key_a, name_a), key_a))
        cross = db.session.get(CA, _row(_cert(key_b, name_b, key_a, name_a), caref=root_a.refid))
        root_b = db.session.get(CA, _row(_cert(key_b, name_b), key_b))
        assert cross.id < root_b.id
        yield {'key_b': key_b, 'cn_b': name_b, 'name_b': f'CN={name_b}', 'cross': cross.refid, 'root': root_b.refid}


@pytest.mark.parametrize('revoked_under', ['root', 'cross'])
def test_legacy_enrolment_is_revoked_whichever_record_carries_the_revocation(app, twin_records, revoked_under):
    from services.mtls_auth_service import MTLSAuthService
    serial = str(uuid.uuid4().int % 10**12)
    db.session.add_all([
        AuthCertificate(user_id=1, cert_serial=serial, cert_subject='CN=legacy',
                        cert_issuer=twin_records['name_b'], cert_fingerprint='', name='legacy', enabled=True),
        RevokedSerial(caref=twin_records[revoked_under], serial_number=serial,
                      valid_to=datetime.utcnow() + timedelta(days=30)),
    ])
    db.session.commit()
    try:
        user, _, err = MTLSAuthService.authenticate_certificate({'serial': serial, 'fingerprint': ''})
        assert user is None and err == 'Certificate has been revoked'
    finally:
        AuthCertificate.query.filter_by(cert_serial=serial).delete()
        RevokedSerial.query.filter_by(serial_number=serial).delete()
        db.session.commit()


def test_imported_enrolment_is_filed_under_the_self_signed_root(app, auth_client, twin_records):
    from cryptography.hazmat.primitives import serialization
    from models import Certificate
    from tests.fixtures.cross_pki import make_cert, new_key
    leaf = make_cert(f'user-{uuid.uuid4().hex[:6]}', new_key(), twin_records['cn_b'], twin_records['key_b'],
                     ca=False, days=30)
    pem = leaf.public_bytes(serialization.Encoding.PEM).decode()
    r = auth_client.post('/api/v2/users/1/mtls/certificates', json={'mode': 'import', 'pem': pem, 'name': 'twin'})
    assert r.status_code in (200, 201), r.data
    row = Certificate.query.filter_by(serial_number=str(leaf.serial_number)).one()
    assert row.caref == twin_records['root']
    AuthCertificate.query.filter_by(cert_serial=str(leaf.serial_number)).delete()
    db.session.delete(row)
    db.session.commit()
