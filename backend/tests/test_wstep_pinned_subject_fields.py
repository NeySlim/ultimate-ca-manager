"""Tests for the "hybrid subject template" feature: per-template pinned
O/OU/C/ST/L subject fields that override whatever a client's CSR or
AD-derivation supplies on WSTEP issuance, while CN/SAN stay dynamic (see
CertificateTemplate.pinned_subject_fields and
wstep_service._required_pinned_subject_fields/_merge_pinned_subject_fields).

Direct wstep_service.issue() calls, no SOAP/HTTP layer -- same pattern as
test_wstep_template_eku.py -- since the enforcement lives entirely in
issue() and its helpers, not in the protocol/auth parsing around it.
"""
import json
import logging

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import NameOID

from models import CA, CATemplatePin, db
from tests.ad_connector_support import mount_connector
from models.certificate_template import CertificateTemplate
from tests.fixtures.templates import delete_templates, template_ids_named
from services.ad_connector import lookup as ad_lookup
from services.wstep import wstep_service
from tests.windows_profile_support import connectors_kept, default_profile, default_realm
from tests.windows_profile_support import windows_profiles_restored  # noqa: F401


# The CAs and certificates this file issues are removed after it
pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')


@pytest.fixture(autouse=True)
def _connectors_put_back(app):
    """The connector rows this file deletes and rewrites are the session's: put back."""
    with connectors_kept(app), default_realm(app, 'HAGLAND.DOMAIN'):
        yield



def _make_csr(attrs=None, common_name=None):
    """A CSR with an arbitrary subject (given as x509.NameAttribute list),
    or just a CN when ``common_name`` is given, or fully naked (no CN, no
    SAN -- what real Windows GPO machine autoenrollment submits) when
    neither is given."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    if attrs is None and common_name is not None:
        attrs = [x509.NameAttribute(NameOID.COMMON_NAME, common_name)]
    csr = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name(attrs or [])
    ).sign(key, hashes.SHA256())
    return csr, key


def _configure_ad_connector(app):
    with app.app_context():
        mount_connector(server='dc1.hagland.domain', base_dn='DC=hagland,DC=domain',
                        bind_dn='svc-ucm', enabled=True)


def _clear_pinned_templates(app):
    with app.app_context():
        names = [
            'Test Pinned Template', 'Test Pinned Template A', 'Test Pinned Template B',
        ]
        delete_templates(template_ids_named(*names))
        db.session.commit()


def _configure_pinned_template(app, ca_id, name, pinned_subject_fields, extended_key_usage=None):
    """An active template pinned to ``ca_id`` (see _configure_acl_template
    in test_wstep_kerberos_issue.py for why pinning to the CA matters --
    _resolve_templates_for_ca falls back to every active template
    CA-wide when nothing is pinned, which would let unrelated leftover
    templates from other test modules win the tie-break)."""
    with app.app_context():
        extensions = {'extended_key_usage': extended_key_usage} if extended_key_usage else {}
        template = CertificateTemplate(
            name=name, template_type='client_auth',
            extensions_template=json.dumps(extensions), is_active=True,
            pinned_subject_fields=json.dumps(pinned_subject_fields),
        )
        db.session.add(template)
        db.session.flush()
        db.session.add(CATemplatePin(ca_id=ca_id, template_id=template.id))
        db.session.commit()
        return template.id


class TestMergePinnedSubjectFields:
    """Pure-function coverage of _merge_pinned_subject_fields -- no DB/Flask
    app needed (mirrors TestTemplateExtraEkus's style in
    test_wstep_template_eku.py)."""

    def test_empty_pinned_fields_is_a_noop(self):
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'host.example.test')])
        assert wstep_service._merge_pinned_subject_fields(subject, {}) is subject

    def test_adds_pinned_fields_to_subject_with_no_conflict(self):
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'host.example.test')])
        merged = wstep_service._merge_pinned_subject_fields(subject, {'O': 'Acme Corp', 'OU': 'IT'})
        assert merged.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == 'host.example.test'
        assert merged.get_attributes_for_oid(NameOID.ORGANIZATION_NAME)[0].value == 'Acme Corp'
        assert merged.get_attributes_for_oid(NameOID.ORGANIZATIONAL_UNIT_NAME)[0].value == 'IT'

    def test_replaces_existing_attribute_of_same_type(self):
        """The actual security property this feature exists for: a
        client-supplied O must be forced to the pinned value, not merely
        supplemented."""
        subject = x509.Name([
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Evil Corp'),
            x509.NameAttribute(NameOID.COMMON_NAME, 'host.example.test'),
        ])
        merged = wstep_service._merge_pinned_subject_fields(subject, {'O': 'Acme Corp'})
        org_attrs = merged.get_attributes_for_oid(NameOID.ORGANIZATION_NAME)
        assert len(org_attrs) == 1
        assert org_attrs[0].value == 'Acme Corp'
        assert merged.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == 'host.example.test'

    def test_pinned_block_ordered_before_remaining_attributes(self):
        """Conventional root-to-leaf order (C, ST, L, O, OU) ahead of
        whatever's left (CN here) -- see _PINNED_FIELD_ORDER."""
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'host.example.test')])
        merged = wstep_service._merge_pinned_subject_fields(
            subject, {'OU': 'IT', 'C': 'US', 'O': 'Acme Corp'}
        )
        oids = [attr.oid for attr in merged]
        assert oids == [
            NameOID.COUNTRY_NAME, NameOID.ORGANIZATION_NAME,
            NameOID.ORGANIZATIONAL_UNIT_NAME, NameOID.COMMON_NAME,
        ]

    def test_never_touches_cn(self):
        """pinned_fields can never contain 'CN' (validated at the API layer
        -- see _clean_pinned_subject_fields in api/v2/templates.py), but
        this confirms the merge itself has no code path that would drop or
        alter CN even if it somehow did."""
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'host.example.test')])
        merged = wstep_service._merge_pinned_subject_fields(subject, {'O': 'Acme Corp'})
        assert merged.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == 'host.example.test'


