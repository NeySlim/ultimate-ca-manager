"""What the administration route writes into the file gunicorn reads.

Applying a managed certificate to HTTPS exists twice: the route under
`/api/v2/system/https/apply`, and `services/https_binding.materialize_https_cert`,
which the renewal subscriber calls. The second decrypts the stored private key
through `load_pem_bytes`; the first only base64-decoded it.

On an installation with a key-encryption key, the column holds
`base64("ENC:" + token)`, so decoding it yields `ENC:gAAAAA…` and that is what
went into `https_key.pem`, in 0600, over a backup of the working one, followed
by a restart. The answer was 200 and the service did not come back.
"""
import base64

import pytest

from models import db


@pytest.fixture
def https_paths(tmp_path, monkeypatch):
    cert_path = tmp_path / 'https_cert.pem'
    key_path = tmp_path / 'https_key.pem'
    monkeypatch.setenv('HTTPS_CERT_PATH', str(cert_path))
    monkeypatch.setenv('HTTPS_KEY_PATH', str(key_path))
    return cert_path, key_path


@pytest.fixture
def no_restart(monkeypatch):
    """The route asks for a restart; the test is about what it wrote first."""
    import api.v2.system.https as route

    monkeypatch.setattr(route, 'restart_service', lambda *a, **k: True,
                        raising=False)


