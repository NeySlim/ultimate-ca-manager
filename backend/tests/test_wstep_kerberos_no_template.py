"""A Kerberos request that matches no template the profile offers is refused, as AD CS refuses a
request without template (CERTSRV_E_NO_CERT_TYPE), instead of being issued as a server certificate
(SQLite, and PostgreSQL with UCM_TEST_APP_PG_URL). A naked request that names its template, the
GPO autoenrollment shape, is still issued; the UsernamePassword binding is not changed."""
import json

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from models import CA, CATemplatePin, Certificate, CertificateTemplate, db
from services.ad_connector import lookup as ad_lookup
from services.ca_service import CAService
from services.wstep import CES_KERBEROS_PATH, wstep_service
from services.xcep.policy_builder import _policy_oid_for_template
from tests.fixtures.templates import delete_templates
from tests.test_wstep_kerberos_issue import _build_rst, _issued_cert_from_rstr
from tests.test_wstep_renew_tls import _cmc_renewal, _rst
from tests.test_windows_profile_routing import (NEGOTIATE, _as, _audits, _fault, _profile, _top_audit,  # noqa: F401
                                                world)

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')
MACHINE = 'hosta$@C04A.TEST'
USER = 'usera@C04A.TEST'
NO_TEMPLATE = getattr(wstep_service, 'NO_TEMPLATE', 'rule missing')
SERVER_AUTH = ExtendedKeyUsageOID.SERVER_AUTH
CLIENT_AUTH = ExtendedKeyUsageOID.CLIENT_AUTH


@pytest.fixture
def realm_a(app, world, monkeypatch):
    """Profile A offers a user template whose subject comes from AD and a machine template;
    the directory answers for hosta$ and usera, so that only the rule stops an issuance."""
    with app.app_context():
        user = db.session.get(CertificateTemplate, world['templates']['A User'])
        user.ad_derived_subject = True
        machine = CertificateTemplate(name='C15 A Machine', template_type='vpn_client', key_type='RSA-2048',
                                      validity_days=30, digest='sha256', is_active=True,
                                      extensions_template=json.dumps({'extended_key_usage': ['clientAuth']}))
        db.session.add(machine)
        db.session.flush()
        db.session.add(CATemplatePin(ca_id=world['cas']['A']['id'], template_id=machine.id))
        db.session.commit()
        ca = db.session.get(CA, world['cas']['A']['id'])
        oids = {'user': _policy_oid_for_template(ca, user), 'machine': _policy_oid_for_template(ca, machine)}
        machine_id = machine.id
    monkeypatch.setattr(ad_lookup, 'lookup_computer_dns_hostname', lambda config, sam: 'hosta.c04a.test')
    monkeypatch.setattr(ad_lookup, 'lookup_user_ad_identity', lambda config, sam: {
        'dn_components': [('CN', 'User A'), ('CN', 'Users'), ('DC', 'c04a'), ('DC', 'test')],
        'upn': 'usera@c04a.test', 'mail': None, 'sam_account_name': 'usera'})
    yield oids
    with app.app_context():
        CATemplatePin.query.filter_by(template_id=machine_id).delete()
        db.session.commit()
        delete_templates([machine_id])
        db.session.commit()


def _csr(cn=None, ekus=(), template_oid=None, key=None):
    key = key or rsa.generate_private_key(public_exponent=65537, key_size=2048)
    attrs = [x509.NameAttribute(NameOID.COMMON_NAME, cn)] if cn else []
    builder = x509.CertificateSigningRequestBuilder().subject_name(x509.Name(attrs))
    if ekus:
        builder = builder.add_extension(x509.ExtendedKeyUsage(list(ekus)), critical=False)
    if template_oid:
        builder = builder.add_extension(
            x509.MSCertificateTemplate(x509.ObjectIdentifier(template_oid), 100, 0), critical=False)
    return builder.sign(key, hashes.SHA256())


def _post(client, world, principal, csr):
    _as(world, principal)
    return client.post(CES_KERBEROS_PATH, data=_build_rst(csr), headers=NEGOTIATE)


def _issued_count(app, world):
    with app.app_context():
        return Certificate.query.filter_by(caref=world['cas']['A']['refid']).count()


@pytest.mark.parametrize('principal', [MACHINE, USER], ids=['machine', 'user'])
@pytest.mark.parametrize('cn', [None, 'c15-asked'], ids=['naked', 'named-subject'])
def test_a_kerberos_request_matching_no_template_is_refused_and_audited(app, client, world, realm_a,
                                                                        principal, cn):
    floor, before = _top_audit(app), _issued_count(app, world)
    assert _fault(_post(client, world, principal, _csr(cn))) == (400, 's:Sender', NO_TEMPLATE)
    rows = _audits(app, floor)
    assert [(action, user, name, ok) for action, user, name, _d, ok in rows] == [
        ('windows_enrollment.refused', principal, 'c04-a', False)]
    assert NO_TEMPLATE in rows[0][3] and 'realm C04A.TEST, profile c04-a' in rows[0][3]
    assert _issued_count(app, world) == before


