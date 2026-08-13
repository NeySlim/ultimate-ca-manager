"""Intune SCEP challenge validation hooked into SCEPService (issue #228 part 2).

Drives SCEPService.process_pkcs_req directly with a real PKCSReq message
(same low-level helpers as test_scep_rfc8894_operations.py), using a fake
IntuneScepClient double rather than mocking `requests` -- the wire-format
correctness of the real client is covered by test_intune_scep_client.py, so
this file is purely about scep_service.py's own orchestration: does it call
validate/notify in the right order, does a notify failure actually roll back
the persisted cert, does a validated request bypass the "no challenge
configured" guard meant for the static-password path.
"""
import base64

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from models import db, Certificate, SCEPRequest
from services.scep.intune_client import IntuneScepError, IntuneScepErrorCode
from services.scep.scep_service import SCEPService
from tests.test_scep_rfc8894_operations import (
    _build_request, _load_ca_material, _client_identity, _response_attributes,
    PKI_STATUS_OID, FAIL_INFO_OID,
)

MSG_TYPE_PKI_REQ = 19


class _FakeIntuneClient:
    def __init__(self, validate_ok=True, notify_ok=True):
        self.validate_ok = validate_ok
        self.notify_ok = notify_ok
        self.validate_calls = []
        self.success_notify_calls = []
        self.failure_notify_calls = []

    def validate_request(self, transaction_id, der_csr):
        self.validate_calls.append((transaction_id, der_csr))
        if not self.validate_ok:
            raise IntuneScepError(
                "validation failed", code=IntuneScepErrorCode.CHALLENGE_EXPIRED,
                description="too old",
            )

    def send_success_notification(self, transaction_id, der_csr, cert):
        self.success_notify_calls.append((transaction_id, der_csr, cert))
        if not self.notify_ok:
            raise IntuneScepError("notify failed")

    def send_failure_notification(self, transaction_id, der_csr, hresult, description):
        self.failure_notify_calls.append((transaction_id, der_csr, hresult, description))


def _build_pkcs_req(ca_cert, nonce=b"intune-test-nonce"):
    signer_cert, signer_key = _client_identity("intune-device.test")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'intune-device.test')]))
        .sign(key, hashes.SHA256())
    )
    csr_der = csr.public_bytes(serialization.Encoding.DER)
    request = _build_request(ca_cert, signer_cert, signer_key, MSG_TYPE_PKI_REQ, csr_der, nonce)
    return request, csr_der


