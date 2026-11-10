"""certificates.serial_number holds one form, the decimal string, whatever wrote it,
so uix_certificates_ca_serial sees one spelling per serial (RFC 5280 §4.1.2.2)."""
import base64
import random
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from models import CA, Certificate, RevokedSerial, db
from utils.serial_format import canonical_serial, canonical_stored_serial


def _digit_hex_serial():
    """A serial whose hexadecimal spelling has no letter: the one ambiguous case."""
    return int('7' + ''.join(random.choice('0123456789') for _ in range(30)), 16)


def _self_signed(serial):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f'serial-{serial:x}')])
    now = datetime.now(timezone.utc)
    return (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(serial)
            .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=30))
            .sign(key, hashes.SHA256()))


def _b64(cert):
    return base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode()


@pytest.mark.parametrize('given, stored', [
    (0xAB, '171'), ('171', '171'), ('ab', '171'), ('AB', '171'), ('0xab', '171'),
    ('00:AB', '171'), ('0X00AB', '171'), ('  0171 ', '171'), ('12:34', str(0x1234)),
    (None, None), ('', ''), ('not-a-serial', 'not-a-serial'), (-5, '-5'),
])
def test_canonical_serial(given, stored):
    assert canonical_serial(given) == stored


def test_the_certificate_settles_an_all_digit_hex_spelling():
    serial = _digit_hex_serial()
    crt = _b64(_self_signed(serial))
    assert canonical_stored_serial(format(serial, 'x'), crt) == str(serial)
    assert canonical_stored_serial(str(serial), crt) == str(serial)
    # Neither reading is the certificate's: the value is never reinterpreted
    assert canonical_stored_serial('42', crt) == '42'


@pytest.fixture
def rows(app):
    ids = {'cert': [], 'revoked': [], 'ca': []}
    yield ids
    with app.app_context():
        db.session.rollback()
        for model, key in ((Certificate, 'cert'), (RevokedSerial, 'revoked'), (CA, 'ca')):
            for row_id in ids[key]:
                row = db.session.get(model, row_id)
                if row is not None:
                    db.session.delete(row)
        db.session.commit()


def _ca(rows):
    ca = CA(refid=f'sc-{uuid.uuid4().hex[:12]}', descr='serial canonical', serial=1,
            crt=_b64(_self_signed(random.getrandbits(100))))
    db.session.add(ca)
    db.session.commit()
    rows['ca'].append(ca.id)
    return ca


@pytest.mark.parametrize('order', ['serial first', 'crt first'])
def test_the_model_stores_the_decimal_form_whatever_the_order(app, rows, order):
    serial = _digit_hex_serial()
    cert = _self_signed(serial)
    with app.app_context():
        caref = _ca(rows).refid
        fields = {'serial_number': format(serial, 'x'), 'crt': _b64(cert)}
        if order == 'crt first':
            fields = dict(reversed(list(fields.items())))
        row = Certificate(refid=f'sc-{uuid.uuid4().hex[:12]}', descr='x', caref=caref, **fields)
        db.session.add(row)
        db.session.commit()
        rows['cert'].append(row.id)
        assert row.serial_number == str(serial)
        row.serial_number = 'AB'
        assert row.serial_number == '171'
        revoked = RevokedSerial(caref=caref, serial_number='0xAB', valid_to=datetime.now(timezone.utc).replace(tzinfo=None))
        db.session.add(revoked)
        db.session.commit()
        rows['revoked'].append(revoked.id)
        assert revoked.serial_number == '171'


def test_the_same_certificate_under_another_spelling_is_refused_by_the_index(app, rows):
    from utils.ca_serial_counter import is_serial_collision
    cert = _self_signed(random.getrandbits(120) | (0xA << 120))
    with app.app_context():
        caref = _ca(rows).refid
        first = Certificate(refid=f'sc-{uuid.uuid4().hex[:12]}', descr='issued', caref=caref,
                            crt=_b64(cert), serial_number=str(cert.serial_number))
        db.session.add(first)
        db.session.commit()
        rows['cert'].append(first.id)
        for spelling in (format(cert.serial_number, 'x'), format(cert.serial_number, 'X'),
                         cert.serial_number.to_bytes(16, 'big').hex(':').upper()):
            db.session.add(Certificate(refid=f'sc-{uuid.uuid4().hex[:12]}', descr='imported',
                                       caref=caref, serial_number=spelling))
            with pytest.raises(Exception) as caught:
                db.session.commit()
            db.session.rollback()
            assert is_serial_collision(caught.value)
        assert Certificate.stored_under(caref, format(cert.serial_number, 'X')).id == first.id


