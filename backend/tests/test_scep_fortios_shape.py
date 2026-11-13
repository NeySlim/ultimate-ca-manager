"""Shapes a FortiOS 7.6 SCEP client was seen to send, frozen as tests: a base64
message folded by %0A in a GET, a SHA-256 / AES-256-CBC request with no GetCACaps,
and GetCACert with a CAIdentifier on a two-level CA."""
import base64
import json
import urllib.parse

import asn1crypto.cms
import asn1crypto.core
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.serialization import pkcs7

from models import SystemConfig, db
from tests.conftest import get_json
from tests.test_scep_get_pkioperation import CHALLENGE, PATHS, _issued, _message_with_both_symbols, _set, pkcs_req, scep_http  # noqa: F401
from tests.test_scep_rfc8894_operations import (
    MESSAGE_TYPE_OID, PKI_STATUS_OID, _client_identity, _response_attributes,
)

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')


def _folded_url(path, message, width=64):
    """The relevant form: '+' as %2B, '=' as %3D, '/' raw, a %0A every ``width`` characters."""
    b64 = base64.b64encode(message).decode()
    lines = [b64[i:i + width] for i in range(0, len(b64), width)]
    folded = '%0A'.join(urllib.parse.quote(line, safe='/') for line in lines) + '%0A'
    return f'{path}?operation=PKIOperation&message={folded}'


def test_get_pkioperation_folded_by_line_feeds_is_served_like_the_plain_message(app, client, auth_client, scep_http):
    """Characterisation: the base64 decoder skips line feeds, so the folded form issues on a
    profile endpoint. Mutating the GET branch to a strict decoder (validate=True) kills it."""
    r = auth_client.post('/api/v2/scep/profiles', data=json.dumps({
        'name': 'fortios fold', 'ca_id': scep_http['id'], 'auto_approve': True,
        'challenge_password': CHALLENGE}), content_type='application/json')
    assert r.status_code == 200, r.data
    profile = get_json(r)['data']
    path = f"/scep/{profile['url_slug']}/pkiclient.exe"
    ca_cert = x509.load_der_x509_certificate(client.get(f'{path}?operation=GetCACert').data)
    message, identity = _message_with_both_symbols(ca_cert)
    url = _folded_url(path, message)
    assert url.count('%0A') > 1 and '%2B' in url
    try:
        r = client.get(url)
        assert r.status_code == 200, r.data
        assert len(_issued(r.data, identity)) == 1
    finally:
        auth_client.delete(f"/api/v2/scep/profiles/{profile['id']}")


# --- a client limited to SHA-256 and AES-256-CBC, without GetCACaps -------------------

def _decode_certrep_sha256_aes256(response, ca_cert, client_key):
    """Reads a CertRep accepting only SHA-256 signing and AES-256-CBC content."""
    signed = asn1crypto.cms.ContentInfo.load(response)['content']
    for algorithm in signed['digest_algorithms']:
        assert algorithm['algorithm'].native == 'sha256', 'this client reads SHA-256 only'
    info = signed['signer_infos'][0]
    assert info['digest_algorithm']['algorithm'].native == 'sha256'
    attrs_der = b'\x31' + info['signed_attrs'].dump()[1:]
    ca_cert.public_key().verify(info['signature'].native, attrs_der, padding.PKCS1v15(), hashes.SHA256())
    envelope = asn1crypto.cms.ContentInfo.load(signed['encap_content_info']['content'].native)['content']
    recipient = envelope['recipient_infos'][0].chosen
    assert recipient['key_encryption_algorithm']['algorithm'].native == 'rsaes_pkcs1v15'
    cek = client_key.decrypt(recipient['encrypted_key'].native, padding.PKCS1v15())
    eci = envelope['encrypted_content_info']
    assert eci['content_encryption_algorithm']['algorithm'].native == 'aes256_cbc', \
        'this client reads AES-256-CBC only'
    assert len(cek) == 32
    iv = eci['content_encryption_algorithm']['parameters'].native
    dec = Cipher(algorithms.AES(cek), modes.CBC(iv)).decryptor()
    padded = dec.update(eci['encrypted_content'].native) + dec.finalize()
    inner = padded[:-padded[-1]]
    return x509.load_der_x509_certificate(
        asn1crypto.cms.ContentInfo.load(inner)['content']['certificates'][0].chosen.dump())


