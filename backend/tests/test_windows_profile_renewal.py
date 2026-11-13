"""Renewal by certificate routed by the profile recorded on the certificate (SQLite, and PostgreSQL
with UCM_TEST_APP_PG_URL): every WSTEP issuance records its profile, the Certificate binding
renews under that profile alone, rechecks the SID with that profile's connector, and refuses a
certificate whose profile is gone or disabled, with an audit entry naming profile and reason."""
import json
from contextlib import contextmanager

import pytest
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import rsa

from models import ADConnectorConfig, AuditLog, Certificate, WindowsEnrollmentProfile, db
from models.policy import ApprovalRequest
from services.ad_connector import lookup as ad_lookup
from services.wstep import CES_CERTIFICATE_PATH, CES_KERBEROS_PATH, CES_USERNAME_PASSWORD_PATH
from tests.protocol_approval_support import approve, requests_of
from tests.test_protocol_approval_wstep import _query_rst
from tests.test_windows_profile_routing import (  # noqa: F401
    NEGOTIATE, _csr, _fault, _profile, held_on_b, world,
)
from tests.test_wstep_issue import WSTEP_PASSWORD, WSTEP_USER, _basic_auth
from tests.test_wstep_kerberos_issue import _build_rst, _issued_cert_from_rstr
from tests.test_wstep_renew import _build_signed_rst
from tests.test_wstep_renew_tls import _cmc_renewal, _post, _renewal_csr, _rst
from tests.windows_profile_support import default_profile, restore, set_config, snapshot
from tests.windows_profile_support import windows_profiles_restored  # noqa: F401

# KB5014754 SID security extension
SID_EXTENSION = '1.3.6.1.4.1.311.25.2'
pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')


@pytest.fixture
def directory(world, monkeypatch):
    """The SID lookups of renewals recorded as (connector id, 'account') in ``world['asked']``."""
    monkeypatch.setattr(ad_lookup, 'lookup_account_by_sid', lambda config, sid: world['asked'].append(
        (config.id, 'account')) or 'someone')
    return world


def _key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _enrolled(client, state, principal, cn):
    """A certificate issued over the Kerberos binding to *principal*, and its key."""
    key = _key()
    state['principal'] = principal
    r = client.post(CES_KERBEROS_PATH, data=_build_rst(_csr(cn, key)), headers=NEGOTIATE)
    assert r.status_code == 200, r.data
    state['asked'].clear()
    return _issued_cert_from_rstr(r.data), key


def _row(cert):
    return Certificate.query.filter_by(serial_number=str(cert.serial_number)).one()


def _profile_id(app, cert):
    with app.app_context():
        return _row(cert).windows_profile_id


def _renew_xml(client, cert, key):
    return client.post(CES_CERTIFICATE_PATH, data=_build_signed_rst(cert, key, _renewal_csr(cert, key)),
                       headers={'Content-Type': 'application/soap+xml; charset=utf-8'})


def _renew_tls(client, cert, key):
    return _post(client, _rst(_cmc_renewal(_renewal_csr(cert, key), [(key, cert)])), tls_cert=cert)


def _top_audit(app):
    with app.app_context():
        return db.session.query(db.func.max(AuditLog.id)).scalar() or 0


def _refusals(app, floor):
    with app.app_context():
        return [(a.username, a.details) for a in AuditLog.query.filter(
            AuditLog.id > floor, AuditLog.action == 'certificate.renewed',
            AuditLog.success.is_(False)).order_by(AuditLog.id)]


def _signed(app, ca_id, cn, source='wstep'):
    """A certificate signed directly, without SID, as with the connector off."""
    from models import CA
    from services.ca_service import CAService
    key = _key()
    with app.app_context():
        pem, _serial = CAService.sign_csr_from_crypto(ca=db.session.get(CA, ca_id), csr=_csr(cn, key),
                                                      validity_days=30, source=source)
    return x509.load_pem_x509_certificate(pem.encode()), key


def _profile_id_named(app, name):
    with app.app_context():
        return _profile(name).id


