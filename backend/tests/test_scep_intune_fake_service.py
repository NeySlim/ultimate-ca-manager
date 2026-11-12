"""Intune SCEP against a real local HTTP service (token, discovery and
ScepActions): the failures it can answer with, and a Windows-shaped enrolment
and renewal bound to one of two applications of different tenants."""
import base64
import secrets

import asn1crypto.cms
import asn1crypto.core
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import AttributeOID, NameOID

from models import Certificate, SCEPRequest, db
from models.scep import IntuneApp, ScepProfile
from services.scep import intune_client as intune
from services.scep.crypto_helpers import create_signed_pkcs7
from tests.intune_fake_service import FakeIntune
from tests.test_scep_fips import _attrs, _envelope
from tests.test_scep_rfc8894_operations import (
    FAIL_INFO_OID, MESSAGE_TYPE_OID, PKI_STATUS_OID, _client_identity, _decrypt_response,
    _response_attributes,
)

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')

TENANTS = {'A': ('tenant-a.example.test', 'client-a', 'secret-a'),
           'B': ('tenant-b.example.test', 'client-b', 'secret-b')}
BAD_MESSAGE_CHECK = '1'


@pytest.fixture
def fake(monkeypatch):
    service = FakeIntune()
    service.start()
    service.patch(monkeypatch)
    for tenant, client_id, secret in TENANTS.values():
        service.register(tenant, client_id, secret)
    yield service
    service.stop()


@pytest.fixture
def env(app, create_ca, fake):
    """A CA, two Intune applications of different tenants and a profile on each."""
    ca = create_ca(cn=f'Intune Fake CA {secrets.token_hex(3)}')
    suffix = secrets.token_hex(3)
    rows = {}
    with app.app_context():
        from models import CA
        refid = db.session.get(CA, ca['id']).refid
        for key, (tenant, client_id, secret) in TENANTS.items():
            row = IntuneApp(name=f'fake-{key}-{suffix}', tenant_id=tenant, client_id=client_id,
                            client_secret=secret)
            db.session.add(row)
            db.session.flush()
            profile = ScepProfile(name=f'fake-{key}-{suffix}', url_slug=f'fake-{key.lower()}-{suffix}',
                                  ca_refid=refid, auto_approve=True, intune_enabled=True,
                                  intune_app_id=row.id)
            db.session.add(profile)
            db.session.flush()
            rows[key] = {'app': row.id, 'profile': profile.id, 'slug': profile.url_slug}
        db.session.commit()
    yield {'ca_id': ca['id'], 'ca_refid': refid, 'rows': rows}
    with app.app_context():
        SCEPRequest.query.filter_by(ca_refid=refid).delete()
        Certificate.query.filter_by(caref=refid).delete()
        for row in rows.values():
            ScepProfile.query.filter_by(id=row['profile']).delete()
            IntuneApp.query.filter_by(id=row['app']).delete()
        db.session.commit()


def _ca_cert(client, slug):
    r = client.get(f'/scep/{slug}/pkiclient.exe?operation=GetCACert')
    assert r.status_code == 200, r.data
    return x509.load_der_x509_certificate(r.data)


def _csr(key, cn, challenge, san='device.example.test'):
    return (x509.CertificateSigningRequestBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(san)]), False)
            .add_attribute(AttributeOID.CHALLENGE_PASSWORD, challenge.encode())
            .sign(key, hashes.SHA256()))


def _windows_request(ca_cert, csr, signer, message_type, txn):
    """RSA-OAEP envelope (as Windows wraps the content key), the challenge inside the PKCS#10."""
    cert, key = signer
    payload = _envelope(csr.public_bytes(serialization.Encoding.DER), [(ca_cert, 'oaep-sha1')], 'aes256')
    attrs = _attrs(txn)
    attrs[1] = {'type': MESSAGE_TYPE_OID, 'values': [
        asn1crypto.core.PrintableString(str(message_type))]}
    return create_signed_pkcs7(payload, key, cert, signed_attributes=attrs)


def _long_challenge(marker=''):
    """An Intune challenge blob: several kilobytes of base64 text."""
    return secrets.token_urlsafe(3500) + marker


