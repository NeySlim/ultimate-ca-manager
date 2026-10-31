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

pytestmark = pytest.mark.skipif(not key_algorithms.mldsa_supported(),
                                reason='this build has no ML-DSA')

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


def test_the_pair_satisfies_a_profile_that_refuses_ml_dsa_alone(app, auth_client, create_ca, monkeypatch):
    import compliance_profiles
    rules = compliance_profiles.PROFILES['anssi']['rules']
    # The profile's own key list does not name ML-DSA yet: pq_standalone alone is tested here
    monkeypatch.setitem(rules, 'allowed_key_types', rules['allowed_key_types'] + [PQ])
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
    assert _row(app, b['id'])['related_certificate_id'] is None
