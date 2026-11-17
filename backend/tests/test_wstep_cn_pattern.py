"""Common name pattern of a template on WSTEP issuance and renewal (SQLite, and PostgreSQL with
UCM_TEST_APP_PG_URL): only the CN changes, the SAN and the SID extension stay the directory's."""
import json

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from lxml import etree

from models import CA, CATemplatePin, db
from models.certificate_template import CertificateTemplate
from services.ad_connector import lookup as ad_lookup
from services.trust_store.csr_operations_mixin import ad_security_extension_sid
from services.wstep import cn_pattern, wstep_service
from services.xcep import policy_builder
from tests.ad_connector_support import add_connector
from tests.fixtures.templates import delete_templates
from tests.windows_profile_support import connectors_kept, default_profile, default_realm
from utils.upn_san import build_upn_other_name

MACHINE = 'WIN11$@EXAMPLE.TEST'
USER = 'alice@EXAMPLE.TEST'
SID = 'S-1-5-21-1-2-3-1000'
SERVER_AUTH = ExtendedKeyUsageOID.SERVER_AUTH
EMAIL = ExtendedKeyUsageOID.EMAIL_PROTECTION
USER_DN = [('CN', 'Alice Martin'), ('OU', 'Staff'), ('DC', 'example'), ('DC', 'test')]
HOST_DN = [('CN', 'WIN11'), ('OU', 'Laptops'), ('DC', 'example'), ('DC', 'test')]
pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')


@pytest.fixture(autouse=True)
def _served_realm(app):
    with default_realm(app, 'EXAMPLE.TEST'):
        yield


@pytest.fixture
def directory(monkeypatch):
    """What AD answers for WIN11$ and alice, in the shape of the lookups."""
    found = {
        'computer': {'dns_hostname': 'win11.example.test', 'sam_account_name': 'WIN11$', 'dn_components': HOST_DN},
        'user': {'dn_components': USER_DN, 'upn': 'alice@example.test', 'mail': 'alice@example.test',
                 'sam_account_name': 'alice', 'display_name': 'Alice Martin', 'given_name': 'Alice',
                 'surname': 'Martin'},
        'asked': [],
    }
    monkeypatch.setattr(ad_lookup, 'connector_account', lambda _config, principal: principal.split('@')[0])
    monkeypatch.setattr(ad_lookup, 'lookup_computer_dns_hostname',
                        lambda _config, sam: found['computer'] and found['computer']['dns_hostname'])
    monkeypatch.setattr(ad_lookup, 'lookup_computer_identity',
                        lambda _config, sam: found['asked'].append('computer') or found['computer'])
    monkeypatch.setattr(ad_lookup, 'lookup_user_ad_identity',
                        lambda _config, sam: found['asked'].append('user') or found['user'])
    monkeypatch.setattr(ad_lookup, 'lookup_object_sid', lambda _config, sam: SID)
    return found


@pytest.fixture
def pattern_ca(app, create_ca):
    """A CA offering a computer template (serverAuth) and a directory-built user template
    (emailProtection); returns (ca_id, {'machine': id, 'user': id})."""
    made = []

    def _make(cn, machine=None, user=None, keep_path=False):
        ca_data = create_ca(cn=cn)
        ids = {}
        with app.app_context():
            for kind, ttype, eku, pattern in (('machine', 'web_server', 'serverAuth', machine),
                                              ('user', 'usr_cert', 'emailProtection', user)):
                t = CertificateTemplate(
                    name=f'{cn} {kind}', template_type=ttype, key_type='RSA-2048', validity_days=30,
                    digest='sha256', is_active=True, ad_derived_subject=kind == 'user',
                    subject_cn_pattern=pattern, subject_cn_keep_path=keep_path,
                    extensions_template=json.dumps({'extended_key_usage': [eku]}))
                db.session.add(t)
                db.session.flush()
                db.session.add(CATemplatePin(ca_id=ca_data['id'], template_id=t.id))
                made.append(t.id)
                ids[kind] = t.id
            db.session.commit()
        return ca_data['id'], ids
    yield _make
    with app.app_context():
        delete_templates(made)
        db.session.commit()


