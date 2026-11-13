"""End-to-end tests for KB5014754 strong certificate mapping via
wstep_service.issue() -- the SID security extension gets embedded whenever
a Kerberos principal resolves and the AD Connector is configured/enabled,
independent of whether the CSR is naked (see issue()'s docstring and
services/ad_connector/lookup.py's lookup_object_sid).

Direct wstep_service.issue() calls, no SOAP/HTTP layer -- same pattern as
test_wstep_template_eku.py, since the enforcement lives entirely in
issue() and its helpers.
"""
import contextlib

import pytest

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from models import CA, CATemplatePin, db
from tests.ad_connector_support import clear_connectors, mount_connector
from models.certificate_template import CertificateTemplate
from services.ad_connector import lookup as ad_lookup
from services.trust_store.csr_operations_mixin import _SID_SECURITY_EXT_OID
from services.wstep import wstep_service
from tests.fixtures.templates import delete_templates
from tests.windows_profile_support import connectors_kept, default_profile, default_realm
from tests.windows_profile_support import windows_profiles_restored  # noqa: F401


# The CAs and certificates this file issues are removed after it
pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')


@pytest.fixture(autouse=True)
def _connectors_put_back(app):
    """The connector rows this file deletes and rewrites are the session's: put back."""
    with connectors_kept(app), default_realm(app, 'HAGLAND.DOMAIN'):
        yield


_REAL_SID = 'S-1-5-21-1608104657-630783805-1473387121-1105'
KERBEROS_MACHINE_PRINCIPAL = 'WIN11$@HAGLAND.DOMAIN'


