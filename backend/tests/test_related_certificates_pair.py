"""A hybrid pair (RFC 9763) through the API: issued together, B naming A,
revoked together unless asked otherwise, renewed together, exported together."""
import base64
import io
import json
import zipfile

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization

from models import CA, Certificate, db
from utils import key_algorithms, related_cert
from utils.datetime_utils import utc_now

pytestmark = pytest.mark.skipif(not key_algorithms.mldsa_supported(),
                                reason='this build has no ML-DSA')
pytestmark = (pytestmark if isinstance(pytestmark, list) else [pytestmark]) + [pytest.mark.usefixtures('drop_new_users')]

CLASSICAL = next(label for label in key_algorithms.labels('EC') if label.endswith('P256'))
PQ = next(label for label in key_algorithms.labels('ML-DSA') if label.endswith('65'))
HYBRID = {'classical': CLASSICAL, 'pq': PQ}


@pytest.fixture(scope='module', autouse=True)
def _certificates_made_here_go(app):
    """A sequential run shares one database, and listings read one page: the
    revoked pairs made here are deleted when the module ends."""
    with app.app_context():
        first = db.session.query(db.func.max(Certificate.id)).scalar() or 0
    yield
    from services.cert_service import CertificateService
    with app.app_context():
        for row_id in [r.id for r in Certificate.query.filter(Certificate.id > first).all()]:
            CertificateService.delete_certificate(row_id, username='test')


def _issue(auth_client, create_ca, cn, **extra):
    ca = create_ca(cn=f'Pair CA {cn}')
    body = {'cn': cn, 'ca_id': ca['id'], 'validity_days': 90, 'hybrid': HYBRID}
    body.update(extra)
    return auth_client.post('/api/v2/certificates', json=body), ca


def _pair(auth_client, create_ca, cn, **extra):
    r, _ca = _issue(auth_client, create_ca, cn, **extra)
    assert r.status_code == 201, r.data
    data = json.loads(r.data)['data']
    return data['certificate'], data['related']


def _x509(row_dict):
    return x509.load_pem_x509_certificate(row_dict['pem'].encode())


def _row(app, cert_id):
    with app.app_context():
        row = db.session.get(Certificate, cert_id)
        return row.to_dict()


# ---- issuance ---------------------------------------------------------------------

def test_the_pair_is_issued_a_first_and_b_names_a(app, auth_client, create_ca, monkeypatch):
    emitted = []
    import services.webhook_service as webhooks
    real = webhooks.emit_cert_issued
    monkeypatch.setattr(webhooks, 'emit_cert_issued',
                        lambda d, **kw: (emitted.append(d['id']), real(d, **kw)))
    a, b = _pair(auth_client, create_ca, 'pair-issue.example.com')
    cert_a, cert_b = _x509(a), _x509(b)
    assert key_algorithms.label_for_public_key(cert_a.public_key()) == CLASSICAL
    assert key_algorithms.label_for_public_key(cert_b.public_key()) == PQ
    assert (a['hybrid_role'], a['related_certificate_id']) == ('classical', b['id'])
    assert (b['hybrid_role'], b['related_certificate_id']) == ('pq', a['id'])
    # A exists before B: B carries A's hash, A carries no link, A's row comes first
    assert related_cert.references(cert_b, cert_a)
    assert related_cert.read_related_certificate(cert_a) is None
    assert a['id'] < b['id'] and emitted == [a['id'], b['id']]
    assert cert_b.subject == cert_a.subject
    assert cert_b.not_valid_after_utc == cert_a.not_valid_after_utc
    assert (cert_b.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
            == cert_a.extensions.get_extension_for_class(x509.SubjectAlternativeName).value)
    ext = cert_b.extensions.get_extension_for_oid(related_cert.RELATED_CERT_EXTENSION_OID)
    assert ext.critical is False
    assert not related_cert.usages_outside(
        cert_a, cert_b.extensions.get_extension_for_class(x509.KeyUsage).value,
        list(cert_b.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value))
    assert _row(app, a['id'])['related_certificate_id'] == b['id']


@pytest.mark.parametrize('hybrid,message', [
    ({'classical': PQ, 'pq': PQ}, 'hybrid.classical must name a classical'),
    ({'classical': CLASSICAL, 'pq': CLASSICAL}, 'hybrid.pq must name a post-quantum'),
    ({'classical': CLASSICAL, 'pq': 'ML-DSA-99'}, 'hybrid.pq names no key type'),
    ('EC-P256+ML-DSA-65', 'hybrid must be an object'),
])
def test_a_malformed_pair_is_refused(auth_client, create_ca, hybrid, message):
    r, _ca = _issue(auth_client, create_ca, 'pair-bad.example.com', hybrid=hybrid)
    assert r.status_code == 400, r.data
    assert message in json.loads(r.data)['message']


def test_nothing_is_stored_when_b_cannot_be_issued(app, auth_client, create_ca, monkeypatch):
    import utils.ct_client as ct_client
    real, calls = ct_client.apply_ct_policy, []

    def second_fails(cert, *args, **kwargs):
        calls.append(cert)
        if len(calls) == 2:
            raise ValueError('CT log refused B')
        return real(cert, *args, **kwargs)
    monkeypatch.setattr(ct_client, 'apply_ct_policy', second_fails)
    cn = 'pair-atomic.example.com'
    r, _ca = _issue(auth_client, create_ca, cn)
    assert r.status_code == 400 and b'CT log refused B' in r.data
    with app.app_context():
        assert Certificate.query.filter(Certificate.descr.like(f'{cn}%')).count() == 0


