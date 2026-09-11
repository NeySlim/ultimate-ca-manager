"""No issuance path signs outside the issuing CA certificate's own validity
window, and none of them lets a leaf outlive the CA.

Before this fix the shared trunk (``TrustStoreService.sign_csr``, reached by
the Sign-CSR API, ACME, EST and WSTEP) neither refused an expired or
not-yet-valid CA certificate nor clamped the leaf to the CA's notAfter; the
mTLS path (``CertificateService.create_certificate``) ignored the CA's
offline flag and turned an expired CA into the issuer of a one-day
certificate; and no path at all compared the CA's notBefore with now.
"""

import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from models import CA, Certificate, db
from services.trust_store.trust_store_service import TrustStoreService
from utils.key_codec import store_pem_bytes


def _ca_material(*, not_before, not_after, cn='Validity Window CA'):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    return cert, key


NOW = datetime.now(timezone.utc)


def _expired():
    return _ca_material(not_before=NOW - timedelta(days=400), not_after=NOW - timedelta(days=1))


def _future():
    return _ca_material(not_before=NOW + timedelta(days=2), not_after=NOW + timedelta(days=400))


def _short_lived(days=10):
    return _ca_material(not_before=NOW - timedelta(days=1), not_after=NOW + timedelta(days=days))


def _csr(cn='leaf.example.test'):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    ).sign(key, hashes.SHA256())


