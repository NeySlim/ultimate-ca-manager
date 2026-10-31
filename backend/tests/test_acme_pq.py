"""ACME and ML-DSA: finalize of an OpenSSL ML-DSA-44 request under an RSA and an ML-DSA CA,
revocation of an ML-DSA certificate, ARI on it, and the ACME client's ML-DSA key types."""
import base64 as b64
import json
import re
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from models import CA, Certificate, SystemConfig, db
from models.acme_models import AcmeAccount, AcmeOrder
from services.acme import profiles as acme_profiles
from services.acme.acme_service import AcmeService
from utils import key_algorithms

pytestmark = pytest.mark.skipif(not key_algorithms.mldsa_supported(),
                                reason='this build has no ML-DSA')

OPENSSL = shutil.which('openssl')


def _openssl_35():
    if not OPENSSL:
        return False
    out = subprocess.run([OPENSSL, 'version'], capture_output=True, text=True).stdout
    m = re.match(r'OpenSSL (\d+)\.(\d+)', out)
    return bool(m) and (int(m.group(1)), int(m.group(2))) >= (3, 5)


needs_openssl_35 = pytest.mark.skipif(not _openssl_35(), reason='needs OpenSSL 3.5 or later')


def openssl_mldsa_csr(tmp_path, cn, dns=(), alg='ML-DSA-44'):
    """(CSR, private key) made by ``openssl req`` over a seed-only ML-DSA key, the
    layout pyca reads back. Shared with ``test_est_pq``."""
    key_pem, csr_pem = tmp_path / f'{alg}-key.pem', tmp_path / f'{alg}-csr.pem'
    subprocess.run([OPENSSL, 'genpkey', '-algorithm', alg,
                    '-provparam', 'ml-dsa.output_formats=seed-only', '-out', str(key_pem)],
                   check=True, capture_output=True)
    args = [OPENSSL, 'req', '-new', '-key', str(key_pem), '-subj', f'/CN={cn}', '-out', str(csr_pem)]
    if dns:
        args += ['-addext', 'subjectAltName=' + ','.join(f'DNS:{d}' for d in dns)]
    subprocess.run(args, check=True, capture_output=True)
    key = serialization.load_pem_private_key(key_pem.read_bytes(), None)
    return x509.load_pem_x509_csr(csr_pem.read_bytes()), key


def _b64u(raw):
    return b64.urlsafe_b64encode(raw).rstrip(b'=').decode()


def _b64json(obj):
    return _b64u(json.dumps(obj).encode())