def test_the_pair_satisfies_a_profile_that_refuses_ml_dsa_alone(app, auth_client, create_ca):
    ca = create_ca(cn='Pair CA anssi', keyAlgo='EC', keySize='P-256')
    with app.app_context():
        row = db.session.get(CA, ca['id'])
        row.compliance_profile = 'anssi'
        db.session.commit()
    alone = auth_client.post('/api/v2/certificates', json={
        'cn': 'pq-alone.example.com', 'ca_id': ca['id'], 'validity_days': 90, 'key_type': PQ})
    assert alone.status_code == 400 and b'alone' in alone.data
    paired = auth_client.post('/api/v2/certificates', json={
        'cn': 'pq-paired.example.com', 'ca_id': ca['id'], 'validity_days': 90, 'hybrid': HYBRID})
    assert paired.status_code == 201, paired.data
    weak = auth_client.post('/api/v2/certificates', json={
        'cn': 'pq-weak.example.com', 'ca_id': ca['id'], 'validity_days': 90,
        'hybrid': {'classical': CLASSICAL, 'pq': 'ML-DSA-44'}})
    assert weak.status_code == 400 and b'ML-DSA-44 is not allowed' in weak.data, weak.data
    effective = json.loads(auth_client.get(f"/api/v2/policies/effective?ca_id={ca['id']}").data)['data']
    assert effective['pq_standalone'] is True and PQ in effective['allowed_key_types']


# ---- revocation (arbitrage 14 a: revoke_related, on by default) ---------------------

def _revoked(app, *ids):
    with app.app_context():
        db.session.expire_all()
        return [bool(db.session.get(Certificate, i).revoked) for i in ids]


def _login(app, create_user, role='operator'):
    user = create_user(role=role)
    client = app.test_client()
    r = client.post('/api/v2/auth/login', json={'username': user['username'], 'password': 'TestPass123!'})
    assert r.status_code == 200, r.data
    return client


def _approval_policy(app, ca_id, operations):
    from models.policy import CertificatePolicy
    with app.app_context():
        pol = CertificatePolicy(name=f'pair-{"-".join(operations)}-{ca_id}', ca_id=ca_id,
                                requires_approval=True, min_approvers=1, is_active=True, priority=100)
        pol.set_rules({})
        pol.set_operations(list(operations))
        db.session.add(pol)
        db.session.commit()
        return pol.id


def _drop_policy(app, pid):
    from models.policy import ApprovalRequest, CertificatePolicy
    with app.app_context():
        ApprovalRequest.query.filter_by(policy_id=pid).delete(synchronize_session=False)
        db.session.delete(db.session.get(CertificatePolicy, pid))
        db.session.commit()


def _pending(app, pid):
    from models.policy import ApprovalRequest
    with app.app_context():
        return ApprovalRequest.query.filter_by(policy_id=pid).count()


def _ca_id_of(app, cert_id):
    with app.app_context():
        return CA.query.filter_by(refid=db.session.get(Certificate, cert_id).caref).first().id


@pytest.mark.parametrize('member', ['certificate', 'related'])
def test_revoking_either_member_revokes_the_pair(app, auth_client, create_ca, member):
    a, b = _pair(auth_client, create_ca, f'pair-revoke-{member}.example.com')
    target, other = (a, b) if member == 'certificate' else (b, a)
    r = auth_client.post(f"/api/v2/certificates/{target['id']}/revoke", json={'reason': 'keyCompromise'})
    assert r.status_code == 200, r.data
    assert json.loads(r.data)['data']['related_revoked'] == other['id']
    assert _revoked(app, a['id'], b['id']) == [True, True]
    with app.app_context():
        assert db.session.get(Certificate, other['id']).revoke_reason == 'keyCompromise'


@pytest.mark.parametrize('route', ['single', 'bulk'])
def test_a_hold_made_final_is_made_final_on_the_pair(app, auth_client, create_ca, route):
    a, b = _pair(auth_client, create_ca, f'pair-hold-final-{route}.example.com')
    r = auth_client.post(f"/api/v2/certificates/{a['id']}/revoke", json={'reason': 'certificateHold'})
    assert r.status_code == 200, r.data
    if route == 'single':
        r = auth_client.post(f"/api/v2/certificates/{a['id']}/revoke", json={'reason': 'keyCompromise'})
        assert r.status_code == 200, r.data
        assert json.loads(r.data)['data']['related_revoked'] == b['id']
    else:
        r = auth_client.post('/api/v2/certificates/bulk/revoke',
                             json={'ids': [a['id']], 'reason': 'keyCompromise'})
        assert r.status_code == 200, r.data
        assert 'related_not_revoked' not in json.loads(r.data)['data'], r.data
    with app.app_context():
        assert [db.session.get(Certificate, i).revoke_reason for i in (a['id'], b['id'])] \
            == ['keyCompromise', 'keyCompromise']


@pytest.mark.parametrize('route', ['single', 'bulk'])
def test_a_partner_left_on_hold_is_said(app, auth_client, create_ca, monkeypatch, route):
    a, b = _pair(auth_client, create_ca, f'pair-hold-left-{route}.example.com')
    r = auth_client.post(f"/api/v2/certificates/{a['id']}/revoke", json={'reason': 'certificateHold'})
    assert r.status_code == 200, r.data
    _partner_revocation_fails(monkeypatch, b['id'])
    if route == 'single':
        r = auth_client.post(f"/api/v2/certificates/{a['id']}/revoke", json={'reason': 'keyCompromise'})
        assert json.loads(r.data)['data']['related_not_revoked'] == b['id'], r.data
    else:
        r = auth_client.post('/api/v2/certificates/bulk/revoke',
                             json={'ids': [a['id']], 'reason': 'keyCompromise'})
        assert json.loads(r.data)['data']['related_not_revoked'] == [b['id']], r.data
    with app.app_context():
        assert db.session.get(Certificate, b['id']).revoke_reason == 'certificateHold'


