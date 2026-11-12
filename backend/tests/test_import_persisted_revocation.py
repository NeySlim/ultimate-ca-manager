"""A certificate its CA revoked comes back revoked when imported again, on every
import path, and the persistent record alone is enough to refuse its renewal.

The revocation record outlives the certificate row: OCSP and the CRL keep
answering "revoked" for the serial, and the row an import creates must agree.
"""
import base64
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes

from models import CA, Certificate, RevokedSerial, db
from tests.test_import_issuer_signature import _gen, _import, _leaf, _pem, _store

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')

REVOKED_AT = datetime(2026, 1, 2, 3, 4, 5)


@pytest.fixture(scope='module')
def issuer(app, create_ca):
    data = create_ca(cn=f'Persisted Revocation CA {uuid.uuid4().hex[:6]}',
                     keyUsage=['digitalSignature', 'keyCertSign', 'cRLSign'])
    with app.app_context():
        from services.hsm.ca_key_loader import get_ca_signing_key
        row = db.session.get(CA, data['id'])
        cert = x509.load_pem_x509_certificate(base64.b64decode(row.crt))
        return row.id, row.refid, cert, get_ca_signing_key(row)


def _record(app, refid, cert, reason='keyCompromise'):
    """The record a revocation leaves once its certificate row is deleted."""
    with app.app_context():
        db.session.add(RevokedSerial(caref=refid, serial_number=str(cert.serial_number),
                                     revoked_at=REVOKED_AT, revoke_reason=reason,
                                     valid_to=cert.not_valid_after_utc.replace(tzinfo=None)))
        db.session.commit()


def _states(app, cert):
    with app.app_context():
        db.session.expire_all()
        return [(r.caref, bool(r.revoked), r.revoke_reason, r.revoked_at)
                for r in Certificate.query.filter_by(serial_number=str(cert.serial_number)).all()]


def _revoked_under(refid, reason='keyCompromise'):
    return [(refid, True, reason, REVOKED_AT)]


