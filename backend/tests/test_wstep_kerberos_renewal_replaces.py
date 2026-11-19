"""A WSTEP renewal replaces the renewed certificate on the Kerberos binding as on the Certificate binding,
and after a change of the profile's CA the certificate of the former CA renews as such (SQLite, and
PostgreSQL with UCM_TEST_APP_PG_URL). The renewed row is archived in the commit that stores its
successor, and a second renewal of it is refused on either binding."""
import base64
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from models import CATemplatePin, Certificate, db
from services.wstep import CES_CERTIFICATE_PATH, CES_KERBEROS_PATH, wstep_service
from tests.protocol_approval_support import approval_policy, approve, requests_of
from tests.test_protocol_approval_wstep import _pending, _query_rst
from tests.test_windows_profile_renewal import directory  # noqa: F401
from tests.test_windows_profile_routing import (NEGOTIATE, SID, _as, _audits, _fault, _profile,  # noqa: F401
                                                _top_audit, world)
from tests.test_wstep_kerberos_issue import _issued_cert_from_rstr
from tests.test_wstep_kerberos_no_template import (MACHINE, NO_TEMPLATE, SERVER_AUTH, _csr, _post,  # noqa: F401
                                                   _renew, _template_less_certificate, realm_a)
from tests.test_wstep_renew import _build_signed_rst
from tests.windows_profile_support import windows_profiles_restored  # noqa: F401

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')
CERT_SUPERSEDED = 'Signing certificate has been superseded by a newer one'


def _key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _old(app, client, world, realm_a, with_template):
    """hosta$'s certificate of CA A (profile c04-a, its SID): issued over Kerberos naming the machine
    template, or issued before 3.0 without template."""
    key = _key()
    if not with_template:
        return _template_less_certificate(app, world, key), key
    r = _post(client, world, MACHINE, _csr(template_oid=realm_a['machine'], key=key))
    assert r.status_code == 200, r.data
    return _issued_cert_from_rstr(r.data), key


def _kerberos_renewal(client, world, realm_a, old, key, with_template):
    """As Windows renews: the new key and the renewed certificate sign the CMC; the template
    extension is copied when the certificate carries one."""
    new_key = _key()
    csr = (_csr(template_oid=realm_a['machine'], key=new_key) if with_template
           else _csr('c15-old', ekus=[SERVER_AUTH], key=new_key))
    return _renew(client, world, MACHINE, old, key, new_key, csr)


def _same_names_csr(cert, key):
    """A renewal request at par: the subject, SAN and EKUs of *cert*, its key."""
    builder = x509.CertificateSigningRequestBuilder().subject_name(cert.subject)
    for kind in (x509.SubjectAlternativeName, x509.ExtendedKeyUsage):
        try:
            builder = builder.add_extension(cert.extensions.get_extension_for_class(kind).value, critical=False)
        except x509.ExtensionNotFound:
            pass
    return builder.sign(key, hashes.SHA256())


def _certificate_renewal(client, old, key):
    return client.post(CES_CERTIFICATE_PATH, data=_build_signed_rst(old, key, _same_names_csr(old, key)),
                       headers={'Content-Type': 'application/soap+xml; charset=utf-8'})


def _renewal(binding, client, world, realm_a, old, key, with_template):
    if binding == 'kerberos':
        return _kerberos_renewal(client, world, realm_a, old, key, with_template)
    return _certificate_renewal(client, old, key)


def _archived(app, cert):
    """The archived flag of every row holding *cert*."""
    with app.app_context():
        return [r.archived for r in Certificate.query.filter_by(serial_number=str(cert.serial_number))]


def _count(app):
    with app.app_context():
        return Certificate.query.count()


def _issuer_cn(cert):
    return cert.issuer.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value


# --- F2: the same replacement on both bindings ----------------------------------------------------

