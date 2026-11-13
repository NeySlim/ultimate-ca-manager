"""EdDSA CAs (#436): Ed25519 and Ed448 keys are generated and imported for a CA,
and every path such a CA signs on yields a signature its own key verifies."""
import base64
import json

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed448, ed25519, rsa

from models import CA, Certificate, db
from tests.fixtures.templates import templates_created_here_removed
from tests.windows_profile_support import windows_profiles_restored  # noqa: F401


@pytest.fixture(autouse=True, scope='module')
def _templates_stay_in_this_module(app):
    with templates_created_here_removed(app):
        yield


EDDSA = {'Ed25519': (ed25519.Ed25519PrivateKey, ed25519.Ed25519PublicKey),
         'Ed448': (ed448.Ed448PrivateKey, ed448.Ed448PublicKey)}


def _post(client, url, body):
    return client.post(url, content_type='application/json', data=json.dumps(body))


def _pem(obj):
    return obj.public_bytes(serialization.Encoding.PEM)


def _row_cert(row):
    return x509.load_pem_x509_certificate(base64.b64decode(row.crt))


def _ca_cert(app, ca_id):
    with app.app_context():
        return _row_cert(db.session.get(CA, ca_id))


def _cert_cert(app, cert_id):
    with app.app_context():
        return _row_cert(db.session.get(Certificate, cert_id))


def _new_ca(auth_client, cn, parent=None, **fields):
    body = {'type': 'intermediate' if parent else 'root', 'commonName': cn,
            'organization': 'EdDSA Test', 'country': 'FR', 'validityYears': 3, **fields}
    if parent:
        body['parentCAId'] = parent
    return _post(auth_client, '/api/v2/cas', body)


def _ca(auth_client, cn, parent=None, **fields):
    r = _new_ca(auth_client, cn, parent, **fields)
    assert r.status_code == 201, r.get_json()
    return r.get_json()['data']


@pytest.fixture(scope='module')
def ed_root(auth_client):
    return _ca(auth_client, 'Ed25519 module root', keyAlgo='EdDSA', keySize='Ed25519')


@pytest.fixture(scope='module')
def rsa_root(auth_client):
    return _ca(auth_client, 'RSA root over Ed25519', keyAlgo='RSA', keySize=2048)


# ---- creation ---------------------------------------------------------------------

@pytest.mark.parametrize('fields, name', [
    ({'keyAlgo': 'EdDSA', 'keySize': 'Ed25519'}, 'Ed25519'),
    ({'keyAlgo': 'EdDSA', 'keySize': 'Ed448'}, 'Ed448'),
    ({'keyAlgo': 'EdDSA'}, 'Ed25519'),
    ({'keyAlgo': 'Ed25519'}, 'Ed25519'),
    ({'keyAlgo': 'ED448'}, 'Ed448'),
    ({'keyType': 'ed25519'}, 'Ed25519'),
])
def test_a_root_gets_the_eddsa_key_it_asks_for(app, auth_client, fields, name):
    ca = _ca(auth_client, f'EdDSA root {" ".join(map(str, fields.values()))}', **fields)
    cert = _ca_cert(app, ca['id'])
    assert isinstance(cert.public_key(), EDDSA[name][1])
    assert cert.signature_hash_algorithm is None
    cert.verify_directly_issued_by(cert)
    with app.app_context():
        from services.hsm.ca_key_loader import get_ca_signing_key
        assert isinstance(get_ca_signing_key(db.session.get(CA, ca['id'])), EDDSA[name][0])
    ku = cert.extensions.get_extension_for_class(x509.KeyUsage).value
    assert ku.key_cert_sign and ku.crl_sign


@pytest.mark.parametrize('fields', [
    {'keyAlgo': 'EdDSA', 'keySize': 'Ed999'},
    {'keyAlgo': 'EdDSA', 'keySize': 2048},
    {'keyAlgo': 'Ed25519', 'keySize': 'Ed448'},
])
def test_an_eddsa_request_naming_no_such_key_is_refused(auth_client, fields):
    r = _new_ca(auth_client, 'EdDSA refused', **fields)
    assert r.status_code == 400, r.get_json()


def test_a_digest_asked_of_an_eddsa_root_is_ignored_with_a_notice(app, auth_client):
    r = _new_ca(auth_client, 'Ed25519 root sha384', keyAlgo='EdDSA', keySize='Ed25519',
                hashAlgorithm='sha384')
    assert r.status_code == 201, r.get_json()
    assert _ca_cert(app, r.get_json()['data']['id']).signature_hash_algorithm is None
    assert 'sha384' in json.dumps(r.get_json().get('meta'))


@pytest.mark.parametrize('parent_fields, child_fields, child_key, child_hash', [
    ({'keyAlgo': 'EdDSA', 'keySize': 'Ed25519'}, {'keyAlgo': 'RSA', 'keySize': 2048}, rsa.RSAPublicKey, None),
    ({'keyAlgo': 'RSA', 'keySize': 2048}, {'keyAlgo': 'EdDSA', 'keySize': 'Ed25519'},
     ed25519.Ed25519PublicKey, 'sha256'),
    ({'keyAlgo': 'ECDSA', 'keySize': 'secp384r1'}, {'keyAlgo': 'EdDSA', 'keySize': 'Ed448'},
     ed448.Ed448PublicKey, 'sha384'),
    ({'keyAlgo': 'EdDSA', 'keySize': 'Ed448'}, {'keyAlgo': 'EdDSA', 'keySize': 'Ed25519'},
     ed25519.Ed25519PublicKey, None),
])
def test_intermediates_across_eddsa_and_other_families(app, auth_client, parent_fields, child_fields,
                                                       child_key, child_hash):
    parent = _ca(auth_client, f'Parent {parent_fields["keySize"]}', **parent_fields)
    child = _ca(auth_client, f'Child {child_fields["keySize"]} of {parent_fields["keySize"]}',
                parent=parent['id'], **child_fields)
    parent_cert, child_cert = _ca_cert(app, parent['id']), _ca_cert(app, child['id'])
    assert isinstance(child_cert.public_key(), child_key)
    hash_alg = child_cert.signature_hash_algorithm
    assert (hash_alg.name if hash_alg else None) == child_hash
    child_cert.verify_directly_issued_by(parent_cert)


