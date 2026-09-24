"""Private-key filesystem mirror policy regression tests (#320)."""
import uuid

from models import CA, Certificate, db
from services.file_regen_service import mirror_private_key, purge_private_key_files
from utils.file_naming import ca_cert_path, ca_key_path, cert_cert_path, cert_key_path


KEY_PEM = b"-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n"


def test_mirror_private_key_writes_mode_0600_when_encryption_disabled(
    monkeypatch, tmp_path
):
    from security.encryption import key_encryption

    monkeypatch.setattr(key_encryption, '_enabled', False)
    path = tmp_path / 'private' / 'certificate.key'

    assert mirror_private_key(path, KEY_PEM, context='test certificate') is True
    assert path.read_bytes() == KEY_PEM
    assert path.stat().st_mode & 0o777 == 0o600


def test_mirror_private_key_skips_and_removes_stale_file_when_encrypted(
    encryption_enabled, tmp_path
):
    path = tmp_path / 'private' / 'certificate.key'
    path.parent.mkdir()
    path.write_bytes(b'plaintext')

    assert mirror_private_key(path, KEY_PEM, context='test certificate') is False
    assert not path.exists()


def test_mirror_private_key_returns_false_on_write_error(
    monkeypatch, tmp_path, caplog
):
    from security.encryption import key_encryption

    monkeypatch.setattr(key_encryption, '_enabled', False)
    monkeypatch.setattr(
        'services.file_regen_service.os.open',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(PermissionError('denied')),
    )

    path = tmp_path / 'private' / 'certificate.key'
    assert mirror_private_key(path, KEY_PEM, context='test certificate') is False
    assert not path.exists()
    assert 'test certificate' in caplog.text


def test_purge_removes_keyed_and_orphan_files_but_keeps_keyless_rows(
    app, encryption_enabled, monkeypatch, tmp_path, caplog
):
    from models import AuditLog
    from config.settings import Config

    monkeypatch.setattr(Config, 'PRIVATE_DIR', tmp_path)
    keyed = Certificate(
        refid=str(uuid.uuid4()), descr='Keyed purge row', prv='stored-key'
    )
    keyless = Certificate(
        refid=str(uuid.uuid4()), descr='Keyless purge row', prv=None
    )

    with app.app_context():
        db.session.add_all([keyed, keyless])
        db.session.commit()
        keyed_id = keyed.id
        keyless_id = keyless.id
        keyed_path = cert_key_path(keyed)
        keyless_path = cert_key_path(keyless)
        orphan_path = tmp_path / 'cert_orphan.key'
        for path in (keyed_path, keyless_path, orphan_path):
            path.write_bytes(b'plaintext')

        stats = purge_private_key_files()

        assert stats == {'removed': 2, 'kept_no_db_key': 1, 'errors': 0}
        assert not keyed_path.exists()
        assert not orphan_path.exists()
        assert keyless_path.exists()
        assert 'database row has no key' in caplog.text
        assert AuditLog.query.filter_by(
            action='private_key_files_purged'
        ).count() >= 1

        keyless_path.unlink()
        Certificate.query.filter(Certificate.id.in_([keyed_id, keyless_id])).delete(
            synchronize_session=False
        )
        db.session.commit()


def test_regeneration_purges_keys_and_keeps_public_certificates(
    app, encryption_enabled, monkeypatch, tmp_path
):
    import base64

    from config.settings import Config
    from services.file_regen_service import regenerate_all_files

    monkeypatch.setattr(Config, 'PRIVATE_DIR', tmp_path / 'private')
    monkeypatch.setattr(Config, 'CERT_DIR', tmp_path / 'certs')
    monkeypatch.setattr(Config, 'CA_DIR', tmp_path / 'cas')
    monkeypatch.setattr(Config, 'CRL_DIR', tmp_path / 'crls')
    cert = Certificate(
        refid=str(uuid.uuid4()),
        descr='Startup purge row',
        subject='CN=startup.example.com',
        crt=base64.b64encode(b'public certificate').decode(),
        prv=base64.b64encode(KEY_PEM).decode(),
    )

    with app.app_context():
        db.session.add(cert)
        db.session.commit()
        cert_id = cert.id
        Config.PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
        cert_key_path(cert).write_bytes(b'plaintext')

        stats = regenerate_all_files()

        assert stats['keys_purged'] == 1
        assert stats['cert_keys'] == 0
        assert not cert_key_path(cert).exists()
        assert cert_cert_path(cert).read_bytes() == b'public certificate'

        cert_cert_path(cert).unlink()
        db.session.delete(db.session.get(Certificate, cert_id))
        db.session.commit()


