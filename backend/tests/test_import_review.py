"""Import and re-import: findings of the independent review of #347's changes.

Records are built directly so that the exact state under test exists
(homonyms, pending CAs, revoked records) whatever the API would allow.
"""
import base64
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, ExtensionOID, NameOID

BASE = '/api/v2/certificates'
CA_IMPORT = '/api/v2/cas/import'


def _name(cn):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def _gen():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _cert(cn, key, *, issuer_cert=None, signer=None, ca=False, path_length=None, aki=True, ekus=None, days=30):
    now = datetime.now(timezone.utc)
    issuer_name = issuer_cert.subject if issuer_cert is not None else _name(cn)
    b = (x509.CertificateBuilder().subject_name(_name(cn)).issuer_name(issuer_name)
         .public_key(key.public_key()).serial_number(x509.random_serial_number())
         .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=days))
         .add_extension(x509.BasicConstraints(ca=ca, path_length=path_length if ca else None), critical=True)
         .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False))
    signing_key = signer or key
    if aki:
        b = b.add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(signing_key.public_key()), critical=False)
    if ekus:
        b = b.add_extension(x509.ExtendedKeyUsage(ekus), critical=False)
    return b.sign(signing_key, hashes.SHA256())


def _pem(cert):
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def _kpem(key):
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()


def _enc(key):
    from security.encryption import encrypt_private_key
    return encrypt_private_key(base64.b64encode(_kpem(key).encode()).decode())


def _csr_b64(cn, key, ca=False):
    b = x509.CertificateSigningRequestBuilder().subject_name(_name(cn))
    if ca:
        b = b.add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
    csr = b.sign(key, hashes.SHA256())
    return base64.b64encode(csr.public_bytes(serialization.Encoding.PEM)).decode()


def _info(cert):
    from services.import_service import extract_cert_info
    return extract_cert_info(cert)


def _store_ca(app, cert, key=None, **extra):
    with app.app_context():
        from models import db, CA
        info = _info(cert)
        fields = dict(refid=str(uuid.uuid4()), descr=info['cn'], serial=0,
                      crt=base64.b64encode(_pem(cert).encode()).decode(),
                      prv=_enc(key) if key is not None else None,
                      subject=info['subject'], issuer=info['issuer'], ski=info.get('ski'),
                      serial_number=str(cert.serial_number))
        fields.update(extra)
        row = CA(**fields)
        db.session.add(row); db.session.commit()
        return row.id, row.refid


def _store_cert(app, cert, key=None, **extra):
    with app.app_context():
        from models import db, Certificate
        info = _info(cert)
        fields = dict(refid=str(uuid.uuid4()), descr=info['cn'],
                      crt=base64.b64encode(_pem(cert).encode()).decode(),
                      prv=_enc(key) if key is not None else None,
                      subject=info['subject'], issuer=info['issuer'],
                      ski=info.get('ski'), aki=info.get('aki'),
                      serial_number=str(cert.serial_number),
                      valid_from=cert.not_valid_before_utc.replace(tzinfo=None),
                      valid_to=cert.not_valid_after_utc.replace(tzinfo=None))
        fields.update(extra)
        row = Certificate(**fields)
        db.session.add(row); db.session.commit()
        return row.id


def _import(auth_client, path, cert, key=None, **form):
    pem = _pem(cert) + (_kpem(key) if key is not None else '')
    return auth_client.post(path, data={'pem_content': pem, **form}, content_type='multipart/form-data')


def _ca_from_fixture(app, ca):
    """(x509 certificate, signing key, refid, ski) of a CA made by create_ca."""
    with app.app_context():
        from models import db, CA
        from services.hsm.ca_key_loader import get_ca_signing_key
        obj = db.session.get(CA, ca['id'])
        cert = x509.load_pem_x509_certificate(base64.b64decode(obj.crt))
        if not obj.ski:
            obj.ski = _info(cert)['ski']; db.session.commit()
        return cert, get_ca_signing_key(obj), obj.refid, obj.ski


def _row(app, model, row_id, *fields):
    with app.app_context():
        from models import db
        db.session.expire_all()
        row = db.session.get(model, row_id)
        return None if row is None else tuple(getattr(row, f) for f in fields)


