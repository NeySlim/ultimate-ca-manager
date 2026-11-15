"""RFC 3161 §2.3: with tsa_require_dedicated_cert absent, /tsa signs only with a dedicated signer."""
import hashlib
import json

import pytest
from asn1crypto import algos, tsp

from models import CA, SystemConfig, db

KEY = 'tsa_require_dedicated_cert'
KEYS = ('tsa_enabled', 'tsa_ca_refid', 'tsa_signer_cert_refid', KEY)
TS_OID = '1.3.6.1.5.5.7.3.8'


def _tsq(label):
    return tsp.TimeStampReq({
        'version': 1,
        'message_imprint': tsp.MessageImprint({
            'hash_algorithm': algos.DigestAlgorithm({'algorithm': 'sha256'}),
            'hashed_message': hashlib.sha256(label).digest(),
        }),
        'cert_req': True,
    }).dump()


def _clear(app):
    with app.app_context():
        SystemConfig.query.filter(SystemConfig.key.in_(KEYS)).delete(synchronize_session=False)
        db.session.commit()


@pytest.fixture
def tsa(app):
    _clear(app)

    def put(**cfg):
        with app.app_context():
            for k, v in cfg.items():
                row = SystemConfig.query.filter_by(key=k).first() or SystemConfig(key=k)
                row.value = v
                db.session.add(row)
            db.session.commit()
    yield put
    _clear(app)


def _ca_refid(app, create_ca, cn):
    ca = create_ca(cn=cn)
    with app.app_context():
        return db.session.get(CA, ca['id']).refid


def _post(client, label):
    return client.post('/tsa', data=_tsq(label), content_type='application/timestamp-query')


def _config(auth_client):
    return json.loads(auth_client.get('/api/v2/tsa/config').data)['data']


def test_absent_setting_reads_as_required(auth_client, tsa):
    assert _config(auth_client)['require_dedicated_cert'] is True


@pytest.mark.parametrize('stored,expected', [('true', True), ('false', False), ('garbage', True), ('', True)])
def test_only_the_exact_word_false_turns_it_off(app, auth_client, tsa, stored, expected):
    from services.tsa_service import TSAService
    tsa(**{KEY: stored})
    with app.app_context():
        runtime = TSAService._require_dedicated_tsa_cert()
    assert (runtime, _config(auth_client)['require_dedicated_cert']) == (expected, expected)


def test_the_ca_does_not_sign_by_default(app, client, create_ca, tsa):
    tsa(tsa_ca_refid=_ca_refid(app, create_ca, 'TSA default strict CA'))
    resp = _post(client, b'strict by default')
    # The service is unavailable: the same 503 the explicit strict mode always answered
    assert resp.status_code == 503
    assert resp.mimetype == 'text/plain'
    assert resp.data == b'TSA configuration invalid'


def test_the_ca_signs_when_the_operator_turned_it_off(app, client, create_ca, tsa):
    tsa(tsa_ca_refid=_ca_refid(app, create_ca, 'TSA compat CA'), **{KEY: 'false'})
    resp = _post(client, b'compat')
    assert resp.status_code == 200
    assert tsp.TimeStampResp.load(resp.data)['status']['status'].native == 'granted'


def test_a_dedicated_signer_signs_by_default(app, client, create_ca, create_cert, tsa):
    ca = create_ca(cn='TSA default dedicated CA')
    signer = create_cert(cn='tsa-default-dedicated', ca_id=ca['id'], extra_ekus=[TS_OID])
    with app.app_context():
        tsa(tsa_ca_refid=db.session.get(CA, ca['id']).refid, tsa_signer_cert_refid=signer['refid'])
    resp = _post(client, b'dedicated')
    assert resp.status_code == 200
    token = tsp.TimeStampResp.load(resp.data)
    assert token['status']['status'].native == 'granted'
    signed = token['time_stamp_token']['content']
    sid = signed['signer_infos'][0]['sid'].chosen
    by_serial = {c.chosen.serial_number: c.chosen for c in signed['certificates']}
    assert by_serial[sid['serial_number'].native].subject.native['common_name'] == 'tsa-default-dedicated'


def test_a_ca_certificate_with_the_timestamping_eku_does_not_sign_either(app, client, create_ca, tsa):
    import base64
    from datetime import datetime, timedelta, timezone
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'TSA CA with timeStamping')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=30))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.TIME_STAMPING]), critical=True)
            .sign(key, hashes.SHA256()))
    refid = _ca_refid(app, create_ca, 'TSA timeStamping CA')
    with app.app_context():
        ca = CA.query.filter_by(refid=refid).first()
        ca.crt = base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode()
        ca.prv = base64.b64encode(key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption())).decode()
        db.session.commit()
    tsa(tsa_ca_refid=refid)
    resp = _post(client, b'ca with timeStamping')
    assert (resp.status_code, resp.data) == (503, b'TSA configuration invalid')
