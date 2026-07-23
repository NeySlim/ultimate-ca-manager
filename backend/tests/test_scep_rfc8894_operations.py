"""RFC 8894 coverage for SCEP certificate/CRL access and message guards."""
import base64
from datetime import datetime, timedelta, timezone

import asn1crypto.algos
import asn1crypto.cms
import asn1crypto.core
import asn1crypto.x509
import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import AttributeOID, NameOID

from models import CA, Certificate, SystemConfig, db
from services.crl_service import CRLService
from services.scep.crypto_helpers import create_signed_pkcs7, encrypt_for_client
from services.scep.message_parser import (
    decrypt_scep_envelope,
    extract_signer_certificate,
)
from services.scep.scep_service import SCEPService
from utils.key_codec import load_pem_bytes


TRANSACTION_ID_OID = "2.16.840.1.113733.1.9.7"
MESSAGE_TYPE_OID = "2.16.840.1.113733.1.9.2"
PKI_STATUS_OID = "2.16.840.1.113733.1.9.3"
FAIL_INFO_OID = "2.16.840.1.113733.1.9.4"
SENDER_NONCE_OID = "2.16.840.1.113733.1.9.5"
RECIPIENT_NONCE_OID = "2.16.840.1.113733.1.9.6"


def _set_config(key, value):
    row = SystemConfig.query.filter_by(key=key).first()
    if row:
        row.value = str(value)
    else:
        db.session.add(SystemConfig(key=key, value=str(value)))
    db.session.commit()


def _clear_config(key):
    row = SystemConfig.query.filter_by(key=key).first()
    if row:
        db.session.delete(row)
        db.session.commit()


def _load_ca_material(ca_id):
    ca = db.session.get(CA, ca_id)
    cert = x509.load_pem_x509_certificate(base64.b64decode(ca.crt), default_backend())
    key = serialization.load_pem_private_key(
        load_pem_bytes(ca.prv, context=f"test SCEP CA {ca.id}"),
        password=None,
        backend=default_backend(),
    )
    return ca, cert, key


def _client_identity(common_name="SCEP requester", key=None, add_ski=False):
    key = key or rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
    )
    if add_ski:
        cert = cert.add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
            critical=False,
        )
    cert = cert.sign(key, hashes.SHA256())
    return cert, key


def _issuer_and_serial(cert):
    cert_asn1 = asn1crypto.x509.Certificate.load(
        cert.public_bytes(serialization.Encoding.DER)
    )
    return asn1crypto.cms.IssuerAndSerialNumber({
        "issuer": cert_asn1.issuer,
        "serial_number": cert.serial_number,
    }).dump()


def _crl_issuer_and_serial(ca_cert, leaf_serial):
    """RFC 8894 §4.6 GetCRL identifier: issuer = the CA's subject DN, serial =
    the serial of the certificate whose status is queried (a leaf, not the CA)."""
    cert_asn1 = asn1crypto.x509.Certificate.load(
        ca_cert.public_bytes(serialization.Encoding.DER)
    )
    return asn1crypto.cms.IssuerAndSerialNumber({
        "issuer": cert_asn1.subject,
        "serial_number": leaf_serial,
    }).dump()


def _build_request(
    ca_cert,
    signer_cert,
    signer_key,
    message_type,
    payload,
    nonce,
    *,
    challenge=None,
    content_encryption_algorithm="aes128_cbc",
    recipient_cert=None,
):
    encrypted_payload = encrypt_for_client(
        payload,
        recipient_cert or ca_cert,
        content_encryption_algorithm=content_encryption_algorithm,
    )
    attrs = [
        {
            "type": TRANSACTION_ID_OID,
            "values": [asn1crypto.core.PrintableString(f"txn-{message_type}")],
        },
        {
            "type": MESSAGE_TYPE_OID,
            "values": [asn1crypto.core.PrintableString(str(message_type))],
        },
    ]
    if nonce is not None:
        attrs.append({
            "type": SENDER_NONCE_OID,
            "values": [asn1crypto.core.OctetString(nonce)],
        })
    if challenge is not None:
        attrs.append({
            "type": "1.2.840.113549.1.9.7",
            "values": [asn1crypto.core.PrintableString(challenge)],
        })
    return create_signed_pkcs7(
        encrypted_payload,
        signer_key,
        signer_cert,
        signed_attributes=attrs,
    )