@pytest.mark.parametrize('name', ['Ed25519', 'Ed448'])
def test_the_ca_view_names_the_eddsa_key(auth_client, name):
    bits = {'Ed25519': 256, 'Ed448': 448}[name]
    ca = _ca(auth_client, f'{name} view root', keyAlgo=name)
    data = auth_client.get(f"/api/v2/cas/{ca['id']}").get_json()['data']
    assert (data['key_type'], data['key_size']) == (name, bits)
    assert (data['keyAlgo'], data['keySize']) == (name, bits)
    assert data['signature_algorithm'] == data['hash_algorithm'] == name
    assert data.get('crl_digest') is None
    listed = next(c for c in auth_client.get('/api/v2/cas?per_page=500').get_json()['data'] if c['id'] == ca['id'])
    assert (listed['key_type'], listed['key_size'], listed['signature_algorithm']) == (name, bits, name)


# ---- certificates -----------------------------------------------------------------

def _csr(key, cn, dns=()):
    builder = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, cn)]))
    if dns:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.DNSName(d) for d in dns]), critical=False)
    digestless = isinstance(key, (ed25519.Ed25519PrivateKey, ed448.Ed448PrivateKey))
    return builder.sign(key, None if digestless else hashes.SHA256())


def _issue(auth_client, ca_id, cn, **body):
    r = _post(auth_client, '/api/v2/certificates', {'cn': cn, 'ca_id': ca_id, 'validity_days': 30, **body})
    assert r.status_code == 201, r.get_json()
    return r.get_json()['data']['id']


@pytest.mark.parametrize('key_fields, key_class', [
    ({'key_type': 'rsa', 'key_size': '2048'}, rsa.RSAPublicKey),
    ({'key_type': 'ecdsa', 'key_size': '384'}, ec.EllipticCurvePublicKey),
    ({'key_type': 'ML-DSA-65'}, None),
])
def test_api_issuance_under_an_eddsa_ca(app, auth_client, ed_root, key_fields, key_class):
    from utils import key_algorithms
    if key_class is None and not key_algorithms.mldsa_supported():
        pytest.skip('this build has no ML-DSA')
    cert_id = _issue(auth_client, ed_root['id'], f'api-{key_fields["key_type"]}.ed.example.test', **key_fields)
    leaf = _cert_cert(app, cert_id)
    if key_class:
        assert isinstance(leaf.public_key(), key_class)
    assert leaf.signature_hash_algorithm is None
    leaf.verify_directly_issued_by(_ca_cert(app, ed_root['id']))
    with app.app_context():
        assert db.session.get(Certificate, cert_id).key_algo is not None


def test_an_issuance_digest_is_ignored_under_an_eddsa_ca(app, auth_client, ed_root):
    cert_id = _issue(auth_client, ed_root['id'], 'digest.ed.example.test', digest='sha512')
    leaf = _cert_cert(app, cert_id)
    assert leaf.signature_hash_algorithm is None
    leaf.verify_directly_issued_by(_ca_cert(app, ed_root['id']))


def _store_csr(app, csr, descr):
    import uuid
    with app.app_context():
        row = Certificate(refid=str(uuid.uuid4()), descr=descr, source='manual',
                          csr=base64.b64encode(_pem(csr)).decode())
        db.session.add(row)
        db.session.commit()
        return row.id


@pytest.mark.parametrize('make_key', [lambda: rsa.generate_private_key(65537, 2048),
                                      ed25519.Ed25519PrivateKey.generate], ids=['rsa', 'ed25519'])
def test_a_csr_is_signed_by_an_eddsa_ca(app, auth_client, ed_root, make_key):
    key = make_key()
    csr_id = _store_csr(app, _csr(key, 'csr.ed.example.test'), 'ed csr')
    r = _post(auth_client, f'/api/v2/csrs/{csr_id}/sign', {'ca_id': ed_root['id'], 'validity_days': 30})
    assert r.status_code in (200, 201), r.get_json()
    shown = auth_client.get(f'/api/v2/certificates/{csr_id}').get_json()['data']
    assert shown['signature_algorithm'] == 'Ed25519'
    if isinstance(key, ed25519.Ed25519PrivateKey):
        assert (shown['key_type'], shown['key_size']) == ('Ed25519', 256)
    leaf = _cert_cert(app, csr_id)
    assert leaf.public_key().public_bytes(serialization.Encoding.DER,
                                          serialization.PublicFormat.SubjectPublicKeyInfo) == \
        key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    leaf.verify_directly_issued_by(_ca_cert(app, ed_root['id']))


def test_template_issuance_under_an_eddsa_ca(app, auth_client, ed_root):
    r = _post(auth_client, '/api/v2/templates', {
        'name': 'ed-ca-template', 'template_type': 'custom', 'key_type': 'EC-P256',
        'validity_days': 90, 'extensions_template': {'key_usage': ['digitalSignature']}})
    assert r.status_code in (200, 201), r.get_json()
    cert_id = _issue(auth_client, ed_root['id'], 'tpl.ed.example.test', template_id=r.get_json()['data']['id'])
    leaf = _cert_cert(app, cert_id)
    assert isinstance(leaf.public_key(), ec.EllipticCurvePublicKey)
    leaf.verify_directly_issued_by(_ca_cert(app, ed_root['id']))


