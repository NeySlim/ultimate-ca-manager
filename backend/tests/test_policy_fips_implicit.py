"""FIPS mode adds a system policy ahead of every issuance policy (#399).

Key types are the registry's FIPS-approved labels, digests SHA-256/384/512.
It only narrows: the operator's policies still apply, and a policy allowing
Ed25519 or Ed448 cannot be saved. Every issuance path refuses an Ed25519 key.
"""
import base64
import json
import uuid

import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed448, ed25519, rsa
from cryptography.x509.oid import NameOID

import fips_mode
from models import CA, Certificate, db
from models.policy import ApprovalRequest, CertificatePolicy
from services.policy_service import POLICY_DIGESTS, PolicyEvaluationService, PolicyViolation
from tests.conftest import get_json
from utils import key_algorithms

CONTENT_JSON = 'application/json'
FIPS_LABELS = sorted(key_algorithms.fips_approved_labels())
SYSTEM_POLICY = 'FIPS mode'


@pytest.fixture
def fips(monkeypatch):
    """Call it to turn simulated FIPS mode on, after the test's own setup."""
    return lambda: monkeypatch.setattr(fips_mode, 'enabled', lambda: True)


def _policy(app, name, ca_id=None, rules=None, requires_approval=False):
    with app.app_context():
        pol = CertificatePolicy(name=name, policy_type='issuance', ca_id=ca_id,
                                requires_approval=requires_approval, min_approvers=1,
                                is_active=True, priority=100)
        pol.set_rules(rules or {})
        db.session.add(pol)
        db.session.commit()
        return pol.id


def _drop(app, model, *ids):
    with app.app_context():
        for row_id in ids:
            row = db.session.get(model, row_id)
            if row is not None:
                db.session.delete(row)
        db.session.commit()


def _ed25519():
    return ed25519.Ed25519PrivateKey.generate()


def _rsa1024():
    return rsa.generate_private_key(public_exponent=65537, key_size=1024)


def _csr(key=None, cn='fips.policy.test'):
    key = key or rsa.generate_private_key(public_exponent=65537, key_size=2048)
    algorithm = None if isinstance(key, (ed25519.Ed25519PrivateKey, ed448.Ed448PrivateKey)) \
        else hashes.SHA256()
    return (x509.CertificateSigningRequestBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(cn)]), critical=False)
            .sign(key, algorithm))


def _store_csr(app, csr, descr='fips-csr'):
    with app.app_context():
        row = Certificate(refid=str(uuid.uuid4()), descr=descr,
                          csr=base64.b64encode(csr.public_bytes(serialization.Encoding.PEM)).decode(),
                          source='manual')
        db.session.add(row)
        db.session.commit()
        return row.id


def _ca_refid(app, ca_id):
    with app.app_context():
        return db.session.get(CA, ca_id).refid


