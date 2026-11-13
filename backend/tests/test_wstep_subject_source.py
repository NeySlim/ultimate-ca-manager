"""WSTEP builds the subject the way XCEP announces it (subjectNameFlags, MS-XCEP 3.1.4.1.3.1).

A machine template (0x18000000) and a "Build subject from Active Directory" template
(0x82000000) never take the subject or SAN of the request on the Kerberos binding; a
template announcing 0x00010001 keeps the request's, as do Windows CertEnroll requests."""
import json
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from lxml import etree

from models import CA, CATemplatePin, db
from models.certificate_template import CertificateTemplate
from services.ad_connector import lookup as ad_lookup
from services.wstep import wstep_service
from services.wstep.rst_parser import _unwrap_pkcs7_csr
from services.xcep import policy_builder
from tests.fixtures.templates import delete_templates
from utils.upn_san import build_upn_other_name, extract_upns_from_san_list
from tests.windows_profile_support import default_profile, default_realm
from tests.windows_profile_support import windows_profiles_restored  # noqa: F401

FIXTURES = Path(__file__).parent / 'fixtures'
MACHINE = 'WIN11$@EXAMPLE.TEST'
USER = 'alice@EXAMPLE.TEST'
SERVER_AUTH = ExtendedKeyUsageOID.SERVER_AUTH
CLIENT_AUTH = ExtendedKeyUsageOID.CLIENT_AUTH
EMAIL = ExtendedKeyUsageOID.EMAIL_PROTECTION


@pytest.fixture(autouse=True)
def _served_realm(app):
    with default_realm(app, 'EXAMPLE.TEST'):
        yield


@pytest.fixture
def subject_ca(app, create_ca):
    """A CA offering {name: (template_type, EKU names, ad_derived_subject, key_type)}."""
    made = []

    def _make(cn, templates):
        ca_data = create_ca(cn=cn)
        with app.app_context():
            for name, (ttype, ekus, ad_derived, key_type) in templates.items():
                t = CertificateTemplate(
                    name=f'{cn} {name}', template_type=ttype, key_type=key_type,
                    validity_days=30, digest='sha256', is_active=True, ad_derived_subject=ad_derived,
                    extensions_template=json.dumps({'extended_key_usage': ekus}))
                db.session.add(t)
                db.session.flush()
                db.session.add(CATemplatePin(ca_id=ca_data['id'], template_id=t.id))
                made.append(t.id)
            db.session.commit()
        return ca_data['id']
    yield _make
    with app.app_context():
        delete_templates(made)
        db.session.commit()


@pytest.fixture
def directory(monkeypatch):
    """AD answers for WIN11$ and alice; the connector's own state is not consulted."""
    found = {'dns': 'win11.example.test', 'user': {
        'dn_components': [('CN', 'Alice'), ('CN', 'Users'), ('DC', 'example'), ('DC', 'test')],
        'upn': 'alice@example.test'}}
    monkeypatch.setattr(ad_lookup, 'connector_account', lambda _config, principal: principal.split('@')[0])
    monkeypatch.setattr(ad_lookup, 'lookup_computer_dns_hostname', lambda _config, sam: found['dns'])
    monkeypatch.setattr(ad_lookup, 'lookup_user_ad_identity', lambda _config, sam: found['user'])
    monkeypatch.setattr(ad_lookup, 'lookup_object_sid', lambda _config, sam: 'S-1-5-21-1-2-3-1000')
    return found


MIXED = {
    'Web': ('web_server', ['serverAuth'], False, 'RSA-2048'),
    'User': ('usr_cert', ['clientAuth'], False, 'RSA-2048'),
    'Mail': ('usr_cert', ['emailProtection'], True, 'RSA-2048'),
}


def _csr(cn=None, sans=(), ekus=(), key=None):
    key = key or rsa.generate_private_key(public_exponent=65537, key_size=2048)
    attrs = [x509.NameAttribute(NameOID.COMMON_NAME, cn)] if cn else []
    builder = x509.CertificateSigningRequestBuilder().subject_name(x509.Name(attrs))
    if sans:
        builder = builder.add_extension(x509.SubjectAlternativeName(list(sans)), critical=False)
    if ekus:
        builder = builder.add_extension(x509.ExtendedKeyUsage(list(ekus)), critical=False)
    return builder.sign(key, hashes.SHA256())