@pytest.fixture
def encrypted_certificate(app):
    """A certificate whose stored key is written the way the product writes
    it: `store_pem_bytes`, which is base64 then the key-encryption layer, so
    the column holds `base64("ENC:" + token)`. Its reader is `load_pem_bytes`,
    and pairing anything else with it is how this defect looks from the
    inside."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from security.encryption import key_encryption
    from utils.key_codec import store_pem_bytes
    from models import CA, Certificate
    from utils.datetime_utils import utc_now
    from datetime import timedelta

    with app.app_context():
        if not key_encryption.is_enabled:
            pytest.skip('at-rest key encryption is off on this installation')

        key = ec.generate_private_key(ec.SECP256R1())
        pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption())

        authority = CA.query.first()
        cert = Certificate(
            refid='https-apply-material', descr='https apply material',
            caref=authority.refid if authority else None,
            crt=base64.b64encode(b'-----BEGIN CERTIFICATE-----\nx\n'
                                 b'-----END CERTIFICATE-----\n').decode(),
            prv=store_pem_bytes(pem),
            subject_cn='https-apply.example.test',
            valid_from=utc_now(), valid_to=utc_now() + timedelta(days=30))
        db.session.add(cert)
        db.session.commit()
        yield cert.id, pem

        db.session.delete(db.session.get(Certificate, cert.id))
        db.session.commit()


class TestTheKeyOnDiskIsAKey:
    def test_the_route_writes_the_decrypted_key(
            self, app, auth_client, https_paths, no_restart,
            encrypted_certificate):
        cert_path, key_path = https_paths
        cert_id, pem = encrypted_certificate

        with app.app_context():
            from models import Certificate
            stored = db.session.get(Certificate, cert_id).prv
            assert not stored.startswith('-----BEGIN'), (
                'the fixture must store the key the way the product does')

        response = auth_client.post('/api/v2/system/https/apply',
                                    json={'cert_id': cert_id})
        assert response.status_code == 200, response.data

        written = key_path.read_text()
        assert not written.startswith('ENC:'), (
            'the ciphertext was written into the file gunicorn reads as the '
            'private key: HTTPS cannot come back up')
        assert written.strip() == pem.decode().strip(), (
            'the file does not hold the key of the certificate that was applied')


class TestAColumnHoldingThePemItself:
    """A row from before the key was stored base64-encoded.

    `load_pem_bytes` hands such a value to the base64 decoder, which decodes
    the body of the PEM into bytes that are not a key and does not raise, so
    the previous version's explicit tolerance for it is kept rather than
    traded for a silent corruption of the same kind this lot is about.
    """

    def test_the_route_writes_it_unchanged(self, app, auth_client,
                                           https_paths, no_restart):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from models import CA, Certificate
        from utils.datetime_utils import utc_now
        from datetime import timedelta
        import base64 as b64

        _cert_path, key_path = https_paths
        key = ec.generate_private_key(ec.SECP256R1())
        pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()).decode()

        with app.app_context():
            authority = CA.query.first()
            cert = Certificate(
                refid='https-apply-legacy-pem', descr='https apply legacy pem',
                caref=authority.refid if authority else None,
                crt=b64.b64encode(b'-----BEGIN CERTIFICATE-----\nx\n'
                                  b'-----END CERTIFICATE-----\n').decode(),
                prv=pem,
                subject_cn='https-legacy.example.test',
                valid_from=utc_now(), valid_to=utc_now() + timedelta(days=30))
            db.session.add(cert)
            db.session.commit()
            cert_id = cert.id

        try:
            response = auth_client.post('/api/v2/system/https/apply',
                                        json={'cert_id': cert_id})
            assert response.status_code == 200, response.data
            assert key_path.read_text().strip() == pem.strip(), (
                'a column holding the PEM itself came out of the base64 '
                'decoder as something that is not a key')
        finally:
            with app.app_context():
                row = db.session.get(Certificate, cert_id)
                if row is not None:
                    db.session.delete(row)
                    db.session.commit()


class TestOnlyAUsableCertificateIsApplied:
    """The picker filters, the route must too: nothing is written for a
    certificate that clients would refuse."""

    @pytest.fixture
    def plain_certificate(self, app):
        from datetime import timedelta
        from models import Certificate
        from utils.datetime_utils import utc_now

        with app.app_context():
            cert = Certificate(
                refid='https-apply-state', descr='https apply state',
                crt=base64.b64encode(b'-----BEGIN CERTIFICATE-----\nx\n'
                                     b'-----END CERTIFICATE-----\n').decode(),
                prv='unused', subject_cn='https-state.example.test',
                valid_from=utc_now() - timedelta(days=40),
                valid_to=utc_now() + timedelta(days=5))
            db.session.add(cert)
            db.session.commit()
            cert_id = cert.id
        yield cert_id
        with app.app_context():
            row = db.session.get(Certificate, cert_id)
            if row:
                db.session.delete(row)
                db.session.commit()

    @pytest.mark.parametrize('change, message', [
        ({'revoked': True}, 'revoked'),
        ({'valid_to_days': -1}, 'expired'),
        ({'crt': None}, 'not been issued'),
    ])
    def test_refused_and_nothing_written(self, app, auth_client, https_paths, no_restart,
                                         plain_certificate, change, message):
        from datetime import timedelta
        from models import Certificate
        from utils.datetime_utils import utc_now

        cert_path, key_path = https_paths
        with app.app_context():
            row = db.session.get(Certificate, plain_certificate)
            if 'revoked' in change:
                row.revoked = True
            if 'valid_to_days' in change:
                row.valid_to = utc_now() + timedelta(days=change['valid_to_days'])
            if 'crt' in change:
                row.crt = None
            db.session.commit()
        response = auth_client.post('/api/v2/system/https/apply', json={'cert_id': plain_certificate})
        assert response.status_code == 400
        assert message in response.get_json()['message']
        assert not cert_path.exists() and not key_path.exists()


class TestBackupOfALoneKeyFile:
    def test_apply_with_only_a_key_file_on_disk(self, app, auth_client, https_paths, no_restart):
        """The backup suffix was set only when the certificate file existed."""
        from datetime import timedelta
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import NameOID
        from models import Certificate
        from utils.datetime_utils import utc_now
        from utils.key_codec import store_pem_bytes

        cert_path, key_path = https_paths
        key_path.write_text('old key')
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'lone-key.example.test')])
        now = utc_now()
        crt = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
               .public_key(key.public_key()).serial_number(x509.random_serial_number())
               .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=20))
               .sign(key, hashes.SHA256()))
        with app.app_context():
            row = Certificate(
                refid='https-lone-key', descr='https lone key', subject_cn='lone-key.example.test',
                crt=base64.b64encode(crt.public_bytes(serialization.Encoding.PEM)).decode(),
                prv=store_pem_bytes(key.private_bytes(serialization.Encoding.PEM,
                                                      serialization.PrivateFormat.PKCS8,
                                                      serialization.NoEncryption())),
                valid_from=now - timedelta(days=1), valid_to=now + timedelta(days=20))
            db.session.add(row)
            db.session.commit()
            cert_id = row.id
        try:
            response = auth_client.post('/api/v2/system/https/apply', json={'cert_id': cert_id})
            assert response.status_code == 200, response.data
            assert list(key_path.parent.glob('https_key.pem.backup-*'))
        finally:
            with app.app_context():
                db.session.delete(db.session.get(Certificate, cert_id))
                db.session.commit()
