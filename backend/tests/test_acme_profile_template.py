"""ACME profile → certificate template binding (issue #327 follow-up).

An ACME order carries no template, so before this an ACME client could only
ever get the server_cert defaults (serverAuth, digitalSignature +
keyEncipherment on RSA). A profile (draft-ietf-acme-profiles) may now bind a
certificate template, as a SCEP profile does (#228): the template's key
usage and extended key usage govern every certificate issued under the
profile, validity and digest stay those of the profile, and the issued
certificate records the template link and its divergences (#258).

Covers the config layer (sanitize / validate / settings API), the signing
layer (TrustStoreService.sign_csr ``template_ext``, CertificateService
``template_id``) and the real finalize_order path end to end.
"""
import base64
import json

import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, ExtensionOID, NameOID

from models import db, CA, Certificate, SystemConfig
from models.certificate_template import CertificateTemplate
from services.acme import profiles as acme_profiles
from services.acme.acme_service import AcmeService
from tests.test_scep_rfc8894_operations import _load_ca_material

CONTENT_JSON = 'application/json'
OCSP_SIGNING = '1.3.6.1.5.5.7.3.9'


def _ku(cert):
    ku = cert.extensions.get_extension_for_oid(ExtensionOID.KEY_USAGE).value
    return {n for n in ('digital_signature', 'content_commitment', 'key_encipherment',
                        'data_encipherment', 'key_agreement', 'key_cert_sign', 'crl_sign')
            if getattr(ku, n)}


def _eku(cert):
    try:
        ext = cert.extensions.get_extension_for_oid(ExtensionOID.EXTENDED_KEY_USAGE)
    except x509.ExtensionNotFound:
        return None
    return set(ext.value)


def _usage(**on):
    flags = dict(digital_signature=False, content_commitment=False,
                 key_encipherment=False, data_encipherment=False,
                 key_agreement=False, key_cert_sign=False, crl_sign=False,
                 encipher_only=False, decipher_only=False)
    flags.update(on)
    return x509.KeyUsage(**flags)


def _csr(key, cn, extensions=()):
    builder = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
    for value, critical in extensions:
        builder = builder.add_extension(value, critical)
    return builder.sign(key, hashes.SHA256(), default_backend())


def _mk_template(app, name, ku, eku, template_type='custom', key_type='RSA-2048',
                 validity_days=30, digest='sha256'):
    with app.app_context():
        tpl = CertificateTemplate(
            name=name, template_type=template_type, key_type=key_type,
            validity_days=validity_days, digest=digest,
            extensions_template=json.dumps({'key_usage': ku, 'extended_key_usage': eku}),
        )
        db.session.add(tpl)
        db.session.commit()
        return tpl.id


def _drop_template(app, tpl_id):
    """Remove a template the way the application would leave the database.

    The route refuses to delete a template certificates still point at; these
    tests delete the row directly, so the link has to be cleared first. Left
    behind, it is a certificate referencing a template that no longer exists —
    a row the schema forbids, which outlives the test and the file."""
    from sqlalchemy import text

    with app.app_context():
        tpl = db.session.get(CertificateTemplate, tpl_id)
        if not tpl:
            return
        db.session.execute(
            text('UPDATE certificates SET template_id = NULL '
                 'WHERE template_id = :tpl'), {'tpl': tpl_id})
        db.session.delete(tpl)
        db.session.commit()


@pytest.fixture
def mtls_template(app):
    """A client-auth template: digitalSignature only, clientAuth only."""
    tpl_id = _mk_template(app, 'acme-mtls-tpl', ['digitalSignature'], ['clientAuth'])
    yield tpl_id
    _drop_template(app, tpl_id)


def _install_profiles(app, profiles):
    with app.app_context():
        row = SystemConfig.query.filter_by(key=acme_profiles.CONFIG_KEY).first()
        if not row:
            row = SystemConfig(key=acme_profiles.CONFIG_KEY, value='')
            db.session.add(row)
        row.value = json.dumps(profiles)
        db.session.commit()