def test_a_leaf_renewal_is_signed_by_the_eddsa_ca(app, auth_client, ed_root):
    cert_id = _issue(auth_client, ed_root['id'], 'renew.ed.example.test', key_type='rsa', key_size='2048')
    old = _cert_cert(app, cert_id)
    r = _post(auth_client, f'/api/v2/certificates/{cert_id}/renew', {})
    assert r.status_code in (200, 201), r.get_json()
    new_id = (r.get_json().get('data') or {}).get('id', cert_id)
    new = _cert_cert(app, new_id)
    assert new.serial_number != old.serial_number
    assert new.signature_hash_algorithm is None
    new.verify_directly_issued_by(_ca_cert(app, ed_root['id']))


# ---- ACME server ------------------------------------------------------------------

def _b64u(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()


def _jws(client, path, payload, key, kid):
    from cryptography.hazmat.primitives.asymmetric import padding
    nonce = client.get('/acme/new-nonce').headers.get('Replay-Nonce')
    p64 = _b64u(json.dumps({'alg': 'RS256', 'nonce': nonce, 'url': f'http://localhost{path}',
                            'kid': kid}).encode())
    b64p = _b64u(json.dumps(payload).encode())
    sig = key.sign(f'{p64}.{b64p}'.encode(), padding.PKCS1v15(), hashes.SHA256())
    return client.post(path, data=json.dumps({'protected': p64, 'payload': b64p, 'signature': _b64u(sig)}),
                       content_type='application/jose+json')


def test_acme_finalize_under_an_eddsa_ca(app, client, ed_root, monkeypatch):
    import uuid
    from models.acme_models import AcmeAccount, AcmeOrder
    from services.acme.acme_service import AcmeService
    from utils import caa_checker
    monkeypatch.setattr(caa_checker, 'check_caa_for_domains', lambda *a, **k: (True, 'allowed'))
    with app.app_context():
        refid = db.session.get(CA, ed_root['id']).refid
    monkeypatch.setattr(AcmeService, '_resolve_ca_for_domains', lambda self, _d: refid)
    key = rsa.generate_private_key(65537, 2048)
    pub = key.public_key().public_numbers()
    jwk = {'kty': 'RSA', 'n': _b64u(pub.n.to_bytes((pub.n.bit_length() + 7) // 8, 'big')),
           'e': _b64u(pub.e.to_bytes(3, 'big'))}
    domain = 'acme.ed.example.com'
    with app.app_context():
        acct = AcmeAccount(jwk=json.dumps(jwk), status='valid', jwk_thumbprint=uuid.uuid4().hex * 2)
        db.session.add(acct)
        db.session.commit()
        order = AcmeOrder(account_id=acct.account_id, status='ready',
                          identifiers=json.dumps([{'type': 'dns', 'value': domain}]))
        db.session.add(order)
        db.session.commit()
        kid, order_id = f'http://localhost/acme/acct/{acct.account_id}', order.order_id
    csr = _csr(ec.generate_private_key(ec.SECP256R1()), domain, [domain])
    r = _jws(client, f'/acme/order/{order_id}/finalize',
             {'csr': _b64u(csr.public_bytes(serialization.Encoding.DER))}, key, kid)
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['status'] == 'valid'
    with app.app_context():
        row = db.session.get(Certificate, AcmeOrder.query.filter_by(order_id=order_id).first().certificate_id)
        leaf = _row_cert(row)
    assert leaf.signature_hash_algorithm is None
    leaf.verify_directly_issued_by(_ca_cert(app, ed_root['id']))


# ---- SCEP: its clients encrypt to the CA's RSA key ------------------------------------

def _set_config(key, value):
    from models import SystemConfig
    row = SystemConfig.query.filter_by(key=key).first()
    if value is None:
        if row:
            db.session.delete(row)
    elif row is None:
        db.session.add(SystemConfig(key=key, value=value))
    else:
        row.value = value
    db.session.commit()


@pytest.fixture
def scep_on_ed_root(app, ed_root):
    from models import SystemConfig
    keys = ('scep_enabled', 'scep_ca_id')
    with app.app_context():
        saved = {k: getattr(SystemConfig.query.filter_by(key=k).first(), 'value', None) for k in keys}
        _set_config('scep_enabled', 'true')
    yield ed_root['id']
    with app.app_context():
        for k, v in saved.items():
            _set_config(k, v)


@pytest.mark.parametrize('operation', ['GetCACaps', 'GetCACert'])
def test_scep_names_the_eddsa_ca_it_cannot_serve(app, client, scep_on_ed_root, operation):
    with app.app_context():
        _set_config('scep_ca_id', str(scep_on_ed_root))
    r = client.get(f'/scep/pkiclient.exe?operation={operation}')
    body = r.get_data(as_text=True)
    assert r.status_code == 503, body
    assert 'Ed25519' in body and 'RSA' in body


def test_scep_settings_refuse_an_eddsa_ca(app, auth_client, scep_on_ed_root):
    with app.app_context():
        _set_config('scep_ca_id', None)
    r = auth_client.patch('/api/v2/scep/config', data=json.dumps({'ca_id': scep_on_ed_root}),
                          content_type='application/json')
    assert r.status_code == 400
    assert 'Ed25519' in r.get_data(as_text=True)


# ---- CRL --------------------------------------------------------------------------

def test_full_and_delta_crls_of_an_eddsa_ca(app, auth_client, ed_root):
    from models.crl import CRLMetadata
    from services.crl import CRLService
    cert_id = _issue(auth_client, ed_root['id'], 'revoked.ed.example.test')
    r = _post(auth_client, f'/api/v2/certificates/{cert_id}/revoke', {'reason': 'keyCompromise'})
    assert r.status_code == 200, r.get_json()
    r = auth_client.post(f"/api/v2/crl/{ed_root['id']}/regenerate")
    assert r.status_code == 200, r.get_json()
    ca_pub = _ca_cert(app, ed_root['id']).public_key()
    serial = _cert_cert(app, cert_id).serial_number
    with app.app_context():
        row = CRLMetadata.query.filter_by(ca_id=ed_root['id'], is_delta=False).order_by(
            CRLMetadata.crl_number.desc()).first()
        crl = x509.load_pem_x509_crl(row.crl_pem.encode())
        ca = db.session.get(CA, ed_root['id'])
        ca.delta_crl_enabled = True
        db.session.commit()
        try:
            delta = x509.load_pem_x509_crl(CRLService.generate_delta_crl(ed_root['id']).crl_pem.encode())
        finally:
            db.session.get(CA, ed_root['id']).delta_crl_enabled = False
            db.session.commit()
    for signed in (crl, delta):
        assert signed.signature_hash_algorithm is None
        assert signed.is_signature_valid(ca_pub)
    assert crl.get_revoked_certificate_by_serial_number(serial) is not None


def test_crl_config_refuses_to_impose_a_digest_on_an_eddsa_ca(auth_client, ed_root):
    r = _post(auth_client, f"/api/v2/crl/{ed_root['id']}/config", {'digest': 'sha384'})
    assert r.status_code == 400
    assert 'Ed25519' in r.get_json()['message']


# ---- OCSP -------------------------------------------------------------------------

def _ocsp(app, client, ca_id, leaf_id):
    from cryptography.x509 import ocsp
    with app.app_context():
        db.session.get(CA, ca_id).ocsp_enabled = True
        db.session.commit()
    issuer, leaf = _ca_cert(app, ca_id), _cert_cert(app, leaf_id)
    req = ocsp.OCSPRequestBuilder().add_certificate(leaf, issuer, hashes.SHA1()).build()
    r = client.post('/ocsp', data=req.public_bytes(serialization.Encoding.DER),
                    content_type='application/ocsp-request')
    assert r.status_code == 200
    resp = ocsp.load_der_ocsp_response(r.data)
    assert resp.response_status == ocsp.OCSPResponseStatus.SUCCESSFUL
    return resp


def _verify_ocsp(resp, signer_pub):
    if isinstance(signer_pub, rsa.RSAPublicKey):
        from cryptography.hazmat.primitives.asymmetric import padding
        signer_pub.verify(resp.signature, resp.tbs_response_bytes, padding.PKCS1v15(),
                          resp.signature_hash_algorithm)
    else:
        signer_pub.verify(resp.signature, resp.tbs_response_bytes)


def test_the_eddsa_ca_signs_its_own_ocsp_answers(app, client, auth_client, ed_root):
    from cryptography.x509 import ocsp
    cert_id = _issue(auth_client, ed_root['id'], 'ocsp.ed.example.test')
    resp = _ocsp(app, client, ed_root['id'], cert_id)
    assert resp.certificate_status == ocsp.OCSPCertStatus.GOOD
    assert resp.signature_hash_algorithm is None
    _verify_ocsp(resp, _ca_cert(app, ed_root['id']).public_key())


def test_a_delegated_rsa_responder_answers_for_the_eddsa_ca(app, client, auth_client, ed_root):
    from models import SystemConfig
    responder_id = _issue(auth_client, ed_root['id'], 'responder.ed.example.test', key_type='rsa',
                          key_size='2048', cert_type='custom', extra_ekus=['OCSPSigning'])
    r = _post(auth_client, f"/api/v2/cas/{ed_root['id']}/ocsp-responder", {'certificate_id': responder_id})
    assert r.status_code == 200, r.get_json()
    try:
        leaf_id = _issue(auth_client, ed_root['id'], 'delegated.ed.example.test')
        resp = _ocsp(app, client, ed_root['id'], leaf_id)
        responder = _cert_cert(app, responder_id)
        responder.verify_directly_issued_by(_ca_cert(app, ed_root['id']))
        _verify_ocsp(resp, responder.public_key())
    finally:
        with app.app_context():
            SystemConfig.query.filter_by(key=f"ocsp_responder_cert_{ed_root['id']}").delete()
            db.session.commit()


def test_an_ed448_ca_answers_two_cert_ids_and_openssl_verifies(app, client, auth_client, tmp_path):
    """Two CertIDs take the hand-built response; OpenSSL checks nonce, signature and statuses."""
    import shutil
    import subprocess
    ca = _ca(auth_client, 'Ed448 OCSP root', keyAlgo='Ed448')
    with app.app_context():
        db.session.get(CA, ca['id']).ocsp_enabled = True
        db.session.commit()
    good = _issue(auth_client, ca['id'], 'good.ed448.example.test')
    revoked = _issue(auth_client, ca['id'], 'revoked.ed448.example.test')
    assert _post(auth_client, f'/api/v2/certificates/{revoked}/revoke', {'reason': 'superseded'}).status_code == 200
    for name, data in {'ca.pem': _pem(_ca_cert(app, ca['id'])), 'good.pem': _pem(_cert_cert(app, good)),
                       'revoked.pem': _pem(_cert_cert(app, revoked))}.items():
        (tmp_path / name).write_bytes(data)
    openssl = shutil.which('openssl')
    certs = ['-issuer', 'ca.pem', '-cert', 'good.pem', '-cert', 'revoked.pem']
    out = subprocess.run([openssl, 'ocsp', *certs, '-reqout', 'q.der'], capture_output=True, text=True, cwd=tmp_path)
    assert out.returncode == 0, out.stderr
    r = client.post('/ocsp', data=(tmp_path / 'q.der').read_bytes(), content_type='application/ocsp-request')
    assert r.status_code == 200
    (tmp_path / 'r.der').write_bytes(r.data)
    out = subprocess.run([openssl, 'ocsp', '-respin', 'r.der', '-reqin', 'q.der', '-VAfile', 'ca.pem'],
                         capture_output=True, text=True, cwd=tmp_path)
    assert out.returncode == 0 and 'Response verify OK' in out.stdout + out.stderr, out.stdout + out.stderr
    out = subprocess.run([openssl, 'ocsp', '-respin', 'r.der', *certs, '-VAfile', 'ca.pem', '-no_nonce'],
                         capture_output=True, text=True, cwd=tmp_path)
    assert 'good.pem: good' in out.stdout and 'revoked.pem: revoked' in out.stdout, out.stdout


def test_a_delegated_responder_renewal_is_signed_by_the_eddsa_ca(app, auth_client, ed_root):
    from services.ocsp_responder_renewal import _renew_responder_cert
    cert_id = _issue(auth_client, ed_root['id'], 'renewed-responder.ed.example.test', key_type='ecdsa',
                     key_size='256', cert_type='custom', extra_ekus=['OCSPSigning'])
    with app.app_context():
        ca = db.session.get(CA, ed_root['id'])
        new = _renew_responder_cert(ca, db.session.get(Certificate, cert_id))
        db.session.commit()
        renewed, ca_cert = _row_cert(new), _row_cert(ca)
    assert renewed.signature_hash_algorithm is None
    renewed.verify_directly_issued_by(ca_cert)


def test_an_rsa_ca_with_an_ed25519_responder(app, client, auth_client, rsa_root):
    """An EdDSA responder key arrives by CSR: UCM generates none for a leaf."""
    from models import SystemConfig
    key = ed25519.Ed25519PrivateKey.generate()
    csr_id = _store_csr(app, _csr(key, 'ed-responder.example.test'), 'ed responder')
    r = _post(auth_client, f'/api/v2/csrs/{csr_id}/sign', {
        'ca_id': rsa_root['id'], 'validity_days': 30, 'cert_type': 'custom', 'extra_ekus': ['OCSPSigning']})
    assert r.status_code in (200, 201), r.get_json()
    with app.app_context():
        from security.encryption import encrypt_private_key
        from utils.key_codec import private_key_to_pem
        row = db.session.get(Certificate, csr_id)
        row.prv = encrypt_private_key(base64.b64encode(private_key_to_pem(key)).decode())
        db.session.commit()
    r = _post(auth_client, f"/api/v2/cas/{rsa_root['id']}/ocsp-responder", {'certificate_id': csr_id})
    assert r.status_code == 200, r.get_json()
    try:
        leaf_id = _issue(auth_client, rsa_root['id'], 'by-ed-responder.example.test')
        resp = _ocsp(app, client, rsa_root['id'], leaf_id)
        _verify_ocsp(resp, key.public_key())
    finally:
        with app.app_context():
            SystemConfig.query.filter_by(key=f"ocsp_responder_cert_{rsa_root['id']}").delete()
            db.session.commit()


# ---- TSA: an EdDSA CA issues the signer, it does not sign timestamps itself -----------

def _tsq(data):
    import hashlib
    from asn1crypto import tsp
    return tsp.TimeStampReq({
        'version': 1, 'cert_req': True,
        'message_imprint': {'hash_algorithm': {'algorithm': 'sha256'},
                            'hashed_message': hashlib.sha256(data).digest()},
    }).dump()


@pytest.fixture
def tsa_settings(app):
    from models import SystemConfig
    keys = ('tsa_enabled', 'tsa_signer_cert_refid', 'tsa_ca_refid')
    with app.app_context():
        saved = {k: getattr(SystemConfig.query.filter_by(key=k).first(), 'value', None) for k in keys}
    yield
    with app.app_context():
        for k, v in saved.items():
            _set_config(k, v)


def test_an_rsa_tsa_signer_issued_by_an_eddsa_ca_signs(app, client, auth_client, ed_root, tsa_settings, tmp_path):
    import hashlib
    import shutil
    import subprocess
    from asn1crypto import tsp
    r = _post(auth_client, '/api/v2/tsa/signer-certificate', {
        'ca_id': ed_root['id'], 'cn': 'ed-tsa-signer', 'key_type': 'rsa', 'key_size': '2048', 'select': True})
    assert r.status_code == 200, r.get_json()
    signer = x509.load_pem_x509_certificate(r.get_json()['data']['certificate']['pem'].encode())
    assert signer.signature_hash_algorithm is None
    signer.verify_directly_issued_by(_ca_cert(app, ed_root['id']))
    with app.app_context():
        _set_config('tsa_enabled', 'true')
    data = b'stamped under an Ed25519 root'
    resp = client.post('/tsa', data=_tsq(data), content_type='application/timestamp-query')
    assert resp.status_code == 200
    token = tsp.TimeStampResp.load(resp.data)['time_stamp_token']
    assert token is not None
    (tmp_path / 'token.der').write_bytes(token.dump())
    (tmp_path / 'ca.pem').write_bytes(_pem(_ca_cert(app, ed_root['id'])))
    out = subprocess.run([shutil.which('openssl'), 'cms', '-verify', '-inform', 'DER', '-in', 'token.der',
                          '-CAfile', 'ca.pem', '-purpose', 'any', '-out', 'tst.der'],
                         capture_output=True, text=True, cwd=tmp_path)
    assert out.returncode == 0, out.stderr
    info = tsp.TSTInfo.load((tmp_path / 'tst.der').read_bytes())
    assert info['message_imprint']['hashed_message'].native == hashlib.sha256(data).digest()


def test_an_eddsa_ca_is_refused_as_the_tsa_signer(auth_client, ed_root, tsa_settings):
    r = auth_client.patch('/api/v2/tsa/config', content_type='application/json',
                          data=json.dumps({'ca_refid': ed_root['refid']}))
    assert r.status_code == 400, r.get_json()
    assert 'EdDSA' in r.get_json()['message']


# ---- cross-signing ----------------------------------------------------------------

@pytest.mark.parametrize('issuer, subject', [('ed', 'rsa'), ('rsa', 'ed')])
def test_cross_signing_between_eddsa_and_rsa(app, auth_client, issuer, subject):
    cas = {'ed': _ca(auth_client, f'Ed25519 cross {issuer}{subject}', keyAlgo='Ed25519'),
           'rsa': _ca(auth_client, f'RSA cross {issuer}{subject}', keyAlgo='RSA-2048')}
    r = auth_client.post(f"/api/v2/cas/{cas[issuer]['id']}/cross-sign",
                         json={'subject_ca_id': cas[subject]['id']})
    assert r.status_code == 201, r.get_json()
    cross = x509.load_pem_x509_certificate(r.get_json()['data']['certificate'].encode())
    own = _ca_cert(app, cas[subject]['id'])
    assert cross.public_key().public_bytes(serialization.Encoding.DER,
                                           serialization.PublicFormat.SubjectPublicKeyInfo) == \
        own.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    assert (cross.signature_hash_algorithm is None) == (issuer == 'ed')
    cross.verify_directly_issued_by(_ca_cert(app, cas[issuer]['id']))


# ---- external-CSR CA and same-key renewal --------------------------------------------

def test_an_external_eddsa_ca_is_installed_then_renewed_on_its_key(app, auth_client, rsa_root):
    from services.hsm.ca_key_loader import get_ca_signing_key
    from services.trust_store import TrustStoreService
    r = _post(auth_client, '/api/v2/cas', {'type': 'external', 'commonName': 'Ed25519 external CA',
                                           'keyAlgo': 'EdDSA', 'keySize': 'Ed25519'})
    assert r.status_code == 201, r.get_json()
    ca_id = r.get_json()['data']['id']
    first = x509.load_pem_x509_csr(auth_client.get(f'/api/v2/cas/{ca_id}/csr').data)
    assert isinstance(first.public_key(), ed25519.Ed25519PublicKey) and first.is_signature_valid
    with app.app_context():
        root_row = db.session.get(CA, rsa_root['id'])
        signed = TrustStoreService.sign_csr(_pem(first), _row_cert(root_row), get_ca_signing_key(root_row),
                                            validity_days=365, cert_type='intermediate_ca')
    r = _post(auth_client, f'/api/v2/cas/{ca_id}/certificate', {'pem_content': signed.decode()})
    assert r.status_code == 200, r.get_json()
    r = _post(auth_client, f'/api/v2/cas/{ca_id}/renew-csr', {'digest': 'sha256'})
    assert r.status_code == 200, r.get_json()
    renewed = x509.load_pem_x509_csr(auth_client.get(f'/api/v2/cas/{ca_id}/csr').data)
    assert renewed.is_signature_valid and renewed.signature_hash_algorithm is None
    assert renewed.public_key() == first.public_key()
    # The installed intermediate signs leaves of its own
    leaf = _cert_cert(app, _issue(auth_client, ca_id, 'leaf.ed-external.example.test'))
    leaf.verify_directly_issued_by(_ca_cert(app, ca_id))


# ---- export -----------------------------------------------------------------------

def test_pkcs12_export_of_an_eddsa_ca_holds_its_key(app, auth_client, rsa_root):
    from cryptography.hazmat.primitives.serialization import pkcs12
    child = _ca(auth_client, 'Ed25519 export intermediate', parent=rsa_root['id'], keyAlgo='Ed25519')
    r = _post(auth_client, f"/api/v2/cas/{child['id']}/export", {
        'format': 'pkcs12', 'include_key': True, 'include_chain': True, 'password': 'Export-Pass-436'})
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    key, cert, extra = pkcs12.load_key_and_certificates(r.data, b'Export-Pass-436')
    assert isinstance(key, ed25519.Ed25519PrivateKey)
    assert key.public_key() == cert.public_key() == _ca_cert(app, child['id']).public_key()
    assert [c.subject for c in extra] == [_ca_cert(app, rsa_root['id']).subject]
    r = _post(auth_client, f"/api/v2/cas/{child['id']}/export", {'format': 'key', 'password': 'Export-Pass-436'})
    assert r.status_code == 200
    key = serialization.load_pem_private_key(r.data, b'Export-Pass-436')
    assert isinstance(key, ed25519.Ed25519PrivateKey)
    r = auth_client.get(f"/api/v2/cas/{child['id']}/export?format=pem&include_chain=true")
    chain = x509.load_pem_x509_certificates(r.data)
    chain[0].verify_directly_issued_by(chain[1])


# ---- backup and restore -----------------------------------------------------------

def _crl_verifies(row):
    from services.hsm.ca_key_loader import get_ca_signing_key
    from services.trust_store import TrustStoreService
    key = get_ca_signing_key(row)
    crl = x509.load_pem_x509_crl(TrustStoreService.generate_crl(_row_cert(row), key, []))
    return key, crl.is_signature_valid(_row_cert(row).public_key())


def test_an_eddsa_ca_key_is_stored_under_the_master_key(app, auth_client, encryption_enabled):
    created = _ca(auth_client, 'Ed448 master key root', keyAlgo='Ed448')
    with app.app_context():
        row = db.session.get(CA, created['id'])
        try:
            assert encryption_enabled.key_encryption.is_encrypted(row.prv)
            key, valid = _crl_verifies(row)
            assert isinstance(key, ed448.Ed448PrivateKey) and valid
        finally:
            db.session.delete(row)
            db.session.commit()


def test_an_eddsa_ca_key_survives_a_backup_and_restore(app, auth_client):
    from services.backup import manifest
    from services.backup_service import BackupService
    created = _ca(auth_client, 'Ed448 backup root', keyAlgo='Ed448')
    password = 'Correct-Horse-Battery-436'
    with app.app_context():
        refid = db.session.get(CA, created['id']).refid
        svc = BackupService()
        blob = svc.create_backup(password, include={n: n == 'certificate_authorities' for n in manifest.SECTIONS})
        CA.query.filter_by(refid=refid).delete()
        db.session.commit()
        try:
            svc.restore_backup(blob, password)
            back = CA.query.filter_by(refid=refid).first()
            assert back is not None and back.prv
            key, valid = _crl_verifies(back)
            assert isinstance(key, ed448.Ed448PrivateKey) and valid
        finally:
            CA.query.filter_by(refid=refid).delete()
            db.session.commit()


# ---- import: certificate first, key afterwards (#436) --------------------------------

def _self_signed_ca(key, cn):
    import datetime
    name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, cn)])
    now = datetime.datetime.now(datetime.timezone.utc)
    return (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=365))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=False, content_commitment=False,
                                         key_encipherment=False, data_encipherment=False, key_agreement=False,
                                         key_cert_sign=True, crl_sign=True, encipher_only=False,
                                         decipher_only=False), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .sign(key, None))