@pytest.mark.parametrize('second', ['kerberos', 'certificate'])
@pytest.mark.parametrize('first', ['kerberos', 'certificate'])
@pytest.mark.parametrize('with_template', [True, False], ids=['template', 'template-less'])
def test_a_renewal_replaces_the_renewed_certificate_on_either_binding(
        app, client, world, realm_a, directory, with_template, first, second):
    """Never renewed: served, certificate.renewed, the old row archived, the new one live. Renewed
    already (by either binding): a second renewal of the same certificate is refused, nothing stored."""
    old, key = _old(app, client, world, realm_a, with_template)
    floor = _top_audit(app)
    r = _renewal(first, client, world, realm_a, old, key, with_template)
    assert r.status_code == 200, r.data
    new = _issued_cert_from_rstr(r.data)
    assert _archived(app, old) == [True] and _archived(app, new) == [False]
    (action, _u, _n, details, ok), = _audits(app, floor)
    assert (action, ok) == ('certificate.renewed', True)
    assert f'old serial {old.serial_number}, new serial {new.serial_number}' in details

    floor, before = _top_audit(app), _count(app)
    status, code, text = _fault(_renewal(second, client, world, realm_a, old, key, with_template))
    expected = wstep_service.RENEWED_SUPERSEDED if second == 'kerberos' else CERT_SUPERSEDED
    assert (status, code, text) == (400, 's:Sender', expected)
    assert _count(app) == before and _archived(app, new) == [False]
    (action, _u, _n, details, ok), = _audits(app, floor)
    assert action == ('windows_enrollment.refused' if second == 'kerberos' else 'certificate.renewed')
    assert not ok and expected in details


def test_a_kerberos_renewal_overtaken_by_another_is_refused_and_stores_nothing(
        app, client, world, realm_a, monkeypatch):
    """Of two concurrent renewals only one archives the renewed row (compare-and-set): the other
    is refused as renewed meanwhile, its certificate rolled back."""
    from services.ca import ca_signing
    old, key = _old(app, client, world, realm_a, True)
    before = _count(app)
    monkeypatch.setattr(ca_signing, '_claim_superseded', lambda *a, **k: False)
    assert _fault(_kerberos_renewal(client, world, realm_a, old, key, True)) == (
        400, 's:Sender', wstep_service.RENEWED_SUPERSEDED)
    assert _count(app) == before and _archived(app, old) == [False]


def _held_renewal(app, client, world, realm_a, policy_id, old, key, with_template=True):
    """A Kerberos renewal of *old* held for approval: (RequestID, approval id)."""
    request_id = _pending(_kerberos_renewal(client, world, realm_a, old, key, with_template))
    (approval_id, status, data, _c), = requests_of(app, policy_id, 'wstep_request')
    assert status == 'pending' and data.get('renewal_of'), data
    return request_id, approval_id


def _policy_active(app, policy_id, active):
    """The policy holds no request while inactive: the other binding's renewal is served at once."""
    from models.policy import CertificatePolicy
    with app.app_context():
        db.session.get(CertificatePolicy, policy_id).is_active = active
        db.session.commit()


def _query(client, world, request_id):
    _as(world, MACHINE)
    return client.post(CES_KERBEROS_PATH, data=_query_rst(request_id), headers=NEGOTIATE)


def test_an_approved_kerberos_renewal_replaces_the_renewed_certificate(
        app, client, auth_client, world, realm_a):
    old, key = _old(app, client, world, realm_a, True)
    with approval_policy(app, world['cas']['A']['id'], 'c19-held-renewal') as pid:
        request_id, approval_id = _held_renewal(app, client, world, realm_a, pid, old, key)
        assert _archived(app, old) == [False]
        approve(auth_client, approval_id)
        r = _query(client, world, request_id)
        assert r.status_code == 200, r.data
        assert _archived(app, old) == [True]
        assert _archived(app, _issued_cert_from_rstr(r.data)) == [False]


