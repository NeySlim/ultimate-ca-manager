"""Post-quantum keys are named, rated and sized like the API contract says:
key_algorithm and key_type carry the registry label, key_size is null, and
security_level/post_quantum tell them apart; classical keys are unchanged."""
import base64
import datetime
import uuid

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from models import Certificate, db
from tests.conftest import get_json
from tests.pqc_fixtures import fixture_bytes

MLDSA_PEM = fixture_bytes('mldsa65-cert.pem')
SLHDSA_PEM = fixture_bytes('slhdsa-sha2-128s-cert.pem')
CSR_PEM = fixture_bytes('mldsa65-csr.pem')


def _b64(pem):
    return base64.b64encode(pem).decode()


def _rsa_pem():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'classic')])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now).not_valid_after(now + datetime.timedelta(days=30))
            .sign(key, hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.PEM)


MLDSA_CONTRACT = {'key_type': 'ML-DSA-65', 'key_algorithm': 'ML-DSA-65', 'key_size': None,
                  'security_level': 3, 'post_quantum': True}
SLHDSA_CONTRACT = {'key_type': 'SLH-DSA-SHA2-128s', 'key_algorithm': 'SLH-DSA-SHA2-128s',
                   'key_size': None, 'security_level': 1, 'post_quantum': True,
                   'verifiable': False}


def _subset(data, expected):
    return {k: data.get(k) for k in expected}


# ------------------------------------------------------------- models

def test_ml_dsa_certificate_row_follows_the_contract():
    row = Certificate(refid='x', descr='x', crt=_b64(MLDSA_PEM))
    data = row.to_dict()
    assert _subset(data, MLDSA_CONTRACT) == MLDSA_CONTRACT
    assert data['signature_algorithm'] == 'ML-DSA-65'
    assert data['verifiable'] is True
    assert row.key_algo == 'ML-DSA-65'


def test_slh_dsa_certificate_row_is_named_by_its_oid_and_never_verifiable():
    row = Certificate(refid='x', descr='x', crt=_b64(SLHDSA_PEM))
    data = row.to_dict()
    assert _subset(data, SLHDSA_CONTRACT) == SLHDSA_CONTRACT
    assert data['signature_algorithm'] == 'SLH-DSA-SHA2-128s'
    assert row.key_algo == 'SLH-DSA-SHA2-128s'


def test_ml_dsa_request_row_names_its_key_and_signature():
    row = Certificate(refid='x', descr='x', csr=_b64(CSR_PEM))
    data = row.to_dict()
    assert _subset(data, MLDSA_CONTRACT) == MLDSA_CONTRACT
    assert data['signature_algorithm'] == 'ML-DSA-65'


def test_classical_certificate_row_is_unchanged():
    data = Certificate(refid='x', descr='x', crt=_b64(_rsa_pem())).to_dict()
    assert (data['key_type'], data['key_algorithm'], data['key_size']) == ('RSA 2048', 'RSA', 2048)
    assert data['post_quantum'] is False and data['security_level'] is None
    assert data['signature_algorithm'] == 'SHA256-RSA'


def test_ml_dsa_ca_row_follows_the_contract(mldsa_ca):
    data = mldsa_ca.to_dict()
    assert _subset(data, MLDSA_CONTRACT) == MLDSA_CONTRACT
    assert data['signature_algorithm'] == 'ML-DSA-65'
    assert data['hash_algorithm'] == 'ML-DSA-65'


def test_slh_dsa_ca_row_is_named():
    from models import CA
    data = CA(refid='c', descr='d', crt=_b64(SLHDSA_PEM)).to_dict()
    assert _subset(data, SLHDSA_CONTRACT) == SLHDSA_CONTRACT
    assert data['hash_algorithm'] == 'SLH-DSA-SHA2-128s'


def test_certificate_api_serves_the_contract(app, auth_client):
    refid = f'pq-display-{uuid.uuid4().hex[:8]}'
    with app.app_context():
        row = Certificate(refid=refid, descr=refid, crt=_b64(MLDSA_PEM),
                          subject='CN=UCM PQC fixture ML-DSA-65', issuer='CN=UCM PQC fixture ML-DSA-65')
        db.session.add(row)
        db.session.commit()
        cert_id = row.id
    try:
        r = auth_client.get(f'/api/v2/certificates/{cert_id}')
        assert r.status_code == 200, r.data
        data = get_json(r)['data']
        assert _subset(data, MLDSA_CONTRACT) == MLDSA_CONTRACT
        assert data['compliance']['breakdown']['key_strength']['score'] == 28
        assert data['compliance']['breakdown']['signature']['score'] == 25
    finally:
        with app.app_context():
            Certificate.query.filter_by(refid=refid).delete()
            db.session.commit()


# --------------------------------------------------------- parsers

@pytest.mark.parametrize('pem,label,level', [
    (MLDSA_PEM, 'ML-DSA-65', 3), (SLHDSA_PEM, 'SLH-DSA-SHA2-128s', 1)], ids=['mldsa', 'slhdsa'])