def test_revoke_related_false_keeps_the_other_member(app, auth_client, create_ca):
    a, b = _pair(auth_client, create_ca, 'pair-keep.example.com')
    r = auth_client.post(f"/api/v2/certificates/{b['id']}/revoke",
                         json={'reason': 'keyCompromise', 'revoke_related': False})
    assert r.status_code == 200, r.data
    assert 'related_revoked' not in json.loads(r.data)['data']
    assert _revoked(app, a['id'], b['id']) == [False, True]


def test_revoke_related_must_be_a_boolean(auth_client, create_ca):
    a, _b = _pair(auth_client, create_ca, 'pair-bool.example.com')
    r = auth_client.post(f"/api/v2/certificates/{a['id']}/revoke", json={'revoke_related': 'no'})
    assert r.status_code == 400


def test_bulk_revocation_counts_each_member_once(app, auth_client, create_ca):
    a, b = _pair(auth_client, create_ca, 'pair-bulk.example.com')
    r = auth_client.post('/api/v2/certificates/bulk/revoke', json={'ids': [a['id'], b['id']]})
    assert r.status_code == 200, r.data
    results = json.loads(r.data)['data']
    assert results['success'] == [a['id'], b['id']] and results['failed'] == []
    assert _revoked(app, a['id'], b['id']) == [True, True]


def test_bulk_revocation_may_keep_the_other_member(app, auth_client, create_ca):
    a, b = _pair(auth_client, create_ca, 'pair-bulk-keep.example.com')
    r = auth_client.post('/api/v2/certificates/bulk/revoke', json={'ids': [a['id']], 'revoke_related': False})
    assert r.status_code == 200, r.data
    assert _revoked(app, a['id'], b['id']) == [True, False]


def _partner_revocation_fails(monkeypatch, partner_id):
    from services.cert.mixins.lifecycle import LifecycleMixin
    real = LifecycleMixin.revoke_certificate

    def refusing(cert_id, *args, **kwargs):
        if cert_id == partner_id:
            raise RuntimeError('storage refused')
        return real(cert_id, *args, **kwargs)
    monkeypatch.setattr(LifecycleMixin, 'revoke_certificate', staticmethod(refusing))


def test_a_partner_left_unrevoked_is_said(app, auth_client, create_ca, monkeypatch):
    a, b = _pair(auth_client, create_ca, 'pair-revoke-partial.example.com')
    _partner_revocation_fails(monkeypatch, b['id'])
    r = auth_client.post(f"/api/v2/certificates/{a['id']}/revoke", json={'reason': 'keyCompromise'})
    assert _revoked(app, a['id'], b['id']) == [True, False]
    body = json.loads(r.data)
    assert body['data']['related_not_revoked'] == b['id'], r.data
    assert 'related_revoked' not in body['data']
    assert f"#{b['id']} was not revoked" in body['message']


def test_bulk_says_a_partner_left_unrevoked(app, auth_client, create_ca, monkeypatch):
    a, b = _pair(auth_client, create_ca, 'pair-bulk-partial.example.com')
    _partner_revocation_fails(monkeypatch, b['id'])
    r = auth_client.post('/api/v2/certificates/bulk/revoke', json={'ids': [a['id']]})
    assert r.status_code == 200, r.data
    results = json.loads(r.data)['data']
    assert results['success'] == [a['id']]
    assert results['related_not_revoked'] == [b['id']], r.data
    assert _revoked(app, a['id'], b['id']) == [True, False]


def test_an_approved_revocation_takes_the_pair(app, auth_client, create_ca, create_user):
    a, b = _pair(auth_client, create_ca, 'pair-approval.example.com')
    pid = _approval_policy(app, _ca_id_of(app, a['id']), ['revocation'])
    try:
        operator = _login(app, create_user)
        r = operator.post(f"/api/v2/certificates/{a['id']}/revoke",
                          json={'reason': 'keyCompromise', 'revoke_related': False})
        assert r.status_code == 400 and b'revoke_related' in r.data
        r = operator.post('/api/v2/certificates/bulk/revoke',
                          json={'ids': [a['id']], 'revoke_related': False})
        assert b'revoke_related' in r.data
        assert _pending(app, pid) == 0
        r = operator.post(f"/api/v2/certificates/{a['id']}/revoke", json={'reason': 'keyCompromise'})
        body = json.loads(r.data)['data']
        assert body['approval_required'], r.data
        r = auth_client.post(f"/api/v2/approvals/{body['approval_id']}/approve", json={'comment': 'ok'})
        assert r.status_code == 200, r.data
        assert _revoked(app, a['id'], b['id']) == [True, True]
    finally:
        _drop_policy(app, pid)


def test_a_pair_is_not_queued_for_issuance_approval(app, create_ca, create_user):
    ca = create_ca(cn='Pair CA approval')
    pid = _approval_policy(app, ca['id'], ['issuance'])
    try:
        operator = _login(app, create_user)
        r = operator.post('/api/v2/certificates', json={
            'cn': 'pair-queued.example.com', 'ca_id': ca['id'], 'validity_days': 90, 'hybrid': HYBRID})
        assert r.status_code == 400 and b'approval workflow' in r.data
        assert _pending(app, pid) == 0
    finally:
        _drop_policy(app, pid)


# ---- renewal ---------------------------------------------------------------------

def _state(app, *ids):
    """``[(serial, renewed_times, certificate)]`` of rows as stored now."""
    with app.app_context():
        db.session.expire_all()
        rows = [db.session.get(Certificate, i) for i in ids]
        return [(r.serial_number, r.renewed_times or 0,
                 x509.load_pem_x509_certificate(base64.b64decode(r.crt))) for r in rows]


