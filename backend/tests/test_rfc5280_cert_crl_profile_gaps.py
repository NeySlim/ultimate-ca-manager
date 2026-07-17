"""
RFC 5280 certificate + CRL profile gaps — non-regression / security / lab.

Covers:
  §4.2.1.1 / §4.2.1.2  CSR must not inject SKI/AKI; always from keys
  §4.2.1.1             EE/CA AKI from issuer SKI when present
  §4.2.2.1             CA AIA caIssuers when configured
  §5.3.2               CRL invalidityDate when invalidity_at set
  §5.3.1               unhold emits removeFromCRL on delta then clears hold
  Auth                 revoke/unhold require authentication
"""
import base64
import json
import os
import sys
from datetime import datetime, timedelta

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import (
    AuthorityInformationAccessOID,
    CRLEntryExtensionOID,
    ExtensionOID,
    NameOID,
)

from tests.conftest import assert_success, get_json
from utils.datetime_utils import utc_now

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONTENT_JSON = 'application/json'
CRL_BASE = '/api/v2/crl'


def _post_json(client, url, data):
    return client.post(url, data=json.dumps(data), content_type=CONTENT_JSON)


def _ext_or_none(obj, oid):
    try:
        return obj.extensions.get_extension_for_oid(oid)
    except x509.ExtensionNotFound:
        return None


def _load_crl(pem: str):
    return x509.load_pem_x509_crl(
        pem.encode() if isinstance(pem, str) else pem,
        default_backend(),
    )


def _fetch_crl_pem(auth_client, ca_id, *, delta=False):
    url = f'{CRL_BASE}/{ca_id}/delta' if delta else f'{CRL_BASE}/{ca_id}'
    r = auth_client.get(url)
    assert r.status_code == 200, r.data
    data = get_json(r).get('data', get_json(r))
    assert data and data.get('crl_pem'), data
    return data['crl_pem']


def _enable_delta(app, ca_id):
    with app.app_context():
        from models import CA, db
        ca = db.session.get(CA, ca_id)
        ca.cdp_enabled = True
        ca.delta_crl_enabled = True
        ca.set_cdp_urls([f'http://cdp.test.local/cdp/{ca.refid}.crl'])
        db.session.commit()
        return ca.refid


def _self_signed_ca():
    key = rsa.generate_private_key(65537, 2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Profile Root CA')])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime(2020, 1, 1))
        .not_valid_after(datetime(2035, 1, 1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    return cert, key


class TestCsrSkiAkiNotInjectable:
    """Security: enrollee CSR SKI/AKI must be ignored."""

    def test_csr_injected_ski_aki_are_overwritten(self):
        from services.trust_store import TrustStoreService

        ca_cert, ca_key = _self_signed_ca()
        leaf_key = rsa.generate_private_key(65537, 2048)
        fake_ski = x509.SubjectKeyIdentifier(b'\xaa' * 20)
        fake_aki = x509.AuthorityKeyIdentifier(
            key_identifier=b'\xbb' * 20,
            authority_cert_issuer=None,
            authority_cert_serial_number=None,
        )
        csr = (
            x509.CertificateSigningRequestBuilder()
            .subject_name(
                x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'inject.example.com')])
            )
            .add_extension(fake_ski, critical=False)
            .add_extension(fake_aki, critical=False)
            .sign(leaf_key, hashes.SHA256())
        )
        pem = TrustStoreService.sign_csr(
            csr_pem=csr.public_bytes(serialization.Encoding.PEM),
            ca_cert=ca_cert,
            ca_private_key=ca_key,
            validity_days=30,
        )
        issued = x509.load_pem_x509_certificate(
            pem if isinstance(pem, bytes) else pem.encode(),
            default_backend(),
        )
        ski = issued.extensions.get_extension_for_oid(
            ExtensionOID.SUBJECT_KEY_IDENTIFIER
        ).value
        aki = issued.extensions.get_extension_for_oid(
            ExtensionOID.AUTHORITY_KEY_IDENTIFIER
        ).value
        expected_ski = x509.SubjectKeyIdentifier.from_public_key(leaf_key.public_key())
        expected_aki = x509.AuthorityKeyIdentifier.from_issuer_subject_key_identifier(
            ca_cert.extensions.get_extension_for_oid(
                ExtensionOID.SUBJECT_KEY_IDENTIFIER
            ).value
        )
        assert ski.digest == expected_ski.digest
        assert aki.key_identifier == expected_aki.key_identifier
        assert ski.digest != fake_ski.digest
        assert aki.key_identifier != fake_aki.key_identifier