def _clear_profiles(app):
    with app.app_context():
        row = SystemConfig.query.filter_by(key=acme_profiles.CONFIG_KEY).first()
        if row:
            db.session.delete(row)
            db.session.commit()


class TestProfileConfig:

    def test_template_id_is_carried_and_sanitized(self, app, mtls_template):
        _install_profiles(app, {
            'mtls': {'validity_days': 30, 'template_id': mtls_template},
            'plain': {'validity_days': 90},
            'str': {'template_id': str(mtls_template)},
            'zero': {'template_id': 0},
            'junk': {'template_id': 'abc'},
            'flag': {'template_id': True},
        })
        try:
            with app.app_context():
                profiles = acme_profiles.get_profiles()
                assert profiles['mtls']['template_id'] == mtls_template
                assert profiles['plain']['template_id'] is None
                assert profiles['str']['template_id'] == mtls_template
                assert profiles['zero']['template_id'] is None
                assert profiles['junk']['template_id'] is None
                assert profiles['flag']['template_id'] is None
                params = acme_profiles.issuance_params('mtls')
                assert params == {'validity_days': 30, 'digest': 'sha256',
                                  'digest_explicit': False, 'template_id': mtls_template}
                assert acme_profiles.issuance_params('plain')['template_id'] is None
        finally:
            _clear_profiles(app)

    def test_validate_accepts_a_bindable_template(self, app, mtls_template):
        with app.app_context():
            ok, err = acme_profiles.validate_config(
                {'mtls': {'validity_days': 30, 'template_id': mtls_template}})
            assert ok, err
            ok, err = acme_profiles.validate_config({'x': {'template_id': None}})
            assert ok, err

    @pytest.mark.parametrize('bad', ['abc', 0, -1, True, 1.5])
    def test_validate_refuses_non_positive_int(self, app, bad):
        with app.app_context():
            ok, err = acme_profiles.validate_config({'p': {'template_id': bad}})
            assert not ok
            assert 'template_id must be a positive integer' in err

    def test_validate_refuses_unknown_template(self, app):
        with app.app_context():
            ok, err = acme_profiles.validate_config({'p': {'template_id': 999999}})
            assert not ok and 'not found' in err

    def test_validate_refuses_ca_template(self, app):
        tpl_id = _mk_template(app, 'acme-ca-tpl', ['keyCertSign'], [], template_type='ca')
        try:
            with app.app_context():
                ok, err = acme_profiles.validate_config({'p': {'template_id': tpl_id}})
                assert not ok and 'CA templates' in err
        finally:
            with app.app_context():
                db.session.delete(db.session.get(CertificateTemplate, tpl_id))
                db.session.commit()

    def test_validate_refuses_sensitive_ekus(self, app):
        tpl_id = _mk_template(app, 'acme-ocsp-tpl', ['digitalSignature'],
                              ['OCSPSigning', 'clientAuth'])
        try:
            with app.app_context():
                ok, err = acme_profiles.validate_config({'p': {'template_id': tpl_id}})
                assert not ok
                assert OCSP_SIGNING in err and 'cannot be issued over ACME' in err
        finally:
            with app.app_context():
                db.session.delete(db.session.get(CertificateTemplate, tpl_id))
                db.session.commit()

    def test_settings_api_roundtrip(self, app, auth_client, mtls_template):
        try:
            r = auth_client.patch('/api/v2/acme/settings', json={'profiles': {
                'mtls': {'description': 'mTLS client', 'validity_days': 30,
                         'digest': 'sha256', 'template_id': mtls_template},
            }})
            assert r.status_code == 200, r.data
            r = auth_client.get('/api/v2/acme/settings')
            assert r.get_json()['data']['profiles']['mtls']['template_id'] == mtls_template

            r = auth_client.patch('/api/v2/acme/settings', json={'profiles': {
                'bad': {'validity_days': 30, 'template_id': 999999},
            }})
            assert r.status_code == 400
            assert 'not found' in r.get_json().get('message', r.get_data(as_text=True))
        finally:
            _clear_profiles(app)


