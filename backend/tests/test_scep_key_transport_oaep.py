"""RSAES-OAEP key transport in SCEP envelopes: the Windows SCEP client wraps
the content key with OAEP, and the reply must wrap its own key the same way
(#228)."""
import base64
import secrets

import asn1crypto.cms
import asn1crypto.core
import asn1crypto.x509
import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from models import Certificate, db
from services.scep.crypto_helpers import (
    RSAES_OAEP, RSAES_PKCS1V15, create_signed_pkcs7, encrypt_for_client,
    select_response_key_transport,
)
from services.scep.message_parser import decrypt_scep_envelope
from services.scep.scep_service import SCEPService
from tests.test_scep_rfc8894_operations import (
    MESSAGE_TYPE_OID, SENDER_NONCE_OID, TRANSACTION_ID_OID,
    _client_identity, _decrypt_response, _issuer_and_serial, _load_ca_material,
)

_HASHES = {"sha1": hashes.SHA1, "sha256": hashes.SHA256}


def _oaep_envelope(plaintext, recipient_cert, hash_name="sha256", *,
                   label=b"", explicit_params=True):
    """An EnvelopedData built by hand, independent of the production encoder."""
    content_key, iv = secrets.token_bytes(16), secrets.token_bytes(16)
    pad = 16 - len(plaintext) % 16
    encryptor = Cipher(algorithms.AES(content_key), modes.CBC(iv)).encryptor()
    ciphertext = encryptor.update(plaintext + bytes([pad]) * pad) + encryptor.finalize()
    hash_cls = _HASHES[hash_name]
    wrapped = recipient_cert.public_key().encrypt(
        content_key,
        padding.OAEP(mgf=padding.MGF1(hash_cls()), algorithm=hash_cls(), label=label or None),
    )
    recipient = asn1crypto.x509.Certificate.load(
        recipient_cert.public_bytes(serialization.Encoding.DER))
    key_algorithm = {'algorithm': 'rsaes_oaep'}
    if explicit_params:
        params = {
            'hash_algorithm': {'algorithm': hash_name},
            'mask_gen_algorithm': {'algorithm': 'mgf1', 'parameters': {'algorithm': hash_name}},
        }
        if label:
            params['p_source_algorithm'] = {'algorithm': 'p_specified', 'parameters': label}
        key_algorithm['parameters'] = params
    enveloped = asn1crypto.cms.EnvelopedData({
        'version': 'v0',
        'recipient_infos': [asn1crypto.cms.RecipientInfo({'ktri': {
            'version': 'v0',
            'rid': {'issuer_and_serial_number': {
                'issuer': recipient.issuer, 'serial_number': recipient.serial_number}},
            'key_encryption_algorithm': key_algorithm,
            'encrypted_key': wrapped,
        }})],
        'encrypted_content_info': {
            'content_type': 'data',
            'content_encryption_algorithm': {
                'algorithm': 'aes128_cbc', 'parameters': asn1crypto.core.OctetString(iv)},
            'encrypted_content': ciphertext,
        },
    })
    return asn1crypto.cms.ContentInfo({
        'content_type': 'enveloped_data', 'content': enveloped}).dump()


def _key_transport_of(envelope):
    recipient = asn1crypto.cms.ContentInfo.load(envelope)['content']['recipient_infos'][0]
    return recipient.chosen['key_encryption_algorithm']


class TestOaepEnvelopeDecryption:
    def test_oaep_sha256_envelope_is_decrypted(self):
        cert, key = _client_identity()
        envelope = _oaep_envelope(b"hello scep", cert, "sha256")
        assert decrypt_scep_envelope(envelope, key, cert) == b"hello scep"

    def test_absent_parameters_mean_sha1(self):
        cert, key = _client_identity()
        envelope = _oaep_envelope(b"defaults", cert, "sha1", explicit_params=False)
        assert decrypt_scep_envelope(envelope, key, cert) == b"defaults"

    def test_oaep_label_is_refused(self):
        cert, key = _client_identity()
        envelope = _oaep_envelope(b"labelled", cert, "sha256", label=b"x")
        with pytest.raises(ValueError, match="label"):
            decrypt_scep_envelope(envelope, key, cert)

    def test_pkcs1v15_is_still_accepted(self):
        cert, key = _client_identity()
        envelope = encrypt_for_client(b"classic", cert)
        assert _key_transport_of(envelope)['algorithm'].native == RSAES_PKCS1V15
        assert decrypt_scep_envelope(envelope, key, cert) == b"classic"


class TestResponseKeyTransport:
    def test_selection_follows_the_request(self):
        cert, _key = _client_identity()
        assert select_response_key_transport(_oaep_envelope(b"x", cert, "sha256")) == (RSAES_OAEP, "sha256")
        assert select_response_key_transport(_oaep_envelope(b"x", cert, "sha1", explicit_params=False)) == (RSAES_OAEP, "sha1")
        assert select_response_key_transport(encrypt_for_client(b"x", cert)) == (RSAES_PKCS1V15, None)

    def test_encoder_produces_oaep_the_decoder_reads_back(self):
        cert, key = _client_identity()
        envelope = encrypt_for_client(b"mirror", cert, key_transport=(RSAES_OAEP, "sha256"))
        algorithm = _key_transport_of(envelope)
        assert algorithm['algorithm'].native == RSAES_OAEP
        assert algorithm['parameters']['hash_algorithm']['algorithm'].native == "sha256"
        assert decrypt_scep_envelope(envelope, key, cert) == b"mirror"

    def test_get_cert_reply_is_wrapped_like_the_request(self, app, create_ca, create_cert):
        ca_data = create_ca(cn="SCEP OAEP Mirror CA")
        cert_data = create_cert(cn="scep-oaep.example", ca_id=ca_data["id"])
        with app.app_context():
            ca, ca_cert, _ = _load_ca_material(ca_data["id"])
            cert_row = db.session.get(Certificate, cert_data["id"])
            issued = x509.load_pem_x509_certificate(
                base64.b64decode(cert_row.crt), default_backend())
            signer_cert, signer_key = _client_identity()
            payload = _oaep_envelope(_issuer_and_serial(issued), ca_cert, "sha256")
            request = create_signed_pkcs7(payload, signer_key, signer_cert, signed_attributes=[
                {"type": TRANSACTION_ID_OID, "values": [asn1crypto.core.PrintableString("txn-oaep")]},
                {"type": MESSAGE_TYPE_OID, "values": [asn1crypto.core.PrintableString("21")]},
                {"type": SENDER_NONCE_OID, "values": [asn1crypto.core.OctetString(b"oaep-nonce-16byt")]},
            ])
            response, status = SCEPService(ca.refid).process_pkcs_req(request, "127.0.0.1")

            assert status == 200
            signed = asn1crypto.cms.ContentInfo.load(response)["content"]
            reply_envelope = signed["encap_content_info"]["content"].native
            algorithm = _key_transport_of(reply_envelope)
            assert algorithm['algorithm'].native == RSAES_OAEP
            assert algorithm['parameters']['hash_algorithm']['algorithm'].native == "sha256"
            degenerate = asn1crypto.cms.ContentInfo.load(
                _decrypt_response(response, signer_key, signer_cert))
            returned = [c.chosen.dump() for c in degenerate["content"]["certificates"]]
            assert issued.public_bytes(serialization.Encoding.DER) in returned
