"""SCEP in FIPS mode: 3DES (absent from the module), RSA PKCS#1 v1.5 key
transport (not blocked by the module) and SHA-1 signatures are refused with a
badAlg CertRep; OAEP, SHA-1 OAEP included, and AES are still served."""
import secrets

import asn1crypto.algos
import asn1crypto.cms
import asn1crypto.core
import asn1crypto.x509
import pytest
from cryptography import x509
from cryptography.exceptions import InternalError
from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.x509.oid import AttributeOID

import fips_mode
from fips_mode import FipsRestricted
from services.scep import message_parser
from services.scep.crypto_helpers import (
    RSAES_OAEP, RSAES_PKCS1V15, create_signed_pkcs7, encrypt_for_client,
    select_response_key_transport,
)
from services.scep.scep_service import SCEPService
from tests.test_scep_rfc8894_operations import (
    FAIL_INFO_OID, MESSAGE_TYPE_OID, PKI_STATUS_OID, SENDER_NONCE_OID, TRANSACTION_ID_OID,
    _client_identity, _decrypt_response, _load_ca_material, _response_attributes,
)

CHALLENGE = 'fips scep horse battery'
_HASHES = {'sha1': hashes.SHA1, 'sha256': hashes.SHA256}
_CIPHERS = {  # name: (OID, key length, block size)
    'aes128': ('2.16.840.1.101.3.4.1.2', 16, 16),
    'aes256': ('2.16.840.1.101.3.4.1.42', 32, 16),
    '3des': ('1.2.840.113549.3.7', 24, 8),
}


@pytest.fixture
def fips_on(monkeypatch):
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)


@pytest.fixture
def fips_off(monkeypatch):
    monkeypatch.setattr(fips_mode, 'enabled', lambda: False)


@pytest.fixture
def module_tdes(monkeypatch):
    """3DES as the FIPS module answers it."""
    def unsupported(*a, **k):
        raise InternalError('3DES unsupported', [])
    monkeypatch.setattr(message_parser, 'TripleDES', unsupported)


@pytest.fixture
def scep_ca(create_ca):
    # One CA per test: requests share their transactionID
    return create_ca(cn='SCEP FIPS CA')


def _ktri(content_key, cert, transport):
    if transport == 'v15':
        wrapped = cert.public_key().encrypt(content_key, padding.PKCS1v15())
        algorithm = {'algorithm': 'rsaes_pkcs1v15'}
    else:
        name = transport.split('-')[1]
        h = _HASHES[name]
        wrapped = cert.public_key().encrypt(
            content_key, padding.OAEP(mgf=padding.MGF1(h()), algorithm=h(), label=None))
        algorithm = {'algorithm': 'rsaes_oaep', 'parameters': {
            'hash_algorithm': {'algorithm': name},
            'mask_gen_algorithm': {'algorithm': 'mgf1', 'parameters': {'algorithm': name}}}}
    asn1 = asn1crypto.x509.Certificate.load(cert.public_bytes(serialization.Encoding.DER))
    return asn1crypto.cms.RecipientInfo({'ktri': {
        'version': 'v0',
        'rid': {'issuer_and_serial_number': {'issuer': asn1.issuer, 'serial_number': asn1.serial_number}},
        'key_encryption_algorithm': algorithm,
        'encrypted_key': wrapped,
    }})


def _envelope(plaintext, recipients, cipher):
    """EnvelopedData built by hand: ``recipients`` is a list of (cert, transport)."""
    oid, key_len, block = _CIPHERS[cipher]
    content_key, iv = secrets.token_bytes(key_len), secrets.token_bytes(block)
    algo = TripleDES(content_key) if cipher == '3des' else algorithms.AES(content_key)
    pad = block - len(plaintext) % block
    enc = Cipher(algo, modes.CBC(iv)).encryptor()
    ciphertext = enc.update(plaintext + bytes([pad]) * pad) + enc.finalize()
    return asn1crypto.cms.ContentInfo({'content_type': 'enveloped_data', 'content': asn1crypto.cms.EnvelopedData({
        'version': 'v0',
        'recipient_infos': [_ktri(content_key, c, t) for c, t in recipients],
        'encrypted_content_info': {
            'content_type': 'data',
            'content_encryption_algorithm': {'algorithm': oid, 'parameters': asn1crypto.core.OctetString(iv)},
            'encrypted_content': ciphertext,
        },
    })}).dump()