@pytest.mark.parametrize('member', ['certificate', 'related'])
def test_renewing_either_member_renews_the_pair(app, auth_client, create_ca, member):
    a, b = _pair(auth_client, create_ca, f'pair-renew-{member}.example.com')
    target, other = (a, b) if member == 'certificate' else (b, a)
    r = auth_client.post(f"/api/v2/certificates/{target['id']}/renew", json={})
    assert r.status_code == 200, r.data
    assert json.loads(r.data)['data']['related_renewed'] == [other['id']]
    (serial_a, times_a, new_a), (serial_b, times_b, new_b) = _state(app, a['id'], b['id'])
    assert (times_a, times_b) == (1, 1)
    assert serial_a != a['serial_number'] and serial_b != b['serial_number']
    # B names A as renewed, not the A it was issued with
    assert related_cert.references(new_b, new_a)
    assert not related_cert.references(new_b, _x509(a))
    assert key_algorithms.label_for_public_key(new_b.public_key()) == PQ
    assert new_b.public_key() != _x509(b).public_key()  # rekeyed, same level


def test_bulk_renewal_renews_each_pair_once(app, auth_client, create_ca):
    a, b = _pair(auth_client, create_ca, 'pair-bulk-renew.example.com')
    r = auth_client.post('/api/v2/certificates/bulk/renew', json={'ids': [a['id'], b['id']]})
    assert r.status_code == 200, r.data
    results = json.loads(r.data)['data']
    assert results['success'] == [a['id'], b['id']] and results['failed'] == []
    (_sa, times_a, new_a), (_sb, times_b, new_b) = _state(app, a['id'], b['id'])
    assert (times_a, times_b) == (1, 1)
    assert related_cert.references(new_b, new_a)


def test_a_member_whose_partner_is_revoked_renews_alone_without_the_link(app, auth_client, create_ca):
    a, b = _pair(auth_client, create_ca, 'pair-renew-alone.example.com')
    r = auth_client.post(f"/api/v2/certificates/{a['id']}/revoke",
                         json={'reason': 'keyCompromise', 'revoke_related': False})
    assert r.status_code == 200, r.data
    r = auth_client.post(f"/api/v2/certificates/{b['id']}/renew", json={})
    assert r.status_code == 200, r.data
    (_sa, times_a, _ca), (_sb, times_b, new_b) = _state(app, a['id'], b['id'])
    assert (times_a, times_b) == (0, 1)
    assert related_cert.read_related_certificate(new_b) is None
    # The rows say what the certificates are: no pair left on either side
    for row in (_row(app, b['id']), _row(app, a['id'])):
        assert (row['related_certificate_id'], row['hybrid_role']) == (None, None), row['id']
    r = auth_client.get(f"/api/v2/certificates/{b['id']}/export?format=hybrid-bundle")
    assert r.status_code == 400, r.data


def test_the_bundle_refuses_members_that_no_longer_name_each_other(app, auth_client, create_ca):
    a, b = _pair(auth_client, create_ca, 'pair-export-broken.example.com')
    other, _ = _pair(auth_client, create_ca, 'pair-export-other.example.com')
    with app.app_context():
        # A stale link: B's certificate names A, not the row it is pointed at
        b_row, o_row = db.session.get(Certificate, b['id']), db.session.get(Certificate, other['id'])
        b_row.related_certificate_id, o_row.related_certificate_id = other['id'], b['id']
        db.session.commit()
    r = auth_client.get(f"/api/v2/certificates/{b['id']}/export?format=hybrid-bundle")
    assert r.status_code == 400 and b'no longer form a pair' in r.data, r.data


def test_an_approved_renewal_renews_the_pair(app, auth_client, create_ca, create_user):
    a, b = _pair(auth_client, create_ca, 'pair-renew-approval.example.com')
    pid = _approval_policy(app, _ca_id_of(app, a['id']), ['renewal'])
    try:
        operator = _login(app, create_user)
        r = operator.post(f"/api/v2/certificates/{b['id']}/renew", json={})
        body = json.loads(r.data)['data']
        assert body['approval_required'], r.data
        r = auth_client.post(f"/api/v2/approvals/{body['approval_id']}/approve", json={'comment': 'ok'})
        assert r.status_code == 200, r.data
        (_sa, times_a, new_a), (_sb, times_b, new_b) = _state(app, a['id'], b['id'])
        assert (times_a, times_b) == (1, 1)
        assert related_cert.references(new_b, new_a)
    finally:
        _drop_policy(app, pid)


def test_the_renewed_pair_still_satisfies_a_profile_that_refuses_ml_dsa_alone(
        app, auth_client, create_ca, monkeypatch):
    import compliance_profiles
    rules = compliance_profiles.PROFILES['anssi']['rules']
    monkeypatch.setitem(rules, 'allowed_key_types', rules['allowed_key_types'] + [PQ])
    ca = create_ca(cn='Pair CA anssi renew', keyAlgo='EC', keySize='P-256')
    r = auth_client.post('/api/v2/certificates', json={
        'cn': 'pair-anssi-renew.example.com', 'ca_id': ca['id'], 'validity_days': 90, 'hybrid': HYBRID})
    assert r.status_code == 201, r.data
    b = json.loads(r.data)['data']['related']
    with app.app_context():
        row = db.session.get(CA, ca['id'])
        row.compliance_profile = 'anssi'
        db.session.commit()
    r = auth_client.post(f"/api/v2/certificates/{b['id']}/renew", json={})
    assert r.status_code == 200, r.data


# ---- export ----------------------------------------------------------------------

def _zip(response):
    assert response.status_code == 200, response.data
    assert response.mimetype == 'application/zip'
    return zipfile.ZipFile(io.BytesIO(response.data))


