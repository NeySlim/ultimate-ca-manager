"""The key issued when nothing names one comes from one registry default, not from a
literal at each path (#397): every site follows it, and the policies in scope bound it."""
import base64
import json

import pytest
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import rsa

from utils import issuance_defaults


@pytest.fixture
def rsa3072(monkeypatch):
    monkeypatch.setattr(issuance_defaults, 'BASELINE_ISSUE_KEY', 'RSA-3072')


def _post(client, url, body):
    return client.post(url, data=json.dumps(body), content_type='application/json')


def _bits(pem_or_b64):
    raw = pem_or_b64 if isinstance(pem_or_b64, bytes) else pem_or_b64.encode()
    if not raw.startswith(b'-----'):
        raw = base64.b64decode(raw)
    obj = (x509.load_pem_x509_csr(raw) if b'REQUEST' in raw[:40] else x509.load_pem_x509_certificate(raw))
    assert isinstance(obj.public_key(), rsa.RSAPublicKey)
    return obj.public_key().key_size


def test_baseline_yields_to_the_compliance_profile_of_the_ca(app, monkeypatch):
    import compliance_profiles
    with app.app_context():
        assert issuance_defaults.default_issue_key_type() == 'RSA-2048'
        assert issuance_defaults.default_issue_key_id() == '2048'
        monkeypatch.setattr(compliance_profiles, 'profile_of_ca', lambda ca_id: 'bsi')
        assert issuance_defaults.default_issue_key_type(1) == 'RSA-3072'
        assert issuance_defaults.default_issue_key_id(1) == '3072'
        assert issuance_defaults.default_rsa_key_size(1) == '3072'


def test_rest_issue_without_key_type(app, auth_client, create_ca, rsa3072):
    ca = create_ca(cn='Defaults REST CA')
    r = _post(auth_client, '/api/v2/certificates', {'cn': 'defaults-rest.example.test', 'ca_id': ca['id']})
    assert r.status_code == 201, r.get_json()
    from models import Certificate
    with app.app_context():
        row = Certificate.query.get(r.get_json()['data']['id'])
        assert _bits(row.crt) == 3072


def test_csr_generation_without_key_type(app, auth_client, rsa3072):
    r = _post(auth_client, '/api/v2/csrs', {'cn': 'defaults-csr.example.test'})
    assert r.status_code in (200, 201), r.get_json()
    from models import Certificate
    with app.app_context():
        row = Certificate.query.get(r.get_json()['data']['id'])
        assert _bits(base64.b64decode(row.csr)) == 3072


def test_ca_creation_without_key_fields(app, auth_client, rsa3072):
    r = _post(auth_client, '/api/v2/cas', {
        'type': 'root', 'commonName': 'Defaults CA key', 'organization': 'Test Org', 'country': 'US',
        'validityYears': 5})
    assert r.status_code in (200, 201), r.get_json()
    from models import CA
    with app.app_context():
        assert _bits(CA.query.get(r.get_json()['data']['id']).crt) == 3072


def test_approved_issuance_without_key_type(app, create_ca, rsa3072):
    from tests.test_approval_template_issuance import _issue_from_request
    ca = create_ca(cn='Defaults approval CA')
    cert, _ = _issue_from_request(app, create_ca, {
        'cn': 'defaults-approval.example.test', 'ca_id': ca['id'], 'cert_type': 'server'})
    assert cert.public_key().key_size == 3072


def test_tsa_signer_key_follows_the_default_but_never_below_3072(app, monkeypatch):
    from services.tsa_signer_cert import _generate_key
    with app.app_context():
        monkeypatch.setattr(issuance_defaults, 'BASELINE_ISSUE_KEY', 'RSA-4096')
        assert _generate_key(None, None, None).key_size == 4096
        monkeypatch.setattr(issuance_defaults, 'BASELINE_ISSUE_KEY', 'RSA-2048')
        assert _generate_key(None, None, None).key_size == 3072


def test_xcep_announces_the_default_for_a_template_without_key_type(app, rsa3072):
    from services.xcep.policy_builder import _key_type_info
    with app.app_context():
        assert _key_type_info(None) == ('RSA', 3072)


def test_wstep_matches_a_template_without_key_type_against_the_default(app, rsa3072):
    from models.certificate_template import CertificateTemplate
    from services.wstep.wstep_service import _template_key_label, _template_takes_key
    template = CertificateTemplate(name='defaults-wstep', template_type='custom', key_type=None)
    with app.app_context():
        assert _template_key_label(template) == 'RSA-3072'
        assert not _template_takes_key(template, 'RSA-2048')
        assert _template_takes_key(template, 'RSA-3072')