def _rewrite_signed_attributes(message, signer_key, transform):
    content_info = asn1crypto.cms.ContentInfo.load(message)
    signer_info = content_info["content"]["signer_infos"][0]
    attributes = transform(list(signer_info["signed_attrs"]))
    rewritten = asn1crypto.cms.CMSAttributes(attributes)
    signer_info["signed_attrs"] = rewritten

    signed_bytes = rewritten.dump()
    if signed_bytes and signed_bytes[0] == 0xA0:
        signed_bytes = b"\x31" + signed_bytes[1:]
    signer_info["signature"] = signer_key.sign(
        signed_bytes,
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    return content_info.dump()


def _response_attributes(response):
    signed_data = asn1crypto.cms.ContentInfo.load(response)["content"]
    result = {}
    for attr in signed_data["signer_infos"][0]["signed_attrs"]:
        oid = attr["type"].dotted
        if len(attr["values"]):
            result[oid] = attr["values"][0].native
    return result


def _decrypt_response(response, client_key, client_cert):
    signed_data = asn1crypto.cms.ContentInfo.load(response)["content"]
    encrypted = signed_data["encap_content_info"]["content"].native
    return decrypt_scep_envelope(encrypted, client_key, client_cert)


def _unwrap_rfc3211_aes_key(wrapped_key, kek, iv):
    block_size = 16
    assert len(wrapped_key) >= block_size * 2
    assert len(wrapped_key) % block_size == 0

    last_block = Cipher(
        algorithms.AES(kek), modes.CBC(wrapped_key[-2 * block_size:-block_size])
    ).decryptor().update(wrapped_key[-block_size:])
    first_blocks = Cipher(
        algorithms.AES(kek), modes.CBC(last_block)
    ).decryptor().update(wrapped_key[:-block_size])
    inner = first_blocks + last_block
    formatted = Cipher(algorithms.AES(kek), modes.CBC(iv)).decryptor().update(inner)

    key_length = formatted[0]
    content_key = formatted[4:4 + key_length]
    assert formatted[1:4] == bytes((~byte) & 0xFF for byte in content_key[:3])
    return content_key


def _decrypt_password_response(response, password):
    signed_data = asn1crypto.cms.ContentInfo.load(response)["content"]
    envelope = asn1crypto.cms.ContentInfo.load(
        signed_data["encap_content_info"]["content"].native
    )["content"]
    recipient_info = envelope["recipient_infos"][0]
    assert recipient_info.name == "pwri"
    pwri = recipient_info.chosen

    kdf_params = pwri["key_derivation_algorithm"]["parameters"]
    prf_name = kdf_params["prf"]["algorithm"].native
    assert prf_name == "sha256"
    kek = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=kdf_params["key_length"].native,
        salt=kdf_params["salt"].native,
        iterations=kdf_params["iteration_count"].native,
    ).derive(password.encode("utf-8"))

    kek_algorithm = asn1crypto.algos.EncryptionAlgorithm.load(
        pwri["key_encryption_algorithm"]["parameters"].dump()
    )
    assert kek_algorithm["algorithm"].native == "aes128_cbc"
    content_key = _unwrap_rfc3211_aes_key(
        pwri["encrypted_key"].native,
        kek,
        kek_algorithm["parameters"].native,
    )

    encrypted_content_info = envelope["encrypted_content_info"]
    content_algorithm = encrypted_content_info["content_encryption_algorithm"]
    decryptor = Cipher(
        algorithms.AES(content_key),
        modes.CBC(content_algorithm["parameters"].native),
    ).decryptor()
    padded = (
        decryptor.update(encrypted_content_info["encrypted_content"].native)
        + decryptor.finalize()
    )
    return padded[:-padded[-1]], recipient_info, envelope


