"""Ed25519 and Ed448 in FIPS mode (#399): SSH CAs and deploy keys default to
ECDSA P-256, and an existing EdDSA key is refused with a readable FIPS error
before the crypto library is asked to load it."""
import base64
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed448, ed25519, rsa
from cryptography.hazmat.primitives.serialization import ssh as ssh_serialization
from cryptography.x509 import ocsp
from cryptography.x509.oid import NameOID

import fips_mode
from fips_mode import FipsRestricted
from models import CA, Certificate, SSHCertificateAuthority, db
from utils.key_codec import eddsa_key_name, store_pem_bytes

_EDDSA = (ed25519.Ed25519PrivateKey, ed25519.Ed25519PublicKey,
          ed448.Ed448PrivateKey, ed448.Ed448PublicKey)


@pytest.fixture
def fips_on(monkeypatch):
    """FIPS mode, with the provider's behaviour: loading an EdDSA key fails opaquely."""
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)

    def is_eddsa(obj):
        if isinstance(obj, ssh_serialization.SSHCertificate):
            return isinstance(obj.public_key(), _EDDSA) or isinstance(obj.signature_key(), _EDDSA)
        return isinstance(obj, _EDDSA)

    def opaque(real):
        def load(*args, **kwargs):
            key = real(*args, **kwargs)
            if is_eddsa(key):
                raise RuntimeError('simulated provider failure: EdDSA key loaded')
            return key
        return load

    for module, name in ((serialization, 'load_pem_private_key'), (serialization, 'load_der_private_key'),
                         (serialization, 'load_ssh_private_key'), (serialization, 'load_ssh_public_identity'),
                         (ssh_serialization, 'load_ssh_private_key'),
                         (ssh_serialization, 'load_ssh_public_identity')):
        monkeypatch.setattr(module, name, opaque(getattr(module, name)))


@pytest.fixture
def fips_off(monkeypatch):
    monkeypatch.setattr(fips_mode, 'enabled', lambda: False)


def _post(client, url, payload):
    return client.post(url, data=json.dumps(payload), content_type='application/json')


def _assert_fips_problem(r, name='Ed25519'):
    body = r.get_json()
    assert r.status_code == 400, body
    assert body['type'] == fips_mode.PROBLEM_TYPE, body
    assert name in body['detail'] and 'FIPS mode' in body['detail'], body


def _openssh(key) -> str:
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH,
                             serialization.NoEncryption()).decode()


def _ssh_public(key) -> str:
    return key.public_key().public_bytes(serialization.Encoding.OpenSSH,
                                         serialization.PublicFormat.OpenSSH).decode()


def _pkcs8(key) -> bytes:
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())


# ---------------------------------------------------------------- recognition

class TestEddsaKeyName:
    @pytest.mark.parametrize('make, name', [
        (ed25519.Ed25519PrivateKey.generate, 'Ed25519'),
        (ed448.Ed448PrivateKey.generate, 'Ed448'),
    ])
    def test_pkcs8_pem_and_der(self, make, name):
        key = make()
        assert eddsa_key_name(_pkcs8(key)) == name
        der = key.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
        assert eddsa_key_name(der) == name
        spki = key.public_key().public_bytes(serialization.Encoding.PEM,
                                             serialization.PublicFormat.SubjectPublicKeyInfo)
        assert eddsa_key_name(spki) == name

    def test_openssh_forms(self):
        key = ed25519.Ed25519PrivateKey.generate()
        assert eddsa_key_name(_openssh(key)) == 'Ed25519'
        encrypted = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH,
                                      serialization.BestAvailableEncryption(b'secret'))
        assert eddsa_key_name(encrypted) == 'Ed25519'  # the public part stays in clear
        line = _ssh_public(key)
        assert eddsa_key_name(line) == 'Ed25519'
        assert eddsa_key_name(line.split()[1]) == 'Ed25519'  # bare blob

    def test_ssh_certificate_signed_by_an_ed25519_ca(self):
        import time
        ca_key = ed25519.Ed25519PrivateKey.generate()
        subject = ec.generate_private_key(ec.SECP256R1())
        now = int(time.time())
        cert = (ssh_serialization.SSHCertificateBuilder().public_key(subject.public_key())
                .serial(1).type(ssh_serialization.SSHCertificateType.USER).key_id(b'k')
                .valid_principals([b'u']).valid_after(now).valid_before(now + 60).sign(ca_key))
        assert eddsa_key_name(cert.public_bytes()) == 'Ed25519'

    @pytest.mark.parametrize('key', [
        rsa.generate_private_key(65537, 2048), ec.generate_private_key(ec.SECP256R1())])
    def test_rsa_and_ec_are_not_eddsa(self, key):
        assert eddsa_key_name(_pkcs8(key)) is None
        assert eddsa_key_name(key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption())) is None
        assert eddsa_key_name(_openssh(key)) is None
        assert eddsa_key_name(_ssh_public(key)) is None

    @pytest.mark.parametrize('junk', [None, b'', 'not a key', b'\x30\x82\xff', b'-----BEGIN PRIVATE KEY-----\n!!\n-----END PRIVATE KEY-----'])
    def test_junk_is_not_eddsa(self, junk):
        assert eddsa_key_name(junk) is None