def test_a_held_kerberos_renewal_whose_certificate_the_other_binding_renewed_is_refused(
        app, client, auth_client, world, realm_a, directory):
    """The guard sees a renewal of either binding: renewed by certificate meanwhile, the held
    Kerberos renewal issues nothing."""
    old, key = _old(app, client, world, realm_a, True)
    with approval_policy(app, world['cas']['A']['id'], 'c19-held-overtaken') as pid:
        _request_id, approval_id = _held_renewal(app, client, world, realm_a, pid, old, key)
        _policy_active(app, pid, False)
        assert _certificate_renewal(client, old, key).status_code == 200
        _policy_active(app, pid, True)
        assert _archived(app, old) == [True]
        before = _count(app)
        r = auth_client.post(f'/api/v2/approvals/{approval_id}/approve', json={'comment': 'ok'})
        assert r.get_json()['message'] == 'Request closed'
        assert r.get_json()['data']['issue_error'].endswith(wstep_service.RENEWED_SUPERSEDED)
        assert _count(app) == before


# --- F3: the certificate of the profile's former CA ---------------------------------------------

@pytest.fixture
def moved(app, world, create_ca):
    """Moves profile c04-a from CA A to a new CA A2 offering the same templates, CA A listed for
    renewal as the profiles API lists it; the profile's template identifiers do not change."""
    a2 = create_ca(cn='C19 A2 CA')
    with app.app_context():
        template_ids = [t.template_id for t in CATemplatePin.query.filter_by(ca_id=world['cas']['A']['id'])]
        for template_id in template_ids:
            db.session.add(CATemplatePin(ca_id=a2['id'], template_id=template_id))
        profile = _profile('c04-a')
        profile.issuing_ca_refid = a2['refid']
        profile.renewal_ca_refids = json.dumps([world['cas']['A']['refid']])
        db.session.commit()
    yield a2
    with app.app_context():
        _profile('c04-a').issuing_ca_refid = world['cas']['A']['refid']
        _profile('c04-a').renewal_ca_refids = '[]'
        CATemplatePin.query.filter_by(ca_id=a2['id']).delete()
        db.session.commit()


@pytest.mark.parametrize('with_template', [True, False], ids=['template', 'template-less'])
def test_after_a_ca_change_the_former_ca_s_certificate_renews_as_a_renewal(
        app, client, world, realm_a, create_ca, with_template, request):
    old, key = _old(app, client, world, realm_a, with_template)
    a2 = request.getfixturevalue('moved')
    floor = _top_audit(app)
    r = _kerberos_renewal(client, world, realm_a, old, key, with_template)
    assert r.status_code == 200, r.data
    new = _issued_cert_from_rstr(r.data)
    assert _issuer_cn(new) == 'C19 A2 CA' and _issuer_cn(old) == 'C04 A CA'
    (action, _u, _n, details, ok), = _audits(app, floor)
    assert (action, ok) == ('certificate.renewed', True)
    assert f'old serial {old.serial_number}, new serial {new.serial_number}' in details
    assert 'old CA C04 A CA' in details
    assert _archived(app, old) == [True]
    with app.app_context():
        assert Certificate.query.filter_by(serial_number=str(new.serial_number)).one().caref == a2['refid']


def _foreign_lookalike(app, world, key):
    """hosta$'s certificate as a CA outside UCM signs it, stored under CA A's record and profile c04-a."""
    foreign_key = _key()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'C04 A CA')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'hosta.c04a.test')]))
            .issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(hours=1)).not_valid_after(now + timedelta(days=30))
            .sign(foreign_key, hashes.SHA256()))
    with app.app_context():
        db.session.add(Certificate(
            refid=uuid.uuid4().hex[:8], descr='lookalike', caref=world['cas']['A']['refid'],
            crt=base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode(),
            serial_number=str(cert.serial_number), subject=cert.subject.rfc4514_string(),
            subject_cn='hosta.c04a.test', source='wstep', windows_profile_id=_profile('c04-a').id,
            valid_from=now.replace(tzinfo=None), valid_to=(now + timedelta(days=30)).replace(tzinfo=None)))
        db.session.commit()
    return cert