class TestTemplatePinnedFields:
    """Pure-function coverage of _template_pinned_fields -- no DB needed."""

    def test_none_template_returns_empty_dict(self):
        assert wstep_service._template_pinned_fields(None) == {}

    def test_unset_column_returns_empty_dict(self):
        template = CertificateTemplate(pinned_subject_fields=None)
        assert wstep_service._template_pinned_fields(template) == {}

    def test_malformed_json_returns_empty_dict_not_crash(self):
        template = CertificateTemplate(pinned_subject_fields='not json')
        assert wstep_service._template_pinned_fields(template) == {}

    def test_filters_unknown_keys_and_falsy_values(self):
        template = CertificateTemplate(
            pinned_subject_fields=json.dumps({'O': 'Acme Corp', 'CN': 'should-be-ignored', 'OU': ''})
        )
        assert wstep_service._template_pinned_fields(template) == {'O': 'Acme Corp'}


class TestRequiredPinnedSubjectFieldsConflict:
    """_required_pinned_subject_fields's CA-wide fallback conflict handling
    (matched_template is None -- the naked-CSR/no-EKU-match case)."""

    def test_matched_template_uses_only_its_own_pins(self, app, create_ca):
        ca_data = create_ca(cn='Pinned Fields Matched CA')
        try:
            with app.app_context():
                ca = db.session.get(CA, ca_data['id'])
                template = CertificateTemplate(
                    name='Test Pinned Template', template_type='client_auth',
                    extensions_template='{}', is_active=True,
                    pinned_subject_fields=json.dumps({'O': 'Acme Corp'}),
                )
                result = wstep_service._required_pinned_subject_fields(ca, template, profile=None)
            assert result == {'O': 'Acme Corp'}
        finally:
            _clear_pinned_templates(app)

    def test_conflicting_candidates_skip_field_and_log_warning(self, app, create_ca, caplog):
        ca_data = create_ca(cn='Pinned Fields Conflict CA')
        try:
            with app.app_context():
                ca = db.session.get(CA, ca_data['id'])
                _configure_pinned_template(
                    app, ca.id, 'Test Pinned Template A',
                    {'O': 'Acme Corp', 'C': 'US'}, extended_key_usage=['clientAuth'],
                )
                _configure_pinned_template(
                    app, ca.id, 'Test Pinned Template B',
                    {'O': 'Other Corp'}, extended_key_usage=['clientAuth'],
                )
                with caplog.at_level(logging.WARNING):
                    result = wstep_service._required_pinned_subject_fields(ca, None, profile=None)
            assert 'O' not in result
            assert result.get('C') == 'US'
            assert any('conflicting values' in r.message for r in caplog.records)
        finally:
            _clear_pinned_templates(app)

    def test_unmatched_with_single_candidate_applies_its_pins(self, app, create_ca):
        ca_data = create_ca(cn='Pinned Fields Unmatched CA')
        try:
            with app.app_context():
                ca = db.session.get(CA, ca_data['id'])
                _configure_pinned_template(
                    app, ca.id, 'Test Pinned Template',
                    {'O': 'Acme Corp', 'OU': 'IT'}, extended_key_usage=['clientAuth'],
                )
                result = wstep_service._required_pinned_subject_fields(ca, None, profile=None)
            assert result == {'O': 'Acme Corp', 'OU': 'IT'}
        finally:
            _clear_pinned_templates(app)


