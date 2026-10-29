"""Follow-ups of the cross-certificate review: the issuing CA is the one whose key signed (#400)."""
import base64
import json
import uuid

from cryptography.hazmat.primitives import serialization

from models import CA, Certificate, db
from tests.fixtures.cross_pki import make_cert, new_key, pem


def _ca_row(cert, label):
    return CA(refid=f'{label}-{uuid.uuid4().hex[:8]}', descr=label, subject=cert.subject.rfc4514_string(),
              issuer=cert.issuer.rfc4514_string(), crt=base64.b64encode(pem(cert).encode()).decode())


def test_an_imported_user_certificate_is_linked_to_the_ca_whose_key_signed_it(app, auth_client, create_user):
    tag = uuid.uuid4().hex[:8]
    name = f'Same Name Root {tag}'
    old_key, new_key_ = new_key(), new_key()
    user_cert = make_cert(f'user-{tag}', new_key(), name, new_key_, ca=False, days=30)
    with app.app_context():
        old = _ca_row(make_cert(name, old_key), 'old-root')
        new = _ca_row(make_cert(name, new_key_), 'new-root')
        db.session.add_all([old, new])
        db.session.commit()
        old_id, new_refid = old.id, new.refid
        assert old_id < new.id
    user = create_user()
    r = auth_client.post(f'/api/v2/users/{user["id"]}/mtls/certificates',
                         data=json.dumps({'mode': 'import', 'pem': pem(user_cert)}),
                         content_type='application/json')
    assert r.status_code == 201, r.data
    with app.app_context():
        row = Certificate.query.filter_by(serial_number=str(user_cert.serial_number)).one()
        assert row.caref == new_refid


def test_a_revocation_held_under_any_ca_of_the_issuer_name_closes_the_pemless_fallback(app, create_user):
    from datetime import timedelta
    from models import RevokedSerial
    from models.auth_certificate import AuthCertificate
    from services.mtls_auth_service import MTLSAuthService
    from utils.datetime_utils import utc_now
    tag = uuid.uuid4().hex[:8]
    name = f'Fallback Root {tag}'
    user = create_user()
    serial = str(int(uuid.uuid4().int >> 80))
    with app.app_context():
        old = _ca_row(make_cert(name, new_key()), 'fb-old')
        new = _ca_row(make_cert(name, new_key()), 'fb-new')
        db.session.add_all([old, new])
        db.session.flush()
        subject = f'CN=user-{tag}'
        db.session.add(AuthCertificate(
            user_id=user['id'], cert_serial=serial, cert_subject=subject, cert_issuer=old.subject,
            cert_fingerprint=uuid.uuid4().hex.upper(), name=f'fb-{tag}', enabled=True,
            valid_from=utc_now() - timedelta(days=1), valid_until=utc_now() + timedelta(days=10)))
        db.session.add(RevokedSerial(caref=new.refid, serial_number=serial, valid_to=utc_now() + timedelta(days=10)))
        db.session.commit()
        got, _, err = MTLSAuthService.authenticate_certificate({'serial': serial})
        assert got is None and 'revoked' in err.lower()
