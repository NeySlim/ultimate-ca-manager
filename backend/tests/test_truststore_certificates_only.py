"""The trust store holds certificates only: an entry carrying a private key is refused on every write
path, what is stored is the certificates re-serialized, and no read hands out anything else."""
import base64
import datetime
import io
import json

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import NameOID

from models import db, CA
from models.truststore import TrustedCertificate

TS = '/api/v2/truststore'
REFUSAL = 'A trust store holds certificates only; remove the private key'


def _issue(cn):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=30)).sign(key, hashes.SHA256()))
    return key, cert


def _pem(cert):
    return cert.public_bytes(serialization.Encoding.PEM)


def _fp(cert):
    return cert.fingerprint(hashes.SHA256()).hex()


def _key_pem(key, fmt=serialization.PrivateFormat.PKCS8, password=None):
    enc = (serialization.BestAvailableEncryption(password) if password else serialization.NoEncryption())
    return key.private_bytes(serialization.Encoding.PEM, fmt, enc)


def _keys(key):
    """Each armour a private key arrives in."""
    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
    return {
        'pkcs8': _key_pem(key),
        'encrypted-pkcs8': _key_pem(key, password=b'secret'),
        'sec1': _key_pem(key, serialization.PrivateFormat.TraditionalOpenSSL),
        'rsa-traditional': _key_pem(rsa_key, serialization.PrivateFormat.TraditionalOpenSSL),
        'openssh': _key_pem(key, serialization.PrivateFormat.OpenSSH),
    }


def _legacy(pem):
    return pem.replace(b'BEGIN CERTIFICATE', b'BEGIN X509 CERTIFICATE').replace(b'END CERTIFICATE',
                                                                                 b'END X509 CERTIFICATE')


def _rows_for(app, cert):
    with app.app_context():
        return TrustedCertificate.query.filter_by(fingerprint_sha256=_fp(cert)).all()


@pytest.fixture
def drop(app):
    """Removes the trust store rows of the certificates a test offered."""
    offered = []
    yield offered.append
    with app.app_context():
        fps = [_fp(c) for c in offered]
        TrustedCertificate.query.filter(TrustedCertificate.fingerprint_sha256.in_(fps)).delete(
            synchronize_session=False)
        db.session.commit()


def _upload(client, data, filename='server.pem'):
    return client.post(f'{TS}/import', data={'file': (io.BytesIO(data), filename), 'purpose': 'custom'},
                       content_type='multipart/form-data')


def _create(client, pem, name='json entry'):
    return client.post(TS, data=json.dumps({'name': name, 'certificate_pem': pem.decode()}),
                       content_type='application/json')


WRITES = {'import': _upload, 'create': _create}


# ---------------------------------------------------------------- writes

@pytest.mark.parametrize('write', sorted(WRITES))
@pytest.mark.parametrize('order', ['key-then-certificate', 'certificate-then-key'])
@pytest.mark.parametrize('armour', ['pkcs8', 'encrypted-pkcs8', 'sec1', 'rsa-traditional', 'openssh'])
def test_an_entry_with_a_private_key_is_refused_and_nothing_is_stored(app, auth_client, drop, caplog,
                                                                     write, order, armour):
    key, cert = _issue(f'{write}-{order}-{armour}')
    drop(cert)
    key_pem = _keys(key)[armour]
    data = key_pem + _pem(cert) if order == 'key-then-certificate' else _pem(cert) + key_pem
    with caplog.at_level('DEBUG'):
        r = WRITES[write](auth_client, data)
    assert r.status_code == 400, r.data
    assert REFUSAL in r.get_data(as_text=True)
    assert _rows_for(app, cert) == []
    body = key_pem.splitlines()[1].decode()
    assert not any(body in m for m in caplog.messages)


def test_a_file_holding_only_a_key_is_told_about_the_key(auth_client):
    key, _ = _issue('key-only')
    r = _upload(auth_client, _key_pem(key), 'server.key')
    assert r.status_code == 400
    assert REFUSAL in r.get_data(as_text=True)