class TestEeAkiMatchesIssuerSki:
    def test_create_certificate_aki_from_issuer_ski(self):
        from services.trust_store import TrustStoreService

        ca_cert, ca_key = _self_signed_ca()
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'ee.example.com')])
        cert_pem, _ = TrustStoreService.create_certificate(
            subject=subject,
            ca_cert=ca_cert,
            ca_private_key=ca_key,
            validity_days=30,
        )
        issued = x509.load_pem_x509_certificate(cert_pem, default_backend())
        aki = issued.extensions.get_extension_for_oid(
            ExtensionOID.AUTHORITY_KEY_IDENTIFIER
        ).value.key_identifier
        ski = ca_cert.extensions.get_extension_for_oid(
            ExtensionOID.SUBJECT_KEY_IDENTIFIER
        ).value.key_identifier
        assert aki == ski


class TestCaAiaCaIssuers:
    def test_intermediate_carries_ca_issuers_when_configured(self):
        from services.trust_store import TrustStoreService

        root_cert, root_key = _self_signed_ca()
        inter_key = rsa.generate_private_key(65537, 2048)
        subject = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, 'AIA Intermediate CA'),
        ])
        aia_url = 'http://aia.test.local/ca/root.crt'
        cert_pem, _ = TrustStoreService.create_ca_certificate(
            subject=subject,
            private_key=inter_key,
            issuer=root_cert.subject,
            issuer_private_key=root_key,
            issuer_cert=root_cert,
            validity_days=365,
            ocsp_uris=['http://ocsp.test.local'],
            aia_ca_issuers_urls=[aia_url],
        )
        issued = x509.load_pem_x509_certificate(cert_pem, default_backend())
        aia = issued.extensions.get_extension_for_oid(
            ExtensionOID.AUTHORITY_INFORMATION_ACCESS
        ).value
        methods = {d.access_method: d.access_location.value for d in aia}
        assert AuthorityInformationAccessOID.OCSP in methods
        assert AuthorityInformationAccessOID.CA_ISSUERS in methods
        assert methods[AuthorityInformationAccessOID.CA_ISSUERS] == aia_url

        aki = issued.extensions.get_extension_for_oid(
            ExtensionOID.AUTHORITY_KEY_IDENTIFIER
        ).value.key_identifier
        root_ski = root_cert.extensions.get_extension_for_oid(
            ExtensionOID.SUBJECT_KEY_IDENTIFIER
        ).value.key_identifier
        assert aki == root_ski


class TestInvalidityDate:
    def test_invalidity_date_on_crl_when_set(self, app, auth_client, create_ca):
        ca = create_ca(cn='Invalidity Date CA')
        with app.app_context():
            from models import CA, db
            row = db.session.get(CA, ca['id'])
            row.cdp_enabled = True
            db.session.commit()

        r = _post_json(auth_client, '/api/v2/certificates', {
            'cn': 'invalidity.example.com',
            'ca_id': ca['id'],
            'validity_days': 30,
        })
        cert = assert_success(r, status=201)
        invalidity = (utc_now() - timedelta(days=3)).replace(microsecond=0)
        r = _post_json(auth_client, f'/api/v2/certificates/{cert["id"]}/revoke', {
            'reason': 'keyCompromise',
            'invalidity_date': invalidity.isoformat() + 'Z',
        })
        assert r.status_code in (200, 201), r.data
        body = get_json(r).get('data', get_json(r))
        assert body.get('invalidity_at')

        assert auth_client.post(f'{CRL_BASE}/{ca["id"]}/regenerate').status_code == 200
        crl = _load_crl(_fetch_crl_pem(auth_client, ca['id']))
        found = False
        for entry in crl:
            ext = _ext_or_none(entry, CRLEntryExtensionOID.INVALIDITY_DATE)
            if ext:
                found = True
                assert ext.critical is False
                # Compare dates (timezone may differ)
                inv = ext.value.invalidity_date
                if getattr(inv, 'tzinfo', None) is not None:
                    inv = inv.replace(tzinfo=None)
                assert inv.date() == invalidity.date()
        assert found, 'expected invalidityDate on at least one CRL entry'