class TestSystemPolicy:

    def test_rules_refuse_what_fips_does_not_approve(self, fips):
        fips()
        for label in ('ED25519', 'ED448', 'RSA-1024'):
            v, _, _ = PolicyEvaluationService.enforce_rules([], key_type=label)
            assert len(v) == 1 and SYSTEM_POLICY in v[0] and label in v[0], (label, v)
        for digest in ('sha1', 'sha224', 'md5'):
            v, _, _ = PolicyEvaluationService.enforce_rules([], digest=digest)
            assert len(v) == 1 and SYSTEM_POLICY in v[0], (digest, v)
        for label in FIPS_LABELS:
            assert PolicyEvaluationService.enforce_rules([], key_type=label)[0] == []
        for digest in POLICY_DIGESTS:
            assert PolicyEvaluationService.enforce_rules([], digest=digest)[0] == []

    def test_absent_outside_fips(self, app):
        assert PolicyEvaluationService.enforce_rules([], key_type='ED25519')[0] == []
        with app.app_context():
            assert all(p.name != SYSTEM_POLICY
                       for p in PolicyEvaluationService.applicable_policies(None))

    def test_heads_the_applicable_policies_once(self, app, fips, create_ca):
        ca = create_ca(cn='FIPS head CA')
        pid = _policy(app, 'fips-head', ca['id'], {'allowed_key_types': ['RSA-2048']})
        fips()
        try:
            with app.app_context():
                policies = PolicyEvaluationService.applicable_policies(ca['id'])
                assert policies[0].name == SYSTEM_POLICY
                assert [p.name for p in policies].count(SYSTEM_POLICY) == 1
                assert 'fips-head' in [p.name for p in policies]
                # Passing them on to the rules does not add it a second time
                v, _, _ = PolicyEvaluationService.enforce_rules(policies, key_type='ED25519')
                assert len(v) == 2 and SYSTEM_POLICY in v[0] and 'fips-head' in v[1]
        finally:
            _drop(app, CertificatePolicy, pid)

    def test_operator_policies_still_narrow(self, app, fips, create_ca):
        ca = create_ca(cn='FIPS narrow CA')
        pid = _policy(app, 'fips-narrow', ca['id'], {'allowed_key_types': ['EC-P384']})
        fips()
        try:
            with app.app_context():
                policies = PolicyEvaluationService.applicable_policies(ca['id'])
                v, _, _ = PolicyEvaluationService.enforce_rules(policies, key_type='RSA-2048')
                assert len(v) == 1 and 'fips-narrow' in v[0]
        finally:
            _drop(app, CertificatePolicy, pid)

    def test_implicit_digest_stays_sha256(self, app, fips, create_ca):
        ca = create_ca(cn='FIPS digest CA')
        fips()
        with app.app_context():
            policies = PolicyEvaluationService.applicable_policies(ca['id'])
            assert PolicyEvaluationService.choose_digest(policies, 'sha256') == 'sha256'
            key = ec.generate_private_key(ec.SECP256R1())
            sign_hash, v = PolicyEvaluationService.checked_signing_hash(
                policies, key, 'sha224', key_type='EC-P256')
            # SHA-224 is no signature hash of UCM's any more: refused before any policy
            assert len(v) == 1 and 'Unsupported signature hash: sha224' in v[0]


class TestPolicyApi:

    def test_effective_without_any_policy(self, app, auth_client, fips, create_ca):
        ca = create_ca(cn='FIPS effective CA')
        fips()
        data = get_json(auth_client.get(f"/api/v2/policies/effective?ca_id={ca['id']}"))['data']
        assert data == {'allowed_key_types': FIPS_LABELS,
                        'allowed_digests': list(POLICY_DIGESTS), 'fips': True}

    def test_effective_intersects_with_the_operator_policies(self, app, auth_client, fips, create_ca):
        ca = create_ca(cn='FIPS effective intersect CA')
        # Saved before FIPS mode was turned on
        pid = _policy(app, 'fips-eff', ca['id'], {'allowed_key_types': ['ED25519', 'EC-P384'],
                                                  'allowed_digests': ['sha384']})
        fips()
        try:
            data = get_json(auth_client.get(f"/api/v2/policies/effective?ca_id={ca['id']}"))['data']
            assert data == {'allowed_key_types': ['EC-P384'], 'allowed_digests': ['sha384'],
                            'fips': True}
        finally:
            _drop(app, CertificatePolicy, pid)

    @pytest.mark.parametrize('label', ['ED25519', 'ed448'])
    def test_policy_allowing_edwards_keys_is_refused(self, app, auth_client, fips, label):
        fips()
        r = auth_client.post('/api/v2/policies', content_type=CONTENT_JSON, data=json.dumps({
            'name': f'fips-edwards-{label}', 'is_active': False,
            'rules': {'allowed_key_types': ['RSA-2048', label]}}))
        assert r.status_code == 400, r.data
        body = get_json(r)
        assert body['type'] == fips_mode.PROBLEM_TYPE and label.upper() in body['detail']
        with app.app_context():
            assert CertificatePolicy.query.filter_by(name=f'fips-edwards-{label}').first() is None

    def test_update_allowing_ed25519_changes_nothing(self, app, auth_client, fips):
        pid = _policy(app, 'fips-update', None, {'allowed_key_types': ['RSA-2048']})
        with app.app_context():
            db.session.get(CertificatePolicy, pid).is_active = False
            db.session.commit()
        fips()
        try:
            r = auth_client.put(f'/api/v2/policies/{pid}', content_type=CONTENT_JSON, data=json.dumps({
                'name': 'fips-update-renamed', 'rules': {'allowed_key_types': ['ED25519']}}))
            assert r.status_code == 400 and get_json(r)['type'] == fips_mode.PROBLEM_TYPE
            with app.app_context():
                row = db.session.get(CertificatePolicy, pid)
                assert row.name == 'fips-update' and row.get_rules()['allowed_key_types'] == ['RSA-2048']
            r = auth_client.put(f'/api/v2/policies/{pid}', content_type=CONTENT_JSON, data=json.dumps({
                'rules': {'allowed_key_types': ['EC-P256']}}))
            assert r.status_code == 200, r.data
        finally:
            _drop(app, CertificatePolicy, pid)