@pytest.mark.parametrize('principal, kind, subject', [
    (MACHINE, 'machine', 'CN=hosta.c04a.test'),
    (USER, 'user', 'CN=User A,CN=Users,DC=c04a,DC=test'),
], ids=['machine', 'user'])
def test_a_naked_request_naming_its_template_is_issued_as_before(app, client, world, realm_a,
                                                                 principal, kind, subject):
    """GPO autoenrollment: no subject, the template named by the extension XCEP announces."""
    r = _post(client, world, principal, _csr(template_oid=realm_a[kind]))
    assert r.status_code == 200, r.data
    cert = _issued_cert_from_rstr(r.data)
    assert cert.subject.rfc4514_string() == subject
    template = cert.extensions.get_extension_for_class(x509.MSCertificateTemplate).value
    assert template.template_id.dotted_string == realm_a[kind]


@pytest.mark.parametrize('principal, kind', [(MACHINE, 'machine'), (USER, 'user')], ids=['machine', 'user'])
def test_a_request_matched_by_its_extended_key_usage_is_issued_as_before(app, client, world, realm_a,
                                                                         principal, kind):
    """The Server 2025 CertEnroll captures name no template and carry the template's EKU."""
    r = _post(client, world, principal, _csr(ekus=[CLIENT_AUTH]))
    assert r.status_code == 200, r.data
    cert = _issued_cert_from_rstr(r.data)
    template = cert.extensions.get_extension_for_class(x509.MSCertificateTemplate).value
    assert template.template_id.dotted_string == realm_a[kind]


def test_the_username_password_binding_still_issues_a_request_matching_no_template(app, world, realm_a):
    """Unchanged here, a decision of its own: no template, the server type, the requested subject."""
    with app.app_context():
        pem, err = wstep_service.issue(db.session.get(CA, world['cas']['A']['id']),
                                       _csr('c15-password.example.test').public_bytes(serialization.Encoding.DER),
                                       30, profile=_profile('c04-a'))
    assert err is None, err
    cert = x509.load_pem_x509_certificate(pem.encode())
    assert cert.subject.rfc4514_string() == 'CN=c15-password.example.test'
    assert list(cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value) == [SERVER_AUTH]


def _template_less_certificate(app, world, key, ekus):
    """A certificate of CA A issued without template extension, as before 3.0."""
    with app.app_context():
        pem, _serial = CAService.sign_csr_from_crypto(
            ca=db.session.get(CA, world['cas']['A']['id']), csr=_csr('c15-old', ekus=ekus, key=key),
            validity_days=30, source='test')
    cert = x509.load_pem_x509_certificate(pem.encode())
    with pytest.raises(x509.ExtensionNotFound):
        cert.extensions.get_extension_for_class(x509.MSCertificateTemplate)
    return cert


def test_a_kerberos_renewal_of_a_certificate_without_template_is_served(app, client, world, realm_a):
    """A certificate issued before 3.0 without template renews as it did: Windows copies its
    extensions (here serverAuth, which no template of the profile issues) into the request."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    old = _template_less_certificate(app, world, key, [SERVER_AUTH])
    new_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = _csr('c15-old', ekus=[SERVER_AUTH], key=new_key)
    _as(world, MACHINE)
    r = client.post(CES_KERBEROS_PATH, data=_rst(_cmc_renewal(csr, [(new_key, None), (key, old)])),
                    headers=NEGOTIATE)
    assert r.status_code == 200, r.data
    # The same request, signed by the new key alone, is an initial enrollment: refused
    _as(world, MACHINE)
    r = client.post(CES_KERBEROS_PATH, data=_rst(_cmc_renewal(csr, [(new_key, None)])), headers=NEGOTIATE)
    assert _fault(r) == (400, 's:Sender', NO_TEMPLATE)


def test_a_kerberos_renewal_of_a_certificate_with_template_follows_the_rule(app, client, world, realm_a):
    """Signed by a certificate that names its template, a request matching none is refused."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    r = _post(client, world, MACHINE, _csr(template_oid=realm_a['machine'], key=key))
    old = _issued_cert_from_rstr(r.data)
    new_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    _as(world, MACHINE)
    r = client.post(CES_KERBEROS_PATH, data=_rst(_cmc_renewal(_csr(key=new_key), [(new_key, None), (key, old)])),
                    headers=NEGOTIATE)
    assert _fault(r) == (400, 's:Sender', NO_TEMPLATE)
