"""Regression tests for issue #226 — templates govern KU/EKU at issuance.

1. A template's extensions_template overrides the cert_type profile: a
   template with only OCSPSigning must yield a cert with only OCSPSigning
   (previously serverAuth was always merged in from the profile).
2. Template key_usage overrides the profile KU flags.
3. cert_type=custom imposes no EKU: extras alone end up in the cert, and
   with no extras the EKU extension is omitted entirely.
4. ocsp_signing is a valid template_type with sane defaults, and the
   OCSP Signing system template seeds correctly.
"""
import base64
import json

import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.x509.oid import ExtensionOID

from tests.conftest import get_json

CONTENT_JSON = 'application/json'
OCSP_SIGNING_OID = '1.3.6.1.5.5.7.3.9'
SERVER_AUTH_OID = '1.3.6.1.5.5.7.3.1'


def _issue_cert(auth_client, ca_id, cn, **extra):
    payload = {'cn': cn, 'ca_id': ca_id, 'key_type': 'rsa', 'key_size': 2048,
               'validity_days': 90}
    payload.update(extra)
    return auth_client.post('/api/v2/certificates',
                            data=json.dumps(payload), content_type=CONTENT_JSON)


def _create_template(auth_client, **overrides):
    data = {
        'name': 'issue226-tpl',
        'template_type': 'custom',
        'key_type': 'RSA-2048',
        'validity_days': 90,
        'digest': 'sha256',
    }
    data.update(overrides)
    r = auth_client.post('/api/v2/templates',
                         data=json.dumps(data), content_type=CONTENT_JSON)
    assert r.status_code in (200, 201), r.data
    body = get_json(r)
    return body.get('data', body)


def _issued_cert_obj(app, cert_id):
    with app.app_context():
        from models import Certificate, db
        row = db.session.get(Certificate, cert_id)
        assert row is not None
        pem = base64.b64decode(row.crt)
    return x509.load_pem_x509_certificate(pem, default_backend())


def _eku_oids(cert):
    ext = cert.extensions.get_extension_for_oid(ExtensionOID.EXTENDED_KEY_USAGE)
    return {oid.dotted_string for oid in ext.value}


class TestTemplateExtensionsGovernIssuance:

    def test_ocsp_only_template_yields_ocsp_only_eku(self, app, auth_client, create_ca):
        ca = create_ca(cn='Issue226 OCSP CA')
        tpl = _create_template(
            auth_client, name='issue226-ocsp-only',
            extensions_template={
                'key_usage': ['digitalSignature'],
                'extended_key_usage': ['OCSPSigning'],
            })

        r = _issue_cert(auth_client, ca['id'], 'ocsp-responder.test',
                        template_id=tpl['id'])
        assert r.status_code in (200, 201), r.data
        cert = _issued_cert_obj(app, get_json(r)['data']['id'])

        assert _eku_oids(cert) == {OCSP_SIGNING_OID}

    def test_template_eku_overrides_cert_type_profile(self, app, auth_client, create_ca):
        ca = create_ca(cn='Issue226 Override CA')
        tpl = _create_template(
            auth_client, name='issue226-client-only',
            extensions_template={'extended_key_usage': ['clientAuth']})

        # cert_type=server would normally impose serverAuth
        r = _issue_cert(auth_client, ca['id'], 'override.test',
                        template_id=tpl['id'], cert_type='server')
        assert r.status_code in (200, 201), r.data
        cert = _issued_cert_obj(app, get_json(r)['data']['id'])

        assert SERVER_AUTH_OID not in _eku_oids(cert)
        assert _eku_oids(cert) == {'1.3.6.1.5.5.7.3.2'}

    def test_template_key_usage_overrides_profile(self, app, auth_client, create_ca):
        ca = create_ca(cn='Issue226 KU CA')
        tpl = _create_template(
            auth_client, name='issue226-ku-ds-only',
            extensions_template={
                'key_usage': ['digitalSignature'],
                'extended_key_usage': ['OCSPSigning'],
            })

        r = _issue_cert(auth_client, ca['id'], 'ku.test', template_id=tpl['id'])
        assert r.status_code in (200, 201), r.data
        cert = _issued_cert_obj(app, get_json(r)['data']['id'])

        ku = cert.extensions.get_extension_for_oid(ExtensionOID.KEY_USAGE).value
        assert ku.digital_signature is True
        assert ku.key_encipherment is False

    def test_extra_ekus_still_merged_on_top_of_template(self, app, auth_client, create_ca):
        ca = create_ca(cn='Issue226 Merge CA')
        tpl = _create_template(
            auth_client, name='issue226-merge',
            extensions_template={'extended_key_usage': ['OCSPSigning']})

        r = _issue_cert(auth_client, ca['id'], 'merge.test',
                        template_id=tpl['id'], extra_ekus=['clientAuth'])
        assert r.status_code in (200, 201), r.data
        cert = _issued_cert_obj(app, get_json(r)['data']['id'])

        assert _eku_oids(cert) == {OCSP_SIGNING_OID, '1.3.6.1.5.5.7.3.2'}