def _attrs(txn):
    return [
        {'type': TRANSACTION_ID_OID, 'values': [asn1crypto.core.PrintableString(txn)]},
        {'type': MESSAGE_TYPE_OID, 'values': [asn1crypto.core.PrintableString('19')]},
        {'type': SENDER_NONCE_OID, 'values': [asn1crypto.core.OctetString(b'fips-nonce-16byt')]},
    ]


def _pkcs_req(ca_cert, identity, transport='oaep-sha256', cipher='aes128', extra_recipients=()):
    cert, key = identity
    csr = (x509.CertificateSigningRequestBuilder().subject_name(cert.subject)
           .add_attribute(AttributeOID.CHALLENGE_PASSWORD, CHALLENGE.encode())
           .sign(key, hashes.SHA256()))
    payload = _envelope(csr.public_bytes(serialization.Encoding.DER),
                        [*extra_recipients, (ca_cert, transport)], cipher)
    return create_signed_pkcs7(payload, key, cert, signed_attributes=_attrs(f'fips-{transport}-{cipher}'))


def _resign(message, key, digest_name, sig_alg):
    """Re-sign a request's SignerInfo with ``digest_name`` and label it ``sig_alg``."""
    ci = asn1crypto.cms.ContentInfo.load(message)
    sd = ci['content']
    si = sd['signer_infos'][0]
    h = _HASHES[digest_name]
    content = sd['encap_content_info']['content'].native
    digest = hashes.Hash(h())
    digest.update(content)
    attrs = [a for a in si['signed_attrs'] if a['type'].native != 'message_digest']
    attrs.append({'type': 'message_digest', 'values': [asn1crypto.core.OctetString(digest.finalize())]})
    signed_attrs = asn1crypto.cms.CMSAttributes(attrs)
    raw = signed_attrs.dump()
    si['signed_attrs'] = signed_attrs
    si['digest_algorithm'] = {'algorithm': digest_name}
    si['signature_algorithm'] = {'algorithm': sig_alg}
    si['signature'] = key.sign(b'\x31' + raw[1:], padding.PKCS1v15(), h())
    sd['digest_algorithms'] = [{'algorithm': digest_name}]
    return ci.dump()


def _process(app, scep_ca, request_for):
    with app.app_context():
        ca, ca_cert, _ = _load_ca_material(scep_ca['id'])
        identity = _client_identity('fips scep device')
        response, status = SCEPService(ca.refid, challenge_password=CHALLENGE, auto_approve=True) \
            .process_pkcs_req(request_for(ca_cert, identity), '127.0.0.1')
        return response, status, identity


def _assert_bad_alg(response, status):
    attrs = _response_attributes(response)
    assert status == 200
    assert attrs[PKI_STATUS_OID] == '2', attrs
    assert attrs[FAIL_INFO_OID] == '0', attrs  # badAlg


def _assert_issued(response, status, identity):
    assert status == 200
    assert _response_attributes(response)[PKI_STATUS_OID] == '0'
    degenerate = asn1crypto.cms.ContentInfo.load(_decrypt_response(response, identity[1], identity[0]))
    assert len(degenerate['content']['certificates']) == 1


def _reply_key_transport(response):
    signed = asn1crypto.cms.ContentInfo.load(response)['content']
    envelope = asn1crypto.cms.ContentInfo.load(signed['encap_content_info']['content'].native)
    return envelope['content']['recipient_infos'][0].chosen['key_encryption_algorithm']


# ── Refused in FIPS mode ───────────────────────────────────────

def test_3des_pkcsreq_gets_bad_alg_in_fips_mode(fips_on, module_tdes, app, scep_ca):
    _assert_bad_alg(*_process(app, scep_ca, lambda c, i: _pkcs_req(c, i, cipher='3des'))[:2])


def test_pkcs1v15_key_transport_gets_bad_alg_in_fips_mode(fips_on, app, scep_ca):
    _assert_bad_alg(*_process(app, scep_ca, lambda c, i: _pkcs_req(c, i, transport='v15'))[:2])