class TestScepSignedAttributeGuards:
    @pytest.mark.parametrize("nonce", [None, b"short nonce"])
    def test_missing_or_short_sender_nonce_is_tolerated(
        self, app, create_ca, nonce
    ):
        # Pre-RFC 8894 clients omit senderNonce or send fewer than 16 bytes;
        # rejecting them broke enrolled fleets on upgrade — the request must
        # proceed (not fail with badMessageCheck).
        ca_data = create_ca(cn=f"SCEP Nonce Guard {nonce!r}")
        with app.app_context():
            ca, ca_cert, _ = _load_ca_material(ca_data["id"])
            signer_cert, signer_key = _client_identity()
            request = _build_request(
                ca_cert, signer_cert, signer_key, 21,
                _issuer_and_serial(ca_cert), nonce,
            )
            response, status = SCEPService(ca.refid).process_pkcs_req(request, "127.0.0.1")

        attrs = _response_attributes(response)
        assert status == 200
        assert attrs.get(FAIL_INFO_OID) != "1"
        assert attrs[TRANSACTION_ID_OID] == "txn-21"

    @pytest.mark.parametrize("mode", ["missing", "stale", "future"])
    def test_signing_time_is_tolerated_by_default(self, app, create_ca, mode):
        # signingTime is optional in CMS; devices without NTP drift. Default
        # is lenient (warning); scep_enforce_signing_time restores rejection.
        ca_data = create_ca(cn=f"SCEP Signing Time Lenient {mode}")
        nonce = b"0123456789abcdef"
        with app.app_context():
            ca, ca_cert, _ = _load_ca_material(ca_data["id"])
            signer_cert, signer_key = _client_identity()
            request = _build_request(
                ca_cert, signer_cert, signer_key, 21,
                _issuer_and_serial(ca_cert), nonce,
            )

            def transform(attributes):
                kept = [
                    attr for attr in attributes
                    if attr["type"].native != "signing_time"
                ]
                if mode != "missing":
                    offset = timedelta(minutes=-11 if mode == "stale" else 11)
                    kept.append({
                        "type": "signing_time",
                        "values": [
                            asn1crypto.core.UTCTime(datetime.now(timezone.utc) + offset)
                        ],
                    })
                return kept

            request = _rewrite_signed_attributes(request, signer_key, transform)
            response, status = SCEPService(ca.refid).process_pkcs_req(request, "127.0.0.1")

        attrs = _response_attributes(response)
        assert status == 200
        assert attrs.get(FAIL_INFO_OID) != "3"
        assert attrs[TRANSACTION_ID_OID] == "txn-21"

    @pytest.mark.parametrize("mode", ["missing", "stale", "future"])
    def test_signing_time_is_enforced_when_opted_in(
        self, app, create_ca, mode
    ):
        ca_data = create_ca(cn=f"SCEP Signing Time {mode}")
        nonce = b"0123456789abcdef"
        with app.app_context():
            _set_config("scep_enforce_signing_time", "true")
            ca, ca_cert, _ = _load_ca_material(ca_data["id"])
            signer_cert, signer_key = _client_identity()
            request = _build_request(
                ca_cert, signer_cert, signer_key, 21,
                _issuer_and_serial(ca_cert), nonce,
            )

            def transform(attributes):
                kept = [
                    attr for attr in attributes
                    if attr["type"].native != "signing_time"
                ]
                if mode != "missing":
                    offset = timedelta(minutes=-11 if mode == "stale" else 11)
                    kept.append({
                        "type": "signing_time",
                        "values": [
                            asn1crypto.core.UTCTime(datetime.now(timezone.utc) + offset)
                        ],
                    })
                return kept

            request = _rewrite_signed_attributes(request, signer_key, transform)
            try:
                response, status = SCEPService(ca.refid).process_pkcs_req(request, "127.0.0.1")
            finally:
                _clear_config("scep_enforce_signing_time")

        attrs = _response_attributes(response)
        assert status == 200
        assert attrs[PKI_STATUS_OID] == "2"
        assert attrs[FAIL_INFO_OID] == "3"
        assert attrs[TRANSACTION_ID_OID] == "txn-21"
        assert attrs[RECIPIENT_NONCE_OID] == nonce