# ------------------------------------------------------------- SSH defaults

class TestSshCaDefaults:
    def test_fips_mode_creates_ecdsa_p256_by_default(self, auth_client, fips_on):
        r = _post(auth_client, '/api/v2/ssh/cas', {'descr': f'FIPS default {uuid.uuid4().hex[:6]}'})
        assert r.status_code == 201, r.get_json()
        data = r.get_json()['data']
        assert data['key_type'] == 'ecdsa-p256'
        assert data['public_key'].startswith('ecdsa-sha2-nistp256 ')

    def test_default_stays_ed25519_outside_fips_mode(self, auth_client, fips_off):
        r = _post(auth_client, '/api/v2/ssh/cas', {'descr': f'Std default {uuid.uuid4().hex[:6]}'})
        assert r.status_code == 201, r.get_json()
        assert r.get_json()['data']['key_type'] == 'ed25519'

    def test_ed25519_is_refused_in_fips_mode(self, auth_client, fips_on):
        r = _post(auth_client, '/api/v2/ssh/cas', {'descr': 'FIPS ed', 'key_type': 'ed25519'})
        _assert_fips_problem(r)

    def test_ecdsa_alias_names_p256(self, auth_client, fips_on):
        r = _post(auth_client, '/api/v2/ssh/cas', {'descr': f'Alias {uuid.uuid4().hex[:6]}', 'key_type': 'ECDSA'})
        assert r.status_code == 201, r.get_json()
        assert r.get_json()['data']['key_type'] == 'ecdsa-p256'

    def test_generated_user_key_defaults_to_ecdsa_in_fips_mode(self, auth_client, fips_on):
        ca = _post(auth_client, '/api/v2/ssh/cas', {'descr': f'Gen {uuid.uuid4().hex[:6]}'}).get_json()['data']
        r = _post(auth_client, '/api/v2/ssh/certificates/generate',
                  {'ca_id': ca['id'], 'cert_type': 'user', 'principals': ['alice']})
        assert r.status_code == 201, r.get_json()
        key = ssh_serialization.load_ssh_private_key(r.get_json()['data']['private_key'].encode(), None)
        assert isinstance(key, ec.EllipticCurvePrivateKey) and key.curve.name == 'secp256r1'

    def test_generated_user_key_stays_ed25519_outside_fips_mode(self, auth_client, fips_off):
        ca = _post(auth_client, '/api/v2/ssh/cas', {'descr': f'Gen std {uuid.uuid4().hex[:6]}'}).get_json()['data']
        r = _post(auth_client, '/api/v2/ssh/certificates/generate',
                  {'ca_id': ca['id'], 'cert_type': 'user', 'principals': ['alice']})
        assert r.status_code == 201, r.get_json()
        assert r.get_json()['data']['private_key'].startswith('-----BEGIN OPENSSH PRIVATE KEY-----')
        assert eddsa_key_name(r.get_json()['data']['private_key']) == 'Ed25519'


# ------------------------------------------------- existing SSH Ed25519 objects

