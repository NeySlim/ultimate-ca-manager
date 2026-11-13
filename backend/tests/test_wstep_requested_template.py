"""WSTEP issues under the template the request names (MS-WCCE 2.2.2.7.7, 3.2.2.6.2.1.4.1).

szOID_CERTIFICATE_TEMPLATE (1.3.6.1.4.1.311.21.7) names it by OID, szOID_ENROLL_CERTTYPE
(1.3.6.1.4.1.311.20.2) by name, as the MS-WSTEP 4.1.1.1 example does. A request naming
neither is matched by its EKUs: the Windows CertEnroll captures carry none."""
import pytest
from asn1crypto import core as asn1_core
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from models import CA, db
from models.certificate_template import CertificateTemplate
from services.xcep.policy_builder import _policy_oid_for_template
from tests.test_wstep_subject_source import CLIENT_AUTH, SERVER_AUTH, _issue, subject_ca  # noqa: F401
from tests.test_wstep_renew_tls import _eku_csr, _renew, _template_oid
from tests.windows_profile_support import default_profile
from tests.windows_profile_support import windows_profiles_restored  # noqa: F401

TWINS = {
    'User': ('usr_cert', ['clientAuth'], False, 'RSA-2048'),
    'VPNUser': ('usr_cert', ['clientAuth'], False, 'RSA-2048'),
    'Web': ('web_server', ['serverAuth'], False, 'RSA-2048'),
}
CERTTYPE_OID = x509.ObjectIdentifier('1.3.6.1.4.1.311.20.2')


@pytest.fixture(autouse=True)
def served_by_the_default_profile(app):
    """A ``wstep`` certificate recording no profile renews through the default one: made when
    missing, so that no test here leans on an earlier one for it."""
    with app.app_context():
        default_profile(create=True)
        db.session.commit()


def _named_csr(oid=None, name=None, ekus=(CLIENT_AUTH,), name_type=asn1_core.BMPString):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    builder = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'named.example.test')]))
    if ekus:
        builder = builder.add_extension(x509.ExtendedKeyUsage(list(ekus)), critical=False)
    if oid:
        builder = builder.add_extension(
            x509.MSCertificateTemplate(x509.ObjectIdentifier(oid), 100, 0), critical=False)
    if name:
        builder = builder.add_extension(
            x509.UnrecognizedExtension(CERTTYPE_OID, name_type(name).dump()), critical=False)
    return builder.sign(key, hashes.SHA256())


def _oid_of(app, ca_id, name):
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        return _policy_oid_for_template(ca, CertificateTemplate.query.filter_by(name=name).one())


def test_the_template_named_by_oid_is_issued(app, subject_ca):
    ca_id = subject_ca('Named oid CA', TWINS)
    oid = _oid_of(app, ca_id, 'Named oid CA VPNUser')
    cert, err = _issue(app, ca_id, _named_csr(oid=oid))
    assert err is None, err
    assert _template_oid(cert).dotted_string == oid


def test_the_template_named_by_name_is_issued(app, subject_ca):
    ca_id = subject_ca('Named name CA', TWINS)
    for name_type in (asn1_core.BMPString, asn1_core.UTF8String):
        cert, err = _issue(app, ca_id, _named_csr(name='named name ca vpnuser', name_type=name_type))
        assert err is None, err
        assert _template_oid(cert).dotted_string == _oid_of(app, ca_id, 'Named name CA VPNUser')


def test_a_template_this_ca_does_not_offer_is_refused(app, subject_ca):
    ca_id = subject_ca('Named unknown CA', TWINS)
    cert, err = _issue(app, ca_id, _named_csr(oid='1.2.3.4.5'))
    assert cert is None
    assert err == 'Certificate template 1.2.3.4.5 is not offered by this CA'
    cert, err = _issue(app, ca_id, _named_csr(name='DoesNotExist'))
    assert cert is None
    assert err == "Certificate template 'DoesNotExist' is not offered by this CA"


