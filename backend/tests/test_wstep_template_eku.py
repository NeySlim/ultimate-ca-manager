"""Regression tests: WSTEP-issued certs carry the matched template's own
configured EKUs (``wstep_service._template_extra_ekus``), not just what a
CSR happened to ask for.

Context (NeySlim's PR #230 review, "Resync with dev (#243 just merged
there)"): upstream's CSR-EKU cap (security audit v2.203 item #3) never
honours Microsoft Smartcard Logon from a CSR's own EKU extension, whatever
``cert_type`` is -- only ``extra_ekus`` (explicit, uncapped admin intent)
still gets it onto the leaf. WSTEP now derives ``extra_ekus`` from the
matched template's own ``extended_key_usage`` config for exactly this
reason. This is meaningful today too, independent of whether #243 has been
resynced into this branch yet: even against the current (pre-#243)
``sign_csr``, a CSR that omits an EKU the admin configured on the matched
template would otherwise never get it.
"""
import json

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import ExtendedKeyUsageOID, ExtensionOID, NameOID

from models import CA, CATemplatePin, db
from models.certificate_template import CertificateTemplate
from models.system_config import SystemConfig
from tests.fixtures.templates import delete_templates
from services.wstep import wstep_service
from tests.windows_profile_support import windows_profiles_restored, restore, set_config, snapshot  # noqa: F401

SMARTCARD_LOGON = x509.ObjectIdentifier('1.3.6.1.4.1.311.20.2.2')


def _set_config(key, value):
    set_config(key, value)


@pytest.fixture(scope='module')
def smartcard_template_config(app, create_ca):
    ca_data = create_ca(cn='WSTEP Smartcard CA')
    keys = ('wstep_enabled', 'wstep_ca_refid', 'wstep_validity_days')
    with app.app_context():
        previous = snapshot(keys)
        ca = db.session.get(CA, ca_data['id'])
        _set_config('wstep_enabled', 'true')
        _set_config('wstep_ca_refid', ca.refid)
        _set_config('wstep_validity_days', '30')

        template = CertificateTemplate(
            name='WSTEP Smartcard Logon',
            template_type='usr_cert',
            key_type='RSA-2048',
            validity_days=365,
            digest='sha256',
            dn_template=json.dumps({'CN': '{cn}'}),
            extensions_template=json.dumps({
                'extended_key_usage': ['clientAuth', 'smartcardLogon'],
            }),
            is_active=True,
        )
        db.session.add(template)
        db.session.commit()
        pin = CATemplatePin(ca_id=ca.id, template_id=template.id)
        db.session.add(pin)
        db.session.commit()
        template_id = template.id

    yield ca_data

    with app.app_context():
        delete_templates([template_id])
        db.session.commit()
        restore(previous)


def _make_csr(common_name, ekus=None):
    """A CSR that -- like a real Windows client's -- carries its own EKU
    extension, but *without* Smartcard Logon: this is the realistic shape
    of the vulnerability. If WSTEP only trusted the CSR's own EKU set (or
    a cert_type ceiling), Smartcard Logon could never reach the issued
    cert even though the admin configured it on the matched template."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    builder = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    )
    if ekus:
        builder = builder.add_extension(x509.ExtendedKeyUsage(ekus), critical=False)
    return builder.sign(key, hashes.SHA256()), key


def _eku_set(cert):
    try:
        ext = cert.extensions.get_extension_for_oid(ExtensionOID.EXTENDED_KEY_USAGE)
    except x509.ExtensionNotFound:
        return set()
    return set(ext.value)


class TestTemplateExtraEkus:
    """Pure-function coverage of ``_template_extra_ekus`` -- no DB/Flask
    app needed."""

    def test_returns_configured_ekus_as_dotted_strings(self):
        template = CertificateTemplate(
            extensions_template=json.dumps({
                'extended_key_usage': ['clientAuth', 'smartcardLogon'],
            }),
        )
        oids = wstep_service._template_extra_ekus(template)
        assert set(oids) == {
            ExtendedKeyUsageOID.CLIENT_AUTH.dotted_string,
            SMARTCARD_LOGON.dotted_string,
        }

    def test_none_template_returns_empty_list(self):
        assert wstep_service._template_extra_ekus(None) == []

    def test_unconfigured_template_returns_empty_list(self):
        template = CertificateTemplate(extensions_template='{}')
        assert wstep_service._template_extra_ekus(template) == []

    def test_malformed_json_returns_empty_list_not_crash(self):
        template = CertificateTemplate(extensions_template='not json')
        assert wstep_service._template_extra_ekus(template) == []

    def test_unknown_eku_names_are_dropped(self):
        template = CertificateTemplate(
            extensions_template=json.dumps({
                'extended_key_usage': ['clientAuth', 'notARealEkuName'],
            }),
        )
        oids = wstep_service._template_extra_ekus(template)
        assert oids == [ExtendedKeyUsageOID.CLIENT_AUTH.dotted_string]


def test_issue_restores_smartcard_logon_from_matched_template(app, smartcard_template_config):
    """End-to-end through wstep_service.issue(): a CSR that only asks for
    clientAuth (no Smartcard Logon) still comes back with Smartcard Logon
    on the issued cert, because the matched template configured it --
    proving extra_ekus, not the CSR's own EKU set, is what actually landed
    it. Before this fix, WSTEP passed no extra_ekus at all, so Smartcard
    Logon would only ever appear if the CSR itself requested it."""
    csr, _key = _make_csr(
        'smartcard-user.hagland.domain',
        ekus=[ExtendedKeyUsageOID.CLIENT_AUTH],
    )
    with app.app_context():
        ca = db.session.get(CA, smartcard_template_config['id'])
        cert_pem, err = wstep_service.issue(ca, csr.public_bytes(Encoding.DER), validity_days=30, profile=None)

    assert err is None, err
    cert = x509.load_pem_x509_certificate(cert_pem.encode())
    ekus = _eku_set(cert)
    assert SMARTCARD_LOGON in ekus
    assert ExtendedKeyUsageOID.CLIENT_AUTH in ekus


def test_issue_with_no_matching_template_has_no_smartcard_logon(app, create_ca):
    """Control: without a matched template configuring it, Smartcard Logon
    never appears -- confirms the previous test's assertion is actually
    exercising template-driven extra_ekus, not some unconditional grant."""
    ca_data = create_ca(cn='WSTEP No Template CA')
    with app.app_context():
        ca = db.session.get(CA, ca_data['id'])
        _set_config('wstep_enabled', 'true')
        _set_config('wstep_ca_refid', ca.refid)
        _set_config('wstep_validity_days', '30')

        csr, _key = _make_csr(
            'plain-user.hagland.domain', ekus=[ExtendedKeyUsageOID.CLIENT_AUTH]
        )
        cert_pem, err = wstep_service.issue(ca, csr.public_bytes(Encoding.DER), validity_days=30, profile=None)

        assert err is None, err
        cert = x509.load_pem_x509_certificate(cert_pem.encode())
        assert SMARTCARD_LOGON not in _eku_set(cert)