def _set_profile(app, cert, profile_id):
    with app.app_context():
        _row(cert).windows_profile_id = profile_id
        db.session.commit()


@contextmanager
def mtls_anchor(app, refid):
    """The mTLS trusted CA, the only anchor of the native TLS listener (A5)."""
    with app.app_context():
        saved = snapshot(('mtls_enabled', 'mtls_trusted_ca_id'))
        set_config('mtls_enabled', 'true', commit=False)
        set_config('mtls_trusted_ca_id', refid)
    try:
        yield
    finally:
        with app.app_context():
            restore(saved)


def test_a_certificate_of_a_renews_under_a_alone(app, client, directory):
    """Criterion 1: new certificate under A's CA, recorded on A, SID looked up with A's connector
    only, though B's connector claims the SID's domain."""
    world = directory
    with app.app_context():
        db.session.get(ADConnectorConfig, world['connectors']['B']).domain_sid = 'S-1-5-21-1-2-3'
        db.session.commit()
    old, key = _enrolled(client, world, 'usera@C04A.TEST', 'c05-a-host')
    with app.app_context():
        assert _row(old).windows_profile_id == _profile('c04-a').id
    r = _renew_xml(client, old, key)
    assert r.status_code == 200, r.data
    new = _issued_cert_from_rstr(r.data)
    with app.app_context():
        row = _row(new)
        assert row.caref == world['cas']['A']['refid']
        assert row.windows_profile_id == _profile('c04-a').id
    assert world['asked'] == [(world['connectors']['A'], 'account')]


def test_a_certificate_whose_row_says_a_is_never_handled_by_b(app, client, directory):
    """Criterion 2: two profiles on the same CA; the row decides which connector and profile."""
    world = directory
    with app.app_context():
        db.session.add(WindowsEnrollmentProfile(
            name='c04-a-twin', realm='C05TWIN.TEST', enabled=True, connector_id=world['connectors']['B'],
            issuing_ca_refid=world['cas']['A']['refid'], validity_days=30))
        db.session.commit()
        twin = _profile('c04-a-twin').id
    for profile_id, connector in ((None, 'A'), (twin, 'B')):
        old, key = _enrolled(client, world, 'usera@C04A.TEST', f'c05-twin-{connector}')
        if profile_id is not None:
            _set_profile(app, old, profile_id)
        r = _renew_xml(client, old, key)
        assert r.status_code == 200, r.data
        with app.app_context():
            expected = profile_id if profile_id is not None else _profile('c04-a').id
            assert _row(_issued_cert_from_rstr(r.data)).windows_profile_id == expected
        assert world['asked'] == [(world['connectors'][connector], 'account')]
        world['asked'].clear()


def test_an_inherited_wstep_certificate_renews_under_the_default(app, client, directory):
    """Criterion 3: no profile recorded on a ``wstep`` row (C-01 attaches it to the default)."""
    old, key = _signed(app, directory['cas']['S']['id'], 'c05-legacy')
    assert _profile_id(app, old) is None
    r = _renew_xml(client, old, key)
    assert r.status_code == 200, r.data
    with app.app_context():
        assert _row(_issued_cert_from_rstr(r.data)).windows_profile_id == default_profile().id


def test_a_certificate_issued_another_way_is_not_renewed_by_wstep(app, client, directory):
    """A row without profile nor ``wstep`` source belongs to no profile: refused and audited."""
    old, key = _signed(app, directory['cas']['S']['id'], 'c05-not-windows', source='manual')
    floor = _top_audit(app)
    r = _renew_xml(client, old, key)
    assert _fault(r)[0] == 400 and 'not issued through Windows enrollment' in _fault(r)[2]
    (_user, details), = _refusals(app, floor)
    assert f'old serial {old.serial_number}' in details and 'profile -' in details