def test_an_inactive_template_is_refused(app, subject_ca):
    ca_id = subject_ca('Named inactive CA', TWINS)
    oid = _oid_of(app, ca_id, 'Named inactive CA VPNUser')
    with app.app_context():
        CertificateTemplate.query.filter_by(name='Named inactive CA VPNUser').update({'is_active': False})
        db.session.commit()
    cert, err = _issue(app, ca_id, _named_csr(oid=oid))
    assert cert is None
    assert err == f'Certificate template {oid} is not offered by this CA'


def test_two_names_for_two_templates_are_refused(app, subject_ca):
    ca_id = subject_ca('Named conflict CA', TWINS)
    cert, err = _issue(app, ca_id, _named_csr(oid=_oid_of(app, ca_id, 'Named conflict CA User'),
                                              name='Named conflict CA VPNUser'))
    assert cert is None
    assert err == 'The request names two different certificate templates'


def test_a_name_two_templates_share_up_to_case_is_refused(app, subject_ca):
    ca_id = subject_ca('Named case CA', {'User': TWINS['User'], 'USER': TWINS['VPNUser']})
    cert, err = _issue(app, ca_id, _named_csr(name='Named case CA user'))
    assert cert is None
    assert err == "Certificate template name 'Named case CA user' is ambiguous"


def test_a_named_template_does_not_widen_its_purposes(app, subject_ca):
    """The EKU match used to pick 'Web' here, with its own Enroll ACL."""
    ca_id = subject_ca('Named eku CA', TWINS)
    cert, err = _issue(app, ca_id, _named_csr(name='Named eku CA User', ekus=(SERVER_AUTH,)))
    assert cert is None
    assert err == "Template 'Named eku CA User' does not issue the Extended Key Usages the request asks for"


def test_a_request_naming_no_template_is_matched_by_its_ekus(app, subject_ca):
    ca_id = subject_ca('Named fallback CA', TWINS)
    cert, err = _issue(app, ca_id, _named_csr())
    assert err is None, err
    assert _template_oid(cert).dotted_string == _oid_of(app, ca_id, 'Named fallback CA User')


def test_an_unreadable_template_name_is_refused(app, subject_ca):
    ca_id = subject_ca('Named garbled CA', TWINS)
    cert, err = _issue(app, ca_id, _named_csr(name='User', name_type=asn1_core.IA5String))
    assert cert is None
    assert err == 'Invalid certificate template extension in the request'


@pytest.fixture
def split_xcep(app, subject_ca, create_ca):
    """A WSTEP CA offering TWINS while XCEP is set to another CA: (WSTEP CA id, XCEP OID of VPNUser)."""
    from tests.windows_profile_support import restore, set_config, snapshot
    ca_id = subject_ca('Named split WSTEP CA', TWINS)
    xcep_ca = create_ca(cn='Named split XCEP CA')
    with app.app_context():
        template = CertificateTemplate.query.filter_by(name='Named split WSTEP CA VPNUser').one()
        oid = _policy_oid_for_template(db.session.get(CA, xcep_ca['id']), template)
        saved = snapshot(('xcep_ca_refid',))
        set_config('xcep_ca_refid', xcep_ca['refid'])
    yield ca_id, oid
    with app.app_context():
        restore(saved)


def test_an_oid_announced_by_a_separate_xcep_ca_is_issued(app, split_xcep):
    """XCEP and WSTEP may be set to two CAs: the client names the OID the XCEP policy gave,
    and autoenrollment finds its template again only if the certificate carries that OID."""
    ca_id, oid = split_xcep
    cert, err = _issue(app, ca_id, _named_csr(oid=oid))
    assert err is None, err
    assert _template_oid(cert).dotted_string == oid != _oid_of(app, ca_id, 'Named split WSTEP CA VPNUser')


