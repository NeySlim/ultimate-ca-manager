"""ML-DSA keys are named, generated and issued on every input path; an unknown
key type is a 400, never an RSA-2048, and SLH-DSA is refused at issuance."""
import base64
import json
import logging

import pytest
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import mldsa, rsa

import fips_mode
from models import CA, Certificate, db
from services.trust_store import TrustStoreService
from tests.pqc_fixtures import fixture_bytes
from utils import key_algorithms

pytestmark = pytest.mark.skipif(not key_algorithms.mldsa_supported(),
                                reason='this build has no ML-DSA')

PRIVATE = {'44': mldsa.MLDSA44PrivateKey, '65': mldsa.MLDSA65PrivateKey, '87': mldsa.MLDSA87PrivateKey}
PUBLIC = {'44': mldsa.MLDSA44PublicKey, '65': mldsa.MLDSA65PublicKey, '87': mldsa.MLDSA87PublicKey}


def _post(client, url, body):
    return client.post(url, content_type='application/json', data=json.dumps(body))


def _row_cert(row):
    return x509.load_pem_x509_certificate(base64.b64decode(row.crt))


# ---- vocabulary -------------------------------------------------------------

@pytest.mark.parametrize('level', ['44', '65', '87'])
def test_trust_store_generates_each_level(level):
    key = TrustStoreService.generate_private_key(f'ml-dsa-{level}')
    assert isinstance(key, PRIVATE[level])


@pytest.mark.parametrize('key_type,key_size,expected', [
    ('ml-dsa', '44', 'ml-dsa-44'),
    ('ML-DSA', 65, 'ml-dsa-65'),
    ('mldsa', '87', 'ml-dsa-87'),
    ('ML-DSA-65', None, 'ml-dsa-65'),
    ('ml-dsa', 'ML-DSA-87', 'ml-dsa-87'),
])
def test_parse_issue_key_type_names_ml_dsa(key_type, key_size, expected):
    from utils.key_type import parse_issue_key_type
    assert parse_issue_key_type(key_type, key_size) == expected


@pytest.mark.parametrize('key_type,key_size', [('ML-DSA-65', None), ('ml-dsa', '65')])
def test_parse_issue_key_type_ignores_a_curve_on_ml_dsa(key_type, key_size):
    from utils.key_type import parse_issue_key_type
    assert parse_issue_key_type(key_type, key_size, curve='P-256') == 'ml-dsa-65'


@pytest.mark.parametrize('key_type,key_size', [('ml-dsa', '99'), ('ml-dsa', '2048'), ('foo', '2048'),
                                               ('ML-DSA-65', 'P256'), ('ML-DSA-65', 'ML-DSA-87')])
def test_parse_issue_key_type_refuses_what_it_cannot_name(key_type, key_size):
    from utils.key_type import parse_issue_key_type
    with pytest.raises(ValueError):
        parse_issue_key_type(key_type, key_size)


def test_parse_csr_key_type_names_ml_dsa():
    from utils.key_type import parse_csr_key_type
    assert parse_csr_key_type('ML-DSA-65') == 'ml-dsa-65'
    assert parse_csr_key_type('ML-DSA 44') == 'ml-dsa-44'


def test_template_key_type_through_the_registry():
    from utils.key_type import fill_key_params_from_template, issue_key_type_from_template
    assert issue_key_type_from_template('ML-DSA-87') == 'ml-dsa-87'
    assert issue_key_type_from_template('EC-P384') == 'secp384r1'
    assert issue_key_type_from_template('RSA-3072') == '3072'
    # The size follows the template only while the algorithm does (#318)
    assert fill_key_params_from_template('rsa', None, 'ML-DSA-65') == ('rsa', None)
    key_type, key_size = fill_key_params_from_template('ml-dsa', None, 'ML-DSA-65')
    assert (key_type.lower(), key_size) == ('ml-dsa', '65')
    # A full label keeps its own level
    assert fill_key_params_from_template('ML-DSA-87', None, 'ML-DSA-65') == ('ML-DSA-87', None)