def test_sha256_aes256_client_without_getcacaps_gets_a_certrep_it_reads(client, scep_http):
    """The reply uses SHA-256 and AES-256-CBC for a client that sent them (the algorithm
    mirror of crypto_helpers), with no prior GetCACaps."""
    ca_cert = x509.load_der_x509_certificate(client.get(f'{PATHS[0]}?operation=GetCACert').data)
    identity = _client_identity('fortios device', key=rsa.generate_private_key(65537, 2048))
    request = pkcs_req(ca_cert, identity, transport='v15', cipher='aes256')
    info = asn1crypto.cms.ContentInfo.load(request)['content']['signer_infos'][0]
    assert info['digest_algorithm']['algorithm'].native == 'sha256'
    sent = {a['type'].dotted: a['values'][0] for a in info['signed_attrs']}
    assert sent[MESSAGE_TYPE_OID].dump() == b'\x13\x0219'  # PrintableString "19", not an INTEGER
    r = client.post(PATHS[0] + '?operation=PKIOperation', data=request,
                    content_type='application/x-pki-message')
    assert r.status_code == 200, r.data
    assert _response_attributes(r.data)[PKI_STATUS_OID] == '0'
    issued = _decode_certrep_sha256_aes256(r.data, ca_cert, identity[1])
    issued.verify_directly_issued_by(ca_cert)


def test_the_sha256_aes256_decoder_refuses_aes128(client, scep_http):
    ca_cert = x509.load_der_x509_certificate(client.get(f'{PATHS[0]}?operation=GetCACert').data)
    identity = _client_identity('fortios device 128')
    r = client.post(PATHS[0] + '?operation=PKIOperation',
                    data=pkcs_req(ca_cert, identity, cipher='aes128'),
                    content_type='application/x-pki-message')
    assert r.status_code == 200, r.data
    with pytest.raises(AssertionError):
        _decode_certrep_sha256_aes256(r.data, ca_cert, identity[1])


# --- GetCACert with a CAIdentifier on a two-level CA ------------------------------------

@pytest.fixture
def two_level(app, create_ca, auth_client):
    root = create_ca(cn='FortiOS Chain Root')
    r = auth_client.post('/api/v2/cas', json={
        'type': 'intermediate', 'commonName': 'FortiOS Chain Intermediate', 'organization': 'Test Org',
        'country': 'US', 'state': 'CA', 'locality': 'Test City', 'keyType': 'RSA', 'keySize': 2048,
        'validityYears': 5, 'hashAlgorithm': 'sha256', 'parentCAId': root['id']})
    assert r.status_code == 201, r.data
    inter = r.get_json()['data']
    with app.app_context():
        saved = {k: (row.value if (row := SystemConfig.query.filter_by(key=k).first()) else None)
                 for k in ('scep_enabled', 'scep_ca_id', 'scep_getcacert_chain')}
        _set('scep_enabled', 'true')
        _set('scep_ca_id', str(inter['id']))
    yield root, inter
    with app.app_context():
        for k, v in saved.items():
            _set(k, v)
        from services.ca_service import CAService
        CAService.delete_ca(inter['id'])  # before its parent, which the module cleanup deletes


def _cn(cert):
    return cert.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[0].value


def test_getcacert_with_caidentifier_serves_the_ca_alone_by_default(app, client, two_level):
    with app.app_context():
        _set('scep_getcacert_chain', None)
    r = client.get('/scep/pkiclient.exe?operation=GetCACert&message=CAIdentifier')
    assert r.status_code == 200
    assert r.content_type == 'application/x-x509-ca-cert'
    assert _cn(x509.load_der_x509_certificate(r.data)) == 'FortiOS Chain Intermediate'