def _csr(cn=None, sans=(), ekus=(), key=None):
    key = key or rsa.generate_private_key(public_exponent=65537, key_size=2048)
    attrs = [x509.NameAttribute(NameOID.COMMON_NAME, cn)] if cn else []
    builder = x509.CertificateSigningRequestBuilder().subject_name(x509.Name(attrs))
    if sans:
        builder = builder.add_extension(x509.SubjectAlternativeName(list(sans)), critical=False)
    if ekus:
        builder = builder.add_extension(x509.ExtendedKeyUsage(list(ekus)), critical=False)
    return builder.sign(key, hashes.SHA256())


def _issue(app, ca_id, csr, principal):
    with app.app_context():
        pem, err = wstep_service.issue(db.session.get(CA, ca_id), csr.public_bytes(serialization.Encoding.DER), 30,
                                       kerberos_principal=principal, profile=default_profile())
    return (x509.load_pem_x509_certificate(pem.encode()) if pem else None), err


def _sans(cert):
    try:
        return list(cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value)
    except x509.ExtensionNotFound:
        return []


USER_SANS = [build_upn_other_name('alice@example.test'), x509.RFC822Name('alice@example.test')]


@pytest.mark.parametrize('with_san', [True, False])
def test_an_empty_pattern_keeps_today_s_subjects(app, pattern_ca, directory, with_san):
    ca_id, _ids = pattern_ca(f'CN pattern none CA {with_san}')
    sans = [x509.DNSName('forged.example.test')] if with_san else []
    cert, err = _issue(app, ca_id, _csr('forged.example.test', sans, [SERVER_AUTH]), MACHINE)
    assert err is None, err
    assert cert.subject.rfc4514_string() == 'CN=win11.example.test'
    assert _sans(cert) == [x509.DNSName('win11.example.test')]
    cert, err = _issue(app, ca_id, _csr('Administrator', ekus=[EMAIL]), USER)
    assert err is None, err
    assert cert.subject.rfc4514_string() == ('1.2.840.113549.1.9.1=alice@example.test,CN=Alice Martin,OU=Staff,'
                                             'DC=example,DC=test')
    assert _sans(cert) == USER_SANS


@pytest.mark.parametrize('with_san', [True, False])
def test_a_machine_pattern_changes_the_cn_only(app, pattern_ca, directory, with_san):
    """``{hostname}-WiFi`` is not a DNS name: the SAN stays the dNSHostName, the SID unchanged."""
    ca_id, _ids = pattern_ca(f'CN pattern machine CA {with_san}', machine='{hostname}-WiFi')
    sans = [x509.DNSName('forged.example.test')] if with_san else []
    cert, err = _issue(app, ca_id, _csr('forged.example.test', sans, [SERVER_AUTH]), MACHINE)
    assert err is None, err
    assert cert.subject.rfc4514_string() == 'CN=WIN11-WiFi'
    assert _sans(cert) == [x509.DNSName('win11.example.test')]
    assert ad_security_extension_sid(cert) == SID


def test_a_machine_pattern_keeping_the_directory_path(app, pattern_ca, directory):
    ca_id, _ids = pattern_ca('CN pattern machine path CA', machine='{fqdn} ({domain}, {realm})', keep_path=True)
    cert, err = _issue(app, ca_id, _csr(ekus=[SERVER_AUTH]), MACHINE)
    assert err is None, err
    assert cert.subject.rfc4514_string() == (
        r'CN=win11.example.test (example.test\, EXAMPLE.TEST),OU=Laptops,DC=example,DC=test')
    assert _sans(cert) == [x509.DNSName('win11.example.test')]