# --- Write paths: each stores str(serial) for a serial whose hex has no letter ---

@pytest.fixture
def fixed_serial(monkeypatch):
    serial = _digit_hex_serial()
    monkeypatch.setattr(x509, 'random_serial_number', lambda: serial)
    return serial


@pytest.fixture
def made_cas(auth_client):
    ids = []
    yield ids
    for ca_id in ids:
        auth_client.delete(f'/api/v2/cas/{ca_id}')


@pytest.fixture
def own_ca(create_ca, made_cas):
    def make(cn):
        ca = create_ca(cn=cn)
        made_cas.append(ca['id'])
        return ca
    return make


def _stored(app, cert_id):
    with app.app_context():
        row = db.session.get(Certificate, cert_id)
        return row.serial_number, x509.load_pem_x509_certificate(base64.b64decode(row.crt)).serial_number


def _drop(app, cert_id):
    with app.app_context():
        row = db.session.get(Certificate, cert_id)
        if row is not None:
            db.session.delete(row)
            db.session.commit()


def test_issue_form(app, own_ca, create_cert, fixed_serial):
    cert = create_cert(cn='sc-issue.test', ca_id=own_ca('SC Issue CA')['id'])
    try:
        assert _stored(app, cert['id']) == (str(fixed_serial), fixed_serial)
    finally:
        _drop(app, cert['id'])


def test_renewal(app, auth_client, own_ca, create_cert, monkeypatch):
    cert = create_cert(cn='sc-renew.test', ca_id=own_ca('SC Renew CA')['id'])
    try:
        serial = _digit_hex_serial()
        monkeypatch.setattr(x509, 'random_serial_number', lambda: serial)
        r = auth_client.post(f"/api/v2/certificates/{cert['id']}/renew", json={})
        assert r.status_code == 200, r.data
        assert _stored(app, cert['id']) == (str(serial), serial)
        with app.app_context():
            assert RevokedSerial.query.filter_by(certificate_id=cert['id']).first().serial_number.isdigit()
    finally:
        with app.app_context():
            RevokedSerial.query.filter_by(certificate_id=cert['id']).delete()
            db.session.commit()
        _drop(app, cert['id'])


def test_tsa_signer(app, own_ca, fixed_serial):
    from services import tsa_signer_cert
    ca = own_ca('SC TSA CA')
    with app.app_context():
        issued = tsa_signer_cert.issue_tsa_signer_certificate(
            ca=db.session.get(CA, ca['id']), cn='sc-tsa.test', key_type='ec', curve='EC-P256')
        cert_id = issued.id
    try:
        assert _stored(app, cert_id) == (str(fixed_serial), fixed_serial)
    finally:
        _drop(app, cert_id)


def test_microsoft_ca(app):
    from api.v2.msca import _import_signed_cert
    serial = _digit_hex_serial()
    pem = _self_signed(serial).public_bytes(serialization.Encoding.PEM).decode()
    with app.app_context():
        name = f'sc-msca-{uuid.uuid4().hex[:8]}'
        _import_signed_cert(None, pem, SimpleNamespace(name=name), 'WebServer', -1)
        cert_id = Certificate.query.filter_by(imported_from=f'msca:{name}').one().id
    try:
        assert _stored(app, cert_id) == (str(serial), serial)
    finally:
        _drop(app, cert_id)


# --- Backups: an archive written before migration 144 restores canonical rows ---