def test_purge_is_noop_when_encryption_is_disabled(monkeypatch, tmp_path):
    from config.settings import Config
    from security.encryption import key_encryption

    monkeypatch.setattr(Config, 'PRIVATE_DIR', tmp_path)
    monkeypatch.setattr(key_encryption, '_enabled', False)
    path = tmp_path / 'cert_orphan.key'
    path.write_bytes(b'plaintext')

    assert purge_private_key_files() == {
        'removed': 0,
        'kept_no_db_key': 0,
        'errors': 0,
    }
    assert path.exists()


def test_purge_counts_unlink_errors(
    app, encryption_enabled, monkeypatch, tmp_path
):
    from config.settings import Config

    monkeypatch.setattr(Config, 'PRIVATE_DIR', tmp_path)
    path = tmp_path / 'cert_orphan.key'
    path.write_bytes(b'plaintext')
    real_unlink = type(path).unlink

    def fail_target(candidate, *args, **kwargs):
        if candidate == path:
            raise PermissionError('denied')
        return real_unlink(candidate, *args, **kwargs)

    monkeypatch.setattr(type(path), 'unlink', fail_target)
    with app.app_context():
        assert purge_private_key_files() == {
            'removed': 0,
            'kept_no_db_key': 0,
            'errors': 1,
        }


def _create_ca(auth_client, common_name):
    response = auth_client.post('/api/v2/cas', json={
        'type': 'root',
        'commonName': common_name,
        'organization': 'Mirror Tests',
        'country': 'US',
        'keyType': 'RSA',
        'keySize': 2048,
        'validityYears': 1,
        'hashAlgorithm': 'sha256',
    })
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    return response.get_json()['data']


def _cleanup_models(app, cert_ids=None, ca_id=None):
    from models import CRLMetadata, OCSPResponse, RevokedSerial

    cert_ids = [cert_ids] if isinstance(cert_ids, int) else (cert_ids or [])
    with app.app_context():
        db.session.rollback()
        if cert_ids:
            RevokedSerial.query.filter(
                RevokedSerial.certificate_id.in_(cert_ids)
            ).delete(synchronize_session=False)
        for cert_id in cert_ids:
            cert = db.session.get(Certificate, cert_id)
            if cert:
                cert_cert_path(cert).unlink(missing_ok=True)
                cert_key_path(cert).unlink(missing_ok=True)
                db.session.delete(cert)
        if ca_id:
            CRLMetadata.query.filter_by(ca_id=ca_id).delete(synchronize_session=False)
            OCSPResponse.query.filter_by(ca_id=ca_id).delete(synchronize_session=False)
            ca = db.session.get(CA, ca_id)
            if ca:
                ca_cert_path(ca).unlink(missing_ok=True)
                ca_key_path(ca).unlink(missing_ok=True)
                db.session.delete(ca)
        db.session.commit()


def test_api_creation_keeps_public_files_but_not_keys_when_encrypted(
    app, auth_client, encryption_enabled
):
    suffix = uuid.uuid4().hex[:10]
    ca_data = _create_ca(auth_client, f'Encrypted Mirror CA {suffix}')
    cert_id = None
    try:
        response = auth_client.post('/api/v2/certificates', json={
            'cn': f'encrypted-{suffix}.example.com',
            'ca_id': ca_data['id'],
            'validity_days': 30,
        })
        assert response.status_code in (200, 201), response.get_data(as_text=True)
        cert_id = response.get_json()['data']['id']

        with app.app_context():
            ca = db.session.get(CA, ca_data['id'])
            cert = db.session.get(Certificate, cert_id)
            assert ca_cert_path(ca).exists()
            assert not ca_key_path(ca).exists()
            assert cert_cert_path(cert).exists()
            assert not cert_key_path(cert).exists()
    finally:
        _cleanup_models(app, cert_id, ca_data['id'])