class TestScepSignerAndEnvelopeValidation:
    def test_signer_certificate_is_selected_by_issuer_and_serial(self):
        signer_cert, signer_key = _client_identity("actual signer")
        decoy_cert, _ = _client_identity("decoy certificate")
        message = asn1crypto.cms.ContentInfo.load(
            create_signed_pkcs7(b"payload", signer_key, signer_cert)
        )
        signed_data = message["content"]
        signed_data["certificates"] = [
            asn1crypto.x509.Certificate.load(
                decoy_cert.public_bytes(serialization.Encoding.DER)
            ),
            signed_data["certificates"][0],
        ]

        selected = extract_signer_certificate(signed_data)

        assert selected is not None
        assert selected.serial_number == signer_cert.serial_number

    def test_signer_certificate_is_selected_by_subject_key_identifier(self):
        signer_cert, signer_key = _client_identity("SKI signer", add_ski=True)
        message = asn1crypto.cms.ContentInfo.load(
            create_signed_pkcs7(b"payload", signer_key, signer_cert)
        )
        signed_data = message["content"]
        signer_info = signed_data["signer_infos"][0]
        signer_info["version"] = "v3"
        signer_info["sid"] = {
            "subject_key_identifier": signer_cert.extensions.get_extension_for_class(
                x509.SubjectKeyIdentifier
            ).value.digest,
        }

        selected = extract_signer_certificate(signed_data)

        assert selected is not None
        assert selected.serial_number == signer_cert.serial_number

    def test_mismatched_signer_identifier_returns_bad_message_check(
        self, app, create_ca
    ):
        ca_data = create_ca(cn="SCEP SID Guard CA")
        nonce = b"sid-guard-nonce!"
        with app.app_context():
            ca, ca_cert, _ = _load_ca_material(ca_data["id"])
            signer_cert, signer_key = _client_identity()
            request = asn1crypto.cms.ContentInfo.load(_build_request(
                ca_cert, signer_cert, signer_key, 21,
                _issuer_and_serial(ca_cert), nonce,
            ))
            signer_info = request["content"]["signer_infos"][0]
            signer_info["sid"] = {
                "issuer_and_serial_number": {
                    "issuer": asn1crypto.x509.Certificate.load(
                        signer_cert.public_bytes(serialization.Encoding.DER)
                    ).issuer,
                    "serial_number": signer_cert.serial_number + 1,
                },
            }
            assert extract_signer_certificate(request["content"]) is None
            response, status = SCEPService(ca.refid).process_pkcs_req(
                request.dump(), "127.0.0.1"
            )

        attrs = _response_attributes(response)
        assert status == 200
        assert attrs[PKI_STATUS_OID] == "2"
        assert attrs[FAIL_INFO_OID] == "1"

    def test_non_enveloped_message_data_returns_bad_message_check(
        self, app, create_ca
    ):
        ca_data = create_ca(cn="SCEP Plaintext Guard CA")
        nonce = b"plaintext-guard!"
        with app.app_context():
            ca, ca_cert, _ = _load_ca_material(ca_data["id"])
            signer_cert, signer_key = _client_identity()
            valid = asn1crypto.cms.ContentInfo.load(_build_request(
                ca_cert, signer_cert, signer_key, 21,
                _issuer_and_serial(ca_cert), nonce,
            ))
            attrs = list(valid["content"]["signer_infos"][0]["signed_attrs"])
            request = create_signed_pkcs7(
                _issuer_and_serial(ca_cert),
                signer_key,
                signer_cert,
                signed_attributes=[
                    attr for attr in attrs
                    if attr["type"].native not in {
                        "content_type", "message_digest", "signing_time"
                    }
                ],
            )
            response, status = SCEPService(ca.refid).process_pkcs_req(
                request, "127.0.0.1"
            )

        response_attrs = _response_attributes(response)
        assert status == 200
        assert response_attrs[PKI_STATUS_OID] == "2"
        assert response_attrs[FAIL_INFO_OID] == "1"

    def test_encrypted_content_type_must_be_data(self, app, create_ca):
        ca_data = create_ca(cn="SCEP Inner Content Type CA")
        nonce = b"inner-type-guard"
        with app.app_context():
            ca, ca_cert, _ = _load_ca_material(ca_data["id"])
            signer_cert, signer_key = _client_identity()
            valid = asn1crypto.cms.ContentInfo.load(_build_request(
                ca_cert, signer_cert, signer_key, 21,
                _issuer_and_serial(ca_cert), nonce,
            ))
            envelope = asn1crypto.cms.ContentInfo.load(
                valid["content"]["encap_content_info"]["content"].native
            )
            envelope["content"]["encrypted_content_info"][
                "content_type"
            ] = "signed_data"
            attrs = list(valid["content"]["signer_infos"][0]["signed_attrs"])
            request = create_signed_pkcs7(
                envelope.dump(),
                signer_key,
                signer_cert,
                signed_attributes=[
                    attr for attr in attrs
                    if attr["type"].native not in {
                        "content_type", "message_digest", "signing_time"
                    }
                ],
            )
            response, status = SCEPService(ca.refid).process_pkcs_req(
                request, "127.0.0.1"
            )

        response_attrs = _response_attributes(response)
        assert status == 200
        assert response_attrs[PKI_STATUS_OID] == "2"
        assert response_attrs[FAIL_INFO_OID] == "1"

    def test_recipient_identifier_must_match_configured_ca(self, app, create_ca):
        ca_data = create_ca(cn="SCEP Recipient Guard CA")
        nonce = b"recipient-guard!"
        with app.app_context():
            ca, ca_cert, _ = _load_ca_material(ca_data["id"])
            other_cert, _ = _client_identity("wrong envelope recipient")
            signer_cert, signer_key = _client_identity()
            request = _build_request(
                ca_cert, signer_cert, signer_key, 21,
                _issuer_and_serial(ca_cert), nonce,
                recipient_cert=other_cert,
            )
            response, status = SCEPService(ca.refid).process_pkcs_req(
                request, "127.0.0.1"
            )

        attrs = _response_attributes(response)
        assert status == 200
        assert attrs[PKI_STATUS_OID] == "2"
        assert attrs[FAIL_INFO_OID] == "1"


