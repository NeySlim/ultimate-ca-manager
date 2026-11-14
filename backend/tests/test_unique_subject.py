"""RFC 5280 §4.1.2.6, the CA option enforce_unique_subject: a CA never certifies a non-empty
subject another entity's certificate of the CA carries, whatever that certificate's status;
manual issuance, CSR signing, renewal in place, approvals, the CA API, the migration.
Races on two real connections: SQLite, and PostgreSQL with UCM_TEST_APP_PG_URL."""
import base64
import contextlib
import hashlib
import json
import re
import secrets
import sqlite3
import threading
import time

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from sqlalchemy import event

from models import CA, AuditLog, Certificate, db

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')


@pytest.fixture(autouse=True, scope='module')
def _made_rows_removed(app):
    """The accounts, orders, users and API keys this file makes go with it."""
    from models import User
    from models.acme_models import AcmeAccount, AcmeOrder
    from models.api_key import APIKey
    models = (AcmeOrder, AcmeAccount, APIKey, User)
    with app.app_context():
        floors = {m: db.session.query(db.func.max(m.id)).scalar() or 0 for m in models}
    yield
    with app.app_context():
        db.session.rollback()
        for model in models:
            model.query.filter(model.id > floors[model]).delete(synchronize_session=False)
        db.session.commit()


def _key():
    return ec.generate_private_key(ec.SECP256R1())


def _name(cn):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]) if cn else x509.Name([])


def _csr(cn, key, dns=None):
    builder = x509.CertificateSigningRequestBuilder().subject_name(_name(cn))
    if dns:
        builder = builder.add_extension(x509.SubjectAlternativeName([x509.DNSName(dns)]), critical=False)
    return builder.sign(key, hashes.SHA256())


def unique_ca(app, create_ca, cn, on=True):
    ca = create_ca(cn=cn)
    with app.app_context():
        db.session.get(CA, ca['id']).enforce_unique_subject = on
        db.session.commit()
    return ca


def _csr_row(app, csr):
    pem = csr.public_bytes(serialization.Encoding.PEM)
    with app.app_context():
        row = Certificate(refid=secrets.token_hex(8), descr='unique subject csr', source='manual',
                          csr=base64.b64encode(pem).decode())
        db.session.add(row)
        db.session.commit()
        return row.id


def _sign(auth_client, app, ca, csr, **extra):
    return auth_client.post(f'/api/v2/csrs/{_csr_row(app, csr)}/sign',
                            json={'ca_id': ca['id'], 'validity_days': 30, **extra})


def _issue(auth_client, ca, cn, **extra):
    return auth_client.post('/api/v2/certificates', json={
        'cn': cn, 'ca_id': ca['id'], 'cert_type': 'server', 'key_type': 'EC', 'curve': 'P-256',
        'validity_days': 30, **extra})


def _data(response, status):
    assert response.status_code == status, response.get_json()
    return response.get_json().get('data')


def _state(app, ca):
    """(certificates of the CA, its issuance count)."""
    with app.app_context():
        row = db.session.get(CA, ca['id'])
        return Certificate.query.filter_by(caref=row.refid).count(), row.serial


def _audit(app, action, after=0):
    with app.app_context():
        return [a.details for a in AuditLog.query.filter(AuditLog.action == action, AuditLog.id > after)
                .order_by(AuditLog.id)]


def _last_audit_id(app):
    with app.app_context():
        return db.session.query(db.func.max(AuditLog.id)).scalar() or 0


def _row(app, cert_id):
    with app.app_context():
        return db.session.get(Certificate, cert_id)


# --- Off by default: nothing changes -------------------------------------------------------------

def test_a_new_ca_does_not_enforce_and_issues_a_subject_twice(app, auth_client, create_ca):
    ca = create_ca(cn='Unique off CA')
    assert ca['enforce_unique_subject'] is False
    _data(_issue(auth_client, ca, 'twice.unique.test'), 201)
    _data(_issue(auth_client, ca, 'twice.unique.test'), 201)
    _data(_sign(auth_client, app, ca, _csr('twice.unique.test', _key())), 200)


def _lookups(app, issue):
    statements = []

    def record(conn, cursor, statement, *args):
        statements.append(statement)
    with app.app_context():
        engine = db.engine
    event.listen(engine, 'before_cursor_execute', record)
    try:
        issue()
    finally:
        event.remove(engine, 'before_cursor_execute', record)
    return len([s for s in statements if re.search(r'WHERE.*subject_key\s*=', s, re.S)])


