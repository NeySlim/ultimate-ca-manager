"""After a change of a Windows enrollment profile's CA, a certificate of the former CA renews on the
Certificate binding as on the Kerberos binding, under the profile's explicit list of former CAs
(SQLite, and PostgreSQL with UCM_TEST_APP_PG_URL).

The list is fed by the change of CA (audited) and only shrinks by the operator; a removal or a
revocation of the former CA closes its renewals at once, on both bindings. The TLS listener trusts a
listed former CA, and a certificate trusted on it alone reaches no route but WSTEP renewal."""
import json
import os
import uuid

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509.oid import NameOID

from models import CA, CATemplatePin, Certificate, ClusterCommand, SystemConfig, db
from services.trust_store.csr_operations_mixin import ad_security_extension_sid
from services.wstep import CES_CERTIFICATE_PATH
from tests.test_windows_profile_renewal import directory  # noqa: F401
from tests.test_windows_profile_routing import SID, _audits, _fault, _profile, _top_audit, world  # noqa: F401
from tests.test_wstep_kerberos_issue import _issued_cert_from_rstr
from tests.test_wstep_kerberos_no_template import MACHINE, realm_a  # noqa: F401
from tests.test_wstep_kerberos_renewal_replaces import (_archived, _certificate_renewal, _count,
                                                        _issuer_cn, _kerberos_renewal, _key, _old,
                                                        _same_names_csr)
from tests.test_wstep_renew_tls import _cmc_renewal, _rst
from tests.windows_profile_support import restore, set_config, snapshot
from tests.windows_profile_support import windows_profiles_restored  # noqa: F401

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')
URL = '/api/v2/windows-profiles'
NOT_RECOGNIZED = 'Signing certificate is not recognized'


@pytest.fixture
def restarts(monkeypatch):
    """The local restarts a save asks for; never a real one."""
    asked = []
    monkeypatch.setattr('config.settings.restart_ucm_service', lambda: asked.append(1) or (True, 'restarting'))
    monkeypatch.setattr('config.settings.is_docker', lambda: False)
    return asked


@pytest.fixture
def mtls_on_a2(app):
    """mTLS on, anchored on the CA the profile moves to (A2, created by ``moved_by_api``)."""
    with app.app_context():
        saved = snapshot(('mtls_enabled', 'mtls_trusted_ca_id'))
    holder = {}

    def anchor(refid):
        with app.app_context():
            set_config('mtls_enabled', 'true', commit=False)
            set_config('mtls_trusted_ca_id', refid)
        holder['refid'] = refid
    yield anchor
    with app.app_context():
        restore(saved)


@pytest.fixture
def listener(app):
    """Writes what gunicorn_config records at start: the former CAs its listener trusts."""
    from config.settings import DATA_DIR
    from utils.client_cert import FORMER_CAS_FILE
    path = os.path.join(str(DATA_DIR), FORMER_CAS_FILE)

    def trusts(*refids):
        with open(path, 'w') as handle:
            json.dump(sorted(refids), handle)
    yield trusts
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


@pytest.fixture
def moved_by_api(app, auth_client, world, create_ca, restarts, mtls_on_a2):
    """Profile c04-a moved from CA A to a new CA A2 (same templates) through the profiles API,
    mTLS anchored on A2: the response, and A2."""
    a2 = create_ca(cn='C20 A2 CA')
    mtls_on_a2(a2['refid'])
    with app.app_context():
        for pin in CATemplatePin.query.filter_by(ca_id=world['cas']['A']['id']).all():
            db.session.add(CATemplatePin(ca_id=a2['id'], template_id=pin.template_id))
        db.session.commit()
        profile_id = _profile('c04-a').id
    r = auth_client.put(f'{URL}/{profile_id}', json={'issuing_ca_refid': a2['refid']})
    assert r.status_code == 200, r.get_json()
    yield r.get_json()['data'], a2, profile_id
    with app.app_context():
        profile = _profile('c04-a')
        profile.issuing_ca_refid, profile.renewal_ca_refids = world['cas']['A']['refid'], '[]'
        CATemplatePin.query.filter_by(ca_id=a2['id']).delete()
        db.session.commit()