class TestBackupPortability:
    """A backup carries the binding by template name, not by numeric id."""

    def test_export_adds_the_template_name(self, app, mtls_template):
        _install_profiles(app, {
            'mtls': {'validity_days': 30, 'template_id': mtls_template},
            'plain': {'validity_days': 90},
            'dangling': {'validity_days': 30, 'template_id': 999999, 'template_name': 'stale'},
        })
        try:
            with app.app_context():
                exported = json.loads(acme_profiles.export_config_json())
                assert exported['mtls']['template_name'] == 'acme-mtls-tpl'
                assert exported['mtls']['template_id'] == mtls_template
                assert 'template_name' not in exported['plain']
                assert 'template_name' not in exported['dangling']
        finally:
            _clear_profiles(app)

    def test_export_of_the_settings_section_carries_the_name(self, app, mtls_template):
        from services.backup_service import BackupService
        _install_profiles(app, {'mtls': {'validity_days': 30, 'template_id': mtls_template}})
        try:
            with app.app_context():
                settings = BackupService()._export_configuration(True)['settings']
                assert json.loads(settings[acme_profiles.CONFIG_KEY])['mtls']['template_name'] == 'acme-mtls-tpl'
        finally:
            _clear_profiles(app)

    def test_remap_points_at_the_template_of_that_name(self, app, mtls_template):
        _install_profiles(app, {
            'mtls': {'validity_days': 30, 'template_id': 424242, 'template_name': 'acme-mtls-tpl'},
            'gone': {'validity_days': 30, 'template_id': 424243, 'template_name': 'no-such-template'},
            'idonly': {'validity_days': 30, 'template_id': mtls_template},
            'dangling': {'validity_days': 30, 'template_id': 424244},
            'plain': {'validity_days': 90},
        })
        try:
            with app.app_context():
                changed = acme_profiles.remap_template_bindings()
                db.session.commit()
                assert changed == 3
                profiles = acme_profiles.get_profiles()
                assert profiles['mtls']['template_id'] == mtls_template
                assert profiles['gone']['template_id'] is None
                assert profiles['idonly']['template_id'] == mtls_template
                assert profiles['dangling']['template_id'] is None
                assert profiles['plain']['template_id'] is None
                stored = json.loads(SystemConfig.query.filter_by(key=acme_profiles.CONFIG_KEY).first().value)
                assert all('template_name' not in spec for spec in stored.values())
        finally:
            _clear_profiles(app)

    def test_round_trip_restores_the_binding_by_name(self, app):
        """Full backup → source template gone, id slot taken by a decoy →
        restore: the profile follows the template name, not the old id."""
        from services.backup import BackupService
        include = {k: False for k in (
            'cas', 'certificates', 'users', 'configuration', 'acme_accounts',
            'acme_eab_credentials', 'email_password', 'groups', 'custom_roles',
            'certificate_templates', 'trusted_certificates', 'sso_providers',
            'hsm_providers', 'api_keys', 'smtp_config', 'notification_config',
            'certificate_policies', 'auth_certificates', 'dns_providers',
            'acme_domains', 'acme_local_domains', 'https_server')}
        include.update(configuration=True, certificate_templates=True)
        password = 'roundtrip-password-123'
        tpl_id = _mk_template(app, 'acme-rt-tpl', ['digitalSignature'], ['clientAuth'])
        _install_profiles(app, {'mtls': {'validity_days': 30, 'template_id': tpl_id}})
        decoy_id = None
        try:
            with app.app_context():
                blob = BackupService().create_backup(password, include=include)
            _clear_profiles(app)
            with app.app_context():
                db.session.delete(db.session.get(CertificateTemplate, tpl_id))
                db.session.commit()
            decoy_id = _mk_template(app, 'acme-rt-decoy', ['digitalSignature'], ['serverAuth'])
            with app.app_context():
                BackupService().restore_backup(blob, password)
                restored = CertificateTemplate.query.filter_by(name='acme-rt-tpl').first()
                assert restored is not None
                assert acme_profiles.get_profiles()['mtls']['template_id'] == restored.id
                tpl_id = restored.id
        finally:
            _clear_profiles(app)
            with app.app_context():
                for tid in (tpl_id, decoy_id):
                    tpl = db.session.get(CertificateTemplate, tid) if tid else None
                    if tpl:
                        db.session.delete(tpl)
                db.session.commit()

    def test_remap_without_config_is_a_noop(self, app):
        _clear_profiles(app)
        with app.app_context():
            assert acme_profiles.remap_template_bindings() == 0