def _issue(app, ca_id, csr, principal=None, **kwargs):
    der = csr if isinstance(csr, bytes) else csr.public_bytes(serialization.Encoding.DER)
    with app.app_context():
        pem, err = wstep_service.issue(db.session.get(CA, ca_id), der, 30,
                                       kerberos_principal=principal, profile=default_profile(), **kwargs)
    return (x509.load_pem_x509_certificate(pem.encode()) if pem else None), err


def _sans(cert):
    try:
        return list(cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value)
    except x509.ExtensionNotFound:
        return []


FORGED_SANS = (x509.DNSName('dc01.example.test'), x509.DNSName('www.bank.test'))


def test_a_machine_template_ignores_the_requested_subject_and_san(app, subject_ca, directory):
    ca_id = subject_ca('Subject source machine CA', MIXED)
    cert, err = _issue(app, ca_id, _csr('dc01.example.test', FORGED_SANS, [SERVER_AUTH]), MACHINE)
    assert err is None, err
    assert cert.subject.rfc4514_string() == 'CN=win11.example.test'
    assert _sans(cert) == [x509.DNSName('win11.example.test')]


def test_a_machine_template_refuses_a_user(app, subject_ca, directory):
    ca_id = subject_ca('Subject source machine user CA', MIXED)
    cert, err = _issue(app, ca_id, _csr('www.bank.test', ekus=[SERVER_AUTH]), USER)
    assert cert is None
    assert err == "Template 'Subject source machine user CA Web' is issued to computers, not users"


def test_a_directory_template_ignores_the_requested_subject_and_upn(app, subject_ca, directory):
    ca_id = subject_ca('Subject source directory CA', MIXED)
    csr = _csr('Administrator', [build_upn_other_name('administrator@example.test')], [EMAIL])
    cert, err = _issue(app, ca_id, csr, USER)
    assert err is None, err
    assert cert.subject.rfc4514_string() == 'CN=Alice,CN=Users,DC=example,DC=test'
    assert extract_upns_from_san_list(_sans(cert)) == ['alice@example.test']


def test_a_directory_template_refuses_a_computer(app, subject_ca, directory):
    ca_id = subject_ca('Subject source directory machine CA', MIXED)
    cert, err = _issue(app, ca_id, _csr('win11.example.test', ekus=[EMAIL]), MACHINE)
    assert cert is None
    assert err == "Template 'Subject source directory machine CA Mail' is issued to users, not computers"


def test_a_subject_the_directory_cannot_build_is_refused(app, subject_ca, directory):
    directory['dns'] = None
    ca_id = subject_ca('Subject source no dns CA', MIXED)
    cert, err = _issue(app, ca_id, _csr('dc01.example.test', FORGED_SANS, [SERVER_AUTH]), MACHINE)
    assert cert is None
    assert err == 'The certificate subject is built from Active Directory, which could not resolve the requester'
    assert not isinstance(err, wstep_service.ServerError)


@pytest.mark.parametrize('principal,naked', [(MACHINE, False), (MACHINE, True), (USER, False), (USER, True)])
def test_a_directory_that_cannot_answer_is_the_server_s_failure(app, subject_ca, directory, principal, naked):
    """Not found stays the request's refusal; no DC bound is a ServerError (env:Receiver)."""
    directory['dns'] = directory['user'] = ad_lookup.UNREACHABLE
    ca_id = subject_ca(f'Subject source unreachable CA {principal.split("@")[0].rstrip("$")} {naked}', MIXED)
    csr = _csr() if naked else _csr('dc01.example.test', FORGED_SANS, [SERVER_AUTH if principal == MACHINE
                                                                        else EMAIL])
    cert, err = _issue(app, ca_id, csr, principal)
    assert cert is None
    assert isinstance(err, wstep_service.ServerError)
    assert err == 'The directory that builds the certificate subject could not be reached'