def _key_pem(key):
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())


def _import_cert_only(auth_client, cert, name):
    r = auth_client.post('/api/v2/cas/import', data={'pem_content': _pem(cert).decode(), 'name': name})
    assert r.status_code in (200, 201), r.get_json()
    data = r.get_json()['data']
    assert not data.get('has_private_key')
    return data['id']


@pytest.mark.parametrize('name', ['Ed25519', 'Ed448'])
def test_a_key_imported_after_its_certificate_lets_the_ca_sign(app, auth_client, name):
    key = EDDSA[name][0].generate()
    cert = _self_signed_ca(key, f'{name} imported in two steps')
    ca_id = _import_cert_only(auth_client, cert, f'{name} two steps')
    r = _post(auth_client, f'/api/v2/cas/{ca_id}/key', {'key': _key_pem(key).decode()})
    assert r.status_code == 200, r.get_json()
    leaf = _cert_cert(app, _issue(auth_client, ca_id, f'two-steps-{name.lower()}.example.test'))
    leaf.verify_directly_issued_by(cert)


def test_a_reimport_with_the_key_completes_a_certificate_only_ca(app, auth_client):
    key = ed25519.Ed25519PrivateKey.generate()
    cert = _self_signed_ca(key, 'Ed25519 reimported with key')
    ca_id = _import_cert_only(auth_client, cert, 'Ed25519 reimport')
    r = auth_client.post('/api/v2/cas/import', data={
        'pem_content': (_pem(cert) + _key_pem(key)).decode(), 'name': 'Ed25519 reimport'})
    assert r.status_code in (200, 201), r.get_json()
    with app.app_context():
        assert db.session.get(CA, ca_id).has_private_key
    leaf = _cert_cert(app, _issue(auth_client, ca_id, 'reimport.ed.example.test'))
    leaf.verify_directly_issued_by(cert)