def _enrol(client, slug, ca_cert, *, cn=None, challenge=None):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cn = cn or f'win-{secrets.token_hex(4)}.example.test'
    challenge = challenge or _long_challenge()
    assert len(challenge) > 4000
    csr = _csr(key, cn, challenge, san=cn)
    device = _client_identity(cn)
    request = _windows_request(ca_cert, csr, device, 19, f'txn-{secrets.token_hex(6)}')
    r = client.post(f'/scep/{slug}/pkiclient.exe?operation=PKIOperation', data=request,
                    content_type='application/x-pki-message')
    assert r.status_code == 200, r.data
    return r.data, key, device


def _issued_cert(response, key, device):
    degenerate = asn1crypto.cms.ContentInfo.load(_decrypt_response(response, device[1], device[0]))
    return x509.load_der_x509_certificate(degenerate['content']['certificates'][0].chosen.dump())


def _persisted(app, refid):
    with app.app_context():
        return (SCEPRequest.query.filter_by(ca_refid=refid).count(),
                Certificate.query.filter_by(caref=refid).count())


def _assert_refused(app, env, response):
    attrs = _response_attributes(response)
    assert attrs[PKI_STATUS_OID] == '2' and attrs[FAIL_INFO_OID] == BAD_MESSAGE_CHECK, attrs
    assert _persisted(app, env['ca_refid']) == (0, 0)


# ---- Criterion 5: what the service can answer ------------------------------

FAILURES = [
    ('token-401', 'token', 401, b'{"error": "invalid_client"}'),
    ('token-429', 'token', 429, b'{"error": "throttled"}'),
    ('validate-503', 'validate', 503, b'service unavailable'),
    ('validate-429', 'validate', 429, b'{}'),
    ('validate-invalid-json', 'validate', 200, b'<html>not json'),
    ('token-expired-at-the-service', 'validate', 401, b'{"error": "token expired"}'),
    ('stale-service-endpoint', 'validate', 404, b'gone'),
]


@pytest.mark.parametrize('case,kind,status,body', FAILURES, ids=[f[0] for f in FAILURES])
def test_intune_service_failure_is_bad_message_check_and_nothing_is_persisted(
        app, client, env, fake, case, kind, status, body):
    slug = env['rows']['A']['slug']
    ca_cert = _ca_cert(client, slug)
    fake.queue(kind, status, body)
    response, _key, _device = _enrol(client, slug, ca_cert)
    _assert_refused(app, env, response)
    assert fake.of('success') == [] and fake.of('failure') == []
    # The next request recovers: the failure left no bad state behind
    response, key, device = _enrol(client, slug, ca_cert)
    assert _response_attributes(response)[PKI_STATUS_OID] == '0'
    assert _persisted(app, env['ca_refid']) == (1, 1)


def test_a_401_from_the_service_makes_the_next_request_ask_for_a_new_token(client, env, fake):
    slug = env['rows']['A']['slug']
    ca_cert = _ca_cert(client, slug)
    _enrol(client, slug, ca_cert)
    tokens = len(fake.of('token'))
    fake.queue('validate', 401, b'{}')
    _enrol(client, slug, ca_cert)           # refused
    _enrol(client, slug, ca_cert)           # served with a new token
    assert len(fake.of('token')) == tokens + 1
    assert fake.of('validate')[-1]['auth'] != fake.of('validate')[0]['auth']


def test_a_stale_service_endpoint_is_discovered_again_by_the_next_request(client, env, fake):
    slug = env['rows']['A']['slug']
    ca_cert = _ca_cert(client, slug)
    _enrol(client, slug, ca_cert)
    assert len(fake.of('discover')) == 1
    fake.queue('validate', 404, b'moved')
    _enrol(client, slug, ca_cert)           # refused, endpoint forgotten
    _enrol(client, slug, ca_cert)           # discovered again
    assert len(fake.of('discover')) == 2


def test_two_enrolments_cost_one_token_and_one_discovery(client, env, fake):
    slug = env['rows']['A']['slug']
    ca_cert = _ca_cert(client, slug)
    for _ in range(2):
        _enrol(client, slug, ca_cert)
    assert len(fake.of('token')) == 2       # Graph and Intune scopes, once each
    assert len(fake.of('discover')) == 1


def test_a_token_that_expires_at_once_is_asked_for_again(client, env, fake):
    slug = env['rows']['A']['slug']
    ca_cert = _ca_cert(client, slug)
    original = intune.TOKEN_EXPIRY_MARGIN_SECONDS
    intune.TOKEN_EXPIRY_MARGIN_SECONDS = 10 ** 6
    try:
        for _ in range(2):
            _enrol(client, slug, ca_cert)
    finally:
        intune.TOKEN_EXPIRY_MARGIN_SECONDS = original
    # graph + validate + notify on the first enrolment, validate + notify on the second
    assert len(fake.of('token')) == 5