class TestAnImportAppliesThePersistedRevocation:

    def test_the_import_route_after_revoke_and_delete(self, app, auth_client, issuer):
        _, refid, ca_cert, ca_key = issuer
        real, key = _leaf('reimported-route.example.test', ca_cert, ca_key)
        row_id = _store(app, real, refid)
        r = auth_client.post(f'/api/v2/certificates/{row_id}/revoke', json={'reason': 'keyCompromise'})
        assert r.status_code == 200, r.data
        with app.app_context():
            record = RevokedSerial.query.filter_by(caref=refid, serial_number=str(real.serial_number)).one()
            expected = (refid, True, 'keyCompromise', record.revoked_at)
        assert auth_client.delete(f'/api/v2/certificates/{row_id}').status_code in (200, 204)
        assert _import(auth_client, real, key).status_code in (200, 201)
        assert _states(app, real) == [expected]

    def test_a_hold_carried_by_the_import_can_be_lifted(self, app, auth_client, issuer):
        from services.ocsp_service import OCSPService
        ca_id, refid, ca_cert, ca_key = issuer
        real, key = _leaf('reimported-held.example.test', ca_cert, ca_key)
        _record(app, refid, real, reason='certificateHold')
        assert _import(auth_client, real, key).status_code in (200, 201)
        assert _states(app, real) == _revoked_under(refid, 'certificateHold')
        with app.app_context():
            row_id = Certificate.query.filter_by(serial_number=str(real.serial_number)).one().id
        r = auth_client.post(f'/api/v2/certificates/{row_id}/unhold')
        assert r.status_code == 200, r.data
        assert _states(app, real) == [(refid, False, None, None)]
        with app.app_context():
            assert OCSPService._status_for_serial(db.session.get(CA, ca_id), real.serial_number)[1] == 'good'

    def test_the_import_route_with_a_named_ca(self, app, auth_client, issuer):
        ca_id, refid, ca_cert, ca_key = issuer
        real, _ = _leaf('reimported-named.example.test', ca_cert, ca_key)
        _record(app, refid, real)
        assert _import(auth_client, real, ca_id=str(ca_id)).status_code in (200, 201)
        assert _states(app, real) == _revoked_under(refid)

    def test_the_update_of_a_stored_duplicate(self, app, auth_client, issuer):
        _, refid, ca_cert, ca_key = issuer
        current, key = _leaf('reimported-duplicate.example.test', ca_cert, ca_key)
        row_id = _store(app, current, refid, key=key)
        revoked, _ = _leaf('reimported-duplicate.example.test', ca_cert, ca_key, key=key)
        _record(app, refid, revoked)
        r = _import(auth_client, revoked)
        assert r.status_code == 200, r.data
        with app.app_context():
            assert db.session.get(Certificate, row_id).serial_number == str(revoked.serial_number)
        assert _states(app, revoked) == _revoked_under(refid)

    def test_a_pending_request_completed_by_the_revoked_certificate(self, app, auth_client, issuer):
        from tests.test_csr_external_certificate import _create_csr, _csr_pem
        _, refid, ca_cert, ca_key = issuer
        request_id = _create_csr(auth_client, 'reimported-pending.example.test')['id']
        csr = x509.load_pem_x509_csr(_csr_pem(auth_client, request_id))
        ski = ca_cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value
        now = datetime.now(timezone.utc)
        answer = (x509.CertificateBuilder().subject_name(csr.subject).issuer_name(ca_cert.subject)
                  .public_key(csr.public_key()).serial_number(x509.random_serial_number())
                  .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=30))
                  .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                  .add_extension(x509.AuthorityKeyIdentifier(ski.digest, None, None), critical=False)
                  .sign(ca_key, hashes.SHA256()))
        _record(app, refid, answer)
        assert _import(auth_client, answer).status_code in (200, 201)
        with app.app_context():
            assert db.session.get(Certificate, request_id).serial_number == str(answer.serial_number)
        assert _states(app, answer) == _revoked_under(refid)

    def test_the_bulk_import(self, app, auth_client, issuer):
        _, refid, ca_cert, ca_key = issuer
        real, _ = _leaf('reimported-bulk.example.test', ca_cert, ca_key)
        _record(app, refid, real)
        r = auth_client.post('/api/v2/import/execute', data=json.dumps({
            'content': _pem(real), 'options': {'skip_duplicates': False}}),
            content_type='application/json')
        assert r.status_code == 200, r.data
        assert _states(app, real) == _revoked_under(refid)

    def test_the_opnsense_import_route(self, app, auth_client, issuer, monkeypatch):
        from api.v2 import import_opnsense
        from tests.test_opnsense_import import _Session
        _, refid, ca_cert, ca_key = issuer
        real, _ = _leaf('reimported-opn.example.test', ca_cert, ca_key)
        _record(app, refid, real)
        rows = [{'uuid': str(uuid.uuid4()), 'refid': uuid.uuid4().hex[:13], 'descr': f'opn-revoked-{refid}',
                 'crt': base64.b64encode(_pem(real).encode()).decode(), 'caref': refid}]
        monkeypatch.setattr(import_opnsense, 'create_session', lambda verify_ssl=True: _Session([], rows))
        r = auth_client.post('/api/v2/import/opnsense/import', json={
            'host': '192.0.2.10', 'port': 443, 'api_key': 'k', 'api_secret': 's',
            'verify_ssl': False, 'items': []})
        assert r.status_code == 200, r.data
        assert _states(app, real) == _revoked_under(refid)

    def test_the_legacy_opnsense_service(self, app, issuer, monkeypatch, tmp_path):
        from services.opnsense import importer
        monkeypatch.setattr(importer, '__file__', str(tmp_path / 'services' / 'opnsense' / 'importer.py'))
        _, refid, ca_cert, ca_key = issuer
        real, _ = _leaf('reimported-legacy.example.test', ca_cert, ca_key)
        _record(app, refid, real)
        entries = [{'refid': uuid.uuid4().hex[:13], 'caref': refid, 'descr': 'legacy revoked',
                    'crt': base64.b64encode(_pem(real).encode()).decode(),
                    'serial_number': str(real.serial_number)}]
        with app.app_context():
            assert importer.ImportMixin().import_certificates(entries)['imported'] == 1
        assert _states(app, real) == _revoked_under(refid)

    def test_an_admin_mtls_import(self, app, auth_client, issuer):
        _, refid, ca_cert, ca_key = issuer
        real, _ = _leaf('reimported-mtls.example.test', ca_cert, ca_key)
        _record(app, refid, real)
        with app.app_context():
            from models import User
            admin_id = User.query.filter_by(username='admin').first().id
        try:
            r = auth_client.post(f'/api/v2/users/{admin_id}/mtls/certificates',
                                 json={'mode': 'import', 'pem': _pem(real)})
            assert r.status_code in (200, 201), r.data
            assert _states(app, real) == _revoked_under(refid)
        finally:
            from models.auth_certificate import AuthCertificate
            with app.app_context():
                AuthCertificate.query.filter_by(cert_serial=str(real.serial_number)).delete()
                db.session.commit()