def test_parse_certificate_info(pem, label, level):
    from utils.cert_extensions import parse_certificate_info
    info = parse_certificate_info(pem.decode())
    assert (info['key_algorithm'], info['key_size']) == (label, None)
    assert (info['security_level'], info['post_quantum']) == (level, True)
    assert info['signature_algorithm'] == label


@pytest.mark.parametrize('pem,label,level', [
    (MLDSA_PEM, 'ML-DSA-65', 3), (SLHDSA_PEM, 'SLH-DSA-SHA2-128s', 1)], ids=['mldsa', 'slhdsa'])
def test_tools_decoder_dict(pem, label, level):
    from api.v2.tools import cert_to_dict
    public_key = cert_to_dict(x509.load_pem_x509_certificate(pem))['public_key']
    assert (public_key['type'], public_key['size']) == (label, None)
    assert (public_key['security_level'], public_key['post_quantum']) == (level, True)


def test_tools_csr_dict():
    from api.v2.tools import csr_to_dict
    data = csr_to_dict(x509.load_pem_x509_csr(CSR_PEM))
    assert data['public_key']['type'] == 'ML-DSA-65' and data['public_key']['size'] is None
    assert data['signature_algorithm'] == 'ML-DSA-65' and data['is_signature_valid'] is True


@pytest.mark.parametrize('pem,label', [(MLDSA_PEM, 'ML-DSA-65'), (SLHDSA_PEM, 'SLH-DSA-SHA2-128s')],
                         ids=['mldsa', 'slhdsa'])
def test_trust_store_details(pem, label):
    from services.trust_store.parsing_mixin import ParsingMixin
    public_key = ParsingMixin.parse_certificate_details(pem)['public_key']
    assert (public_key['algorithm'], public_key['key_size']) == (label, None)
    assert public_key['post_quantum'] is True


@pytest.mark.parametrize('pem,label', [(MLDSA_PEM, 'ML-DSA-65'), (SLHDSA_PEM, 'SLH-DSA-SHA2-128s')],
                         ids=['mldsa', 'slhdsa'])
def test_smart_import_parser(pem, label):
    from services.smart_import.parser import SmartParser
    certs = [o for o in SmartParser().parse(pem.decode()) if o.type.value == 'certificate']
    assert [(c.key_algorithm, c.key_size) for c in certs] == [(label, None)]


def test_smart_import_parser_names_an_ml_dsa_private_key():
    from services.smart_import.parser import SmartParser
    keys = [o for o in SmartParser().parse(fixture_bytes('mldsa65-seed.pem').decode())
            if o.type.value == 'private_key']
    assert [(k.key_algorithm, k.key_size) for k in keys] == [('ML-DSA-65', None)]


@pytest.mark.parametrize('pem,label', [(MLDSA_PEM, 'ML-DSA-65'), (SLHDSA_PEM, 'SLH-DSA-SHA2-128s')],
                         ids=['mldsa', 'slhdsa'])
def test_certificate_import_records_the_key(app, pem, label):
    from services.cert.service import CertificateService
    with app.app_context():
        cert = CertificateService.import_certificate(descr=f'pq-import-{uuid.uuid4().hex[:6]}',
                                                     cert_pem=pem.decode(), username='admin')
        try:
            assert cert.key_algo == label
        finally:
            db.session.delete(cert)
            db.session.commit()


def test_smart_import_spki_of_a_foreign_key():
    from services.smart_import.importer import _spki_der
    from utils.foreign_algorithms import spki_der
    cert = x509.load_pem_x509_certificate(SLHDSA_PEM)
    assert _spki_der(cert) == spki_der(cert)


# --------------------------------------------------------- compliance

@pytest.mark.parametrize('spelling,points', [
    ('ML-DSA-44', 25), ('ML-DSA-65', 28), ('ML-DSA-87', 30), ('SLH-DSA-SHA2-128s', 30),
    ('SLH-DSA-SHAKE-256f', 30)])
def test_post_quantum_key_strength(spelling, points):
    from services.compliance_service import _score_key_strength
    score = _score_key_strength({'key_algorithm': spelling, 'key_size': None})
    assert (score['score'], score['reason']) == (points, spelling)


@pytest.mark.parametrize('spelling', ['ML-DSA-65', 'SLH-DSA-SHA2-128s'])
def test_post_quantum_signature_scores_full(spelling):
    from services.compliance_service import _score_signature
    assert _score_signature({'signature_algorithm': spelling})['score'] == 25


def test_sort_points_rank_post_quantum_keys():
    from services.compliance_service import key_algo_sort_points
    points = dict(key_algo_sort_points())
    assert points['ML-DSA-44'] == 25 and points['ML-DSA-87'] == 30
    assert points['SLH-DSA-SHA2-128s'] == 30


# ------------------------------------------------------ foreign names