class TestScepResponseEncryption:
    @pytest.mark.parametrize(
        ("algorithm", "expected"),
        [("aes128_cbc", "aes128_cbc"), ("aes256_cbc", "aes256_cbc")],
    )
    def test_aes_cbc_round_trip_and_algorithm_selection(
        self, algorithm, expected
    ):
        recipient_cert, recipient_key = _client_identity()
        envelope_bytes = encrypt_for_client(
            b"SCEP encrypted payload",
            recipient_cert,
            content_encryption_algorithm=algorithm,
        )
        envelope = asn1crypto.cms.ContentInfo.load(envelope_bytes)["content"]

        assert envelope["encrypted_content_info"][
            "content_encryption_algorithm"
        ]["algorithm"].native == expected
        assert decrypt_scep_envelope(
            envelope_bytes, recipient_key, recipient_cert
        ) == b"SCEP encrypted payload"

    def test_aes256_request_selects_aes256_response(self, app, create_ca, create_cert):
        ca_data = create_ca(cn="SCEP AES256 Selection CA")
        cert_data = create_cert(cn="scep-aes256.example", ca_id=ca_data["id"])
        nonce = b"aes256-response!"
        with app.app_context():
            ca, ca_cert, _ = _load_ca_material(ca_data["id"])
            cert_row = db.session.get(Certificate, cert_data["id"])
            issued_cert = x509.load_pem_x509_certificate(
                base64.b64decode(cert_row.crt), default_backend()
            )
            signer_cert, signer_key = _client_identity()
            request = _build_request(
                ca_cert, signer_cert, signer_key, 21,
                _issuer_and_serial(issued_cert), nonce,
                content_encryption_algorithm="aes256_cbc",
            )
            response, status = SCEPService(ca.refid).process_pkcs_req(
                request, "127.0.0.1"
            )

        response_signed_data = asn1crypto.cms.ContentInfo.load(response)["content"]
        response_envelope = asn1crypto.cms.ContentInfo.load(
            response_signed_data["encap_content_info"]["content"].native
        )["content"]
        assert status == 200
        assert response_envelope["encrypted_content_info"][
            "content_encryption_algorithm"
        ]["algorithm"].native == "aes256_cbc"

    def test_ec_client_receives_password_recipient_info(
        self, app, create_ca
    ):
        ca_data = create_ca(cn="SCEP EC Password Recipient CA")
        challenge = "correct horse battery staple"
        nonce = b"ec-password-pwri"
        ec_key = ec.generate_private_key(ec.SECP256R1())
        ec_cert, _ = _client_identity("EC SCEP client", key=ec_key)
        csr = (
            x509.CertificateSigningRequestBuilder()
            .subject_name(ec_cert.subject)
            .add_attribute(
                AttributeOID.CHALLENGE_PASSWORD,
                challenge.encode("utf-8"),
            )
            .sign(ec_key, hashes.SHA256())
        )

        with app.app_context():
            ca, ca_cert, _ = _load_ca_material(ca_data["id"])
            request = _build_request(
                ca_cert,
                ec_cert,
                ec_key,
                19,
                csr.public_bytes(serialization.Encoding.DER),
                nonce,
            )
            response, status = SCEPService(
                ca.refid,
                challenge_password=challenge,
                auto_approve=True,
            ).process_pkcs_req(request, "127.0.0.1")

        plaintext, recipient_info, envelope = _decrypt_password_response(
            response, challenge
        )
        certs = pkcs7.load_der_pkcs7_certificates(plaintext)
        attrs = _response_attributes(response)
        assert status == 200
        assert attrs[PKI_STATUS_OID] == "0"
        assert recipient_info.name == "pwri"
        assert envelope["version"].native == "v3"
        assert len(certs) == 2

    def test_ec_client_without_challenge_receives_bad_message_check(
        self, app, create_ca, create_cert
    ):
        ca_data = create_ca(cn="SCEP EC Missing Challenge CA")
        cert_data = create_cert(cn="scep-ec-no-password.example", ca_id=ca_data["id"])
        nonce = b"ec-no-password!!"
        ec_key = ec.generate_private_key(ec.SECP256R1())
        ec_cert, _ = _client_identity("EC client without password", key=ec_key)

        with app.app_context():
            ca, ca_cert, _ = _load_ca_material(ca_data["id"])
            cert_row = db.session.get(Certificate, cert_data["id"])
            issued_cert = x509.load_pem_x509_certificate(
                base64.b64decode(cert_row.crt), default_backend()
            )
            request = _build_request(
                ca_cert, ec_cert, ec_key, 21,
                _issuer_and_serial(issued_cert), nonce,
            )
            response, status = SCEPService(ca.refid).process_pkcs_req(
                request, "127.0.0.1"
            )

        attrs = _response_attributes(response)
        assert status == 200
        assert attrs[PKI_STATUS_OID] == "2"
        assert attrs[FAIL_INFO_OID] == "1"


