"""Policies, compliance profiles and preflights with ML-DSA: labels the policy API reads,
key-type rules on every issuance path, no digest rule on a key that takes none, the
ml_dsa signature scheme, pq_standalone on a real ML-DSA CA, and the scores."""
import base64
import json
import uuid

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, mldsa, rsa
from cryptography.x509.oid import NameOID

import fips_mode
from models import CA, Certificate, User, db
from models.certificate_template import CertificateTemplate
from models.policy import ApprovalRequest, CertificatePolicy
from services.policy_service import PolicyEvaluationService, PolicyViolation
from tests.conftest import get_json
from utils import key_algorithms

pytestmark = pytest.mark.skipif(not key_algorithms.mldsa_supported(),
                                reason='this build has no ML-DSA')


def _post(client, url, body):
    return client.post(url, content_type='application/json', data=json.dumps(body))


def _policy(auth_client, name, rules, ca_id=None):
    """A policy made through the API, so its labels go through the policy validation."""
    body = {'name': f'{name}-{uuid.uuid4().hex[:8]}', 'rules': rules, 'is_active': True}
    if ca_id is not None:
        body['ca_id'] = ca_id
    r = _post(auth_client, '/api/v2/policies', body)
    assert r.status_code in (200, 201), r.get_json()
    return get_json(r)['data']['id']


def _drop(app, model, *ids):
    with app.app_context():
        for row_id in ids:
            row = db.session.get(model, row_id)
            if row is not None:
                db.session.delete(row)
        db.session.commit()


def _mldsa_ca(create_ca, cn):
    return create_ca(cn=f'{cn} {uuid.uuid4().hex[:6]}', keyAlgo='ML-DSA', keySize=65)


def _issue(auth_client, ca_id, key_type, key_size, cn, **extra):
    return _post(auth_client, '/api/v2/certificates', {
        'cn': cn, 'ca_id': ca_id, 'key_type': key_type, 'key_size': key_size,
        'validity_days': 30, **extra})


def _csr(key, cn):
    algorithm = hashes.SHA256() if isinstance(key, (rsa.RSAPrivateKey, ec.EllipticCurvePrivateKey)) else None
    return (x509.CertificateSigningRequestBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(cn)]), critical=False)
            .sign(key, algorithm))


def _stored_csr(app, key, cn):
    with app.app_context():
        pem = _csr(key, cn).public_bytes(serialization.Encoding.PEM)
        row = Certificate(refid=str(uuid.uuid4()), descr=cn, source='manual',
                          csr=base64.b64encode(pem).decode())
        db.session.add(row)
        db.session.commit()
        return row.id


def _row_cert(app, model, row_id):
    with app.app_context():
        return x509.load_pem_x509_certificate(base64.b64decode(db.session.get(model, row_id).crt))


def _rsa():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


ONLY_65 = {'allowed_key_types': ['ML-DSA-65']}


# ---------------------------------------------------------------- policy API

def test_policy_api_names_ml_dsa_labels(app, auth_client):
    pid = _policy(auth_client, 'pq-labels', {
        'allowed_key_types': ['ml-dsa-65', 'mldsa87', 'EC-P256'],
        'allowed_signature_schemes': ['ml_dsa', 'ecdsa'],
        'key_type_horizons': {'ml dsa 44': '2035-12-31'},
        'pq_standalone': False})
    try:
        with app.app_context():
            rules = db.session.get(CertificatePolicy, pid).get_rules()
        assert rules['allowed_key_types'] == ['ML-DSA-65', 'ML-DSA-87', 'EC-P256']
        assert rules['allowed_signature_schemes'] == ['ml_dsa', 'ecdsa']
        assert rules['key_type_horizons'] == {'ML-DSA-44': '2035-12-31'}
    finally:
        _drop(app, CertificatePolicy, pid)
    r = _post(auth_client, '/api/v2/policies', {'name': 'pq-unknown',
                                                'rules': {'allowed_key_types': ['ML-DSA-99']}})
    assert r.status_code == 400 and b'ML-DSA-99' in r.data


def test_fips_refuses_a_policy_that_allows_ml_dsa(app, auth_client, monkeypatch):
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
    r = _post(auth_client, '/api/v2/policies', {'name': f'pq-fips-{uuid.uuid4().hex[:6]}',
                                                'rules': ONLY_65, 'ca_id': None})
    if r.status_code < 300:  # a global policy left behind would bind every later test
        _drop(app, CertificatePolicy, get_json(r)['data']['id'])
    assert r.status_code in (400, 403) and b'ML-DSA-65' in r.data, r.data


