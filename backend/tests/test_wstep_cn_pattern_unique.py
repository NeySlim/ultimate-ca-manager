"""RFC 5280 §4.1.2.6 at issuance (SQLite, and PostgreSQL with UCM_TEST_APP_PG_URL): a subject a
common name pattern renders is refused once a certificate of the same CA, whatever its status,
carries it for another entity, or for one its SID extension does not name."""
import base64
import datetime
import re
import threading

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from sqlalchemy import event

from models import CA, Certificate, db
from services.ad_connector import lookup as ad_lookup
from services.trust_store.csr_operations_mixin import _ad_security_extension, ad_security_extension_sid
from services.wstep import wstep_service
from tests.ad_connector_support import add_connector
from tests.test_revocation_record_rule import _wait_for_a_lock_waiter
from tests.test_wstep_cn_pattern import _connector, _csr, _renew, _served_realm, pattern_ca  # noqa: F401
from tests.windows_profile_support import connectors_kept, default_profile

EMAIL = ExtendedKeyUsageOID.EMAIL_PROTECTION
SERVER_AUTH = ExtendedKeyUsageOID.SERVER_AUTH
pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')

# sAMAccountName: (SID, displayName, dNSHostName)
ACCOUNTS = {
    'alice': ('S-1-5-21-7-8-9-1101', 'John Smith', None),
    'carol': ('S-1-5-21-7-8-9-1102', 'John Smith', None),
    'bob': ('S-1-5-21-7-8-9-1103', 'john  smith', None),
    'pc1': ('S-1-5-21-7-8-9-1104', 'PC One', None),
    'PC1$': ('S-1-5-21-7-8-9-1105', None, 'pc1.example.test'),
    'WIN11$': ('S-1-5-21-7-8-9-1106', None, 'win11.example.test'),
    'WIN12$': ('S-1-5-21-7-8-9-1107', None, 'win12.example.test'),
}


def _principal(sam):
    return f'{sam}@EXAMPLE.TEST'


@pytest.fixture
def accounts(app, monkeypatch):
    """The directory of ACCOUNTS; a renewal finds the account its SID names."""
    import services.windows_profiles as profiles
    by_sid = {sid: sam for sam, (sid, _n, _h) in ACCOUNTS.items()}
    dn = [('CN', 'x'), ('OU', 'Staff'), ('DC', 'example'), ('DC', 'test')]
    monkeypatch.setattr(ad_lookup, 'connector_account', lambda _config, principal: principal.split('@')[0])
    monkeypatch.setattr(ad_lookup, 'lookup_object_sid', lambda _config, sam: ACCOUNTS[sam][0])
    monkeypatch.setattr(ad_lookup, 'lookup_computer_dns_hostname', lambda _config, sam: ACCOUNTS[sam][2])
    monkeypatch.setattr(ad_lookup, 'lookup_computer_identity', lambda _config, sam: {
        'dns_hostname': ACCOUNTS[sam][2], 'sam_account_name': sam, 'dn_components': dn})
    monkeypatch.setattr(ad_lookup, 'lookup_user_ad_identity', lambda _config, sam: {
        'dn_components': dn, 'upn': f'{sam}@example.test', 'mail': None, 'sam_account_name': sam,
        'display_name': ACCOUNTS[sam][1], 'given_name': None, 'surname': None})
    with connectors_kept(app):
        with app.app_context():
            connector_id = add_connector('cn-unique', server='dc.example.test', base_dn='DC=example,DC=test',
                                         bind_dn='svc', enabled=True).id
        monkeypatch.setattr(profiles, 'profile_sid_connectors', lambda profile, sid: [_connector(connector_id)])
        monkeypatch.setattr(ad_lookup, 'lookup_account_by_sid', lambda config, sid: by_sid[sid])
        yield


def _issue(app, ca_id, sam, key=None):
    eku = SERVER_AUTH if sam.endswith('$') else EMAIL
    with app.app_context():
        pem, err = wstep_service.issue(db.session.get(CA, ca_id), _csr(ekus=[eku], key=key).public_bytes(
            serialization.Encoding.DER), 30, kerberos_principal=_principal(sam), profile=default_profile())
    return (x509.load_pem_x509_certificate(pem.encode()) if pem else None), err


def _taken(template, subject):
    return f"Template '{template}' builds the subject {subject}, which a certificate of another account already carries"