def test_ml_dsa_label_over_a_template_of_another_level(app, auth_client, create_ca):
    ca = create_ca(cn='PQ template level issuer')
    r = _post(auth_client, '/api/v2/templates', {
        'name': 'pq-level-template', 'template_type': 'custom', 'key_type': 'ML-DSA-65',
        'validity_days': 90, 'extensions_template': {'key_usage': ['digitalSignature']}})
    assert r.status_code in (200, 201), r.get_json()
    tpl_id = r.get_json()['data']['id']
    r = _post(auth_client, '/api/v2/certificates', {
        'cn': 'mldsa87-over-65.example.test', 'ca_id': ca['id'], 'template_id': tpl_id,
        'key_type': 'ML-DSA-87', 'validity_days': 30})
    assert r.status_code == 201, r.get_json()
    with app.app_context():
        leaf = _row_cert(db.session.get(Certificate, r.get_json()['data']['id']))
    assert isinstance(leaf.public_key(), mldsa.MLDSA87PublicKey)


def test_ca_key_size_must_name_the_key():
    from api.v2.cas.crud import _resolve_local_key_type
    assert _resolve_local_key_type({'keyAlgo': 'ML-DSA-87', 'keySize': 'None'})[0] is None
    assert _resolve_local_key_type({'keyAlgo': 'ML-DSA-87', 'keySize': 87}) == ('ml-dsa-87', None)


def test_unknown_template_key_type_is_refused_not_rsa():
    from utils.key_type import issue_key_type_from_template
    with pytest.raises(ValueError):
        issue_key_type_from_template('FOO-1')


def test_template_key_types_include_ml_dsa():
    from services.template_service import TEMPLATE_KEY_TYPES, template_key_type_label
    assert {'ML-DSA-44', 'ML-DSA-65', 'ML-DSA-87'} <= set(TEMPLATE_KEY_TYPES)
    assert template_key_type_label('ml-dsa-65') == 'ML-DSA-65'
    assert template_key_type_label('Ed25519') is None


def test_enrollment_accepts_ml_dsa_outside_fips(monkeypatch):
    from utils.key_type import validate_enrollment_public_key
    pub = mldsa.MLDSA44PrivateKey.generate().public_key()
    monkeypatch.setattr(fips_mode, 'enabled', lambda: False)
    assert validate_enrollment_public_key(pub) is None
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
    assert 'FIPS' in validate_enrollment_public_key(pub)


def test_slh_dsa_csr_is_not_signable(app):
    from utils.key_type import validate_enrollment_csr
    csr = x509.load_pem_x509_csr(fixture_bytes('slhdsa-sha2-128s-csr.pem'))
    assert validate_enrollment_csr(csr) == 'SLH-DSA-SHA2-128s keys are not signable by this instance'


def test_sign_csr_refuses_slh_dsa_before_reading_its_signature():
    ca_key = rsa.generate_private_key(65537, 2048)
    ca_cert = x509.load_pem_x509_certificate(TrustStoreService.create_ca_certificate(
        x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, 'slh refusal root')]),
        ca_key, validity_days=30)[0])
    with pytest.raises(ValueError, match='not signable by this instance'):
        TrustStoreService.sign_csr(fixture_bytes('slhdsa-sha2-128s-csr.pem'), ca_cert, ca_key)


def test_upload_refuses_slh_dsa_with_a_400(app, auth_client):
    pem = fixture_bytes('slhdsa-sha2-128s-csr.pem')
    with app.app_context():
        before = Certificate.query.count()
    r = _post(auth_client, '/api/v2/csrs/upload', {'pem': pem.decode(), 'name': 'slh'})
    assert r.status_code == 400, r.get_json()
    assert 'not signable by this instance' in r.get_json()['detail']
    r = auth_client.post('/api/v2/csrs/import', data={'pem_content': pem.decode(), 'name': 'slh'})
    assert r.status_code == 400, r.get_json()
    assert 'not signable by this instance' in r.get_json()['detail']
    with app.app_context():
        assert Certificate.query.count() == before


def test_smart_import_refuses_slh_dsa_like_the_upload(app, auth_client):
    pem = fixture_bytes('slhdsa-sha2-128s-csr.pem').decode()
    r = _post(auth_client, '/api/v2/import/analyze', {'content': pem})
    assert r.status_code == 200, r.get_json()
    errors = r.get_json()['data']['validation']['errors']
    assert any('not signable by this instance' in e for e in errors), errors
    with app.app_context():
        before = Certificate.query.count()
    r = _post(auth_client, '/api/v2/import/execute', {'content': pem})
    assert r.status_code == 200, r.get_json()
    data = r.get_json()['data']
    assert data['csrs_imported'] == 0 and data['success'] is False, data
    assert any('not signable by this instance' in e for e in data['errors']), data
    with app.app_context():
        assert Certificate.query.count() == before