def _make_csr(common_name=None):
    """A naked (no CN, no SAN) CSR when common_name is None -- what real
    Windows GPO machine autoenrollment submits -- else a normal CSR with
    its own subject and clientAuth, e.g. a manually-typed certmgr.msc/certreq request."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    attrs = [x509.NameAttribute(NameOID.COMMON_NAME, common_name)] if common_name else []
    builder = x509.CertificateSigningRequestBuilder().subject_name(x509.Name(attrs))
    if common_name:
        builder = builder.add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
    return builder.sign(key, hashes.SHA256()), key


def _configure_ad_connector(app, enabled=True):
    with app.app_context():
        mount_connector(server='dc1.hagland.domain', base_dn='DC=hagland,DC=domain',
                        bind_dn='svc-ucm', enabled=enabled)


def _clear_ad_connector(app):
    with app.app_context():
        clear_connectors()


@contextlib.contextmanager
def _supplied_subject_template(app, ca_id):
    """Pins to ``ca_id`` a template whose subject the client supplies (0x00010001):
    a manual request keeps its own subject only under such a template."""
    with app.app_context():
        template = CertificateTemplate(name=f'Strong Mapping supplied subject {ca_id}',
                                       template_type='usr_cert', is_active=True,
                                       extensions_template='{"extended_key_usage": ["clientAuth"]}')
        db.session.add(template)
        db.session.flush()
        db.session.add(CATemplatePin(ca_id=ca_id, template_id=template.id))
        db.session.commit()
        template_id = template.id
    try:
        yield
    finally:
        with app.app_context():
            delete_templates([template_id])
            db.session.commit()


def _sid_extension_value(cert):
    try:
        return cert.extensions.get_extension_for_oid(_SID_SECURITY_EXT_OID)
    except x509.ExtensionNotFound:
        return None


class TestStrongCertMapping:
    def test_naked_csr_kerberos_bound_gets_sid_extension(self, app, create_ca, monkeypatch):
        """GPO machine autoenrollment: naked CSR, AD-derived CN, AND the
        SID extension, both present on the same issued cert."""
        ca_data = create_ca(cn='Strong Mapping Naked CA')
        _configure_ad_connector(app)
        monkeypatch.setattr(ad_lookup, 'lookup_computer_dns_hostname', lambda _config, sam: 'win11.hagland.domain')
        monkeypatch.setattr(ad_lookup, 'lookup_object_sid', lambda _config, sam: _REAL_SID)

        csr, _key = _make_csr()
        with app.app_context():
            ca = db.session.get(CA, ca_data['id'])
            cert_pem, err = wstep_service.issue(
                ca, csr.public_bytes(Encoding.DER), validity_days=30,
                kerberos_principal=KERBEROS_MACHINE_PRINCIPAL, profile=default_profile(),
            )
        assert err is None, err
        cert = x509.load_pem_x509_certificate(cert_pem.encode())
        assert cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == 'win11.hagland.domain'
        ext = _sid_extension_value(cert)
        assert ext is not None
        assert ext.critical is False

    def test_non_naked_csr_kerberos_bound_also_gets_sid_extension(self, app, create_ca, monkeypatch):
        """Manual enrollment (certmgr.msc/certreq, a CSR with its own
        subject) also gets the SID extension -- proves this is independent
        of _is_naked_csr, unlike the AD-derived-subject mechanism."""
        ca_data = create_ca(cn='Strong Mapping Manual CA')
        _configure_ad_connector(app)
        monkeypatch.setattr(ad_lookup, 'lookup_object_sid', lambda _config, sam: _REAL_SID)

        csr, _key = _make_csr(common_name='win11-manual.hagland.domain')
        with _supplied_subject_template(app, ca_data['id']), app.app_context():
            ca = db.session.get(CA, ca_data['id'])
            cert_pem, err = wstep_service.issue(
                ca, csr.public_bytes(Encoding.DER), validity_days=30,
                kerberos_principal=KERBEROS_MACHINE_PRINCIPAL, profile=default_profile(),
            )
        assert err is None, err
        cert = x509.load_pem_x509_certificate(cert_pem.encode())
        assert cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == 'win11-manual.hagland.domain'
        assert _sid_extension_value(cert) is not None

    def test_ad_connector_not_configured_issues_normally_without_extension(self, app, create_ca, monkeypatch):
        """The feature doesn't apply at all when AD Connector isn't
        configured/enabled -- regression guard for every existing
        Kerberos-bound WSTEP install that has never set up AD Connector.
        A spy proves lookup_object_sid is never even called, not just
        that it happens to return something falsy."""
        ca_data = create_ca(cn='Strong Mapping Unconfigured CA')
        _clear_ad_connector(app)

        def _fail_if_called(_config, sam):
            raise AssertionError('lookup_object_sid must not be called when AD Connector is unconfigured')

        monkeypatch.setattr(ad_lookup, 'lookup_object_sid', _fail_if_called)

        csr, _key = _make_csr(common_name='win11-manual.hagland.domain')
        with _supplied_subject_template(app, ca_data['id']), app.app_context():
            ca = db.session.get(CA, ca_data['id'])
            cert_pem, err = wstep_service.issue(
                ca, csr.public_bytes(Encoding.DER), validity_days=30,
                kerberos_principal=KERBEROS_MACHINE_PRINCIPAL, profile=default_profile(),
            )
        assert err is None, err
        cert = x509.load_pem_x509_certificate(cert_pem.encode())
        assert _sid_extension_value(cert) is None

    def test_ad_connector_configured_but_lookup_fails_refuses_issuance(self, app, create_ca, monkeypatch):
        """The real 'fail closed' case: AD Connector is enabled, but this
        specific request's SID can't be resolved (account not found, LDAP
        error, ...) -- issuance must be refused, not silently downgraded
        to a weaker-mapped cert."""
        ca_data = create_ca(cn='Strong Mapping Lookup Fail CA')
        _configure_ad_connector(app)
        monkeypatch.setattr(ad_lookup, 'lookup_object_sid', lambda _config, sam: None)

        csr, _key = _make_csr(common_name='win11-manual.hagland.domain')
        with app.app_context():
            ca = db.session.get(CA, ca_data['id'])
            cert_pem, err = wstep_service.issue(
                ca, csr.public_bytes(Encoding.DER), validity_days=30,
                kerberos_principal=KERBEROS_MACHINE_PRINCIPAL, profile=default_profile(),
            )
        assert cert_pem is None
        assert err is not None

    def test_username_password_bound_never_gets_sid_extension(self, app, create_ca, monkeypatch):
        """No per-request AD identity exists on the UsernamePassword-bound
        path (kerberos_principal=None) -- same limitation Enroll ACL
        already documents. A spy proves lookup_object_sid is never called,
        even with AD Connector configured and enabled."""
        ca_data = create_ca(cn='Strong Mapping UP CA')
        _configure_ad_connector(app)

        def _fail_if_called(_config, sam):
            raise AssertionError('lookup_object_sid must not be called for UsernamePassword-bound issuance')

        monkeypatch.setattr(ad_lookup, 'lookup_object_sid', _fail_if_called)

        csr, _key = _make_csr(common_name='device.hagland.domain')
        with app.app_context():
            ca = db.session.get(CA, ca_data['id'])
            cert_pem, err = wstep_service.issue(
                ca, csr.public_bytes(Encoding.DER), validity_days=30, kerberos_principal=None,
                profile=default_profile(),
            )
        assert err is None, err
        cert = x509.load_pem_x509_certificate(cert_pem.encode())
        assert _sid_extension_value(cert) is None


def _configure_connector_row(app, **fields):
    with app.app_context():
        values = dict(server='dc1.hagland.domain', base_dn='DC=hagland,DC=domain',
                      bind_dn='svc-ucm', enabled=True)
        values.update(fields)
        mount_connector(**values)


def _issue_supplied_subject(app, ca_id, principal):
    csr, _key = _make_csr(common_name='win11-manual.hagland.domain')
    with _supplied_subject_template(app, ca_id), app.app_context():
        ca = db.session.get(CA, ca_id)
        return wstep_service.issue(ca, csr.public_bytes(Encoding.DER), validity_days=30,
                                   kerberos_principal=principal, profile=default_profile())


class TestSidCheckIsNeverSkipped:
    """An enabled connector that cannot resolve the requester refuses: issuing under a
    template that keeps the request's subject would drop the SID extension (KB5014754)."""

    @pytest.fixture(autouse=True)
    def _no_connector_left_behind(self, app):
        yield
        _clear_ad_connector(app)

    def test_foreign_realm_is_refused_before_any_lookup(self, app, create_ca, monkeypatch):
        """The profile of the realm with a connector of another domain: never looked up there."""
        ca_data = create_ca(cn='Strong Mapping Foreign Realm CA')
        _configure_connector_row(app, base_dn='DC=other,DC=domain')

        def _fail_if_called(_config, sam):
            raise AssertionError('a foreign principal must not be looked up in this domain')

        monkeypatch.setattr(ad_lookup, 'lookup_object_sid', _fail_if_called)
        cert_pem, err = _issue_supplied_subject(app, ca_data['id'], KERBEROS_MACHINE_PRINCIPAL)
        assert cert_pem is None
        assert err == "The requester's realm is not served by the directory connector"
        assert not isinstance(err, wstep_service.ServerError)

    def test_principal_without_an_account_is_refused(self, app, create_ca, monkeypatch):
        ca_data = create_ca(cn='Strong Mapping No Account CA')
        _configure_connector_row(app)
        monkeypatch.setattr(ad_lookup, 'lookup_object_sid', lambda _config, sam: _REAL_SID)
        # A principal naming no account names no realm either: no profile serves it
        for principal in ('@HAGLAND.DOMAIN', 'WIN11$'):
            cert_pem, err = _issue_supplied_subject(app, ca_data['id'], principal)
            assert cert_pem is None, principal
            assert err == wstep_service.REALM_NOT_SERVED
            assert not isinstance(err, wstep_service.ServerError)

    def test_connector_without_base_dn_is_a_server_fault(self, app, create_ca, monkeypatch, caplog):
        ca_data = create_ca(cn='Strong Mapping No Base DN CA')
        monkeypatch.setattr(ad_lookup, 'lookup_object_sid', lambda _config, sam: _REAL_SID)
        for base_dn, cause in ((None, 'no base DN'), ('', 'no base DN'),
                               ('not a dn', 'no DC component'), ('OU=Machines', 'no DC component')):
            _configure_connector_row(app, base_dn=base_dn)
            caplog.clear()
            cert_pem, err = _issue_supplied_subject(app, ca_data['id'], KERBEROS_MACHINE_PRINCIPAL)
            assert cert_pem is None, base_dn
            assert isinstance(err, wstep_service.ServerError), base_dn
            assert err == 'Could not resolve requester identity for strong certificate mapping'
            assert cause in caplog.text, base_dn

    def test_disabled_connector_issues_its_realm_without_sid_and_never_a_foreign_one(
            self, app, create_ca, monkeypatch):
        ca_data = create_ca(cn='Strong Mapping Disabled Foreign CA')
        _configure_connector_row(app, enabled=False)
        monkeypatch.setattr(ad_lookup, 'lookup_object_sid',
                            lambda _config, sam: (_ for _ in ()).throw(AssertionError('connector is off')))
        cert_pem, err = _issue_supplied_subject(app, ca_data['id'], KERBEROS_MACHINE_PRINCIPAL)
        assert err is None, err
        assert _sid_extension_value(x509.load_pem_x509_certificate(cert_pem.encode())) is None
        cert_pem, err = _issue_supplied_subject(app, ca_data['id'], 'WIN11$@OTHER.DOMAIN')
        assert (cert_pem, err) == (None, wstep_service.REALM_NOT_SERVED)

    def test_same_realm_keeps_the_sid_and_its_lowercase_spelling_is_another_realm(
            self, app, create_ca, monkeypatch):
        ca_data = create_ca(cn='Strong Mapping Same Realm CA')
        _configure_connector_row(app)
        looked_up = []
        monkeypatch.setattr(ad_lookup, 'lookup_object_sid', lambda _config, sam: looked_up.append(sam) or _REAL_SID)
        cert_pem, err = _issue_supplied_subject(app, ca_data['id'], KERBEROS_MACHINE_PRINCIPAL)
        assert err is None, err
        assert looked_up == ['WIN11$']
        assert _sid_extension_value(x509.load_pem_x509_certificate(cert_pem.encode())) is not None
        # RFC 4120 §6.1: realm names are case sensitive
        cert_pem, err = _issue_supplied_subject(app, ca_data['id'], 'WIN11$@hagland.domain')
        assert cert_pem is None
        assert err == wstep_service.REALM_NOT_SERVED

    def test_two_accounts_of_the_requester_s_name_are_a_server_fault(self, app, create_ca, monkeypatch):
        """A Global Catalog answers for child domains too: an ambiguous account is never mapped."""
        ca_data = create_ca(cn='Strong Mapping Duplicate Account CA')
        _configure_connector_row(app)

        class _Entry:
            def __init__(self, dn):
                self.entry_dn = dn
                self.objectSid = type('A', (), {'raw_values': [b'\x01\x01\x00\x00\x00\x00\x00\x05\x12\x00\x00\x00']})()

            def __contains__(self, key):
                return key == 'objectSid'

        class _Conn:
            result = {'result': 0, 'description': 'success'}
            entries = [_Entry('CN=CHILDDC,CN=Computers,DC=hagland,DC=domain'),
                       _Entry('CN=CHILDDC,OU=Domain Controllers,DC=child,DC=hagland,DC=domain')]

            def search(self, *args, **kwargs):
                return True

            def unbind(self):
                pass

        monkeypatch.setattr(ad_lookup, '_connect', lambda config: _Conn())
        cert_pem, err = _issue_supplied_subject(app, ca_data['id'], 'CHILDDC$@HAGLAND.DOMAIN')
        assert cert_pem is None
        assert isinstance(err, wstep_service.ServerError)
        assert err == 'Could not resolve requester identity for strong certificate mapping'