def _tls_renewal(client, old, key, peer=None):
    """As Windows renews on the Certificate binding: no XML-DSig, the TLS client certificate
    (*peer*, by default the renewed one) authenticates, the renewed key signs the CMC."""
    body = _rst(_cmc_renewal(_same_names_csr(old, key), [(key, old)]))
    peercert = (peer or old).public_bytes(serialization.Encoding.DER)
    return client.post(CES_CERTIFICATE_PATH, data=body, environ_base={'peercert': peercert},
                       headers={'Content-Type': 'application/soap+xml; charset=utf-8'})


def _renew_by(binding, client, world, realm_a, old, key):
    if binding == 'tls':
        return _tls_renewal(client, old, key)
    if binding == 'xml-dsig':
        return _certificate_renewal(client, old, key)
    return _kerberos_renewal(client, world, realm_a, old, key, True)


def _remove_former(auth_client, profile_id, refids=()):
    r = auth_client.put(f'{URL}/{profile_id}', json={'renewal_ca_refids': list(refids)})
    assert r.status_code == 200, r.get_json()
    return r.get_json()['data']


# --- The list: fed by the change of CA, shrunk by the operator only ---------------------------------

def test_a_change_of_ca_lists_the_outgoing_ca_audits_it_and_reloads_the_listener(
        app, world, moved_by_api, restarts):
    data, _a2, profile_id = moved_by_api
    assert data['renewal_cas'] == [{'refid': world['cas']['A']['refid'], 'name': 'C04 A CA'}]
    # mTLS is anchored on A2: the listener must add A, so the save asks for the restart
    assert data['needs_restart'] is True and restarts == [1]
    with app.app_context():
        from models import AuditLog
        entry = AuditLog.query.filter_by(action='windows_profile_update', resource_id=str(profile_id)) \
            .order_by(AuditLog.id.desc()).first()
        assert 'former CA listed for renewal: C04 A CA' in entry.details


def test_the_operator_removes_a_former_ca_and_cannot_list_another(app, auth_client, world, moved_by_api,
                                                                    restarts):
    _data, a2, profile_id = moved_by_api
    floor = _top_audit(app)
    # B was never this profile's CA, A2 is its current one: neither may be listed
    for refid in (world['cas']['B']['refid'], a2['refid']):
        r = auth_client.put(f'{URL}/{profile_id}', json={'renewal_ca_refids': [world['cas']['A']['refid'], refid]})
        assert r.status_code == 400 and 'may only remove' in r.get_json()['message']
    data = _remove_former(auth_client, profile_id)
    assert data['renewal_cas'] == [] and restarts == [1, 1]
    (entry,) = [a for a in _audits(app, floor) if a[0] == 'windows_profile_update']
    assert 'former CA removed from renewal: C04 A CA' in entry[3]


def test_moving_back_to_the_former_ca_takes_it_off_the_list(app, auth_client, world, moved_by_api):
    _data, a2, profile_id = moved_by_api
    r = auth_client.put(f'{URL}/{profile_id}', json={'issuing_ca_refid': world['cas']['A']['refid']})
    assert r.get_json()['data']['renewal_cas'] == [{'refid': a2['refid'], 'name': 'C20 A2 CA'}]


def test_in_ha_the_rolling_restart_is_committed_with_the_list(app, auth_client, moved_by_api, restarts,
                                                              monkeypatch):
    _data, _a2, profile_id = moved_by_api
    monkeypatch.setattr('utils.ha.ha_enabled', lambda: True)
    with app.app_context():
        last = db.session.query(db.func.max(ClusterCommand.id)).scalar() or 0
    data = _remove_former(auth_client, profile_id)
    from services.cluster_commands import RESTART, ROLLING_RESTART_MESSAGE
    assert data['restart_message'] == ROLLING_RESTART_MESSAGE and restarts == [1]
    with app.app_context():
        assert [c.kind for c in ClusterCommand.query.filter(ClusterCommand.id > last)] == [RESTART]