def test_template_created_without_key_type(app, auth_client, rsa3072):
    from models.certificate_template import CertificateTemplate
    ext = json.dumps({'key_usage': ['digitalSignature']})
    created = _post(auth_client, '/api/v2/templates', {
        'name': 'defaults-created', 'template_type': 'custom', 'extensions_template': ext})
    assert created.status_code in (200, 201), created.get_json()
    imported = auth_client.post('/api/v2/templates/import', data={'json_content': json.dumps(
        {'name': 'defaults-imported', 'template_type': 'custom', 'extensions_template': ext})},
        content_type='multipart/form-data')
    assert imported.status_code == 200, imported.get_json()
    with app.app_context():
        for name in ('defaults-created', 'defaults-imported'):
            assert CertificateTemplate.query.filter_by(name=name).one().key_type == 'RSA-3072', name


KEY_LITERAL_FILES = [
    'api/v2/certificates/cert_create.py', 'api/v2/csrs.py', 'api/v2/policies.py', 'api/v2/cas/crud.py',
    'api/v2/templates.py', 'services/tsa_signer_cert.py', 'services/xcep/policy_builder.py',
    'services/wstep/wstep_service.py', 'services/cert/mixins/lifecycle.py', 'services/ca/ca_creation.py',
    'services/trust_store/csr_operations_mixin.py', 'services/cert/mixins/csr.py',
    'services/trust_store/certificate_creation_mixin.py',
]
DIGEST_LITERAL_FILES = [
    'services/cert/mixins/lifecycle.py', 'services/ca/ca_creation.py',
    'services/trust_store/ca_certificate_creation_mixin.py', 'services/trust_store/csr_operations_mixin.py',
    'services/trust_store/certificate_creation_mixin.py', 'services/trust_store/crl_operations_mixin.py',
    'services/cert/mixins/csr.py', 'services/ca/cross_signing.py', 'services/xcep/policy_builder.py',
]


def _literals(path, wanted):
    """Lines of the string constants of *path* equal to one of *wanted*, lookup tables apart."""
    import ast
    from pathlib import Path
    tree = ast.parse((Path(__file__).resolve().parent.parent / path).read_text())
    keys = {id(c) for n in ast.walk(tree) if isinstance(n, ast.Dict) for c in ast.walk(n)}
    return [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Constant)
            and isinstance(n.value, str) and n.value in wanted and id(n) not in keys]


@pytest.mark.parametrize('path', KEY_LITERAL_FILES)
def test_no_key_literal_on_an_issuance_path(path):
    assert _literals(path, {'2048', 'RSA-2048', 'RSA 2048'}) == []


@pytest.mark.parametrize('path', DIGEST_LITERAL_FILES)
def test_no_digest_literal_on_an_issuance_path(path):
    assert _literals(path, {'sha256'}) == []


def test_default_key_follows_the_profile_of_a_ca_not_created_yet(app):
    with app.app_context():
        assert issuance_defaults.default_issue_key_type(None, 'bsi') == 'RSA-3072'


def _ca_body(cn, **extra):
    return {'type': 'root', 'commonName': cn, 'organization': 'Test Org', 'country': 'US',
            'validityYears': 5, **extra}


def test_ca_creation_without_key_under_a_compliance_profile(app, auth_client):
    r = _post(auth_client, '/api/v2/cas', _ca_body('Profile CA key', complianceProfile='bsi', signatureScheme='pss'))
    assert r.status_code in (200, 201), r.get_json()
    from models import CA
    with app.app_context():
        assert _bits(CA.query.get(r.get_json()['data']['id']).crt) == 3072


def test_intermediate_without_key_under_a_profiled_parent(app, auth_client):
    parent = _post(auth_client, '/api/v2/cas', _ca_body('Profile parent', complianceProfile='bsi', signatureScheme='pss'))
    assert parent.status_code in (200, 201), parent.get_json()
    r = _post(auth_client, '/api/v2/cas', {
        **_ca_body('Profile child'), 'type': 'intermediate', 'parentCAId': parent.get_json()['data']['id']})
    assert r.status_code in (200, 201), r.get_json()
    from models import CA
    with app.app_context():
        assert _bits(CA.query.get(r.get_json()['data']['id']).crt) == 3072


def test_xcep_and_wstep_default_follows_the_profile_of_their_ca(app, monkeypatch):
    import compliance_profiles
    from models.certificate_template import CertificateTemplate
    from services.wstep.wstep_service import _template_key_label, _template_takes_key
    from services.xcep.policy_builder import _key_type_info
    template = CertificateTemplate(name='profile-wstep', template_type='custom', key_type=None)
    monkeypatch.setattr(compliance_profiles, 'profile_of_ca', lambda ca_id: 'bsi')
    with app.app_context():
        assert _key_type_info(None, 1) == ('RSA', 3072)
        assert _template_key_label(template, 1) == 'RSA-3072'
        assert not _template_takes_key(template, 'RSA-2048', 1)