def _install(app, ca_id, cert, key, **flags):
    """Replace a CA row's certificate and key with hand-made material."""
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        ca.crt = base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode()
        ca.prv = store_pem_bytes(key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        for name, value in flags.items():
            setattr(ca, name, value)
        db.session.commit()
        return ca.refid


def _sign(app, csr, ca_cert, ca_key, **kwargs):
    with app.app_context():
        return TrustStoreService.sign_csr(
            csr_pem=csr.public_bytes(serialization.Encoding.PEM),
            ca_cert=ca_cert, ca_private_key=ca_key, **kwargs,
        )


class TestSharedTrunk:

    def test_expired_ca_is_refused(self, app):
        ca_cert, ca_key = _expired()
        with pytest.raises(ValueError, match='expired'):
            _sign(app, _csr(), ca_cert, ca_key, validity_days=30)

    def test_not_yet_valid_ca_is_refused(self, app):
        ca_cert, ca_key = _future()
        with pytest.raises(ValueError, match='not yet valid'):
            _sign(app, _csr(), ca_cert, ca_key, validity_days=30)

    def test_leaf_never_outlives_the_ca(self, app):
        ca_cert, ca_key = _short_lived(10)
        pem = _sign(app, _csr(), ca_cert, ca_key, validity_days=3650)
        leaf = x509.load_pem_x509_certificate(pem, default_backend())
        assert leaf.not_valid_after_utc <= ca_cert.not_valid_after_utc
        assert leaf.not_valid_after_utc > leaf.not_valid_before_utc


class TestProtocolEntryPoint:
    """EST and WSTEP sign through CAService.sign_csr_from_crypto."""

    @pytest.mark.parametrize('material', [_expired, _future])
    def test_ca_outside_its_window_cannot_sign(self, app, create_ca, material):
        from services.ca_service import CAService
        ca_data = create_ca(cn=f'Window protocol {material.__name__}')
        cert, key = material()
        _install(app, ca_data['id'], cert, key)
        with app.app_context():
            ca = db.session.get(CA, ca_data['id'])
            with pytest.raises(Exception, match='expired|not yet valid'):
                CAService.sign_csr_from_crypto(ca=ca, csr=_csr(), validity_days=30, source='est')


class TestMtlsPath:

    def test_offline_ca_is_refused_by_the_service(self, app, create_ca):
        from services.cert_service import CertificateService
        ca_data = create_ca(cn='Window mTLS offline')
        with app.app_context():
            ca = db.session.get(CA, ca_data['id'])
            ca.offline = True
            db.session.commit()
            with pytest.raises(ValueError, match='offline'):
                CertificateService.create_certificate(
                    descr='x', caref=ca.refid, dn={'CN': 'x@mtls'}, cert_type='usr_cert',
                    key_type='2048', validity_days=30, username='admin',
                )

    def test_expired_ca_is_refused_by_the_service(self, app, create_ca):
        from services.cert_service import CertificateService
        ca_data = create_ca(cn='Window mTLS expired')
        cert, key = _expired()
        refid = _install(app, ca_data['id'], cert, key)
        with app.app_context():
            with pytest.raises(ValueError, match='expired'):
                CertificateService.create_certificate(
                    descr='x', caref=refid, dn={'CN': 'x@mtls'}, cert_type='usr_cert',
                    key_type='2048', validity_days=30, username='admin',
                )

    def test_offline_ca_is_a_400_on_the_route(self, app, auth_client, create_ca):
        ca_data = create_ca(cn='Window mTLS route')
        with app.app_context():
            ca = db.session.get(CA, ca_data['id'])
            ca.offline = True
            db.session.commit()
        r = auth_client.post('/api/v2/mtls/certificates',
                             data=json.dumps({'ca_id': ca_data['id'], 'name': 'x'}),
                             content_type='application/json')
        assert r.status_code == 400, (r.status_code, r.get_json())


class TestOperatorPaths:

    def test_direct_issue_refuses_a_not_yet_valid_ca(self, app, auth_client, create_ca):
        ca_data = create_ca(cn='Window direct future')
        cert, key = _future()
        _install(app, ca_data['id'], cert, key)
        r = auth_client.post('/api/v2/certificates',
                             data=json.dumps({'cn': 'future.example.test', 'ca_id': ca_data['id'],
                                              'validity_days': 30}),
                             content_type='application/json')
        assert r.status_code == 400, (r.status_code, r.get_json())

    def test_approval_issuance_refuses_a_not_yet_valid_ca(self, app, create_ca):
        from tests.test_approval_template_issuance import _mk_approval_id, _requester_id
        from models.policy import ApprovalRequest
        from api.v2.policies import _issue_approved_certificate
        ca_data = create_ca(cn='Window approval future')
        cert, key = _future()
        _install(app, ca_data['id'], cert, key)
        with app.app_context():
            approval = db.session.get(ApprovalRequest, _mk_approval_id(
                app, _requester_id(app),
                {'cn': 'appr-future.test', 'ca_id': ca_data['id'], 'cert_type': 'server',
                 'validity_days': 30},
            ))
            with pytest.raises(ValueError, match='not yet valid'):
                _issue_approved_certificate(approval)

    def test_renewal_refuses_a_not_yet_valid_ca(self, app, create_ca):
        from services.cert_service import CertificateService
        from services.cert.renewal import RenewalError, renew_certificate_in_place
        ca_data = create_ca(cn='Window renewal future')
        with app.app_context():
            ca = db.session.get(CA, ca_data['id'])
            row = CertificateService.create_certificate(
                descr='renew-me', caref=ca.refid, dn={'CN': 'renew.example.test'},
                cert_type='server_cert', key_type='2048', validity_days=30, username='admin',
            )
            db.session.commit()
            row_id = row.id
        cert, key = _future()
        _install(app, ca_data['id'], cert, key)
        with app.app_context():
            row = db.session.get(Certificate, row_id)
            with pytest.raises(RenewalError, match='not yet valid'):
                renew_certificate_in_place(row, username='admin')
            db.session.rollback()
            db.session.delete(db.session.get(Certificate, row_id))
            db.session.commit()


class TestRemainingIssuers:
    """Follow-up: the issuers the first pass left out."""

    def test_issue_form_refuses_before_queueing_an_approval(self, app, create_ca, create_user):
        from models.policy import ApprovalRequest, CertificatePolicy
        ca_data = create_ca(cn='Window approval queue CA')
        cert, key = _expired()
        _install(app, ca_data['id'], cert, key)
        with app.app_context():
            pol = CertificatePolicy(name=f'window-queue-{ca_data["id"]}', policy_type='issuance',
                                    ca_id=ca_data['id'], requires_approval=True, min_approvers=1,
                                    is_active=True, priority=100)
            pol.set_rules({})
            db.session.add(pol)
            db.session.commit()
            pol_id = pol.id
        user = create_user(role='operator')
        operator = app.test_client()
        r = operator.post('/api/v2/auth/login', data=json.dumps(
            {'username': user['username'], 'password': 'TestPass123!'}), content_type='application/json')
        assert r.status_code == 200
        try:
            r = operator.post('/api/v2/certificates', data=json.dumps(
                {'cn': 'queued.example.test', 'ca_id': ca_data['id'], 'validity_days': 30}),
                content_type='application/json')
            assert r.status_code == 400, (r.status_code, r.get_json())
            with app.app_context():
                assert ApprovalRequest.query.filter_by(policy_id=pol_id).count() == 0
        finally:
            with app.app_context():
                ApprovalRequest.query.filter_by(policy_id=pol_id).delete()
                db.session.delete(db.session.get(CertificatePolicy, pol_id))
                db.session.commit()

    def test_sub_ca_refuses_a_not_yet_valid_parent(self, app, auth_client, create_ca):
        ca_data = create_ca(cn='Window parent future')
        cert, key = _future()
        _install(app, ca_data['id'], cert, key)
        r = auth_client.post('/api/v2/cas', data=json.dumps({
            'type': 'intermediate', 'parentCAId': ca_data['id'],
            'commonName': 'Window child', 'keyType': 'RSA', 'keySize': 2048,
            'validityYears': 1, 'hashAlgorithm': 'sha256',
        }), content_type='application/json')
        assert r.status_code == 400, (r.status_code, r.get_json())

    def test_tsa_signer_refuses_a_not_yet_valid_ca(self, app, create_ca):
        from services import tsa_signer_cert
        ca_data = create_ca(cn='Window TSA future')
        cert, key = _future()
        _install(app, ca_data['id'], cert, key)
        with app.app_context():
            ca = db.session.get(CA, ca_data['id'])
            with pytest.raises(tsa_signer_cert.TsaSignerIssueError, match='not yet valid'):
                tsa_signer_cert.issue_tsa_signer_certificate(ca=ca, cn='window-tsa.example.test')

    def test_ocsp_responder_renewal_refuses_an_expired_ca(self, app, create_ca):
        from services.cert_service import CertificateService
        from services import ocsp_responder_renewal
        ca_data = create_ca(cn='Window responder expired')
        with app.app_context():
            ca = db.session.get(CA, ca_data['id'])
            row = CertificateService.create_certificate(
                descr='responder', caref=ca.refid, dn={'CN': 'responder.example.test'},
                cert_type='server_cert', key_type='2048', validity_days=30, username='admin',
            )
            db.session.commit()
            row_id = row.id
        cert, key = _expired()
        _install(app, ca_data['id'], cert, key)
        with app.app_context():
            ca = db.session.get(CA, ca_data['id'])
            row = db.session.get(Certificate, row_id)
            with pytest.raises(ValueError, match='expired'):
                ocsp_responder_renewal._renew_responder_cert(ca, row)
            db.session.rollback()
            db.session.delete(db.session.get(Certificate, row_id))
            db.session.commit()