class TestBoundTemplateCannotBeDeleted:
    """A profile keeps only the numeric id; SQLite reuses it for the next
    template, so a binding left behind would silently apply a foreign
    template. Deletion is refused until the profile is unbound."""

    def test_single_delete_refused_then_allowed(self, app, auth_client):
        tpl_id = _mk_template(app, 'acme-bound-del', ['digitalSignature'], ['clientAuth'])
        _install_profiles(app, {'mtls': {'validity_days': 30, 'template_id': tpl_id}})
        try:
            r = auth_client.delete(f'/api/v2/templates/{tpl_id}')
            assert r.status_code == 409, r.data
            assert 'ACME profile' in r.get_data(as_text=True) and 'mtls' in r.get_data(as_text=True)
        finally:
            _clear_profiles(app)
        r = auth_client.delete(f'/api/v2/templates/{tpl_id}')
        assert r.status_code == 204, r.data

    def test_bulk_delete_reports_the_binding(self, app, auth_client):
        tpl_id = _mk_template(app, 'acme-bound-bulk', ['digitalSignature'], ['clientAuth'])
        _install_profiles(app, {'mtls': {'validity_days': 30, 'template_id': tpl_id}})
        try:
            r = auth_client.post('/api/v2/templates/bulk/delete',
                                 data=json.dumps({'ids': [tpl_id]}), content_type=CONTENT_JSON)
            assert r.status_code == 200, r.data
            body = r.get_json()
            failed = body.get('data', body).get('failed') or []
            assert any(f['id'] == tpl_id and 'ACME profile' in f['error'] for f in failed), body
            with app.app_context():
                assert db.session.get(CertificateTemplate, tpl_id) is not None
        finally:
            _clear_profiles(app)
            with app.app_context():
                tpl = db.session.get(CertificateTemplate, tpl_id)
                if tpl:
                    db.session.delete(tpl)
                    db.session.commit()