def _scoped_policy(app, ca_id, template_id, allowed):
    from models import CertificatePolicy, db
    with app.app_context():
        pol = CertificatePolicy(name=f'default-key-{ca_id}-{template_id}', policy_type='issuance',
                                ca_id=ca_id, template_id=template_id, requires_approval=False,
                                min_approvers=1, is_active=True, priority=100)
        pol.set_rules({'allowed_key_types': allowed})
        db.session.add(pol)
        db.session.commit()
        return pol.id


def _drop_policy(app, pid):
    from models import CertificatePolicy, db
    with app.app_context():
        db.session.delete(db.session.get(CertificatePolicy, pid))
        db.session.commit()


def test_default_key_honours_the_policies_of_the_template(app, create_ca):
    from models import CertificateTemplate, db
    ca = create_ca(cn='Default key template CA')
    with app.app_context():
        tpl = CertificateTemplate(name='default-key-tpl', template_type='web_server',
                                  key_type='', validity_days=30, digest='sha256',
                                  extensions_template='{}')
        db.session.add(tpl)
        db.session.commit()
        tpl_id = tpl.id
    pid = _scoped_policy(app, None, tpl_id, ['EC-P256'])
    try:
        with app.app_context():
            assert issuance_defaults.default_issue_key_type(ca['id']) == 'RSA-2048'
            assert issuance_defaults.default_issue_key_type(ca['id'], template_id=tpl_id) == 'EC-P256'
    finally:
        _drop_policy(app, pid)


def test_default_key_with_no_allowed_candidate_is_refused_not_rsa_2048(app, auth_client, create_ca):
    from services.policy_service import PolicyViolation
    ca = create_ca(cn='Default key refused CA')
    pid = _scoped_policy(app, ca['id'], None, ['RSA-4096'])
    try:
        with app.app_context():
            with pytest.raises(PolicyViolation, match='no default key type is allowed'):
                issuance_defaults.default_issue_key_type(ca['id'])
        r = _post(auth_client, '/api/v2/certificates',
                  {'cn': 'default-refused.example.test', 'ca_id': ca['id']})
        assert r.status_code == 400, r.get_json()
        assert 'RSA-2048' in json.dumps(r.get_json())
    finally:
        _drop_policy(app, pid)


def test_default_ca_digest_follows_the_hsm_key_algorithm(app):
    from services.ca.ca_creation import _default_ca_digest
    with app.app_context():
        assert _default_ca_digest(None, '2048') == 'sha256'
        assert _default_ca_digest(None, '2048', hsm_key_algorithm='EC-P384') == 'sha384'
        assert _default_ca_digest(None, '2048', hsm_key_algorithm='EC-P521') == 'sha512'


def _effective(auth_client, **args):
    r = auth_client.get('/api/v2/policies/effective', query_string=args)
    assert r.status_code == 200, r.get_json()
    return r.get_json()['data']


def test_effective_route_announces_the_default_key_of_the_ca_and_template(app, auth_client, create_ca):
    from models import CertificateTemplate, db
    ca = create_ca(cn='Effective default CA')
    with app.app_context():
        tpl = CertificateTemplate(name='effective-default-tpl', template_type='web_server',
                                  key_type='', validity_days=30, digest='sha256',
                                  extensions_template='{}')
        db.session.add(tpl)
        db.session.commit()
        tpl_id = tpl.id
    pid = _scoped_policy(app, None, tpl_id, ['EC-P256'])
    try:
        plain = _effective(auth_client, ca_id=ca['id'])
        assert plain['default_key_type'] == 'RSA-2048'
        assert plain['baseline_key_type'] == issuance_defaults.BASELINE_ISSUE_KEY
        assert _effective(auth_client, ca_id=ca['id'], template_id=tpl_id)['default_key_type'] == 'EC-P256'
    finally:
        _drop_policy(app, pid)
        with app.app_context():
            CertificateTemplate.query.filter_by(id=tpl_id).delete()
            db.session.commit()


def test_effective_route_with_no_candidate_gives_a_readable_error_not_a_key(app, auth_client, create_ca):
    ca = create_ca(cn='Effective refused CA')
    pid = _scoped_policy(app, ca['id'], None, ['RSA-4096'])
    try:
        data = _effective(auth_client, ca_id=ca['id'])
        assert data['default_key_type'] is None
        assert 'no default key type is allowed' in data['default_key_error']
    finally:
        _drop_policy(app, pid)