@pytest.mark.parametrize('pattern,keep_path,subject', [
    ('{username}', False, 'CN=alice'),
    ('{displayName}', False, 'CN=Alice Martin'),
    ('{username}', True, '1.2.840.113549.1.9.1=alice@example.test,CN=alice,OU=Staff,DC=example,DC=test'),
    ('{displayName}', True, '1.2.840.113549.1.9.1=alice@example.test,CN=Alice Martin,OU=Staff,DC=example,DC=test'),
    ('{givenName}.{surname} {{{upn}}}', False, 'CN=Alice.Martin {alice@example.test}'),
])
def test_a_user_pattern_with_and_without_the_directory_path(app, pattern_ca, directory, pattern, keep_path,
                                                             subject):
    ca_id, _ids = pattern_ca(f'CN pattern user CA {len(pattern)} {keep_path}', user=pattern, keep_path=keep_path)
    cert, err = _issue(app, ca_id, _csr('Administrator', [build_upn_other_name('root@example.test')], [EMAIL]),
                       USER)
    assert err is None, err
    assert cert.subject.rfc4514_string() == subject
    assert _sans(cert) == USER_SANS
    assert ad_security_extension_sid(cert) == SID


def test_pinned_fields_still_apply_to_a_patterned_subject(app, pattern_ca, directory):
    ca_id, ids = pattern_ca('CN pattern pinned CA', user='{username}')
    with app.app_context():
        db.session.get(CertificateTemplate, ids['user']).pinned_subject_fields = json.dumps({'O': 'Example Org'})
        db.session.commit()
    cert, err = _issue(app, ca_id, _csr(ekus=[EMAIL]), USER)
    assert err is None, err
    assert cert.subject.rfc4514_string() == 'CN=alice,O=Example Org'


def test_a_hostile_attribute_is_one_cn_value(app, pattern_ca, directory):
    """A comma, '=', '+' or 'CN=' in the directory's value adds no RDN."""
    directory['user']['display_name'] = 'Doe, John+OU=Admins,CN=root'
    ca_id, _ids = pattern_ca('CN pattern hostile CA', user='{displayName}')
    cert, err = _issue(app, ca_id, _csr(ekus=[EMAIL]), USER)
    assert err is None, err
    assert [(a.oid, a.value) for a in cert.subject] == [(NameOID.COMMON_NAME, 'Doe, John+OU=Admins,CN=root')]
    assert len(cert.subject.rdns) == 1


REFUSALS = [
    ('{displayName}', 'display_name', None, '{displayName} has no value in the directory for the requester'),
    ('{displayName}', 'display_name', '   ', '{displayName} has no value in the directory for the requester'),
    ('{givenName}', 'given_name', 'A' * 65, 'the result is longer than 64 characters'),
    ('{surname}-x', 'surname', 'Mar\x07tin', 'the result contains a control character'),
]


@pytest.mark.parametrize('pattern,attr,value,why', REFUSALS, ids=['absent', 'blank', 'too-long', 'control'])
def test_a_pattern_the_directory_cannot_fill_is_the_requester_s_refusal(app, pattern_ca, directory, pattern,
                                                                         attr, value, why):
    directory['user'][attr] = value
    ca_id, _ids = pattern_ca(f'CN pattern refused CA {attr} {len(value or "")}', user=pattern)
    cert, err = _issue(app, ca_id, _csr(ekus=[EMAIL]), USER)
    assert cert is None
    assert err == f"Template 'CN pattern refused CA {attr} {len(value or '')} user' cannot build its common name: {why}"
    assert not isinstance(err, wstep_service.ServerError)


def test_sixty_four_characters_are_issued_whole(app, pattern_ca, directory):
    directory['user']['given_name'] = 'A' * 64
    ca_id, _ids = pattern_ca('CN pattern 64 CA', user='{givenName}')
    cert, err = _issue(app, ca_id, _csr(ekus=[EMAIL]), USER)
    assert err is None, err
    assert cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == 'A' * 64