@pytest.mark.parametrize('how', ['deleted', 'disabled'])
def test_a_certificate_of_a_gone_or_disabled_profile_is_refused_and_audited(app, client, directory, how):
    """Criteria 4 and 7: refused, audited with the profile and the reason, nothing issued."""
    world = directory
    old, key = _enrolled(client, world, 'usera@C04A.TEST', f'c05-{how}')
    with app.app_context():
        if how == 'deleted':
            # The profile row gone under a certificate that still names it
            _row(old).windows_profile_id = 10 ** 6
        else:
            _profile('c04-a').enabled = False
        db.session.commit()
        before = Certificate.query.count()
    floor = _top_audit(app)
    for renew in (_renew_xml, _renew_tls):
        r = renew(client, old, key)
        assert _fault(r)[0] == 400, r.data
    with app.app_context():
        assert Certificate.query.count() == before
    reason = ('The Windows enrollment profile of this certificate no longer exists' if how == 'deleted'
              else 'The Windows enrollment profile c04-a is disabled')
    profile = f'profile #{10 ** 6}' if how == 'deleted' else 'profile c04-a'
    rows = _refusals(app, floor)
    assert [user for user, _d in rows] == ['wstep-ws-security', 'wstep-client-cert']
    assert all(reason in d and profile in d and f'old serial {old.serial_number}' in d for _u, d in rows), rows
    assert world['asked'] == []


def test_tls_renewal_needs_the_profile_ca_under_the_mtls_anchor(app, client, directory):
    """Criterion 5 (A5): the TLS trust is not widened; a certificate of a profile whose CA is not
    the mTLS CA renews over TLS only behind a proxy, never natively; under the anchor, as in 2.x."""
    world = directory
    old, key = _enrolled(client, world, 'usera@C04A.TEST', 'c05-tls')
    floor = _top_audit(app)
    with mtls_anchor(app, world['cas']['S']['refid']):
        r = _renew_tls(client, old, key)
        assert _fault(r)[0] == 400 and 'mTLS trusted CA' in _fault(r)[2]
        assert 'Kerberos' in _fault(r)[2]
    (_user, details), = _refusals(app, floor)
    assert 'mTLS trusted CA' in details and 'profile c04-a' in details
    with mtls_anchor(app, world['cas']['A']['refid']):
        r = _renew_tls(client, old, key)
        assert r.status_code == 200, r.data
        with app.app_context():
            assert _row(_issued_cert_from_rstr(r.data)).windows_profile_id == _profile('c04-a').id


def test_a_root_mtls_anchor_admits_the_profile_ca_under_it(app, client, directory, create_ca):
    """The listener anchored on a root accepts its whole hierarchy: the route follows it."""
    from models import CA
    world = directory
    old, key = _enrolled(client, world, 'usera@C04A.TEST', 'c05-tls-root')
    root = create_ca(cn='C05 root anchor')
    with app.app_context():
        db.session.get(CA, world['cas']['A']['id']).caref = root['refid']
        db.session.commit()
    try:
        with mtls_anchor(app, root['refid']):
            assert _renew_tls(client, old, key).status_code == 200
    finally:
        # The CAs are deleted by id: A must not hang under the root made after it
        with app.app_context():
            db.session.get(CA, world['cas']['A']['id']).caref = None
            db.session.commit()


def test_a_certificate_without_sid_of_a_disabled_profile_is_refused(app, client, directory):
    """Criterion 6: issued with the connector off (no SID), on a profile sharing the default's CA;
    the default would renew it, its own profile disabled refuses it, enabled renews it."""
    world = directory
    with app.app_context():
        db.session.add(WindowsEnrollmentProfile(
            name='c04-s-nosid', realm='C05NOSID.TEST', enabled=True, connector_id=None,
            issuing_ca_refid=world['cas']['S']['refid'], validity_days=30))
        db.session.commit()
    old, key = _signed(app, world['cas']['S']['id'], 'c05-nosid')
    _set_profile(app, old, _profile_id_named(app, 'c04-s-nosid'))
    assert SID_EXTENSION not in {e.oid.dotted_string for e in old.extensions}
    with app.app_context():
        assert _row(old).windows_profile_id == _profile('c04-s-nosid').id
        _profile('c04-s-nosid').enabled = False
        db.session.commit()
    r = _renew_xml(client, old, key)
    assert _fault(r) == (400, 's:Sender', 'The Windows enrollment profile c04-s-nosid is disabled')
    with app.app_context():
        _profile('c04-s-nosid').enabled = True
        db.session.commit()
    r = _renew_xml(client, old, key)
    assert r.status_code == 200, r.data
    with app.app_context():
        assert _row(_issued_cert_from_rstr(r.data)).windows_profile_id == _profile('c04-s-nosid').id


