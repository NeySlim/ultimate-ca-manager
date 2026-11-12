"""A SCEP client limited to SHA-1/SHA-256, 3DES/AES-128 and RSA PKCS#1 v1.5
(a FortiGate-class device) asks for a certificate; its decoder refuses anything
else in the CertRep, the envelope and the issued certificate."""
import asn1crypto.cms
import asn1crypto.x509
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES

from tests.test_scep_fips import _resign
from tests.test_scep_get_pkioperation import PATHS, pkcs_req, scep_http  # noqa: F401
from tests.test_scep_rfc8894_operations import (
    PKI_STATUS_OID, SENDER_NONCE_OID, RECIPIENT_NONCE_OID, TRANSACTION_ID_OID,
    _client_identity, _response_attributes,
)

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')

DIGESTS = {'sha1': hashes.SHA1, 'sha256': hashes.SHA256}
SIGNATURES = {  # CMS and X.509 labels of RSA PKCS#1 v1.5 with SHA-1 or SHA-256
    'rsassa_pkcs1v15', 'rsa', 'sha1_rsa', 'sha256_rsa',
}
CONTENT_CIPHERS = {'tripledes_3key', 'aes128_cbc'}


def _only(value, allowed, what):
    assert value in allowed, f'a limited client cannot read {what} {value!r}'
    return value


def _verify_rsa_v15(public_key, signature, data, digest_name, label):
    _only(digest_name, DIGESTS, 'digest')
    _only(label, SIGNATURES, 'signature algorithm')
    assert isinstance(public_key, rsa.RSAPublicKey), 'a limited client reads RSA keys only'
    public_key.verify(signature, data, padding.PKCS1v15(), DIGESTS[digest_name]())


def decode_certrep(response, ca_cert, client_key, client_cert):
    """The CertRep read as a limited client would; returns (attributes, issued certificate)."""
    signed = asn1crypto.cms.ContentInfo.load(response)['content']
    for algorithm in signed['digest_algorithms']:
        _only(algorithm['algorithm'].native, DIGESTS, 'digest')
    info = signed['signer_infos'][0]
    digest = _only(info['digest_algorithm']['algorithm'].native, DIGESTS, 'digest')
    label = info['signature_algorithm']['algorithm'].native
    # The signer certificate carried in the message must be the CA's
    signer = [c.chosen for c in signed['certificates']
              if c.chosen.dump() == ca_cert.public_bytes(serialization.Encoding.DER)]
    assert signer, 'CertRep not signed by the CA certificate'
    attrs_der = b'\x31' + info['signed_attrs'].dump()[1:]
    _verify_rsa_v15(ca_cert.public_key(), info['signature'].native, attrs_der, digest, label)
    h = hashes.Hash(DIGESTS[digest]())
    h.update(signed['encap_content_info']['content'].native)
    wanted = [a['values'][0].native for a in info['signed_attrs'] if a['type'].native == 'message_digest']
    assert wanted == [h.finalize()]

    # Envelope: RSA PKCS#1 v1.5 key transport, 3DES or AES-128 content
    envelope = asn1crypto.cms.ContentInfo.load(signed['encap_content_info']['content'].native)['content']
    recipient = envelope['recipient_infos'][0]
    assert recipient.name == 'ktri'
    _only(recipient.chosen['key_encryption_algorithm']['algorithm'].native, {'rsaes_pkcs1v15'}, 'key transport')
    cek = client_key.decrypt(recipient.chosen['encrypted_key'].native, padding.PKCS1v15())
    eci = envelope['encrypted_content_info']
    cipher = _only(eci['content_encryption_algorithm']['algorithm'].native, CONTENT_CIPHERS, 'content cipher')
    iv = eci['content_encryption_algorithm']['parameters'].native
    algo = TripleDES(cek) if cipher == 'tripledes_3key' else algorithms.AES(cek)
    dec = Cipher(algo, modes.CBC(iv)).decryptor()
    padded = dec.update(eci['encrypted_content'].native) + dec.finalize()
    inner = padded[:-padded[-1]]

    certs = asn1crypto.cms.ContentInfo.load(inner)['content']['certificates']
    assert len(certs) == 1
    cert = certs[0].chosen
    tbs_label = cert['signature_algorithm']['algorithm'].native
    _only(tbs_label, SIGNATURES, 'certificate signature algorithm')
    _verify_rsa_v15(ca_cert.public_key(), cert['signature_value'].native, cert['tbs_certificate'].dump(),
                    'sha1' if tbs_label.startswith('sha1') else 'sha256', tbs_label)
    assert cert['tbs_certificate']['subject_public_key_info']['algorithm']['algorithm'].native == 'rsa'
    return _response_attributes(response), x509.load_der_x509_certificate(cert.dump())