def test_effective_algorithms_list_ml_dsa_and_fips_masks_it(app, auth_client, create_ca, monkeypatch):
    ca = create_ca(cn=f'PQ effective {uuid.uuid4().hex[:6]}')
    pid = _policy(auth_client, 'pq-effective', {'allowed_key_types': ['ML-DSA-65', 'EC-P256']}, ca['id'])
    try:
        data = get_json(auth_client.get(f"/api/v2/policies/effective?ca_id={ca['id']}"))['data']
        assert data['allowed_key_types'] == ['EC-P256', 'ML-DSA-65']
        monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
        with app.app_context():
            key_types, _ = PolicyEvaluationService.effective_algorithms(ca['id'])
        assert key_types == ['EC-P256']
    finally:
        monkeypatch.undo()
        _drop(app, CertificatePolicy, pid)


# ------------------------------------------- allowed_key_types on every path

def test_direct_issuance_follows_an_ml_dsa_only_policy(app, auth_client, create_ca):
    ca = _mldsa_ca(create_ca, 'PQ direct')
    pid = _policy(auth_client, 'pq-direct', ONLY_65, ca['id'])
    try:
        r = _issue(auth_client, ca['id'], 'rsa', 2048, 'pq-direct-rsa.example.test')
        assert r.status_code == 400 and b'RSA-2048' in r.data, r.data
        r = _issue(auth_client, ca['id'], 'ml-dsa', 87, 'pq-direct-87.example.test')
        assert r.status_code == 400 and b'ML-DSA-87' in r.data, r.data
        r = _issue(auth_client, ca['id'], 'ml-dsa', 65, 'pq-direct-65.example.test')
        assert r.status_code == 201, r.get_json()
        leaf = _row_cert(app, Certificate, get_json(r)['data']['id'])
        assert isinstance(leaf.public_key(), mldsa.MLDSA65PublicKey)
    finally:
        _drop(app, CertificatePolicy, pid)


def test_signed_csr_follows_an_ml_dsa_only_policy(app, auth_client, create_ca):
    ca = _mldsa_ca(create_ca, 'PQ sign CSR')
    pid = _policy(auth_client, 'pq-csr', ONLY_65, ca['id'])
    rsa_id = _stored_csr(app, _rsa(), 'pq-csr-rsa.example.test')
    ok_id = _stored_csr(app, mldsa.MLDSA65PrivateKey.generate(), 'pq-csr-65.example.test')
    try:
        r = _post(auth_client, f'/api/v2/csrs/{rsa_id}/sign', {'ca_id': ca['id']})
        assert r.status_code == 400 and b'RSA-2048' in r.data, r.data
        r = _post(auth_client, f'/api/v2/csrs/{ok_id}/sign', {'ca_id': ca['id']})
        assert r.status_code in (200, 201), r.get_json()
        assert _row_cert(app, Certificate, ok_id).signature_hash_algorithm is None
    finally:
        _drop(app, CertificatePolicy, pid)
        _drop(app, Certificate, rsa_id)


def _approval(app, request_data):
    """An approved CSR request under its own rule-less gate policy."""
    with app.app_context():
        gate = CertificatePolicy(name=f'pq-gate-{uuid.uuid4().hex[:8]}', policy_type='issuance',
                                 requires_approval=True, min_approvers=1, is_active=False)
        db.session.add(gate)
        db.session.commit()
        requester = User.query.filter_by(role='admin').first()
        approval = PolicyEvaluationService.create_approval_request(
            policy=gate, request_data=request_data, requester_id=requester.id, request_type='csr')
        approval.status = 'approved'
        db.session.commit()
        return approval.id, gate.id