def test_the_certificate_binding_serves_b_with_the_default_disabled(app, client, directory):
    """Report 9: the binding no longer depends on the default profile's state."""
    world = directory
    old, key = _enrolled(client, world, 'userb@C04B.TEST', 'c05-b-only')
    with app.app_context():
        default_profile().enabled = False
        db.session.commit()
    r = _renew_xml(client, old, key)
    assert r.status_code == 200, r.data
    with app.app_context():
        assert _row(_issued_cert_from_rstr(r.data)).caref == world['cas']['B']['refid']


def test_a_kerberos_renewal_takes_the_profile_of_the_realm(app, client, directory):
    """The Kerberos binding issues by realm (C-04): a certificate of A renewed by a principal of B
    comes back under B's CA and records B."""
    world = directory
    old, key = _enrolled(client, world, 'usera@C04A.TEST', 'c05-moved')
    world['principal'] = 'userb@C04B.TEST'
    new_key = _key()
    body = _rst(_cmc_renewal(_renewal_csr(old, new_key), [(new_key, None), (key, old)]))
    r = client.post(CES_KERBEROS_PATH, data=body, headers=NEGOTIATE)
    assert r.status_code == 200, r.data
    with app.app_context():
        row = _row(_issued_cert_from_rstr(r.data))
        assert (row.caref, row.windows_profile_id) == (world['cas']['B']['refid'], _profile('c04-b').id)


@pytest.fixture
def account(app, world):
    """The default profile's UsernamePassword account, on CA A (one template)."""
    from utils.password_hash import hash_password
    keys = ('wstep_username', 'wstep_password', 'wstep_ca_refid')
    with app.app_context():
        saved = snapshot(keys)
        set_config('wstep_username', WSTEP_USER, commit=False)
        set_config('wstep_password', hash_password(WSTEP_PASSWORD), commit=False)
        set_config('wstep_ca_refid', world['cas']['A']['refid'])
    yield
    with app.app_context():
        restore(saved)


def test_every_wstep_issuance_records_its_profile(app, client, auth_client, directory, account, held_on_b):
    """Criterion 8: Kerberos, UsernamePassword, Certificate and the deferred approval."""
    world = directory
    kerberos, key = _enrolled(client, world, 'usera@C04A.TEST', 'c05-k')
    r = client.post(CES_USERNAME_PASSWORD_PATH, data=_build_rst(_csr('c05-up')), headers=_basic_auth())
    password = _issued_cert_from_rstr(r.data)
    renewed = _issued_cert_from_rstr(_renew_xml(client, kerberos, key).data)
    world['principal'] = 'userb@C04B.TEST'
    assert b'Pending' in client.post(CES_KERBEROS_PATH, data=_build_rst(_csr('c05-held')), headers=NEGOTIATE).data
    (approval_id, *_), = requests_of(app, held_on_b, 'wstep_request')
    approve(auth_client, approval_id)
    (_id, _status, _data, cert_id), = requests_of(app, held_on_b, 'wstep_request')
    with app.app_context():
        a, b, default = _profile('c04-a').id, _profile('c04-b').id, default_profile().id
        recorded = {path: _row(c).windows_profile_id
                    for path, c in (('kerberos', kerberos), ('password', password), ('certificate', renewed))}
        recorded['approval'] = db.session.get(Certificate, cert_id).windows_profile_id
        assert recorded == {'kerberos': a, 'password': default, 'certificate': a, 'approval': b}