@pytest.mark.parametrize('with_template', [True, False], ids=['template', 'template-less'])
@pytest.mark.parametrize('kind', ['foreign-ca', 'revoked', 'expired', 'other-profile'])
def test_after_a_ca_change_no_other_certificate_opens_a_renewal(
        app, client, world, realm_a, create_ca, request, kind, with_template):
    """A certificate of a CA outside UCM (stored under A's record), revoked, expired or of another
    profile opens nothing more than before: an enrollment naming its template is audited as such,
    a template-less renewal is refused, and nothing is archived."""
    key = _key()
    if kind == 'foreign-ca':
        old = _foreign_lookalike(app, world, key)
    else:
        old = _template_less_certificate(app, world, key, revoked=kind == 'revoked', expired=kind == 'expired',
                                         profile='c04-b' if kind == 'other-profile' else 'c04-a')
    request.getfixturevalue('moved')
    floor, before = _top_audit(app), _count(app)
    r = _kerberos_renewal(client, world, realm_a, old, key, with_template)
    if with_template:
        assert r.status_code == 200, r.data
        (action, _u, _n, details, _ok), = _audits(app, floor)
        assert action == 'certificate.issued' and str(old.serial_number) not in details
    else:
        assert _fault(r) == (400, 's:Sender', NO_TEMPLATE)
        assert _count(app) == before
    assert not any(_archived(app, old))


def test_after_a_ca_change_a_held_renewal_of_the_former_ca_s_certificate_replaces_it(
        app, client, auth_client, world, realm_a, create_ca, request):
    """Approved, it replaces the renewed certificate; revoked after the approval, it is not delivered."""
    from tests.test_protocol_approval_wstep import _fault as _held_fault
    old, key = _old(app, client, world, realm_a, False)
    a2 = request.getfixturevalue('moved')
    with approval_policy(app, a2['id'], 'c19-held-moved') as pid:
        request_id, approval_id = _held_renewal(app, client, world, realm_a, pid, old, key, with_template=False)
        approve(auth_client, approval_id)
        assert _archived(app, old) == [True]
        with app.app_context():
            Certificate.query.filter_by(serial_number=str(old.serial_number)).one().revoked = True
            db.session.commit()
        reason, invalid, _echo = _held_fault(_query(client, world, request_id))
        assert reason == 'Renewed certificate revoked' and invalid == 'true'


# --- A request for another template signed by a certificate of the first ---------------------------

@pytest.fixture
def other_machine(app, world, realm_a):
    """A second machine template on CA A: the OID profile c04-a serves for it."""
    import json
    from models import CA, CertificateTemplate, WindowsEnrollmentProfile
    from services.xcep.policy_builder import served_template_oid
    from tests.fixtures.templates import delete_templates
    with app.app_context():
        other = CertificateTemplate(name='ZZ Other Machine', template_type='vpn_client', key_type='RSA-2048',
                                    validity_days=30, digest='sha256', is_active=True,
                                    extensions_template=json.dumps({'extended_key_usage': ['clientAuth']}))
        db.session.add(other)
        db.session.flush()
        db.session.add(CATemplatePin(ca_id=world['cas']['A']['id'], template_id=other.id))
        db.session.commit()
        profile = WindowsEnrollmentProfile.query.filter_by(name='c04-a').one()
        oid, other_id = served_template_oid(profile, db.session.get(CA, world['cas']['A']['id']), other), other.id
    yield oid
    with app.app_context():
        CATemplatePin.query.filter_by(template_id=other_id).delete()
        db.session.commit()
        delete_templates([other_id])
        db.session.commit()


def _other_template_request(client, world, old, key, template_oid):
    """A request naming *template_oid*, signed by the new key and by *old*, as Windows renews."""
    new_key = _key()
    return _renew(client, world, MACHINE, old, key, new_key, _csr(template_oid=template_oid, key=new_key))


def test_a_request_for_another_template_signed_by_a_certificate_of_the_first_is_an_enrollment(
        app, client, world, realm_a, other_machine, directory):
    """Signed by hosta$'s certificate of the machine template, a request naming another template is
    an enrollment: audited as an issuance, nothing archived; the certificate still renews after it."""
    old, key = _old(app, client, world, realm_a, True)
    floor = _top_audit(app)
    r = _other_template_request(client, world, old, key, other_machine)
    assert r.status_code == 200, r.data
    (action, _u, _n, details, ok), = _audits(app, floor)
    assert (action, ok) == ('certificate.issued', True) and str(old.serial_number) not in details
    assert _archived(app, old) == [False]
    assert _certificate_renewal(client, old, key).status_code == 200
    assert _archived(app, old) == [True]