def test_the_option_off_runs_no_lookup_on_any_trunk(app, auth_client, create_ca, monkeypatch):
    """Manual issuance, CSR signing, the protocol trunk, the service mTLS calls, renewal in place
    and SCEP; on, each looks up twice: before the CT logs and under the CA row lock."""
    from services.ca_service import CAService
    from services.cert_service import CertificateService
    from tests.test_unique_subject_before_publication import _pkcs_req
    from services.scep.scep_service import SCEPService
    monkeypatch.setenv('UCM_SCEP_ALLOW_NO_CHALLENGE', '1')
    off, on = create_ca(cn='Unique counted off CA'), unique_ca(app, create_ca, 'Unique counted on CA')

    def trunk(ca):
        with app.app_context():
            CAService.sign_csr_from_crypto(db.session.get(CA, ca['id']), _csr('trunk.unique.test', _key()),
                                           validity_days=30, source='test')

    def mtls(ca):
        with app.app_context():
            CertificateService.create_certificate(descr='mtls', caref=ca['refid'], dn={'CN': 'mtls.unique.test'},
                                                  validity_days=30, subject_holder='user:1')

    def scep(ca):
        request = _pkcs_req(app, ca['id'], 'scep-count.unique.test', secrets.token_hex(8))
        with app.app_context():
            assert SCEPService(ca['refid'], auto_approve=True).process_pkcs_req(request, '127.0.0.1')[1] == 200

    counts = []
    for ca in (off, on):
        held = _data(_issue(auth_client, ca, 'renewed.unique.test'), 201)
        counts.append((
            _lookups(app, lambda: _data(_issue(auth_client, ca, 'counted.unique.test'), 201)),
            _lookups(app, lambda: _data(_sign(auth_client, app, ca, _csr('signed.unique.test', _key())), 200)),
            _lookups(app, lambda: trunk(ca)),
            _lookups(app, lambda: mtls(ca)),
            _lookups(app, lambda: _data(auth_client.post(f"/api/v2/certificates/{held['id']}/renew", json={}), 200)),
            _lookups(app, lambda: scep(ca))))
    assert counts == [(0,) * 6, (2,) * 6]


# --- Refused, audited, nothing stored ------------------------------------------------------------

def test_manual_issuance_of_a_taken_subject_is_409_naming_the_certificate(app, auth_client, create_ca):
    ca = unique_ca(app, create_ca, 'Unique manual CA')
    first = _data(_issue(auth_client, ca, 'taken.unique.test'), 201)
    before, after_audit = _state(app, ca), _last_audit_id(app)
    r = _issue(auth_client, ca, 'taken.unique.test')
    assert r.status_code == 409, r.get_json()
    body = r.get_json()
    assert body['details'] == {'subject': 'CN=taken.unique.test', 'serial_number': first['serial_number'],
                               'override_field': 'override_unique_subject'}
    assert first['serial_number'] in body['message'] and 'override_unique_subject' in body['message']
    # Nothing stored, and the count rolled back with it
    assert _state(app, ca) == before
    assert _audit(app, 'certificate.subject_taken', after_audit) == [
        f"manual issuance refused: the subject CN=taken.unique.test is already carried by "
        f"certificate serial {first['serial_number']}"]


def test_csr_signing_of_a_taken_subject_is_409_and_the_same_key_is_the_same_entity(app, auth_client, create_ca):
    ca = unique_ca(app, create_ca, 'Unique CSR CA')
    key = _key()
    first = _data(_sign(auth_client, app, ca, _csr('csr.unique.test', key)), 200)
    before = _state(app, ca)
    r = _sign(auth_client, app, ca, _csr('csr.unique.test', _key()))
    assert r.status_code == 409 and r.get_json()['details']['serial_number'] == first['serial_number']
    assert _state(app, ca)[1] == before[1]
    # Proof 1: the request proves possession of the key a certificate of that subject carries
    _data(_sign(auth_client, app, ca, _csr('csr.unique.test', key)), 200)


def test_bulk_signing_reports_the_taken_subject(app, auth_client, create_ca):
    ca = unique_ca(app, create_ca, 'Unique bulk CA')
    first = _data(_sign(auth_client, app, ca, _csr('bulk.unique.test', _key())), 200)
    csr_id = _csr_row(app, _csr('bulk.unique.test', _key()))
    data = _data(auth_client.post('/api/v2/csrs/bulk/sign', json={'ids': [csr_id], 'ca_id': ca['id']}), 200)
    error = f"the subject CN=bulk.unique.test is already carried by certificate serial {first['serial_number']}"
    assert data['failed'] == [{'id': csr_id, 'error': error}]


@pytest.mark.parametrize('status', ['revoked', 'expired', 'archived'])
def test_a_revoked_expired_or_superseded_certificate_still_holds_its_subject(
        app, auth_client, create_ca, status):
    from datetime import timedelta
    from utils.datetime_utils import utc_now
    ca = unique_ca(app, create_ca, f'Unique {status} CA')
    first = _data(_issue(auth_client, ca, f'{status}.unique.test'), 201)
    with app.app_context():
        row = db.session.get(Certificate, first['id'])
        if status == 'revoked':
            row.revoked, row.revoked_at = True, utc_now()
        elif status == 'expired':
            row.valid_to = utc_now() - timedelta(days=1)
        else:
            row.archived = True
        db.session.commit()
    assert _issue(auth_client, ca, f'{status}.unique.test').status_code == 409


