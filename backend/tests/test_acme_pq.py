"""ACME and ML-DSA: finalize of an OpenSSL ML-DSA-44 request under an RSA and an ML-DSA CA,
revocation of an ML-DSA certificate, ARI on it, and the ACME client's ML-DSA key types."""
import base64 as b64
import json
import re
import shutil
import subprocess
import uuid

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
        """An ML-DSA key cannot sign an ACME request: the refusal names that, not a bare 403."""
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
        assert 'ML-DSA-44' in body['detail'] and 'account that ordered it' in body['detail'], body
        with app.app_context():
            assert not db.session.get(Certificate, cert_id).revoked
