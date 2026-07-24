"""SCEP profiles (issue #228): named endpoints at /scep/<slug>/pkiclient.exe,
each bound to its own CA, template, challenge and approval policy. The
unlabelled endpoints keep serving the global configuration.
"""
import base64
import json

import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.x509.oid import ExtensionOID

from models import db, CA
from tests.conftest import get_json
from tests.test_scep_rfc8894_operations import (
    _set_config, _clear_config, _load_ca_material,
)

CONTENT_JSON = 'application/json'


def _create_profile(auth_client, **overrides):
    data = {'name': 'Device Certs', 'auto_approve': True}
    data.update(overrides)
    r = auth_client.post('/api/v2/scep/profiles',
                         data=json.dumps(data), content_type=CONTENT_JSON)
    return r


def _create_template(auth_client, **overrides):
    data = {
        'name': 'scep-profile-tpl',
        'template_type': 'custom',
        'key_type': 'RSA-2048',
        'validity_days': 30,
        'digest': 'sha256',
    }
    data.update(overrides)
    r = auth_client.post('/api/v2/templates',
                         data=json.dumps(data), content_type=CONTENT_JSON)
    assert r.status_code in (200, 201), r.data
    body = get_json(r)
    return body.get('data', body)


class TestScepProfileCrud:

    def test_create_generates_slug_and_hides_challenge(self, app, auth_client, create_ca):
        ca = create_ca(cn='Profile CRUD CA')
        r = _create_profile(auth_client, name='IoT Devices!', ca_id=ca['id'],
                            challenge_password='super-secret')
        assert r.status_code == 200, r.data
        prof = get_json(r)['data']
        assert prof['url_slug'] == 'iot-devices'
        assert prof['challenge_set'] is True
        assert 'challenge_password' not in prof

        r = auth_client.get('/api/v2/scep/profiles')
        listed = get_json(r)['data']
        match = next(p for p in listed if p['id'] == prof['id'])
        assert 'challenge_password' not in match
        assert match['ca_name']

    def test_challenge_encrypted_at_rest(self, app, auth_client, create_ca):
        ca = create_ca(cn='Profile Enc CA')
        r = _create_profile(auth_client, name='enc-check', ca_id=ca['id'],
                            challenge_password='plaintext-secret')
        prof_id = get_json(r)['data']['id']
        with app.app_context():
            from models import ScepProfile
            row = db.session.get(ScepProfile, prof_id)
            # Round-trip always holds; ciphertext-at-rest only when the
            # instance actually has encryption available (master key present)
            assert row.decrypted_challenge() == 'plaintext-secret'
            try:
                from security.encryption import encrypt_text
                # encrypt_text is a no-op passthrough when encryption is
                # disabled — only assert ciphertext when it actually ciphers
                encryption_active = encrypt_text('probe') != 'probe'
            except Exception:
                encryption_active = False
            if encryption_active:
                assert row.challenge_password != 'plaintext-secret'

    def test_duplicate_slug_rejected(self, auth_client, create_ca):
        ca = create_ca(cn='Profile Dup CA')
        assert _create_profile(auth_client, name='dup-a', url_slug='shared',
                               ca_id=ca['id']).status_code == 200
        r = _create_profile(auth_client, name='dup-b', url_slug='shared',
                            ca_id=ca['id'])
        assert r.status_code == 400

    def test_invalid_slug_rejected(self, auth_client, create_ca):
        ca = create_ca(cn='Profile Slug CA')
        r = _create_profile(auth_client, name='bad slug', url_slug='No/Slash',
                            ca_id=ca['id'])
        assert r.status_code == 400

    def test_regenerate_returns_challenge_once(self, auth_client, create_ca):
        ca = create_ca(cn='Profile Regen CA')
        prof = get_json(_create_profile(auth_client, name='regen',
                                        ca_id=ca['id']))['data']
        r = auth_client.post(f"/api/v2/scep/profiles/{prof['id']}/challenge/regenerate")
        assert r.status_code == 200
        challenge = get_json(r)['data']['challenge']
        assert challenge
        r = auth_client.get('/api/v2/scep/profiles')
        match = next(p for p in get_json(r)['data'] if p['id'] == prof['id'])
        assert match['challenge_set'] is True
        assert challenge not in r.get_data(as_text=True)

    def test_update_and_delete(self, auth_client, create_ca):
        ca = create_ca(cn='Profile UpdDel CA')
        prof = get_json(_create_profile(auth_client, name='upddel',
                                        ca_id=ca['id']))['data']
        r = auth_client.patch(f"/api/v2/scep/profiles/{prof['id']}",
                              data=json.dumps({'enabled': False}),
                              content_type=CONTENT_JSON)
        assert r.status_code == 200
        assert get_json(r)['data']['enabled'] is False

        r = auth_client.delete(f"/api/v2/scep/profiles/{prof['id']}")
        assert r.status_code == 200
        r = auth_client.get('/api/v2/scep/profiles')
        assert all(p['id'] != prof['id'] for p in get_json(r)['data'])