def test_another_ca_is_another_namespace(app, auth_client, create_ca):
    one, other = unique_ca(app, create_ca, 'Unique ns one CA'), unique_ca(app, create_ca, 'Unique ns two CA')
    _data(_issue(auth_client, one, 'ns.unique.test'), 201)
    _data(_issue(auth_client, other, 'ns.unique.test'), 201)


# --- Exemptions ----------------------------------------------------------------------------------

def _leaf(app, ca, subject, key):
    """A certificate of *ca* for *subject*, signed with its key, outside any issuance path."""
    from datetime import datetime, timedelta, timezone
    from services.hsm.ca_key_loader import get_ca_signing_key
    with app.app_context():
        row = db.session.get(CA, ca['id'])
        issuer = x509.load_pem_x509_certificate(base64.b64decode(row.crt))
        now = datetime.now(timezone.utc)
        builder = (x509.CertificateBuilder().subject_name(subject).issuer_name(issuer.subject)
                   .public_key(key.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(now).not_valid_after(now + timedelta(days=1))
                   .add_extension(x509.SubjectAlternativeName([x509.DNSName('empty.unique.test')]),
                                  critical=True))
        return builder.sign(get_ca_signing_key(row), hashes.SHA256())


def test_an_empty_subject_is_not_concerned(app, create_ca):
    """RFC 5280 §4.1.2.6 binds a non-empty subject only (EJBCA exempts a blank one too)."""
    from services.cert.unique_subject import refuse_taken_subject
    ca = unique_ca(app, create_ca, 'Unique empty CA')
    held = _leaf(app, ca, x509.Name([]), _key())
    with app.app_context():
        db.session.add(Certificate(refid=secrets.token_hex(8), descr='empty', caref=ca['refid'],
                                   crt=base64.b64encode(held.public_bytes(serialization.Encoding.PEM)).decode()))
        db.session.commit()
        assert refuse_taken_subject(db.session.get(CA, ca['id']), _leaf(app, ca, x509.Name([]), _key())) is None


def test_a_ca_certificate_is_not_concerned(app, auth_client, create_ca):
    """Signed as a sub-CA, the request becomes a CA row: never counted against an entity."""
    from services.ca_service import CAService
    ca = unique_ca(app, create_ca, 'Unique sub-CA parent')
    subs = []
    for _ in range(2):
        r = _sign(auth_client, app, ca, _csr('Unique Sub CA', _key()), cert_type='intermediate_ca')
        subs.append(_data(r, 200)['id'])
    with app.app_context():
        for sub_id in subs:
            CAService.delete_ca(sub_id)


def test_the_two_certificates_of_a_hybrid_pair_are_one_entity(app, auth_client, create_ca):
    """RFC 9763: B carries A's subject; both renew together in place."""
    ca = unique_ca(app, create_ca, 'Unique hybrid CA')
    pair = {'classical': 'EC-P256', 'pq': 'ML-DSA-44'}
    data = _data(_issue(auth_client, ca, 'hybrid.unique.test', hybrid=pair), 201)
    a_id = data['certificate']['id']
    assert _row(app, data['related']['id']).subject_holder == f"cert:{_row(app, a_id).refid}"
    assert auth_client.post(f'/api/v2/certificates/{a_id}/renew', json={}).status_code == 200
    assert _issue(auth_client, ca, 'hybrid.unique.test').status_code == 409
    # B revoked, A renews alone and leaves the pair: B's lineage still names A
    from utils.datetime_utils import utc_now
    with app.app_context():
        b = db.session.get(Certificate, data['related']['id'])
        b.revoked, b.revoked_at = True, utc_now()
        db.session.commit()
    r = auth_client.post(f'/api/v2/certificates/{a_id}/renew', json={})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['data'].get('related') in (None, []), r.get_json()


def test_a_certificate_transparency_precertificate_does_not_count(app, create_ca, monkeypatch):
    """The pre-certificate is signed with the final certificate and never stored."""
    from services.cert_service import CertificateService
    from utils import ct_client
    ca = unique_ca(app, create_ca, 'Unique CT CA')
    signed = []

    def precert_then_final(cert, ca_cert, ca_key):
        signed.append(cert)  # stands for the pre-certificate submitted to the logs
        return cert, [{'log': 'test'}]
    monkeypatch.setattr(ct_client, 'apply_ct_policy', precert_then_final)
    with app.app_context():
        issued = CertificateService.create_certificate(
            descr='ct', caref=ca['refid'], dn={'CN': 'ct.unique.test'}, validity_days=30)
        assert signed and Certificate.query.filter_by(caref=ca['refid']).count() == 1
        assert issued.subject == 'CN=ct.unique.test'


# --- Renewal in place, override, approval --------------------------------------------------------

def test_renewal_in_place_is_the_same_entity_but_not_another_one(app, auth_client, create_ca):
    ca = unique_ca(app, create_ca, 'Unique renewal CA', on=False)
    mine = _data(_issue(auth_client, ca, 'renew.unique.test'), 201)
    other = _data(_issue(auth_client, ca, 'renew-shared.unique.test'), 201)
    _data(_issue(auth_client, ca, 'renew-shared.unique.test'), 201)  # shared before the option
    with app.app_context():
        db.session.get(CA, ca['id']).enforce_unique_subject = True
        db.session.commit()
    assert auth_client.post(f"/api/v2/certificates/{mine['id']}/renew", json={}).status_code == 200
    r = auth_client.post(f"/api/v2/certificates/{other['id']}/renew", json={})
    assert r.status_code == 409, r.get_json()
    assert 'renew-shared.unique.test' in r.get_json()['message']
    assert _row(app, other['id']).serial_number == other['serial_number']


def _renews(app, auth_client, held, how):
    """Renew *held* in place by the Renew button's route, the bulk API or the scheduler."""
    from services.auto_renewal_service import AutoRenewalService
    if how == 'button':
        r = auth_client.post(f"/api/v2/certificates/{held['id']}/renew", json={})
        return r.status_code == 200
    if how == 'api':
        data = _data(auth_client.post('/api/v2/certificates/bulk/renew', json={'ids': [held['id']]}), 200)
        return data['success'] == [held['id']]
    with app.app_context():
        renewed, _message = AutoRenewalService.renew_certificate(db.session.get(Certificate, held['id']))
        return renewed is True


@pytest.mark.parametrize('how', ['button', 'api', 'auto'])
def test_an_override_attests_the_same_entity_and_both_renew_without_it(app, auth_client, create_ca, how):
    """RFC 5280 §4.1.2.6: a CA MAY certify one DN again for the same entity, never for another."""
    ca = unique_ca(app, create_ca, f'Unique override renewal {how} CA')
    first = _data(_issue(auth_client, ca, 'override-renew.unique.test'), 201)
    forced = _data(_issue(auth_client, ca, 'override-renew.unique.test', override_unique_subject=True), 201)
    assert _row(app, forced['id']).subject_holder == f"cert:{first['refid']}"
    assert [_renews(app, auth_client, held, how) for held in (first, forced, first)] == [True, True, True]
    # Still one entity: another one is refused, and the override is needed again
    assert _issue(auth_client, ca, 'override-renew.unique.test').status_code == 409


def test_an_override_on_a_subject_several_entities_carry_keeps_it_shared(app, auth_client, create_ca):
    """Nothing says which entity is attested: the new certificate is one more, each later
    issuance of the subject needs the override."""
    ca = unique_ca(app, create_ca, 'Unique override shared CA', on=False)
    first = _data(_issue(auth_client, ca, 'override-shared.unique.test'), 201)
    second = _data(_issue(auth_client, ca, 'override-shared.unique.test'), 201)
    with app.app_context():
        db.session.get(CA, ca['id']).enforce_unique_subject = True
        db.session.commit()
    after = _last_audit_id(app)
    forced = _data(_issue(auth_client, ca, 'override-shared.unique.test', override_unique_subject=True), 201)
    assert _row(app, forced['id']).subject_holder is None
    entry, = _audit(app, 'certificate.subject_override', after)
    assert entry == (f"admin issued certificate serial {forced['serial_number']} under CA Unique override "
                     f"shared CA (id={ca['id']}) with the subject CN=override-shared.unique.test, already "
                     f"carried by 2 entities (certificate serial {first['serial_number']} among them): "
                     "the subject stays shared")
    for held in (forced, second):
        assert auth_client.post(f"/api/v2/certificates/{held['id']}/renew", json={}).status_code == 409


def test_the_override_issues_and_audits_operator_subject_and_certificate(app, auth_client, create_ca):
    ca = unique_ca(app, create_ca, 'Unique override CA')
    first = _data(_issue(auth_client, ca, 'override.unique.test'), 201)
    after = _last_audit_id(app)
    issued = _data(_issue(auth_client, ca, 'override.unique.test', override_unique_subject=True), 201)
    signed = _data(_sign(auth_client, app, ca, _csr('override.unique.test', _key()),
                         override_unique_subject=True), 200)
    assert {_row(app, c['id']).subject_holder for c in (issued, signed)} == {f"cert:{first['refid']}"}
    assert _audit(app, 'certificate.subject_override', after) == [
        f"admin attested that certificate serial {c['serial_number']} under CA Unique override CA "
        f"(id={ca['id']}) with the subject CN=override.unique.test is for the same entity as the one "
        f"that already carries this subject: it takes the holder of certificate serial {first['serial_number']}"
        for c in (issued, signed)]
    # Only true asks for it
    assert _issue(auth_client, ca, 'override.unique.test', override_unique_subject='yes').status_code == 409


def _scoped_client(app, permissions):
    from models import User
    from models.api_key import APIKey
    raw = f'ucm_ak_{secrets.token_urlsafe(32)}'
    with app.app_context():
        user = User(username=f'unique-{secrets.token_hex(4)}', email=f'{secrets.token_hex(4)}@test.local',
                    password_hash='!', role='operator', active=True)
        db.session.add(user)
        db.session.flush()
        db.session.add(APIKey(user_id=user.id, key_hash=hashlib.sha256(raw.encode()).hexdigest(),
                              key_prefix=raw[:12], name='unique', permissions=json.dumps(permissions)))
        db.session.commit()
    return {'X-API-Key': raw}


def test_the_override_needs_the_permission_to_issue(app, client, create_ca):
    """The route's own write:certificates requirement: the override adds no check of its own."""
    ca = unique_ca(app, create_ca, 'Unique override perm CA')
    headers = _scoped_client(app, ['read:certificates', 'write:csrs'])
    r = client.post('/api/v2/certificates', headers=headers, json={
        'cn': 'perm.unique.test', 'ca_id': ca['id'], 'override_unique_subject': True})
    assert r.status_code == 403


def test_an_approved_request_is_checked_again_at_approval(app, auth_client, create_ca, caplog):
    """The subject was free when the CSR was queued, taken when it is approved: a refusal the
    approver is told about, logged as a warning, not a failure with its trace."""
    import logging
    from models.policy import ApprovalRequest
    from tests.protocol_approval_support import approval_policy
    ca = unique_ca(app, create_ca, 'Unique approval CA')
    operator = _scoped_client(app, ['read:csrs', 'write:csrs', 'read:certificates', 'write:certificates'])
    with approval_policy(app, ca['id'], 'unique-held-csr') as pid:
        csr_id = _csr_row(app, _csr('held.unique.test', _key()))
        r = app.test_client().post(f'/api/v2/csrs/{csr_id}/sign', headers=operator,
                                   json={'ca_id': ca['id'], 'validity_days': 30})
        assert r.status_code == 200 and r.get_json()['data']['approval_required'], r.get_json()
        first = _data(_issue(auth_client, ca, 'held.unique.test'), 201)  # admins bypass the policy
        with app.app_context():
            approval_id = ApprovalRequest.query.filter_by(policy_id=pid).one().id
        with caplog.at_level(logging.WARNING, logger='api.v2.policies'):
            r = auth_client.post(f'/api/v2/approvals/{approval_id}/approve', json={'comment': 'ok'})
        logged = [(rec.levelname, rec.exc_info is not None) for rec in caplog.records
                  if rec.name == 'api.v2.policies' and f'approval #{approval_id}' in rec.getMessage()]
        assert logged == [('WARNING', False)], logged
        body = r.get_json()
        assert r.status_code == 200 and body['data'].get('certificate_issued') is not True, body
        with app.app_context():
            assert db.session.get(ApprovalRequest, approval_id).status == 'pending'
            assert db.session.get(Certificate, csr_id).crt is None
        assert any(f"already carried by certificate serial {first['serial_number']}" in d
                   for d in _audit(app, 'approval_issue_failed'))


def test_an_approved_manual_issuance_is_checked_again_at_approval(app, auth_client, create_ca):
    from models.policy import ApprovalRequest
    from tests.protocol_approval_support import approval_policy
    ca = unique_ca(app, create_ca, 'Unique manual approval CA')
    operator = _scoped_client(app, ['read:certificates', 'write:certificates'])
    with approval_policy(app, ca['id'], 'unique-held-manual') as pid:
        r = app.test_client().post('/api/v2/certificates', headers=operator, json={
            'cn': 'held-manual.unique.test', 'ca_id': ca['id'], 'validity_days': 30})
        assert r.status_code == 200 and r.get_json()['data']['approval_required'], r.get_json()
        first = _data(_issue(auth_client, ca, 'held-manual.unique.test'), 201)
        with app.app_context():
            approval_id = ApprovalRequest.query.filter_by(policy_id=pid).one().id
        r = auth_client.post(f'/api/v2/approvals/{approval_id}/approve', json={'comment': 'ok'})
        assert r.status_code == 200 and r.get_json()['data'].get('certificate_issued') is not True
        with app.app_context():
            assert db.session.get(ApprovalRequest, approval_id).status == 'pending'
        assert _state(app, ca)[0] == 1
        assert any(f"already carried by certificate serial {first['serial_number']}" in d
                   for d in _audit(app, 'approval_issue_failed'))


def test_an_mtls_certificate_is_its_user_s(app, create_ca):
    """The service the mTLS routes call records the UCM user the certificate is for."""
    from services.cert.unique_subject import SubjectTaken
    from services.cert_service import CertificateService
    ca = unique_ca(app, create_ca, 'Unique mTLS CA')
    with app.app_context():
        for _ in range(2):
            CertificateService.create_certificate(descr='mtls', caref=ca['refid'], dn={'CN': 'bob@mtls'},
                                                  validity_days=30, subject_holder='user:41')
        with pytest.raises(SubjectTaken):
            CertificateService.create_certificate(descr='mtls', caref=ca['refid'], dn={'CN': 'bob@mtls'},
                                                  validity_days=30, subject_holder='user:42')
        assert Certificate.query.filter_by(caref=ca['refid']).count() == 2


# --- Concurrency ---------------------------------------------------------------------------------

def _race(app, ca_id, monkeypatch, second_ca_id=None):
    """Two entities ask for one subject at once, each on its own connection; the first holds the
    CA lock until the second is on its way."""
    from services.ca import ca_signing
    from services.ca_service import CAService
    paused, release, outcome = threading.Event(), threading.Event(), {}
    bump = ca_signing.next_ca_serial

    def hold_after_the_lock(ca):
        count = bump(ca)
        if threading.current_thread().name == 'first':
            paused.set()
            release.wait(30)
        return count
    monkeypatch.setattr(ca_signing, 'next_ca_serial', hold_after_the_lock)

    def request(name):
        try:
            with app.app_context():
                signer = ca_id if name == 'first' else (second_ca_id or ca_id)
                CAService.sign_csr_from_crypto(db.session.get(CA, signer), _csr('race.unique.test', _key()),
                                               validity_days=30, source='test')
            outcome[name] = 'issued'
        except Exception as e:  # noqa: BLE001
            outcome[name] = repr(e)
        finally:
            paused.set()
    first = threading.Thread(target=request, args=('first',), name='first')
    first.start()
    assert paused.wait(30)
    second = threading.Thread(target=request, args=('second',), name='second')
    second.start()
    return first, second, release, outcome


@contextlib.contextmanager
def _database_on_two_connections(app, path):
    """SQLite: the session database copied to a file the app then opens one connection per
    thread on (the in-memory one is a single shared connection); PostgreSQL already does."""
    from tests.test_revocation_record_rule import _on_postgresql
    if _on_postgresql(app):
        yield
        return
    from sqlalchemy import create_engine
    with app.app_context():
        db.session.commit()
        db.session.remove()
        engines = db._app_engines[app]
        memory = engines[None]
        raw = memory.raw_connection()
        try:
            target = sqlite3.connect(path)
            raw.driver_connection.backup(target)
            target.close()
        finally:
            raw.close()
        engines[None] = create_engine(f'sqlite:///{path}', connect_args={'timeout': 30})
    try:
        yield
    finally:
        with app.app_context():
            db.session.remove()
            engines[None].dispose()
            engines[None] = memory


def test_two_entities_at_once_get_one_certificate(app, create_ca, monkeypatch, tmp_path):
    """Never two: PostgreSQL waits on the CA row, SQLite on the database write lock."""
    from tests.test_revocation_record_rule import _on_postgresql, _wait_for_a_lock_waiter
    ca = unique_ca(app, create_ca, 'Unique race CA')
    with _database_on_two_connections(app, tmp_path / 'race.db'):
        first, second, release, outcome = _race(app, ca['id'], monkeypatch)
        if _on_postgresql(app):
            with app.app_context():
                with db.engine.connect() as conn:
                    assert _wait_for_a_lock_waiter(conn, 10)
        else:
            time.sleep(1)  # the second reaches its write and waits on the lock
        release.set()
        for thread in (first, second):
            thread.join(60)
        assert outcome['first'] == 'issued', outcome
        # PostgreSQL re-reads after the lock wait and refuses the subject; SQLite refuses the
        # second write transaction itself (its reads began before the first commit)
        assert ('SubjectTaken' if _on_postgresql(app) else 'database is locked') in outcome['second'], outcome
        with app.app_context():
            assert Certificate.query.filter_by(caref=ca['refid']).count() == 1


# --- The issuer, not the record (RFC 5280 §4.1.2.6) ---------------------------------------------

@pytest.fixture
def twins(app):
    """Root B and its cross-certificate by root A, two records of one issuer, both holding B's key:
    ``(root B id, cross record id)``, the root first (the lower id)."""
    from tests.test_backfill_cross_dupes import _cert, _row
    key_a, key_b = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
    tag = secrets.token_hex(3)
    with app.app_context():
        root_a = _row(_cert(key_a, f'Unique Root A {tag}'), key_a)
        root_b = _row(_cert(key_b, f'Unique Root B {tag}'), key_b)
        cross = _row(_cert(key_b, f'Unique Root B {tag}', key_a, f'Unique Root A {tag}'), key_b,
                     caref=db.session.get(CA, root_a).refid)
        assert root_b < cross
    yield root_b, cross
    with app.app_context():
        db.session.rollback()
        rows = [db.session.get(CA, ca_id) for ca_id in (cross, root_b, root_a)]
        Certificate.query.filter(Certificate.caref.in_([r.refid for r in rows])).delete(
            synchronize_session=False)
        for row in rows:
            db.session.delete(row)
        db.session.commit()


def _trunk_issue(app, ca_id, cn):
    from services.ca_service import CAService
    with app.app_context():
        CAService.sign_csr_from_crypto(db.session.get(CA, ca_id), _csr(cn, _key()), validity_days=30,
                                       source='test')


@pytest.mark.parametrize('enforcing', ['root', 'cross'])
def test_a_root_and_its_cross_certificate_share_their_subjects(app, twins, enforcing):
    """The option on one record counts the certificates of both; off on the other, it issues."""
    from services.cert.unique_subject import SubjectTaken
    root, cross = twins
    on, off = (root, cross) if enforcing == 'root' else (cross, root)
    with app.app_context():
        db.session.get(CA, on).enforce_unique_subject = True
        db.session.commit()
    _trunk_issue(app, off, f'twin-{enforcing}.unique.test')
    with pytest.raises(SubjectTaken):
        _trunk_issue(app, on, f'twin-{enforcing}.unique.test')
    _trunk_issue(app, off, f'twin-{enforcing}.unique.test')  # the record without the option
    with app.app_context():
        from services.cert.unique_subject import shared_subjects
        assert [s['subject'] for s in shared_subjects(db.session.get(CA, on))] == [
            f'CN=twin-{enforcing}.unique.test']


def test_two_twin_records_at_once_get_one_certificate(app, twins, monkeypatch, tmp_path):
    """The issuance by the cross record waits on the root's row, the lowest of the twins (PostgreSQL);
    SQLite serialises every write anyway."""
    from tests.test_revocation_record_rule import _on_postgresql, _wait_for_a_lock_waiter
    root, cross = twins
    with app.app_context():
        for ca_id in twins:
            db.session.get(CA, ca_id).enforce_unique_subject = True
        db.session.commit()
        refids = [db.session.get(CA, ca_id).refid for ca_id in twins]
    with _database_on_two_connections(app, tmp_path / 'twins.db'):
        first, second, release, outcome = _race(app, root, monkeypatch, second_ca_id=cross)
        if _on_postgresql(app):
            with app.app_context():
                with db.engine.connect() as conn:
                    assert _wait_for_a_lock_waiter(conn, 10)
        else:
            time.sleep(1)
        release.set()
        for thread in (first, second):
            thread.join(60)
        assert outcome['first'] == 'issued', outcome
        assert ('SubjectTaken' if _on_postgresql(app) else 'database is locked') in outcome['second'], outcome
        with app.app_context():
            assert Certificate.query.filter(Certificate.caref.in_(refids)).count() == 1


# --- CA API --------------------------------------------------------------------------------------

def test_the_option_is_read_written_and_audited(app, auth_client, create_ca):
    ca = create_ca(cn='Unique API CA')
    after = _last_audit_id(app)
    for field, value in (('enforceUniqueSubject', True), ('enforce_unique_subject', False)):
        data = _data(auth_client.patch(f"/api/v2/cas/{ca['id']}", json={field: value}), 200)
        assert data['enforce_unique_subject'] is value
        assert _data(auth_client.get(f"/api/v2/cas/{ca['id']}"), 200)['enforce_unique_subject'] is value
    assert _audit(app, 'ca_updated', after) == [
        'CA Unique API CA updated: unique subject enforced',
        'CA Unique API CA updated: unique subject no longer enforced']
    r = auth_client.patch(f"/api/v2/cas/{ca['id']}", json={'enforceUniqueSubject': 'yes'})
    assert r.status_code == 400 and r.get_json()['message'] == 'enforceUniqueSubject must be true or false'


def test_turning_it_on_counts_the_subjects_already_shared(app, auth_client, create_ca):
    """Allowed, as in EJBCA: the rule applies to the next issuance only."""
    ca = create_ca(cn='Unique shared CA')
    serials = {}
    for cn in ('a.shared.test', 'a.shared.test', 'b.shared.test', 'b.shared.test', 'c.shared.test'):
        serials.setdefault(cn, []).append(_data(_issue(auth_client, ca, cn), 201)['serial_number'])
    key = _key()
    for _ in range(2):  # one entity: its key
        _data(_sign(auth_client, app, ca, _csr('d.shared.test', key)), 200)
    data = _data(auth_client.patch(f"/api/v2/cas/{ca['id']}", json={'enforceUniqueSubject': True}), 200)
    assert data['shared_subjects'] == 2
    assert data['shared_subject_examples'] == [
        {'subject': f'CN={cn}', 'serial_numbers': serials[cn]} for cn in ('a.shared.test', 'b.shared.test')]
    data = _data(auth_client.patch(f"/api/v2/cas/{ca['id']}", json={'enforceUniqueSubject': True}), 200)
    assert 'shared_subjects' not in data and 'shared_subject_examples' not in data


def test_the_shared_subject_examples_stop_at_twenty(app, auth_client, create_ca):
    ca = create_ca(cn='Unique shared many CA')
    for index in range(21):
        for _ in range(2):
            _data(_issue(auth_client, ca, f'{index}.many.shared.test'), 201)
    data = _data(auth_client.patch(f"/api/v2/cas/{ca['id']}", json={'enforceUniqueSubject': True}), 200)
    assert data['shared_subjects'] == 21
    assert [e['subject'] for e in data['shared_subject_examples']] == [
        f'CN={index}.many.shared.test' for index in range(20)]


def test_backups_export_the_option_and_the_holder(app, auth_client, create_ca):
    from services.backup.backup_service import BackupService
    ca = unique_ca(app, create_ca, 'Unique backup CA')
    issued = _data(_issue(auth_client, ca, 'backup.unique.test'), 201)
    with app.app_context():
        db.session.get(Certificate, issued['id']).subject_holder = 'acme:backup'
        db.session.commit()
        exported = next(r for r in BackupService()._export_cas(True) if r['refid'] == ca['refid'])
        cert = next(r for r in BackupService()._export_certificates(True) if r['refid'] == issued['refid'])
    assert exported['enforce_unique_subject'] is True and cert['subject_holder'] == 'acme:backup'


# --- Migration -----------------------------------------------------------------------------------

def _step():
    import importlib
    return importlib.import_module('migrations._from_2_254.157_certificate_subject_key')


def test_the_upgrade_step_adds_the_option_off_and_the_acme_holders(app):
    conn = sqlite3.connect(':memory:')
    conn.executescript(
        "CREATE TABLE certificates (id INTEGER PRIMARY KEY, refid VARCHAR(36), caref VARCHAR(36), crt TEXT,"
        " related_certificate_id INTEGER, hybrid_role VARCHAR(16));"
        "CREATE TABLE certificate_authorities (id INTEGER PRIMARY KEY, refid VARCHAR(36));"
        "CREATE TABLE acme_orders (id INTEGER PRIMARY KEY, account_id VARCHAR(64), certificate_id INTEGER);"
        "INSERT INTO certificates (id, refid, related_certificate_id, hybrid_role) VALUES (1, 'r1', NULL, NULL),"
        " (2, 'r2', NULL, NULL), (3, 'r3', 4, 'classical'), (4, 'r4', 3, 'pq'), (5, 'r5', 9, 'pq');"
        "INSERT INTO certificate_authorities (id, refid) VALUES (1, 'ca');"
        "INSERT INTO acme_orders (id, account_id, certificate_id) VALUES (5, 'acct-b', 1), (4, 'acct-a', 1),"
        " (6, 'acct-c', 2);")
    for _ in range(2):
        _step().upgrade(conn)
    # 1: the lowest order's account; 4: B of the pair names A (3); 5 names a row that is gone
    assert conn.execute('SELECT id, subject_holder FROM certificates ORDER BY id').fetchall() == [
        (1, 'acme:acct-a'), (2, 'acme:acct-c'), (3, None), (4, 'cert:r3'), (5, None)]
    assert conn.execute('SELECT enforce_unique_subject FROM certificate_authorities').fetchall() == [(0,)]


@pytest.mark.postgres
def test_the_upgrade_step_on_postgresql():
    import os
    from sqlalchemy import create_engine, inspect, text
    url = os.getenv('UCM_TEST_PG_URL')
    if not url:
        pytest.skip('UCM_TEST_PG_URL not set')
    engine = create_engine(url)
    schema = f'unique_{secrets.token_hex(4)}'
    try:
        with engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA {schema}'))
            conn.execute(text(f'SET search_path TO {schema}'))
            conn.execute(text("CREATE TABLE certificates (id INTEGER PRIMARY KEY, refid VARCHAR(36), "
                              "caref VARCHAR(36), crt TEXT, related_certificate_id INTEGER, "
                              "hybrid_role VARCHAR(16))"))
            conn.execute(text("CREATE TABLE certificate_authorities (id INTEGER PRIMARY KEY)"))
            conn.execute(text("CREATE TABLE acme_orders (id INTEGER PRIMARY KEY, account_id VARCHAR(64), "
                              "certificate_id INTEGER)"))
            conn.execute(text("INSERT INTO certificates (id, refid, related_certificate_id, hybrid_role) "
                              "VALUES (1, 'r1', NULL, NULL), (2, 'r2', 3, 'classical'), (3, 'r3', 2, 'pq')"))
            conn.execute(text("INSERT INTO certificate_authorities (id) VALUES (1)"))
            conn.execute(text("INSERT INTO acme_orders VALUES (1, 'acct-a', 1)"))
            for _ in range(2):
                _step().upgrade(conn)
            assert conn.execute(text('SELECT id, subject_holder FROM certificates ORDER BY id')).fetchall() == [
                (1, 'acme:acct-a'), (2, None), (3, 'cert:r2')]
            assert conn.execute(text('SELECT enforce_unique_subject FROM certificate_authorities')).scalar() is False
            assert inspect(conn).get_columns('certificates', schema=schema)
    finally:
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
        engine.dispose()
