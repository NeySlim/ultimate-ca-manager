"""RFC 8894 coverage for SCEP certificate/CRL access and message guards."""
import base64
from datetime import datetime, timedelta, timezone

import asn1crypto.cms
import asn1crypto.core
import asn1crypto.x509
import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import NameOID

from models import CA, Certificate, SystemConfig, db
from services.crl_service import CRLService
from services.scep.crypto_helpers import create_signed_pkcs7, encrypt_for_client
from services.scep.message_parser import decrypt_scep_envelope
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


def _client_identity(common_name="SCEP requester"):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
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
        .sign(key, hashes.SHA256())
    )
    return cert, key


def _issuer_and_serial(cert):
    cert_asn1 = asn1crypto.x509.Certificate.load(
        cert.public_bytes(serialization.Encoding.DER)
    )
    return asn1crypto.cms.IssuerAndSerialNumber({
        "issuer": cert_asn1.issuer,
        "serial_number": cert.serial_number,
    }).dump()


def _build_request(ca_cert, signer_cert, signer_key, message_type, payload, nonce):
    encrypted_payload = encrypt_for_client(payload, ca_cert)
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


def _decrypt_response(response, client_key):
    signed_data = asn1crypto.cms.ContentInfo.load(response)["content"]
    encrypted = signed_data["encap_content_info"]["content"].native
    return decrypt_scep_envelope(encrypted, client_key)


class TestScepSignedAttributeGuards:
    @pytest.mark.parametrize("nonce", [None, b"short nonce"])
    def test_sender_nonce_is_mandatory_and_exactly_16_bytes(
        self, app, create_ca, nonce
    ):
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
        assert attrs[PKI_STATUS_OID] == "2"
        assert attrs[FAIL_INFO_OID] == "1"
        assert attrs[TRANSACTION_ID_OID] == "txn-21"
        if nonce is None:
            assert RECIPIENT_NONCE_OID not in attrs
        else:
            assert attrs[RECIPIENT_NONCE_OID] == nonce

    @pytest.mark.parametrize("mode", ["missing", "stale", "future"])
    def test_signing_time_is_required_and_within_ten_minutes(
        self, app, create_ca, mode
    ):
        ca_data = create_ca(cn=f"SCEP Signing Time {mode}")
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
        assert attrs[PKI_STATUS_OID] == "2"
        assert attrs[FAIL_INFO_OID] == "3"
        assert attrs[TRANSACTION_ID_OID] == "txn-21"
        assert attrs[RECIPIENT_NONCE_OID] == nonce


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
        certs = pkcs7.load_der_pkcs7_certificates(_decrypt_response(response, signer_key))
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
            request = _build_request(
                ca_cert, signer_cert, signer_key, 22,
                _issuer_and_serial(ca_cert), nonce,
            )
            response, status = SCEPService(ca.refid).process_pkcs_req(request, "127.0.0.1")

        attrs = _response_attributes(response)
        degenerate = asn1crypto.cms.ContentInfo.load(_decrypt_response(response, signer_key))
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
                _issuer_and_serial(ca_cert), nonce,
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
            expected_serials = {
                _load_ca_material(root["id"])[1].serial_number,
                _load_ca_material(intermediate["id"])[1].serial_number,
            }
        try:
            response = client.get("/scep/pkiclient.exe?operation=GetCACert")
            certs = pkcs7.load_der_pkcs7_certificates(response.data)
            assert response.status_code == 200
            assert response.content_type == "application/x-x509-ca-ra-cert"
            assert {cert.serial_number for cert in certs} == expected_serials
        finally:
            with app.app_context():
                _clear_config("scep_ca_id")

    def test_get_ca_caps_advertises_implemented_standard_features(self, client):
        response = client.get("/scep/pkiclient.exe?operation=GetCACaps")
        capabilities = set(response.get_data(as_text=True).splitlines())
        assert response.status_code == 200
        assert {
            "AES",
            "POSTPKIOperation",
            "SHA-256",
            "Renewal",
            "GetNextCACert",
            "SCEPStandard",
        } <= capabilities