class TestSmartImportKeysEncrypted:
    def test_smart_import_encrypts_the_key_at_rest(self, app, auth_client, encryption_enabled):
        key = _gen()
        cert = _cert('Smart Import Enc CA', key, ca=True)
        r = auth_client.post('/api/v2/import/execute', data=json.dumps({
            'content': _pem(cert) + _kpem(key), 'options': {'import_cas': True, 'import_certs': True}}),
            content_type='application/json')
        assert r.status_code in (200, 201), r.data
        with app.app_context():
            from models import CA
            from security.encryption import decrypt_private_key
            row = CA.query.filter_by(subject=_info(cert)['subject']).order_by(CA.id.desc()).first()
            assert row is not None and row.prv
            plain_b64 = base64.b64encode(_kpem(key).encode()).decode()
            assert row.prv != plain_b64, 'stored in clear'
            assert base64.b64decode(decrypt_private_key(row.prv)).decode().strip() == _kpem(key).strip()


class TestRevocationFollowsTheCertificate:
    def test_renewed_certificate_on_a_revoked_record_is_not_revoked(self, app, auth_client, create_ca):
        from models import Certificate
        from models.revoked_serial import RevokedSerial
        ca = create_ca(cn='Revoked Record CA')
        ca_cert, ca_key, caref, _ = _ca_from_fixture(app, ca)
        key = _gen()
        old = _cert('revoked-renew.example.com', key, issuer_cert=ca_cert, signer=ca_key)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        cert_id = _store_cert(app, old, key, caref=caref, revoked=True, revoked_at=now, revoke_reason='keyCompromise')
        with app.app_context():
            from models import db
            db.session.add(RevokedSerial(caref=caref, serial_number=str(old.serial_number), revoked_at=now,
                                         revoke_reason='keyCompromise', valid_to=now + timedelta(days=30),
                                         certificate_id=cert_id))
            db.session.commit()
        new = _cert('revoked-renew.example.com', key, issuer_cert=ca_cert, signer=ca_key)
        r = _import(auth_client, f'{BASE}/import', new)
        assert r.status_code == 200, r.data
        body = json.loads(r.data)
        assert body['data']['id'] == cert_id
        assert _row(app, Certificate, cert_id, 'revoked', 'revoke_reason', 'serial_number') == (False, None, str(new.serial_number))
        with app.app_context():
            assert RevokedSerial.query.filter_by(caref=caref, serial_number=str(old.serial_number)).first() is not None
        # The very same revoked certificate imported again stays revoked
        cert_id2 = _store_cert(app, old, key, caref=caref, revoked=True, revoked_at=now, revoke_reason='keyCompromise',
                               subject='CN=revoked-same.example.com')
        with app.app_context():
            from models import db
            row = db.session.get(Certificate, cert_id2); row.subject = _info(old)['subject']; db.session.commit()
        r = _import(auth_client, f'{BASE}/import', old)
        assert r.status_code in (200, 409), r.data   # same certificate: lands on one of the records or refused
        if r.status_code == 200:
            assert _row(app, Certificate, json.loads(r.data)['data']['id'], 'revoked')[0] is True

    def test_renewed_sub_ca_on_a_revoked_record_is_not_revoked(self, app, auth_client, create_ca):
        from models import CA
        from models.revoked_serial import RevokedSerial
        parent = create_ca(cn='Revoked Sub Parent')
        p_cert, p_key, p_refid, _ = _ca_from_fixture(app, parent)
        key = _gen()
        old = _cert('Revoked Sub CA', key, issuer_cert=p_cert, signer=p_key, ca=True)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        ca_id, _ = _store_ca(app, old, key, caref=p_refid, revoked=True, revoked_at=now, revoke_reason='keyCompromise')
        with app.app_context():
            from models import db
            db.session.add(RevokedSerial(caref=p_refid, serial_number=str(old.serial_number), revoked_at=now,
                                         revoke_reason='keyCompromise', valid_to=now + timedelta(days=30)))
            db.session.commit()
        new = _cert('Revoked Sub CA', key, issuer_cert=p_cert, signer=p_key, ca=True)
        r = _import(auth_client, CA_IMPORT, new)
        assert r.status_code == 200, r.data
        assert json.loads(r.data)['data']['id'] == ca_id
        assert _row(app, CA, ca_id, 'revoked', 'revoke_reason', 'serial_number', 'caref') == (False, None, str(new.serial_number), p_refid)