class TestScepProfileRouting:

    def test_profile_getcacert_serves_profile_ca(self, app, client, auth_client, create_ca):
        global_ca = create_ca(cn='Global SCEP CA')
        profile_ca = create_ca(cn='Profile SCEP CA')
        prof = get_json(_create_profile(auth_client, name='routed',
                                        ca_id=profile_ca['id']))['data']
        with app.app_context():
            _set_config('scep_ca_id', str(global_ca['id']))
            global_serial = _load_ca_material(global_ca['id'])[1].serial_number
            profile_serial = _load_ca_material(profile_ca['id'])[1].serial_number
        try:
            r = client.get('/scep/pkiclient.exe?operation=GetCACert')
            assert r.status_code == 200
            assert x509.load_der_x509_certificate(r.data).serial_number == global_serial

            r = client.get(f"/scep/{prof['url_slug']}/pkiclient.exe?operation=GetCACert")
            assert r.status_code == 200
            assert x509.load_der_x509_certificate(r.data).serial_number == profile_serial
        finally:
            with app.app_context():
                _clear_config('scep_ca_id')

    def test_unknown_profile_rejected(self, client):
        r = client.get('/scep/nope-nope/pkiclient.exe?operation=GetCACert')
        assert r.status_code == 500

    def test_disabled_profile_rejected(self, app, client, auth_client, create_ca):
        ca = create_ca(cn='Disabled Profile CA')
        prof = get_json(_create_profile(auth_client, name='disabledp',
                                        ca_id=ca['id']))['data']
        auth_client.patch(f"/api/v2/scep/profiles/{prof['id']}",
                          data=json.dumps({'enabled': False}),
                          content_type=CONTENT_JSON)
        r = client.get(f"/scep/{prof['url_slug']}/pkiclient.exe?operation=GetCACert")
        assert r.status_code == 500

    def test_getcacaps_works_per_profile(self, client, auth_client, create_ca):
        ca = create_ca(cn='Caps Profile CA')
        prof = get_json(_create_profile(auth_client, name='capsp',
                                        ca_id=ca['id']))['data']
        r = client.get(f"/scep/{prof['url_slug']}/pkiclient.exe?operation=GetCACaps")
        assert r.status_code == 200
        assert b'SHA-256' in r.data


class TestScepProfileTemplateIssuance:

    def _issue_via_service(self, app, ca_id, template_id):
        """Drive SCEPService directly with the profile-style template binding."""
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
        from services.scep.scep_service import SCEPService
        from models import SCEPRequest, CertificateTemplate, Certificate

        with app.app_context():
            ca_obj = db.session.get(CA, ca_id)
            template = db.session.get(CertificateTemplate, template_id)
            svc = SCEPService(ca_refid=ca_obj.refid, auto_approve=True,
                              template=template)

            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            csr = (x509.CertificateSigningRequestBuilder()
                   .subject_name(x509.Name(
                       [x509.NameAttribute(NameOID.COMMON_NAME, 'device1.test')]))
                   .add_extension(x509.ExtendedKeyUsage(
                       [x509.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
                   .sign(key, hashes.SHA256()))

            scep_req = SCEPRequest(
                transaction_id='profile-tpl-txn',
                ca_refid=ca_obj.refid,
                csr=base64.b64encode(
                    csr.public_bytes(serialization.Encoding.DER)).decode(),
                status='pending',
                subject='CN=device1.test',
            )
            db.session.add(scep_req)
            db.session.flush()
            cert_refid = svc._auto_approve_request(scep_req, csr)
            db.session.commit()
            row = Certificate.query.filter_by(refid=cert_refid).first()
            pem = base64.b64decode(row.crt)
        return x509.load_pem_x509_certificate(pem, default_backend())

    def test_template_governs_eku_and_validity(self, app, auth_client, create_ca):
        ca = create_ca(cn='Profile Tpl CA')
        tpl = _create_template(
            auth_client, name='scep-client-only', validity_days=30,
            extensions_template={
                'key_usage': ['digitalSignature'],
                'extended_key_usage': ['clientAuth'],
            })

        cert = self._issue_via_service(app, ca['id'], tpl['id'])

        eku = cert.extensions.get_extension_for_oid(
            ExtensionOID.EXTENDED_KEY_USAGE).value
        assert {oid.dotted_string for oid in eku} == {'1.3.6.1.5.5.7.3.2'}
        ku = cert.extensions.get_extension_for_oid(ExtensionOID.KEY_USAGE).value
        assert ku.digital_signature is True
        assert ku.key_encipherment is False
        days = (cert.not_valid_after_utc - cert.not_valid_before_utc).days
        assert days in (29, 30)

    def test_without_template_csr_allowlist_applies(self, app, auth_client, create_ca):
        # No template bound: the CSR's serverAuth passes the generic allowlist
        ca = create_ca(cn='Profile NoTpl CA')
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        from cryptography.x509.oid import NameOID
        from services.scep.scep_service import SCEPService
        from models import SCEPRequest, Certificate

        with app.app_context():
            ca_obj = db.session.get(CA, ca['id'])
            svc = SCEPService(ca_refid=ca_obj.refid, auto_approve=True)
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            csr = (x509.CertificateSigningRequestBuilder()
                   .subject_name(x509.Name(
                       [x509.NameAttribute(NameOID.COMMON_NAME, 'device2.test')]))
                   .add_extension(x509.ExtendedKeyUsage(
                       [x509.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
                   .sign(key, hashes.SHA256()))
            scep_req = SCEPRequest(
                transaction_id='profile-notpl-txn',
                ca_refid=ca_obj.refid,
                csr=base64.b64encode(
                    csr.public_bytes(serialization.Encoding.DER)).decode(),
                status='pending',
                subject='CN=device2.test',
            )
            db.session.add(scep_req)
            db.session.flush()
            cert_refid = svc._auto_approve_request(scep_req, csr)
            db.session.commit()
            row = Certificate.query.filter_by(refid=cert_refid).first()
            pem = base64.b64decode(row.crt)
        cert = x509.load_pem_x509_certificate(pem, default_backend())
        eku = cert.extensions.get_extension_for_oid(
            ExtensionOID.EXTENDED_KEY_USAGE).value
        assert {oid.dotted_string for oid in eku} == {'1.3.6.1.5.5.7.3.1'}