def test_approval_follows_an_ml_dsa_only_policy(app, auth_client, create_ca):
    from api.v2.policies import _issue_approved_certificate
    ca = _mldsa_ca(create_ca, 'PQ approval')
    pid = _policy(auth_client, 'pq-approval', ONLY_65, ca['id'])
    rsa_id = _stored_csr(app, _rsa(), 'pq-appr-rsa.example.test')
    ok_id = _stored_csr(app, mldsa.MLDSA65PrivateKey.generate(), 'pq-appr-65.example.test')
    base = {'ca_id': ca['id'], 'cert_type': 'server_cert', 'validity_days': 30}
    rsa_ap, gate_a = _approval(app, {**base, 'csr_id': rsa_id, 'cn': 'pq-appr-rsa.example.test'})
    ok_ap, gate_b = _approval(app, {**base, 'csr_id': ok_id, 'cn': 'pq-appr-65.example.test'})
    try:
        with app.app_context():
            with pytest.raises(PolicyViolation, match='RSA-2048'):
                _issue_approved_certificate(db.session.get(ApprovalRequest, rsa_ap))
            db.session.rollback()
            assert _issue_approved_certificate(db.session.get(ApprovalRequest, ok_ap))['id'] == ok_id
            db.session.commit()
        assert isinstance(_row_cert(app, Certificate, ok_id).public_key(), mldsa.MLDSA65PublicKey)
    finally:
        _drop(app, ApprovalRequest, rsa_ap, ok_ap)
        _drop(app, CertificatePolicy, pid, gate_a, gate_b)
        _drop(app, Certificate, rsa_id)


def test_renewal_follows_an_ml_dsa_only_policy(app, auth_client, create_ca):
    from services.cert.renewal import renew_certificate_in_place
    ca = _mldsa_ca(create_ca, 'PQ renewal')
    r = _issue(auth_client, ca['id'], 'rsa', 2048, 'pq-renew-rsa.example.test')
    rsa_id = get_json(r)['data']['id']
    r = _issue(auth_client, ca['id'], 'ml-dsa', 65, 'pq-renew-65.example.test')
    ok_id = get_json(r)['data']['id']
    pid = _policy(auth_client, 'pq-renewal', ONLY_65, ca['id'])
    try:
        with app.app_context():
            with pytest.raises(Exception, match='RSA-2048'):
                renew_certificate_in_place(db.session.get(Certificate, rsa_id))
            db.session.rollback()
            before = db.session.get(Certificate, ok_id).serial_number
            renew_certificate_in_place(db.session.get(Certificate, ok_id))
            assert db.session.get(Certificate, ok_id).serial_number != before
        assert isinstance(_row_cert(app, Certificate, ok_id).public_key(), mldsa.MLDSA65PublicKey)
    finally:
        _drop(app, CertificatePolicy, pid)


def test_ca_creation_follows_an_ml_dsa_only_policy(app, auth_client):
    pid = _policy(auth_client, 'pq-global', ONLY_65)
    try:
        r = _post(auth_client, '/api/v2/cas', {'type': 'root', 'commonName': 'PQ refused RSA root',
                                               'keyAlgo': 'RSA', 'keySize': 3072, 'validityYears': 2})
        assert r.status_code == 400 and b'RSA-3072' in r.data, r.data
        r = _post(auth_client, '/api/v2/cas', {'type': 'root', 'commonName': 'PQ allowed root',
                                               'keyAlgo': 'ML-DSA', 'keySize': 65, 'validityYears': 2})
        assert r.status_code == 201, r.get_json()
        assert isinstance(_row_cert(app, CA, get_json(r)['data']['id']).public_key(),
                          mldsa.MLDSA65PublicKey)
    finally:
        _drop(app, CertificatePolicy, pid)


# --------------------------------------------------- digests and signature schemes

def test_allowed_digests_do_not_bind_a_signer_without_digest(app, auth_client, create_ca):
    """A template digest outside allowed_digests refuses an RSA CA, not an ML-DSA one."""
    pq_ca, rsa_ca = _mldsa_ca(create_ca, 'PQ digest'), create_ca(cn=f'PQ digest RSA {uuid.uuid4().hex[:6]}')
    with app.app_context():
        tpl = CertificateTemplate(name=f'pq-digest-{uuid.uuid4().hex[:6]}', template_type='custom',
                                  key_type='ML-DSA-65', digest='sha256', validity_days=30,
                                  extensions_template='{}')
        db.session.add(tpl)
        db.session.commit()
        tid = tpl.id
    pids = [_policy(auth_client, 'pq-digest', {'allowed_digests': ['sha512']}, c['id'])
            for c in (pq_ca, rsa_ca)]
    try:
        r = _issue(auth_client, rsa_ca['id'], 'ml-dsa', 65, 'pq-digest-rsa.example.test', template_id=tid)
        assert r.status_code == 400 and b'SHA256' in r.data, r.data
        r = _issue(auth_client, pq_ca['id'], 'ml-dsa', 65, 'pq-digest-65.example.test', template_id=tid)
        assert r.status_code == 201, r.get_json()
        assert _row_cert(app, Certificate, get_json(r)['data']['id']).signature_hash_algorithm is None
    finally:
        _drop(app, CertificatePolicy, *pids)