@pytest.fixture
def ed25519_ssh_ca(app, monkeypatch):
    """An Ed25519 SSH CA created before the instance went FIPS."""
    from services.ssh_ca_service import SSHCAService
    with app.app_context():
        with monkeypatch.context() as m:
            m.setattr(fips_mode, 'enabled', lambda: False)
            ca = SSHCAService.create_ca(descr=f'Legacy Ed SSH CA {uuid.uuid4().hex[:6]}',
                                        ca_type='user', key_type='ed25519', username='t')
        return ca.id


class TestExistingSshObjects:
    def test_signing_with_an_ed25519_ca_is_refused_before_a_serial_is_spent(
            self, app, auth_client, ed25519_ssh_ca, fips_on):
        subject = ec.generate_private_key(ec.SECP256R1())
        r = _post(auth_client, '/api/v2/ssh/certificates', {
            'ca_id': ed25519_ssh_ca, 'cert_type': 'user', 'principals': ['alice'],
            'public_key': _ssh_public(subject)})
        _assert_fips_problem(r)
        with app.app_context():
            assert db.session.get(SSHCertificateAuthority, ed25519_ssh_ca).serial_counter == 0

    def test_the_stored_key_is_refused_even_when_its_type_column_is_wrong(
            self, app, ed25519_ssh_ca, fips_on):
        from services.ssh_ca_service import SSHCAService
        with app.app_context():
            ca = db.session.get(SSHCertificateAuthority, ed25519_ssh_ca)
            ca.key_type = 'ecdsa-p256'
            db.session.commit()
            with pytest.raises(FipsRestricted, match='Ed25519 key of SSH CA'):
                SSHCAService.get_private_key_object(ed25519_ssh_ca)

    def test_an_ed25519_subject_key_is_refused(self, app, auth_client, fips_on):
        ca = _post(auth_client, '/api/v2/ssh/cas', {'descr': f'EC signer {uuid.uuid4().hex[:6]}'}).get_json()['data']
        r = _post(auth_client, '/api/v2/ssh/certificates', {
            'ca_id': ca['id'], 'cert_type': 'user', 'principals': ['alice'],
            'public_key': _ssh_public(ed25519.Ed25519PrivateKey.generate())})
        _assert_fips_problem(r)

    def test_importing_an_ed25519_ca_is_refused(self, auth_client, fips_on):
        r = _post(auth_client, '/api/v2/ssh/cas/import', {
            'descr': 'Imported Ed', 'ca_type': 'user',
            'private_key': _openssh(ed25519.Ed25519PrivateKey.generate())})
        _assert_fips_problem(r)

    def test_the_same_ca_still_signs_outside_fips_mode(self, auth_client, ed25519_ssh_ca, fips_off):
        r = _post(auth_client, '/api/v2/ssh/certificates', {
            'ca_id': ed25519_ssh_ca, 'cert_type': 'user', 'principals': ['alice'],
            'public_key': _ssh_public(ec.generate_private_key(ec.SECP256R1()))})
        assert r.status_code == 201, r.get_json()


# ------------------------------------------------------------- deploy keys

class TestDeployKeys:
    def test_generated_key_is_ecdsa_p256_in_fips_mode(self, fips_on):
        from services.deploy.ssh import generate_keypair
        private, public = generate_keypair()
        assert public.startswith('ecdsa-sha2-nistp256 ')
        assert eddsa_key_name(private) is None

    def test_generated_key_stays_ed25519_outside_fips_mode(self, fips_off):
        from services.deploy.ssh import generate_keypair
        _, public = generate_keypair()
        assert public.startswith('ssh-ed25519 ')

    def test_an_ed25519_key_is_refused_on_create(self, auth_client, fips_on):
        r = _post(auth_client, '/api/v2/deploy/targets', {
            'name': f'fips-ed-{uuid.uuid4().hex[:6]}', 'host': 'h.example.test', 'username': 'u',
            'private_key': _openssh(ed25519.Ed25519PrivateKey.generate())})
        assert r.status_code == 400, r.get_json()
        assert 'Ed25519 key of the deploy target not available in FIPS mode' in r.get_json()['message']

    def test_a_stored_ed25519_key_is_refused_before_connecting(self, app, auth_client, monkeypatch):
        import services.deploy.ssh as deploy_ssh
        with monkeypatch.context() as m:
            m.setattr(fips_mode, 'enabled', lambda: False)
            target = _post(auth_client, '/api/v2/deploy/targets', {
                'name': f'legacy-ed-{uuid.uuid4().hex[:6]}', 'host': 'h.example.test',
                'username': 'u'}).get_json()['data']
        assert target['public_key'].startswith('ssh-ed25519 ')
        monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
        monkeypatch.setattr(deploy_ssh, '_require_paramiko',
                            lambda: pytest.fail('the key reached paramiko'))
        r = auth_client.post(f"/api/v2/deploy/targets/{target['id']}/test")
        _assert_fips_problem(r)


