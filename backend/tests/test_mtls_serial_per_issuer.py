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


def _named_leaf(issuer, serial):
    key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, SUBJECT)]))
            .issuer_name(issuer).public_key(key.public_key()).serial_number(serial)
            .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=30))
            .sign(ec.generate_private_key(ec.SECP256R1()), hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.PEM).decode()


@pytest.mark.parametrize('keep_pem', [True, False], ids=['enrolled-with-its-pem', 'issuer-text-only'])
@pytest.mark.parametrize('header', [
    'emailAddress=ca@x.org,O=Soci\\C3\\A9t\\C3\\A9',   # nginx $ssl_client_i_dn
    'O=Société,emailAddress=ca@x.org',                # another order, raw UTF-8
    '/O=Société/emailAddress=ca@x.org',               # OpenSSL's legacy form
])
def test_the_issuer_a_proxy_spells_otherwise_still_signs_in(app, auth_client, same_serial, header, keep_pem):
    tag = uuid.uuid4().hex[:6]
    issuer = x509.Name([x509.NameAttribute(NameOID.EMAIL_ADDRESS, 'ca@x.org'),
                        x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Société')])
    serial = same_serial[0] + 7
    pem = _named_leaf(issuer, serial)
    r = _import(auth_client, pem)
    assert r.status_code == 201, (tag, r.get_json())
    with app.app_context():
        row = db.session.get(AuthCertificate, r.get_json()['data']['id'])
        assert row.cert_issuer == issuer.rfc4514_string() == 'O=Société,1.2.840.113549.1.9.1=ca@x.org'
        if not keep_pem:
            row.cert_pem = None
            db.session.commit()
        info = {'serial': format(serial, 'X'), 'issuer_dn': header, 'fingerprint': None,
                'subject_dn': f'CN={SUBJECT}'}
        user, found, err = MTLSAuthService.authenticate_certificate(info)
        assert user is not None and found.id == row.id, err
        # Another issuer, read on both sides, is another certificate
        other = dict(info, issuer_dn=header.replace('x.org', 'y.org'))
        assert MTLSAuthService.authenticate_certificate(other)[2] == 'Certificate not enrolled'


def test_a_serial_from_headers_is_hexadecimal(app, auth_client, same_serial):
    """`10` in a header is 0x10: it never opens the enrolment of the certificate numbered ten."""
    issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f'Hex reading {uuid.uuid4().hex[:6]}')])
    pem = _named_leaf(issuer, 10)
    r = _import(auth_client, pem)
    assert r.status_code == 201, r.get_json()
    with app.app_context():
        assert db.session.get(AuthCertificate, r.get_json()['data']['id']).cert_serial == '10'
        info = {'issuer_dn': issuer.rfc4514_string(), 'fingerprint': None, 'subject_dn': f'CN={SUBJECT}'}
        assert MTLSAuthService.authenticate_certificate(dict(info, serial='10'))[2] == 'Certificate not enrolled'
        user, _found, err = MTLSAuthService.authenticate_certificate(dict(info, serial='0A'))
        assert user is not None, err


def _header_login(serial, issuer_dn):
    return MTLSAuthService.authenticate_certificate(
        {'serial': format(serial, 'X'), 'issuer_dn': issuer_dn, 'fingerprint': None, 'subject_dn': f'CN={SUBJECT}'})


@pytest.mark.parametrize('issuer, header', [
    (x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Société'),
                x509.NameAttribute(NameOID.COMMON_NAME, 'Legacy CA')]),
     '/O=Soci\\xC3\\xA9t\\xC3\\xA9/CN=Legacy CA'),          # nginx _legacy, Apache LegacyDNStringFormat
    (x509.Name([x509.NameAttribute(x509.ObjectIdentifier('1.2.3.4'), 'abc'),
                x509.NameAttribute(NameOID.COMMON_NAME, 'Hex CA')]),
     'CN=Hex CA,1.2.3.4=#0C03616263'),                      # a value as its DER
    (x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, ' Root ')]),
     'CN=\\ Root\\ '),                                      # escaped spaces at both ends
    (x509.Name([x509.NameAttribute(x509.ObjectIdentifier('2.5.4.13'), 'Issuing'),
                x509.NameAttribute(NameOID.COMMON_NAME, 'Described CA')]),
     'CN=Described CA,description=Issuing'),               # a name RFC 4514 does not define
])
def test_other_spellings_of_the_issuer_sign_in(app, auth_client, same_serial, issuer, header):
    serial = same_serial[0] + 11
    r = _import(auth_client, _named_leaf(issuer, serial))
    assert r.status_code == 201, r.get_json()
    with app.app_context():
        user, found, err = _header_login(serial, header)
        assert user is not None and found.id == r.get_json()['data']['id'], err


@pytest.mark.parametrize('header', ['CN=Evil,description=x', 'CN=Evil,notAnAttribute=x'],
                         ids=['readable-other-issuer', 'unreadable-issuer'])