def test_a_key_of_another_eddsa_ca_is_still_refused(auth_client):
    cert = _self_signed_ca(ed25519.Ed25519PrivateKey.generate(), 'Ed25519 wrong key')
    ca_id = _import_cert_only(auth_client, cert, 'Ed25519 wrong key')
    r = _post(auth_client, f'/api/v2/cas/{ca_id}/key',
              {'key': _key_pem(ed25519.Ed25519PrivateKey.generate()).decode()})
    assert r.status_code == 400 and 'does not match' in r.get_json()['message']


# ---- FIPS mode, policies, compliance profiles, HSM -----------------------------------

@pytest.fixture
def fips_on(monkeypatch):
    import fips_mode
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)


@pytest.mark.parametrize('fields', [{'keyAlgo': 'EdDSA', 'keySize': 'Ed25519'}, {'keyAlgo': 'Ed448'}])
def test_fips_mode_refuses_an_eddsa_ca_key(app, auth_client, fips_on, fields):
    with app.app_context():
        before = CA.query.count()
    r = _new_ca(auth_client, 'Ed FIPS refused', **fields)
    assert r.status_code == 400, r.get_json()
    assert 'FIPS' in json.dumps(r.get_json())
    with app.app_context():
        assert CA.query.count() == before


def test_fips_mode_refuses_an_eddsa_key_import(auth_client, monkeypatch):
    import fips_mode
    key = ed25519.Ed25519PrivateKey.generate()
    ca_id = _import_cert_only(auth_client, _self_signed_ca(key, 'Ed25519 FIPS key import'), 'Ed FIPS key')
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
    r = _post(auth_client, f'/api/v2/cas/{ca_id}/key', {'key': _key_pem(key).decode()})
    assert r.status_code == 400, r.get_json()
    assert 'FIPS' in json.dumps(r.get_json())