@pytest.mark.parametrize('sig_alg', ['sha1_rsa', 'rsassa_pkcs1v15'])
def test_sha1_signed_pkcsreq_gets_bad_alg_in_fips_mode(sig_alg, fips_on, app, scep_ca):
    _assert_bad_alg(*_process(app, scep_ca, lambda c, i: _resign(_pkcs_req(c, i), i[1], 'sha1', sig_alg))[:2])


def test_sha1_rsa_label_is_refused_in_fips_mode(fips_on, app, scep_ca):
    """A SHA-256 signature labelled sha1WithRSAEncryption: the label alone is refused."""
    _assert_bad_alg(*_process(app, scep_ca, lambda c, i: _resign(_pkcs_req(c, i), i[1], 'sha256', 'sha1_rsa'))[:2])


# ── Still served in FIPS mode ──────────────────────────────────

@pytest.mark.parametrize('transport,cipher', [('oaep-sha1', 'aes128'), ('oaep-sha256', 'aes256')])
def test_oaep_and_aes_are_served_in_fips_mode(transport, cipher, fips_on, app, scep_ca):
    response, status, identity = _process(app, scep_ca, lambda c, i: _pkcs_req(c, i, transport, cipher))
    _assert_issued(response, status, identity)
    algorithm = _reply_key_transport(response)
    assert algorithm['algorithm'].native == RSAES_OAEP
    assert algorithm['parameters']['hash_algorithm']['algorithm'].native == transport.split('-')[1]


def test_reply_skips_a_pkcs1v15_recipient_in_fips_mode(fips_on, app, scep_ca):
    """The first recipient is someone else's, in v1.5: the reply follows UCM's own, in OAEP."""
    other = _client_identity('other recipient')[0]
    response, status, identity = _process(app, scep_ca, lambda c, i: _pkcs_req(
        c, i, 'oaep-sha256', extra_recipients=[(other, 'v15')]))
    _assert_issued(response, status, identity)
    assert _reply_key_transport(response)['algorithm'].native == RSAES_OAEP


def test_reply_never_wraps_in_pkcs1v15_in_fips_mode(fips_on):
    cert = _client_identity('fips reply')[0]
    with pytest.raises(FipsRestricted):
        encrypt_for_client(b'x', cert, key_transport=(RSAES_PKCS1V15, None))
    with pytest.raises(FipsRestricted):
        encrypt_for_client(b'x', cert)  # the default transport is v1.5


def test_get_ca_caps_announces_nothing_refused_in_fips_mode(fips_on, app, scep_ca):
    with app.app_context():
        ca, _, _ = _load_ca_material(scep_ca['id'])
        caps = SCEPService(ca.refid).get_ca_caps().split('\n')
    assert not {'DES3', 'SHA-1', 'MD5', 'DES'} & set(caps), caps
    assert {'AES', 'SHA-256', 'SCEPStandard'} <= set(caps), caps


# ── Unchanged outside FIPS mode ────────────────────────────────

@pytest.mark.parametrize('transport,cipher', [('v15', '3des'), ('v15', 'aes128'), ('oaep-sha1', '3des')])
def test_legacy_pkcsreq_unchanged_outside_fips_mode(transport, cipher, fips_off, app, scep_ca):
    response, status, identity = _process(app, scep_ca, lambda c, i: _pkcs_req(c, i, transport, cipher))
    _assert_issued(response, status, identity)


def test_sha1_signed_pkcsreq_unchanged_outside_fips_mode(fips_off, app, scep_ca):
    response, status, identity = _process(
        app, scep_ca, lambda c, i: _resign(_pkcs_req(c, i), i[1], 'sha1', 'sha1_rsa'))
    _assert_issued(response, status, identity)


def test_reply_transport_selection_unchanged_outside_fips_mode(fips_off):
    ca_cert = _client_identity('ca')[0]
    other = _client_identity('other')[0]
    envelope = _envelope(b'x', [(other, 'v15'), (ca_cert, 'oaep-sha256')], 'aes128')
    assert select_response_key_transport(envelope) == (RSAES_PKCS1V15, None)
    assert select_response_key_transport(encrypt_for_client(b'x', ca_cert)) == (RSAES_PKCS1V15, None)