def _shift_ids(app, approval_id, profile_id, ca_id):
    """What a restore on another installation does to a held request: its surrogate ids name
    other rows, the names and refids it carries still name its own."""
    with app.app_context():
        row = db.session.get(ApprovalRequest, approval_id)
        data = json.loads(row.request_data)
        data.update(profile_id=profile_id, ca_id=ca_id)
        row.request_data = json.dumps(data)
        db.session.commit()


def test_a_held_request_restored_elsewhere_replays_its_profile_by_name(app, client, auth_client, directory,
                                                                        held_on_b):
    """Report 10: held on B; its ids now name A and A's CA; the query and the approval follow B."""
    world = directory
    world['principal'] = 'userb@C04B.TEST'
    assert b'Pending' in client.post(CES_KERBEROS_PATH, data=_build_rst(_csr('c05-restored')),
                                     headers=NEGOTIATE).data
    (approval_id, _status, data, _c), = requests_of(app, held_on_b, 'wstep_request')
    assert data['profile_name'] == 'c04-b' and data['ca_refid'] == world['cas']['B']['refid']
    with app.app_context():
        _shift_ids(app, approval_id, _profile('c04-a').id, world['cas']['A']['id'])
    r = client.post(CES_KERBEROS_PATH, data=_query_rst(approval_id), headers=NEGOTIATE)
    assert b'Pending' in r.data, r.data
    approve(auth_client, approval_id)
    (_id, _status, _data, cert_id), = requests_of(app, held_on_b, 'wstep_request')
    with app.app_context():
        row = db.session.get(Certificate, cert_id)
        assert (row.caref, row.windows_profile_id) == (world['cas']['B']['refid'], _profile('c04-b').id)


def test_a_held_request_whose_profile_name_is_unknown_is_refused_readably(app, client, auth_client, directory,
                                                                         held_on_b):
    world = directory
    world['principal'] = 'userb@C04B.TEST'
    client.post(CES_KERBEROS_PATH, data=_build_rst(_csr('c05-unknown')), headers=NEGOTIATE)
    (approval_id, *_), = requests_of(app, held_on_b, 'wstep_request')
    with app.app_context():
        row = db.session.get(ApprovalRequest, approval_id)
        data = json.loads(row.request_data)
        # Restored elsewhere: its name unknown, its id naming a profile of another realm
        data.update(profile_name='c05-elsewhere', profile_id=_profile('c04-a').id)
        row.request_data = json.dumps(data)
        db.session.commit()
    body = auth_client.post(f'/api/v2/approvals/{approval_id}/approve', json={'comment': 'ok'}).get_json()
    assert body['data']['issue_error'] == 'The Windows enrollment profile c05-elsewhere no longer exists'



@pytest.fixture
def held_on_a(app, world):
    from tests.protocol_approval_support import approval_policy
    with approval_policy(app, world['cas']['A']['id'], 'c05-held-on-a', operations=['renewal']) as policy_id:
        yield policy_id


def test_a_held_renewal_replayed_under_another_profile_is_refused(app, client, auth_client, directory, held_on_a):
    """A renewal held under the default (as before profiles were recorded on certificates) for a
    certificate of A is never signed under the default."""
    world = directory
    old, key = _enrolled(client, world, 'usera@C04A.TEST', 'c05-held-renew')
    assert b'Pending' in _renew_xml(client, old, key).data
    world['asked'].clear()
    (approval_id, _status, data, _c), = requests_of(app, held_on_a, 'wstep_request')
    assert data['profile_name'] == 'c04-a' and data['operation'] == 'renew'
    with app.app_context():
        row = db.session.get(ApprovalRequest, approval_id)
        row.request_data = json.dumps(dict(data, profile_name=default_profile().name,
                                           profile_id=default_profile().id))
        db.session.commit()
    body = auth_client.post(f'/api/v2/approvals/{approval_id}/approve', json={'comment': 'ok'}).get_json()
    assert 'belongs to another Windows enrollment profile' in body['data']['issue_error'], body
    assert world['asked'] == []