class TestSignCsrWithTemplate:
    """TrustStoreService.sign_csr(template_ext=...)."""

    @staticmethod
    def _sign(app, ca, csr, template_ext, **kwargs):
        from services.trust_store import TrustStoreService
        with app.app_context():
            _, ca_cert, ca_key = _load_ca_material(ca['id'])
            pem = TrustStoreService.sign_csr(
                csr.public_bytes(serialization.Encoding.PEM), ca_cert, ca_key,
                validity_days=30, cert_type='server_cert', template_ext=template_ext,
                **kwargs)
        return x509.load_pem_x509_certificate(pem, default_backend())

    def test_template_ku_eku_replace_the_csr_ones(self, app, create_ca):
        ca = create_ca(cn='ACME tpl CA 1')
        key = rsa.generate_private_key(65537, 2048, default_backend())
        csr = _csr(key, 'dev.test', [
            (_usage(digital_signature=True, key_encipherment=True), True),
            (x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False)])
        cert = self._sign(app, ca, csr, {
            'key_usage': ['digitalSignature'], 'extended_key_usage': ['clientAuth']})
        assert _ku(cert) == {'digital_signature'}
        assert _eku(cert) == {ExtendedKeyUsageOID.CLIENT_AUTH}

    def test_template_applies_to_a_csr_without_extensions(self, app, create_ca):
        """certbot's shape: no KU, no EKU in the CSR."""
        ca = create_ca(cn='ACME tpl CA 2')
        key = rsa.generate_private_key(65537, 2048, default_backend())
        cert = self._sign(app, ca, _csr(key, 'bare.test'), {
            'key_usage': ['digitalSignature', 'nonRepudiation'],
            'extended_key_usage': ['serverAuth', 'clientAuth']})
        assert _ku(cert) == {'digital_signature', 'content_commitment'}
        assert _eku(cert) == {ExtendedKeyUsageOID.SERVER_AUTH, ExtendedKeyUsageOID.CLIENT_AUTH}

    def test_empty_template_changes_nothing(self, app, create_ca):
        ca = create_ca(cn='ACME tpl CA 3')
        key = rsa.generate_private_key(65537, 2048, default_backend())
        cert = self._sign(app, ca, _csr(key, 'plain.test'), {})
        assert _ku(cert) == {'digital_signature', 'key_encipherment'}
        assert _eku(cert) == {ExtendedKeyUsageOID.SERVER_AUTH}

    def test_sensitive_template_ekus_are_dropped_for_protocol_paths(self, app, create_ca):
        ca = create_ca(cn='ACME tpl CA 4')
        key = rsa.generate_private_key(65537, 2048, default_backend())
        cert = self._sign(app, ca, _csr(key, 'ocsp.test'), {
            'extended_key_usage': ['OCSPSigning', 'clientAuth']})
        assert _eku(cert) == {ExtendedKeyUsageOID.CLIENT_AUTH}

    def test_template_with_only_refused_ekus_falls_back_to_type_default(self, app, create_ca):
        """A policy entirely refused is still a policy: the CSR's own request
        (clientAuth here) must not slip back in; the cert_type default does."""
        ca = create_ca(cn='ACME tpl CA 5')
        key = rsa.generate_private_key(65537, 2048, default_backend())
        csr = _csr(key, 'only-ocsp.test', [
            (x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), False)])
        cert = self._sign(app, ca, csr, {'extended_key_usage': ['OCSPSigning']})
        assert _eku(cert) == {ExtendedKeyUsageOID.SERVER_AUTH}

    def test_template_without_eku_policy_keeps_csr_ekus(self, app, create_ca):
        ca = create_ca(cn='ACME tpl CA 5b')
        key = rsa.generate_private_key(65537, 2048, default_backend())
        csr = _csr(key, 'no-policy.test', [
            (x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), False)])
        cert = self._sign(app, ca, csr, {'key_usage': ['digitalSignature']})
        assert _eku(cert) == {ExtendedKeyUsageOID.CLIENT_AUTH}

    def test_admin_path_keeps_sensitive_template_ekus(self, app, create_ca):
        ca = create_ca(cn='ACME tpl CA 6')
        key = rsa.generate_private_key(65537, 2048, default_backend())
        cert = self._sign(app, ca, _csr(key, 'admin.test'), {
            'extended_key_usage': ['OCSPSigning']}, allow_sensitive_ekus=True)
        assert _eku(cert) == {x509.ObjectIdentifier(OCSP_SIGNING)}

    def test_extra_ekus_merge_on_top_of_template(self, app, create_ca):
        ca = create_ca(cn='ACME tpl CA 7')
        key = rsa.generate_private_key(65537, 2048, default_backend())
        cert = self._sign(app, ca, _csr(key, 'extra.test'), {
            'extended_key_usage': ['clientAuth']}, extra_ekus=['serverAuth'])
        assert _eku(cert) == {ExtendedKeyUsageOID.CLIENT_AUTH, ExtendedKeyUsageOID.SERVER_AUTH}

    def test_template_key_encipherment_is_clamped_on_ec_key(self, app, create_ca):
        """#327: the key-algorithm rule still applies on top of the template."""
        ca = create_ca(cn='ACME tpl CA 8')
        key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        cert = self._sign(app, ca, _csr(key, 'ec-tpl.test'), {
            'key_usage': ['digitalSignature', 'keyEncipherment'],
            'extended_key_usage': ['serverAuth']})
        assert _ku(cert) == {'digital_signature'}

    def test_template_never_grants_ca_bits(self, app, create_ca):
        ca = create_ca(cn='ACME tpl CA 9')
        key = rsa.generate_private_key(65537, 2048, default_backend())
        cert = self._sign(app, ca, _csr(key, 'cabits.test'), {
            'key_usage': ['digitalSignature', 'keyCertSign', 'cRLSign']})
        assert _ku(cert) == {'digital_signature'}
        bc = cert.extensions.get_extension_for_oid(ExtensionOID.BASIC_CONSTRAINTS).value
        assert bc.ca is False