class TestScepGetCert:
    def test_get_cert_returns_requested_certificate_encrypted_for_signer(
        self, app, create_ca, create_cert
    ):
        ca_data = create_ca(cn="SCEP GetCert CA")
        cert_data = create_cert(cn="scep-getcert.example", ca_id=ca_data["id"])
        nonce = b"get-cert-nonce!!"

        with app.app_context():
            ca, ca_cert, _ = _load_ca_material(ca_data["id"])
            cert_row = db.session.get(Certificate, cert_data["id"])
            issued_cert = x509.load_pem_x509_certificate(
                base64.b64decode(cert_row.crt), default_backend()
            )
            signer_cert, signer_key = _client_identity()
            request = _build_request(
                ca_cert, signer_cert, signer_key, 21,
                _issuer_and_serial(issued_cert), nonce,
            )
            response, status = SCEPService(ca.refid).process_pkcs_req(request, "127.0.0.1")

        attrs = _response_attributes(response)
        certs = pkcs7.load_der_pkcs7_certificates(
            _decrypt_response(response, signer_key, signer_cert)
        )
        assert status == 200
        assert attrs[PKI_STATUS_OID] == "0"
        assert attrs[TRANSACTION_ID_OID] == "txn-21"
        assert attrs[RECIPIENT_NONCE_OID] == nonce
        assert issued_cert.serial_number in {cert.serial_number for cert in certs}

    def test_get_cert_unknown_serial_returns_bad_cert_id(self, app, create_ca):
        ca_data = create_ca(cn="SCEP GetCert Missing CA")
        nonce = b"missing-cert-id!"
        with app.app_context():
            ca, ca_cert, _ = _load_ca_material(ca_data["id"])
            signer_cert, signer_key = _client_identity()
            requested = asn1crypto.cms.IssuerAndSerialNumber.load(
                _issuer_and_serial(ca_cert)
            )
            requested["issuer"] = asn1crypto.x509.Certificate.load(
                ca_cert.public_bytes(serialization.Encoding.DER)
            ).subject
            requested["serial_number"] = ca_cert.serial_number + 1
            request = _build_request(
                ca_cert, signer_cert, signer_key, 21, requested.dump(), nonce
            )
            response, _ = SCEPService(ca.refid).process_pkcs_req(request, "127.0.0.1")

        attrs = _response_attributes(response)
        assert attrs[PKI_STATUS_OID] == "2"
        assert attrs[FAIL_INFO_OID] == "4"
        assert attrs[TRANSACTION_ID_OID] == "txn-21"