def _refused(err, template, subject):
    assert isinstance(err, wstep_service.SubjectHeldByAnother) and not isinstance(err, wstep_service.ServerError)
    assert err == _taken(template, subject)


def test_a_display_name_serves_the_first_account_refuses_the_second_and_renews_the_first(
        app, pattern_ca, accounts):
    ca_id, _ids = pattern_ca('CN unique display CA', user='{displayName}')
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    first, err = _issue(app, ca_id, 'alice', key)
    assert err is None, err
    cert, err = _issue(app, ca_id, 'carol')
    assert cert is None
    _refused(err, 'CN unique display CA user', 'CN=John Smith')
    assert err.audited == f'{err} (serial {first.serial_number})'
    renewed, err = _renew(app, ca_id, first, key)
    assert err is None, err
    assert renewed.subject == first.subject and ad_security_extension_sid(renewed) == ACCOUNTS['alice'][0]
    with app.app_context():
        assert Certificate.query.filter_by(caref=db.session.get(CA, ca_id).refid).count() == 2


@pytest.mark.parametrize('pattern,kind,sams,subjects', [
    ('{hostname}-WiFi', 'machine', ('WIN11$', 'WIN12$', 'WIN11$'), ('CN=WIN11-WiFi', 'CN=WIN12-WiFi', 'CN=WIN11-WiFi')),
    ('{username}', 'user', ('alice', 'bob', 'alice'), ('CN=alice', 'CN=bob', 'CN=alice')),
], ids=['hostname', 'username'])
def test_a_simple_pattern_serves_each_account_and_the_same_one_again(app, pattern_ca, accounts, pattern, kind,
                                                                     sams, subjects):
    ca_id, _ids = pattern_ca(f'CN unique simple CA {kind}', **{kind: pattern})
    for sam, subject in zip(sams, subjects):
        cert, err = _issue(app, ca_id, sam)
        assert err is None, err
        assert cert.subject.rfc4514_string() == subject


def test_a_subject_differing_in_case_and_spaces_is_the_same(app, pattern_ca, accounts):
    ca_id, _ids = pattern_ca('CN unique case CA', user='{displayName}')
    _cert, err = _issue(app, ca_id, 'alice')
    assert err is None, err
    cert, err = _issue(app, ca_id, 'bob')
    assert cert is None
    _refused(err, 'CN unique case CA user', 'CN=john  smith')


def test_a_user_and_a_computer_of_one_name_under_two_templates(app, pattern_ca, accounts):
    ca_id, _ids = pattern_ca('CN unique kinds CA', machine='{hostname}', user='{username}')
    cert, err = _issue(app, ca_id, 'pc1')
    assert err is None and cert.subject.rfc4514_string() == 'CN=pc1', err
    cert, err = _issue(app, ca_id, 'PC1$')
    assert cert is None
    _refused(err, 'CN unique kinds CA machine', 'CN=PC1')


def _hold(app, ca_id, cn, sid=None, days=30, **row):
    """A certificate of the CA for ``CN=<cn>``, SID extension of ``sid`` when given, stored with ``row``."""
    from services.ca.helpers import get_ca_cert_pem
    from services.hsm.ca_key_loader import get_ca_signing_key
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        issuer = x509.load_pem_x509_certificate(get_ca_cert_pem(ca))
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = datetime.datetime.now(datetime.timezone.utc)
        builder = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
                   .issuer_name(issuer.subject).public_key(key.public_key())
                   .serial_number(x509.random_serial_number())
                   .not_valid_before(now + datetime.timedelta(days=min(days, 0) - 1))
                   .not_valid_after(now + datetime.timedelta(days=days)))
        if sid:
            builder = builder.add_extension(_ad_security_extension(sid), critical=False)
        cert = builder.sign(get_ca_signing_key(ca), hashes.SHA256())
        db.session.add(Certificate(refid=f'cnu{cert.serial_number % 10**8}', descr=cn, caref=ca.refid,
                                   crt=base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode(),
                                   serial_number=str(cert.serial_number), subject=cert.subject.rfc4514_string(),
                                   source='manual', valid_to=cert.not_valid_after_utc.replace(tzinfo=None), **row))
        db.session.commit()
    return cert