def test_slh_dsa_oids_are_named():
    from utils.foreign_algorithms import describe_public_key, signature_name
    info = describe_public_key(x509.load_pem_x509_certificate(SLHDSA_PEM))
    assert info['name'] == info['label'] == 'SLH-DSA-SHA2-128s'
    assert info['oid'] == '2.16.840.1.101.3.4.3.20' and info['key_size'] is None
    assert signature_name('2.16.840.1.101.3.4.3.31') == 'SLH-DSA-SHAKE-256f'


def test_registry_rates_post_quantum_names():
    from utils import key_algorithms as ka
    assert ka.is_post_quantum('SLH-DSA-SHA2-192f')
    assert ka.post_quantum_info('2.16.840.1.101.3.4.3.24').label == 'SLH-DSA-SHA2-256s'
    assert ka.post_quantum_info('slh-dsa-sha2-256s').security_level == 5
    assert ka.post_quantum_info('mldsa44').security_level == 2
    assert ka.post_quantum_info('RSA-2048') is None


# ------------------------------------------- mTLS enrolments, trust store

RSA_CONTRACT = {'key_type': 'RSA 2048', 'key_algorithm': 'RSA', 'key_size': 2048,
                'security_level': None, 'post_quantum': False}
_ROUTE_CASES = [('rsa', RSA_CONTRACT, 'SHA256-RSA'), ('mldsa', MLDSA_CONTRACT, 'ML-DSA-65'),
                ('slhdsa', {k: v for k, v in SLHDSA_CONTRACT.items() if k != 'verifiable'},
                 'SLH-DSA-SHA2-128s')]


def _route_pem(kind):
    return {'rsa': _rsa_pem, 'mldsa': lambda: MLDSA_PEM, 'slhdsa': lambda: SLHDSA_PEM}[kind]()


@pytest.mark.parametrize('kind,contract,_sig', _ROUTE_CASES, ids=[c[0] for c in _ROUTE_CASES])
def test_mtls_listing_names_the_key(app, auth_client, kind, contract, _sig):
    from models import User
    from models.auth_certificate import AuthCertificate
    pem = _route_pem(kind)
    serial = uuid.uuid4().hex
    with app.app_context():
        admin = User.query.filter_by(username='admin').first()
        db.session.add(AuthCertificate(user_id=admin.id, cert_pem=pem, cert_serial=serial,
                                       cert_subject='CN=classic', name=f'pq-{serial}'))
        db.session.commit()
    try:
        r = auth_client.get('/api/v2/mtls/certificates')
        assert r.status_code == 200, r.data
        [row] = [c for c in get_json(r)['data'] if c['cert_serial'] == serial]
        assert _subset(row, contract) == contract
    finally:
        with app.app_context():
            AuthCertificate.query.filter_by(cert_serial=serial).delete()
            db.session.commit()


def test_mtls_listing_names_the_key_of_an_enrolment_without_its_pem(app, auth_client):
    from models import User
    from models.auth_certificate import AuthCertificate
    cert = x509.load_pem_x509_certificate(MLDSA_PEM)
    serial, refid = str(cert.serial_number), f'pq-mtls-{uuid.uuid4().hex[:8]}'
    issuer = cert.issuer.rfc4514_string()
    with app.app_context():
        admin = User.query.filter_by(username='admin').first()
        db.session.add(Certificate(refid=refid, descr=refid, crt=_b64(MLDSA_PEM),
                                   serial_number=serial, subject=issuer, issuer=issuer))
        db.session.add(AuthCertificate(user_id=admin.id, cert_serial=serial, cert_subject=issuer,
                                       cert_issuer=issuer, name=refid))
        db.session.commit()
    try:
        r = auth_client.get('/api/v2/mtls/certificates')
        assert r.status_code == 200, r.data
        [row] = [c for c in get_json(r)['data'] if c['name'] == refid]
        assert _subset(row, MLDSA_CONTRACT) == MLDSA_CONTRACT
    finally:
        with app.app_context():
            AuthCertificate.query.filter_by(name=refid).delete()
            Certificate.query.filter_by(refid=refid).delete()
            db.session.commit()


@pytest.mark.parametrize('kind,contract,sig', _ROUTE_CASES, ids=[c[0] for c in _ROUTE_CASES])
def test_trust_store_names_the_key(app, auth_client, kind, contract, sig):
    from models.truststore import TrustedCertificate
    pem = _route_pem(kind)
    fingerprint = uuid.uuid4().hex + uuid.uuid4().hex
    with app.app_context():
        row = TrustedCertificate(name=f'pq-{fingerprint[:8]}', certificate_pem=pem.decode(),
                                 fingerprint_sha256=fingerprint, purpose='root_ca')
        db.session.add(row)
        db.session.commit()
        row_id = row.id
    try:
        for url in ('/api/v2/truststore', f'/api/v2/truststore/{row_id}'):
            r = auth_client.get(url)
            assert r.status_code == 200, r.data
            data = get_json(r)['data']
            item = next(c for c in data if c['id'] == row_id) if isinstance(data, list) else data
            assert _subset(item, contract) == contract, url
            assert item['signature_algorithm'] == sig, url
    finally:
        with app.app_context():
            TrustedCertificate.query.filter_by(id=row_id).delete()
            db.session.commit()