def _rsa_jwk(key):
    pub = key.public_key().public_numbers()
    return {'kty': 'RSA', 'n': _b64u(pub.n.to_bytes((pub.n.bit_length() + 7) // 8, 'big')),
            'e': _b64u(pub.e.to_bytes((pub.e.bit_length() + 7) // 8, 'big'))}


def _jws(client, path, payload, key, *, kid=None, jwk=None):
    nonce = client.get('/acme/new-nonce').headers.get('Replay-Nonce')
    protected = {'alg': 'RS256', 'nonce': nonce, 'url': f'http://localhost{path}'}
    protected.update({'kid': kid} if kid else {'jwk': jwk})
    p64, b64p = _b64json(protected), _b64json(payload)
    sig = key.sign(f'{p64}.{b64p}'.encode(), padding.PKCS1v15(), hashes.SHA256())
    return client.post(path, data=json.dumps({'protected': p64, 'payload': b64p,
                                              'signature': _b64u(sig)}),
                       content_type='application/jose+json')


@pytest.fixture
def rsa_account(app):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = _rsa_jwk(key)
    with app.app_context():
        acct = AcmeAccount(jwk=json.dumps(jwk), status='valid',
                           jwk_thumbprint=uuid.uuid4().hex + uuid.uuid4().hex[:11])
        db.session.add(acct)
        db.session.commit()
        return {'key': key, 'jwk': jwk, 'id': acct.account_id,
                'kid': f'http://localhost/acme/acct/{acct.account_id}'}


@pytest.fixture(scope='module')
def rsa_ca(create_ca):
    return create_ca(cn='ACME PQ RSA root')


@pytest.fixture(scope='module')
def mldsa_issuing_ca(create_ca):
    return create_ca(cn='ACME PQ ML-DSA-65 root', keyAlgo='ML-DSA', keySize=65)


@pytest.fixture
def signing_ca(monkeypatch, app):
    """Points finalize at the CA a test names, with CAA allowed."""
    from utils import caa_checker
    monkeypatch.setattr(caa_checker, 'check_caa_for_domains', lambda *a, **k: (True, 'allowed'))

    def _use(ca):
        with app.app_context():
            refid = db.session.get(CA, ca['id']).refid
        monkeypatch.setattr(AcmeService, '_resolve_ca_for_domains', lambda self, _d: refid)
        return refid
    return _use


def _ready_order(app, account, domain, profile=None):
    with app.app_context():
        order = AcmeOrder(account_id=account['id'], status='ready', profile=profile,
                          identifiers=json.dumps([{'type': 'dns', 'value': domain}]))
        db.session.add(order)
        db.session.commit()
        return order.order_id


def _finalize(app, client, account, tmp_path, domain, profile=None):
    order_id = _ready_order(app, account, domain, profile)
    csr, key = openssl_mldsa_csr(tmp_path, domain, [domain])
    path = f'/acme/order/{order_id}/finalize'
    r = _jws(client, path, {'csr': _b64u(csr.public_bytes(serialization.Encoding.DER))},
             account['key'], kid=account['kid'])
    return r, order_id, key


def _issued(app, order_id):
    with app.app_context():
        order = AcmeOrder.query.filter_by(order_id=order_id).first()
        row = db.session.get(Certificate, order.certificate_id)
        ca = CA.query.filter_by(refid=row.caref).first()
        return (x509.load_pem_x509_certificate(b64.b64decode(row.crt)),
                x509.load_pem_x509_certificate(b64.b64decode(ca.crt)), row.id)


@needs_openssl_35
class TestFinalizeMldsaRequest:
    """RSA account, ML-DSA-44 request from ``openssl req``, RSA or ML-DSA issuer."""

    @pytest.mark.parametrize('issuer', ['rsa_ca', 'mldsa_issuing_ca'])
    def test_finalize_issues_the_mldsa_leaf(self, app, client, rsa_account, signing_ca,
                                            tmp_path, request, issuer):
        signing_ca(request.getfixturevalue(issuer))
        domain = f'{issuer.replace("_", "-")}.pq.example.com'
        r, order_id, key = _finalize(app, client, rsa_account, tmp_path, domain)
        assert r.status_code == 200, r.get_json()
        assert r.get_json()['status'] == 'valid'
        leaf, ca_cert, _ = _issued(app, order_id)
        assert key_algorithms.label_for_public_key(leaf.public_key()) == 'ML-DSA-44'
        assert leaf.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo) == \
            key.public_key().public_bytes(
                serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        leaf.verify_directly_issued_by(ca_cert)

    @pytest.mark.parametrize('issuer', ['rsa_ca', 'mldsa_issuing_ca'])
    def test_fips_mode_refuses_the_mldsa_request(self, app, client, rsa_account, signing_ca,
                                                 tmp_path, monkeypatch, request, issuer):
        import fips_mode
        signing_ca(request.getfixturevalue(issuer))
        monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
        r, order_id, _ = _finalize(app, client, rsa_account, tmp_path,
                                   f'fips-{issuer.replace("_", "-")}.pq.example.com')
        body = r.get_json()
        assert r.status_code == 400, body
        assert body['type'] == 'urn:ietf:params:acme:error:badCSR', body
        assert 'ML-DSA-44 keys are not available in FIPS mode' in body['detail'], body
        with app.app_context():
            assert AcmeOrder.query.filter_by(order_id=order_id).first().certificate_id is None

    def test_profile_digest_yields_to_an_mldsa_issuer(self, app, client, rsa_account,
                                                       signing_ca, mldsa_issuing_ca, tmp_path):
        """A profile that names sha384 still issues under an ML-DSA CA, which signs without one."""
        signing_ca(mldsa_issuing_ca)
        with app.app_context():
            db.session.add(SystemConfig(key=acme_profiles.CONFIG_KEY,
                                        value=json.dumps({'pq384': {'digest': 'sha384'}})))
            db.session.commit()
        try:
            r, order_id, _ = _finalize(app, client, rsa_account, tmp_path,
                                       'profile.pq.example.com', profile='pq384')
        finally:
            with app.app_context():
                SystemConfig.query.filter_by(key=acme_profiles.CONFIG_KEY).delete()
                db.session.commit()
        assert r.status_code == 200, r.get_json()
        leaf, ca_cert, _ = _issued(app, order_id)
        assert leaf.signature_hash_algorithm is None
        leaf.verify_directly_issued_by(ca_cert)

    def test_ari_answers_for_the_mldsa_leaf(self, app, client, rsa_account, signing_ca,
                                             mldsa_issuing_ca, tmp_path):
        signing_ca(mldsa_issuing_ca)
        r, order_id, _ = _finalize(app, client, rsa_account, tmp_path, 'ari.pq.example.com')
        assert r.status_code == 200, r.get_json()
        leaf, _, _ = _issued(app, order_id)
        aki = leaf.extensions.get_extension_for_class(x509.AuthorityKeyIdentifier).value
        n = leaf.serial_number
        certid = f'{_b64u(aki.key_identifier)}.{_b64u(n.to_bytes((n.bit_length() + 7) // 8, "big"))}'
        # sign_csr leaves the AKI column to the scheduled backfill, whatever the key
        from services.ski_aki_backfill import backfill_ski_aki
        with app.app_context():
            backfill_ski_aki()
        r = client.get(f'/acme/renewalInfo/{certid}')
        assert r.status_code == 200, r.data
        assert set(r.get_json()['suggestedWindow']) == {'start', 'end'}


@needs_openssl_35
class TestRevokeMldsaCertificate:
    """RFC 8555 §7.6 by the issuing account, and by a key that cannot sign a JWS."""

    def _issue(self, app, client, account, signing_ca, ca, tmp_path, domain):
        signing_ca(ca)
        r, order_id, key = _finalize(app, client, account, tmp_path, domain)
        assert r.status_code == 200, r.get_json()
        leaf, _, cert_id = _issued(app, order_id)
        return leaf, cert_id, key

    def test_issuing_account_revokes_it(self, app, client, rsa_account, signing_ca,
                                         mldsa_issuing_ca, tmp_path):
        leaf, cert_id, _ = self._issue(app, client, rsa_account, signing_ca, mldsa_issuing_ca,
                                       tmp_path, 'revoke.pq.example.com')
        r = _jws(client, '/acme/revoke-cert',
                 {'certificate': _b64u(leaf.public_bytes(serialization.Encoding.DER))},
                 rsa_account['key'], kid=rsa_account['kid'])
        assert r.status_code == 200, r.get_json()
        with app.app_context():
            assert db.session.get(Certificate, cert_id).revoked

    @pytest.mark.parametrize('by', ['jwk', 'other_account'])
    def test_a_stranger_is_told_why(self, app, client, rsa_account, signing_ca, rsa_ca,
                                    tmp_path, by):
        """An ML-DSA key cannot sign an ACME request: a jwk requester is told so; another
        account, which never tried the key, gets the plain refusal."""
        leaf, cert_id, _ = self._issue(app, client, rsa_account, signing_ca, rsa_ca,
                                       tmp_path, f'stranger-{by}.pq.example.com')
        payload = {'certificate': _b64u(leaf.public_bytes(serialization.Encoding.DER))}
        if by == 'jwk':
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            r = _jws(client, '/acme/revoke-cert', payload, key, jwk=_rsa_jwk(key))
        else:
            other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            with app.app_context():
                other = AcmeAccount(jwk=json.dumps(_rsa_jwk(other_key)), status='valid',
                                    jwk_thumbprint=uuid.uuid4().hex + uuid.uuid4().hex[:11])
                db.session.add(other)
                db.session.commit()
                kid = f'http://localhost/acme/acct/{other.account_id}'
            r = _jws(client, '/acme/revoke-cert', payload, other_key, kid=kid)
        assert r.status_code == 403
        body = r.get_json()
        assert body['type'] == 'urn:ietf:params:acme:error:unauthorized'
        if by == 'jwk':
            assert 'ML-DSA-44' in body['detail'] and 'account that ordered it' in body['detail'], body
        else:
            assert body['detail'] == 'Not authorized to revoke this certificate', body
        with app.app_context():
            assert not db.session.get(Certificate, cert_id).revoked


FIXTURES = Path(__file__).resolve().parent / 'fixtures' / 'pqc'


def _brainpool_cert():
    from cryptography.hazmat.primitives.asymmetric import ec
    return _self_signed(ec.generate_private_key(ec.BrainpoolP256R1()))


def _self_signed(key):
    from datetime import datetime, timedelta, timezone
    name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, 'bp.pq.example.com')])
    now = datetime.now(timezone.utc)
    return (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=30))
            .sign(key, hashes.SHA256()))