class TestScepGetCrl:
    def test_get_crl_returns_current_crl_in_degenerate_signed_data(
        self, app, create_ca
    ):
        ca_data = create_ca(cn="SCEP GetCRL CA")
        nonce = b"get-crl-nonce!!!"
        with app.app_context():
            ca, ca_cert, _ = _load_ca_material(ca_data["id"])
            expected = CRLService.generate_crl(ca.id, username="scep-test")
            signer_cert, signer_key = _client_identity()
            # RFC-correct identifier: CA subject + an arbitrary leaf serial that
            # is NOT the CA's own serial — the serial must be ignored.
            request = _build_request(
                ca_cert, signer_cert, signer_key, 22,
                _crl_issuer_and_serial(ca_cert, 0xDEADBEEF), nonce,
            )
            response, status = SCEPService(ca.refid).process_pkcs_req(request, "127.0.0.1")

        attrs = _response_attributes(response)
        degenerate = asn1crypto.cms.ContentInfo.load(
            _decrypt_response(response, signer_key, signer_cert)
        )
        crls = degenerate["content"]["crls"]
        assert status == 200
        assert attrs[PKI_STATUS_OID] == "0"
        assert attrs[RECIPIENT_NONCE_OID] == nonce
        assert len(crls) == 1
        assert crls[0].chosen.dump() == expected.crl_der

    def test_get_crl_without_available_crl_returns_bad_cert_id(
        self, app, create_ca, monkeypatch
    ):
        ca_data = create_ca(cn="SCEP GetCRL Missing CA")
        nonce = b"no-crl-available"
        with app.app_context():
            ca, ca_cert, _ = _load_ca_material(ca_data["id"])
            signer_cert, signer_key = _client_identity()
            request = _build_request(
                ca_cert, signer_cert, signer_key, 22,
                _crl_issuer_and_serial(ca_cert, 0xDEADBEEF), nonce,
            )
            monkeypatch.setattr(CRLService, "get_latest_crl", lambda _ca_id: None)
            monkeypatch.setattr(CRLService, "generate_crl", lambda _ca_id, **_kwargs: None)
            response, _ = SCEPService(ca.refid).process_pkcs_req(request, "127.0.0.1")

        attrs = _response_attributes(response)
        assert attrs[PKI_STATUS_OID] == "2"
        assert attrs[FAIL_INFO_OID] == "4"
        assert attrs[TRANSACTION_ID_OID] == "txn-22"