class TestCustomCertType:

    def test_custom_type_with_extras_only(self, app, auth_client, create_ca):
        ca = create_ca(cn='Issue226 Custom CA')
        r = _issue_cert(auth_client, ca['id'], 'custom-extras.test',
                        cert_type='custom', extra_ekus=['OCSPSigning'])
        assert r.status_code in (200, 201), r.data
        cert = _issued_cert_obj(app, get_json(r)['data']['id'])

        assert _eku_oids(cert) == {OCSP_SIGNING_OID}

    def test_custom_type_without_extras_omits_eku(self, app, auth_client, create_ca):
        ca = create_ca(cn='Issue226 Custom NoEku CA')
        r = _issue_cert(auth_client, ca['id'], 'custom-noeku.test',
                        cert_type='custom')
        assert r.status_code in (200, 201), r.data
        cert = _issued_cert_obj(app, get_json(r)['data']['id'])

        with pytest.raises(x509.ExtensionNotFound):
            cert.extensions.get_extension_for_oid(ExtensionOID.EXTENDED_KEY_USAGE)

    def test_default_type_unchanged(self, app, auth_client, create_ca):
        ca = create_ca(cn='Issue226 Server CA')
        r = _issue_cert(auth_client, ca['id'], 'plain-server.test')
        assert r.status_code in (200, 201), r.data
        cert = _issued_cert_obj(app, get_json(r)['data']['id'])

        assert _eku_oids(cert) == {SERVER_AUTH_OID}


class TestTemplateDefaultsAtIssuance:
    """Template key_type / validity_days are the defaults when the request
    omits them (API parity with the UI prefill), and explicit values win."""

    def _issue_raw(self, auth_client, payload):
        return auth_client.post('/api/v2/certificates',
                                data=json.dumps(payload),
                                content_type=CONTENT_JSON)

    def test_template_key_and_validity_used_as_defaults(self, app, auth_client, create_ca):
        from cryptography.hazmat.primitives.asymmetric import ec
        ca = create_ca(cn='Issue226 Defaults CA')
        tpl = _create_template(
            auth_client, name='issue226-defaults',
            key_type='EC-P384', validity_days=120,
            extensions_template={'extended_key_usage': ['clientAuth']})

        r = self._issue_raw(auth_client, {
            'cn': 'defaults.test', 'ca_id': ca['id'], 'template_id': tpl['id']})
        assert r.status_code in (200, 201), r.data
        cert = _issued_cert_obj(app, get_json(r)['data']['id'])

        pub = cert.public_key()
        assert isinstance(pub, ec.EllipticCurvePublicKey)
        assert pub.curve.name == 'secp384r1'
        days = (cert.not_valid_after_utc - cert.not_valid_before_utc).days
        assert 119 <= days <= 121

    def test_template_rsa_key_default(self, app, auth_client, create_ca):
        from cryptography.hazmat.primitives.asymmetric import rsa
        ca = create_ca(cn='Issue226 RSA Defaults CA')
        tpl = _create_template(
            auth_client, name='issue226-rsa-defaults',
            key_type='RSA-4096',
            extensions_template={'extended_key_usage': ['clientAuth']})

        r = self._issue_raw(auth_client, {
            'cn': 'rsa-defaults.test', 'ca_id': ca['id'], 'template_id': tpl['id']})
        assert r.status_code in (200, 201), r.data
        cert = _issued_cert_obj(app, get_json(r)['data']['id'])

        pub = cert.public_key()
        assert isinstance(pub, rsa.RSAPublicKey)
        assert pub.key_size == 4096

    def test_explicit_request_values_override_template(self, app, auth_client, create_ca):
        from cryptography.hazmat.primitives.asymmetric import ec
        ca = create_ca(cn='Issue226 Override Defaults CA')
        tpl = _create_template(
            auth_client, name='issue226-override-defaults',
            key_type='RSA-2048', validity_days=120,
            extensions_template={'extended_key_usage': ['clientAuth']})

        r = self._issue_raw(auth_client, {
            'cn': 'override-defaults.test', 'ca_id': ca['id'],
            'template_id': tpl['id'],
            'key_type': 'ecdsa', 'key_size': 256, 'validity_days': 30})
        assert r.status_code in (200, 201), r.data
        cert = _issued_cert_obj(app, get_json(r)['data']['id'])

        pub = cert.public_key()
        assert isinstance(pub, ec.EllipticCurvePublicKey)
        assert pub.curve.name == 'secp256r1'
        days = (cert.not_valid_after_utc - cert.not_valid_before_utc).days
        assert 29 <= days <= 31

    def test_no_template_keeps_current_defaults(self, app, auth_client, create_ca):
        from cryptography.hazmat.primitives.asymmetric import rsa
        ca = create_ca(cn='Issue226 Plain Defaults CA')
        r = self._issue_raw(auth_client, {'cn': 'plain-defaults.test', 'ca_id': ca['id']})
        assert r.status_code in (200, 201), r.data
        cert = _issued_cert_obj(app, get_json(r)['data']['id'])

        pub = cert.public_key()
        assert isinstance(pub, rsa.RSAPublicKey)
        assert pub.key_size == 2048
        days = (cert.not_valid_after_utc - cert.not_valid_before_utc).days
        assert 364 <= days <= 366


class TestOcspSigningTemplateType:

    def test_ocsp_signing_type_accepted_with_defaults(self, auth_client):
        tpl = _create_template(auth_client, name='issue226-ocsp-type',
                               template_type='ocsp_signing')
        ext = tpl.get('extensions_template')
        if isinstance(ext, str):
            ext = json.loads(ext)
        assert ext['extended_key_usage'] == ['OCSPSigning']
        assert ext['key_usage'] == ['digitalSignature']

    def test_system_template_seeds_ocsp_signing(self, app):
        with app.app_context():
            from services.template_service import TemplateService
            TemplateService.seed_system_templates()
            tpl = TemplateService.get_template_by_name('OCSP Signing')
            assert tpl is not None
            assert tpl.template_type == 'ocsp_signing'
            ext = json.loads(tpl.extensions_template)
            assert ext['extended_key_usage'] == ['OCSPSigning']