def _policy(app, ca_id, rules):
    from models.policy import CertificatePolicy
    with app.app_context():
        pol = CertificatePolicy(name=f'ed-policy-{ca_id}-{sorted(rules)}', policy_type='issuance', ca_id=ca_id,
                                requires_approval=False, min_approvers=1, is_active=True, priority=100)
        pol.set_rules(rules)
        db.session.add(pol)
        db.session.commit()
        return pol.id


def _drop_policy(app, pid):
    from models.policy import CertificatePolicy
    with app.app_context():
        db.session.delete(db.session.get(CertificatePolicy, pid))
        db.session.commit()


@pytest.mark.parametrize('allowed, status', [(['RSA-2048'], 400), (['RSA-2048', 'ED25519'], 201)])
def test_allowed_key_types_bind_an_eddsa_intermediate(app, auth_client, allowed, status):
    parent = _ca(auth_client, f'Policy parent {len(allowed)}', keyAlgo='RSA-2048')
    pid = _policy(app, parent['id'], {'allowed_key_types': allowed})
    try:
        r = _new_ca(auth_client, f'Policy child {len(allowed)}', parent=parent['id'], keyAlgo='Ed25519')
        assert r.status_code == status, r.get_json()
        if status == 400:
            assert 'ED25519' in json.dumps(r.get_json())
    finally:
        _drop_policy(app, pid)