def test_a_certificate_stored_under_two_profiles_is_refused(app, client, directory):
    """A restored copy recording another profile: neither one is chosen."""
    world = directory
    old, key = _enrolled(client, world, 'usera@C04A.TEST', 'c05-twice')
    with app.app_context():
        original = _row(old)
        columns = {c.name: getattr(original, c.name) for c in Certificate.__table__.columns
                   if c.name not in ('id', 'refid')}
        columns.update(caref=world['cas']['B']['refid'], windows_profile_id=_profile('c04-b').id)
        db.session.add(Certificate(refid=f'{original.refid}-b', **columns))
        db.session.commit()
    r = _renew_xml(client, old, key)
    assert _fault(r) == (400, 's:Sender', 'The certificate is recorded under several Windows enrollment profiles')


@pytest.mark.parametrize('refid', [None, 'c05-gone-ca'])
def test_a_certificate_of_a_profile_without_issuing_ca_is_refused_and_audited(app, client, directory, refid):
    """Criterion 7: a profile with no issuing CA, or one that no longer resolves, refuses and audits."""
    world = directory
    old, key = _enrolled(client, world, 'usera@C04A.TEST', f'c05-no-ca-{refid}')
    with app.app_context():
        _profile('c04-a').issuing_ca_refid = refid
        db.session.commit()
    floor = _top_audit(app)
    r = _renew_xml(client, old, key)
    reason = 'The Windows enrollment profile c04-a has no issuing CA'
    assert _fault(r) == (503, 's:Receiver', reason)
    (_user, details), = _refusals(app, floor)
    assert reason in details and 'profile c04-a' in details and f'old serial {old.serial_number}' in details


@pytest.mark.parametrize('fallback_ca', ['A', 'S'])
def test_certificates_of_a_deleted_profile_stay_refused_under_the_default(app, client, auth_client, directory,
                                                                         fallback_ca):
    """Deleting a profile clears its id on its certificates, all revoked or expired: falling back to
    the default, on their own CA or another, never renews them."""
    from datetime import timedelta
    from utils.datetime_utils import utc_now
    world = directory
    with app.app_context():
        db.session.add(WindowsEnrollmentProfile(
            name='c04-deleted', realm='C05DEL.TEST', enabled=True, connector_id=None,
            issuing_ca_refid=world['cas']['A']['refid'], validity_days=30))
        db.session.commit()
        deleted_id = _profile('c04-deleted').id
    revoked, revoked_key = _enrolled(client, world, 'usera@C05DEL.TEST', f'c05-del-revoked-{fallback_ca}')
    expired, expired_key = _enrolled(client, world, 'usera@C05DEL.TEST', f'c05-del-expired-{fallback_ca}')
    with app.app_context():
        assert {_row(c).windows_profile_id for c in (revoked, expired)} == {deleted_id}
        row = _row(revoked)
        row.revoked, row.revoked_at, row.revoke_reason = True, utc_now(), 'superseded'
        _row(expired).valid_to = utc_now() - timedelta(days=1)
        saved = snapshot(('wstep_ca_refid',))
        set_config('wstep_ca_refid', world['cas'][fallback_ca]['refid'])
    try:
        assert auth_client.delete(f'/api/v2/windows-profiles/{deleted_id}').status_code == 200
        with app.app_context():
            assert {_row(c).windows_profile_id for c in (revoked, expired)} == {None}
            before = Certificate.query.count()
        reasons = {}
        for name, cert, key in (('revoked', revoked, revoked_key), ('expired', expired, expired_key)):
            r = _renew_xml(client, cert, key)
            assert _fault(r)[0] == 400, r.data
            reasons[name] = _fault(r)[2]
        with app.app_context():
            assert Certificate.query.count() == before
        if fallback_ca == 'A':
            assert reasons == {'revoked': 'Signing certificate has been revoked',
                               'expired': 'Signing certificate has expired'}
    finally:
        with app.app_context():
            restore(saved)


