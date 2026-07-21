"""
Microsoft CA certificate lifecycle tests (issue #159 follow-ups)

- Renew of an msca-sourced certificate goes through the AD CS connection
  (resubmits the original CSR) instead of the local re-sign path.
- Revoke of an msca-sourced certificate warns that the revocation is local
  to UCM (Web Enrollment has no revocation endpoint).
"""
import base64
import json
from datetime import timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from tests.conftest import get_json

CONTENT_JSON = 'application/json'
BASE = '/api/v2/certificates'


def post_json(client, url, data):
    return client.post(url, data=json.dumps(data), content_type=CONTENT_JSON)


def _make_key_csr_cert(cn, days=365):
    """Generate a key, a CSR for it, and a matching self-signed 'issued' cert."""
    from utils.datetime_utils import utc_now

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(name)
           .sign(key, hashes.SHA256()))
    now = utc_now()
    cert = (x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Fake ADCS CA')]))
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=days))
            .sign(key, hashes.SHA256()))
    csr_pem = csr.public_bytes(serialization.Encoding.PEM).decode()
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    return key, csr_pem, cert_pem


def _create_msca_cert(app, cn, with_csr=True):
    """Insert a MicrosoftCA connection + an msca-sourced Certificate row
    with its linked issued MSCARequest. Returns (cert_id, msca_id, req_id)."""
    with app.app_context():
        from models import Certificate, db
        from models.msca import MicrosoftCA, MSCARequest

        _, csr_pem, cert_pem = _make_key_csr_cert(cn)

        msca = MicrosoftCA(
            name=f'Test ADCS {cn}',
            server='adcs.test.local',
            auth_method='basic',
            enabled=True,
        )
        db.session.add(msca)
        db.session.flush()

        cert = Certificate(
            refid=f'msca-{cn[:20]}',
            descr=f'MSCA: {cn} (WebServer)',
            crt=base64.b64encode(cert_pem.encode()).decode(),
            csr=base64.b64encode(csr_pem.encode()).decode() if with_csr else None,
            cert_type='server',
            subject=f'CN={cn}',
            subject_cn=cn,
            source='msca',
            imported_from=f'msca:{msca.name}',
        )
        db.session.add(cert)
        db.session.flush()

        req = MSCARequest(
            msca_id=msca.id,
            csr_id=cert.id,
            cert_id=cert.id,
            template='WebServer',
            status='issued',
        )
        db.session.add(req)
        db.session.commit()
        return cert.id, msca.id, req.id


class TestMscaRevokeLocalOnly:
    """Revoking an msca cert works but must flag it as local to UCM."""

    def test_revoke_msca_cert_warns_local_only(self, app, auth_client):
        cert_id, _, _ = _create_msca_cert(app, 'revoke-msca.test.local')

        r = post_json(auth_client, f'{BASE}/{cert_id}/revoke', {'reason': 'unspecified'})
        assert r.status_code == 200
        body = get_json(r)
        assert body['data']['revoked'] is True
        assert body['meta']['msca_local_only'] is True
        assert 'UCM only' in body['message']

    def test_revoke_local_cert_message_unchanged(self, auth_client, create_cert):
        cert = create_cert(cn='revoke-local.example.com')
        r = post_json(auth_client, f"{BASE}/{cert['id']}/revoke", {'reason': 'unspecified'})
        assert r.status_code == 200
        body = get_json(r)
        assert body['message'] == 'Certificate revoked successfully'
        assert 'meta' not in body