def test_an_unreachable_directory_stays_the_server_s_failure(app, pattern_ca, directory):
    directory['computer'] = ad_lookup.UNREACHABLE
    directory['user'] = ad_lookup.UNREACHABLE
    ca_id, _ids = pattern_ca('CN pattern unreachable CA', machine='{hostname}', user='{username}')
    for csr, principal in ((_csr(ekus=[SERVER_AUTH]), MACHINE), (_csr(ekus=[EMAIL]), USER)):
        cert, err = _issue(app, ca_id, csr, principal)
        assert cert is None
        assert isinstance(err, wstep_service.ServerError)


def _announced_flags(ca):
    templates = CertificateTemplate.query.filter_by(is_active=True).all()
    root = etree.fromstring(policy_builder.build_get_policies_response(ca, templates, ad_identity=True))
    ns = {'x': policy_builder.XCEP_NS}
    return {p.find('x:attributes/x:commonName', ns).text: int(p.find('x:attributes/x:subjectNameFlags', ns).text)
            for p in root.iterfind('.//x:policy', ns)}


def test_xcep_announces_no_subject_flag_a_pattern_contradicts(app, pattern_ca):
    """MS-WCCE 3.2.2.6.2.1.4.5.9: DNS_AS_CN and DIRECTORY_PATH would name another subject; the
    SAN flags stay, and no ENROLLEE_SUPPLIES_SUBJECT, so the CA still builds the subject."""
    plain_id, _ = pattern_ca('CN pattern flags plain CA')
    patterned_id, _ = pattern_ca('CN pattern flags CA', machine='{hostname}-WiFi', user='{username}')
    with app.app_context():
        plain = _announced_flags(db.session.get(CA, plain_id))
        patterned = _announced_flags(db.session.get(CA, patterned_id))
    assert plain == {'CN pattern flags plain CA machine': 0x18000000, 'CN pattern flags plain CA user': 0x82000000}
    assert patterned == {'CN pattern flags CA machine': 0x08000000, 'CN pattern flags CA user': 0x02000000}


# Renewal on the Certificate binding: the SID names the account, the pattern in force the CN

def _renew(app, ca_id, signing_cert, key):
    csr = (x509.CertificateSigningRequestBuilder().subject_name(signing_cert.subject)
           .add_extension(signing_cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value,
                          critical=False)
           .sign(key, hashes.SHA256()))
    with app.app_context():
        pem, err = wstep_service.renew(db.session.get(CA, ca_id), signing_cert,
                                       csr.public_bytes(serialization.Encoding.DER), 30, profile=default_profile())
    return (x509.load_pem_x509_certificate(pem.encode()) if pem else None), err


@pytest.fixture
def renewal_directory(app, directory, monkeypatch):
    """The default profile's connector finds the SID's account (alice, or WIN11$)."""
    import services.windows_profiles as profiles
    state = {'account': 'alice'}
    with connectors_kept(app):
        with app.app_context():
            connector = add_connector('cn-pattern', server='dc.example.test', base_dn='DC=example,DC=test',
                                      bind_dn='svc', enabled=True)
            connector_id = connector.id
        monkeypatch.setattr(profiles, 'profile_sid_connectors', lambda profile, sid: [_connector(connector_id)])
        monkeypatch.setattr(ad_lookup, 'lookup_account_by_sid',
                            lambda config, sid: directory['asked'].append('sid') or state['account'])
        yield state


def _connector(connector_id):
    from models import ADConnectorConfig
    return db.session.get(ADConnectorConfig, connector_id)


