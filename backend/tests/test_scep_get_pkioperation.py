"""PKIOperation over GET (RFC 8894 §4.1: the message base64-encoded in the URL),
on both SCEP paths, after GetCACaps and GetCACert, plus the two tolerances
of the request parser that nothing else exercised."""
import base64
import secrets
import urllib.parse
from datetime import timedelta

import asn1crypto.cms
import asn1crypto.core
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization

from models import SystemConfig, db
from services.scep.crypto_helpers import create_signed_pkcs7
from tests.test_scep_fips import _envelope, _attrs
from tests.test_scep_rfc8894_operations import (
    MESSAGE_TYPE_OID, PKI_STATUS_OID,
    _client_identity, _decrypt_response, _load_ca_material, _response_attributes,
)

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')

PATHS = ['/scep/pkiclient.exe', '/cgi-bin/pkiclient.exe']
CHALLENGE = 'get pkioperation challenge'


def _set(key, value):
    row = SystemConfig.query.filter_by(key=key).first()
    if value is None:
        if row:
            db.session.delete(row)
    elif row is None:
        db.session.add(SystemConfig(key=key, value=value))
    else:
        row.value = value
    db.session.commit()


@pytest.fixture
def scep_http(app, create_ca):
    """The default SCEP endpoint on a fresh RSA CA, auto-approving behind a challenge."""
    ca = create_ca(cn=f'SCEP GET CA {secrets.token_hex(3)}')
    keys = ['scep_enabled', 'scep_ca_id', f"scep_challenge_{ca['id']}", 'scep_auto_approve']
    with app.app_context():
        saved = {k: (r.value if (r := SystemConfig.query.filter_by(key=k).first()) else None) for k in keys}
        _set('scep_enabled', 'true')
        _set('scep_ca_id', str(ca['id']))
        _set(f"scep_challenge_{ca['id']}", CHALLENGE)
        _set('scep_auto_approve', 'true')
    yield ca
    with app.app_context():
        for k, v in saved.items():
            _set(k, v)
        _set(f"scep_challenge_{ca['id']}_generated_at", None)


def pkcs_req(ca_cert, identity, *, message_type=None, transport='v15', cipher='aes128',
             recipients=None, txn=None):
    """A PKCSReq; ``message_type`` None sends the PrintableString of RFC 8894 §3.2.1.2."""
    cert, key = identity
    csr = (x509.CertificateSigningRequestBuilder().subject_name(cert.subject)
           .add_attribute(x509.oid.AttributeOID.CHALLENGE_PASSWORD, CHALLENGE.encode())
           .sign(key, hashes.SHA256()))
    payload = _envelope(csr.public_bytes(serialization.Encoding.DER),
                        recipients or [(ca_cert, transport)], cipher)
    attrs = _attrs(txn or secrets.token_hex(8))
    if message_type is not None:
        attrs[1] = {'type': MESSAGE_TYPE_OID, 'values': [asn1crypto.core.Integer(message_type)]}
    return create_signed_pkcs7(payload, key, cert, signed_attributes=attrs)


def _url(path, message, *, encode):
    b64 = base64.b64encode(message).decode()
    if encode == 'all':
        b64 = urllib.parse.quote(b64, safe='')
    elif encode == 'slash-raw':  # '+' and '=' encoded, '/' left as is
        b64 = urllib.parse.quote(b64, safe='/')
    return f'{path}?operation=PKIOperation&message={b64}'


def _ca_der(client, path):
    r = client.get(f'{path}?operation=GetCACert')
    assert r.status_code == 200
    return x509.load_der_x509_certificate(r.data)


def _message_with_both_symbols(ca_cert):
    """Base64 of a request holding both '+' and '/', whatever the random keys gave."""
    for _ in range(40):
        identity = _client_identity('get device')
        message = pkcs_req(ca_cert, identity)
        b64 = base64.b64encode(message).decode()
        if '+' in b64 and '/' in b64:
            return message, identity
    raise AssertionError('no message with both symbols')


def _issued(response_data, identity):
    assert _response_attributes(response_data)[PKI_STATUS_OID] == '0'
    degenerate = asn1crypto.cms.ContentInfo.load(_decrypt_response(response_data, identity[1], identity[0]))
    return degenerate['content']['certificates']


@pytest.mark.parametrize('path', PATHS)
@pytest.mark.parametrize('encode', ['all', 'slash-raw'])
def test_get_pkioperation_with_plus_and_slash_issues(client, scep_http, path, encode):
    assert b'POSTPKIOperation' in client.get(f'{path}?operation=GetCACaps').data
    ca_cert = _ca_der(client, path)
    message, identity = _message_with_both_symbols(ca_cert)
    r = client.get(_url(path, message, encode=encode))
    assert r.status_code == 200, r.data
    assert r.headers['Content-Type'] == 'application/x-pki-message'
    assert len(_issued(r.data, identity)) == 1


def test_get_pkioperation_with_a_raw_plus_is_read_as_a_plus(client, scep_http):
    """A client that does not percent-encode '+' sends what form decoding turns into a
    space; the server reads it back as '+' and issues."""
    ca_cert = _ca_der(client, PATHS[0])
    message, identity = _message_with_both_symbols(ca_cert)
    r = client.get(_url(PATHS[0], message, encode='none'))
    assert r.status_code == 200, r.data
    assert len(_issued(r.data, identity)) == 1


def test_single_recipient_naming_a_stale_ca_certificate_is_served(app, client, scep_http, caplog):
    """A client whose recipient identifier points at an older certificate of the
    same CA key is tried anyway when it is the only recipient."""
    with app.app_context():
        _ca, ca_cert, ca_key = _load_ca_material(scep_http['id'])
    now = ca_cert.not_valid_before_utc
    stale = (x509.CertificateBuilder().subject_name(ca_cert.subject).issuer_name(ca_cert.subject)
             .public_key(ca_cert.public_key()).serial_number(x509.random_serial_number())
             .not_valid_before(now).not_valid_after(now + timedelta(days=30))
             .sign(ca_key, hashes.SHA256()))
    identity = _client_identity('stale recipient device')
    message = pkcs_req(ca_cert, identity, recipients=[(stale, 'v15')])
    caplog.set_level('WARNING')
    r = client.post(PATHS[0] + '?operation=PKIOperation', data=message,
                    content_type='application/x-pki-message')
    assert r.status_code == 200
    assert len(_issued(r.data, identity)) == 1
    assert 'attempting the single recipient present' in caplog.text


def test_message_type_as_a_raw_integer_is_served(client, scep_http):
    ca_cert = _ca_der(client, PATHS[0])
    identity = _client_identity('integer type device')
    message = pkcs_req(ca_cert, identity, message_type=19)
    r = client.post(PATHS[0] + '?operation=PKIOperation', data=message,
                    content_type='application/x-pki-message')
    assert r.status_code == 200
    assert len(_issued(r.data, identity)) == 1