# ---- Criterion 6: Windows-shaped enrolment and renewal, two applications ----

def test_windows_enrolment_and_renewal_call_the_profiles_own_application(app, client, env, fake):
    slug_a, slug_b = env['rows']['A']['slug'], env['rows']['B']['slug']
    tenant_a, tenant_b = TENANTS['A'][0], TENANTS['B'][0]
    ca_cert = _ca_cert(client, slug_a)

    response, key, device = _enrol(client, slug_a, ca_cert, cn='win-device.example.test')
    issued = _issued_cert(response, key, device)
    assert _response_attributes(response)[PKI_STATUS_OID] == '0'
    issued.verify_directly_issued_by(ca_cert)

    # The renewal is signed by the issued certificate, with the long challenge again
    new_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = _csr(new_key, 'win-device.example.test', _long_challenge(), san='win-device.example.test')
    renewal = _windows_request(ca_cert, csr, (issued, key), 17, f'txn-{secrets.token_hex(6)}')
    r = client.post(f'/scep/{slug_a}/pkiclient.exe?operation=PKIOperation', data=renewal,
                    content_type='application/x-pki-message')
    assert r.status_code == 200
    assert _response_attributes(r.data)[PKI_STATUS_OID] == '0', _response_attributes(r.data)

    # Everything went to tenant A: tokens with A's client, validate and success on A's service
    assert {c['client_id'] for c in fake.of('token')} == {TENANTS['A'][1]}
    assert len(fake.of('validate', tenant_a)) == 2 and len(fake.of('success', tenant_a)) == 2
    assert fake.of('validate', tenant_b) == [] and fake.of('success', tenant_b) == []
    sent = fake.of('validate', tenant_a)[0]['json']['request']
    csr_der = base64.b64decode(sent['certificateRequest'])
    challenge = x509.load_der_x509_csr(csr_der).attributes.get_attribute_for_oid(
        AttributeOID.CHALLENGE_PASSWORD).value
    assert len(challenge) > 4000

    # The profile on the other tenant calls the other application
    response, _k, _d = _enrol(client, slug_b, ca_cert)
    assert _response_attributes(response)[PKI_STATUS_OID] == '0'
    assert len(fake.of('validate', tenant_b)) == 1
    assert {c['client_id'] for c in fake.of('token', tenant_b)} == {TENANTS['B'][1]}


@pytest.mark.parametrize('code', ['ChallengeExpired', 'RegisteredKeyMismatch'])
def test_intune_refusal_code_is_bad_message_check_without_certificate_or_failure_notice(
        app, client, env, fake, code):
    """Freezes today's behaviour: a refusal by validateRequest is answered badMessageCheck;
    Intune is not sent a failure notification for a request it refused itself."""
    slug = env['rows']['A']['slug']
    ca_cert = _ca_cert(client, slug)
    fake.refusals[TENANTS['A'][0]] = (code, 'refused by the test service')
    response, _key, _device = _enrol(client, slug, ca_cert)
    _assert_refused(app, env, response)
    assert len(fake.of('validate')) == 1
    assert fake.of('failure') == [] and fake.of('success') == []


def test_a_request_intune_validated_but_the_ca_refuses_is_reported_as_a_failure(app, client, env, fake):
    slug = env['rows']['A']['slug']
    ca_cert = _ca_cert(client, slug)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = _csr(key, 'win-bad-name.example.test', _long_challenge(), san='not a dns name')
    device = _client_identity('win-bad-name.example.test')
    request = _windows_request(ca_cert, csr, device, 19, f'txn-{secrets.token_hex(6)}')
    r = client.post(f'/scep/{slug}/pkiclient.exe?operation=PKIOperation', data=request,
                    content_type='application/x-pki-message')
    attrs = _response_attributes(r.data)
    assert attrs[PKI_STATUS_OID] == '2' and attrs[FAIL_INFO_OID] == '2'   # badRequest
    assert _persisted(app, env['ca_refid']) == (0, 0)
    assert len(fake.of('validate')) == 1
    failures = fake.of('failure', TENANTS['A'][0])
    assert len(failures) == 1 and fake.of('success') == []
    assert 'DNS' in failures[0]['json']['notification']['errorDescription']