def test_a_save_that_leaves_the_listener_as_it_is_asks_for_no_restart(app, auth_client, moved_by_api, restarts):
    _data, _a2, profile_id = moved_by_api
    r = auth_client.put(f'{URL}/{profile_id}', json={'validity_days': 40})
    assert r.get_json()['data']['needs_restart'] is False and restarts == [1]


def test_the_list_filter_finds_a_profile_by_its_former_ca(auth_client, world, moved_by_api):
    r = auth_client.get(f"{URL}?ca={world['cas']['A']['refid']}")
    assert 'c04-a' in [p['name'] for p in r.get_json()['data']]


# --- Invariant 1: symmetry --------------------------------------------------------------------------

@pytest.mark.parametrize('binding', ['tls', 'xml-dsig', 'kerberos'])
def test_a_former_ca_s_certificate_renews_on_either_binding(
        app, client, world, realm_a, directory, request, listener, binding):
    """Signed by the profile's current CA, the old one archived, audited as a renewal naming the old CA;
    the SID it carries is carried over, checked under the CA that signed it."""
    old, key = _old(app, client, world, realm_a, True)
    moved = request.getfixturevalue('moved_by_api')
    listener(world['cas']['A']['refid'])
    floor = _top_audit(app)
    r = _renew_by(binding, client, world, realm_a, old, key)
    assert r.status_code == 200, r.data
    new = _issued_cert_from_rstr(r.data)
    assert _issuer_cn(new) == 'C20 A2 CA' and _issuer_cn(old) == 'C04 A CA'
    assert ad_security_extension_sid(new) == SID
    assert _archived(app, old) == [True]
    (action, _u, _n, details, ok), = [a for a in _audits(app, floor) if a[0].startswith('certificate.')]
    assert (action, ok) == ('certificate.renewed', True)
    assert f'old serial {old.serial_number}' in details and 'old CA C04 A CA' in details


# --- Invariant 2: nothing beyond what UCM issued under this profile ---------------------------------

def _make(app, world, kind, old):
    """The state each refusal starts from."""
    with app.app_context():
        row = Certificate.query.filter_by(serial_number=str(old.serial_number)).one()
        if kind == 'revoked':
            row.revoked = True
        elif kind == 'expired':
            from datetime import datetime, timedelta
            row.valid_to = datetime.utcnow() - timedelta(days=1)
        elif kind == 'other-profile':
            row.windows_profile_id = _profile('c04-b').id
        elif kind == 'unknown':
            # Chained to A, byte for byte the certificate A signed, but no longer on record
            db.session.delete(row)
        db.session.commit()


REFUSED = {'revoked': b'revoked', 'expired': b'expired', 'unknown': NOT_RECOGNIZED.encode()}


@pytest.mark.parametrize('binding', ['tls', 'kerberos'])
@pytest.mark.parametrize('kind', ['revoked', 'expired', 'other-profile', 'unknown'])
def test_no_other_certificate_of_the_former_ca_renews(
        app, client, world, realm_a, directory, request, listener, binding, kind):
    """Revoked, expired, recorded under another profile, or unknown to the database: refused on the
    Certificate binding; on Kerberos a request naming the template is an enrollment, nothing archived."""
    old, key = _old(app, client, world, realm_a, True)
    moved = request.getfixturevalue('moved_by_api')
    listener(world['cas']['A']['refid'])
    _make(app, world, kind, old)
    floor = _top_audit(app)
    r = _renew_by(binding, client, world, realm_a, old, key)
    if binding == 'tls':
        assert r.status_code == 400, r.data
        if kind in REFUSED:
            assert REFUSED[kind] in r.data, r.data
        else:
            # Its profile c04-b serves under B, which never listed A, and the listener anchors on A2
            assert b'renew over the Kerberos binding' in r.data, r.data
    else:
        assert r.status_code == 200, r.data
        (action, _u, _n, details, _ok), = [a for a in _audits(app, floor) if a[0].startswith('certificate.')]
        assert action == 'certificate.issued' and str(old.serial_number) not in details
    if kind != 'unknown':
        assert not any(_archived(app, old))