class TestEveryIssuancePath:
    """No policy in the database: the system policy alone refuses."""

    def test_sign_csr_route(self, app, auth_client, fips, create_ca):
        ca = create_ca(cn='FIPS sign CSR CA')
        ed_id = _store_csr(app, _csr(_ed25519(), cn='ed.sign.fips.test'))
        weak_id = _store_csr(app, _csr(_rsa1024(), cn='weak.sign.fips.test'))
        ok_id = _store_csr(app, _csr(cn='ok.sign.fips.test'))
        fips()
        try:
            for csr_id, label in ((ed_id, b'ED25519'), (weak_id, b'RSA-1024')):
                r = auth_client.post(f'/api/v2/csrs/{csr_id}/sign', content_type=CONTENT_JSON,
                                     data=json.dumps({'ca_id': ca['id']}))
                assert r.status_code == 400 and label in r.data and b'FIPS mode' in r.data, r.data
            r = auth_client.post(f'/api/v2/csrs/{ok_id}/sign', content_type=CONTENT_JSON,
                                 data=json.dumps({'ca_id': ca['id']}))
            assert r.status_code in (200, 201), r.data
        finally:
            _drop(app, Certificate, ed_id, weak_id)

    def test_bulk_sign_route(self, app, auth_client, fips, create_ca):
        ca = create_ca(cn='FIPS bulk CA')
        ed_id = _store_csr(app, _csr(_ed25519(), cn='ed.bulk.fips.test'))
        fips()
        try:
            r = auth_client.post('/api/v2/csrs/bulk/sign', content_type=CONTENT_JSON,
                                 data=json.dumps({'ids': [ed_id], 'ca_id': ca['id']}))
            failed = get_json(r)['data']['failed']
            assert [f['id'] for f in failed] == [ed_id] and 'FIPS mode' in failed[0]['error']
        finally:
            _drop(app, Certificate, ed_id)

    def test_service_sign_csr_acme(self, app, fips, create_ca):
        # The ACME finalize signs through CertificateService.sign_csr
        from services.cert_service import CertificateService
        ca = create_ca(cn='FIPS ACME CA')
        ed_id = _store_csr(app, _csr(_ed25519(), cn='ed.acme.fips.test'))
        fips()
        try:
            with app.app_context():
                with pytest.raises(PolicyViolation, match='ED25519.*FIPS mode'):
                    CertificateService.sign_csr(cert_id=ed_id, caref=_ca_refid(app, ca['id']),
                                                validity_days=30, digest='sha256',
                                                digest_explicit=False)
                db.session.rollback()
        finally:
            _drop(app, Certificate, ed_id)

    def test_trunk_without_policy_scope(self, app, fips, create_ca):
        from services.hsm.ca_key_loader import get_ca_signing_key
        from services.trust_store import TrustStoreService
        ca = create_ca(cn='FIPS trunk CA')
        fips()
        with app.app_context():
            row = db.session.get(CA, ca['id'])
            ca_cert = x509.load_pem_x509_certificate(base64.b64decode(row.crt), default_backend())
            with pytest.raises(PolicyViolation, match='FIPS mode'):
                TrustStoreService.sign_csr(
                    csr_pem=_csr(_ed25519()).public_bytes(serialization.Encoding.PEM),
                    ca_cert=ca_cert, ca_private_key=get_ca_signing_key(row), validity_days=30)

    def test_certificate_creation(self, app, auth_client, fips, create_ca):
        from services.cert_service import CertificateService
        ca = create_ca(cn='FIPS create CA')
        fips()
        with app.app_context():
            ref = _ca_refid(app, ca['id'])
            for key_type in ('ED25519', 'ED448'):
                with pytest.raises(PolicyViolation, match=f'{key_type}.*FIPS mode'):
                    CertificateService.create_certificate(
                        descr='fips-create', caref=ref, dn={'CN': 'create.fips.test'},
                        cert_type='usr_cert', key_type=key_type)
                db.session.rollback()
        # An approved key still issues through the form
        r = auth_client.post('/api/v2/certificates', content_type=CONTENT_JSON, data=json.dumps({
            'cn': 'form.fips.test', 'ca_id': ca['id'], 'key_type': 'rsa', 'key_size': 2048,
            'validity_days': 30, 'cert_type': 'server'}))
        assert r.status_code in (200, 201), r.data

    def test_renewal(self, app, fips, create_ca, monkeypatch):
        from services.cert import renewal
        from services.cert_service import CertificateService
        ca = create_ca(cn='FIPS renewal CA')
        from utils.key_codec import store_pem_bytes
        key = _ed25519()
        cert_id = _store_csr(app, _csr(key, cn='ed.renew.fips.test'))
        with app.app_context():
            CertificateService.sign_csr(cert_id=cert_id, caref=_ca_refid(app, ca['id']),
                                        validity_days=30)
            # Issued before FIPS mode, key held by the server
            db.session.get(Certificate, cert_id).prv = store_pem_bytes(key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption()))
            db.session.commit()
        fips()

        def _no_key(*args, **kwargs):
            raise AssertionError('a key was generated for a refused renewal')
        # Every generator a renewal can reach: the registry and the EdDSA classes
        monkeypatch.setattr(key_algorithms.KeyAlgorithm, 'generate', _no_key)
        monkeypatch.setattr(ed25519.Ed25519PrivateKey, 'generate', _no_key)
        monkeypatch.setattr(ed448.Ed448PrivateKey, 'generate', _no_key)
        try:
            with app.app_context():
                with pytest.raises(renewal.RenewalError, match='(?i)ED25519.*FIPS mode'):
                    renewal.renew_certificate_in_place(db.session.get(Certificate, cert_id))
                db.session.rollback()
                with pytest.raises(renewal.RenewalError, match='(?i)ED25519.*FIPS mode'):
                    renewal.renew_certificate_in_place(db.session.get(Certificate, cert_id),
                                                       rekey=False)
                db.session.rollback()
        finally:
            _drop(app, Certificate, cert_id)

    def test_ca_creation(self, app, auth_client, fips, monkeypatch):
        from services.ca.ca_creation import CACreationMixin

        def _no_key(*args, **kwargs):
            raise AssertionError('a key was generated for a refused CA')
        fips()
        monkeypatch.setattr(CACreationMixin, '_resolve_signing_key', staticmethod(_no_key))
        with app.app_context():
            with pytest.raises(PolicyViolation, match='ED25519.*FIPS mode'):
                CACreationMixin.create_internal_ca(
                    descr='fips ed root', dn={'CN': 'fips ed root'},
                    hsm_provider_id=1, hsm_key_label='fips-ed', hsm_key_algorithm='ED25519')
            db.session.rollback()
            with pytest.raises(PolicyViolation, match='ED25519.*FIPS mode'):
                CACreationMixin.create_external_ca(
                    descr='fips ed pending', dn={'CN': 'fips ed pending'},
                    hsm_provider_id=1, hsm_key_label='fips-ed2', hsm_key_algorithm='ED25519')
            db.session.rollback()

    def test_est(self, app, fips, create_ca):
        from services.ca_service import CAService
        ca = create_ca(cn='FIPS EST CA')
        fips()
        with app.app_context():
            ca_row = db.session.get(CA, ca['id'])
            with pytest.raises(PolicyViolation, match='ED25519.*FIPS mode'):
                CAService.sign_csr_from_crypto(ca=ca_row, csr=_csr(_ed25519()), validity_days=30,
                                               source='est')
            db.session.rollback()
            pem, _ = CAService.sign_csr_from_crypto(ca=ca_row, csr=_csr(cn='ok.est.fips.test'),
                                                    validity_days=30, source='est')
            assert x509.load_pem_x509_certificate(pem.encode()).signature_hash_algorithm.name == 'sha256'

    def test_wstep(self, app, fips, create_ca):
        from services.wstep import wstep_service
        ca = create_ca(cn='FIPS WSTEP CA')
        fips()
        with app.app_context():
            ca_row = db.session.get(CA, ca['id'])
            der = _csr(_ed25519(), cn='ed.wstep.fips.test').public_bytes(serialization.Encoding.DER)
            cert_pem, err = wstep_service.issue(ca_row, der, 30)
            assert cert_pem is None and err.startswith('Policy violation') and 'FIPS mode' in err, err

    def test_scep(self, app, fips, create_ca):
        from services.scep.scep_service import SCEPService
        ca = create_ca(cn='FIPS SCEP CA')
        fips()
        with app.app_context():
            svc = SCEPService(_ca_refid(app, ca['id']))
            _, v = svc._policy_signing_hash(_csr(_ed25519()))
            assert len(v) == 1 and 'ED25519' in v[0] and SYSTEM_POLICY in v[0]
            assert svc._policy_signing_hash(_csr())[1] == []

    def test_scep_manual_approval(self, app, auth_client, fips, create_ca):
        from models import SCEPRequest
        ca = create_ca(cn='FIPS SCEP approve CA')
        with app.app_context():
            req = SCEPRequest(transaction_id=f'txn-fips-{uuid.uuid4().hex[:8]}',
                              ca_refid=_ca_refid(app, ca['id']),
                              csr=base64.b64encode(_csr(_ed25519()).public_bytes(
                                  serialization.Encoding.DER)).decode(),
                              status='pending', subject='CN=fips.policy.test')
            db.session.add(req)
            db.session.commit()
            req_id = req.id
        fips()
        try:
            r = auth_client.post(f'/api/v2/scep/{req_id}/approve', data='{}', content_type=CONTENT_JSON)
            assert r.status_code == 400 and b'ED25519' in r.data and b'FIPS mode' in r.data, r.data
        finally:
            _drop(app, SCEPRequest, req_id)

    def test_csr_approval(self, app, auth_client, fips, create_ca, create_user):
        # Queued before FIPS mode was turned on, approved after
        ca = create_ca(cn='FIPS approval CA')
        pid = _policy(app, f'fips-approval-{ca["id"]}', ca['id'], requires_approval=True)
        csr_id = _store_csr(app, _csr(_ed25519(), cn='ed.approval.fips.test'))
        user = create_user(username=f'fips-op-{uuid.uuid4().hex[:6]}', role='operator')
        operator = app.test_client()
        r = operator.post('/api/v2/auth/login', content_type=CONTENT_JSON, data=json.dumps(
            {'username': user['username'], 'password': 'TestPass123!'}))
        assert r.status_code == 200, r.data
        try:
            r = operator.post(f'/api/v2/csrs/{csr_id}/sign', content_type=CONTENT_JSON,
                              data=json.dumps({'ca_id': ca['id'], 'validity_days': 30}))
            assert r.status_code == 200, r.data
            approval_id = get_json(r)['data']['approval_id']
            fips()
            r = auth_client.post(f'/api/v2/approvals/{approval_id}/approve', content_type=CONTENT_JSON,
                                 data=json.dumps({'comment': 'ok'}))
            data = get_json(r)['data']
            assert data['certificate_issued'] is False, data
            assert 'ED25519' in data['issue_error'] and 'FIPS mode' in data['issue_error']
            with app.app_context():
                assert not db.session.get(Certificate, csr_id).crt
        finally:
            with app.app_context():
                for ap in ApprovalRequest.query.filter_by(policy_id=pid).all():
                    db.session.delete(ap)
                db.session.commit()
            _drop(app, CertificatePolicy, pid)
            _drop(app, Certificate, csr_id)