# --------------------------------------------------------- X.509 EdDSA objects

def _ed_ca_row(cn):
    key = ed25519.Ed25519PrivateKey.generate()
    now = datetime.now(timezone.utc)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=365))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .sign(key, None))
    row = CA(refid=str(uuid.uuid4()), descr=cn, serial=0, prv=store_pem_bytes(_pkcs8(key)),
             crt=base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode(),
             subject=name.rfc4514_string(), issuer=name.rfc4514_string(),
             ocsp_enabled=True, cdp_enabled=True)
    db.session.add(row)
    db.session.commit()
    return row.id


@pytest.fixture
def ed_ca(app):
    with app.app_context():
        ca_id = _ed_ca_row(f'Legacy Ed25519 CA {uuid.uuid4().hex[:6]}')
    yield ca_id
    with app.app_context():
        db.session.rollback()
        row = db.session.get(CA, ca_id)
        if row is not None:
            from models.crl import CRLMetadata
            CRLMetadata.query.filter_by(ca_id=ca_id).delete()
            db.session.delete(row)
            db.session.commit()


class TestExistingX509Objects:
    def test_the_signing_key_loader_refuses_it(self, app, ed_ca, fips_on):
        from services.hsm.ca_key_loader import get_ca_signing_key
        with app.app_context():
            with pytest.raises(FipsRestricted, match=r"Ed25519 key of CA 'Legacy Ed25519 CA"):
                get_ca_signing_key(db.session.get(CA, ed_ca))

    def test_issuing_from_it_answers_the_fips_problem(self, auth_client, ed_ca, fips_on):
        r = _post(auth_client, '/api/v2/certificates', {
            'cn': 'leaf.fips-ed.test', 'ca_id': ed_ca, 'validity_days': 30,
            'key_type': 'ec', 'key_size': 'secp256r1'})
        _assert_fips_problem(r)

    def test_crl_regeneration_answers_the_fips_problem(self, auth_client, ed_ca, fips_on):
        _assert_fips_problem(auth_client.post(f'/api/v2/crl/{ed_ca}/regenerate'))

    def test_ocsp_answers_unauthorized(self, app, ed_ca, fips_on):
        from services.ocsp_service import OCSPService
        with app.app_context():
            der, _status = OCSPService().generate_response(db.session.get(CA, ed_ca), 12345)
        assert ocsp.load_der_ocsp_response(der).response_status == ocsp.OCSPResponseStatus.UNAUTHORIZED

    def test_scep_refuses_it(self, app, ed_ca, fips_on):
        from services.scep.scep_service import SCEPService
        with app.app_context():
            refid = db.session.get(CA, ed_ca).refid
            with pytest.raises(FipsRestricted, match='Ed25519 key of CA'):
                SCEPService(ca_refid=refid)

    def test_the_scep_endpoint_refuses_with_the_reason(self, app, ed_ca, fips_on, monkeypatch):
        import api.scep_protocol as scep_protocol
        config = {'scep_enabled': 'true', 'scep_ca_id': str(ed_ca)}
        monkeypatch.setattr(scep_protocol, 'get_config', lambda key, default=None: config.get(key, default))
        with app.app_context():
            service, error = scep_protocol.get_scep_service()
        assert service is None
        assert 'Ed25519 key of CA' in str(error) and error.status == 503

    def test_the_same_ca_still_signs_outside_fips_mode(self, app, ed_ca, fips_off):
        from services.hsm.ca_key_loader import get_ca_signing_key
        with app.app_context():
            assert isinstance(get_ca_signing_key(db.session.get(CA, ed_ca)), ed25519.Ed25519PrivateKey)