def test_getcacert_chain_mode_orders_certificates_by_der_encoding_not_by_chain(app, client, two_level):
    """The degenerate PKCS#7 holds a SET OF, which DER sorts by encoding: the served order is
    that sort, not CA-first (the service builds the chain CA first). A client keeping only the
    last certificate gets whichever encodes last. The order is not changed here."""
    with app.app_context():
        _set('scep_getcacert_chain', 'true')
    r = client.get('/scep/pkiclient.exe?operation=GetCACert&message=CAIdentifier')
    assert r.status_code == 200
    assert r.content_type == 'application/x-x509-ca-ra-cert'
    certs = pkcs7.load_der_pkcs7_certificates(r.data)
    ders = [c.public_bytes(serialization.Encoding.DER) for c in certs]
    assert ders == sorted(ders)
    assert {_cn(c) for c in certs} == {'FortiOS Chain Intermediate', 'FortiOS Chain Root'}


# --- a CA imported after its parent is linked to it at once -----------------------------

def _ca_pem(cn, key, issuer_cn=None, issuer_key=None, serial=1):
    import datetime
    from cryptography.x509.oid import NameOID
    issuer_key = issuer_key or key
    now = datetime.datetime.now(datetime.timezone.utc)
    name = lambda v: x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, v)])  # noqa: E731
    return (x509.CertificateBuilder().subject_name(name(cn)).issuer_name(name(issuer_cn or cn))
            .public_key(key.public_key()).serial_number(serial)
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=365))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(issuer_key.public_key()),
                           critical=False)
            .sign(issuer_key, hashes.SHA256()).public_bytes(serialization.Encoding.PEM).decode())


def _key_pem(key):
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()


@pytest.mark.parametrize('endpoint', ['/api/v2/cas/import', '/api/v2/certificates/import'])
def test_imported_child_ca_is_linked_to_its_imported_parent_at_once(app, client, auth_client, endpoint):
    """Parent known from the import response on, and GetCACert in chain mode serves both
    certificates without waiting for the hourly backfill."""
    import uuid
    from models import CA
    tag = uuid.uuid4().hex[:6]
    root_key, child_key = rsa.generate_private_key(65537, 2048), rsa.generate_private_key(65537, 2048)
    root_cn, child_cn = f'Import Root {tag}', f'Import Child {tag}'
    ids, refids = [], []
    with app.app_context():
        saved = {k: (row.value if (row := SystemConfig.query.filter_by(key=k).first()) else None)
                 for k in ('scep_enabled', 'scep_ca_id', 'scep_getcacert_chain')}
    try:
        for pem, key in ((_ca_pem(root_cn, root_key, serial=11), root_key),
                         (_ca_pem(child_cn, child_key, root_cn, root_key, serial=12), child_key)):
            r = auth_client.post(endpoint, data={'pem_content': pem + _key_pem(key)},
                                 content_type='multipart/form-data')
            assert r.status_code in (200, 201), r.data
            data = get_json(r)['data']
            # The response itself names the parent
            assert data['caref'] == (refids[0] if refids else None)
            ids.append(data['id'])
            refids.append(data['refid'])
        with app.app_context():
            root, child = db.session.get(CA, ids[0]), db.session.get(CA, ids[1])
            assert child.caref == root.refid
            assert root.caref is None
            _set('scep_enabled', 'true')
            _set('scep_ca_id', str(ids[1]))
            _set('scep_getcacert_chain', 'true')
        r = client.get('/scep/pkiclient.exe?operation=GetCACert')
        assert r.status_code == 200, r.data
        assert {_cn(c) for c in pkcs7.load_der_pkcs7_certificates(r.data)} == {root_cn, child_cn}
    finally:
        with app.app_context():
            for k, v in saved.items():
                _set(k, v)
            for ca_id in reversed(ids):
                CA.query.filter_by(id=ca_id).delete()
            db.session.commit()