class TestIntuneChallengeValidation:

    def test_validate_failure_rejects_without_persisting(self, app, create_ca):
        ca_data = create_ca(cn="Intune Validate Fail CA")
        with app.app_context():
            ca, ca_cert, _ = _load_ca_material(ca_data["id"])
            fake = _FakeIntuneClient(validate_ok=False)
            request, csr_der = _build_pkcs_req(ca_cert)

            response, status = SCEPService(
                ca.refid, auto_approve=True, intune_client=fake,
            ).process_pkcs_req(request, "127.0.0.1")

            attrs = _response_attributes(response)
            assert status == 200
            assert attrs[PKI_STATUS_OID] == "2"
            assert attrs[FAIL_INFO_OID] == "1"  # FAIL_BAD_MESSAGE_CHECK
            assert len(fake.validate_calls) == 1
            assert fake.success_notify_calls == []
            assert SCEPRequest.query.filter_by(ca_refid=ca.refid).count() == 0
            assert Certificate.query.filter_by(caref=ca.refid).count() == 0

    def test_notify_failure_rolls_back_already_signed_cert(self, app, create_ca):
        ca_data = create_ca(cn="Intune Notify Fail CA")
        with app.app_context():
            ca, ca_cert, _ = _load_ca_material(ca_data["id"])
            fake = _FakeIntuneClient(validate_ok=True, notify_ok=False)
            request, csr_der = _build_pkcs_req(ca_cert)

            response, status = SCEPService(
                ca.refid, auto_approve=True, intune_client=fake,
            ).process_pkcs_req(request, "127.0.0.1")

            attrs = _response_attributes(response)
            assert status == 200
            assert attrs[PKI_STATUS_OID] == "2"
            assert attrs[FAIL_INFO_OID] == "2"  # FAIL_BAD_REQUEST -> server error mapping
            assert len(fake.validate_calls) == 1
            # The cert WAS signed (send_success_notification received a real
            # x509.Certificate) but must not have survived the rollback.
            assert len(fake.success_notify_calls) == 1
            _txn, _csr, cert_obj = fake.success_notify_calls[0]
            assert isinstance(cert_obj, x509.Certificate)
            assert SCEPRequest.query.filter_by(ca_refid=ca.refid).count() == 0
            assert Certificate.query.filter_by(caref=ca.refid).count() == 0

    def test_success_notifies_before_returning_cert(self, app, create_ca):
        ca_data = create_ca(cn="Intune Success CA")
        with app.app_context():
            ca, ca_cert, _ = _load_ca_material(ca_data["id"])
            fake = _FakeIntuneClient(validate_ok=True, notify_ok=True)
            request, csr_der = _build_pkcs_req(ca_cert)

            response, status = SCEPService(
                ca.refid, auto_approve=True, intune_client=fake,
            ).process_pkcs_req(request, "127.0.0.1")

            attrs = _response_attributes(response)
            assert status == 200
            assert attrs[PKI_STATUS_OID] == "0"
            assert len(fake.validate_calls) == 1
            assert len(fake.success_notify_calls) == 1
            assert fake.failure_notify_calls == []

            scep_req = SCEPRequest.query.filter_by(ca_refid=ca.refid).first()
            assert scep_req is not None
            assert scep_req.status == "approved"
            cert_row = Certificate.query.filter_by(refid=scep_req.cert_refid).first()
            assert cert_row is not None

            # The certificate object Intune was notified about must be the
            # exact same one that got persisted and returned.
            _txn, _csr, notified_cert = fake.success_notify_calls[0]
            persisted_cert = x509.load_pem_x509_certificate(
                base64.b64decode(cert_row.crt), default_backend()
            )
            assert notified_cert.serial_number == persisted_cert.serial_number

    def test_no_static_challenge_required_when_intune_bound(self, app, create_ca):
        """The generic 'no challenge + auto-approve = anonymous cert' guard
        must not fire for Intune profiles -- self.challenge_password is
        legitimately empty there since Intune supplies its own per-device
        challenge, validated above via a different mechanism entirely."""
        ca_data = create_ca(cn="Intune No Static Challenge CA")
        with app.app_context():
            ca, ca_cert, _ = _load_ca_material(ca_data["id"])
            fake = _FakeIntuneClient(validate_ok=True, notify_ok=True)
            request, csr_der = _build_pkcs_req(ca_cert)

            response, status = SCEPService(
                ca.refid, auto_approve=True, challenge_password=None,
                intune_client=fake,
            ).process_pkcs_req(request, "127.0.0.1")

            attrs = _response_attributes(response)
            assert status == 200
            assert attrs[PKI_STATUS_OID] == "0"

    def test_signing_failure_after_validation_sends_failure_notification(
        self, app, create_ca
    ):
        """A CA-signing error occurring after Intune already validated the
        request must still notify Intune (best-effort) that issuance failed,
        not just silently return a SCEP error."""
        ca_data = create_ca(cn="Intune Signing Fail CA")
        with app.app_context():
            ca, ca_cert, _ = _load_ca_material(ca_data["id"])
            from models import CA
            ca_row = db.session.get(CA, ca_data["id"])
            ca_row.offline = True
            ca_row.offline_reason = "test-forced-offline"
            db.session.commit()

            fake = _FakeIntuneClient(validate_ok=True, notify_ok=True)
            request, csr_der = _build_pkcs_req(ca_cert)

            response, status = SCEPService(
                ca.refid, auto_approve=True, intune_client=fake,
            ).process_pkcs_req(request, "127.0.0.1")

            attrs = _response_attributes(response)
            assert status == 200
            assert attrs[PKI_STATUS_OID] == "2"
            assert len(fake.validate_calls) == 1
            assert fake.success_notify_calls == []
            assert len(fake.failure_notify_calls) == 1
            _txn, _csr, hresult, description = fake.failure_notify_calls[0]
            assert hresult == 0x80004005
            assert "offline" in description.lower()