@pytest.mark.parametrize('write', sorted(WRITES))
def test_what_is_stored_is_the_certificates_reserialized(app, auth_client, drop, write):
    _, first = _issue(f'{write}-first')
    _, second = _issue(f'{write}-second')
    drop(first)
    received = (b'Bag Attributes\n    localKeyID: 01\nsubject=CN=x\n'
                + _pem(first).replace(b'\n', b'\r\n') + b'trailing words\n' + _pem(second))
    r = WRITES[write](auth_client, received)
    assert r.status_code == 201, r.data
    (row,) = _rows_for(app, first)
    assert row.certificate_pem == (_pem(first) + _pem(second)).decode()
    assert r.get_json()['data']['certificate_pem'] == row.certificate_pem


@pytest.mark.parametrize('write', sorted(WRITES))
def test_a_block_that_is_not_a_certificate_is_refused(app, auth_client, drop, write):
    _, cert = _issue(f'{write}-broken-after')
    drop(cert)
    r = WRITES[write](auth_client, _pem(cert) + b'-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----\n')
    assert r.status_code == 400, r.data
    assert _rows_for(app, cert) == []


@pytest.mark.parametrize('write', sorted(WRITES))
def test_a_block_left_open_after_a_certificate_refuses_the_entry(app, auth_client, drop, write):
    """A chain cut short is refused whole: half of it is never stored in silence."""
    _, first = _issue(f'cut-first-{write}')
    _, second = _issue(f'cut-second-{write}')
    drop(first)
    cut = _pem(second).split(b'-----END')[0]
    r = WRITES[write](auth_client, _pem(first) + cut)
    assert r.status_code == 400, r.get_data(as_text=True)
    assert _rows_for(app, first) == []


@pytest.mark.parametrize('write', sorted(WRITES))
def test_a_legacy_label_is_accepted_and_stored_as_a_certificate(app, auth_client, drop, write):
    _, cert = _issue(f'legacy-{write}')
    drop(cert)
    r = WRITES[write](auth_client, _legacy(_pem(cert)))
    assert r.status_code == 201, r.get_data(as_text=True)
    (row,) = _rows_for(app, cert)
    assert row.certificate_pem.encode() == _pem(cert)


@pytest.mark.parametrize('label', ['CERTIFICATE', 'X509 CERTIFICATE'])
@pytest.mark.parametrize('write', sorted(WRITES))
def test_a_block_with_rfc1421_headers_is_read_the_same_by_both_writes(app, auth_client, drop, write, label):
    _, cert = _issue(f'headers-{write}-{label[:4]}')
    drop(cert)
    pem = _pem(cert).replace(b'-----BEGIN CERTIFICATE-----\n', b'-----BEGIN CERTIFICATE-----\nComment: x\n\n')
    pem = pem.replace(b'CERTIFICATE-----', label.encode() + b'-----')
    r = WRITES[write](auth_client, pem)
    assert r.status_code == 201, r.get_data(as_text=True)
    (row,) = _rows_for(app, cert)
    assert row.certificate_pem.encode() == _pem(cert)


