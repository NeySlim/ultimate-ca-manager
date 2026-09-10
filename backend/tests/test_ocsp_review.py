"""OCSP, issuance and approval: findings of the independent review of #347's
changes (self-review batch)."""
import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509 import ocsp
from cryptography.x509.oid import ExtendedKeyUsageOID, ExtensionOID, NameOID

from models import db, CA, Certificate, SystemConfig
from services.ocsp_service import OCSPService

from tests.test_ocsp_service import (  # noqa: E402
    _ca_model, _load_x509, _delegated_certificate, _configure_delegated_responder,
)
from tests.test_ca_service_hsm import _patch_hsm, hsm_provider_and_key  # noqa: E402,F401


def _gen():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _leaf(cn, key, issuer_cert, signer, serial=None, days=30):
    now = datetime.now(timezone.utc)
    return (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
            .issuer_name(issuer_cert.subject).public_key(key.public_key())
            .serial_number(serial or x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=days))
            .sign(signer, hashes.SHA256()))


def _store_leaf(cert, key, caref, serial_number, **extra):
    row = Certificate(
        refid=f'ocsp-review-{cert.serial_number}', descr='leaf', caref=caref,
        crt=base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode(),
        prv=base64.b64encode(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                               serialization.NoEncryption())).decode(),
        serial_number=serial_number, subject=cert.subject.rfc4514_string(), issuer=cert.issuer.rfc4514_string(),
        **extra)
    db.session.add(row); db.session.commit()
    return row


class TestHsmCaSingleResponse:
    def test_single_and_multi_responses_from_an_hsm_ca(self, app, hsm_provider_and_key):
        """An HSM-backed CA answered internalError on the single-CertID path
        (unregistered key wrapper) while the multi path answered good."""
        fx = hsm_provider_and_key
        with app.app_context():
            now = datetime.now(timezone.utc)
            name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'HSM OCSP CA')])
            ca_cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                       .public_key(fx['real_key'].public_key()).serial_number(x509.random_serial_number())
                       .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=365))
                       .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                       .sign(fx['real_key'], hashes.SHA256()))
            ca = CA(refid='hsm-ocsp-ca', descr='HSM OCSP CA', serial=0, prv=None, hsm_key_id=fx['hsm_key_id'],
                    crt=base64.b64encode(ca_cert.public_bytes(serialization.Encoding.PEM)).decode(),
                    subject=name.rfc4514_string(), issuer=name.rfc4514_string(), ocsp_enabled=True)
            db.session.add(ca); db.session.commit()
            key = _gen()
            leaf = _leaf('hsm-leaf.example.com', key, ca_cert, fx['real_key'])
            _store_leaf(leaf, key, ca.refid, str(leaf.serial_number))
            patches = _patch_hsm(fx['real_key'], fx['pub_pem'])
            for p in patches: p.start()
            try:
                der, status = OCSPService().generate_response(ca, leaf.serial_number)
                assert status == 'good'
                resp = ocsp.load_der_ocsp_response(der)
                assert resp.response_status == ocsp.OCSPResponseStatus.SUCCESSFUL
                fx['real_key'].public_key().verify(resp.signature, resp.tbs_response_bytes,
                                                    __import__('cryptography.hazmat.primitives.asymmetric.padding', fromlist=['PKCS1v15']).PKCS1v15(), hashes.SHA256())
            finally:
                for p in patches: p.stop()


class TestNextUpdateBoundByResponder:
    def test_next_update_never_outlives_the_delegated_responder(self, app, auth_client, create_ca, create_cert):
        with app.app_context():
            ca = create_ca(cn='Short Responder CA')
            leaf = create_cert(cn='leaf-short.example.com', ca_id=ca['id'])
            ca_obj = _ca_model(ca); ca_cert = _load_x509(ca_obj)
            from services.hsm.ca_key_loader import get_ca_signing_key
            key = _gen()
            now = datetime.now(timezone.utc)
            resp_cert = _delegated_certificate(ca_cert, get_ca_signing_key(ca_obj), key,
                                               not_after=now + timedelta(hours=1))
            row = db.session.get(Certificate, leaf['id'])
            responder_row = Certificate(refid='short-resp', descr='short', caref=ca_obj.refid,
                                        serial_number=str(resp_cert.serial_number))
            db.session.add(responder_row); db.session.commit()
            _configure_delegated_responder(ca_obj, responder_row, resp_cert, key)
            serial = int(row.serial_number, 16)
            der, status = OCSPService().generate_response(ca_obj, serial)
            assert status == 'good'
            resp = ocsp.load_der_ocsp_response(der)
            assert resp.next_update_utc <= resp_cert.not_valid_after_utc
            assert resp.next_update_utc > resp.this_update_utc