def test_scheme_of_an_ml_dsa_signer():
    from services import compliance_signer
    assert compliance_signer.scheme_for(mldsa.MLDSA44PrivateKey.generate().public_key()) == 'ml_dsa'
    assert compliance_signer.scheme_for(mldsa.MLDSA87PrivateKey.generate().public_key(), 'pss') == 'ml_dsa'


def test_allowed_signature_schemes_bind_an_ml_dsa_ca(app, auth_client, create_ca):
    pq_ca, rsa_ca = _mldsa_ca(create_ca, 'PQ scheme'), create_ca(cn=f'PQ scheme RSA {uuid.uuid4().hex[:6]}')
    classical = _policy(auth_client, 'pq-classical', {'allowed_signature_schemes': ['rsa_pss', 'ecdsa']},
                        pq_ca['id'])
    pq_only = _policy(auth_client, 'pq-only', {'allowed_signature_schemes': ['ml_dsa']}, rsa_ca['id'])
    try:
        r = _issue(auth_client, pq_ca['id'], 'ec', 256, 'pq-scheme-refused.example.test')
        assert r.status_code == 400 and b'Signature scheme ml_dsa' in r.data, r.data
        r = _issue(auth_client, rsa_ca['id'], 'ec', 256, 'pq-scheme-rsa.example.test')
        assert r.status_code == 400 and b'rsa_pkcs1v15' in r.data, r.data
        _drop(app, CertificatePolicy, classical)
        allow = _policy(auth_client, 'pq-allow', {'allowed_signature_schemes': ['ml_dsa']}, pq_ca['id'])
        r = _issue(auth_client, pq_ca['id'], 'ec', 256, 'pq-scheme-ok.example.test')
        assert r.status_code == 201, r.get_json()
        _drop(app, CertificatePolicy, allow)
    finally:
        _drop(app, CertificatePolicy, classical, pq_only)


def test_pq_standalone_refuses_what_a_real_ml_dsa_ca_signs(app, auth_client, create_ca):
    ca = _mldsa_ca(create_ca, 'PQ standalone')
    pid = _policy(auth_client, 'pq-standalone', {'pq_standalone': True}, ca['id'])
    try:
        # A classical leaf still carries an ML-DSA signature
        r = _issue(auth_client, ca['id'], 'ec', 256, 'pq-alone-ec.example.test')
        assert r.status_code == 400 and b'post-quantum key or signature (ml_dsa)' in r.data, r.data
    finally:
        _drop(app, CertificatePolicy, pid)


@pytest.mark.parametrize('profile', ['anssi', 'bsi', 'eu-acm'])
def test_european_profiles_refuse_an_ml_dsa_ca_alone(app, auth_client, create_ca, profile):
    ca = _mldsa_ca(create_ca, f'PQ profile {profile}')
    with app.app_context():
        db.session.get(CA, ca['id']).compliance_profile = profile
        db.session.commit()
    r = _issue(auth_client, ca['id'], 'ec', 384, f'pq-profile-{profile}.example.test')
    assert r.status_code == 400, r.data
    assert b'(ml_dsa) alone' in r.data and b'Signature scheme ml_dsa' in r.data, r.data


# ------------------------------------------------------------------- templates

def test_template_overrides_compare_ml_dsa_labels():
    from services.template_service import compute_template_overrides
    tpl = CertificateTemplate(key_type='ML-DSA-65', validity_days=30, digest='sha384')
    assert compute_template_overrides(tpl, key_type='ml-dsa-65') is None
    assert compute_template_overrides(tpl, key_type='mldsa65', validity_days=30) is None
    assert json.loads(compute_template_overrides(tpl, key_type='ML-DSA-87')) == ['key_type']
    # Any registry spelling on either side compares, not only the canonical label
    legacy = CertificateTemplate(key_type='mldsa65', validity_days=30)
    assert json.loads(compute_template_overrides(legacy, key_type='ml-dsa-87')) == ['key_type']


