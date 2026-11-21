"""The Intune success notification runs without the CA row lock on PostgreSQL.

The issuance count locks the CA row until the commit; counting before the call to
Intune would stall every issuance under that CA while Intune answers.
"""
import base64
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from models import CA, Certificate, db
from services.scep.scep_service import SCEPService
from tests.test_scep_rfc8894_operations import (
    PKI_STATUS_OID, _build_request, _client_identity, _load_ca_material, _response_attributes,
)

_PG_URL = os.environ.get('UCM_TEST_PG_URL')


def _rsa_ca():
    from utils.key_codec import store_pem_bytes
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Intune lock CA')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
                           critical=False)
            .sign(key, hashes.SHA256()))
    refid = str(uuid.uuid4())
    ca = CA(refid=refid, descr='Intune lock CA', url_slug=refid,
            crt=base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode(),
            prv=store_pem_bytes(key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption())),
            subject=cert.subject.rfc4514_string(), issuer=cert.issuer.rfc4514_string(),
            serial_number=format(cert.serial_number, 'x'),
            valid_from=cert.not_valid_before_utc.replace(tzinfo=None),
            valid_to=cert.not_valid_after_utc.replace(tzinfo=None))
    db.session.add(ca)
    db.session.commit()
    return ca.id


class _ProbingIntune:
    """Answers Intune's calls and, on the success notice, tries the CA row from another connection."""

    def __init__(self, engine, ca_id):
        self.engine, self.ca_id, self.lock_free = engine, ca_id, []

    def validate_request(self, transaction_id, csr_data):
        return True

    def send_success_notification(self, transaction_id, csr_data, cert):
        with self.engine.connect() as other:
            try:
                other.execute(text('SELECT id FROM certificate_authorities WHERE id = :id '
                                   'FOR NO KEY UPDATE NOWAIT'), {'id': self.ca_id})
                self.lock_free.append(True)
            except OperationalError:
                self.lock_free.append(False)
            other.rollback()

    def send_failure_notification(self, *args, **kwargs):
        pass


def _request(ca_cert, cn):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
           .sign(key, hashes.SHA256()))
    signer_cert, _ = _client_identity(key=key)
    return _build_request(ca_cert, signer_cert, key, 19,
                          csr.public_bytes(serialization.Encoding.DER), os.urandom(16))


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
def test_intune_notice_runs_without_the_ca_row_lock(app):
    from tests.test_backup_cross_installation import _bound_to
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own

    with _a_schema_of_our_own(f'scep_intune_lock_{uuid.uuid4().hex[:6]}') as url, \
            _bound_to(app, url, is_postgresql=True) as engine, app.app_context():
        # The test requests share one transactionID: one CA per path
        for auto_approve in (True, False):
            ca_id = _rsa_ca()
            ca, ca_cert, _ = _load_ca_material(ca_id)
            intune = _ProbingIntune(engine, ca_id)
            _issue_through(ca, ca_cert, intune, auto_approve)
            assert intune.lock_free == [True]
            db.session.expire_all()
            assert (db.session.get(CA, ca_id).serial,
                    Certificate.query.filter_by(caref=ca.refid).count()) == (1, 1)
        db.session.remove()


def _issue_through(ca, ca_cert, intune, auto_approve):
    if auto_approve:
        # Auto-approval: the notice precedes the commit of the issuance
        response, status = SCEPService(ca.refid, auto_approve=True, intune_client=intune) \
            .process_pkcs_req(_request(ca_cert, 'auto.example'), '127.0.0.1')
        assert status == 200 and _response_attributes(response)[PKI_STATUS_OID] == '0'
        return
    # Approval of a pending request: the same notice before the commit
    response, _ = SCEPService(ca.refid, intune_client=intune) \
        .process_pkcs_req(_request(ca_cert, 'pending.example'), '127.0.0.1')
    assert _response_attributes(response)[PKI_STATUS_OID] == '3'
    from models import SCEPRequest
    pending = SCEPRequest.query.filter_by(ca_refid=ca.refid, status='pending').one()
    assert SCEPService(ca.refid, intune_client=intune).approve_request(
        pending.transaction_id, 'admin')