@pytest.fixture
def stored_cert(app, rsa_ca):
    """Stores a certificate (PEM bytes) under the RSA CA, optionally on an ACME order."""
    with app.app_context():
        caref = db.session.get(CA, rsa_ca['id']).refid
    made = []

    def _store(pem, account=None):
        cert = x509.load_pem_x509_certificate(pem)
        with app.app_context():
            row = Certificate(refid=uuid.uuid4().hex[:13], descr='revoke.pq.example.com',
                              caref=caref, serial_number=format(cert.serial_number, 'X'),
                              crt=b64.b64encode(pem).decode())
            db.session.add(row)
            db.session.flush()
            if account is not None:
                db.session.add(AcmeOrder(account_id=account['id'], status='valid',
                                         certificate_id=row.id,
                                         identifiers=json.dumps([{'type': 'dns', 'value': 'x'}])))
            db.session.commit()
            made.append(row.id)
        return cert, row.id
    yield _store
    with app.app_context():
        AcmeOrder.query.filter(AcmeOrder.certificate_id.in_(made)).delete(synchronize_session=False)
        Certificate.query.filter(Certificate.id.in_(made)).delete(synchronize_session=False)
        db.session.commit()


class TestRevokeByAKeyThatCannotSign:
    """A stranger's jwk request for a certificate whose key cannot sign a JWS."""

    @staticmethod
    def _stranger_revokes(client, cert):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        payload = {'certificate': _b64u(cert.public_bytes(serialization.Encoding.DER))}
        return _jws(client, '/acme/revoke-cert', payload, key, jwk=_rsa_jwk(key))

    def test_a_key_this_build_cannot_load_is_refused_not_crashed(self, client, stored_cert,
                                                                 rsa_account):
        cert, _ = stored_cert((FIXTURES / 'slhdsa-sha2-128s-cert.pem').read_bytes(), rsa_account)
        r = self._stranger_revokes(client, cert)
        assert r.status_code == 403, r.get_json()
        assert 'SLH-DSA-SHA2-128s' in r.get_json()['detail']

    def test_outside_acme_the_refusal_names_no_ordering_account(self, client, stored_cert):
        cert, _ = stored_cert((FIXTURES / 'mldsa65-cert.pem').read_bytes())
        r = self._stranger_revokes(client, cert)
        assert r.status_code == 403
        assert r.get_json()['detail'] == 'Not authorized to revoke this certificate'

    def test_a_brainpool_key_is_named_too(self, client, stored_cert, rsa_account):
        cert, _ = stored_cert(_brainpool_cert().public_bytes(serialization.Encoding.PEM),
                              rsa_account)
        r = self._stranger_revokes(client, cert)
        assert r.status_code == 403
        assert r.get_json()['detail'].startswith(
            "This certificate's key (EC-BP256) cannot sign an ACME request"), r.get_json()

    def test_an_unregistered_curve_is_named_by_its_curve(self, client, stored_cert, rsa_account):
        from cryptography.hazmat.primitives.asymmetric import ec
        cert, _ = stored_cert(_self_signed(ec.generate_private_key(ec.SECP256K1()))
                              .public_bytes(serialization.Encoding.PEM), rsa_account)
        r = self._stranger_revokes(client, cert)
        assert r.status_code == 403
        detail = r.get_json()['detail']
        assert 'secp256k1' in detail and 'ECPublicKey' not in detail, detail