def test_an_unresolved_principal_gets_no_requested_subject(app, subject_ca, directory, monkeypatch):
    """No connector leaves no identity to build from; a realm it does not serve is refused outright."""
    ca_id = subject_ca('Subject source unresolved CA', MIXED)
    monkeypatch.setattr(ad_lookup, 'connector_account', lambda _config, principal: None)
    cert, err = _issue(app, ca_id, _csr('dc01.example.test', ekus=[SERVER_AUTH]), MACHINE)
    assert cert is None
    assert err == 'The certificate subject is built from Active Directory, which could not resolve the requester'
    monkeypatch.setattr(ad_lookup, 'connector_account', lambda _config, principal: ad_lookup.FOREIGN_REALM)
    cert, err = _issue(app, ca_id, _csr('dc01.example.test', ekus=[SERVER_AUTH]), MACHINE)
    assert cert is None
    assert err == "The requester's realm is not served by the directory connector"


def test_a_request_matching_no_template_of_a_ca_that_builds_every_subject(app, subject_ca, directory):
    """No EKU, so no template: the CA announces no template the client may name itself."""
    ca_id = subject_ca('Subject source unmatched CA', {'Web': MIXED['Web']})
    cert, err = _issue(app, ca_id, _csr('dc01.example.test', FORGED_SANS), MACHINE)
    assert err is None, err
    assert cert.subject.rfc4514_string() == 'CN=win11.example.test'
    assert _sans(cert) == [x509.DNSName('win11.example.test')]


def test_a_template_announcing_a_supplied_subject_keeps_it(app, subject_ca, directory):
    ca_id = subject_ca('Subject source supplied CA', MIXED)
    for principal in (USER, MACHINE):
        cert, err = _issue(app, ca_id, _csr('custom.example.test', ekus=[CLIENT_AUTH]), principal)
        assert err is None, err
        assert cert.subject.rfc4514_string() == 'CN=custom.example.test'


def test_a_naked_machine_request_is_still_derived(app, subject_ca, directory):
    ca_id = subject_ca('Subject source naked CA', MIXED)
    cert, err = _issue(app, ca_id, _csr(ekus=[SERVER_AUTH]), MACHINE)
    assert err is None, err
    assert cert.subject.rfc4514_string() == 'CN=win11.example.test'
    assert _sans(cert) == [x509.DNSName('win11.example.test')]


def test_the_username_password_binding_keeps_the_requested_subject(app, subject_ca):
    """That binding has no identity to build from: its policy announces 0x00010001."""
    ca_id = subject_ca('Subject source password CA', MIXED)
    cert, err = _issue(app, ca_id, _csr('dc01.example.test', ekus=[SERVER_AUTH]))
    assert err is None, err
    assert cert.subject.rfc4514_string() == 'CN=dc01.example.test'


@pytest.mark.parametrize('principal', [None, USER])
def test_windows_certenroll_requests_are_unchanged(app, subject_ca, directory, principal):
    """The Server 2025 CertEnroll captures: P-256 key, clientAuth, CN set by the client."""
    ca_id = subject_ca(f'Subject source capture CA {principal}', {
        'User': ('usr_cert', ['clientAuth'], False, 'EC-P256')})
    csr_der, _part, outer = _unwrap_pkcs7_csr((FIXTURES / 'wstep_windows_ecdsa_p256.cmc.der').read_bytes())
    cert, err = _issue(app, ca_id, csr_der, principal, require_pop=False, outer_signed_data=outer)
    assert err is None, err
    assert cert.subject.rfc4514_string() == 'CN=rc-xcep-ec256-ce1'


def _announced_flags(ca, ad_identity):
    templates = CertificateTemplate.query.filter_by(is_active=True).all()
    root = etree.fromstring(policy_builder.build_get_policies_response(ca, templates, ad_identity=ad_identity))
    ns = {'x': policy_builder.XCEP_NS}
    return {p.find('x:attributes/x:commonName', ns).text: int(p.find('x:attributes/x:subjectNameFlags', ns).text)
            for p in root.iterfind('.//x:policy', ns)}