class TestEdKeys:
    @pytest.mark.parametrize('path', [CA_IMPORT, f'{BASE}/import'])
    def test_ed25519_ca_key_is_refused_with_the_reason(self, app, auth_client, path):
        key = ed25519.Ed25519PrivateKey.generate()
        now = datetime.now(timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(_name('Ed CA')).issuer_name(_name('Ed CA'))
                .public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=30))
                .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                .sign(key, None))
        r = _import(auth_client, path, cert, key)
        assert r.status_code == 400, r.data
        assert 'Ed25519' in json.loads(r.data)['message']

    def test_ed25519_leaf_renewal_keeps_the_key_type(self, app, auth_client, create_ca):
        from models import Certificate
        ca = create_ca(cn='Ed Leaf Renew CA')
        ca_cert, ca_key, caref, _ = _ca_from_fixture(app, ca)
        key = ed25519.Ed25519PrivateKey.generate()
        now = datetime.now(timezone.utc)
        leaf = (x509.CertificateBuilder().subject_name(_name('ed-leaf.example.com')).issuer_name(ca_cert.subject)
                .public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=30))
                .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                .sign(ca_key, hashes.SHA256()))
        r = _import(auth_client, f'{BASE}/import', leaf, key, ca_id=str(ca['id']))
        assert r.status_code in (200, 201), r.data
        cert_id = json.loads(r.data)['data']['id']
        r = auth_client.post(f'{BASE}/{cert_id}/renew', data=json.dumps({}), content_type='application/json')
        assert r.status_code == 200, r.data
        with app.app_context():
            from models import db
            db.session.expire_all()
            renewed = x509.load_pem_x509_certificate(base64.b64decode(db.session.get(Certificate, cert_id).crt))
            assert isinstance(renewed.public_key(), ed25519.Ed25519PublicKey)
            assert renewed.serial_number != leaf.serial_number


class TestPendingCaTargets:
    def test_foreign_homonym_of_a_pending_ca_is_a_new_ca(self, app, auth_client):
        from models import CA
        k1, k2 = _gen(), _gen()
        probe = _cert('Pending Homonym Foreign', k1, ca=True)
        with app.app_context():
            from models import db
            row = CA(refid=str(uuid.uuid4()), descr='Pending Homonym Foreign', crt='', serial=0,
                     csr=_csr_b64('Pending Homonym Foreign', k1, ca=True), prv=_enc(k1),
                     subject=_info(probe)['subject'], imported_from='external_csr')
            db.session.add(row); db.session.commit(); pending_id = row.id
        r = _import(auth_client, CA_IMPORT, _cert('Pending Homonym Foreign', k2, ca=True))
        assert r.status_code == 201, r.data
        assert json.loads(r.data)['data']['id'] != pending_id
        crt, csr, prv = _row(app, CA, pending_id, 'crt', 'csr', 'prv')
        assert crt == '' and csr and prv

    def test_pending_ca_without_key_takes_the_key_arriving_with_its_certificate(self, app, auth_client):
        from models import CA
        key, ext = _gen(), _gen()
        ext_cert = _cert('External Root For Pending', ext, ca=True)
        signed = _cert('Pending Keyless CA', key, issuer_cert=ext_cert, signer=ext, ca=True)
        with app.app_context():
            from models import db
            row = CA(refid=str(uuid.uuid4()), descr='Pending Keyless CA', crt='', serial=0,
                     csr=_csr_b64('Pending Keyless CA', key, ca=True), prv=None,
                     subject=_info(signed)['subject'], imported_from='external_csr')
            db.session.add(row); db.session.commit(); pending_id = row.id
        r = _import(auth_client, CA_IMPORT, signed, key, name='Renamed On Install')
        assert r.status_code == 200, r.data
        body = json.loads(r.data)
        assert body['data']['id'] == pending_id and body['data']['has_private_key'] is True
        assert 'installed' in body['message']
        assert _row(app, CA, pending_id, 'descr', 'csr')[0] == 'Renamed On Install'
        assert _row(app, CA, pending_id, 'crt')[0]