# ---------------------------------------------------------------------------
# ACME client
# ---------------------------------------------------------------------------

REGISTRY_JS = Path(__file__).resolve().parents[2] / 'frontend' / 'src' / 'lib' / 'keyAlgorithms.js'


@pytest.fixture(scope='module')
def js_key_lists():
    """KEY_ALGORITHMS and ACME_CLIENT_LABELS as the screens read them, evaluated by node."""
    node = shutil.which('node')
    if node is None:
        pytest.skip('node is not installed')
    out = subprocess.run(
        [node, '--input-type=module', '-e',
         f'import {{ KEY_ALGORITHMS, ACME_CLIENT_LABELS }} from {json.dumps("file://" + str(REGISTRY_JS))};'
         'console.log(JSON.stringify({rows: KEY_ALGORITHMS, acme: ACME_CLIENT_LABELS}))'],
        capture_output=True, text=True, timeout=60, check=True)
    return json.loads(out.stdout)


def _js_mldsa_labels(js):
    labels = [r['label'] for r in js['rows'] if r['family'] == 'ML-DSA' and r['generate']]
    assert labels, 'the frontend registry lists no ML-DSA key'
    return labels


class TestClientKeyTypes:
    def test_the_client_generates_every_mldsa_key_of_the_registry(self, js_key_lists):
        from services.acme.acme_client_service import CERT_KEY_TYPES
        assert set(_js_mldsa_labels(js_key_lists)) <= set(CERT_KEY_TYPES)
        assert set(js_key_lists['acme']) <= set(CERT_KEY_TYPES)
        for label in _js_mldsa_labels(js_key_lists):
            assert key_algorithms.label_for_private_key(CERT_KEY_TYPES[label]()) == label

    def test_an_mldsa_csr_is_signed_without_a_digest(self, js_key_lists):
        from services.acme.acme_client_service import AcmeClientService
        for label in _js_mldsa_labels(js_key_lists):
            key = key_algorithms.generate(label)
            der = b64.urlsafe_b64decode(
                AcmeClientService._build_csr_b64(key, ['pq.example.com'], 'pq.example.com') + '==')
            csr = x509.load_der_x509_csr(der)
            assert csr.is_signature_valid and csr.signature_hash_algorithm is None, label
            assert key_algorithms.label_for_public_key(csr.public_key()) == label

    def test_fips_mode_refuses_them_at_both_doors(self, auth_client, monkeypatch, js_key_lists):
        import fips_mode
        from services.acme.acme_client_service import fips_key_type_refusal
        monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
        for label in _js_mldsa_labels(js_key_lists):
            assert 'FIPS' in fips_key_type_refusal(label)
            r = auth_client.patch('/api/v2/acme/client/settings', content_type='application/json',
                                  data=json.dumps({'key_type': label}))
            assert r.status_code == 400 and 'FIPS' in r.get_json()['message'], label
            r = auth_client.post('/api/v2/acme/client/request', json={
                'domains': ['fips.pq.example.com'], 'email': 'admin@example.com',
                'challenge_type': 'http-01', 'environment': 'staging', 'key_type': label})
            assert r.status_code == 400 and 'FIPS' in r.get_json()['message'], label