def _import_leaf(app, auth_client, ca_id, key, cn):
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        ca_cert = x509.load_pem_x509_certificate(base64.b64decode(ca.crt))
        from utils.key_codec import load_pem_bytes
        ca_key = serialization.load_pem_private_key(load_pem_bytes(ca.prv), None)
    now = datetime.now(timezone.utc)
    algorithm = None if isinstance(ca_key, ed25519.Ed25519PrivateKey) else hashes.SHA256()
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
            .issuer_name(ca_cert.subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=30))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(cn)]), critical=False)
            .sign(ca_key, algorithm))
    pem = cert.public_bytes(serialization.Encoding.PEM) + _pkcs8(key)
    r = auth_client.post('/api/v2/certificates/import',
                         data={'pem_content': pem.decode(), 'name': cn},
                         content_type='multipart/form-data')
    assert r.status_code in (200, 201), r.get_json()
    return r.get_json()['data']['id']


class TestRenewal:
    def test_an_ed25519_leaf_is_refused_and_left_intact(self, app, auth_client, create_ca, monkeypatch):
        ca_id = create_ca(cn=f'RSA issuer {uuid.uuid4().hex[:6]}')['id']
        with monkeypatch.context() as m:
            m.setattr(fips_mode, 'enabled', lambda: False)
            cert_id = _import_leaf(app, auth_client, ca_id, ed25519.Ed25519PrivateKey.generate(),
                                   'ed-leaf.fips.test')
        with app.app_context():
            row = db.session.get(Certificate, cert_id)
            before = (row.crt, row.prv, row.serial_number)
        monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
        r = _post(auth_client, f'/api/v2/certificates/{cert_id}/renew', {})
        _assert_fips_problem(r)
        with app.app_context():
            db.session.expire_all()
            row = db.session.get(Certificate, cert_id)
            assert (row.crt, row.prv, row.serial_number) == before

    def test_a_leaf_of_an_ed25519_ca_is_refused(self, app, auth_client, ed_ca, monkeypatch):
        with monkeypatch.context() as m:
            m.setattr(fips_mode, 'enabled', lambda: False)
            cert_id = _import_leaf(app, auth_client, ed_ca, ec.generate_private_key(ec.SECP256R1()),
                                   'ec-leaf-of-ed.fips.test')
        monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
        r = _post(auth_client, f'/api/v2/certificates/{cert_id}/renew', {})
        _assert_fips_problem(r)
        with app.app_context():
            row = db.session.get(Certificate, cert_id)
            db.session.delete(row)
            db.session.commit()


class TestOcspDelegatedResponder:
    def test_an_ed25519_responder_key_is_refused(self, app, fips_on):
        from types import SimpleNamespace
        from services.ocsp_service import OCSPService
        record = SimpleNamespace(id=7, prv=store_pem_bytes(_pkcs8(ed25519.Ed25519PrivateKey.generate())))
        with app.app_context(), pytest.raises(FipsRestricted, match='OCSP responder certificate 7'):
            OCSPService()._load_responder_key(record)


# ------------------------------------------------------------------ OpenBao

class TestOpenBaoInventory:
    @staticmethod
    def _provider(monkeypatch):
        from services.hsm.openbao_provider import OpenBaoProvider
        provider = OpenBaoProvider.__new__(OpenBaoProvider)
        keys = {'ca-ec': 'ecdsa-p256', 'ssh-ed': 'ed25519', 'wrap': 'chacha20-poly1305', 'aes': 'aes256-gcm96'}

        def api(method, path, **_):
            if method == 'LIST':
                return {'data': {'keys': list(keys)}}
            return {'data': {'type': keys[path.split('/')[1]], 'keys': {}}}
        monkeypatch.setattr(provider, '_api', api, raising=False)
        return provider

    def test_unapproved_types_are_left_out_in_fips_mode(self, monkeypatch, fips_on):
        listed = {k.key_identifier for k in self._provider(monkeypatch).list_keys()}
        assert listed == {'ca-ec', 'aes'}

    def test_every_type_is_listed_outside_fips_mode(self, monkeypatch, fips_off):
        listed = {k.key_identifier for k in self._provider(monkeypatch).list_keys()}
        assert listed == {'ca-ec', 'ssh-ed', 'wrap', 'aes'}


