"""A Kerberos request that matches no template the profile offers is refused, as AD CS refuses a
request without template (CERTSRV_E_NO_CERT_TYPE), instead of being issued as a server certificate
(SQLite, and PostgreSQL with UCM_TEST_APP_PG_URL). A naked request that names its template, the
GPO autoenrollment shape, is still issued; the UsernamePassword binding is not changed."""
import json
from datetime import datetime, timedelta

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
from tests.test_windows_profile_routing import (NEGOTIATE, SID, _as, _audits, _fault, _profile,  # noqa: F401
                                                _top_audit, world)

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


def _template_less_certificate(app, world, key, ekus=(SERVER_AUTH,), *, cn='hosta.c04a.test', sid=SID,
                               source='wstep', profile='c04-a', revoked=False, expired=False):
    """A certificate of CA A issued without template extension, as before 3.0: by default the
    Windows certificate of hosta$ (profile c04-a, its SID); each keyword departs from that."""
    with app.app_context():
        pem, _serial = CAService.sign_csr_from_crypto(
            ca=db.session.get(CA, world['cas']['A']['id']), csr=_csr(cn, ekus=ekus, key=key),
            validity_days=30, source=source, requester_sid=sid,
            windows_profile_id=_profile(profile).id if profile else None)
        cert = x509.load_pem_x509_certificate(pem.encode())
        row = Certificate.query.filter_by(serial_number=str(cert.serial_number)).one()
        row.revoked = revoked
        if expired:
            row.valid_to = datetime.utcnow() - timedelta(days=1)
        db.session.commit()
    with pytest.raises(x509.ExtensionNotFound):
        cert.extensions.get_extension_for_class(x509.MSCertificateTemplate)
    return cert


def _renew(client, world, principal, old, key, new_key=None, csr=None):
    """A Kerberos request signed by the new key and by *old*'s key, as Windows renews."""
    new_key = new_key or rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = csr or _csr('c15-old', ekus=[SERVER_AUTH], key=new_key)
    _as(world, principal)
    signers = [(new_key, None), (key, old)] if old is not None else [(new_key, None)]
    return client.post(CES_KERBEROS_PATH, data=_rst(_cmc_renewal(csr, signers)), headers=NEGOTIATE)


@pytest.mark.parametrize('principal, cn, sid', [
    (MACHINE, 'hosta.c04a.test', SID),
    (MACHINE, 'hosta.c04a.test', None),
    (USER, 'User A', SID),
], ids=['machine-sid', 'machine-dns-hostname', 'user-sid'])
def test_a_kerberos_renewal_of_its_own_windows_certificate_without_template_is_served(
        app, client, world, realm_a, principal, cn, sid):
    """A certificate issued before 3.0 without template renews as it did: Windows copies its
    extensions (here serverAuth, which no template of the profile issues) into the request."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    old = _template_less_certificate(app, world, key, cn=cn, sid=sid)
    floor = _top_audit(app)
    r = _renew(client, world, principal, old, key)
    assert r.status_code == 200, r.data
    (action, _u, _n, details, ok), = _audits(app, floor)
    assert action == 'certificate.renewed' and ok and f'old serial {old.serial_number}' in details
    # The same request, signed by the new key alone, is an initial enrollment: refused
    assert _fault(_renew(client, world, principal, None, None)) == (400, 's:Sender', NO_TEMPLATE)


def test_a_kerberos_renewal_of_a_user_certificate_without_sid_matches_its_directory_subject(
        app, client, world, realm_a):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with app.app_context():
        pem, _s = CAService.sign_csr_from_crypto(
            ca=db.session.get(CA, world['cas']['A']['id']), csr=_csr('ignored', ekus=[SERVER_AUTH], key=key),
            validity_days=30, source='wstep', windows_profile_id=_profile('c04-a').id,
            override_subject=x509.Name.from_rfc4514_string('CN=user a,CN=Users,DC=C04A,DC=test'))
    assert _renew(client, world, USER, x509.load_pem_x509_certificate(pem.encode()), key).status_code == 200
    other = _template_less_certificate(app, world, key, cn='User B', sid=None)
    assert _fault(_renew(client, world, USER, other, key)) == (400, 's:Sender', NO_TEMPLATE)


@pytest.mark.parametrize('principal', [MACHINE, USER], ids=['machine', 'user'])
@pytest.mark.parametrize('kind', ['acme-of-another-revoked', 'windows-of-another-sid',
                                  'windows-of-another-host', 'own-revoked', 'own-expired',
                                  'own-not-windows', 'own-of-another-profile'])
def test_a_kerberos_renewal_of_any_other_certificate_without_template_is_refused(
        app, client, world, realm_a, principal, kind):
    """Only the requester's own valid certificate of the Windows enrollment is exempted; the
    audit never names another certificate as renewed."""
    own_cn = 'hosta.c04a.test' if principal == MACHINE else 'User A'
    old_kwargs = {
        'acme-of-another-revoked': dict(cn='victim.example.test', sid=None, source='acme', profile=None,
                                        revoked=True),
        'windows-of-another-sid': dict(cn=own_cn, sid='S-1-5-21-1-2-3-9999'),
        'windows-of-another-host': dict(cn='hostb.c04a.test' if principal == MACHINE else 'User B', sid=None),
        'own-revoked': dict(cn=own_cn, revoked=True),
        'own-expired': dict(cn=own_cn, expired=True),
        'own-not-windows': dict(cn=own_cn, source='acme', profile=None),
        'own-of-another-profile': dict(cn=own_cn, profile='c04-b'),
    }[kind]
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    old = _template_less_certificate(app, world, key, **old_kwargs)
    floor, before = _top_audit(app), _issued_count(app, world)
    assert _fault(_renew(client, world, principal, old, key)) == (400, 's:Sender', NO_TEMPLATE)
    assert [a[0] for a in _audits(app, floor)] == ['windows_enrollment.refused']
    assert _issued_count(app, world) == before


def test_a_request_signed_by_the_certificate_of_another_is_audited_as_an_enrollment(app, client, world, realm_a):
    """A request naming its template, signed by a key that holds another's revoked certificate,
    is issued as an enrollment: the audit does not call that certificate renewed."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    old = _template_less_certificate(app, world, key, cn='victim.example.test', sid=None, source='acme',
                                     profile=None, revoked=True)
    new_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    floor = _top_audit(app)
    r = _renew(client, world, MACHINE, old, key, new_key, _csr(template_oid=realm_a['machine'], key=new_key))
    assert r.status_code == 200, r.data
    (action, _u, _n, details, _ok), = _audits(app, floor)
    assert action == 'certificate.issued' and str(old.serial_number) not in details


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