def test_a_held_request_for_another_template_carries_no_renewal(
        app, client, auth_client, world, realm_a, other_machine):
    """Held for approval, the same request names no renewed certificate, and its approval archives nothing."""
    old, key = _old(app, client, world, realm_a, True)
    with approval_policy(app, world['cas']['A']['id'], 'c19-held-other-template') as pid:
        request_id = _pending(_other_template_request(client, world, old, key, other_machine))
        (approval_id, status, data, _c), = requests_of(app, pid, 'wstep_request')
        assert status == 'pending' and not data.get('renewal_of'), data
        approve(auth_client, approval_id)
        assert _query(client, world, request_id).status_code == 200
        assert _archived(app, old) == [False]


def test_a_request_for_another_template_signed_by_a_renewed_certificate_is_an_enrollment(
        app, client, world, realm_a, other_machine, directory):
    """The template check comes before the renewed-already refusal: signed by hosta$'s certificate
    already replaced, a request naming another template is served as an enrollment."""
    old, key = _old(app, client, world, realm_a, True)
    assert _certificate_renewal(client, old, key).status_code == 200
    floor = _top_audit(app)
    r = _other_template_request(client, world, old, key, other_machine)
    assert r.status_code == 200, r.data
    (action, _u, _n, details, ok), = _audits(app, floor)
    assert (action, ok) == ('certificate.issued', True) and str(old.serial_number) not in details
    assert _archived(app, old) == [True]


def test_a_template_less_request_signed_by_a_templated_certificate_is_refused_alike_replaced_or_not(
        app, client, world, realm_a, directory):
    """Naming no template, signed by hosta$'s certificate of a template: the same refusal whether
    that certificate is still valid or was renewed already."""
    old, key = _old(app, client, world, realm_a, True)
    assert _fault(_renew(client, world, MACHINE, old, key)) == (400, 's:Sender', NO_TEMPLATE)
    assert _certificate_renewal(client, old, key).status_code == 200
    assert _fault(_renew(client, world, MACHINE, old, key)) == (400, 's:Sender', NO_TEMPLATE)


# --- The webhook a renewal emits ------------------------------------------------------------------

@pytest.fixture
def webhook_events(monkeypatch):
    """The certificate webhooks emitted, as (event, serial)."""
    from services import webhook_service
    events = []
    for name, event in (('emit_cert_renewed', 'cert.renewed'), ('emit_cert_issued', 'cert.issued')):
        monkeypatch.setattr(webhook_service, name,
                            lambda cert, ca_refid=None, _e=event: events.append((_e, cert.get('serial_number'))))
    return events


@pytest.mark.parametrize('binding', ['kerberos', 'certificate'])
@pytest.mark.parametrize('with_template', [True, False], ids=['template', 'template-less'])
def test_a_renewal_emits_cert_renewed_on_either_binding(
        app, client, world, realm_a, directory, webhook_events, with_template, binding):
    """A renewal that replaces a certificate emits cert.renewed on both bindings, never cert.issued."""
    old, key = _old(app, client, world, realm_a, with_template)
    webhook_events.clear()
    r = _renewal(binding, client, world, realm_a, old, key, with_template)
    assert r.status_code == 200, r.data
    new = _issued_cert_from_rstr(r.data)
    assert [e for e, _s in webhook_events] == ['cert.renewed']
    assert _archived(app, old) == [True] and _archived(app, new) == [False]


def test_an_enrollment_signed_by_a_certificate_of_another_template_emits_cert_issued(
        app, client, world, realm_a, other_machine, directory, webhook_events):
    """Nothing replaced, nothing renewed: the enrollment emits cert.issued."""
    old, key = _old(app, client, world, realm_a, True)
    webhook_events.clear()
    assert _other_template_request(client, world, old, key, other_machine).status_code == 200
    assert [e for e, _s in webhook_events] == ['cert.issued']