def test_a_digest_policy_does_not_block_an_eddsa_issuer(app, auth_client, ed_root):
    pid = _policy(app, ed_root['id'], {'allowed_digests': ['sha384']})
    try:
        leaf = _cert_cert(app, _issue(auth_client, ed_root['id'], 'policy-digest.ed.example.test'))
        assert leaf.signature_hash_algorithm is None
        leaf.verify_directly_issued_by(_ca_cert(app, ed_root['id']))
    finally:
        _drop_policy(app, pid)


@pytest.mark.parametrize('profile, allowed', [('anssi', True), ('bsi', False), ('eu-acm', False)])
def test_compliance_profiles_on_an_eddsa_root(auth_client, profile, allowed):
    r = _new_ca(auth_client, f'Ed25519 profile {profile}', keyAlgo='Ed25519', complianceProfile=profile)
    if allowed:
        assert r.status_code == 201, r.get_json()
    else:
        assert r.status_code in (400, 403), r.get_json()
        assert 'ED25519' in json.dumps(r.get_json()) or 'eddsa' in json.dumps(r.get_json())


@pytest.mark.parametrize('existing', [False, True], ids=['new-key', 'existing-key'])
@pytest.mark.parametrize('type_name', ['pkcs11', 'openbao', 'azure-keyvault', 'google-kms'])
def test_an_hsm_eddsa_ca_key_is_refused_with_a_400(app, auth_client, type_name, existing):
    """No HSM wrapper signs EdDSA, OpenBao's own ed25519 transit keys included."""
    from models.hsm import HsmKey, HsmProvider
    with app.app_context():
        row = HsmProvider(name=f'ed-hsm-{type_name}-{existing}', type=type_name, config='{}')
        db.session.add(row)
        db.session.commit()
        pid = row.id
        key = HsmKey(provider_id=pid, key_identifier='ed-x', label='ed-x', algorithm='Ed25519',
                     key_type='asymmetric', purpose='signing')
        db.session.add(key)
        db.session.commit()
        key_id = key.id
    body = {'hsm_key_id': key_id} if existing else {
        'hsm_provider_id': pid, 'hsm_key_label': 'ed', 'hsm_key_algorithm': 'ED25519'}
    try:
        r = auth_client.post('/api/v2/cas', json={
            'type': 'root', 'commonName': f'ed-hsm-{type_name}', 'organization': 'T', **body})
        assert r.status_code == 400, r.get_json()
        assert 'Ed25519 keys are not supported on an HSM' in r.get_json()['message']
    finally:
        with app.app_context():
            HsmKey.query.filter_by(provider_id=pid).delete()
            HsmProvider.query.filter_by(id=pid).delete()
            db.session.commit()