@pytest.fixture
def pending_csr(auth_client):
    """A CSR made before FIPS mode is switched on (list it ahead of fips_on)."""
    r = _post(auth_client, '/api/v2/csrs', {'cn': f'csr-{uuid.uuid4().hex[:6]}.fips-ed.test',
                                            'organization': 'FIPS', 'country': 'US',
                                            'key_type': 'EC-P256'})
    assert r.status_code in (200, 201), r.get_json()
    return r.get_json()['data']['id']


class TestSiblingIssuancePaths:
    """Paths next to POST /certificates keep the FIPS problem type."""

    def test_signing_a_csr_from_it_answers_the_fips_problem(self, auth_client, pending_csr, ed_ca, fips_on):
        _assert_fips_problem(_post(auth_client, f'/api/v2/csrs/{pending_csr}/sign',
                                   {'ca_id': ed_ca, 'validity_days': 30}))

    def test_bulk_signing_names_the_fips_reason(self, auth_client, pending_csr, ed_ca, fips_on):
        r = _post(auth_client, '/api/v2/csrs/bulk/sign', {'ids': [pending_csr], 'ca_id': ed_ca})
        failed = r.get_json()['data']['failed']
        assert failed and 'not available in FIPS mode' in failed[0]['error'], r.get_json()

    def test_the_tsa_signer_from_it_answers_the_fips_problem(self, auth_client, ed_ca, fips_on):
        _assert_fips_problem(_post(auth_client, '/api/v2/tsa/signer-certificate',
                                   {'ca_id': ed_ca, 'key_type': 'ec', 'curve': 'P-256'}))

    def test_an_intermediate_under_it_answers_the_fips_problem(self, auth_client, ed_ca, fips_on):
        _assert_fips_problem(_post(auth_client, '/api/v2/cas', {
            'type': 'intermediate', 'parentCAId': ed_ca, 'commonName': 'Sub of Ed25519',
            'organization': 'FIPS', 'country': 'US', 'validityYears': 1,
            'keyAlgo': 'EC', 'keySize': 'secp256r1'}))

    def test_service_issuance_keeps_the_fips_refusal(self, app, ed_ca, fips_on):
        from services.cert_service import CertificateService
        with app.app_context():
            refid = db.session.get(CA, ed_ca).refid
            with pytest.raises(FipsRestricted, match='Ed25519 key of CA'):
                CertificateService.create_certificate(
                    descr='svc leaf', caref=refid, dn={'CN': 'svc.fips-ed.test'},
                    cert_type='server_cert', key_type='EC-P256', validity_days=30)

    def test_installing_a_certificate_on_it_keeps_the_fips_refusal(self, app, ed_ca, fips_on):
        from services.ca_service import CAService
        with app.app_context():
            ca = db.session.get(CA, ed_ca)
            with pytest.raises(FipsRestricted, match='Ed25519 key of CA'):
                CAService.complete_external_ca(ca, base64.b64decode(ca.crt))


def _ed_pem_bundle(cn, ca=True):
    key = ed25519.Ed25519PrivateKey.generate()
    now = datetime.now(timezone.utc)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=365))
            .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
            .sign(key, None))
    return (cert.public_bytes(serialization.Encoding.PEM) + _pkcs8(key)).decode()


class TestImports:
    @pytest.mark.parametrize('url, ca', [('/api/v2/cas/import', True),
                                         ('/api/v2/certificates/import', False)])
    def test_an_ed25519_file_answers_the_fips_problem(self, auth_client, fips_on, url, ca):
        pem = _ed_pem_bundle(f'Imported Ed25519 {uuid.uuid4().hex[:6]}', ca=ca)
        r = auth_client.post(url, data={'pem_content': pem, 'name': 'ed import'})
        _assert_fips_problem(r)
        assert 'the imported file' in r.get_json()['detail']