@pytest.fixture
def client_key_type(app):
    with app.app_context():
        previous = getattr(SystemConfig.query.filter_by(key='acme.client.key_type').first(), 'value', None)

    def _set(value):
        with app.app_context():
            SystemConfig.query.filter_by(key='acme.client.key_type').delete()
            db.session.add(SystemConfig(key='acme.client.key_type', value=value))
            db.session.commit()
    yield _set
    with app.app_context():
        SystemConfig.query.filter_by(key='acme.client.key_type').delete()
        if previous is not None:
            db.session.add(SystemConfig(key='acme.client.key_type', value=previous))
        db.session.commit()


class TestUnknownConfiguredKeyType:
    """A setting this instance cannot generate is refused, never replaced by RSA-2048."""

    def test_the_default_raises(self, app, client_key_type):
        from services.acme.acme_client_service import AcmeClientService
        client_key_type('ML-DSA-99')
        with app.app_context():
            with pytest.raises(ValueError, match='ML-DSA-99'):
                AcmeClientService._get_default_key_type()

    def test_fips_mode_refuses_a_configured_mldsa_default(self, app, auth_client,
                                                          client_key_type, monkeypatch):
        import fips_mode
        from services.acme.acme_client_service import AcmeClientService
        monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
        monkeypatch.setattr(AcmeClientService, 'for_issuance', classmethod(
            lambda cls, **_k: pytest.fail('an upstream order was started')))
        client_key_type('ML-DSA-44')
        with app.app_context():
            with pytest.raises(ValueError, match='FIPS'):
                AcmeClientService._get_default_key_type()
        r = auth_client.post('/api/v2/acme/client/request', json={
            'domains': ['fips-default.pq.example.com'], 'email': 'admin@example.com',
            'challenge_type': 'http-01', 'environment': 'staging'})
        assert r.status_code == 400 and 'FIPS' in r.get_json()['message']

    def test_finalize_reports_it_instead_of_signing_rsa(self, app, client_key_type):
        from models.acme_models import AcmeClientOrder
        from tests.test_acme_client_key_type import _finalize as client_finalize
        client_key_type('ML-DSA-99')
        with app.app_context():
            order = AcmeClientOrder(
                domains=json.dumps(['legacy.pq.example.com']), challenge_type='http-01',
                environment='staging', status='ready', key_source='generate', key_type=None,
                order_url='https://ca.example/order/pq', finalize_url='https://ca.example/order/pq/finalize')
            (ok, msg, _), csr = client_finalize(order)
        assert not ok and 'ML-DSA-99' in msg
        assert csr is None

    def test_a_request_is_refused_before_any_upstream_order(self, app, auth_client, client_key_type,
                                                            monkeypatch):
        from services.acme.acme_client_service import AcmeClientService
        client_key_type('ML-DSA-99')
        monkeypatch.setattr(AcmeClientService, 'for_issuance', classmethod(
            lambda cls, **_k: pytest.fail('an upstream order was started')))
        r = auth_client.post('/api/v2/acme/client/request', json={
            'domains': ['unknown.pq.example.com'], 'email': 'admin@example.com',
            'challenge_type': 'http-01', 'environment': 'staging'})
        assert r.status_code == 400 and 'ML-DSA-99' in r.get_json()['message']


