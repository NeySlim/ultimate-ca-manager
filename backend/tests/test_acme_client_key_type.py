"""ACME client certificate key type: the setting is the default, unknown types fail."""
import base64
import json

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, ed25519

from models import db, SystemConfig
from models.acme_models import AcmeClientOrder
from services.acme.acme_client_service import AcmeClientService

REQUEST = '/api/v2/acme/client/request'


@pytest.fixture
def key_type_setting(app):
    """Set acme.client.key_type, restoring the previous value afterwards."""
    with app.app_context():
        row = SystemConfig.query.filter_by(key='acme.client.key_type').first()
        previous = row.value if row else None

    def _set(value):
        with app.app_context():
            cfg = SystemConfig.query.filter_by(key='acme.client.key_type').first()
            if cfg is None:
                cfg = SystemConfig(key='acme.client.key_type', value=value)
                db.session.add(cfg)
            else:
                cfg.value = value
            db.session.commit()

    yield _set
    with app.app_context():
        cfg = SystemConfig.query.filter_by(key='acme.client.key_type').first()
        if previous is None and cfg is not None:
            db.session.delete(cfg)
        elif cfg is not None:
            cfg.value = previous
        db.session.commit()


@pytest.fixture
def fake_issuance(app, monkeypatch):
    """A real service whose create_order stores a local order without contacting a CA."""
    created = []

    def create_order(self, domains, email, challenge_type, dns_provider_id=None, **_kw):
        order = AcmeClientOrder(
            domains=json.dumps(domains), challenge_type=challenge_type,
            environment='staging', status='pending',
            order_url=f'https://ca.example/order/{len(created) + 1}',
            finalize_url=f'https://ca.example/order/{len(created) + 1}/finalize',
        )
        db.session.add(order)
        db.session.commit()
        created.append(order.id)
        return True, 'Order created', order

    monkeypatch.setattr(AcmeClientService, 'create_order', create_order)
    monkeypatch.setattr(AcmeClientService, 'for_issuance',
                        classmethod(lambda cls, **_kw: object.__new__(cls)))
    yield created
    with app.app_context():
        for order_id in created:
            order = db.session.get(AcmeClientOrder, order_id)
            if order is not None:
                db.session.delete(order)
        db.session.commit()


def _request(auth_client, **extra):
    body = {'domains': ['keytype.example.com'], 'email': 'admin@example.com',
            'challenge_type': 'http-01', 'environment': 'staging', **extra}
    return auth_client.post(REQUEST, json=body)


class _FinalizeResponse:
    status_code = 200

    def json(self):
        return {'status': 'processing', 'certificate': 'https://ca.example/cert/1'}


class _CertResponse:
    status_code = 200
    headers = {}
    text = '-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n'


def _finalize(order):
    """Run finalize_order against a fake CA; returns (result, submitted CSR or None)."""
    captured = {}
    svc = object.__new__(AcmeClientService)
    svc.check_order_status = lambda o: ('ready', {})

    def post(url, payload):
        if 'finalize' in url:
            captured['csr'] = payload['csr']
            return _FinalizeResponse()
        return _CertResponse()

    svc._post = post
    svc._import_certificate = lambda **kw: 7
    result = AcmeClientService.finalize_order(svc, order)
    csr = None
    if 'csr' in captured:
        der = base64.urlsafe_b64decode(captured['csr'] + '=' * (-len(captured['csr']) % 4))
        csr = x509.load_der_x509_csr(der)
    return result, csr


def test_order_without_key_type_takes_the_setting(app, auth_client, key_type_setting, fake_issuance):
    key_type_setting('EC-P384')
    r = _request(auth_client)
    assert r.status_code == 201, r.get_json()
    assert r.get_json()['data']['order']['key_type'] == 'EC-P384'

    with app.app_context():
        order = db.session.get(AcmeClientOrder, fake_issuance[-1])
        assert order.key_type == 'EC-P384'
        (ok, msg, _), csr = _finalize(order)
        assert ok, msg
        assert isinstance(csr.public_key(), ec.EllipticCurvePublicKey)
        assert csr.public_key().curve.name == 'secp384r1'


def test_explicit_key_type_wins_over_the_setting(app, auth_client, key_type_setting, fake_issuance):
    key_type_setting('EC-P384')
    r = _request(auth_client, key_type='EC-P256')
    assert r.status_code == 201, r.get_json()
    with app.app_context():
        assert db.session.get(AcmeClientOrder, fake_issuance[-1]).key_type == 'EC-P256'