class TestActiveCaWithRequest:
    def test_renewal_request_is_fulfilled_through_the_dedicated_path(self, app, auth_client):
        from models import CA
        key, ext = _gen(), _gen()
        ext_cert = _cert('External Root For Renewal', ext, ca=True)
        first = _cert('External CSR CA', key, issuer_cert=ext_cert, signer=ext, ca=True)
        ca_id, _ = _store_ca(app, first, key, imported_from='external_csr', csr=_csr_b64('External CSR CA', key, ca=True))
        renewed = _cert('External CSR CA', key, issuer_cert=ext_cert, signer=ext, ca=True)
        r = _import(auth_client, CA_IMPORT, renewed)
        assert r.status_code == 200, r.data
        body = json.loads(r.data)
        assert body['data']['id'] == ca_id and 'installed' in body['message']
        assert body['data'].get('superseded_serial') == format(first.serial_number, 'x')
        assert _row(app, CA, ca_id, 'csr', 'serial_number') == (None, str(renewed.serial_number))

    def test_generic_update_relinks_parent_and_path_length(self, app, auth_client, create_ca):
        from models import CA
        parent_a = create_ca(cn='Relink Parent A')
        parent_b = create_ca(cn='Relink Parent B')
        a_cert, a_key, a_refid, _ = _ca_from_fixture(app, parent_a)
        b_cert, b_key, b_refid, _ = _ca_from_fixture(app, parent_b)
        key = _gen()
        under_a = _cert('Relinked Sub CA', key, issuer_cert=a_cert, signer=a_key, ca=True, path_length=0)
        ca_id, _ = _store_ca(app, under_a, key, caref=a_refid, path_length=0)
        under_b = _cert('Relinked Sub CA', key, issuer_cert=b_cert, signer=b_key, ca=True, path_length=2)
        r = _import(auth_client, CA_IMPORT, under_b)
        assert r.status_code == 200, r.data
        assert json.loads(r.data)['data']['id'] == ca_id
        assert _row(app, CA, ca_id, 'caref', 'path_length') == (b_refid, 2)


class TestCertificateParentResolvedWithoutCaId:
    def test_reimport_without_ca_id_links_the_issuing_ca_by_aki(self, app, auth_client, create_ca):
        from models import Certificate
        ca = create_ca(cn='AKI Link CA')
        ca_cert, ca_key, caref, ski = _ca_from_fixture(app, ca)
        key = _gen()
        leaf = _cert('aki-link.example.com', key, issuer_cert=ca_cert, signer=ca_key)
        cert_id = _store_cert(app, leaf, key, caref=None)
        r = _import(auth_client, f'{BASE}/import', leaf)
        assert r.status_code == 200, r.data
        assert json.loads(r.data)['data']['id'] == cert_id
        assert _row(app, Certificate, cert_id, 'caref')[0] == caref


class TestCaCertificateForAPendingRequest:
    @pytest.mark.parametrize('path', [CA_IMPORT, f'{BASE}/import'])
    def test_intermediate_request_key_moves_to_the_new_ca(self, app, auth_client, path):
        from models import CA, Certificate
        key, ext = _gen(), _gen()
        ext_cert = _cert('External Root For Request', ext, ca=True)
        cn = f"Requested Intermediate {path.split('/')[3]}"
        with app.app_context():
            from models import db
            req = Certificate(refid=str(uuid.uuid4()), descr=cn, csr=_csr_b64(cn, key, ca=True), prv=_enc(key),
                              crt=None, subject=f'CN={cn}')
            db.session.add(req); db.session.commit(); req_id = req.id
        signed = _cert(cn, key, issuer_cert=ext_cert, signer=ext, ca=True)
        r = _import(auth_client, path, signed)
        assert r.status_code == 201, r.data
        body = json.loads(r.data)
        assert body['data']['has_private_key'] is True
        assert 'fulfilled' in body['message']
        assert _row(app, Certificate, req_id, 'id') is None
        assert _row(app, CA, body['data']['id'], 'serial_number')[0] == str(signed.serial_number)