@pytest.fixture
def key_holder(app):
    """Stores a certificate row holding a private key of the given label, made before FIPS mode."""
    made = []

    def _store(label):
        alg = key_algorithms.get(label)
        key = alg.private_class.generate() if alg.family == 'ML-DSA' else alg.generate()
        pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
        with app.app_context():
            row = Certificate(refid=uuid.uuid4().hex[:13], descr=f'reuse {label}',
                              prv=b64.b64encode(pem).decode())
            db.session.add(row)
            db.session.commit()
            made.append(row.id)
            return row.id
    yield _store
    with app.app_context():
        Certificate.query.filter(Certificate.id.in_(made)).delete(synchronize_session=False)
        db.session.commit()


class TestFipsReusedKey:
    """FIPS mode refuses a reused ML-DSA key as it refuses generating one."""

    @pytest.fixture(autouse=True)
    def _fips(self, monkeypatch):
        import fips_mode
        monkeypatch.setattr(fips_mode, 'enabled', lambda: True)

    @pytest.mark.parametrize('label, refused', [('ML-DSA-65', True), ('RSA-2048', False)])
    def test_the_request_is_refused_before_any_upstream_order(self, auth_client, monkeypatch,
                                                              key_holder, label, refused):
        from services.acme.acme_client_service import AcmeClientService
        started = []

        def for_issuance(cls, **_k):
            started.append(True)
            raise RuntimeError('upstream not reachable in tests')
        monkeypatch.setattr(AcmeClientService, 'for_issuance', classmethod(for_issuance))
        r = auth_client.post('/api/v2/acme/client/request', json={
            'domains': ['reuse.pq.example.com'], 'email': 'admin@example.com',
            'challenge_type': 'http-01', 'environment': 'staging',
            'key_source': 'reuse', 'source_certificate_id': key_holder(label)})
        message = r.get_json().get('message', '')
        if refused:
            assert r.status_code == 400 and 'FIPS' in message, r.get_json()
            assert not started
        else:
            assert started and 'FIPS' not in message, r.get_json()

    def test_finalize_and_renewal_do_not_sign_with_it(self, app, key_holder):
        from models.acme_models import AcmeClientOrder
        from tests.test_acme_client_key_type import _finalize as client_finalize
        src_id = key_holder('ML-DSA-65')
        with app.app_context():
            for field in ('source_certificate_id', 'certificate_id'):
                order = AcmeClientOrder(
                    domains=json.dumps(['reuse.pq.example.com']), challenge_type='http-01',
                    environment='staging', status='ready', key_source='reuse',
                    order_url='https://ca.example/order/r', finalize_url='https://ca.example/order/r/finalize',
                    **{field: src_id})
                (ok, msg, _), csr = client_finalize(order)
                assert not ok and 'FIPS' in msg, (field, msg)
                assert csr is None, field