@pytest.mark.parametrize('path', ['tls', 'xml'])
def test_a_certificate_naming_the_xcep_oid_renews_under_it(app, split_xcep, path):
    ca_id, oid = split_xcep
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f'split-renew-{path}.example.test')]))
           .add_extension(x509.ExtendedKeyUsage([CLIENT_AUTH]), critical=False)
           .add_extension(x509.MSCertificateTemplate(x509.ObjectIdentifier(oid), 100, 0), critical=False)
           .sign(key, hashes.SHA256()))
    old_cert, err = _issue(app, ca_id, csr)
    assert err is None, err
    cert, err = _renew(app, ca_id, path, old_cert, key, _eku_csr(old_cert, key, CLIENT_AUTH))
    assert err is None, err
    assert _template_oid(cert).dotted_string == oid


def test_only_an_oid_of_the_template_is_stamped(app, split_xcep):
    from services.wstep.wstep_service import _template_oid_for
    ca_id, oid = split_xcep
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        vpn = CertificateTemplate.query.filter_by(name='Named split WSTEP CA VPNUser').one()
        user = CertificateTemplate.query.filter_by(name='Named split WSTEP CA User').one()
        assert _template_oid_for(ca, vpn, oid, profile=default_profile()) == oid
        xcep_ca = db.session.get(CA, ca_id_of_xcep(oid))
        # A request naming another template's OID, or none, gets the OID XCEP announced
        assert _template_oid_for(ca, user, oid, profile=default_profile()) == _policy_oid_for_template(xcep_ca, user)
        assert _template_oid_for(ca, user, None, profile=default_profile()) == _policy_oid_for_template(xcep_ca, user)


def ca_id_of_xcep(oid):
    from tests.windows_profile_support import get_config
    return CA.query.filter_by(refid=get_config('xcep_ca_refid')).one().id


@pytest.mark.parametrize('how', ['name', 'eku'])
def test_a_request_not_naming_the_oid_carries_the_one_xcep_announced(app, split_xcep, how):
    """Named by szOID_ENROLL_CERTTYPE only, or matched by its EKUs: autoenrollment still
    looks the certificate's template up by the OID XCEP announced."""
    ca_id, _oid = split_xcep
    csr = (_named_csr(name='Named split WSTEP CA VPNUser') if how == 'name'
           else _named_csr(ekus=(SERVER_AUTH,)))
    cert, err = _issue(app, ca_id, csr)
    assert err is None, err
    template = 'VPNUser' if how == 'name' else 'Web'
    with app.app_context():
        xcep_ca = db.session.get(CA, ca_id_of_xcep(_oid))
        wanted = _policy_oid_for_template(
            xcep_ca, CertificateTemplate.query.filter_by(name=f'Named split WSTEP CA {template}').one())
    assert _template_oid(cert).dotted_string == wanted != _oid_of(app, ca_id, f'Named split WSTEP CA {template}')


@pytest.mark.parametrize('path', ['tls', 'xml'])
@pytest.mark.parametrize('change', ['cleared', 'moved'])
def test_a_certificate_renews_after_the_xcep_ca_changes(app, split_xcep, create_ca, change, path):
    """The renewed certificate was issued by this CA: its template OID, stamped under the XCEP
    CA of the time, still names its template once that setting is cleared or moved."""
    ca_id, oid = split_xcep
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f'split-move-{change}-{path}.example.test')]))
           .add_extension(x509.ExtendedKeyUsage([CLIENT_AUTH]), critical=False)
           .add_extension(x509.MSCertificateTemplate(x509.ObjectIdentifier(oid), 100, 0), critical=False)
           .sign(key, hashes.SHA256()))
    old_cert, err = _issue(app, ca_id, csr)
    assert err is None, err
    other = create_ca(cn=f'Named split other XCEP CA {change} {path}') if change == 'moved' else None
    with app.app_context():
        from tests.windows_profile_support import set_config
        set_config('xcep_ca_refid', other['refid'] if other else '')
    cert, err = _renew(app, ca_id, path, old_cert, key, _eku_csr(old_cert, key, CLIENT_AUTH))
    assert err is None, err
    with app.app_context():
        vpn = CertificateTemplate.query.filter_by(name='Named split WSTEP CA VPNUser').one()
        now = _policy_oid_for_template(db.session.get(CA, other['id'] if other else ca_id), vpn)
    assert _template_oid(cert).dotted_string == now != oid