class TestSerialLookupVerifiedByCertificate:
    def test_decimal_ten_and_hex_ten_are_told_apart(self, app, create_ca):
        with app.app_context():
            ca = create_ca(cn='Serial Ambiguity CA')
            ca_obj = _ca_model(ca); ca_cert = _load_x509(ca_obj)
            from services.hsm.ca_key_loader import get_ca_signing_key
            ca_key = get_ca_signing_key(ca_obj)
            k10, k16 = _gen(), _gen()
            ten = _leaf('ten.example.com', k10, ca_cert, ca_key, serial=10)
            sixteen = _leaf('sixteen.example.com', k16, ca_cert, ca_key, serial=16)
            _store_leaf(ten, k10, ca_obj.refid, '10', revoked=True, revoke_reason='keyCompromise')
            _store_leaf(sixteen, k16, ca_obj.refid, '16')
            record, status, _, _ = OCSPService._status_for_serial(ca_obj, 16)
            assert status == 'good' and record.serial_number == '16'
            record, status, _, _ = OCSPService._status_for_serial(ca_obj, 10)
            assert status == 'revoked'


class TestChildCaFoundBySignature:
    def test_sub_ca_with_stale_caref_is_still_good(self, app, create_ca):
        with app.app_context():
            parent = create_ca(cn='Stale Caref Parent')
            other = create_ca(cn='Stale Caref Other')
            p_obj = _ca_model(parent); p_cert = _load_x509(p_obj)
            from services.hsm.ca_key_loader import get_ca_signing_key
            key = _gen()
            now = datetime.now(timezone.utc)
            sub_cert = (x509.CertificateBuilder()
                        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Stale Caref Sub')]))
                        .issuer_name(p_cert.subject).public_key(key.public_key())
                        .serial_number(x509.random_serial_number())
                        .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=30))
                        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                        .sign(get_ca_signing_key(p_obj), hashes.SHA256()))
            sub = CA(refid='stale-caref-sub', descr='Stale Caref Sub', serial=0,
                     crt=base64.b64encode(sub_cert.public_bytes(serialization.Encoding.PEM)).decode(),
                     subject=sub_cert.subject.rfc4514_string(), issuer=sub_cert.issuer.rfc4514_string(),
                     caref=_ca_model(other).refid, serial_number=str(sub_cert.serial_number))
            db.session.add(sub); db.session.commit()
            _, status, _, _ = OCSPService._status_for_serial(p_obj, sub_cert.serial_number)
            assert status == 'good'


class TestResponderBindingLifecycle:
    def test_deleting_the_responder_drops_its_binding(self, app, auth_client, create_ca, create_cert):
        with app.app_context():
            ca = create_ca(cn='Binding Delete CA')
            ca_obj = _ca_model(ca)
            resp = create_cert(cn='resp-delete.example.com', ca_id=ca['id'])
            db.session.add(SystemConfig(key=f"ocsp_responder_cert_{ca['id']}", value=str(resp['id'])))
            row = db.session.get(Certificate, resp['id'])
            row.valid_to = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
            db.session.commit()
            r = auth_client.delete(f"/api/v2/certificates/{resp['id']}")
            assert r.status_code in (200, 204), r.data
            assert SystemConfig.query.filter_by(key=f"ocsp_responder_cert_{ca['id']}").first() is None

    def test_get_names_the_refusal_and_the_signing_error_does_too(self, app, auth_client, create_ca, create_cert):
        with app.app_context():
            ca = create_ca(cn='Refusal Reason CA')
            ca_obj = _ca_model(ca)
            resp = create_cert(cn='resp-refused.example.com', ca_id=ca['id'])   # no OCSPSigning EKU
            db.session.add(SystemConfig(key=f"ocsp_responder_cert_{ca['id']}", value=str(resp['id'])))
            db.session.commit()
            r = auth_client.get(f"/api/v2/cas/{ca['id']}/ocsp-responder")
            body = json.loads(r.data)['data']['responder']
            assert body['id'] == resp['id'] and body['refusal_reason'] and 'OCSPSigning' in body['refusal_reason']
            ca_obj.prv = None; db.session.commit()
            from services.ocsp_service import OCSPSigningUnavailable
            with pytest.raises(OCSPSigningUnavailable) as exc:
                OCSPService()._resolve_signing(ca_obj, _load_x509(ca_obj))
            assert 'refused' in str(exc.value) and 'OCSPSigning' in str(exc.value)