def test_an_older_archive_restores_canonical_serials(app, create_ca):
    from tests.test_backup_restore_failfast import PASSWORD, _forged, _service
    caref = create_ca(cn=f'SC restore {uuid.uuid4().hex[:6]}')['refid']
    digits = _digit_hex_serial()
    pem = _self_signed(digits).public_bytes(serialization.Encoding.PEM).decode()
    refids = [f'sc-restore-{uuid.uuid4().hex[:8]}' for _ in range(2)]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with app.app_context():
        blob = _forged(['certificates', 'revoked_serials'], certificates=[
            {'refid': refids[0], 'descr': 'legacy hex', 'caref': caref, 'serial_number': 'AB:CD',
             'cert_type': 'server_cert'},
            {'refid': refids[1], 'descr': 'issue form', 'caref': caref, 'serial_number': format(digits, 'x'),
             'cert_type': 'server_cert', 'certificate_pem': pem},
        ], revoked_serials=[{'caref': caref, 'serial_number': 'FF', 'revoked_at': now.isoformat(),
                             'valid_to': now.isoformat()}])
        # A record this installation already holds, which the archive names in hex
        db.session.add(RevokedSerial(caref=caref, serial_number='255', revoked_at=now, valid_to=now))
        db.session.commit()
        try:
            _service().restore_backup(blob, PASSWORD, mode='merge')
            stored = dict(db.session.query(Certificate.refid, Certificate.serial_number)
                          .filter(Certificate.refid.in_(refids)))
            assert stored == {refids[0]: str(0xABCD), refids[1]: str(digits)}
            assert [r.serial_number for r in RevokedSerial.query.filter_by(caref=caref)] == ['255']
        finally:
            db.session.rollback()
            RevokedSerial.query.filter_by(caref=caref).delete()
            Certificate.query.filter(Certificate.refid.in_(refids)).delete()
            db.session.commit()


def test_an_archive_holding_one_serial_under_two_spellings_is_refused(app, create_ca):
    from services.backup.errors import BackupSchemaError
    from tests.test_backup_restore_failfast import PASSWORD, _forged, _service
    caref = create_ca(cn=f'SC twins {uuid.uuid4().hex[:6]}')['refid']
    refids = [f'sc-twin-{uuid.uuid4().hex[:8]}' for _ in range(2)]
    with app.app_context():
        blob = _forged(['certificates'], certificates=[
            {'refid': r, 'descr': 'twin', 'caref': caref, 'serial_number': spelling, 'cert_type': 'server_cert'}
            for r, spelling in zip(refids, ('ab', '171'))])
        try:
            with pytest.raises(BackupSchemaError) as refusal:
                _service().restore_backup(blob, PASSWORD, mode='merge')
            assert all(r in str(refusal.value) for r in refids)
            assert Certificate.query.filter(Certificate.refid.in_(refids)).count() == 0
        finally:
            db.session.rollback()
            Certificate.query.filter(Certificate.refid.in_(refids)).delete()
            db.session.commit()


def test_a_backend_migration_compares_canonical_serials():
    import sqlite3
    from sqlalchemy import create_engine
    from utils.serial_duplicates import duplicates_in_database
    digits = _digit_hex_serial()
    conn = sqlite3.connect(':memory:')
    conn.execute(f"CREATE TABLE {Certificate.__tablename__} "
                 "(id INTEGER PRIMARY KEY, caref TEXT, serial_number TEXT, crt TEXT)")
    conn.executemany(f"INSERT INTO {Certificate.__tablename__} VALUES (?, ?, ?, ?)",
                     [(1, 'ca-a', 'ab', None), (2, 'ca-a', '171', None), (3, 'ca-a', '172', None),
                      (4, 'ca-b', format(digits, 'x'), _b64(_self_signed(digits))), (5, 'ca-b', str(digits), None)])
    conn.commit()
    with create_engine('sqlite://', creator=lambda: conn).connect() as c:
        assert duplicates_in_database(c) == [{'caref': 'ca-a', 'serial_number': '171', 'ids': [1, 2]},
                                             {'caref': 'ca-b', 'serial_number': str(digits), 'ids': [4, 5]}]


def test_search_finds_a_serial_in_the_spelling_the_ui_shows(app, auth_client, own_ca, create_cert, fixed_serial):
    cert = create_cert(cn='sc-search.test', ca_id=own_ca('SC Search CA')['id'])
    try:
        width = (fixed_serial.bit_length() + 7) // 8
        for typed in (fixed_serial.to_bytes(width, 'big').hex(':').upper(), format(fixed_serial, 'x'),
                      str(fixed_serial)):
            listed = auth_client.get('/api/v2/certificates', query_string={'search': typed}).get_json()
            assert [c['id'] for c in listed['data']] == [cert['id']], typed
            found = auth_client.get('/api/v2/search', query_string={'q': typed}).get_json()
            assert [c['id'] for c in found['data']['certificates']] == [cert['id']], typed
    finally:
        _drop(app, cert['id'])