class TestAnImportWithoutAPersistedRevocationIsUnchanged:
    """Non-regression: these pass with or without the fix, they are not proofs of it."""

    def test_a_hold_lifted_before_the_row_went(self, app, auth_client, issuer):
        """A valid certificate cannot be deleted through the API: its row is dropped directly."""
        _, refid, ca_cert, ca_key = issuer
        real, key = _leaf('reimported-unheld.example.test', ca_cert, ca_key)
        row_id = _store(app, real, refid)
        assert auth_client.post(f'/api/v2/certificates/{row_id}/revoke',
                                json={'reason': 'certificateHold'}).status_code == 200
        assert auth_client.post(f'/api/v2/certificates/{row_id}/unhold').status_code == 200
        with app.app_context():
            db.session.delete(db.session.get(Certificate, row_id))
            db.session.commit()
        assert _import(auth_client, real, key).status_code in (200, 201)
        assert _states(app, real) == [(refid, False, None, None)]

    def test_a_certificate_never_revoked(self, app, auth_client, issuer):
        _, refid, ca_cert, ca_key = issuer
        real, _ = _leaf('never-revoked.example.test', ca_cert, ca_key)
        assert _import(auth_client, real).status_code in (200, 201)
        assert _states(app, real) == [(refid, False, None, None)]

    def test_a_third_party_certificate_without_a_ca(self, app, auth_client, issuer):
        """A record of the same serial under a CA that did not sign it does not reach it."""
        _, refid, ca_cert, _ = issuer
        elsewhere, _ = _leaf('third-party-revoked.example.test', ca_cert, _gen())
        _record(app, refid, elsewhere)
        assert _import(auth_client, elsewhere).status_code in (200, 201)
        assert _states(app, elsewhere) == [(None, False, None, None)]


class TestARenewalRefusesAPersistedRevocation:
    """A row left unrevoked beside the record of its serial (stored by an earlier release)."""

    def test_the_renewability_check_refuses_it(self, app, issuer):
        from services.cert.renewal import RenewalError, check_renewable
        _, refid, ca_cert, ca_key = issuer
        real, key = _leaf('unrevoked-row-check.example.test', ca_cert, ca_key)
        row_id = _store(app, real, refid, key=key)
        _record(app, refid, real)
        with app.app_context():
            with pytest.raises(RenewalError) as e:
                check_renewable(db.session.get(Certificate, row_id))
            assert e.value.status == 409 and 'revoked' in e.value.message

    def test_the_renew_route_refuses_it(self, app, auth_client, issuer):
        _, refid, ca_cert, ca_key = issuer
        real, key = _leaf('unrevoked-row-route.example.test', ca_cert, ca_key)
        row_id = _store(app, real, refid, key=key)
        _record(app, refid, real)
        r = auth_client.post(f'/api/v2/certificates/{row_id}/renew', json={})
        assert r.status_code == 409, r.data
        with app.app_context():
            assert db.session.get(Certificate, row_id).serial_number == str(real.serial_number)

    def test_a_row_without_a_ca_link_is_refused_under_the_ca_that_signed_it(self, app, issuer):
        from services.cert.renewal import RenewalError, renew_certificate_in_place
        _, refid, ca_cert, ca_key = issuer
        real, key = _leaf('unrevoked-row-unlinked.example.test', ca_cert, ca_key)
        row_id = _store(app, real, None, key=key)
        _record(app, refid, real)
        with app.app_context():
            with pytest.raises(RenewalError) as e:
                renew_certificate_in_place(db.session.get(Certificate, row_id))
            assert e.value.status == 409 and 'revoked' in e.value.message
            db.session.expire_all()
            assert db.session.get(Certificate, row_id).serial_number == str(real.serial_number)

    def test_protocol_renewals_already_answer_revoked(self, app, issuer):
        """Non-regression: issued_certificate_status read the record before this fix."""
        from services.cert.issued_lookup import REVOKED, issued_certificate_status
        ca_id, refid, ca_cert, ca_key = issuer
        real, key = _leaf('unrevoked-row-protocol.example.test', ca_cert, ca_key)
        _store(app, real, refid, key=key)
        _record(app, refid, real)
        with app.app_context():
            assert issued_certificate_status(db.session.get(CA, ca_id), real)[1] == REVOKED