class TestPinnedSubjectFieldsIssuance:
    """End-to-end through wstep_service.issue()."""

    def test_naked_csr_ad_derived_cn_plus_pinned_org_fields(self, app, create_ca, monkeypatch):
        """The GPO machine-autoenrollment scenario: AD-derived CN and
        pinned O/OU land on the same issued cert."""
        ca_data = create_ca(cn='Pinned Fields Naked CA')
        _configure_ad_connector(app)
        try:
            with app.app_context():
                ca = db.session.get(CA, ca_data['id'])
                _configure_pinned_template(
                    app, ca.id, 'Test Pinned Template',
                    {'O': 'Acme Corp', 'OU': 'IT'}, extended_key_usage=['clientAuth'],
                )
                monkeypatch.setattr(
                    ad_lookup, 'lookup_computer_dns_hostname',
                    lambda _config, sam_account_name: 'win11.hagland.domain',
                )
                # Kerberos-bound issuance refuses when the AD Connector is
                # enabled but the requester SID lookup fails (KB5014754
                # strong mapping, #275) -- mock the SID like the other
                # Kerberos-bound tests do.
                monkeypatch.setattr(
                    ad_lookup, 'lookup_object_sid',
                    lambda _config, sam_account_name: 'S-1-5-21-3623811015-3361044348-30300820-1105',
                )
                csr, _key = _make_csr()
                cert_pem, err = wstep_service.issue(
                    ca, csr.public_bytes(Encoding.DER), validity_days=30,
                    kerberos_principal='WIN11$@HAGLAND.DOMAIN', profile=default_profile(),
                )
            assert err is None, err
            cert = x509.load_pem_x509_certificate(cert_pem.encode())
            assert cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == 'win11.hagland.domain'
            assert cert.subject.get_attributes_for_oid(NameOID.ORGANIZATION_NAME)[0].value == 'Acme Corp'
            assert cert.subject.get_attributes_for_oid(NameOID.ORGANIZATIONAL_UNIT_NAME)[0].value == 'IT'
        finally:
            _clear_pinned_templates(app)

    def test_client_supplied_org_field_is_overridden_not_merged(self, app, create_ca):
        """The actual reporter scenario: a manually-typed CSR (certmgr.msc/
        certreq) that misrepresents O must have it forced to the pinned
        value, not kept."""
        ca_data = create_ca(cn='Pinned Fields Override CA')
        try:
            with app.app_context():
                ca = db.session.get(CA, ca_data['id'])
                _configure_pinned_template(
                    app, ca.id, 'Test Pinned Template', {'O': 'Acme Corp'},
                )
                csr, _key = _make_csr(attrs=[
                    x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Evil Corp'),
                    x509.NameAttribute(NameOID.COMMON_NAME, 'device.hagland.domain'),
                ])
                cert_pem, err = wstep_service.issue(ca, csr.public_bytes(Encoding.DER), validity_days=30, profile=None)
            assert err is None, err
            cert = x509.load_pem_x509_certificate(cert_pem.encode())
            assert cert.subject.get_attributes_for_oid(NameOID.ORGANIZATION_NAME)[0].value == 'Acme Corp'
            assert cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == 'device.hagland.domain'
        finally:
            _clear_pinned_templates(app)

    def test_username_password_bound_issuance_still_applies_pins(self, app, create_ca):
        """Pinning doesn't need a Kerberos identity -- unlike Enroll ACL,
        it must also apply when kerberos_principal is None (the
        UsernamePassword-bound path)."""
        ca_data = create_ca(cn='Pinned Fields UP CA')
        try:
            with app.app_context():
                ca = db.session.get(CA, ca_data['id'])
                _configure_pinned_template(
                    app, ca.id, 'Test Pinned Template', {'O': 'Acme Corp'},
                )
                csr, _key = _make_csr(common_name='device.hagland.domain')
                cert_pem, err = wstep_service.issue(
                    ca, csr.public_bytes(Encoding.DER), validity_days=30, kerberos_principal=None, profile=None,
                )
            assert err is None, err
            cert = x509.load_pem_x509_certificate(cert_pem.encode())
            assert cert.subject.get_attributes_for_oid(NameOID.ORGANIZATION_NAME)[0].value == 'Acme Corp'
        finally:
            _clear_pinned_templates(app)

    def test_no_pinned_fields_leaves_existing_behavior_unchanged(self, app, create_ca):
        """A template with pinned_subject_fields unset (the default) must
        issue exactly as before this feature existed -- regression guard."""
        ca_data = create_ca(cn='Pinned Fields None CA')
        try:
            with app.app_context():
                ca = db.session.get(CA, ca_data['id'])
                _configure_pinned_template(app, ca.id, 'Test Pinned Template', {})
                csr, _key = _make_csr(attrs=[
                    x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Whatever Corp'),
                    x509.NameAttribute(NameOID.COMMON_NAME, 'device.hagland.domain'),
                ])
                cert_pem, err = wstep_service.issue(ca, csr.public_bytes(Encoding.DER), validity_days=30, profile=None)
            assert err is None, err
            cert = x509.load_pem_x509_certificate(cert_pem.encode())
            assert cert.subject.get_attributes_for_oid(NameOID.ORGANIZATION_NAME)[0].value == 'Whatever Corp'
        finally:
            _clear_pinned_templates(app)