class TestRenewalDropsResponderCache:
    def test_renewing_the_responder_drops_the_ca_cache(self, app, auth_client, create_ca, create_cert):
        from models import OCSPResponse
        with app.app_context():
            ca = create_ca(cn='Renew Responder Cache CA')
            leaf = create_cert(cn='leaf-renew-cache.example.com', ca_id=ca['id'])
            resp = auth_client.post('/api/v2/certificates', data=json.dumps({
                'cn': 'resp-renew-cache.example.com', 'ca_id': ca['id'], 'validity_days': 60,
                'key_type': 'rsa', 'key_size': 2048, 'cert_type': 'custom', 'extra_ekus': ['OCSPSigning']}),
                content_type='application/json')
            resp_id = json.loads(resp.data)['data']['id']
            r = auth_client.post(f"/api/v2/cas/{ca['id']}/ocsp-responder",
                                 data=json.dumps({'certificate_id': resp_id}), content_type='application/json')
            assert r.status_code == 200, r.data
            ca_obj = _ca_model(ca)
            serial = int(db.session.get(Certificate, leaf['id']).serial_number, 16)
            OCSPService().generate_response(ca_obj, serial)
            assert OCSPResponse.query.filter_by(ca_id=ca['id']).count() >= 1
            r = auth_client.post(f"/api/v2/certificates/{resp_id}/renew", data=json.dumps({}), content_type='application/json')
            assert r.status_code == 200, r.data
            assert OCSPResponse.query.filter_by(ca_id=ca['id']).count() == 0


class TestHsmPublicKeyLookupDoesNotCommit:
    def test_lookup_stays_inside_the_callers_transaction(self, app, hsm_provider_and_key):
        from unittest.mock import MagicMock, patch
        from models.hsm import HsmKey
        from services.hsm import HsmService
        fx = hsm_provider_and_key
        with app.app_context():
            HsmKey.query.filter_by(id=fx['hsm_key_id']).update({'public_key_pem': None}); db.session.commit()
            fake = MagicMock(); fake.__enter__.return_value = fake
            fake.get_public_key.return_value = fx['pub_pem']
            marker = SystemConfig(key='zz_review_marker', value='pending')
            db.session.add(marker)
            with patch('services.hsm.hsm_service.HsmService._get_provider_instance', return_value=fake):
                assert HsmService.get_public_key(fx['hsm_key_id']) == fx['pub_pem']
            db.session.rollback()
            assert SystemConfig.query.filter_by(key='zz_review_marker').first() is None
            assert db.session.get(HsmKey, fx['hsm_key_id']).public_key_pem is None


class TestIssuanceStoresEncryptedKeys:
    def test_direct_issuance_encrypts_the_key(self, app, auth_client, create_ca, encryption_enabled):
        ca = create_ca(cn='Encrypted Issue CA')
        r = auth_client.post('/api/v2/certificates', data=json.dumps({
            'cn': 'enc-issue.example.com', 'ca_id': ca['id'], 'validity_days': 30,
            'key_type': 'RSA 2048', 'cert_type': 'server'}), content_type='application/json')
        assert r.status_code in (200, 201), r.data
        with app.app_context():
            from security.encryption import decrypt_private_key
            row = db.session.get(Certificate, json.loads(r.data)['data']['id'])
            assert not base64.b64decode(row.prv, validate=False).startswith(b'-----BEGIN'), 'stored in clear'
            assert base64.b64decode(decrypt_private_key(row.prv)).startswith(b'-----BEGIN')


class TestApprovalIssuesTheRequestedCertificate:
    def test_extra_ekus_honoured_and_approval_linked(self, app, create_ca):
        from tests.test_approval_template_issuance import _issue_from_request, _mk_approval_id, _requester_id
        from models.policy import ApprovalRequest
        ca = create_ca(cn='Approval Extra EKU CA')
        cert, (row_id, _, _, _) = _issue_from_request(app, create_ca, {
            'cn': 'appr-extra.test', 'ca_id': ca['id'], 'cert_type': 'custom',
            'extra_ekus': ['OCSPSigning']})
        eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
        assert list(eku) == [ExtendedKeyUsageOID.OCSP_SIGNING]
        cert.extensions.get_extension_for_oid(ExtensionOID.OCSP_NO_CHECK)
        with app.app_context():
            approval = ApprovalRequest.query.filter_by(certificate_id=row_id).first()
            assert approval is not None, 'approval not linked to the issued certificate'