@pytest.mark.parametrize('anchor_record', ['root', 'cross'])
def test_an_mtls_anchor_stored_twice_admits_the_profile_ca_under_either(app, client, directory, create_ca,
                                                                       anchor_record):
    """A root stored as two records (same subject and key, as with a cross-certificate): the listener
    anchored on one accepts a CA issued under the other, so the route does too."""
    from models import CA
    world = directory
    old, key = _enrolled(client, world, 'usera@C04A.TEST', f'c05-tls-cross-{anchor_record}')
    root = create_ca(cn=f'C05 root stored twice {anchor_record}')
    with app.app_context():
        original = db.session.get(CA, root['id'])
        columns = {c.name: getattr(original, c.name) for c in CA.__table__.columns if c.name not in ('id', 'refid')}
        columns.update(descr=f'{original.descr} (cross)', prv=None)
        cross = CA(refid=f'{original.refid[:30]}-cross', **columns)
        db.session.add(cross)
        db.session.commit()
        refids = {'root': original.refid, 'cross': cross.refid}
        parent = refids['cross' if anchor_record == 'root' else 'root']
        db.session.get(CA, world['cas']['A']['id']).caref = parent
        db.session.commit()
    try:
        with mtls_anchor(app, refids[anchor_record]):
            r = _renew_tls(client, old, key)
            assert r.status_code == 200, r.data
    finally:
        with app.app_context():
            db.session.get(CA, world['cas']['A']['id']).caref = None
            db.session.commit()


def _held_on_b(app, client, world, held_on_b, cn):
    """A Kerberos enrolment of B held for approval: its RST body and the request's (id, data)."""
    world['principal'] = 'userb@C04B.TEST'
    body = _build_rst(_csr(cn))
    assert b'Pending' in client.post(CES_KERBEROS_PATH, data=body, headers=NEGOTIATE).data
    (approval_id, _status, data, _c), = requests_of(app, held_on_b, 'wstep_request')
    return body, approval_id, data


def test_a_held_request_is_found_again_under_another_ca_id(app, client, directory, held_on_b):
    """The reference of a held request names the CA by refid: the same request reaching the gate
    under the same CA restored with another id is the request already held, not a new one."""
    from types import SimpleNamespace
    from services.wstep.approval import make_gate
    world = directory
    _body, approval_id, data = _held_on_b(app, client, world, held_on_b, 'c05-ref-refid')
    csr = x509.load_pem_x509_csr(data['csr'].encode())
    restored = SimpleNamespace(id=10 ** 6, refid=world['cas']['B']['refid'])
    with app.app_context():
        gate = make_gate(restored, operation=data['operation'], profile=_profile('c04-b'),
                         identity=data['identity'], extra={'kerberos_principal': data['kerberos_principal']})
        held = gate(csr=csr, template=None, subject=csr.subject, san=None)
        assert held is not None and held.id == approval_id


def test_a_request_held_under_the_former_reference_is_still_recognised(app, client, directory, held_on_b):
    """A request held before the reference named the CA by refid carries the id form: the client
    sending it again gets it back, no second request opens."""
    from services import protocol_approval
    world = directory
    body, approval_id, data = _held_on_b(app, client, world, held_on_b, 'c05-ref-former')
    csr = x509.load_pem_x509_csr(data['csr'].encode())
    former = protocol_approval.make_ref('wstep', data['operation'], world['cas']['B']['id'], data['identity'],
                                        protocol_approval.csr_ref(csr))
    with app.app_context():
        row = db.session.get(ApprovalRequest, approval_id)
        row.request_data = json.dumps(dict(data, protocol_ref=former))
        db.session.commit()
    assert b'Pending' in client.post(CES_KERBEROS_PATH, data=body, headers=NEGOTIATE).data
    assert [r[0] for r in requests_of(app, held_on_b, 'wstep_request')] == [approval_id]