# ---- XCEP / WSTEP: Windows validates no EdDSA signature ---------------------------------

@pytest.fixture
def xcep_ca_setting(app):
    from tests.windows_profile_support import restore, snapshot
    with app.app_context():
        saved = snapshot(('xcep_ca_refid',))
        restore({'xcep_ca_refid': None})
    yield
    with app.app_context():
        restore(saved)


@pytest.mark.parametrize('name', ['Ed25519', 'Ed448'])
def test_xcep_settings_refuse_an_eddsa_ca(app, auth_client, xcep_ca_setting, name):
    from tests.windows_profile_support import get_config, put_default_profile
    ca = _ca(auth_client, f'{name} XCEP policy', keyAlgo=name)
    r = put_default_profile(auth_client, policy_ca_refid=ca['refid'])
    assert r.status_code == 400, r.get_json()
    assert name in r.get_json()['message'] and 'Windows' in r.get_json()['message']
    with app.app_context():
        assert not get_config('xcep_ca_refid')


def test_xcep_settings_still_take_an_rsa_ca(app, auth_client, xcep_ca_setting, rsa_root):
    from tests.windows_profile_support import put_default_profile
    r = put_default_profile(auth_client, policy_ca_refid=rsa_root['refid'])
    assert r.status_code == 200, r.get_json()