def test_a_certificate_of_another_subject_does_not_renew_on_the_certificate_binding(
        app, client, world, realm_a, directory, request, listener):
    old, key = _old(app, client, world, realm_a, True)
    moved = request.getfixturevalue('moved_by_api')
    listener(world['cas']['A']['refid'])
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'other.c04a.test')]))
           .sign(key, hashes.SHA256()))
    r = client.post(CES_CERTIFICATE_PATH, data=_rst(_cmc_renewal(csr, [(key, old)])),
                    environ_base={'peercert': old.public_bytes(serialization.Encoding.DER)},
                    headers={'Content-Type': 'application/soap+xml; charset=utf-8'})
    assert r.status_code == 400 and b'CSR subject does not match' in r.data
    assert _archived(app, old) == [False]


@pytest.mark.parametrize('binding', ['tls', 'kerberos'])
def test_a_certificate_of_a_ca_that_never_was_the_profile_s_renews_nothing(
        app, client, world, realm_a, directory, request, listener, binding):
    """Recorded under c04-a but signed by B, a CA of UCM that never was c04-a's: not on the list,
    even when the listener trusts it."""
    key = _key()
    with app.app_context():
        from services.ca_service import CAService
        from tests.test_wstep_kerberos_no_template import SERVER_AUTH, _csr
        pem, _s = CAService.sign_csr_from_crypto(
            ca=db.session.get(CA, world['cas']['B']['id']), csr=_csr('hosta.c04a.test', ekus=[SERVER_AUTH], key=key),
            validity_days=30, source='wstep', requester_sid=SID, windows_profile_id=_profile('c04-a').id)
    old = x509.load_pem_x509_certificate(pem.encode())
    request.getfixturevalue('moved_by_api')
    listener(world['cas']['A']['refid'], world['cas']['B']['refid'])
    r = (_tls_renewal(client, old, key) if binding == 'tls'
         else _kerberos_renewal(client, world, realm_a, old, key, False))
    assert r.status_code == 400, r.data
    assert _archived(app, old) == [False]


# --- Invariant 3: the operator cuts at once; a revoked former CA renews nothing --------------------

@pytest.mark.parametrize('binding', ['tls', 'xml-dsig', 'kerberos'])
@pytest.mark.parametrize('cut', ['removed', 'ca-revoked', 'ca-deleted'])
def test_a_cut_closes_the_former_ca_s_renewals_at_once(
        app, client, auth_client, world, realm_a, directory, request, listener, binding, cut):
    old, key = _old(app, client, world, realm_a, True)
    moved = request.getfixturevalue('moved_by_api')
    _data, _a2, profile_id = moved
    # The listener still trusts A until its restart: the refusal is the application's own
    listener(world['cas']['A']['refid'])
    if cut == 'removed':
        _remove_former(auth_client, profile_id)
    elif cut == 'ca-revoked':
        with app.app_context():
            db.session.get(CA, world['cas']['A']['id']).revoked = True
            db.session.commit()
    else:
        with app.app_context():
            # A deleted CA: its record gone, its refid left on the list
            ca = db.session.get(CA, world['cas']['A']['id'])
            ca.refid, keep = str(uuid.uuid4()), ca.refid
            db.session.commit()
    try:
        floor = _top_audit(app)
        r = _renew_by(binding, client, world, realm_a, old, key)
        if binding == 'kerberos':
            # The machine's Kerberos right to enroll stays; the renewal is gone
            assert r.status_code == 200, r.data
            (action, _u, _n, details, _ok), = [a for a in _audits(app, floor) if a[0].startswith('certificate.')]
            assert action == 'certificate.issued' and 'old CA' not in details
        else:
            assert r.status_code == 400, r.data
            expected = b'is revoked' if cut == 'ca-revoked' else NOT_RECOGNIZED.encode()
            assert expected in r.data, r.data
        assert not any(_archived(app, old))
    finally:
        with app.app_context():
            ca = db.session.get(CA, world['cas']['A']['id'])
            ca.revoked = False
            if cut == 'ca-deleted':
                ca.refid = keep
            db.session.commit()