class TestScepCaCertificateAndCapabilities:
    def test_root_get_ca_cert_remains_single_der(self, app, client, create_ca):
        root = create_ca(cn="SCEP Root GetCACert")
        with app.app_context():
            _set_config("scep_ca_id", root["id"])
        try:
            response = client.get("/scep/pkiclient.exe?operation=GetCACert")
            cert = x509.load_der_x509_certificate(response.data)
            assert response.status_code == 200
            assert response.content_type == "application/x-x509-ca-cert"
            assert cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == "SCEP Root GetCACert"
        finally:
            with app.app_context():
                _clear_config("scep_ca_id")

    def test_intermediate_get_ca_cert_returns_full_chain(self, app, client, auth_client, create_ca):
        root = create_ca(cn="SCEP Chain Root")
        response = auth_client.post("/api/v2/cas", json={
            "type": "intermediate",
            "commonName": "SCEP Chain Intermediate",
            "organization": "Test Org",
            "country": "US",
            "state": "CA",
            "locality": "Test City",
            "keyType": "RSA",
            "keySize": 2048,
            "validityYears": 5,
            "hashAlgorithm": "sha256",
            "parentCAId": root["id"],
        })
        assert response.status_code == 201
        intermediate = response.get_json()["data"]

        with app.app_context():
            _set_config("scep_ca_id", intermediate["id"])
            root_serial = _load_ca_material(root["id"])[1].serial_number
            intermediate_serial = _load_ca_material(intermediate["id"])[1].serial_number
        try:
            # Default: single CA cert (Apple clients choke on ca-ra-cert)
            response = client.get("/scep/pkiclient.exe?operation=GetCACert")
            assert response.status_code == 200
            assert response.content_type == "application/x-x509-ca-cert"
            single = x509.load_der_x509_certificate(response.data)
            assert single.serial_number == intermediate_serial

            # Opt-in: full chain as degenerate PKCS#7 (RFC 8894 §4.2.1)
            with app.app_context():
                _set_config("scep_getcacert_chain", "true")
            response = client.get("/scep/pkiclient.exe?operation=GetCACert")
            certs = pkcs7.load_der_pkcs7_certificates(response.data)
            assert response.status_code == 200
            assert response.content_type == "application/x-x509-ca-ra-cert"
            assert {cert.serial_number for cert in certs} == {
                root_serial, intermediate_serial,
            }
        finally:
            with app.app_context():
                _clear_config("scep_ca_id")
                _clear_config("scep_getcacert_chain")

    def test_get_ca_caps_advertises_implemented_standard_features(self, client):
        response = client.get("/scep/pkiclient.exe?operation=GetCACaps")
        capabilities = set(response.get_data(as_text=True).splitlines())
        assert response.status_code == 200
        assert "AES-256" not in capabilities
        assert {
            "AES",
            "POSTPKIOperation",
            "SHA-256",
            "Renewal",
            "GetNextCACert",
            "SCEPStandard",
        } <= capabilities