@pytest.mark.parametrize('label,sid,days,row', [
    ('none', None, 30, {}),
    ('revoked', ACCOUNTS['carol'][0], 30, {'revoked': True, 'revoke_reason': 'superseded'}),
    ('expired', ACCOUNTS['carol'][0], -1, {}),
    ('archived', ACCOUNTS['carol'][0], 30, {'archived': True}),
], ids=['no-sid-extension', 'revoked', 'expired', 'superseded'])
def test_any_certificate_of_the_ca_carrying_the_subject_refuses(app, pattern_ca, accounts, label, sid, days, row):
    ca_id, _ids = pattern_ca(f'CN unique held CA {label}', user='{displayName}')
    held = _hold(app, ca_id, 'JOHN SMITH', sid=sid, days=days, **row)
    cert, err = _issue(app, ca_id, 'alice')
    assert cert is None
    assert err.audited.endswith(f'(serial {held.serial_number})')


def test_a_certificate_of_another_ca_does_not_count(app, pattern_ca, accounts):
    other_id, _ = pattern_ca('CN unique other CA')
    _hold(app, other_id, 'John Smith')
    ca_id, _ids = pattern_ca('CN unique this CA', user='{displayName}')
    cert, err = _issue(app, ca_id, 'alice')
    assert err is None and cert.subject.rfc4514_string() == 'CN=John Smith', err


def test_a_template_without_a_pattern_runs_no_more_query(app, pattern_ca, accounts):
    """The patterned issuance runs the plain one's statements and one lookup by subject key."""
    statements = []

    def record(conn, cursor, statement, *args):
        statements.append(statement)
    plain_id, _ = pattern_ca('CN unique plain CA')
    patterned_id, _ = pattern_ca('CN unique counted CA', user='{username}')
    counts = []
    with app.app_context():
        engine = db.engine
    for ca_id in (plain_id, patterned_id):
        statements.clear()
        event.listen(engine, 'before_cursor_execute', record)
        try:
            _cert, err = _issue(app, ca_id, 'alice')
        finally:
            event.remove(engine, 'before_cursor_execute', record)
        assert err is None, err
        lookups = [s for s in statements if re.search(r'WHERE.*subject_key\s*=', s, re.S)]
        counts.append((len(statements), len(lookups)))
    (plain, plain_lookups), (patterned, patterned_lookups) = counts
    assert (plain_lookups, patterned_lookups, patterned - plain) == (0, 1, 1)


def test_two_accounts_at_once_get_one_certificate(app, pattern_ca, accounts, monkeypatch):
    """PostgreSQL: the second waits on the CA row the first holds, then finds its certificate."""
    from services.ca import ca_signing
    from tests.test_revocation_record_rule import _on_postgresql
    if not _on_postgresql(app):
        pytest.skip('row locks are PostgreSQL behaviour; SQLite holds its write lock from the flush')
    ca_id, _ids = pattern_ca('CN unique race CA', user='{displayName}')
    with app.app_context():
        engine = db.engine
    paused, release, outcome = threading.Event(), threading.Event(), {}
    bump = ca_signing.next_ca_serial

    def hold_after_the_lock(ca):
        count = bump(ca)
        if threading.current_thread().name == 'first':
            paused.set()
            release.wait(30)
        return count
    monkeypatch.setattr(ca_signing, 'next_ca_serial', hold_after_the_lock)

    def request(sam):
        try:
            outcome[sam] = _issue(app, ca_id, sam)
        except Exception as e:  # noqa: BLE001
            outcome[sam] = (None, repr(e))
        finally:
            paused.set()

    def release_once_the_second_waits():
        with engine.connect() as conn:
            outcome['waited'] = _wait_for_a_lock_waiter(conn, 10)
        release.set()

    first = threading.Thread(target=request, args=('alice',), name='first')
    first.start()
    assert paused.wait(30)
    releaser = threading.Thread(target=release_once_the_second_waits)
    second = threading.Thread(target=request, args=('carol',), name='second')
    releaser.start()
    second.start()
    for thread in (first, second, releaser):
        thread.join(60)
    assert outcome['waited'], outcome
    assert outcome['alice'][1] is None, outcome
    _refused(outcome['carol'][1], 'CN unique race CA user', 'CN=John Smith')
    with app.app_context():
        assert Certificate.query.filter_by(caref=db.session.get(CA, ca_id).refid).count() == 1