@pytest.mark.parametrize('key_type,expected', [('ml-dsa-65', None), ('ml-dsa-87', ['key_type'])])
def test_template_digest_is_ignored_under_an_ml_dsa_ca(app, create_ca, key_type, expected):
    from services.cert_service import CertificateService
    ca = _mldsa_ca(create_ca, 'PQ template')
    with app.app_context():
        tpl = CertificateTemplate(name=f'pq-tpl-{uuid.uuid4().hex[:6]}', template_type='custom',
                                  key_type='ML-DSA-65', digest='sha384', validity_days=30,
                                  extensions_template='{}')
        db.session.add(tpl)
        db.session.commit()
        row = CertificateService.create_certificate(
            descr='pq-template', caref=db.session.get(CA, ca['id']).refid,
            dn={'CN': f'pq-tpl-{key_type}.example.test'}, cert_type='server_cert',
            key_type=key_type, digest='sha512', validity_days=30, template_id=tpl.id)
        db.session.commit()
        overrides = row.template_overrides
        cert = x509.load_pem_x509_certificate(base64.b64decode(row.crt))
    assert cert.signature_hash_algorithm is None
    assert (json.loads(overrides) if overrides else None) == expected


@pytest.mark.parametrize('key,expected', [(mldsa.MLDSA65PrivateKey, None),
                                          (mldsa.MLDSA87PrivateKey, ['key_type'])])
def test_signed_csr_template_digest_is_ignored_under_an_ml_dsa_ca(app, create_ca, key, expected):
    from services.cert_service import CertificateService
    ca = _mldsa_ca(create_ca, 'PQ CSR template')
    csr_id = _stored_csr(app, key.generate(), f'pq-csr-tpl-{uuid.uuid4().hex[:6]}.example.test')
    with app.app_context():
        tpl = CertificateTemplate(name=f'pq-csr-tpl-{uuid.uuid4().hex[:6]}', template_type='custom',
                                  key_type='ML-DSA-65', digest='sha384', validity_days=30,
                                  extensions_template='{}')
        db.session.add(tpl)
        db.session.commit()
        row = CertificateService.sign_csr(csr_id, db.session.get(CA, ca['id']).refid, validity_days=30,
                                          digest='sha512', template_id=tpl.id)
        db.session.commit()
        overrides = row.template_overrides
    assert (json.loads(overrides) if overrides else None) == expected


# ------------------------------------------------------------------- preflights

def test_fips_preflight_names_ml_dsa_ca_template_and_policy(app, auth_client, create_ca):
    from services import fips_preflight
    ca = _mldsa_ca(create_ca, 'PQ FIPS preflight')
    pid = _policy(auth_client, 'pq-fips-preflight', {'allowed_key_types': ['ML-DSA-65', 'EC-P256']})
    with app.app_context():
        tpl = CertificateTemplate(name=f'pq-fips-tpl-{uuid.uuid4().hex[:6]}', template_type='custom',
                                  key_type='ML-DSA-87', validity_days=30, extensions_template='{}')
        db.session.add(tpl)
        db.session.commit()
        tid, tname = tpl.id, tpl.name
    try:
        with app.app_context():
            unapproved_cas = fips_preflight._ca_weak()
            templates = fips_preflight._templates()
            policies = fips_preflight._policies()
        assert any(f"(#{ca['id']}): ML-DSA-65" in n for n in unapproved_cas), unapproved_cas
        assert f'{tname} (#{tid}): ML-DSA-87' in templates
        assert any(f'(#{pid}): ML-DSA-65' in n and 'EC-P256' not in n for n in policies), policies
    finally:
        _drop(app, CertificatePolicy, pid)
        _drop(app, CertificateTemplate, tid)


def test_compliance_preflight_grades_an_ml_dsa_ca(app, create_ca):
    from services import compliance_preflight as cp
    ca = _mldsa_ca(create_ca, 'PQ compliance preflight')
    with app.app_context():
        ctx = cp.build_context('anssi', ca['id'])
        keys, schemes = cp._ca_key_type(ctx), cp._ca_scheme(ctx)
    assert (cp.REFUSE, f"{ctx.ca.descr} (#{ca['id']}): ML-DSA-65") in keys
    assert (cp.REFUSE, f"{ctx.ca.descr} (#{ca['id']}): ml_dsa") in schemes