def test_sign_route_refuses_a_stored_slh_dsa_csr(app, auth_client, create_ca):
    from services.cert_service import CertificateService
    ca = create_ca(cn='PQ SLH sign route issuer')
    with app.app_context():
        row = Certificate(refid='slh-dsa-stored-csr', descr='slh stored', source='manual',
                          csr=base64.b64encode(fixture_bytes('slhdsa-sha2-128s-csr.pem')).decode())
        db.session.add(row)
        db.session.commit()
        csr_id = row.id
        ca_refid = db.session.get(CA, ca['id']).refid
    try:
        r = _post(auth_client, f'/api/v2/csrs/{csr_id}/sign', {'ca_id': ca['id'], 'validity_days': 30})
        assert r.status_code == 400, r.get_json()
        assert 'not signable by this instance' in r.get_json()['detail']
        with app.app_context(), pytest.raises(ValueError, match='not signable by this instance'):
            CertificateService.sign_csr(cert_id=csr_id, caref=ca_refid, validity_days=30)
    finally:
        with app.app_context():
            db.session.delete(db.session.get(Certificate, csr_id))
            db.session.commit()


def test_protocol_csr_checks_refuse_slh_dsa_by_name():
    from api.est_protocol import _validate_est_csr
    from services.wstep.wstep_service import _validate_csr
    csr = x509.load_pem_x509_csr(fixture_bytes('slhdsa-sha2-128s-csr.pem'))
    ok, response = _validate_est_csr(csr)
    assert not ok and response.status_code == 400
    assert b'not signable by this instance' in response.get_data()
    assert 'not signable by this instance' in _validate_csr(csr)


def test_scep_refuses_slh_dsa_by_name(app, create_ca, caplog):
    from cryptography.hazmat.primitives import serialization
    from services.scep.scep_service import SCEPService
    from tests.test_scep_rfc8894_operations import (
        FAIL_INFO_OID, PKI_STATUS_OID, _build_request, _client_identity, _load_ca_material,
        _response_attributes)
    csr_der = x509.load_pem_x509_csr(fixture_bytes('slhdsa-sha2-128s-csr.pem')).public_bytes(
        serialization.Encoding.DER)
    ca_data = create_ca(cn='PQ SLH SCEP issuer')
    with app.app_context():
        ca, ca_cert, _ = _load_ca_material(ca_data['id'])
        signer_cert, signer_key = _client_identity('slh-scep.example.test')
        request = _build_request(ca_cert, signer_cert, signer_key, 19, csr_der, b'slh-scep-nonce16')
        with caplog.at_level(logging.WARNING, logger='services.scep'):
            response, status = SCEPService(ca.refid, auto_approve=True).process_pkcs_req(
                request, '127.0.0.1')
    attrs = _response_attributes(response)
    assert status == 200 and attrs[PKI_STATUS_OID] == '2' and attrs[FAIL_INFO_OID] == '2'
    # badRequest either way on the wire: the reason is only in the log
    assert any('not signable by this instance' in rec.getMessage() for rec in caplog.records), \
        [rec.getMessage() for rec in caplog.records]


def test_msca_sign_refuses_slh_dsa_by_name(app, auth_client):
    from models.msca import MicrosoftCA
    with app.app_context():
        conn = MicrosoftCA(name='pq-slh-msca-sign', server='ca.example.test', ca_name='Example Issuing CA',
                           auth_method='basic', username='svc', enabled=True)
        row = Certificate(refid='slh-dsa-msca-csr', descr='slh msca', source='manual',
                          csr=base64.b64encode(fixture_bytes('slhdsa-sha2-128s-csr.pem')).decode())
        db.session.add_all([conn, row])
        db.session.commit()
        conn_id, csr_id = conn.id, row.id
    try:
        r = _post(auth_client, f'/api/v2/microsoft-cas/{conn_id}/sign/{csr_id}', {'template': 'WebServer'})
        assert r.status_code == 400, r.get_json()
        assert 'not signable by this instance' in r.get_json()['detail']
    finally:
        with app.app_context():
            db.session.delete(db.session.get(Certificate, csr_id))
            db.session.delete(db.session.get(MicrosoftCA, conn_id))
            db.session.commit()


# ---- digests ----------------------------------------------------------------

