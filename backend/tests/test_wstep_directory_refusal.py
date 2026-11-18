"""A Kerberos request whose subject the directory cannot build is refused with the directory's reason,
whatever the request's shape (SQLite, and PostgreSQL with UCM_TEST_APP_PG_URL): the real autoenrollment
request is naked (empty subject, no SAN, the template extension, signed SHA-1 inside CMC), and the fault
and the audit entry name the directory's answer, never the request's subject."""
import pytest
from asn1crypto import algos as asn1_algos, csr as asn1_csr
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from services.ad_connector import lookup as ad_lookup
from services.wstep import CES_KERBEROS_PATH
from tests.test_wstep_kerberos_no_template import MACHINE, USER, realm_a  # noqa: F401
from tests.test_wstep_renew_tls import _cmc_renewal, _rst
from tests.test_windows_profile_routing import NEGOTIATE, _as, _audits, _fault, _top_audit, world  # noqa: F401
from tests.windows_profile_support import windows_profiles_restored  # noqa: F401

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')
BUILT = 'The certificate subject is built from Active Directory, which '
UNREACHABLE = 'The directory that builds the certificate subject could not be reached'
SUBJECT_BLAME = 'CSR subject must include a non-empty CN or a SubjectAltName'


def _windows_request(template_oid, shape):
    """The autoenrollment request as Windows sends it: the template's EKU, critical Key Usage, the
    template extension v2 (version 100), SKI, signed SHA-1; *shape* adds a subject or a SAN."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = [x509.NameAttribute(NameOID.COMMON_NAME, 'asked.c04a.test')] if shape == 'subject' else []
    builder = (x509.CertificateSigningRequestBuilder().subject_name(x509.Name(subject))
               .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
               .add_extension(x509.KeyUsage(True, False, True, False, False, False, False, False, False),
                              critical=True)
               .add_extension(x509.MSCertificateTemplate(x509.ObjectIdentifier(template_oid), 100, 0),
                              critical=False)
               .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False))
    if shape == 'san':
        builder = builder.add_extension(x509.SubjectAlternativeName([x509.DNSName('asked.c04a.test')]),
                                        critical=False)
    # cryptography signs no CSR with SHA-1: the TBS is signed again by the key primitive
    tbs = builder.sign(key, hashes.SHA256()).tbs_certrequest_bytes
    csr = x509.load_der_x509_csr(asn1_csr.CertificationRequest({
        'certification_request_info': asn1_csr.CertificationRequestInfo.load(tbs),
        'signature_algorithm': asn1_algos.SignedDigestAlgorithm({'algorithm': 'sha1_rsa'}),
        'signature': key.sign(tbs, padding.PKCS1v15(), hashes.SHA1())}).dump())
    return _rst(_cmc_renewal(csr, [(key, None)]))


# What the directory answers -> the reason the fault gives (None: the directory could not be reached)
USER_ANSWERS = {
    'no-account': (None, 'found no account for the requester'),
    'no-upn': (ad_lookup.NO_UPN, 'found the account but it has no userPrincipalName'),
    'unreadable-path': ({'dn_components': [('XX', 'unknown')], 'upn': 'usera@c04a.test', 'mail': None,
                         'sam_account_name': 'usera'}, 'found the account but could not read its directory path'),
    'unreachable': (ad_lookup.UNREACHABLE, None),
}
MACHINE_ANSWERS = {
    'no-account': (None, 'could not resolve the requester'),
    'unreachable': (ad_lookup.UNREACHABLE, None),
}
CASES = ([('user', USER, k) for k in USER_ANSWERS] + [('machine', MACHINE, k) for k in MACHINE_ANSWERS])


@pytest.mark.parametrize('shape', ['naked', 'subject', 'san'])
@pytest.mark.parametrize('kind, principal, answer', CASES, ids=[f'{c[0]}-{c[2]}' for c in CASES])
def test_the_fault_and_the_audit_name_the_directory_whatever_the_request_s_shape(
        app, client, world, realm_a, monkeypatch, kind, principal, answer, shape):
    if kind == 'user':
        found, reason = USER_ANSWERS[answer]
        monkeypatch.setattr(ad_lookup, 'lookup_user_ad_identity', lambda config, sam: found)
    else:
        found, reason = MACHINE_ANSWERS[answer]
        monkeypatch.setattr(ad_lookup, 'lookup_computer_dns_hostname', lambda config, sam: found)
    floor = _top_audit(app)
    _as(world, principal)
    status, code, text = _fault(client.post(CES_KERBEROS_PATH, data=_windows_request(realm_a[kind], shape),
                                            headers=NEGOTIATE))
    expected = (500, 's:Receiver', UNREACHABLE) if reason is None else (400, 's:Sender', BUILT + reason)
    assert (status, code, text) == expected
    (action, user, name, details, ok), = _audits(app, floor)
    assert (action, user, name, ok) == ('windows_enrollment.refused', principal, 'c04-a', False)
    assert expected[2] in details and SUBJECT_BLAME not in details