@pytest.mark.parametrize('kind', ['user', 'machine'])
def test_a_renewal_takes_the_pattern_in_force(app, pattern_ca, directory, renewal_directory, kind):
    ca_id, ids = pattern_ca(f'CN pattern renewal CA {kind}', machine='{hostname}-WiFi', user='{username}')
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    principal, eku = (USER, EMAIL) if kind == 'user' else (MACHINE, SERVER_AUTH)
    renewal_directory['account'] = principal.split('@')[0]
    cert, err = _issue(app, ca_id, _csr(ekus=[eku], key=key), principal)
    assert err is None, err
    first = cert.subject.rfc4514_string()
    with app.app_context():
        template = db.session.get(CertificateTemplate, ids[kind])
        template.subject_cn_pattern = '{hostname}-Corp' if kind == 'machine' else '{displayName}'
        db.session.commit()
    directory['asked'].clear()
    renewed, err = _renew(app, ca_id, cert, key)
    assert err is None, err
    assert first == ('CN=alice' if kind == 'user' else 'CN=WIN11-WiFi')
    assert renewed.subject.rfc4514_string() == ('CN=Alice Martin' if kind == 'user' else 'CN=WIN11-Corp')
    assert _sans(renewed) == _sans(cert)
    assert ad_security_extension_sid(renewed) == SID
    # Under a pattern the renewal asks for the account once more, by the name its SID gave
    assert directory['asked'] == ['sid', 'user' if kind == 'user' else 'computer']


def test_a_renewal_without_a_pattern_keeps_the_renewed_subject(app, pattern_ca, directory, renewal_directory):
    ca_id, ids = pattern_ca('CN pattern renewal cleared CA', user='{username}')
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cert, err = _issue(app, ca_id, _csr(ekus=[EMAIL], key=key), USER)
    assert err is None, err
    with app.app_context():
        db.session.get(CertificateTemplate, ids['user']).subject_cn_pattern = None
        db.session.commit()
    directory['asked'].clear()
    renewed, err = _renew(app, ca_id, cert, key)
    assert err is None, err
    assert renewed.subject.rfc4514_string() == 'CN=alice'
    assert directory['asked'] == ['sid']


def test_a_renewal_the_directory_cannot_fill_is_refused(app, pattern_ca, directory, renewal_directory):
    ca_id, ids = pattern_ca('CN pattern renewal refused CA', user='{username}')
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cert, err = _issue(app, ca_id, _csr(ekus=[EMAIL], key=key), USER)
    assert err is None, err
    with app.app_context():
        db.session.get(CertificateTemplate, ids['user']).subject_cn_pattern = '{displayName}'
        db.session.commit()
    directory['user']['display_name'] = None
    renewed, err = _renew(app, ca_id, cert, key)
    assert renewed is None
    assert err == ("Template 'CN pattern renewal refused CA user' cannot build its common name: "
                   '{displayName} has no value in the directory for the requester')


# The directory is asked no more often: the attributes join the searches already made

class _Attr:
    def __init__(self, value, raw=None):
        self.value, self.raw_values = value, raw or ([value] if value else [])


class _Entry:
    def __init__(self, dn, attrs):
        self.entry_dn, self._attrs = dn, attrs
        for key, value in attrs.items():
            setattr(self, key, _Attr(value, [value] if isinstance(value, bytes) else None))

    def __contains__(self, key):
        return key in self._attrs


class _Directory:
    """An LDAP connection answering by filter; ``searches`` lists the attributes each asked."""

    def __init__(self):
        self.searches = []
        self.entries, self.result = [], {'result': 0}

    def search(self, base_dn, search_filter, attributes=None):
        self.searches.append(tuple(attributes))
        if 'objectSid' in attributes:
            dn, attrs = 'CN=x,DC=example,DC=test', {'objectSid': ad_lookup._sid_string_to_bytes(SID)}
        elif 'dNSHostName' in attributes:
            dn, attrs = 'CN=WIN11,OU=Laptops,DC=example,DC=test', {
                'dNSHostName': 'win11.example.test', 'sAMAccountName': 'WIN11$'}
        else:
            dn, attrs = 'CN=Alice Martin,OU=Staff,DC=example,DC=test', {
                'userPrincipalName': 'alice@example.test', 'mail': 'alice@example.test',
                'sAMAccountName': 'alice', 'displayName': 'Alice Martin', 'givenName': 'Alice', 'sn': 'Martin'}
        # Only what the search asked for comes back, as from a directory
        self.entries = [_Entry(dn, {k: v for k, v in attrs.items() if k in attributes})]
        return True

    def unbind(self):
        pass