def _foreign_oid_cert(app, ca_id, template_name, key, refid='another-ucm-instance-ca'):
    """A certificate of this CA carrying the policy OID the CA of ``refid`` derives for the
    template: by default another UCM instance's, as an imported certificate could."""
    from types import SimpleNamespace
    from services.ca_service import CAService
    with app.app_context():
        template = CertificateTemplate.query.filter_by(name=template_name).one()
        foreign = _policy_oid_for_template(SimpleNamespace(refid=refid), template)
        csr = (x509.CertificateSigningRequestBuilder()
               .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'foreign.example.test')]))
               .add_extension(x509.ExtendedKeyUsage([CLIENT_AUTH]), critical=False)
               .sign(key, hashes.SHA256()))
        pem, _serial = CAService.sign_csr_from_crypto(
            ca=db.session.get(CA, ca_id), csr=csr, validity_days=30, source='wstep',
            ms_certificate_template_oid=foreign, cert_type='client_cert',
            extra_ekus=[CLIENT_AUTH.dotted_string], template_ekus=[CLIENT_AUTH.dotted_string])
    cert = x509.load_pem_x509_certificate(pem.encode())
    assert _template_oid(cert).dotted_string == foreign
    return cert


@pytest.mark.parametrize('path', ['tls', 'xml'])
def test_a_template_oid_of_another_instance_does_not_renew(app, subject_ca, path):
    """Only a prefix derived from one of this instance's CAs names a template here."""
    ca_id = subject_ca(f'Named foreign {path} CA', TWINS)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    old_cert = _foreign_oid_cert(app, ca_id, f'Named foreign {path} CA VPNUser', key)
    cert, err = _renew(app, ca_id, path, old_cert, key, _eku_csr(old_cert, key, CLIENT_AUTH))
    assert cert is None
    assert err == 'The certificate template of the certificate being renewed is not offered by this CA'


@pytest.mark.parametrize('path', ['tls', 'xml'])
def test_a_template_of_capped_ekus_only_does_not_renew(app, subject_ca, path):
    """Its only EKU would be dropped and the server profile applied instead."""
    ca_id = subject_ca(f'Named capped {path} CA', {**TWINS, 'OCSP': ('ocsp', ['ocspSigning'], False, 'RSA-2048')})
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with app.app_context():
        refid = db.session.get(CA, ca_id).refid
    old_cert = _foreign_oid_cert(app, ca_id, f'Named capped {path} CA OCSP', key, refid=refid)
    cert, err = _renew(app, ca_id, path, old_cert, key,
                       _eku_csr(old_cert, key, x509.oid.ExtendedKeyUsageOID.OCSP_SIGNING))
    assert cert is None
    assert err == (f"Template 'Named capped {path} CA OCSP' configures only Extended Key Usages "
                   'this service does not issue')


@pytest.mark.parametrize('path', ['tls', 'xml'])
def test_a_certificate_without_template_does_not_renew_into_capped_ekus_only(app, subject_ca, path):
    """Matched by its EKUs on renewal, as on issuance, the capped template is refused too."""
    from services.ca_service import CAService
    ca_id = subject_ca(f'Named capped bare {path} CA', {**TWINS, 'OCSP': ('ocsp', ['ocspSigning'], False, 'RSA-2048')})
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with app.app_context():
        pem, _serial = CAService.sign_csr_from_crypto(
            ca=db.session.get(CA, ca_id), csr=_eku_csr('bare-renew.example.test', key, CLIENT_AUTH),
            validity_days=30, source='wstep', cert_type='client_cert')
    old_cert = x509.load_pem_x509_certificate(pem.encode())
    assert _template_oid(old_cert) is None
    cert, err = _renew(app, ca_id, path, old_cert, key,
                       _eku_csr(old_cert, key, x509.oid.ExtendedKeyUsageOID.OCSP_SIGNING))
    assert cert is None
    assert err == (f"Template 'Named capped bare {path} CA OCSP' configures only Extended Key Usages "
                   'this service does not issue')