class TestCertificateServiceTemplate:
    """CertificateService.sign_csr(template_id=...) records the link."""

    def test_template_link_and_overrides_recorded(self, app, create_ca, mtls_template):
        from services.cert_service import CertificateService
        ca = create_ca(cn='ACME tpl svc CA')
        key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        csr = _csr(key, 'svc.test')
        with app.app_context():
            ca_row = db.session.get(CA, ca['id'])
            row = Certificate(
                refid='acme-tpl-svc', descr='svc.test', caref=ca_row.refid,
                csr=base64.b64encode(csr.public_bytes(serialization.Encoding.PEM)).decode(),
                cert_type='server_cert', source='acme', created_by='acme')
            db.session.add(row)
            db.session.flush()
            signed = CertificateService.sign_csr(
                cert_id=row.id, caref=ca_row.refid, cert_type='server_cert',
                validity_days=90, digest='sha256', username='acme',
                template_id=mtls_template)
            db.session.commit()
            assert signed.template_id == mtls_template
            # RSA-2048 template, 30 days: the EC key and the profile's 90 days diverge
            assert sorted(signed.template_overrides_list) == ['key_type', 'validity_days']
            cert = x509.load_pem_x509_certificate(base64.b64decode(signed.crt), default_backend())
        assert _eku(cert) == {ExtendedKeyUsageOID.CLIENT_AUTH}
        assert _ku(cert) == {'digital_signature'}

    def test_ed25519_key_diverges_from_an_rsa_template(self, app, create_ca, mtls_template):
        from cryptography.hazmat.primitives.asymmetric import ed25519
        from services.cert_service import CertificateService
        ca = create_ca(cn='ACME tpl ed25519 CA')
        key = ed25519.Ed25519PrivateKey.generate()
        csr = (x509.CertificateSigningRequestBuilder()
               .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'ed.test')]))
               .sign(key, None, default_backend()))
        with app.app_context():
            ca_row = db.session.get(CA, ca['id'])
            row = Certificate(
                refid='acme-tpl-ed25519', descr='ed.test', caref=ca_row.refid,
                csr=base64.b64encode(csr.public_bytes(serialization.Encoding.PEM)).decode(),
                cert_type='server_cert', source='acme', created_by='acme')
            db.session.add(row)
            db.session.flush()
            signed = CertificateService.sign_csr(
                cert_id=row.id, caref=ca_row.refid, cert_type='server_cert',
                validity_days=30, digest='sha256', username='acme',
                template_id=mtls_template)
            db.session.commit()
            assert 'key_type' in signed.template_overrides_list
            assert 'validity_days' not in signed.template_overrides_list

    def test_deleted_template_does_not_break_signing(self, app, create_ca):
        from services.cert_service import CertificateService
        ca = create_ca(cn='ACME tpl gone CA')
        key = rsa.generate_private_key(65537, 2048, default_backend())
        csr = _csr(key, 'gone.test')
        with app.app_context():
            ca_row = db.session.get(CA, ca['id'])
            row = Certificate(
                refid='acme-tpl-gone', descr='gone.test', caref=ca_row.refid,
                csr=base64.b64encode(csr.public_bytes(serialization.Encoding.PEM)).decode(),
                cert_type='server_cert', source='acme', created_by='acme')
            db.session.add(row)
            db.session.flush()
            signed = CertificateService.sign_csr(
                cert_id=row.id, caref=ca_row.refid, cert_type='server_cert',
                validity_days=90, digest='sha256', username='acme',
                template_id=999999)
            db.session.commit()
            assert signed.template_id is None
            cert = x509.load_pem_x509_certificate(base64.b64decode(signed.crt), default_backend())
        assert _eku(cert) == {ExtendedKeyUsageOID.SERVER_AUTH}