def test_the_bundle_holds_both_certificates(auth_client, create_ca):
    a, b = _pair(auth_client, create_ca, 'pair-export.example.com')
    bundle = _zip(auth_client.get(f"/api/v2/certificates/{b['id']}/export?format=hybrid-bundle"))
    names = sorted(bundle.namelist())
    assert names == sorted([f"classical-{a['id']}.crt", f"pq-{b['id']}.crt"])
    cert_a = x509.load_pem_x509_certificate(bundle.read(f"classical-{a['id']}.crt"))
    cert_b = x509.load_pem_x509_certificate(bundle.read(f"pq-{b['id']}.crt"))
    assert related_cert.references(cert_b, cert_a)


def test_the_bundle_holds_both_keys_when_asked(auth_client, create_ca):
    a, b = _pair(auth_client, create_ca, 'pair-export-keys.example.com')
    bundle = _zip(auth_client.post(f"/api/v2/certificates/{a['id']}/export", json={
        'format': 'hybrid-bundle', 'include_key': True, 'password': 'BundlePass123!'}))
    for role, row in (('classical', a), ('pq', b)):
        cert = x509.load_pem_x509_certificate(bundle.read(f"{role}-{row['id']}.crt"))
        key = serialization.load_pem_private_key(bundle.read(f"{role}-{row['id']}.key"), b'BundlePass123!')
        assert key.public_key() == cert.public_key()


def test_the_bundle_keys_need_the_private_key_permission(app, auth_client, create_ca, create_user):
    a, _b = _pair(auth_client, create_ca, 'pair-export-denied.example.com')
    operator = _login(app, create_user)
    r = operator.get(f"/api/v2/certificates/{a['id']}/export?format=hybrid-bundle&include_key=true")
    assert r.status_code == 403
    assert operator.get(f"/api/v2/certificates/{a['id']}/export?format=hybrid-bundle").status_code == 200


def test_a_certificate_without_a_partner_has_no_bundle(auth_client, create_cert):
    lone = create_cert(cn='pair-export-lone.example.com')
    r = auth_client.get(f"/api/v2/certificates/{lone['id']}/export?format=hybrid-bundle")
    assert r.status_code == 400 and b'no related certificate' in r.data


def test_deleting_a_member_unlinks_the_other(app, auth_client, create_ca):
    a, b = _pair(auth_client, create_ca, 'pair-delete.example.com')
    r = auth_client.post(f"/api/v2/certificates/{a['id']}/revoke", json={'revoke_related': False})
    assert r.status_code == 200, r.data
    r = auth_client.delete(f"/api/v2/certificates/{a['id']}")
    assert r.status_code == 204, r.data
    row = _row(app, b['id'])
    assert (row['related_certificate_id'], row['hybrid_role']) == (None, None)


def test_deleting_b_takes_a_out_of_the_pair(app, auth_client, create_ca):
    a, b = _pair(auth_client, create_ca, 'pair-delete-b.example.com')
    r = auth_client.post(f"/api/v2/certificates/{b['id']}/revoke", json={'revoke_related': False})
    assert r.status_code == 200, r.data
    r = auth_client.delete(f"/api/v2/certificates/{b['id']}")
    assert r.status_code == 204, r.data
    row = _row(app, a['id'])
    assert (row['related_certificate_id'], row['hybrid_role']) == (None, None)


# ---- automatic callers revoke the replaced member only ----------------------------

def _set_config(app, key, value):
    from models import SystemConfig
    with app.app_context():
        row = SystemConfig.query.filter_by(key=key).first()
        previous = row.value if row is not None else None
        if row is None:
            db.session.add(SystemConfig(key=key, value=value))
        else:
            row.value = value
        db.session.commit()
        return previous


def _restore_config(app, key, previous):
    from models import SystemConfig
    with app.app_context():
        row = SystemConfig.query.filter_by(key=key).first()
        if previous is None and row is not None:
            db.session.delete(row)
        elif previous is not None:
            row.value = previous
        db.session.commit()


@pytest.mark.parametrize('caller', ['finalize', 'settings sweep'])
def test_acme_supersede_leaves_the_new_partner_valid(app, auth_client, create_ca, caller):
    from datetime import timedelta
    from models.acme_models import AcmeAccount, AcmeOrder
    from services.acme.acme_service import AcmeService
    from api.v2.acme.settings import _revoke_superseded_certificates
    cn = f"pair-supersede-{caller.replace(' ', '-')}.example.com"
    a, b = _pair(auth_client, create_ca, cn)
    previous = _set_config(app, 'acme.revoke_on_renewal', 'true')
    try:
        with app.app_context():
            account = AcmeAccount(jwk='{}', jwk_thumbprint=cn)
            db.session.add(account)
            db.session.flush()
            idents = json.dumps([{'type': 'dns', 'value': cn}])
            now = utc_now()
            old = AcmeOrder(account_id=account.account_id, status='valid', identifiers=idents,
                            certificate_id=a['id'], created_at=now - timedelta(days=1))
            new = AcmeOrder(account_id=account.account_id, status='valid', identifiers=idents,
                            certificate_id=b['id'], created_at=now)
            db.session.add_all([old, new])
            db.session.commit()
            if caller == 'finalize':
                AcmeService(base_url='http://localhost')._auto_supersede(new, b['id'])
            else:
                assert _revoke_superseded_certificates() >= 1
        assert _revoked(app, a['id'], b['id']) == [True, False]
    finally:
        _restore_config(app, 'acme.revoke_on_renewal', previous)
        with app.app_context():
            AcmeOrder.query.filter(AcmeOrder.certificate_id.in_([a['id'], b['id']])).delete(
                synchronize_session=False)
            AcmeAccount.query.filter_by(jwk_thumbprint=cn).delete()
            db.session.commit()