class TestMscaRenew:
    """Renew of msca certs resubmits the original CSR via the connection."""

    def test_renew_msca_issued(self, app, auth_client, monkeypatch):
        cert_id, msca_id, req_id = _create_msca_cert(app, 'renew-msca.test.local')

        with app.app_context():
            from models import Certificate, db
            cert = db.session.get(Certificate, cert_id)
            old_serial = cert.serial_number
            # Mark revoked to verify renewal clears the flags
            cert.revoked = True
            cert.revoke_reason = 'superseded'
            db.session.commit()

        _, _, new_cert_pem = _make_key_csr_cert('renew-msca.test.local', days=730)
        captured = {}

        def fake_submit_csr(msca_id, csr_pem, template, csr_id=None,
                            submitted_by=None, enrollee_name=None, enrollee_upn=None):
            captured.update(msca_id=msca_id, template=template, csr_id=csr_id)
            assert 'BEGIN CERTIFICATE REQUEST' in csr_pem
            return {'status': 'issued', 'request_id': req_id, 'cert_pem': new_cert_pem}

        from services.msca_service import MicrosoftCAService
        monkeypatch.setattr(MicrosoftCAService, 'submit_csr', staticmethod(fake_submit_csr))

        r = post_json(auth_client, f'{BASE}/{cert_id}/renew', {})
        assert r.status_code == 200, r.data
        body = get_json(r)
        assert body['meta']['msca_status'] == 'issued'
        assert captured == {'msca_id': msca_id, 'template': 'WebServer', 'csr_id': cert_id}

        with app.app_context():
            from models import Certificate, db
            cert = db.session.get(Certificate, cert_id)
            assert cert.serial_number != old_serial
            assert cert.revoked is False
            assert cert.revoke_reason is None
            assert cert.source == 'msca'
            new_pem = base64.b64decode(cert.crt).decode()
            assert new_pem == new_cert_pem

    def test_renew_msca_pending(self, app, auth_client, monkeypatch):
        cert_id, _, _ = _create_msca_cert(app, 'renew-pending.test.local')

        def fake_submit_csr(**kwargs):
            return {'status': 'pending', 'request_id': None, 'ms_request_id': 42,
                    'message': 'Request pending manager approval'}

        from services.msca_service import MicrosoftCAService
        monkeypatch.setattr(MicrosoftCAService, 'submit_csr', staticmethod(fake_submit_csr))

        r = post_json(auth_client, f'{BASE}/{cert_id}/renew', {})
        assert r.status_code == 200, r.data
        body = get_json(r)
        assert body['meta']['msca_status'] == 'pending'
        assert 'pending' in body['message'].lower()

    def test_renew_msca_without_csr_rekeys(self, app, auth_client, monkeypatch):
        """Imported certs with no CSR/key are renewed by rekey: a fresh key
        pair + CSR with the same subject is generated, stored on the cert,
        and submitted to the connection."""
        cert_id, msca_id, req_id = _create_msca_cert(
            app, 'renew-nocsr.test.local', with_csr=False)
        _, _, new_cert_pem = _make_key_csr_cert('renew-nocsr.test.local', days=730)
        captured = {}

        def fake_submit_csr(msca_id, csr_pem, template, csr_id=None,
                            submitted_by=None, enrollee_name=None, enrollee_upn=None):
            captured['csr_pem'] = csr_pem
            return {'status': 'issued', 'request_id': req_id, 'cert_pem': new_cert_pem}

        from services.msca_service import MicrosoftCAService
        monkeypatch.setattr(MicrosoftCAService, 'submit_csr', staticmethod(fake_submit_csr))

        r = post_json(auth_client, f'{BASE}/{cert_id}/renew', {})
        assert r.status_code == 200, r.data
        assert get_json(r)['meta']['msca_status'] == 'issued'

        # The generated CSR carries the original subject and validates.
        csr = x509.load_pem_x509_csr(captured['csr_pem'].encode())
        assert csr.subject.rfc4514_string() == 'CN=renew-nocsr.test.local'
        assert csr.is_signature_valid

        with app.app_context():
            from models import Certificate, db
            from utils.key_codec import load_pem_bytes
            cert = db.session.get(Certificate, cert_id)
            assert cert.csr  # CSR stored for future renewals
            key_pem = load_pem_bytes(cert.prv, context='rekey test')
            key = serialization.load_pem_private_key(key_pem, password=None)
            # New key matches the CSR's public key
            assert key.public_key().public_numbers() == \
                csr.public_key().public_numbers()

    def test_renew_msca_without_csr_pending_persists_key(self, app, auth_client, monkeypatch):
        """On a rekey renewal that lands in manager approval, the key + CSR
        must already be persisted so the status poll can finalize."""
        cert_id, _, _ = _create_msca_cert(
            app, 'renew-nocsr-pending.test.local', with_csr=False)

        def fake_submit_csr(**kwargs):
            return {'status': 'pending', 'request_id': None, 'ms_request_id': 77,
                    'message': 'Request pending manager approval'}

        from services.msca_service import MicrosoftCAService
        monkeypatch.setattr(MicrosoftCAService, 'submit_csr', staticmethod(fake_submit_csr))

        r = post_json(auth_client, f'{BASE}/{cert_id}/renew', {})
        assert r.status_code == 200, r.data
        assert get_json(r)['meta']['msca_status'] == 'pending'

        with app.app_context():
            from models import Certificate, db
            from utils.key_codec import load_pem_bytes
            cert = db.session.get(Certificate, cert_id)
            assert cert.csr
            load_pem_bytes(cert.prv, context='rekey pending test')

    def test_renew_msca_disabled_connection_fails(self, app, auth_client):
        cert_id, msca_id, _ = _create_msca_cert(app, 'renew-disabled.test.local')
        with app.app_context():
            from models import db
            from models.msca import MicrosoftCA
            db.session.get(MicrosoftCA, msca_id).enabled = False
            db.session.commit()

        r = post_json(auth_client, f'{BASE}/{cert_id}/renew', {})
        assert r.status_code == 400
        assert 'disabled' in get_json(r)['message']