# --- Invariant 4: the listener trusts a former CA for WSTEP renewal only ----------------------------

def _peer_hook(app, cert):
    """``environ`` as every route sees it once the hooks have run, for a native client certificate."""
    der = cert.public_bytes(serialization.Encoding.DER)
    with app.test_request_context('/api/v2/auth/login/mtls', method='POST', environ_base={'peercert': der}):
        app.preprocess_request()
        from flask import request
        from utils.client_cert import FORMER_PEERCERT, trusted_client_cert
        import logging
        log = logging.getLogger('test')
        return (bool(request.environ.get('peercert')), bool(request.environ.get(FORMER_PEERCERT)),
                trusted_client_cert(log, 'EST') is not None, trusted_client_cert(log, 'WSTEP', former_ca=True)
                is not None)


def test_a_certificate_trusted_on_a_former_ca_alone_reaches_wstep_renewal_only(
        app, client, world, realm_a, directory, request, listener):
    old, _key_old = _old(app, client, world, realm_a, True)
    moved = request.getfixturevalue('moved_by_api')
    listener(world['cas']['A']['refid'])
    # A's certificate: out of every route's reach (login, EST, ...) but WSTEP renewal's
    assert _peer_hook(app, old) == (False, True, False, True)
    # A certificate of A2, the mTLS anchor: seen by every route as before
    new = _issued_cert_from_rstr(_kerberos_renewal(client, world, realm_a, old, _key_old, True).data)
    assert _issuer_cn(new) == 'C20 A2 CA'
    assert _peer_hook(app, new) == (True, False, True, True)


def test_a_former_ca_s_certificate_opens_no_session(app, client, world, realm_a, directory, request,
                                                     listener, monkeypatch):
    """Login by certificate never sees it, whatever an enrolment would say."""
    from services.mtls_auth_service import MTLSAuthService
    seen = []
    monkeypatch.setattr(MTLSAuthService, 'authenticate_certificate',
                        staticmethod(lambda info: seen.append(info) or (None, None, 'Certificate not enrolled')))
    old, _k = _old(app, client, world, realm_a, True)
    moved = request.getfixturevalue('moved_by_api')
    der = old.public_bytes(serialization.Encoding.DER)
    listener(world['cas']['A']['refid'])
    client.post('/api/v2/auth/login/mtls', environ_base={'peercert': der})
    assert seen == []
    # Control: a listener that does not trust A was never handed this certificate by TLS; a test
    # client that injects it reaches the login, which is what the hook prevents above
    listener()
    client.post('/api/v2/auth/login/mtls', environ_base={'peercert': der})
    assert seen


def test_the_listener_rule_lists_a_former_ca_only_while_it_may_renew(app, auth_client, world, moved_by_api):
    from services.windows_profiles import listener_former_refids
    _data, _a2, profile_id = moved_by_api
    with app.app_context():
        assert listener_former_refids() == [world['cas']['A']['refid']]
        db.session.get(CA, world['cas']['A']['id']).revoked = True
        db.session.commit()
        try:
            assert listener_former_refids() == []
        finally:
            db.session.get(CA, world['cas']['A']['id']).revoked = False
            db.session.commit()
        SystemConfig.query.filter_by(key='mtls_enabled').one().value = 'false'
        db.session.commit()
        assert listener_former_refids() == []


# --- Invariant 5: a profile whose CA never changed is as before --------------------------------------

def test_a_profile_that_never_moved_lists_nothing_and_renews_as_before(
        app, client, auth_client, world, realm_a, directory):
    with app.app_context():
        profile_id = _profile('c04-b').id
    data = auth_client.get(f'{URL}/{profile_id}').get_json()['data']
    assert data['renewal_cas'] == []
    old, key = _old(app, client, world, realm_a, True)
    r = _kerberos_renewal(client, world, realm_a, old, key, True)
    assert r.status_code == 200 and _archived(app, old) == [True]
    assert _count(app) > 0