class _LoopResponse:
    """A Flask test response under the requests.Response names the ACME client reads."""

    def __init__(self, resp):
        self.status_code, self.headers, self.content = resp.status_code, resp.headers, resp.data
        self.text = resp.get_data(as_text=True)

    def json(self):
        return json.loads(self.content)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f'HTTP {self.status_code}')


@pytest.fixture
def acme_loop(app, monkeypatch):
    """The ACME client's HTTP routed to UCM's own ACME server through the test client."""
    from services.acme import outbound
    from utils import ssrf_protection
    web = app.test_client()

    def _path(url):
        assert url.startswith('http://localhost/'), url
        return url[len('http://localhost'):]

    def _post(url, json=None, **_kw):
        return _LoopResponse(web.post(_path(url), data=_dumps(json), content_type='application/jose+json'))

    _dumps = json.dumps
    monkeypatch.setattr(outbound, 'validate_outbound_acme_url', lambda url: None)
    monkeypatch.setattr(ssrf_protection, 'safe_request_get', lambda url, **_kw: _LoopResponse(web.get(_path(url))))
    monkeypatch.setattr(ssrf_protection, 'safe_request_head', lambda url, **_kw: _LoopResponse(web.head(_path(url))))
    monkeypatch.setattr(ssrf_protection, 'safe_request_post', _post)
    return web


@pytest.mark.parametrize('label', ['ML-DSA-44', 'ML-DSA-65'])
def test_client_orders_an_mldsa_certificate_from_ucm_itself(app, acme_loop, signing_ca, mldsa_issuing_ca,
                                                             monkeypatch, label):
    from models.acme_models import AcmeClientOrder
    from services.acme.acme_client_service import AcmeClientService
    signing_ca(mldsa_issuing_ca)
    imported = {}

    def _keep(self, cert_pem, key_pem, domains, source='acme_client'):
        imported.update(cert=cert_pem, key=key_pem)
        return 4242
    monkeypatch.setattr(AcmeClientService, '_import_certificate', _keep)
    domain = f'loop-{label.lower()}.pq.example.com'
    from models.acme_client_account import AcmeClientAccount
    with app.app_context():
        account = AcmeClientAccount(directory_url='http://localhost/acme/directory', label='UCM loop',
                                    email='loop@example.com', account_key_algorithm='RS256',
                                    is_default=False)
        db.session.add(account)
        db.session.commit()
        account_id = account.id
        svc = AcmeClientService(account=account)
        ok, msg, order = svc.create_order([domain], 'loop@example.com', challenge_type='http-01')
        assert ok, msg
        # The challenge is not the point here: the server marks its authorization valid
        server_order = AcmeOrder.query.filter_by(order_id=order.order_url.rstrip('/').rsplit('/', 1)[1]).first()
        for authz in server_order.authorizations:
            authz.status = 'valid'
        server_order.status = 'ready'
        order.key_source, order.key_type = 'generate', label
        db.session.commit()
        ok, msg, cert_id = svc.finalize_order(order)
        assert ok, msg
        assert cert_id == 4242
        leaf = x509.load_pem_x509_certificate(imported['cert'].encode())
        key = serialization.load_pem_private_key(imported['key'].encode(), None)
        assert key_algorithms.label_for_public_key(leaf.public_key()) == label
        assert leaf.public_key() == key.public_key()
        AcmeClientOrder.query.filter_by(acme_client_account_id=account_id).delete()
        AcmeClientAccount.query.filter_by(id=account_id).delete()
        db.session.commit()


