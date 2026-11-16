"""The trust store stores certificates only: an entry carrying a private key is refused on every
write path, and what is stored is the certificates re-serialized, never the text received."""
import base64
import datetime
import io
import json

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import NameOID

from models import db, CA
from models.truststore import TrustedCertificate
from utils.trust_pem import PRIVATE_KEY_REFUSAL

TS = '/api/v2/truststore'


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


def _rows_for(app, cert):
    fp = cert.fingerprint(hashes.SHA256()).hex()
    with app.app_context():
        return TrustedCertificate.query.filter_by(fingerprint_sha256=fp).all()


@pytest.fixture
def drop(app):
    """Removes the trust store rows of the certificates a test offered."""
    offered = []
    yield offered.append
    with app.app_context():
        fps = [c.fingerprint(hashes.SHA256()).hex() for c in offered]
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


@pytest.mark.parametrize('write', WRITES, ids=str)
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
    assert PRIVATE_KEY_REFUSAL in r.get_data(as_text=True)
    assert _rows_for(app, cert) == []
    body = key_pem.splitlines()[1].decode()
    assert not any(body in m for m in caplog.messages)


def test_a_file_holding_only_a_key_is_told_about_the_key(auth_client):
    key, _ = _issue('key-only')
    r = _upload(auth_client, _key_pem(key), 'server.key')
    assert r.status_code == 400
    assert PRIVATE_KEY_REFUSAL in r.get_data(as_text=True)


@pytest.mark.parametrize('write', WRITES, ids=str)
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


@pytest.mark.parametrize('write', WRITES, ids=str)
def test_a_block_that_is_not_a_certificate_is_refused(app, auth_client, drop, write):
    _, cert = _issue(f'{write}-broken-after')
    drop(cert)
    r = WRITES[write](auth_client, _pem(cert) + b'-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----\n')
    assert r.status_code == 400, r.data
    assert _rows_for(app, cert) == []


@pytest.fixture
def ca_row(app, create_ca):
    ca = create_ca(cn='Trust copy CA')
    yield ca
    with app.app_context():
        TrustedCertificate.query.filter_by(subject=CA.query.get(ca['id']).subject).delete()
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
    assert PRIVATE_KEY_REFUSAL in r.get_data(as_text=True)
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