def test_renew_import_csr_and_restore_do_not_recreate_encrypted_key_mirrors(
    app, auth_client, encryption_enabled, tmp_path
):
    import base64

    from services.backup_service import BackupService
    from services.cert_service import CertificateService
    from utils.file_naming import cert_csr_path
    from utils.key_codec import load_pem_bytes

    suffix = uuid.uuid4().hex[:10]
    ca_data = _create_ca(auth_client, f'Encrypted Operations CA {suffix}')
    cert_ids = []
    try:
        response = auth_client.post('/api/v2/certificates', json={
            'cn': f'operations-{suffix}.example.com',
            'ca_id': ca_data['id'],
            'validity_days': 30,
        })
        assert response.status_code in (200, 201), response.get_data(as_text=True)
        cert_id = response.get_json()['data']['id']
        cert_ids.append(cert_id)

        renewal = auth_client.post(f'/api/v2/certificates/{cert_id}/renew', json={})
        assert renewal.status_code == 200, renewal.get_data(as_text=True)

        with app.app_context():
            cert = db.session.get(Certificate, cert_id)
            cert_pem = base64.b64decode(cert.crt).decode()
            key_pem = load_pem_bytes(
                cert.prv, context=f"certificate {cert.id}"
            ).decode()
            assert not cert_key_path(cert).exists()

            imported = CertificateService.import_certificate(
                f'Imported encrypted certificate {suffix}', cert_pem, key_pem
            )
            cert_ids.append(imported.id)
            # The ACME client stores its certificates through this call; the
            # key was written in the clear while encryption was enabled
            from security.encryption import key_encryption
            assert key_encryption.is_encrypted(imported.prv)
            assert load_pem_bytes(imported.prv).decode() == key_pem
            assert cert_cert_path(imported).exists()
            assert not cert_key_path(imported).exists()

            csr = CertificateService.generate_csr(
                f'Encrypted CSR {suffix}',
                {'CN': f'csr-{suffix}.example.com'},
            )
            cert_ids.append(csr.id)
            assert cert_csr_path(csr).exists()
            assert not cert_key_path(csr).exists()

            for item in (cert, imported, csr):
                cert_key_path(item).write_bytes(b'stale plaintext')
            # The certificate files are staged and published with the rest of
            # the restore now; the key mirrors are still a direct write, and
            # removing a stale one is what this checks.
            from services.backup.restore.files import StagedFiles
            with StagedFiles(base_dir=tmp_path / 'staging') as staged:
                BackupService()._regenerate_files(staged)
                staged.publish()
                staged.discard()
            assert all(not cert_key_path(item).exists() for item in (cert, imported, csr))
    finally:
        _cleanup_models(app, cert_ids, ca_data['id'])


def test_legacy_opnsense_import_skips_key_mirrors_when_encrypted(
    app, encryption_enabled, monkeypatch, tmp_path
):
    import base64

    from services.opnsense import importer

    fake_module = tmp_path / 'services' / 'opnsense' / 'importer.py'
    monkeypatch.setattr(importer, '__file__', str(fake_module))
    encoded_key = base64.b64encode(KEY_PEM).decode()
    encoded_cert = base64.b64encode(b'public certificate').decode()

    with app.app_context():
        ca_refid = str(uuid.uuid4())
        cert_refid = str(uuid.uuid4())
        ca_result = importer.ImportMixin().import_cas([{
            'refid': ca_refid,
            'descr': 'Legacy OPNsense encrypted CA',
            'crt': encoded_cert,
            'prv': encoded_key,
            'is_root': True,
        }])
        cert_result = importer.ImportMixin().import_certificates([{
            'refid': cert_refid,
            'descr': 'Legacy OPNsense encrypted certificate',
            'crt': encoded_cert,
            'prv': encoded_key,
        }])

        assert ca_result['imported'] == 1
        assert cert_result['imported'] == 1
        data_dir = tmp_path / 'data'
        assert (data_dir / 'ca' / f'{ca_refid}.crt').exists()
        assert (data_dir / 'certs' / f'{cert_refid}.crt').exists()
        assert not (data_dir / 'private' / f'{ca_refid}.key').exists()
        assert not (data_dir / 'private' / f'{cert_refid}.key').exists()

        CA.query.filter_by(refid=ca_refid).delete()
        Certificate.query.filter_by(refid=cert_refid).delete()
        db.session.commit()


def test_api_creation_keeps_key_mirrors_when_encryption_disabled(
    app, auth_client, monkeypatch
):
    from security.encryption import key_encryption

    monkeypatch.setattr(key_encryption, '_enabled', False)
    suffix = uuid.uuid4().hex[:10]
    ca_data = _create_ca(auth_client, f'Plain Mirror CA {suffix}')
    cert_id = None
    try:
        response = auth_client.post('/api/v2/certificates', json={
            'cn': f'plain-{suffix}.example.com',
            'ca_id': ca_data['id'],
            'validity_days': 30,
        })
        assert response.status_code in (200, 201), response.get_data(as_text=True)
        cert_id = response.get_json()['data']['id']

        with app.app_context():
            ca = db.session.get(CA, ca_data['id'])
            cert = db.session.get(Certificate, cert_id)
            assert ca_key_path(ca).exists()
            assert cert_key_path(cert).exists()
    finally:
        _cleanup_models(app, cert_id, ca_data['id'])