def test_compliance_preflight_grades_ml_dsa_templates_policies_responders(app, auth_client, create_ca):
    from models import SystemConfig
    from services import compliance_preflight as cp
    ca = create_ca(cn=f'PQ compliance responder {uuid.uuid4().hex[:6]}')
    pid = _policy(auth_client, 'pq-compliance', {'allowed_key_types': ['ML-DSA-44']}, ca['id'])
    r = _post(auth_client, '/api/v2/certificates', {
        'cn': 'pq-compliance-responder.test', 'ca_id': ca['id'], 'key_type': 'ml-dsa', 'key_size': 44,
        'validity_days': 30, 'cert_type': 'custom', 'extra_ekus': ['OCSPSigning']})
    _drop(app, CertificatePolicy, pid)
    assert r.status_code == 201, r.get_json()
    responder = get_json(r)['data']['id']
    assert _post(auth_client, f"/api/v2/cas/{ca['id']}/ocsp-responder",
                 {'certificate_id': responder}).status_code == 200
    pid = _policy(auth_client, 'pq-compliance', {'allowed_key_types': ['ML-DSA-44']}, ca['id'])
    with app.app_context():
        tpl = CertificateTemplate(name=f'pq-cp-tpl-{uuid.uuid4().hex[:6]}', template_type='custom',
                                  key_type='ML-DSA-44', validity_days=30, extensions_template='{}')
        db.session.add(tpl)
        db.session.commit()
        tid = tpl.id
    try:
        with app.app_context():
            ctx = cp.build_context('bsi', ca['id'])
            templates, policies = cp._templates_key(ctx), cp._policies_key(ctx)
            responders = cp._ocsp_responders(ctx)
        assert any(g == cp.REFUSE and f'(#{tid}): ML-DSA-44' in n for g, n in templates), templates
        assert any(g == cp.REFUSE and f'(#{pid}): ML-DSA-44' in n for g, n in policies), policies
        assert any(g == cp.REFUSE and f'(#{responder}): ML-DSA-44' in n for g, n in responders), responders
    finally:
        with app.app_context():
            SystemConfig.query.filter_by(key=f"ocsp_responder_cert_{ca['id']}").delete()
            db.session.commit()
        _drop(app, CertificatePolicy, pid)
        _drop(app, CertificateTemplate, tid)


# ---------------------------------------------------------------------- scores

def test_ml_dsa_key_strength_matches_the_classical_curve_of_its_category():
    from services.compliance_service import _score_key_strength
    for level, curve in ((44, 'EC-P256'), (65, 'EC-P384'), (87, 'EC-P521')):
        assert (_score_key_strength({'key_algo': f'ML-DSA-{level}'})['score']
                == _score_key_strength({'key_algo': curve})['score']), level


def test_sort_points_follow_the_score_and_levels_break_ties():
    from services.compliance_service import _score_key_strength, key_algo_sort_levels, key_algo_sort_points
    points, levels = dict(key_algo_sort_points()), dict(key_algo_sort_levels())
    for n in (44, 65, 87):
        assert points[f'ML-DSA-{n}'] == _score_key_strength({'key_algo': f'ML-DSA-{n}'})['score']
    assert levels['ML-DSA-44'] < levels['ML-DSA-65'] < levels['ML-DSA-87']
    assert levels['SLH-DSA-SHA2-128s'] < levels['SLH-DSA-SHAKE-256f']


def test_certificate_list_sorts_ml_dsa_by_level(app, auth_client, create_ca):
    ca = create_ca(cn=f'PQ sort {uuid.uuid4().hex[:6]}')
    tag = uuid.uuid4().hex[:6]
    # Names in the reverse of the expected order, so a tie falls back visibly to the name
    for name, level in (('a', 44), ('b', 65), ('c', 87)):
        r = _issue(auth_client, ca['id'], 'ml-dsa', level, f'pqsort{tag}-{name}-{level}.example.test')
        assert r.status_code == 201, r.get_json()
    for order, expected in (('desc', ['87', '65', '44']), ('asc', ['44', '65', '87'])):
        r = auth_client.get(f'/api/v2/certificates?search=pqsort{tag}&sort_by=compliance_grade&sort_order={order}')
        names = [c.get('common_name') or c.get('cn') or c.get('subject') for c in get_json(r)['data']]
        assert [n.split('-')[2].split('.')[0] for n in names] == expected, (order, names)