def test_another_issuers_certificate_does_not_open_the_account(app, auth_client, same_serial, header):
    """Headers only: a serial of CA A presented under an issuer that is not A's opens nothing."""
    serial, pem_a, _pem_b = same_serial
    r = _import(auth_client, pem_a)
    assert r.status_code == 201, r.get_json()
    with app.app_context():
        assert _header_login(serial, header)[2] == 'Certificate not enrolled'
        # An enrolment that recorded no issuer is still found by an unreadable one
        row = db.session.get(AuthCertificate, r.get_json()['data']['id'])
        row.cert_issuer, row.cert_pem = '', None
        db.session.commit()
        user, _found, err = _header_login(serial, 'CN=Evil,notAnAttribute=x')
        assert user is not None, err


# A serial without its issuer (RFC 5280 §4.1.2.2): headers that name no readable issuer
# never open an enrolment that recorded one.

def _proxy_headers(pem, **extra):
    info = _info(pem)
    headers = {'X-SSL-Client-Verify': 'SUCCESS', 'X-SSL-Client-S-DN': info['subject_dn'],
               'X-SSL-Client-Serial': info['serial']}
    headers.update(extra)
    return headers


@pytest.mark.parametrize('issuer_dn', [None, '', 'CN=Evil,notAnAttribute=x'],
                         ids=['absent', 'empty', 'unreadable'])
def test_a_serial_alone_does_not_open_an_enrolment_with_an_issuer(app, auth_client, same_serial,
                                                                   issuer_dn, caplog):
    serial, pem_a, _pem_b = same_serial
    r = _import(auth_client, pem_a)
    assert r.status_code == 201, r.get_json()
    info = {'serial': format(serial, 'X'), 'issuer_dn': issuer_dn, 'fingerprint': None,
            'subject_dn': f'CN={SUBJECT}'}
    with app.app_context():
        with caplog.at_level('WARNING', logger='services.mtls_enrollment'):
            assert MTLSAuthService.authenticate_certificate(info)[2] == 'Certificate not enrolled'
        assert 'X-SSL-Client-I-DN' in caplog.text
        # The issuer text alone, without the stored certificate, is still a registered issuer
        row = db.session.get(AuthCertificate, r.get_json()['data']['id'])
        row.cert_pem = None
        db.session.commit()
        assert MTLSAuthService.authenticate_certificate(info)[2] == 'Certificate not enrolled'
        # And the stored certificate alone too
        row.cert_pem, row.cert_issuer = pem_a.encode(), ''
        db.session.commit()
        assert MTLSAuthService.authenticate_certificate(info)[2] == 'Certificate not enrolled'


def test_an_enrolment_without_an_issuer_still_opens_by_serial(app, auth_client, same_serial):
    serial, pem_a, _pem_b = same_serial
    r = _import(auth_client, pem_a)
    assert r.status_code == 201, r.get_json()
    with app.app_context():
        row = db.session.get(AuthCertificate, r.get_json()['data']['id'])
        row.cert_issuer, row.cert_pem = '', None
        db.session.commit()
        user, found, err = _header_login(serial, None)
        assert user is not None and found.id == row.id, err


def test_proxy_login_needs_the_issuer_header_or_the_certificate(app, client, auth_client, same_serial):
    import urllib.parse
    _serial, pem_a, _pem_b = same_serial
    assert _import(auth_client, pem_a).status_code == 201
    login = '/api/v2/auth/login/mtls'
    r = client.post(login, headers=_proxy_headers(pem_a))
    assert r.status_code == 401, r.get_json()
    methods = client.get('/api/v2/auth/methods', headers=_proxy_headers(pem_a)).get_json()['data']
    assert methods.get('mtls_status') == 'present_not_enrolled' and methods.get('mtls_user') is None
    r = client.post(login, headers=_proxy_headers(pem_a, **{'X-SSL-Client-I-DN': _info(pem_a)['issuer_dn']}))
    assert r.status_code == 200, r.get_json()
    client.post('/api/v2/auth/logout')
    r = client.post(login, headers=_proxy_headers(pem_a, **{'X-SSL-Client-Cert': urllib.parse.quote(pem_a)}))
    assert r.status_code == 200, r.get_json()


def test_enrolling_from_headers_needs_the_issuer(app, auth_client, same_serial):
    """An enrolment made from a serial alone could never be told apart from another CA's."""
    _serial, pem_a, _pem_b = same_serial
    r = auth_client.post('/api/v2/mtls/enroll', json={}, headers=_proxy_headers(pem_a))
    assert r.status_code == 400, r.get_json()
    assert 'X-SSL-Client-I-DN' in r.get_json()['message']
    assert _enrolments(app) == 0
    r = auth_client.post('/api/v2/mtls/enroll', json={},
                         headers=_proxy_headers(pem_a, **{'X-SSL-Client-I-DN': _info(pem_a)['issuer_dn']}))
    assert r.status_code == 200, r.get_json()
    with app.app_context():
        row = AuthCertificate.query.filter(AuthCertificate.cert_subject == f'CN={SUBJECT}').one()
        assert row.cert_issuer == _info(pem_a)['issuer_dn']