def test_ca_profile_digest_is_none_without_a_digest():
    from utils.ca_profile import default_digest_for_key_type, resolve_digest
    assert default_digest_for_key_type('ml-dsa-65') is None
    assert resolve_digest('auto', 'ml-dsa-65') == (None, None)
    assert resolve_digest('sha384', 'ml-dsa-87') == (None, None)
    assert resolve_digest('sha1', 'ml-dsa-87')[1]
    # Classical keys keep their curve digest
    assert resolve_digest('auto', 'secp384r1') == ('sha384', None)
    assert resolve_digest(None, '2048') == ('sha256', None)


def test_key_default_digest_is_none_for_ml_dsa():
    from services.ca.ca_creation import _key_default_digest
    assert _key_default_digest(mldsa.MLDSA65PrivateKey.generate()) is None
    assert _key_default_digest(rsa.generate_private_key(65537, 2048)) == 'sha256'


# ---- API ------------------------------------------------------------------------

def _ml_dsa_ca(auth_client, level, **extra):
    body = {'type': 'root', 'commonName': f'PQ root ML-DSA-{level}', 'keyAlgo': 'ML-DSA',
            'keySize': int(level), 'validityYears': 2, **extra}
    return _post(auth_client, '/api/v2/cas', body)


def test_api_creates_ml_dsa_root(app, auth_client):
    r = _ml_dsa_ca(auth_client, '65', hashAlgorithm='auto')
    assert r.status_code == 201, r.get_json()
    with app.app_context():
        cert = _row_cert(db.session.get(CA, r.get_json()['data']['id']))
    assert isinstance(cert.public_key(), mldsa.MLDSA65PublicKey)
    assert cert.signature_hash_algorithm is None
    cert.verify_directly_issued_by(cert)


def test_api_ignores_a_digest_for_ml_dsa_with_a_notice(app, auth_client):
    r = _ml_dsa_ca(auth_client, '44', hashAlgorithm='sha384')
    assert r.status_code == 201, r.get_json()
    notices = (r.get_json().get('meta') or {}).get('notices') or []
    assert any('sha384' in n and 'ignored' in n for n in notices), notices


@pytest.mark.parametrize('body', [
    {'keyAlgo': 'FOO'},
    {'keyAlgo': 'FOO', 'keySize': 2048},
    {'keyAlgo': 'ML-DSA', 'keySize': 99},
    {'keyAlgo': 'ML-DSA', 'keySize': 2048},
    {'keyType': 'SLH-DSA-SHA2-128s'},
])
def test_api_refuses_an_unknown_ca_key(app, auth_client, body):
    with app.app_context():
        before = CA.query.count()
    r = _post(auth_client, '/api/v2/cas', {'type': 'root', 'commonName': 'never made', **body})
    assert r.status_code == 400, r.get_json()
    with app.app_context():
        assert CA.query.count() == before


@pytest.mark.parametrize('issuer', ['rsa', 'ml-dsa'])
def test_api_issues_ml_dsa_44_leaf(app, auth_client, create_ca, issuer):
    if issuer == 'rsa':
        ca = create_ca(cn='PQ leaf issuer RSA')
    else:
        r = _ml_dsa_ca(auth_client, '87')
        assert r.status_code == 201, r.get_json()
        ca = r.get_json()['data']
    r = _post(auth_client, '/api/v2/certificates', {
        'cn': f'mldsa44-under-{issuer}.example.test', 'ca_id': ca['id'],
        'key_type': 'ml-dsa', 'key_size': 44, 'validity_days': 30})
    assert r.status_code == 201, r.get_json()
    with app.app_context():
        leaf = _row_cert(db.session.get(Certificate, r.get_json()['data']['id']))
        ca_cert = _row_cert(db.session.get(CA, ca['id']))
    assert isinstance(leaf.public_key(), mldsa.MLDSA44PublicKey)
    leaf.verify_directly_issued_by(ca_cert)


def test_api_refuses_an_unknown_leaf_key_type(auth_client, create_ca):
    ca = create_ca(cn='PQ unknown leaf issuer')
    r = _post(auth_client, '/api/v2/certificates', {
        'cn': 'never.example.test', 'ca_id': ca['id'], 'key_type': 'FOO', 'key_size': 2048})
    assert r.status_code == 400, r.get_json()