def test_each_policy_binding_announces_what_its_issuance_does(app, subject_ca):
    ca_id = subject_ca('Subject source flags CA', MIXED)
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        kerberos = _announced_flags(ca, ad_identity=True)
        password = _announced_flags(ca, ad_identity=False)
    name = 'Subject source flags CA'
    assert kerberos == {f'{name} Web': 0x18000000, f'{name} User': 0x00010001, f'{name} Mail': 0x82000000}
    assert password == {f'{name} Web': 0x00010001, f'{name} User': 0x00010001, f'{name} Mail': 0x00010001}


CODE_SIGNING = ExtendedKeyUsageOID.CODE_SIGNING
PINNED = {'Web': MIXED['Web'], 'User': MIXED['User']}


@pytest.mark.parametrize('ekus', [(), (CODE_SIGNING,)], ids=['no-eku', 'code-signing'])
def test_a_request_matching_no_template_never_keeps_its_subject(app, subject_ca, directory, ekus):
    """The CA offering a template with a supplied subject does not lend it to a request naming none."""
    ca_id = subject_ca(f'Subject source unmatched supplied CA {len(ekus)}', PINNED)
    csr = _csr('www.bank.test', [x509.DNSName('www.bank.test')], ekus)
    cert, err = _issue(app, ca_id, csr, MACHINE)
    assert err is None, err
    assert cert.subject.rfc4514_string() == 'CN=win11.example.test'
    assert _sans(cert) == [x509.DNSName('win11.example.test')]
    cert, err = _issue(app, ca_id, csr, USER)
    assert cert is None
    assert err == 'The request matches no certificate template whose subject it may supply'


def test_a_template_with_a_supplied_subject_issues_only_its_own_ekus(app, subject_ca, directory):
    ca_id = subject_ca('Subject source supplied ekus CA', PINNED)
    csr = _csr('www.bank.test', [x509.DNSName('www.bank.test')], [SERVER_AUTH, CLIENT_AUTH])
    cert, err = _issue(app, ca_id, csr, USER)
    assert err is None, err
    assert wstep_service._eku_oids(cert) == {CLIENT_AUTH.dotted_string}


def test_a_template_with_a_supplied_subject_and_no_eku_is_refused(app, subject_ca, directory):
    """Its default profile would be serverAuth for whatever name the request gives."""
    ca_id = subject_ca('Subject source no eku CA', {'Web': MIXED['Web'], 'Any': ('usr_cert', [], False, 'RSA-2048')})
    cert, err = _issue(app, ca_id, _csr('www.bank.test', [x509.DNSName('www.bank.test')]), USER)
    assert cert is None
    assert err == ("Template 'Subject source no eku CA Any' lets the request name its subject "
                   'but configures no Extended Key Usage')
    assert isinstance(err, wstep_service.ServerError)  # the template's configuration, not the request


def test_a_naked_request_under_a_template_without_eku_is_still_derived(app, subject_ca, directory):
    """The directory names it, so the template's missing EKUs cannot lend it a chosen name."""
    ca_id = subject_ca('Subject source naked no eku CA', {'Any': ('usr_cert', [], False, 'RSA-2048')})
    cert, err = _issue(app, ca_id, _csr(), MACHINE)
    assert err is None, err
    assert cert.subject.rfc4514_string() == 'CN=win11.example.test'


SMARTCARD_LOGON = x509.ObjectIdentifier('1.3.6.1.4.1.311.20.2.2')


@pytest.mark.parametrize('principal', [USER, MACHINE])
def test_a_smartcard_logon_only_template_adds_no_default_profile(app, subject_ca, directory, principal):
    """Smartcard Logon is kept out of the replacing EKUs, so the default profile must not fill in."""
    ca_id = subject_ca(f'Subject source smartcard CA {principal[:3]}', {
        'Smartcard': ('usr_cert', ['msSmartcardLogin'], False, 'RSA-2048')})
    csr = _csr('www.bank.test', [x509.DNSName('www.bank.test')], [SMARTCARD_LOGON])
    cert, err = _issue(app, ca_id, csr, principal)
    assert err is None, err
    assert wstep_service._eku_oids(cert) == {SMARTCARD_LOGON.dotted_string}
