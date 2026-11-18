"""An archive (2.254 or 3.0) whose trust store entry holds a private key is restored without the
key, with the warning and the audit entry of upgrade step 166."""
import datetime
import os
import uuid
from contextlib import contextmanager

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from models import AuditLog, db
from models.truststore import TrustedCertificate
from tests.test_backup_cross_installation import Keys, _installation
from tests.test_backup_hostile_corpus import PASSWORD, _forged, _service
from utils.trust_pem import REMOVED_ACTION

_PG_URL = os.environ.get('UCM_TEST_PG_URL')
ENGINES = ['sqlite', pytest.param('postgresql', marks=[
    pytest.mark.postgres, pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')])]


def _issue(cn):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=30)).sign(key, hashes.SHA256()))
    return (cert.public_bytes(serialization.Encoding.PEM).decode(),
            key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                              serialization.NoEncryption()).decode(),
            cert.fingerprint(hashes.SHA256()).hex())


@contextmanager
def _database(engine, tmp_path):
    if engine == 'sqlite':
        yield f"sqlite:///{tmp_path / 'trust-restore.db'}"
        return
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own
    with _a_schema_of_our_own(f'trust_restore_{uuid.uuid4().hex[:6]}') as url:
        yield url


@pytest.fixture(params=ENGINES)
def here(app, tmp_path, request):
    """A separate installation the archive is restored into."""
    with _database(request.param, tmp_path) as url, \
            _installation(app, url, Keys(tmp_path, 'trust'), is_postgresql=request.param != 'sqlite'), \
            app.app_context():
        yield
        db.session.rollback()


@pytest.mark.parametrize('archive', ['2.254', '3.0'])
def test_an_archived_entry_holding_a_key_is_restored_without_it(here, caplog, archive):
    keyed, key, keyed_fp = _issue('archived-with-key')
    clean, _, clean_fp = _issue('archived-clean')

    def entries(data):
        data['trusted_certificates'] = [
            {'name': 'server.pem', 'certificate_pem': key + keyed, 'fingerprint_sha256': keyed_fp,
             'purpose': 'custom'},
            {'name': 'clean', 'certificate_pem': clean, 'fingerprint_sha256': clean_fp, 'purpose': 'custom'},
        ]
        if archive == '3.0':
            data['windows_enrollment_profiles'] = []
        else:
            data.pop('windows_enrollment_profiles', None)

    blob = _forged(['trusted_certificates'], mutate=entries)
    before = db.session.query(db.func.max(AuditLog.id)).scalar() or 0
    with caplog.at_level('WARNING'):
        results = _service().restore_backup(blob, PASSWORD, mode='merge')
    db.session.expire_all()
    stored = {r.fingerprint_sha256: r for r in TrustedCertificate.query.all()}
    assert stored[keyed_fp].certificate_pem == keyed
    assert stored[clean_fp].certificate_pem == clean
    assert [e['fingerprint_sha256'] for e in results['truststore_private_keys_removed']] == [keyed_fp]
    warned = [m for m in caplog.messages if 'held a private key' in m]
    assert warned and all(keyed_fp in m for m in warned)
    body = key.splitlines()[1]
    assert not any(body in m for m in caplog.messages) and body not in str(results)
    (entry,) = AuditLog.query.filter(AuditLog.id > before, AuditLog.action == REMOVED_ACTION).all()
    assert entry.resource_id == str(stored[keyed_fp].id) and keyed_fp in entry.details