@pytest.fixture
def ldap(app, monkeypatch):
    conn = _Directory()
    monkeypatch.setattr(ad_lookup, '_connect', lambda config: conn)
    with connectors_kept(app):
        with app.app_context():
            add_connector('cn-pattern-ldap', server='dc.example.test', base_dn='DC=example,DC=test',
                          bind_dn='svc', enabled=True, link=True)
        yield conn


@pytest.mark.parametrize('principal,eku', [(MACHINE, SERVER_AUTH), (USER, EMAIL)], ids=['machine', 'user'])
def test_a_pattern_adds_no_directory_search(app, pattern_ca, ldap, principal, eku):
    plain_id, _ = pattern_ca(f'CN pattern ldap plain CA {principal[:4]}')
    patterned_id, _ = pattern_ca(f'CN pattern ldap CA {principal[:4]}', machine='{hostname}-WiFi',
                                 user='{displayName}')
    counts = []
    for ca_id, expected in ((plain_id, None), (patterned_id, 'WIN11-WiFi' if principal == MACHINE
                                               else 'Alice Martin')):
        ldap.searches.clear()
        cert, err = _issue(app, ca_id, _csr(ekus=[eku]), principal)
        assert err is None, err
        if expected:
            assert cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == expected
        counts.append(len(ldap.searches))
    assert counts[0] == counts[1] == 2


# The pattern's own grammar

@pytest.mark.parametrize('pattern,kind,error', [
    ('{hostname}-WiFi', 'machine', None),
    ('{username}@{domain}', 'directory', None),
    ('{{literal}} {realm}', 'machine', None),
    ('{nickname}', 'directory', 'Unknown variable {nickname} in the common name pattern'),
    ('{hostname}', 'directory', 'Variable {hostname} is for computer templates; this is a user template'),
    ('{displayName}', 'machine', 'Variable {displayName} is for user templates; this is a computer template'),
    ('{username', 'directory', "A '{' in the common name pattern is never closed; write '{{' for a brace"),
    ('a}b', 'machine', "A lone '}' in the common name pattern must be written '}}'"),
    ('{}', 'machine', "A '{' in the common name pattern names no variable; write '{{' for a brace"),
])
def test_the_pattern_grammar(pattern, kind, error):
    assert cn_pattern.validation_error(pattern, kind) == error


def test_literal_braces_render_as_one():
    assert cn_pattern.render('{{{hostname}}}', {'hostname': 'WIN11'}) == ('{WIN11}', None)


def test_a_patterned_renewal_keeps_the_pinned_fields(app, pattern_ca, directory, renewal_directory):
    ca_id, ids = pattern_ca('CN pattern renewal pinned CA', user='{username}')
    with app.app_context():
        db.session.get(CertificateTemplate, ids['user']).pinned_subject_fields = json.dumps({'O': 'Example Org'})
        db.session.commit()
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cert, err = _issue(app, ca_id, _csr(ekus=[EMAIL], key=key), USER)
    assert err is None, err
    with app.app_context():
        db.session.get(CertificateTemplate, ids['user']).subject_cn_pattern = '{displayName}'
        db.session.commit()
    renewed, err = _renew(app, ca_id, cert, key)
    assert err is None, err
    assert (cert.subject.rfc4514_string(), renewed.subject.rfc4514_string()) == (
        'CN=alice,O=Example Org', 'CN=Alice Martin,O=Example Org')
