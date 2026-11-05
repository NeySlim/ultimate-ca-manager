"""An mTLS enrolment is identified by (issuer, serial): two CAs may issue the same serial (RFC 5280 §4.1.2.2)."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from sqlalchemy.exc import IntegrityError

from models import db
from models.auth_certificate import AuthCertificate
from services.certificate_parser import CertificateParser
from services.mtls_auth_service import MTLSAuthService

SUBJECT = 'serial-per-issuer client'


def _leaf(issuer_cn, serial, ca_key=None):
    ca_key, key = ca_key or ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, SUBJECT)]))
            .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_cn)]))
            .public_key(key.public_key()).serial_number(serial)
            .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=30))
            .sign(ca_key, hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.PEM).decode()


@pytest.fixture
def same_serial(app):
    """Two CAs of this server, and a certificate of each bearing the same serial."""
    from models import CA, Certificate
    from tests.test_backfill_cross_dupes import _cert, _row
    tag = uuid.uuid4().hex[:8]
    serial = uuid.uuid4().int % 10**15
    pems, ca_ids = [], []
    with app.app_context():
        for name in (f'Issuer A {tag}', f'Issuer B {tag}'):
            key = ec.generate_private_key(ec.SECP256R1())
            ca_ids.append(_row(_cert(key, name), key))
            pems.append(_leaf(name, serial, key))
    yield serial, pems[0], pems[1]
    with app.app_context():
        db.session.rollback()
        AuthCertificate.query.filter(AuthCertificate.cert_subject == f'CN={SUBJECT}').delete()
        Certificate.query.filter(Certificate.subject == f'CN={SUBJECT}').delete()
        CA.query.filter(CA.id.in_(ca_ids)).delete()
        db.session.commit()


def _import(client, pem):
    return client.post('/api/v2/users/1/mtls/certificates', json={'mode': 'import', 'pem': pem})


def _info(pem):
    return CertificateParser.extract_certificate_info(CertificateParser.parse_pem_certificate(pem))


def _enrolments(app):
    with app.app_context():
        return AuthCertificate.query.filter(AuthCertificate.cert_subject == f'CN={SUBJECT}').count()


def test_two_issuers_may_enrol_the_same_serial(app, auth_client, same_serial):
    _serial, pem_a, pem_b = same_serial
    assert _import(auth_client, pem_a).status_code == 201
    r = _import(auth_client, pem_b)
    assert r.status_code == 201, r.get_json()
    assert _enrolments(app) == 2


def test_enroll_import_takes_the_other_issuers_certificate(app, auth_client, same_serial):
    _serial, pem_a, pem_b = same_serial
    for pem in (pem_a, pem_b):
        r = auth_client.post('/api/v2/mtls/enroll-import', json={'pem': pem})
        assert r.status_code == 201, r.get_json()
    assert _enrolments(app) == 2


def test_the_other_issuers_certificate_stays_available_and_assignable(app, auth_client, same_serial):
    import base64
    from models import Certificate
    serial, pem_a, pem_b = same_serial
    assert _import(auth_client, pem_a).status_code == 201
    with app.app_context():
        info = _info(pem_b)
        row = Certificate(refid=str(uuid.uuid4()), descr='other issuer', cert_type='usr_cert',
                          crt=base64.b64encode(pem_b.encode()).decode(), subject=info['subject_dn'],
                          issuer=info['issuer_dn'], serial_number=str(serial), created_by='admin')
        db.session.add(row)
        db.session.commit()
        row_id = row.id
    with app.app_context():
        enrolled_id = Certificate.query.filter(Certificate.subject == f'CN={SUBJECT}',
                                               Certificate.id != row_id).one().id
    listed = [c['id'] for c in auth_client.get('/api/v2/mtls/available-certificates').get_json()['data']]
    assert row_id in listed and enrolled_id not in listed
    r = auth_client.post('/api/v2/mtls/assign', json={'cert_id': row_id})
    assert r.status_code in (200, 201), r.get_json()
    assert _enrolments(app) == 2


def test_the_same_issuer_and_serial_is_refused(app, auth_client, same_serial):
    serial, pem_a, _ = same_serial
    assert _import(auth_client, pem_a).status_code == 201
    issuer = _info(pem_a)['issuer_dn']
    # Another certificate of that issuer and serial: the route refuses it, and so does the index
    r = _import(auth_client, _leaf(issuer.removeprefix('CN='), serial))
    assert r.status_code == 409, r.get_json()
    with app.app_context():
        db.session.add(AuthCertificate(user_id=1, cert_serial=str(serial), cert_subject=f'CN={SUBJECT}',
                                       cert_issuer=issuer, enabled=True))
        with pytest.raises(IntegrityError):
            db.session.commit()


def test_an_unknown_issuer_is_still_held_by_the_index(app, same_serial):
    serial = str(same_serial[0])
    with app.app_context():
        rows = [AuthCertificate(user_id=1, cert_serial=serial, cert_subject=f'CN={SUBJECT}',
                                cert_issuer=issuer, enabled=True) for issuer in (None, 'CN=for now')]
        db.session.add_all(rows)
        db.session.commit()
        rows[1].cert_issuer = None   # as a restore writes an archive's NULL
        with pytest.raises(IntegrityError):
            db.session.commit()


def test_each_certificate_signs_in_to_its_own_enrolment(app, auth_client, same_serial):
    _serial, pem_a, pem_b = same_serial
    ids = [_import(auth_client, pem).get_json()['data']['id'] for pem in (pem_a, pem_b)]
    with app.app_context():
        for pem, enrolment_id in zip((pem_a, pem_b), ids):
            _user, found, err = MTLSAuthService.authenticate_certificate(_info(pem))
            assert found is not None and found.id == enrolment_id, err
            # The fingerprint alone, or the issuer alone, still tells them apart
            digest = _info(pem)['fingerprint'].lower()
            info = dict(_info(pem), issuer_dn=None, fingerprint=':'.join(digest[i:i + 2] for i in range(0, 64, 2)))
            _user, found, err = MTLSAuthService.authenticate_certificate(info)
            assert found is not None and found.id == enrolment_id, err
            info = dict(_info(pem), fingerprint=None, cert_pem=None)
            _user, found, err = MTLSAuthService.authenticate_certificate(info)
            assert found is not None and found.id == enrolment_id, err
        # Neither fingerprint nor issuer: two candidates, no guess
        info = dict(_info(pem_a), fingerprint=None, cert_pem=None, issuer_dn=None)
        user, found, err = MTLSAuthService.authenticate_certificate(info)
        assert (user, found, err) == (None, None, 'Certificate not enrolled')


def test_a_restore_adds_the_other_issuers_certificate_of_that_serial(app, auth_client, same_serial):
    from tests.test_backup_restore_failfast import PASSWORD, _only, _reseal, _service
    _serial, pem_a, pem_b = same_serial
    assert _import(auth_client, pem_b).status_code == 201
    with app.app_context():
        svc = _service()
        blob = svc.create_backup(PASSWORD, include=_only('auth_certificates'))
        _key, data = svc._decrypt_framed(blob, PASSWORD)
        archived = next(r for r in data['auth_certificates'] if r['cert_subject'] == f'CN={SUBJECT}')
        AuthCertificate.query.filter(AuthCertificate.cert_subject == f'CN={SUBJECT}').delete()
        db.session.commit()
    # Without fingerprints, only (issuer, serial) tells the two apart
    archived['cert_fingerprint'] = ''
    assert _import(auth_client, pem_a).status_code == 201
    with app.app_context():
        AuthCertificate.query.filter(AuthCertificate.cert_subject == f'CN={SUBJECT}').update({'cert_fingerprint': ''})
        db.session.commit()
        svc.restore_backup(_reseal(blob, data), PASSWORD, mode='merge')
        db.session.expire_all()
        rows = AuthCertificate.query.filter(AuthCertificate.cert_subject == f'CN={SUBJECT}').all()
        assert sorted(r.cert_issuer for r in rows) == sorted([_info(pem_a)['issuer_dn'], archived['cert_issuer']])
