"""A CA that holds only its certificate can receive its private key (#348)."""
import base64
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa
from cryptography.x509.oid import NameOID

from models import db, CA


def _pem(key, password=None):
    enc = serialization.BestAvailableEncryption(password.encode()) if password else serialization.NoEncryption()
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, enc).decode()


def _keyless_ca(app, key, cn, **extra):
    """A CA record holding only its certificate, as signing an external CA request leaves it."""
    now = datetime.now(timezone.utc)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=365))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, None if isinstance(key, ed25519.Ed25519PrivateKey) else hashes.SHA256()))
    with app.app_context():
        row = CA(refid=str(uuid.uuid4()), descr=cn, serial=0, prv=None,
                 crt=base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode(),
                 subject=name.rfc4514_string(), issuer=name.rfc4514_string(),
                 serial_number=str(cert.serial_number), imported_from='csr_signed', **extra)
        db.session.add(row); db.session.commit()
        return row.id


def _post(auth_client, ca_id, body):
    return auth_client.post(f'/api/v2/cas/{ca_id}/key', data=json.dumps(body), content_type='application/json')


class TestCaKeyImport:
    def test_certificate_only_flag_and_key_import(self, app, auth_client):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        ca_id = _keyless_ca(app, key, 'Certificate Only CA')
        r = auth_client.get(f'/api/v2/cas/{ca_id}')
        body = json.loads(r.data)['data']
        assert body['certificate_only'] is True and body['has_private_key'] is False
        r = _post(auth_client, ca_id, {'key': _pem(key)})
        assert r.status_code == 200, r.data
        body = json.loads(r.data)['data']
        assert body['has_private_key'] is True and body['certificate_only'] is False
        with app.app_context():
            from services.hsm.ca_key_loader import get_ca_signing_key
            loaded = get_ca_signing_key(db.session.get(CA, ca_id))
            assert loaded.public_key().public_numbers() == key.public_key().public_numbers()
        # The CA can now sign
        r = auth_client.post('/api/v2/certificates', data=json.dumps({
            'cn': 'under-imported-key.example.com', 'ca_id': ca_id, 'validity_days': 30,
            'key_type': 'RSA 2048', 'cert_type': 'server'}), content_type='application/json')
        assert r.status_code in (200, 201), r.data

    def test_encrypted_key_with_passphrase_and_ec(self, app, auth_client):
        key = ec.generate_private_key(ec.SECP256R1())
        ca_id = _keyless_ca(app, key, 'EC Keyless CA')
        r = _post(auth_client, ca_id, {'key': _pem(key, 'pass-phrase')})
        assert r.status_code == 400 and 'passphrase' in json.loads(r.data)['message']
        r = _post(auth_client, ca_id, {'key': _pem(key, 'pass-phrase'), 'passphrase': 'pass-phrase'})
        assert r.status_code == 200, r.data

    def test_refusals(self, app, auth_client, create_ca):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        ca_id = _keyless_ca(app, key, 'Refusals CA')
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        r = _post(auth_client, ca_id, {'key': _pem(other)})
        assert r.status_code == 400 and 'does not match' in json.loads(r.data)['message']
        r = _post(auth_client, ca_id, {'key': 'not a key'})
        assert r.status_code == 400
        r = _post(auth_client, ca_id, {})
        assert r.status_code == 400
        # An Ed25519 CA key is refused with the reason
        edkey = ed25519.Ed25519PrivateKey.generate()
        ed_id = _keyless_ca(app, edkey, 'Ed Keyless CA')
        r = _post(auth_client, ed_id, {'key': _pem(edkey)})
        assert r.status_code == 400 and 'Ed25519' in json.loads(r.data)['message']
        # A CA that already has a key
        full = create_ca(cn='Already Keyed CA')
        r = _post(auth_client, full['id'], {'key': _pem(key)})
        assert r.status_code == 400 and 'already' in json.loads(r.data)['message']
        # A pending CA keeps its own key flow
        with app.app_context():
            pending = CA(refid=str(uuid.uuid4()), descr='Pending Keyless', serial=0, crt='', prv=None,
                         subject='CN=Pending Keyless', imported_from='external_csr')
            db.session.add(pending); db.session.commit(); pending_id = pending.id
        r = _post(auth_client, pending_id, {'key': _pem(key)})
        assert r.status_code == 409

    def test_signing_an_external_ca_request_says_the_ca_has_no_key(self, app, auth_client, create_ca):
        root = create_ca(cn='Root For External Sub')
        win_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        csr = (x509.CertificateSigningRequestBuilder()
               .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'External Sub CA')]))
               .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
               .sign(win_key, hashes.SHA256()))
        r = auth_client.post('/api/v2/csrs/import', data={'pem_content': csr.public_bytes(serialization.Encoding.PEM).decode()},
                             content_type='multipart/form-data')
        assert r.status_code in (200, 201), r.data
        csr_id = json.loads(r.data)['data']['id']
        r = auth_client.post(f'/api/v2/csrs/{csr_id}/sign', data=json.dumps({'ca_id': root['id'], 'validity_days': 365, 'cert_type': 'intermediate_ca'}),
                             content_type='application/json')
        assert r.status_code in (200, 201), r.data
        body = json.loads(r.data)
        assert body['data']['certificate_only'] is True
        assert 'no private key' in body['message']
        sub_id = body['data']['id']
        r = auth_client.post(f'/api/v2/cas/{sub_id}/offline', data=json.dumps({'password': 'Correct-Horse-9-Battery', 'mode': 'password_protected'}),
                             content_type='application/json')
        assert r.status_code == 400
        r = _post(auth_client, sub_id, {'key': _pem(win_key)})
        assert r.status_code == 200, r.data
        assert json.loads(r.data)['data']['certificate_only'] is False


class TestCaKeyImportReview:
    """Review of the #348 fix: offline CAs, accurate message, banner scope."""

    def test_offline_ca_refuses_a_key_import(self, app, auth_client, create_ca):
        ca = create_ca(cn='Offline Then Key CA')
        r = auth_client.post(f"/api/v2/cas/{ca['id']}/offline", data=json.dumps({'password': 'Correct-Horse-9-Battery', 'mode': 'file_exported'}),
                             content_type='application/json')
        assert r.status_code == 200, r.data
        body = json.loads(auth_client.get(f"/api/v2/cas/{ca['id']}").data)['data']
        assert body['offline'] is True and body['has_private_key'] is False
        assert body['certificate_only'] is False, 'an offline CA is not a certificate-only one'
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        r = _post(auth_client, ca['id'], {'key': _pem(key)})
        assert r.status_code == 409 and 'offline' in json.loads(r.data)['message']

    def test_message_says_when_the_ca_still_cannot_sign(self, app, auth_client):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        ca_id = _keyless_ca(app, key, 'Revoked Keyless CA', revoked=True, revoke_reason='keyCompromise',
                            revoked_at=datetime.now(timezone.utc).replace(tzinfo=None))
        r = _post(auth_client, ca_id, {'key': _pem(key)})
        assert r.status_code == 200, r.data
        assert 'still cannot sign' in json.loads(r.data)['message']