def test_api_generates_an_ml_dsa_csr(app, auth_client):
    r = _post(auth_client, '/api/v2/csrs', {'cn': 'mldsa-csr.example.test', 'key_type': 'ML-DSA-65'})
    assert r.status_code == 201, r.get_json()
    with app.app_context():
        row = db.session.get(Certificate, r.get_json()['data']['id'])
        csr = x509.load_pem_x509_csr(base64.b64decode(row.csr))
    assert isinstance(csr.public_key(), mldsa.MLDSA65PublicKey)
    assert csr.is_signature_valid


def test_fips_refuses_ml_dsa_on_the_issue_path(app, auth_client, create_ca, monkeypatch):
    ca = create_ca(cn='PQ FIPS issuer')
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
    with app.app_context():
        before = Certificate.query.count()
    r = _post(auth_client, '/api/v2/certificates', {
        'cn': 'fips-mldsa.example.test', 'ca_id': ca['id'], 'key_type': 'ml-dsa', 'key_size': 65})
    # Refused by the registry generator, before the implicit FIPS policy is consulted
    assert r.status_code == 400, r.get_json()
    assert r.get_json()['type'] == fips_mode.PROBLEM_TYPE, r.get_json()
    assert 'ML-DSA-65' in r.get_json()['detail']
    with app.app_context():
        assert Certificate.query.count() == before


@pytest.mark.parametrize('key_type', ['ML-DSA-65', 'EC brainpoolP256r1'])
def test_fips_refuses_a_csr_key_with_the_fips_problem(app, auth_client, monkeypatch, key_type):
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
    with app.app_context():
        before = Certificate.query.count()
    r = _post(auth_client, '/api/v2/csrs', {'cn': 'fips-csr.example.test', 'key_type': key_type})
    assert r.status_code == 400, r.get_json()
    assert r.get_json()['type'] == fips_mode.PROBLEM_TYPE, r.get_json()
    with app.app_context():
        assert Certificate.query.count() == before


@pytest.mark.parametrize('extra', [{}, {'type': 'external'}])
def test_fips_refuses_an_ml_dsa_ca(app, auth_client, monkeypatch, extra):
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
    with app.app_context():
        before = CA.query.count()
    r = _ml_dsa_ca(auth_client, '65', **extra)
    assert r.status_code == 400, r.get_json()
    assert r.get_json()['type'] == fips_mode.PROBLEM_TYPE, r.get_json()
    assert 'ML-DSA-65' in r.get_json()['detail']
    with app.app_context():
        assert CA.query.count() == before


# ---- TSA signer ---------------------------------------------------------------

def test_tsa_signer_issue_refuses_ml_dsa(app, auth_client, create_ca):
    # Timestamps are signed in RSA or ECDSA only: an ML-DSA signer would be selected, then fail every request
    from models import SystemConfig
    ca = create_ca(cn='PQ TSA issuer')

    def selected():
        row = SystemConfig.query.filter_by(key='tsa_signer_cert_refid').first()
        return row.value if row else None
    with app.app_context():
        before, signer = Certificate.query.count(), selected()
    r = _post(auth_client, '/api/v2/tsa/signer-certificate',
              {'ca_id': ca['id'], 'key_type': 'ml-dsa', 'key_size': '65'})
    assert r.status_code == 400, r.get_json()
    assert 'RSA or ECDSA' in r.get_json()['detail']
    with app.app_context():
        assert Certificate.query.count() == before
        assert selected() == signer


def test_tsa_refuses_an_ml_dsa_ca_as_signer(app, auth_client):
    # Without a dedicated signer the CA signs the timestamps itself, in RSA or ECDSA only
    from models import SystemConfig
    r = _ml_dsa_ca(auth_client, '65', commonName='PQ TSA CA-as-signer')
    assert r.status_code == 201, r.get_json()
    with app.app_context():
        refid = db.session.get(CA, r.get_json()['data']['id']).refid

    def stored():
        return {row.key: row.value for row in SystemConfig.query.filter(
            SystemConfig.key.in_(('tsa_ca_refid', 'tsa_signer_cert_refid')))}
    with app.app_context():
        before = stored()
    r = auth_client.patch('/api/v2/tsa/config', content_type='application/json',
                          data=json.dumps({'ca_refid': refid, 'signer_cert_refid': ''}))
    assert r.status_code == 400, r.get_json()
    assert 'RSA or ECDSA' in r.get_json()['detail'] and 'ML-DSA-65' in r.get_json()['detail']
    with app.app_context():
        assert stored() == before