def test_an_upstream_refusal_is_reported_as_is(app):
    """Against another CA, its refusal of an ML-DSA request reaches the operator unchanged."""
    from models.acme_models import AcmeClientOrder
    from services.acme.acme_client_service import AcmeClientService
    detail = 'Error finalizing order :: key type ML-DSA-65 is not supported'

    class _Refusal:
        status_code = 400
        headers = {}

        def json(self):
            return {'type': 'urn:ietf:params:acme:error:badPublicKey', 'detail': detail}

    with app.app_context():
        order = AcmeClientOrder(
            domains=json.dumps(['upstream.pq.example.com']), challenge_type='http-01',
            environment='staging', status='ready', key_source='generate', key_type='ML-DSA-65',
            order_url='https://ca.example/order/up', finalize_url='https://ca.example/order/up/finalize')
        svc = object.__new__(AcmeClientService)
        svc.check_order_status = lambda o: ('ready', {})
        svc._post = lambda url, payload: _Refusal()
        ok, msg, _ = AcmeClientService.finalize_order(svc, order)
    assert not ok and msg == f'Finalization failed: {detail}'


class TestFinalizeUnderAComplianceProfile:
    """The BSI profile's allowed_key_types refuse an RSA-2048 or ML-DSA request at finalize."""

    @pytest.fixture
    def bsi_ca(self, app, create_ca):
        ca = create_ca(cn=f'ACME BSI root {uuid.uuid4().hex[:6]}', keyAlgo='EC', keySize='P-256')
        with app.app_context():
            db.session.get(CA, ca['id']).compliance_profile = 'bsi'
            db.session.commit()
        yield ca
        with app.app_context():
            db.session.get(CA, ca['id']).compliance_profile = None
            db.session.commit()

    @staticmethod
    def _finalize_with(app, client, account, key, domain):
        from cryptography.hazmat.primitives.asymmetric import ec
        order_id = _ready_order(app, account, domain)
        digest = hashes.SHA256() if isinstance(key, (rsa.RSAPrivateKey, ec.EllipticCurvePrivateKey)) else None
        csr = (x509.CertificateSigningRequestBuilder()
               .subject_name(x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, domain)]))
               .add_extension(x509.SubjectAlternativeName([x509.DNSName(domain)]), critical=False)
               .sign(key, digest))
        r = _jws(client, f'/acme/order/{order_id}/finalize',
                 {'csr': _b64u(csr.public_bytes(serialization.Encoding.DER))},
                 account['key'], kid=account['kid'])
        with app.app_context():
            order = AcmeOrder.query.filter_by(order_id=order_id).first()
            return r, order.status, order.certificate_id

    @pytest.mark.parametrize('label', ['RSA-2048', 'ML-DSA-44'])
    def test_a_key_type_the_profile_leaves_out_is_a_bad_csr(self, app, client, rsa_account,
                                                            signing_ca, bsi_ca, label):
        from cryptography.hazmat.primitives.asymmetric import mldsa
        signing_ca(bsi_ca)
        key = (rsa.generate_private_key(public_exponent=65537, key_size=2048) if label == 'RSA-2048'
               else mldsa.MLDSA44PrivateKey.generate())
        r, status, cert_id = self._finalize_with(app, client, rsa_account, key,
                                                 f'{label.lower()}.bsi.example.com')
        body = r.get_json()
        assert r.status_code == 400 and body['type'] == 'urn:ietf:params:acme:error:badCSR', body
        assert f'Key type {label} is not allowed by policy' in body['detail'], body
        assert status == 'invalid' and cert_id is None

    def test_a_key_type_the_profile_lists_is_issued(self, app, client, rsa_account, signing_ca, bsi_ca):
        from cryptography.hazmat.primitives.asymmetric import ec
        signing_ca(bsi_ca)
        r, status, cert_id = self._finalize_with(app, client, rsa_account,
                                                 ec.generate_private_key(ec.SECP256R1()),
                                                 'ec-p256.bsi.example.com')
        assert r.status_code == 200 and status == 'valid' and cert_id is not None, r.get_json()