@pytest.mark.parametrize('recorded', ['realm', 'principal only'])
def test_a_held_request_follows_its_renamed_profile_by_id_and_realm(app, client, auth_client, directory,
                                                                    held_on_b, recorded):
    """The name no longer found, the recorded id serves when its profile has the request's realm
    (recorded with it, or that of the principal for a request held before)."""
    world = directory
    _body, approval_id, data = _held_on_b(app, client, world, held_on_b, f'c05-renamed-{recorded[0]}')
    assert data['profile_realm'] == 'C04B.TEST'
    with app.app_context():
        if recorded != 'realm':
            row = db.session.get(ApprovalRequest, approval_id)
            row.request_data = json.dumps({k: v for k, v in data.items() if k != 'profile_realm'})
        _profile('c04-b').name = 'c04-b-renamed'
        db.session.commit()
    approve(auth_client, approval_id)
    (_id, _status, _data, cert_id), = requests_of(app, held_on_b, 'wstep_request')
    with app.app_context():
        row = db.session.get(Certificate, cert_id)
        assert (row.caref, row.windows_profile_id) == (world['cas']['B']['refid'], _profile('c04-b-renamed').id)


def test_a_held_request_follows_its_renamed_profile_past_a_homonym(app, client, auth_client, directory,
                                                                  held_on_b):
    """The name taken by another profile after a rename names that other one: the recorded realm
    tells them apart, and the request is issued under the profile it was held for."""
    world = directory
    _body, approval_id, _data = _held_on_b(app, client, world, held_on_b, 'c05-homonym')
    with app.app_context():
        held_for = _profile('c04-b')
        held_for.name = 'c04-b-renamed'
        db.session.flush()
        db.session.add(WindowsEnrollmentProfile(name='c04-b', realm='C05HOMONYM.TEST', enabled=True,
                                                issuing_ca_refid=world['cas']['A']['refid']))
        db.session.commit()
    try:
        approve(auth_client, approval_id)
        (_id, _status, _data, cert_id), = requests_of(app, held_on_b, 'wstep_request')
        with app.app_context():
            row = db.session.get(Certificate, cert_id)
            assert (row.caref, row.windows_profile_id) == (world['cas']['B']['refid'],
                                                           _profile('c04-b-renamed').id)
    finally:
        with app.app_context():
            WindowsEnrollmentProfile.query.filter_by(realm='C05HOMONYM.TEST').delete()
            db.session.commit()


def test_a_former_reference_of_a_request_held_on_another_ca_is_not_this_request(app, client, directory,
                                                                               held_on_b):
    """The id form is recognised for the CA the request was held on only: an id a restore gave
    another CA opens a request of its own."""
    from services import protocol_approval
    world = directory
    body, approval_id, data = _held_on_b(app, client, world, held_on_b, 'c05-ref-other-ca')
    csr = x509.load_pem_x509_csr(data['csr'].encode())
    former = protocol_approval.make_ref('wstep', data['operation'], world['cas']['B']['id'], data['identity'],
                                        protocol_approval.csr_ref(csr))
    with app.app_context():
        row = db.session.get(ApprovalRequest, approval_id)
        row.request_data = json.dumps(dict(data, protocol_ref=former, ca_refid=world['cas']['A']['refid']))
        db.session.commit()
    assert b'Pending' in client.post(CES_KERBEROS_PATH, data=body, headers=NEGOTIATE).data
    assert len(requests_of(app, held_on_b, 'wstep_request')) == 2


def test_a_held_request_whose_renamed_profile_changed_realm_is_refused(app, client, auth_client, directory,
                                                                      held_on_b):
    world = directory
    _body, approval_id, _data = _held_on_b(app, client, world, held_on_b, 'c05-renamed-realm')
    with app.app_context():
        profile = _profile('c04-b')
        profile.name, profile.realm = 'c04-b-elsewhere', 'C05OTHER.TEST'
        db.session.commit()
    body = auth_client.post(f'/api/v2/approvals/{approval_id}/approve', json={'comment': 'ok'}).get_json()
    assert body['data']['issue_error'] == 'The Windows enrollment profile c04-b no longer exists'