def test_request_rejects_a_type_the_client_cannot_generate(auth_client, fake_issuance):
    r = _request(auth_client, key_type='RSA-3072')
    assert r.status_code == 400
    assert 'key type' in r.get_json()['message'].lower()
    assert fake_issuance == []


def test_unknown_key_type_on_order_fails_finalize(app):
    with app.app_context():
        order = AcmeClientOrder(
            domains=json.dumps(['unknown-type.example.com']), challenge_type='http-01',
            environment='staging', status='ready', key_source='generate', key_type='DSA-1024',
            order_url='https://ca.example/order/x', finalize_url='https://ca.example/order/x/finalize',
        )
        (ok, msg, cert_id), csr = _finalize(order)
        assert not ok
        assert 'DSA-1024' in msg
        assert csr is None and cert_id is None


def test_csr_order_reports_no_generated_key_type(app):
    with app.app_context():
        order = AcmeClientOrder(
            domains=json.dumps(['csr.example.com']), challenge_type='http-01',
            environment='staging', status='pending', key_source='csr', key_type='RSA-2048',
        )
        assert order.to_dict()['key_type'] is None
        order.key_source = 'reuse'
        order.source_certificate_id = 12
        assert order.to_dict()['key_type'] is None
        order.key_source = 'generate'
        assert order.to_dict()['key_type'] == 'RSA-2048'


def test_csr_order_stores_no_key_type(app, auth_client, key_type_setting, fake_issuance):
    key = ec.generate_private_key(ec.SECP256R1())
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, 'keytype.example.com')]))
           .add_extension(x509.SubjectAlternativeName([x509.DNSName('keytype.example.com')]), critical=False)
           .sign(key, hashes.SHA256()))
    from cryptography.hazmat.primitives.serialization import Encoding
    key_type_setting('EC-P384')
    r = _request(auth_client, key_source='csr', csr_pem=csr.public_bytes(Encoding.PEM).decode())
    assert r.status_code == 201, r.get_json()
    with app.app_context():
        assert db.session.get(AcmeClientOrder, fake_issuance[-1]).key_type is None


def _csr_from_b64(value):
    return x509.load_der_x509_csr(base64.urlsafe_b64decode(value + '=' * (-len(value) % 4)))


def test_csr_signed_by_an_ed25519_key_is_valid():
    key = ed25519.Ed25519PrivateKey.generate()
    csr = _csr_from_b64(AcmeClientService._build_csr_b64(key, ['ed.example.com'], 'ed.example.com'))
    assert csr.is_signature_valid
    assert csr.signature_hash_algorithm is None


@pytest.mark.parametrize('curve, digest', [
    (ec.SECP256R1, hashes.SHA256), (ec.SECP384R1, hashes.SHA384), (ec.SECP521R1, hashes.SHA512),
])
def test_ec_csr_digest_matches_the_curve(curve, digest):
    key = ec.generate_private_key(curve())
    csr = _csr_from_b64(AcmeClientService._build_csr_b64(key, ['ec.example.com'], 'ec.example.com'))
    assert csr.is_signature_valid
    assert isinstance(csr.signature_hash_algorithm, digest)


def test_proxy_order_does_not_claim_a_key_type(app):
    """The proxy's client finalizes with its own key: no type is stored or reported."""
    with app.app_context():
        order = AcmeClientOrder(
            domains=json.dumps(['proxy.example.com']), challenge_type='dns-01',
            environment='staging', status='pending', is_proxy_order=True,
            order_url='https://ca.example/order/proxy-keytype',
        )
        db.session.add(order)
        db.session.commit()
        try:
            db.session.refresh(order)
            assert order.key_type is None
            assert order.to_dict()['key_type'] is None
        finally:
            db.session.delete(order)
            db.session.commit()


def test_an_unsupported_account_key_is_refused_not_signed_rs256():
    import pytest
    from cryptography.hazmat.primitives.asymmetric import ec, ed25519
    from services.acme.acme_client_service import AcmeClientService
    detect = AcmeClientService._detect_key_algorithm
    assert detect(None, ec.generate_private_key(ec.SECP384R1())) == 'ES384'
    for key in (ec.generate_private_key(ec.SECP521R1()), ed25519.Ed25519PrivateKey.generate()):
        with pytest.raises(ValueError, match='Unsupported ACME account key'):
            detect(None, key)