def test_acme_client_renewal_revokes_the_replaced_member_only(app, auth_client, create_ca):
    from unittest import mock
    from services.acme_renewal_service import _replaced_snapshot, _revoke_replaced_certificate
    a, b = _pair(auth_client, create_ca, 'pair-client-renew.example.com')
    previous = _set_config(app, 'acme.revoke_on_renewal', 'true')
    try:
        client = mock.Mock()
        client.revoke_certificate.return_value = mock.Mock(status_code=200)
        with app.app_context():
            # A replaced row of its own (renewed into a new row): revoked alone
            _revoke_replaced_certificate(client, _replaced_snapshot(db.session.get(Certificate, a['id'])),
                                         in_place=False)
        assert _revoked(app, a['id'], b['id']) == [True, False]
    finally:
        _restore_config(app, 'acme.revoke_on_renewal', previous)


def test_removing_an_enrolment_revokes_its_certificate_only(app, auth_client, create_ca, create_user):
    from models import AuthCertificate
    from services.mtls_enrollment import remove_enrolment
    a, b = _pair(auth_client, create_ca, 'pair-enrolment.example.com')
    user = create_user()
    with app.app_context():
        cert = _x509(a)
        enrolment = AuthCertificate(user_id=user['id'], cert_pem=a['pem'].encode(),
                                    cert_serial=str(cert.serial_number),
                                    cert_subject=cert.subject.rfc4514_string())
        db.session.add(enrolment)
        db.session.commit()
        ok, response = remove_enrolment(enrolment, username='test')
        assert ok, response
    with app.app_context():
        assert db.session.get(Certificate, a['id']) is None  # revoked, then deleted with the enrolment
    assert _revoked(app, b['id']) == [False]


# ---- the partner's approval policy holds the pair -----------------------------------

def _move_to_new_ca(app, create_ca, cert_id, cn):
    """Point *cert_id* at a CA of its own (as a pair whose B another CA signed)."""
    ca = create_ca(cn=cn)
    with app.app_context():
        row = db.session.get(Certificate, cert_id)
        row.caref = db.session.get(CA, ca['id']).refid
        db.session.commit()
    return ca['id']


def test_the_partner_policy_holds_the_revocation_of_the_pair(app, auth_client, create_ca, create_user):
    a, b = _pair(auth_client, create_ca, 'pair-partner-policy.example.com')
    pid = _approval_policy(app, _move_to_new_ca(app, create_ca, b['id'], 'Pair CA2 revoke'), ['revocation'])
    try:
        operator = _login(app, create_user)
        r = operator.post(f"/api/v2/certificates/{a['id']}/revoke", json={'reason': 'keyCompromise'})
        assert r.status_code == 200, r.data
        body = json.loads(r.data)['data']
        assert body['approval_required'], r.data
        assert _revoked(app, a['id'], b['id']) == [False, False]
        r = operator.post('/api/v2/certificates/bulk/revoke', json={'ids': [a['id']]})
        assert json.loads(r.data)['data']['pending_approval'][0]['id'] == a['id']
        assert _revoked(app, a['id'], b['id']) == [False, False]
        r = auth_client.post(f"/api/v2/approvals/{body['approval_id']}/approve", json={'comment': 'ok'})
        assert r.status_code == 200, r.data
        assert _revoked(app, a['id'], b['id']) == [True, True]
    finally:
        _drop_policy(app, pid)


def test_the_partner_policy_holds_a_user_certificate_revocation(
        app, auth_client, create_ca, create_user):
    from models import AuthCertificate
    from services.approval_gate import revocation_policy_for
    a, b = _pair(auth_client, create_ca, 'pair-partner-user.example.com')
    pid = _approval_policy(app, _move_to_new_ca(app, create_ca, b['id'], 'Pair CA2 user'), ['revocation'])
    try:
        user = create_user()
        with app.app_context():
            cert = _x509(a)
            enrolment = AuthCertificate(user_id=user['id'], cert_pem=a['pem'].encode(),
                                        cert_serial=str(cert.serial_number),
                                        cert_subject=cert.subject.rfc4514_string())
            db.session.add(enrolment)
            db.session.commit()
            enrolment_id = enrolment.id
            # What the user-certificate route asks before revoking A (and B with it)
            row_a, row_b = db.session.get(Certificate, a['id']), db.session.get(Certificate, b['id'])
            assert revocation_policy_for(row_a) is None
            assert revocation_policy_for(row_a, row_b).id == pid
        operator = _login(app, create_user)
        r = operator.post(f'/api/v2/user-certificates/{enrolment_id}/revoke', json={'reason': 'keyCompromise'})
        assert r.status_code == 200, r.data
        assert json.loads(r.data)['data']['approval_required'], r.data
        assert _revoked(app, a['id'], b['id']) == [False, False]
    finally:
        _drop_policy(app, pid)
        with app.app_context():
            AuthCertificate.query.filter_by(cert_serial=str(_x509(a).serial_number)).delete()
            db.session.commit()


def _drop_made(app, cert_ids, ca_ids, user_ids):
    """The rows a test made: its certificates, then their CAs, then its users."""
    from models import User
    from services.ca_service import CAService
    from services.cert_service import CertificateService
    with app.app_context():
        for cert_id in cert_ids:
            if db.session.get(Certificate, cert_id) is not None:
                CertificateService.delete_certificate(cert_id, username='test')
        for ca_id in ca_ids:
            if db.session.get(CA, ca_id) is not None:
                CAService.delete_ca(ca_id, username='test')
        for user_id in user_ids:
            user = db.session.get(User, user_id)
            if user is not None:
                db.session.delete(user)
        db.session.commit()