class TestUnholdRemoveFromCrl:
    def test_unhold_emits_remove_from_crl_on_delta(self, app, auth_client, create_ca):
        ca = create_ca(cn='Unhold Delta CA')
        _enable_delta(app, ca['id'])
        assert auth_client.post(f'{CRL_BASE}/{ca["id"]}/regenerate').status_code == 200

        r = _post_json(auth_client, '/api/v2/certificates', {
            'cn': 'hold.example.com',
            'ca_id': ca['id'],
            'validity_days': 30,
        })
        cert = assert_success(r, status=201)
        r = _post_json(auth_client, f'/api/v2/certificates/{cert["id"]}/revoke', {
            'reason': 'certificateHold',
        })
        assert r.status_code in (200, 201), r.data
        # Ensure hold is after base thisUpdate for delta inclusion
        with app.app_context():
            from models import Certificate, db
            from models.crl import CRLMetadata
            base = CRLMetadata.query.filter_by(
                ca_id=ca['id'], is_delta=False
            ).order_by(CRLMetadata.crl_number.desc()).first()
            row = db.session.get(Certificate, cert['id'])
            row.revoked_at = base.this_update + timedelta(minutes=1)
            db.session.commit()

        r = auth_client.post(f'/api/v2/certificates/{cert["id"]}/unhold')
        assert r.status_code == 200, r.data

        delta = _load_crl(_fetch_crl_pem(auth_client, ca['id'], delta=True))
        reasons = [
            e.value.reason
            for entry in delta
            if (e := _ext_or_none(entry, CRLEntryExtensionOID.CRL_REASON))
        ]
        assert x509.ReasonFlags.remove_from_crl in reasons

        with app.app_context():
            from models import Certificate, db
            row = db.session.get(Certificate, cert['id'])
            assert row.revoked is False
            assert row.revoke_reason is None

        full = _load_crl(_fetch_crl_pem(auth_client, ca['id']))
        # Serial should not appear as still-revoked on the new full CRL
        with app.app_context():
            from models import Certificate, db
            from utils.serial_format import serial_to_int
            row = db.session.get(Certificate, cert['id'])
            serial_int = serial_to_int(row.serial_number)
        for entry in full:
            assert entry.serial_number != serial_int


class TestAuthGates:
    def test_revoke_requires_auth(self, client, auth_client, create_ca):
        ca = create_ca(cn='Auth Revoke CA')
        r = _post_json(auth_client, '/api/v2/certificates', {
            'cn': 'auth.revoke.test',
            'ca_id': ca['id'],
            'validity_days': 30,
        })
        cert = assert_success(r, status=201)
        r = _post_json(client, f'/api/v2/certificates/{cert["id"]}/revoke', {
            'reason': 'keyCompromise',
        })
        assert r.status_code in (401, 403)

    def test_unhold_requires_auth(self, client, auth_client, create_ca):
        ca = create_ca(cn='Auth Unhold CA')
        r = _post_json(auth_client, '/api/v2/certificates', {
            'cn': 'auth.unhold.test',
            'ca_id': ca['id'],
            'validity_days': 30,
        })
        cert = assert_success(r, status=201)
        assert _post_json(auth_client, f'/api/v2/certificates/{cert["id"]}/revoke', {
            'reason': 'certificateHold',
        }).status_code in (200, 201)
        r = client.post(f'/api/v2/certificates/{cert["id"]}/unhold')
        assert r.status_code in (401, 403)


class TestLabOpensslTextDump:
    """Lab-style: openssl crl -text shows invalidityDate when set."""

    def test_openssl_shows_invalidity_date(self, app, auth_client, create_ca):
        import subprocess
        import tempfile

        ca = create_ca(cn='Lab Invalidity CA')
        with app.app_context():
            from models import CA, db
            row = db.session.get(CA, ca['id'])
            row.cdp_enabled = True
            db.session.commit()

        r = _post_json(auth_client, '/api/v2/certificates', {
            'cn': 'lab.invalidity.test',
            'ca_id': ca['id'],
            'validity_days': 30,
        })
        cert = assert_success(r, status=201)
        invalidity = (utc_now() - timedelta(days=1)).replace(microsecond=0)
        assert _post_json(auth_client, f'/api/v2/certificates/{cert["id"]}/revoke', {
            'reason': 'keyCompromise',
            'invalidity_date': invalidity.isoformat() + 'Z',
        }).status_code in (200, 201)
        assert auth_client.post(f'{CRL_BASE}/{ca["id"]}/regenerate').status_code == 200
        pem = _fetch_crl_pem(auth_client, ca['id'])

        with tempfile.NamedTemporaryFile('w', suffix='.crl', delete=False) as tf:
            tf.write(pem)
            path = tf.name
        try:
            out = subprocess.run(
                ['openssl', 'crl', '-in', path, '-text', '-noout'],
                capture_output=True, text=True, check=True,
            ).stdout
        finally:
            os.unlink(path)

        assert 'Invalidity Date' in out or 'invalidityDate' in out.lower()
