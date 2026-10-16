"""certificates.key_algo follows the certificate on every path: issuance left
it empty (only imports, renewals and the TSA wrote it), so sorting by key
algorithm or compliance grade lumped most certificates together."""
import base64
import datetime
import importlib.util
import json
import sqlite3

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa
from cryptography.x509.oid import NameOID

from models import Certificate, db
from tests.conftest import get_json


def _crt(key, cn='key-algo.test'):
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.datetime.now(datetime.timezone.utc)
    algorithm = None if isinstance(key, ed25519.Ed25519PrivateKey) else hashes.SHA256()
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now).not_valid_after(now + datetime.timedelta(days=30))
            .sign(key, algorithm))
    return base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode()


def _key_algo(app, cert_id):
    with app.app_context():
        return db.session.get(Certificate, cert_id).key_algo


def test_issued_certificates_record_their_key_algorithm(app, create_cert):
    rsa_cert = create_cert(cn='key-algo-rsa.test', key_type='RSA', key_size=3072)
    ec_cert = create_cert(cn='key-algo-ec.test', key_type='EC', curve='P-384')
    assert _key_algo(app, rsa_cert['id']) == 'RSA 3072'
    assert _key_algo(app, ec_cert['id']) == 'EC secp384r1'


def test_setting_crt_sets_key_algo_and_key_type():
    row = Certificate(refid='x', descr='x', crt=_crt(ed25519.Ed25519PrivateKey.generate()))
    assert row.key_algo == 'Ed25519' and row.key_type == 'Ed25519'
    row.crt = _crt(ec.generate_private_key(ec.SECP256R1()))
    assert row.key_algo == 'EC secp256r1'


def test_compliance_sort_ranks_stronger_keys_higher(app, auth_client, create_cert):
    # P-256 scores 25 and RSA 4096 30; the old SQL gave every EC key 30, and
    # the name tie-break then put the P-256 first
    weak = create_cert(cn='grade-sort-a-p256.test', key_type='EC', curve='P-256')
    strong = create_cert(cn='grade-sort-b-rsa4096.test', key_type='RSA', key_size=4096)
    r = auth_client.get('/api/v2/certificates?search=grade-sort-&sort_by=compliance_grade'
                        '&sort_order=desc&per_page=50')
    assert r.status_code == 200, r.data
    ids = [c['id'] for c in get_json(r)['data'] if c['id'] in (weak['id'], strong['id'])]
    assert ids == [strong['id'], weak['id']]


def _migration():
    spec = importlib.util.spec_from_file_location(
        'm095', 'migrations/095_certificate_key_algo_backfill.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_recomputes_every_readable_certificate():
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE certificates (id INTEGER PRIMARY KEY, crt TEXT, key_algo VARCHAR(50))')
    rows = [
        (1, _crt(rsa.generate_private_key(public_exponent=65537, key_size=2048)), None),
        (2, _crt(ec.generate_private_key(ec.SECP384R1())), ''),
        (3, _crt(ed25519.Ed25519PrivateKey.generate()), 'EdDSA'),
        (4, _crt(rsa.generate_private_key(public_exponent=65537, key_size=2048)), 'RSA'),
        (7, _crt(ec.generate_private_key(ec.SECP256R1())), 'ECDSA'),
        (5, None, None),
        (6, 'not a certificate', 'kept as is'),
    ]
    conn.executemany('INSERT INTO certificates VALUES (?, ?, ?)', rows)
    _migration().upgrade(conn)
    assert dict(conn.execute('SELECT id, key_algo FROM certificates').fetchall()) == {
        1: 'RSA 2048', 2: 'EC secp384r1', 3: 'Ed25519', 4: 'RSA 2048', 5: None,
        6: 'kept as is', 7: 'EC secp256r1'}


def test_dsa_and_curves_outside_the_registry():
    from cryptography.hazmat.primitives.asymmetric import dsa
    from utils.key_algorithms import key_algo_for_public_key
    assert key_algo_for_public_key(dsa.generate_private_key(key_size=2048).public_key()) == 'DSA 2048'
    assert key_algo_for_public_key(ec.generate_private_key(ec.SECP256K1()).public_key()) == 'EC secp256k1'


def test_compliance_sort_scores_other_curves_like_the_service(app, auth_client):
    # secp256k1 scores 15 in compliance_service and in the SQL sort; a DSA key 10.
    # Names are chosen so the name tie-break would put the DSA first.
    from cryptography.hazmat.primitives.asymmetric import dsa
    from services.cert_service import CertificateService
    ids = []
    with app.app_context():
        for cn, key in (('grade-other-a-dsa.test', dsa.generate_private_key(key_size=2048)),
                        ('grade-other-b-k1.test', ec.generate_private_key(ec.SECP256K1()))):
            pem = base64.b64decode(_crt(key, cn)).decode()
            ids.append(CertificateService.import_certificate(descr=cn, cert_pem=pem).id)
    try:
        r = auth_client.get('/api/v2/certificates?search=grade-other-&sort_by=compliance_grade'
                            '&sort_order=desc&per_page=50')
        assert r.status_code == 200, r.data
        order = [c['id'] for c in get_json(r)['data'] if c['id'] in ids]
        assert order == [ids[1], ids[0]]
    finally:
        with app.app_context():
            for cert_id in ids:
                db.session.delete(db.session.get(Certificate, cert_id))
            db.session.commit()