def test_a_superseded_partner_does_not_bring_its_policy_to_a_user_certificate_revocation(
        app, auth_client, create_ca, create_user):
    """The user-certificate route follows ``revocation_partner``: an archived partner is left alone."""
    from models import AuthCertificate
    a, b = _pair(auth_client, create_ca, 'pair-archived-user.example.com')
    ca_ids = [_ca_id_of(app, a['id'])]
    ca_ids.append(_move_to_new_ca(app, create_ca, b['id'], 'Pair CA2 archived'))
    pid = _approval_policy(app, ca_ids[1], ['revocation'])
    user_ids = []
    try:
        user = create_user(username='pair_archived_holder')
        user_ids.append(user['id'])
        with app.app_context():
            db.session.get(Certificate, b['id']).archived = True
            cert = _x509(a)
            enrolment = AuthCertificate(user_id=user['id'], cert_pem=a['pem'].encode(),
                                        cert_serial=str(cert.serial_number),
                                        cert_subject=cert.subject.rfc4514_string())
            db.session.add(enrolment)
            db.session.commit()
            enrolment_id = enrolment.id
        operator = create_user(username='pair_archived_operator', role='operator')
        user_ids.append(operator['id'])
        client = app.test_client()
        r = client.post('/api/v2/auth/login', json={'username': operator['username'], 'password': 'TestPass123!'})
        assert r.status_code == 200, r.data
        r = client.post(f'/api/v2/user-certificates/{enrolment_id}/revoke', json={'reason': 'keyCompromise'})
        assert r.status_code == 200, r.data
        assert not json.loads(r.data)['data'].get('approval_required'), r.data
        assert _revoked(app, a['id'], b['id']) == [True, False]
    finally:
        _drop_policy(app, pid)
        with app.app_context():
            AuthCertificate.query.filter_by(cert_serial=str(_x509(a).serial_number)).delete()
            db.session.commit()
        _drop_made(app, [a['id'], b['id']], ca_ids, user_ids)


@pytest.mark.parametrize('route', ['single', 'bulk', 'user'])
def test_the_partner_policy_holds_a_hold_made_final(app, auth_client, create_ca, create_user, route):
    from models import AuthCertificate
    a, b = _pair(auth_client, create_ca, f'pair-held-policy-{route}.example.com')
    r = auth_client.post(f"/api/v2/certificates/{a['id']}/revoke", json={'reason': 'certificateHold'})
    assert r.status_code == 200, r.data
    pid = _approval_policy(app, _move_to_new_ca(app, create_ca, b['id'], f'Pair CA2 held {route}'),
                           ['revocation'])
    try:
        operator = _login(app, create_user)
        if route == 'user':
            user = create_user()
            with app.app_context():
                cert = _x509(a)
                enrolment = AuthCertificate(user_id=user['id'], cert_pem=a['pem'].encode(),
                                            cert_serial=str(cert.serial_number),
                                            cert_subject=cert.subject.rfc4514_string())
                db.session.add(enrolment)
                db.session.commit()
                url, body = f'/api/v2/user-certificates/{enrolment.id}/revoke', {}
        elif route == 'bulk':
            url, body = '/api/v2/certificates/bulk/revoke', {'ids': [a['id']]}
        else:
            url, body = f"/api/v2/certificates/{a['id']}/revoke", {}
        r = operator.post(url, json=dict(body, reason='keyCompromise'))
        assert r.status_code == 200, r.data
        data = json.loads(r.data)['data']
        assert (data['pending_approval'] if route == 'bulk' else data['approval_required']), r.data
        with app.app_context():
            assert [db.session.get(Certificate, i).revoke_reason for i in (a['id'], b['id'])] \
                == ['certificateHold', 'certificateHold']
    finally:
        _drop_policy(app, pid)
        with app.app_context():
            AuthCertificate.query.filter_by(cert_serial=str(_x509(a).serial_number)).delete()
            db.session.commit()


def test_acme_revokes_the_presented_certificate_only_whatever_the_partner_policy(
        app, client, auth_client, create_ca):
    """RFC 8555 §7.6 revokes the certificate presented: B and its CA's policy are not involved."""
    from tests.test_acme_security_paths import _build_jws, _int_to_b64, _nonce, _post_jws
    from utils.key_codec import load_pem_bytes
    a, b = _pair(auth_client, create_ca, 'pair-partner-acme.example.com',
                 hybrid={'classical': 'RSA-2048', 'pq': PQ})
    pid = _approval_policy(app, _move_to_new_ca(app, create_ca, b['id'], 'Pair CA2 acme'), ['revocation'])
    try:
        with app.app_context():
            key = serialization.load_pem_private_key(
                load_pem_bytes(db.session.get(Certificate, a['id']).prv, context='test'), None)
        pub = key.public_key().public_numbers()
        der = _x509(a).public_bytes(serialization.Encoding.DER)
        path = '/acme/revoke-cert'
        jws = _build_jws(f'http://localhost{path}',
                         {'certificate': base64.urlsafe_b64encode(der).rstrip(b'=').decode(), 'reason': 1},
                         key, jwk={'kty': 'RSA', 'n': _int_to_b64(pub.n), 'e': _int_to_b64(pub.e)},
                         nonce=_nonce(client))
        r = _post_jws(client, path, jws)
        assert r.status_code == 200, r.data
        assert _revoked(app, a['id'], b['id']) == [True, False]
        assert _pending(app, pid) == 0
    finally:
        _drop_policy(app, pid)