class TestFinalizeWithBoundTemplate:
    """The real finalize_order path: order → profile → template → leaf."""

    @staticmethod
    def _order(profile):
        import uuid
        from models.acme_models import AcmeAccount, AcmeOrder
        acct = AcmeAccount(jwk='{}', jwk_thumbprint=uuid.uuid4().hex + uuid.uuid4().hex[:11],
                           status='valid')
        db.session.add(acct)
        db.session.flush()
        order = AcmeOrder(account_id=acct.account_id, status='ready', profile=profile,
                          identifiers=json.dumps([{'type': 'dns', 'value': 'web.example.com'}]))
        db.session.add(order)
        db.session.commit()
        return order

    def _finalize(self, app, monkeypatch, create_ca, profile, cn='web.example.com'):
        ca = create_ca(cn=f'ACME finalize CA {profile or "none"}')
        with app.app_context():
            ca_refid = db.session.get(CA, ca['id']).refid
            order = self._order(profile)
            service = AcmeService(base_url='http://localhost')
            from utils import caa_checker
            monkeypatch.setattr(caa_checker, 'check_caa_for_domains',
                                lambda *a, **k: (True, 'allowed'))
            monkeypatch.setattr(service, '_resolve_ca_for_domains', lambda _d: ca_refid)
            key = ec.generate_private_key(ec.SECP256R1(), default_backend())
            csr = _csr(key, cn, [(x509.SubjectAlternativeName([x509.DNSName(cn)]), False)])
            csr_pem = csr.public_bytes(serialization.Encoding.PEM).decode()
            service.begin_order_processing(order)
            service._finalizing_order_id = order.order_id
            success, error = service.finalize_order(order.order_id, csr_pem)
            service._finalizing_order_id = None
            assert success, error
            db.session.refresh(order)
            row = db.session.get(Certificate, order.certificate_id)
            cert = x509.load_pem_x509_certificate(base64.b64decode(row.crt), default_backend())
            return cert, row.template_id, row.template_overrides_list

    def test_bound_template_governs_the_acme_leaf(self, app, monkeypatch, create_ca, mtls_template):
        _install_profiles(app, {'mtls': {'validity_days': 30, 'template_id': mtls_template}})
        try:
            cert, tpl_id, overrides = self._finalize(app, monkeypatch, create_ca, 'mtls')
        finally:
            _clear_profiles(app)
        assert _eku(cert) == {ExtendedKeyUsageOID.CLIENT_AUTH}
        assert _ku(cert) == {'digital_signature'}
        assert (cert.not_valid_after_utc - cert.not_valid_before_utc).days in (29, 30)
        assert tpl_id == mtls_template
        assert 'key_type' in overrides  # EC key against an RSA-2048 template

    def test_profile_without_template_keeps_defaults(self, app, monkeypatch, create_ca):
        _install_profiles(app, {'plain': {'validity_days': 7}})
        try:
            cert, tpl_id, _ = self._finalize(app, monkeypatch, create_ca, 'plain')
        finally:
            _clear_profiles(app)
        assert _eku(cert) == {ExtendedKeyUsageOID.SERVER_AUTH}
        assert _ku(cert) == {'digital_signature'}
        assert tpl_id is None