def test_sha1_3des_pkcs1v15_client_gets_a_certrep_it_can_read(client, scep_http):
    """Requests SHA-1, 3DES and PKCS#1 v1.5; the reply is SHA-256, AES-128 and PKCS#1 v1.5."""
    ca_cert = x509.load_der_x509_certificate(client.get(f'{PATHS[0]}?operation=GetCACert').data)
    identity = _client_identity('limited device')
    request = _resign(pkcs_req(ca_cert, identity, transport='v15', cipher='3des'),
                      identity[1], 'sha1', 'sha1_rsa')
    request_info = asn1crypto.cms.ContentInfo.load(request)['content']['signer_infos'][0]
    assert request_info['digest_algorithm']['algorithm'].native == 'sha1'

    r = client.post(PATHS[0] + '?operation=PKIOperation', data=request,
                    content_type='application/x-pki-message')
    assert r.status_code == 200, r.data
    attrs, issued = decode_certrep(r.data, ca_cert, identity[1], identity[0])
    assert attrs[PKI_STATUS_OID] == '0'
    sent = {a['type'].native: a['values'][0].native for a in request_info['signed_attrs']}
    assert attrs[TRANSACTION_ID_OID] == sent[TRANSACTION_ID_OID]
    assert attrs[RECIPIENT_NONCE_OID] == sent[SENDER_NONCE_OID]
    assert attrs[SENDER_NONCE_OID]
    issued.verify_directly_issued_by(ca_cert)


def test_the_limited_decoder_refuses_what_it_cannot_read():
    with pytest.raises(AssertionError):
        _only('sha384', DIGESTS, 'digest')
    with pytest.raises(AssertionError):
        _only('rsassa_pss', SIGNATURES, 'signature algorithm')
    with pytest.raises(AssertionError):
        _only('aes256_cbc', CONTENT_CIPHERS, 'content cipher')


def test_an_ec_p384_ca_is_refused_by_scep_at_every_operation(app, client, create_ca):
    """Freezes today's behaviour: SCEP clients encrypt to an RSA key (RFC 8894 §3.4), so an
    EC CA serves no operation, capabilities included; there is no CertRep to read."""
    from models import SystemConfig
    from tests.test_scep_get_pkioperation import _set
    ca = create_ca(cn='SCEP EC P-384 CA', keyAlgo='ECDSA', keySize='secp384r1')
    with app.app_context():
        previous = SystemConfig.query.filter_by(key='scep_ca_id').first()
        previous = previous.value if previous else None
        _set('scep_ca_id', str(ca['id']))
    try:
        for query in ('operation=GetCACaps', 'operation=GetCACert'):
            r = client.get(f'{PATHS[0]}?{query}')
            assert r.status_code == 503, r.data
            assert b'RSA' in r.data
        r = client.post(PATHS[0] + '?operation=PKIOperation', data=b'\x30\x00',
                        content_type='application/x-pki-message')
        assert r.status_code == 503 and b'RSA' in r.data
    finally:
        with app.app_context():
            _set('scep_ca_id', previous)