@pytest.mark.parametrize('operation', ['revocation', 'renewal'])
def test_a_bulk_listing_both_members_queues_one_request(app, auth_client, create_ca, create_user, operation):
    a, b = _pair(auth_client, create_ca, f'pair-bulk-one-{operation}.example.com')
    pid = _approval_policy(app, _move_to_new_ca(app, create_ca, b['id'], f'Pair CA2 bulk {operation}'),
                           [operation])
    try:
        operator = _login(app, create_user)
        path = '/api/v2/certificates/bulk/' + ('revoke' if operation == 'revocation' else 'renew')
        r = operator.post(path, json={'ids': [a['id'], b['id']]})
        assert r.status_code == 200, r.data
        pending = json.loads(r.data)['data']['pending_approval']
        assert [p['id'] for p in pending] == [a['id'], b['id']], pending
        assert len({p['approval_id'] for p in pending}) == 1, pending
        assert _pending(app, pid) == 1
        assert _revoked(app, a['id'], b['id']) == [False, False]
    finally:
        _drop_policy(app, pid)


def test_two_policies_on_a_pair_refuse_the_operator(app, auth_client, create_ca, create_user):
    a, b = _pair(auth_client, create_ca, 'pair-two-policies.example.com')
    p1 = _approval_policy(app, _ca_id_of(app, a['id']), ['revocation', 'renewal'])
    p2 = _approval_policy(app, _move_to_new_ca(app, create_ca, b['id'], 'Pair CA2 two'), ['revocation', 'renewal'])
    try:
        operator = _login(app, create_user)
        r = operator.post(f"/api/v2/certificates/{a['id']}/revoke", json={'reason': 'keyCompromise'})
        assert r.status_code == 409 and b'different policies' in r.data, r.data
        r = operator.post(f"/api/v2/certificates/{a['id']}/renew", json={})
        assert r.status_code == 409 and b'different policies' in r.data, r.data
        assert (_pending(app, p1), _pending(app, p2)) == (0, 0)
        assert _revoked(app, a['id'], b['id']) == [False, False]
    finally:
        _drop_policy(app, p1)
        _drop_policy(app, p2)


def test_the_partner_policy_holds_the_renewal_of_the_pair(app, auth_client, create_ca, create_user):
    a, b = _pair(auth_client, create_ca, 'pair-partner-renewal.example.com')
    pid = _approval_policy(app, _move_to_new_ca(app, create_ca, b['id'], 'Pair CA2 renew'), ['renewal'])
    try:
        operator = _login(app, create_user)
        r = operator.post(f"/api/v2/certificates/{a['id']}/renew", json={})
        assert r.status_code == 200, r.data
        assert json.loads(r.data)['data']['approval_required'], r.data
        r = operator.post('/api/v2/certificates/bulk/renew', json={'ids': [a['id']]})
        assert json.loads(r.data)['data']['pending_approval'][0]['id'] == a['id']
        assert [s[1] for s in _state(app, a['id'], b['id'])] == [0, 0]
    finally:
        _drop_policy(app, pid)


# ---- the scheduler renews a pair once ---------------------------------------------

@pytest.mark.parametrize('order', ['ab', 'ba'])
def test_the_scheduler_renews_a_listed_pair_once(app, auth_client, create_ca, monkeypatch, order):
    from services.auto_renewal_service import AutoRenewalService
    a, b = _pair(auth_client, create_ca, f'pair-scheduler-{order}.example.com')
    ids = [a['id'], b['id']] if order == 'ab' else [b['id'], a['id']]
    monkeypatch.setattr(AutoRenewalService, 'get_renewal_config', staticmethod(
        lambda: {'enabled': True, 'notify_on_renewal': False, 'notify_on_failure': False}))
    monkeypatch.setattr(AutoRenewalService, 'waiting_certificates', staticmethod(lambda config: {}))
    monkeypatch.setattr(AutoRenewalService, 'get_certificates_for_renewal', staticmethod(
        lambda: [db.session.get(Certificate, i) for i in ids]))
    with app.app_context():
        stats = AutoRenewalService.run_auto_renewal()
    assert (stats['renewed'], stats['failed'], stats['errors']) == (2, 0, []), stats
    (_sa, times_a, new_a), (_sb, times_b, new_b) = _state(app, a['id'], b['id'])
    assert (times_a, times_b) == (1, 1)
    assert related_cert.references(new_b, new_a)


def test_the_scheduler_queues_a_pair_held_by_the_partner_policy_once(app, auth_client, create_ca, monkeypatch):
    from services.auto_renewal_service import AutoRenewalService
    a, b = _pair(auth_client, create_ca, 'pair-scheduler-held.example.com')
    pid = _approval_policy(app, _move_to_new_ca(app, create_ca, b['id'], 'Pair CA2 scheduler'), ['renewal'])
    monkeypatch.setattr(AutoRenewalService, 'get_renewal_config', staticmethod(
        lambda: {'enabled': True, 'notify_on_renewal': False, 'notify_on_failure': False}))
    monkeypatch.setattr(AutoRenewalService, 'waiting_certificates', staticmethod(lambda config: {}))
    monkeypatch.setattr(AutoRenewalService, 'get_certificates_for_renewal', staticmethod(
        lambda: [db.session.get(Certificate, i) for i in (a['id'], b['id'])]))
    try:
        with app.app_context():
            stats = AutoRenewalService.run_auto_renewal()
        assert (stats['renewed'], stats['queued'], stats['failed']) == (0, 2, 0), stats
        assert _pending(app, pid) == 1
        assert [s[1] for s in _state(app, a['id'], b['id'])] == [0, 0]
        with app.app_context():
            stats = AutoRenewalService.run_auto_renewal()  # the request waits: nothing more
        assert (stats['renewed'], stats['failed']) == (0, 0) and _pending(app, pid) == 1, stats
    finally:
        _drop_policy(app, pid)