@pytest.mark.parametrize('label', ['CERTIFICATE', 'X509 CERTIFICATE', 'PRIVATE KEY'])
def test_a_der_file_naming_a_pem_opening_is_still_read_as_der(app, auth_client, drop, label):
    """An armour line inside a field of a DER certificate is signed public data, not a key block."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f'-----BEGIN {label}-----')])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=30)).sign(key, hashes.SHA256()))
    drop(cert)
    r = _upload(auth_client, cert.public_bytes(serialization.Encoding.DER), 'odd.der')
    assert r.status_code == 201, r.get_data(as_text=True)
    (row,) = _rows_for(app, cert)
    assert row.certificate_pem.encode() == _pem(cert)


@pytest.fixture
def ca_row(app, create_ca):
    ca = create_ca(cn='Trust copy CA')
    yield ca
    with app.app_context():
        TrustedCertificate.query.filter_by(subject=db.session.get(CA, ca['id']).subject).delete()
        CA.query.filter_by(id=ca['id']).delete()
        db.session.commit()


def _set_ca_crt(app, ca_id, pem):
    with app.app_context():
        row = db.session.get(CA, ca_id)
        cert = x509.load_pem_x509_certificate(base64.b64decode(row.crt))
        row.crt = base64.b64encode(pem(cert)).decode()
        db.session.commit()
        return cert


def test_a_managed_ca_is_copied_as_its_certificate_only(app, auth_client, ca_row):
    cert = _set_ca_crt(app, ca_row['id'], lambda c: b'subject=CN=x\n' + _pem(c))
    r = auth_client.post(f"{TS}/add-from-ca/{ca_row['refid']}", data='{}', content_type='application/json')
    assert r.status_code == 201, r.data
    (row,) = _rows_for(app, cert)
    assert row.certificate_pem == _pem(cert).decode()


def test_a_managed_ca_row_holding_a_key_is_refused(app, auth_client, ca_row):
    key, _ = _issue('stray')
    cert = _set_ca_crt(app, ca_row['id'], lambda c: _key_pem(key) + _pem(c))
    r = auth_client.post(f"{TS}/add-from-ca/{ca_row['refid']}", data='{}', content_type='application/json')
    assert r.status_code == 400
    assert REFUSAL in r.get_data(as_text=True)
    assert _rows_for(app, cert) == []


def test_the_system_bundle_is_stored_reserialized(app, auth_client, drop, tmp_path, monkeypatch):
    _, cert = _issue('system-bundle-entry')
    drop(cert)
    bundle = tmp_path / 'ca-certificates.crt'
    bundle.write_bytes(b'# a comment\n' + _pem(cert).replace(b'\n', b'\r\n'))
    monkeypatch.setattr('api.v2.truststore.SYSTEM_CA_BUNDLE', str(bundle))
    r = auth_client.post(f'{TS}/sync', data=json.dumps({'limit': 1}), content_type='application/json')
    assert r.status_code == 200, r.data
    (row,) = _rows_for(app, cert)
    assert row.certificate_pem == _pem(cert).decode()


# ---------------------------------------------------------------- reads of a row an older version stored

@pytest.fixture
def keyed_row(app, drop):
    """A row as 2.254.4 stored an uploaded `key + certificate` file, written straight to the table."""
    key, cert = _issue('stored-with-key')
    drop(cert)
    key_pem = _key_pem(key).decode()
    with app.app_context():
        row = TrustedCertificate(name='stored with key', certificate_pem=key_pem + _legacy(_pem(cert)).decode(),
                                 fingerprint_sha256=_fp(cert), subject=cert.subject.rfc4514_string(),
                                 purpose='custom')
        db.session.add(row)
        db.session.commit()
        row_id = row.id
    return row_id, cert, key_pem.splitlines()[1]


def test_the_detail_and_the_list_hand_out_the_certificate_only(auth_client, keyed_row):
    row_id, cert, body = keyed_row
    detail = auth_client.get(f'{TS}/{row_id}')
    assert detail.status_code == 200
    assert detail.get_json()['data']['certificate_pem'].encode() == _pem(cert)
    listing = auth_client.get(TS)
    assert body not in listing.get_data(as_text=True)
    (entry,) = [e for e in listing.get_json()['data'] if e['id'] == row_id]
    assert entry['certificate_pem'].encode() == _pem(cert)


def test_the_pem_export_hands_out_the_certificate_only(auth_client, keyed_row):
    _, cert, body = keyed_row
    r = auth_client.get(f'{TS}/export?format=pem')
    assert r.status_code == 200
    text = r.get_data(as_text=True)
    assert body not in text and 'PRIVATE KEY' not in text
    assert _pem(cert).decode().strip() in text and 'X509 CERTIFICATE' not in text


def test_the_p7b_export_carries_the_certificate(auth_client, keyed_row):
    _, cert, body = keyed_row
    r = auth_client.get(f'{TS}/export?format=p7b')
    assert r.status_code == 200
    assert body.encode() not in r.data
    assert cert in pkcs7.load_der_pkcs7_certificates(r.data)


def test_a_backup_carries_the_certificate_only(app, keyed_row):
    """The archive does not wait on the start-up cleanup: it reads the blocks of the row itself."""
    from services.backup.export_generic import IdentityIndex, export_section
    row_id, cert, body = keyed_row
    with app.app_context():
        rows = export_section('trusted_certificates', IdentityIndex())
    (entry,) = [e for e in rows if e['fingerprint_sha256'] == _fp(cert)]
    assert entry['certificate_pem'].encode() == _pem(cert)
    assert body not in json.dumps(rows)
