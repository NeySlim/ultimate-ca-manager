"""One rule for the revocation record of a serial: a ``RevokedSerial`` of the CA's key
(or a record of the same key) for the serial, in any spelling, says revoked; lifting a
suspension deletes it. Every surface reads it through ``persisted_revocation``."""
import base64
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from models import CA, Certificate, RevokedSerial, db
from tests.test_import_issuer_signature import _import, _leaf, _pem, _store

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')

EARLY = datetime(2026, 1, 2, 3, 4, 5)
LATER = datetime(2026, 2, 3, 4, 5, 6)


@pytest.fixture(scope='module')
def issuer(app, create_ca):
    data = create_ca(cn=f'Record Rule CA {uuid.uuid4().hex[:6]}',
                     keyUsage=['digitalSignature', 'keyCertSign', 'cRLSign'])
    with app.app_context():
        from services.hsm.ca_key_loader import get_ca_signing_key
        row = db.session.get(CA, data['id'])
        cert = x509.load_pem_x509_certificate(base64.b64decode(row.crt))
        return row.id, row.refid, cert, get_ca_signing_key(row)


@pytest.fixture
def twin(app, issuer):
    """A second record of the issuer's subject and key (a re-signed root), dropped afterwards."""
    ca_id, _, ca_cert, ca_key = issuer
    now = datetime.now(timezone.utc)
    again = (x509.CertificateBuilder().subject_name(ca_cert.subject).issuer_name(ca_cert.subject)
             .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
             .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=365))
             .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
             .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
             .sign(ca_key, hashes.SHA256()))
    with app.app_context():
        original = db.session.get(CA, ca_id)
        row = CA(refid=str(uuid.uuid4()), descr='twin record', serial=0, prv=original.prv,
                 crt=base64.b64encode(again.public_bytes(serialization.Encoding.PEM)).decode(),
                 subject=original.subject, issuer=original.issuer)
        db.session.add(row)
        db.session.commit()
        refid = row.id, row.refid
    yield refid
    from services.ca_service import CAService
    from services.cert_service import CertificateService
    with app.app_context():
        for row_id in [r.id for r in Certificate.query.filter_by(caref=refid[1])]:
            CertificateService.delete_certificate(row_id)
        CAService.delete_ca(refid[0])


def _record(app, caref, cert, *, reason='keyCompromise', at=EARLY, column=None, certificate_id=None):
    with app.app_context():
        record = RevokedSerial(caref=caref, serial_number=column or str(cert.serial_number),
                               revoked_at=at, revoke_reason=reason, certificate_id=certificate_id,
                               valid_to=cert.not_valid_after_utc.replace(tzinfo=None))
        db.session.add(record)
        db.session.commit()
        return record.id


def _row(app, row_id):
    with app.app_context():
        db.session.expire_all()
        row = db.session.get(Certificate, row_id)
        return bool(row.revoked), row.revoke_reason, row.revoked_at


def _surfaces(app, ca_id, cert):
    """(OCSP status, OCSP reason, CRL entry reason or None, issued status)."""
    from services.cert.issued_lookup import issued_certificate_status
    from services.crl_service import CRLService
    from services.ocsp_service import OCSPService
    with app.app_context():
        db.session.expire_all()
        ca = db.session.get(CA, ca_id)
        _, ocsp_status, _, ocsp_reason = OCSPService._status_for_serial(ca, cert.serial_number)
        crl = x509.load_pem_x509_crl(CRLService.generate_crl(ca_id).crl_pem.encode())
        entry = crl.get_revoked_certificate_by_serial_number(cert.serial_number)
        crl_reason = None
        if entry is not None:
            try:
                crl_reason = entry.extensions.get_extension_for_class(x509.CRLReason).value.reason
            except x509.ExtensionNotFound:
                crl_reason = x509.ReasonFlags.unspecified
        return ocsp_status, ocsp_reason, crl_reason, issued_certificate_status(ca, cert)[1]


KEY_COMPROMISED = ('revoked', x509.ReasonFlags.key_compromise, x509.ReasonFlags.key_compromise, 'revoked')


def _renewal_refused(app, row_id):
    from services.cert.renewal import RenewalError, check_renewable
    with app.app_context():
        with pytest.raises(RenewalError) as e:
            check_renewable(db.session.get(Certificate, row_id))
        return e.value.status


class TestAHomonymImportNeverLiftsARevocation:
    """A revoked row updated by a namesake, then by the revoked certificate again."""

    def _revoked_then_replaced(self, app, auth_client, issuer, cn):
        _, refid, ca_cert, ca_key = issuer
        real, key = _leaf(cn, ca_cert, ca_key)
        row_id = _store(app, real, refid, key=key)
        assert auth_client.post(f'/api/v2/certificates/{row_id}/revoke',
                                json={'reason': 'keyCompromise'}).status_code == 200
        with app.app_context():
            revoked_at = db.session.get(Certificate, row_id).revoked_at
        namesake, _ = _leaf(cn, ca_cert, ca_key)
        r = _import(auth_client, namesake)
        assert r.status_code == 200, r.data
        assert r.get_json()['data']['id'] == row_id
        return real, key, row_id, revoked_at

    def test_the_record_of_the_replaced_serial_is_unlinked_and_kept(self, app, auth_client, issuer):
        _, refid, _, _ = issuer
        real, _, row_id, revoked_at = self._revoked_then_replaced(
            app, auth_client, issuer, 'homonym-unlinked.example.test')
        with app.app_context():
            record = RevokedSerial.query.filter_by(caref=refid, serial_number=str(real.serial_number)).one()
            assert (record.certificate_id, record.revoke_reason, record.revoked_at) == (
                None, 'keyCompromise', revoked_at)

    def test_the_revoked_certificate_imported_again_answers_revoked_everywhere(
            self, app, auth_client, issuer):
        ca_id, _, _, _ = issuer
        real, key, row_id, revoked_at = self._revoked_then_replaced(
            app, auth_client, issuer, 'homonym-everywhere.example.test')
        r = _import(auth_client, real, key)
        assert r.status_code == 200, r.data
        assert r.get_json()['data']['id'] == row_id
        assert _row(app, row_id) == (True, 'keyCompromise', revoked_at)
        assert _surfaces(app, ca_id, real) == KEY_COMPROMISED
        assert _renewal_refused(app, row_id) == 409
        assert auth_client.post(f'/api/v2/certificates/{row_id}/renew', json={}).status_code == 409
        assert _row(app, row_id) == (True, 'keyCompromise', revoked_at)


class TestARecordLinkedToTheLiveRowStillRevokes:
    """A record linked to a row that is not revoked is not a lifted revocation."""

    def test_every_surface_answers_revoked(self, app, issuer):
        ca_id, refid, ca_cert, ca_key = issuer
        real, key = _leaf('linked-live.example.test', ca_cert, ca_key)
        row_id = _store(app, real, refid, key=key)
        _record(app, refid, real, certificate_id=row_id)
        assert _surfaces(app, ca_id, real) == KEY_COMPROMISED
        assert _renewal_refused(app, row_id) == 409

    def test_the_import_applies_it(self, app, auth_client, issuer):
        _, refid, ca_cert, ca_key = issuer
        real, key = _leaf('linked-import.example.test', ca_cert, ca_key)
        row_id = _store(app, real, refid, key=key)
        _record(app, refid, real, certificate_id=row_id)
        assert _import(auth_client, real, key).status_code == 200
        assert _row(app, row_id) == (True, 'keyCompromise', EARLY)


class TestTheGravestRecordWins:

    def test_a_compromise_outranks_an_earlier_hold_of_a_twin(self, app, auth_client, issuer, twin):
        ca_id, refid, ca_cert, ca_key = issuer
        real, key = _leaf('gravest.example.test', ca_cert, ca_key)
        _record(app, twin[1], real, reason='certificateHold', at=EARLY)
        _record(app, refid, real, reason='keyCompromise', at=LATER)
        from services.cert.issued_lookup import persisted_revocation
        with app.app_context():
            record = persisted_revocation(db.session.get(CA, ca_id), real.serial_number)
            assert (record.revoke_reason, record.revoked_at) == ('keyCompromise', LATER)
        assert _surfaces(app, ca_id, real) == KEY_COMPROMISED
        assert _import(auth_client, real, key).status_code in (200, 201)
        with app.app_context():
            row_id = Certificate.query.filter_by(serial_number=str(real.serial_number)).one().id
        assert _row(app, row_id) == (True, 'keyCompromise', LATER)

    def test_between_equal_reasons_the_earliest_date(self, app, issuer, twin):
        """Non-regression: the earliest record already won before the fix."""
        ca_id, refid, ca_cert, ca_key = issuer
        real, _ = _leaf('earliest.example.test', ca_cert, ca_key)
        _record(app, refid, real, reason='unspecified', at=LATER)
        _record(app, twin[1], real, reason='unspecified', at=EARLY)
        from services.cert.issued_lookup import persisted_revocation
        with app.app_context():
            assert persisted_revocation(db.session.get(CA, ca_id), real.serial_number).revoked_at == EARLY


class TestLiftingAHoldDeletesEveryRecordOfTheSerial:

    def test_a_record_under_a_twin_goes_with_the_hold(self, app, auth_client, issuer, twin):
        ca_id, refid, ca_cert, ca_key = issuer
        real, key = _leaf('unhold-twin.example.test', ca_cert, ca_key)
        row_id = _store(app, real, twin[1], key=key)
        _record(app, refid, real, reason='certificateHold')
        with app.app_context():
            row = db.session.get(Certificate, row_id)
            row.revoked, row.revoke_reason, row.revoked_at = True, 'certificateHold', EARLY
            db.session.commit()
        r = auth_client.post(f'/api/v2/certificates/{row_id}/unhold')
        assert r.status_code == 200, r.data
        with app.app_context():
            assert RevokedSerial.query.filter(
                RevokedSerial.caref.in_([refid, twin[1]]),
                RevokedSerial.serial_number == str(real.serial_number)).count() == 0
        assert _surfaces(app, ca_id, real) == ('good', None, None, 'ok')

    def test_a_record_in_another_spelling_goes_with_the_hold(self, app, auth_client, issuer):
        """Issued with a hexadecimal serial column, deleted, imported again in decimal."""
        ca_id, refid, ca_cert, ca_key = issuer
        real, key = _leaf('unhold-hex.example.test', ca_cert, ca_key)
        row_id = _store(app, real, refid, key=key)
        _record(app, refid, real, reason='certificateHold', column=format(real.serial_number, 'x'))
        with app.app_context():
            row = db.session.get(Certificate, row_id)
            row.revoked, row.revoke_reason, row.revoked_at = True, 'certificateHold', EARLY
            db.session.commit()
        r = auth_client.post(f'/api/v2/certificates/{row_id}/unhold')
        assert r.status_code == 200, r.data
        with app.app_context():
            assert RevokedSerial.query.filter_by(caref=refid).filter(RevokedSerial.serial_number.in_(
                [str(real.serial_number), format(real.serial_number, 'x')])).count() == 0
        assert _surfaces(app, ca_id, real) == ('good', None, None, 'ok')

    def test_a_hold_is_not_lifted_over_a_compromise(self, app, auth_client, issuer, twin):
        ca_id, refid, ca_cert, ca_key = issuer
        real, key = _leaf('unhold-compromised.example.test', ca_cert, ca_key)
        row_id = _store(app, real, twin[1], key=key)
        _record(app, twin[1], real, reason='certificateHold', certificate_id=row_id)
        _record(app, refid, real, reason='keyCompromise', at=LATER)
        with app.app_context():
            row = db.session.get(Certificate, row_id)
            row.revoked, row.revoke_reason, row.revoked_at = True, 'certificateHold', EARLY
            db.session.commit()
        r = auth_client.post(f'/api/v2/certificates/{row_id}/unhold')
        assert r.status_code == 409, r.data
        assert _row(app, row_id) == (True, 'certificateHold', EARLY)
        with app.app_context():
            assert RevokedSerial.query.filter_by(caref=refid, serial_number=str(real.serial_number)).count() == 1
        surfaces = _surfaces(app, ca_id, real)
        assert (surfaces[0], surfaces[2] is not None, surfaces[3]) == ('revoked', True, 'revoked')


class TestASupersededRecordNeverReplacesAGraverOne:

    def test_a_compromise_keeps_its_reason_and_date(self, app, issuer, leaf_row):
        from services.cert.renewal import _record_superseded
        ca_id, refid, ca_cert, ca_key = issuer
        real, row_id = leaf_row
        _record(app, refid, real, reason='keyCompromise', at=EARLY)
        with app.app_context():
            _record_superseded(row_id, db.session.get(CA, ca_id), str(real.serial_number),
                               datetime(2030, 1, 1), LATER)
            db.session.commit()
            [record] = RevokedSerial.query.filter_by(caref=refid, serial_number=str(real.serial_number)).all()
            assert (record.revoke_reason, record.revoked_at) == ('keyCompromise', EARLY)

    def test_a_record_for_the_serial_is_updated_not_duplicated(self, app, issuer, leaf_row):
        """Non-regression: passes before the fix, called on the record alone."""
        from services.cert.renewal import _record_superseded
        ca_id, refid, ca_cert, ca_key = issuer
        real, row_id = leaf_row
        _record(app, refid, real, reason='superseded', at=EARLY)
        with app.app_context():
            _record_superseded(row_id, db.session.get(CA, ca_id), str(real.serial_number),
                               datetime(2030, 1, 1), LATER)
            db.session.commit()
            [record] = RevokedSerial.query.filter_by(caref=refid, serial_number=str(real.serial_number)).all()
            assert (record.certificate_id, record.valid_to) == (row_id, datetime(2030, 1, 1))


@pytest.fixture
def leaf_row(app, issuer):
    _, refid, ca_cert, ca_key = issuer
    real, key = _leaf(f'superseded-{uuid.uuid4().hex[:6]}.example.test', ca_cert, ca_key)
    return real, _store(app, real, refid, key=key)


class TestAnAttachedRowTakesTheRecord:

    def test_the_backfill_that_links_an_orphan_applies_it(self, app, issuer):
        from services.ski_aki_backfill import backfill_ski_aki
        _, refid, ca_cert, ca_key = issuer
        real, key = _leaf('orphan-linked.example.test', ca_cert, ca_key)
        row_id = _store(app, real, None, key=key)
        with app.app_context():
            row = db.session.get(Certificate, row_id)
            row.aki = real.extensions.get_extension_for_class(
                x509.AuthorityKeyIdentifier).value.key_identifier.hex(':').upper()
            db.session.commit()
        _record(app, refid, real)
        with app.app_context():
            backfill_ski_aki()
            db.session.expire_all()
            assert db.session.get(Certificate, row_id).caref == refid
        assert _row(app, row_id) == (True, 'keyCompromise', EARLY)

    def test_the_hourly_repair_marks_a_linked_row_left_unrevoked(self, app, issuer):
        from services.ski_aki_backfill import backfill_ski_aki
        _, refid, ca_cert, ca_key = issuer
        real, key = _leaf('legacy-unrevoked.example.test', ca_cert, ca_key)
        row_id = _store(app, real, refid, key=key)
        _record(app, refid, real)
        with app.app_context():
            backfill_ski_aki()
        assert _row(app, row_id) == (True, 'keyCompromise', EARLY)


class TestAnUpdateThatComesBackRevokedIsNoRenewal:

    def test_no_renewal_event(self, app, auth_client, issuer, monkeypatch):
        from services import webhook_service
        _, refid, ca_cert, ca_key = issuer
        current, key = _leaf('revoked-update.example.test', ca_cert, ca_key)
        row_id = _store(app, current, refid, key=key)
        revoked, _ = _leaf('revoked-update.example.test', ca_cert, ca_key, key=key)
        _record(app, refid, revoked)
        renewed = []
        monkeypatch.setattr(webhook_service, 'emit_cert_renewed', lambda *a, **k: renewed.append(a))
        r = _import(auth_client, revoked, key)
        assert r.status_code == 200, r.data
        assert _row(app, row_id) == (True, 'keyCompromise', EARLY)
        assert renewed == []


class TestTheSchedulerMarksARecordedRevocation:

    def test_the_row_is_marked_revoked_instead_of_failing_each_pass(self, app, issuer, monkeypatch):
        from models import AuditLog
        from services.auto_renewal_service import AutoRenewalService
        _, refid, ca_cert, ca_key = issuer
        real, key = _leaf('scheduled-revoked.example.test', ca_cert, ca_key)
        row_id = _store(app, real, refid, key=key)
        _record(app, refid, real)
        monkeypatch.setattr(AutoRenewalService, 'get_renewal_config', staticmethod(lambda: {'enabled': True}))
        monkeypatch.setattr(AutoRenewalService, '_held_for_approval',
                            staticmethod(lambda cert, already_queued: None))
        monkeypatch.setattr(AutoRenewalService, 'waiting_certificates', staticmethod(lambda config: {}))
        monkeypatch.setattr(AutoRenewalService, '_publish_crls', staticmethod(lambda carefs: None))
        with app.app_context():
            monkeypatch.setattr(AutoRenewalService, 'get_certificates_for_renewal',
                                staticmethod(lambda: [db.session.get(Certificate, row_id)]))
            floor = db.session.query(db.func.max(AuditLog.id)).scalar() or 0
            stats = AutoRenewalService.run_auto_renewal()
            assert (stats['failed'], stats['skipped']) == (0, 1), stats
            assert AuditLog.query.filter(AuditLog.id > floor,
                                         AuditLog.action == 'certificate.auto_renewal_failed').count() == 0
        assert _row(app, row_id) == (True, 'keyCompromise', EARLY)


class TestAPairPartnerRevokedOnlyByItsRecord:

    def test_it_is_left_out_like_a_revoked_partner(self, app, issuer, monkeypatch):
        from services.cert import related_pair
        from services.cert.renewal import _renewal_members
        _, refid, ca_cert, ca_key = issuer
        first, key_a = _leaf('pair-a.example.test', ca_cert, ca_key)
        second, key_b = _leaf('pair-b.example.test', ca_cert, ca_key)
        a_id, b_id = _store(app, first, refid, key=key_a), _store(app, second, refid, key=key_b)
        _record(app, refid, second)
        with app.app_context():
            a, b = db.session.get(Certificate, a_id), db.session.get(Certificate, b_id)
            monkeypatch.setattr(related_pair, 'mutual_partner', lambda cert: b if cert is a else a)
            assert _renewal_members(a) == [a]


class TestAnAcmeReplacementNeverSupersedesAGraverRecord:

    def test_a_compromise_keeps_its_reason_and_date(self, app, issuer, leaf_row):
        from types import SimpleNamespace
        from services.acme_renewal_service import _record_replaced_serial
        _, refid, _, _ = issuer
        real, row_id = leaf_row
        _record(app, refid, real, reason='keyCompromise', at=EARLY)
        with app.app_context():
            _record_replaced_serial(SimpleNamespace(
                id=row_id, caref=refid, serial=str(real.serial_number), valid_to=datetime(2030, 1, 1),
                pem=real.public_bytes(serialization.Encoding.PEM)))
            [record] = RevokedSerial.query.filter_by(caref=refid, serial_number=str(real.serial_number)).all()
            assert (record.revoke_reason, record.revoked_at) == ('keyCompromise', EARLY)


def _homonyms():
    """(d, h): ``h``'s hexadecimal is all digits and spells ``d`` in decimal (16 and "10")."""
    import secrets
    d = int(''.join(secrets.choice('0123456789') for _ in range(11)).lstrip('0') or '7') + 10 ** 11
    return d, int(str(d), 16)


def _held(app, row_id, at=EARLY):
    with app.app_context():
        row = db.session.get(Certificate, row_id)
        row.revoked, row.revoke_reason, row.revoked_at = True, 'certificateHold', at
        db.session.commit()


def _renewable(app, row_id):
    from services.cert.renewal import check_renewable
    with app.app_context():
        check_renewable(db.session.get(Certificate, row_id))


class TestAnotherSerialsHexSpellingNamesNothing:
    """A serial whose hex is all digits is the decimal spelling of another one."""

    def test_revoking_the_decimal_one_leaves_the_other_good_everywhere(self, app, auth_client, issuer):
        from services.ski_aki_backfill import backfill_ski_aki
        ca_id, refid, ca_cert, ca_key = issuer
        d, h = _homonyms()
        cert_d, key_d = _leaf('homonym-d.example.test', ca_cert, ca_key, serial=d)
        cert_h, key_h = _leaf('homonym-h.example.test', ca_cert, ca_key, serial=h)
        d_id, h_id = _store(app, cert_d, refid, key=key_d), _store(app, cert_h, refid, key=key_h)
        assert auth_client.post(f'/api/v2/certificates/{d_id}/revoke',
                                json={'reason': 'keyCompromise'}).status_code == 200
        assert _surfaces(app, ca_id, cert_h) == ('good', None, None, 'ok')
        with app.app_context():
            backfill_ski_aki()
        assert _row(app, h_id) == (False, None, None)
        assert _surfaces(app, ca_id, cert_h) == ('good', None, None, 'ok')
        _renewable(app, h_id)
        assert _import(auth_client, cert_h, key_h).status_code == 200
        assert _row(app, h_id) == (False, None, None)
        assert _surfaces(app, ca_id, cert_d)[0] == 'revoked'

    def test_lifting_a_hold_keeps_the_other_serials_record(self, app, auth_client, issuer):
        _, refid, ca_cert, ca_key = issuer
        d, h = _homonyms()
        cert_d, _ = _leaf('unhold-d.example.test', ca_cert, ca_key, serial=d)
        cert_h, key_h = _leaf('unhold-h.example.test', ca_cert, ca_key, serial=h)
        h_id = _store(app, cert_h, refid, key=key_h)
        _held(app, h_id)
        _record(app, refid, cert_h, reason='certificateHold', certificate_id=h_id)
        other = _record(app, refid, cert_d, reason='certificateHold')
        r = auth_client.post(f'/api/v2/certificates/{h_id}/unhold')
        assert r.status_code == 200, r.data
        with app.app_context():
            assert db.session.get(RevokedSerial, other) is not None

    def test_another_serials_compromise_does_not_block_a_lift(self, app, auth_client, issuer):
        ca_id, refid, ca_cert, ca_key = issuer
        d, h = _homonyms()
        cert_d, _ = _leaf('unhold-409-d.example.test', ca_cert, ca_key, serial=d)
        cert_h, key_h = _leaf('unhold-409-h.example.test', ca_cert, ca_key, serial=h)
        h_id = _store(app, cert_h, refid, key=key_h)
        _held(app, h_id)
        _record(app, refid, cert_h, reason='certificateHold', certificate_id=h_id)
        _record(app, refid, cert_d, reason='keyCompromise')
        r = auth_client.post(f'/api/v2/certificates/{h_id}/unhold')
        assert r.status_code == 200, r.data
        assert _surfaces(app, ca_id, cert_h) == ('good', None, None, 'ok')

    def test_the_hourly_task_never_marks_the_other_row(self, app, issuer):
        from services.ski_aki_backfill import backfill_ski_aki
        _, refid, ca_cert, ca_key = issuer
        d, h = _homonyms()
        cert_d, _ = _leaf('hourly-d.example.test', ca_cert, ca_key, serial=d)
        cert_h, key_h = _leaf('hourly-h.example.test', ca_cert, ca_key, serial=h)
        h_id = _store(app, cert_h, refid, key=key_h)
        _record(app, refid, cert_d)
        with app.app_context():
            backfill_ski_aki()
        assert _row(app, h_id) == (False, None, None)


class TestAnIssuedSpellingIsStillFound:
    """Issuance stores the serial in hexadecimal, an import in decimal."""

    def test_revoked_deleted_and_imported_again_it_comes_back_revoked(self, app, auth_client, issuer):
        ca_id, refid, ca_cert, ca_key = issuer
        serial = x509.random_serial_number()
        while format(serial, 'x').isdigit():
            serial = x509.random_serial_number()
        real, key = _leaf('issued-hex.example.test', ca_cert, ca_key, serial=serial)
        row_id = _store(app, real, refid, key=key)
        with app.app_context():
            db.session.get(Certificate, row_id).serial_number = format(serial, 'x')
            db.session.commit()
        assert auth_client.post(f'/api/v2/certificates/{row_id}/revoke',
                                json={'reason': 'keyCompromise'}).status_code == 200
        with app.app_context():
            assert RevokedSerial.query.filter_by(caref=refid, serial_number=format(serial, 'x')).count() == 1
        assert auth_client.delete(f'/api/v2/certificates/{row_id}').status_code in (200, 204)
        r = _import(auth_client, real, key)
        assert r.status_code in (200, 201), r.data
        again = r.get_json()['data']['id']
        assert _row(app, again)[:2] == (True, 'keyCompromise')
        assert _surfaces(app, ca_id, real) == KEY_COMPROMISED


class TestARecordAloneHoldsItsRow:
    """A suspension record linked to its unrevoked row of the same serial is a hold, with no
    exception (migration 136 deleted, once, those an earlier lift left behind)."""

    def test_every_surface_answers_hold_and_the_hourly_pass_marks_the_row(self, app, issuer):
        from services.ski_aki_backfill import backfill_ski_aki
        ca_id, refid, ca_cert, ca_key = issuer
        real, key = _leaf('record-holds.example.test', ca_cert, ca_key)
        row_id = _store(app, real, refid, key=key)
        record_id = _record(app, refid, real, reason='certificateHold', certificate_id=row_id)
        hold = x509.ReasonFlags.certificate_hold
        assert _surfaces(app, ca_id, real) == ('revoked', hold, hold, 'revoked')
        with app.app_context():
            backfill_ski_aki()
            assert db.session.get(RevokedSerial, record_id) is not None
        assert _row(app, row_id) == (True, 'certificateHold', EARLY)

    def test_a_hold_survives_a_merge_restore_of_an_earlier_archive(self, app, auth_client, issuer):
        from services.backup_service import BackupService
        from services.ski_aki_backfill import backfill_ski_aki
        ca_id, refid, ca_cert, ca_key = issuer
        real, key = _leaf('restore-keeps-hold.example.test', ca_cert, ca_key)
        row_id = _store(app, real, refid, key=key)
        with app.app_context():
            row = db.session.get(Certificate, row_id)
            archived = next(c for c in BackupService()._export_certificates(True) if c['refid'] == row.refid)
        assert auth_client.post(f'/api/v2/certificates/{row_id}/revoke',
                                json={'reason': 'certificateHold'}).status_code == 200
        with app.app_context():
            BackupService()._restore_certificates({'certificates': [archived]},
                                                  {'cas': 0, 'certificates': 0}, master_key=None)
            db.session.commit()
        assert _row(app, row_id) == (False, None, None)
        hold = x509.ReasonFlags.certificate_hold
        assert _surfaces(app, ca_id, real) == ('revoked', hold, hold, 'revoked')
        with app.app_context():
            backfill_ski_aki()
        assert _row(app, row_id)[:2] == (True, 'certificateHold')
        assert _surfaces(app, ca_id, real) == ('revoked', hold, hold, 'revoked')

    def test_the_hourly_pass_reads_the_record_afresh(self, app, issuer):
        from sqlalchemy import text
        from services.cert.issued_lookup import apply_persisted_revocations
        _, refid, ca_cert, ca_key = issuer
        real, key = _leaf('hourly-afresh.example.test', ca_cert, ca_key)
        row_id = _store(app, real, refid, key=key)
        record_id = _record(app, refid, real, reason='certificateHold', certificate_id=row_id)
        with app.app_context():
            # Held in this session's identity map (weakly referenced otherwise)
            stale = db.session.get(RevokedSerial, record_id), db.session.get(Certificate, row_id)
            assert (stale[0].revoke_reason, stale[1].revoked) == ('certificateHold', False)
            # Made final by another worker while this session holds its stale copy
            with db.engine.begin() as conn:
                conn.execute(text(f"UPDATE {RevokedSerial.__tablename__} SET revoke_reason = 'keyCompromise' "
                                  "WHERE id = :i"), {'i': record_id})
            marked = {row.id: row.revoke_reason for row, _ in apply_persisted_revocations()}
            db.session.rollback()
        assert marked[row_id] == 'keyCompromise'

    def test_made_final_it_is_invalid_since_the_hold(self, app, auth_client, issuer):
        _, refid, ca_cert, ca_key = issuer
        real, key = _leaf('record-hold-final.example.test', ca_cert, ca_key)
        row_id = _store(app, real, refid, key=key)
        _record(app, refid, real, reason='certificateHold', certificate_id=row_id)
        r = auth_client.post(f'/api/v2/certificates/{row_id}/revoke', json={'reason': 'keyCompromise'})
        assert r.status_code == 200, r.data
        with app.app_context():
            row = db.session.get(Certificate, row_id)
            assert (row.revoked, row.revoke_reason, row.invalidity_at) == (True, 'keyCompromise', EARLY)


    def test_a_real_hold_unlinked_by_an_import_still_applies(self, app, auth_client, issuer):
        ca_id, refid, ca_cert, ca_key = issuer
        cn = 'held-unlinked.example.test'
        real, key = _leaf(cn, ca_cert, ca_key)
        row_id = _store(app, real, refid, key=key)
        assert auth_client.post(f'/api/v2/certificates/{row_id}/revoke',
                                json={'reason': 'certificateHold'}).status_code == 200
        namesake, _ = _leaf(cn, ca_cert, ca_key)
        assert _import(auth_client, namesake).status_code == 200
        assert _surfaces(app, ca_id, real)[:2] == ('revoked', x509.ReasonFlags.certificate_hold)
        assert _import(auth_client, real, key).status_code == 200
        assert _row(app, row_id)[:2] == (True, 'certificateHold')

    def test_a_final_reason_linked_to_an_unrevoked_row_still_revokes(self, app, issuer):
        from services.ski_aki_backfill import backfill_ski_aki
        ca_id, refid, ca_cert, ca_key = issuer
        real, key = _leaf('final-linked.example.test', ca_cert, ca_key)
        row_id = _store(app, real, refid, key=key)
        _record(app, refid, real, reason='cessationOfOperation', certificate_id=row_id)
        assert _surfaces(app, ca_id, real)[0] == 'revoked'
        with app.app_context():
            backfill_ski_aki()
        assert _row(app, row_id) == (True, 'cessationOfOperation', EARLY)


class TestAHeldRowUnderAFinalRecordAnswersTheGraverReason:

    def test_ocsp_and_crl_say_compromise(self, app, issuer, twin):
        ca_id, refid, ca_cert, ca_key = issuer
        real, key = _leaf('held-graver.example.test', ca_cert, ca_key)
        row_id = _store(app, real, refid, key=key)
        _held(app, row_id, at=LATER)
        _record(app, twin[1], real)
        assert _surfaces(app, ca_id, real) == KEY_COMPROMISED


def _es256_revocation(client, key, pem, reason):
    """A revokeCert to UCM's own ACME server, signed by the certificate's key (RFC 8555 §7.6)."""
    import json
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

    def b64(raw):
        return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()

    numbers = key.public_key().public_numbers()
    jwk = {'kty': 'EC', 'crv': 'P-256', 'x': b64(numbers.x.to_bytes(32, 'big')),
           'y': b64(numbers.y.to_bytes(32, 'big'))}
    der = x509.load_pem_x509_certificate(pem).public_bytes(serialization.Encoding.DER)
    nonce = client.get('/acme/new-nonce').headers.get('Replay-Nonce')
    protected = b64(json.dumps({'alg': 'ES256', 'nonce': nonce, 'jwk': jwk,
                                'url': 'http://localhost/acme/revoke-cert'}).encode())
    payload = b64(json.dumps({'certificate': b64(der), 'reason': reason}).encode())
    r, s = decode_dss_signature(key.sign(f'{protected}.{payload}'.encode(), ec.ECDSA(hashes.SHA256())))
    jws = {'protected': protected, 'payload': payload,
           'signature': b64(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}
    return client.post('/acme/revoke-cert', data=json.dumps(jws), content_type='application/jose+json')


class TestARecordedFinalRevocationIsNotRevokedAgain:
    """A row its CA's record revokes for good is already revoked: each caller takes its own
    "already revoked" path, and the check commits nothing (the hourly pass marks the row)."""

    def _covered(self, app, issuer, cn, *, caref=None, held=False):
        _, refid, ca_cert, ca_key = issuer
        real, key = _leaf(cn, ca_cert, ca_key)
        row_id = _store(app, real, refid, key=key)
        if held:
            _held(app, row_id, at=LATER)
        record_id = _record(app, caref or refid, real)
        return real, key, row_id, record_id

    def _record_kept(self, app, record_id):
        with app.app_context():
            record = db.session.get(RevokedSerial, record_id)
            return record.revoke_reason, record.revoked_at

    @pytest.mark.parametrize('reason', ['certificateHold', 'superseded'])
    def test_the_unit_route_answers_already_revoked(self, app, auth_client, issuer, reason):
        ca_id, _, _, _ = issuer
        real, _, row_id, record_id = self._covered(app, issuer, f'unit-{reason.lower()}.example.test')
        r = auth_client.post(f'/api/v2/certificates/{row_id}/revoke', json={'reason': reason})
        assert r.status_code == 400 and b'already revoked' in r.data, r.data
        assert _row(app, row_id) == (False, None, None)
        assert self._record_kept(app, record_id) == ('keyCompromise', EARLY)
        assert auth_client.post(f'/api/v2/certificates/{row_id}/unhold').status_code != 200
        assert _surfaces(app, ca_id, real) == KEY_COMPROMISED

    def test_a_held_row_over_a_twins_compromise_is_already_revoked(self, app, auth_client, issuer, twin):
        real, _, row_id, _ = self._covered(app, issuer, 'held-over-twin.example.test', caref=twin[1], held=True)
        r = auth_client.post(f'/api/v2/certificates/{row_id}/revoke', json={'reason': 'superseded'})
        assert r.status_code == 400 and b'already revoked' in r.data, r.data
        assert _row(app, row_id) == (True, 'certificateHold', LATER)

    def test_the_service_refuses_it_too(self, app, issuer):
        from services.cert_service import CertificateService
        _, _, row_id, record_id = self._covered(app, issuer, 'service-over-compromise.example.test')
        with app.app_context():
            with pytest.raises(ValueError, match='already revoked'):
                CertificateService.revoke_certificate(row_id, reason='certificateHold')
        assert _row(app, row_id) == (False, None, None)
        assert self._record_kept(app, record_id) == ('keyCompromise', EARLY)

    def test_the_bulk_route_counts_it_already_revoked(self, app, auth_client, issuer):
        _, _, row_id, record_id = self._covered(app, issuer, 'bulk-over-compromise.example.test')
        r = auth_client.post('/api/v2/certificates/bulk/revoke', json={'ids': [row_id], 'reason': 'superseded'})
        assert r.status_code == 200, r.data
        assert r.get_json()['data']['failed'] == [{'id': row_id, 'error': 'Already revoked'}]
        assert self._record_kept(app, record_id) == ('keyCompromise', EARLY)

    def test_acme_revoke_cert_answers_already_revoked(self, app, client, issuer):
        real, key, row_id, record_id = self._covered(app, issuer, 'acme-over-compromise.example.test')
        r = _es256_revocation(client, key, real.public_bytes(serialization.Encoding.PEM), 4)
        assert r.status_code == 400, r.data[:300]
        assert r.get_json()['type'] == 'urn:ietf:params:acme:error:alreadyRevoked'
        assert self._record_kept(app, record_id) == ('keyCompromise', EARLY)

    def test_an_approved_revocation_is_closed_on_it(self, app, auth_client, issuer):
        import json
        from models.policy import ApprovalRequest
        real, _, row_id, record_id = self._covered(app, issuer, 'approval-over-compromise.example.test')
        with app.app_context():
            approval = ApprovalRequest(
                request_type='revocation', status='pending', required_approvals=1,
                request_data=json.dumps({'certificate_id': row_id, 'serial_number': str(real.serial_number),
                                         'reason': 'superseded', 'cn': 'approval-over-compromise'}))
            db.session.add(approval)
            db.session.commit()
            approval_id = approval.id
        try:
            r = auth_client.post(f'/api/v2/approvals/{approval_id}/approve', json={})
            assert r.status_code == 200, r.data
            with app.app_context():
                approval = db.session.get(ApprovalRequest, approval_id)
                assert (approval.status, approval.certificate_id) == ('approved', row_id)
            assert r.get_json()['data']['certificate']['already_revoked'] is True, r.data
            assert _row(app, row_id) == (False, None, None)
            assert self._record_kept(app, record_id) == ('keyCompromise', EARLY)
        finally:
            with app.app_context():
                ApprovalRequest.query.filter_by(id=approval_id).delete()
                db.session.commit()

    def test_an_acme_replacement_sends_the_recorded_reason(self, app, issuer, monkeypatch):
        from unittest import mock
        from services import acme_renewal_service
        from services.cert_service import CertificateService
        from tests.test_related_certificates_pair import _restore_config, _set_config
        _, _, row_id, record_id = self._covered(app, issuer, 'replaced-over-compromise.example.test')
        local = mock.Mock()
        monkeypatch.setattr(CertificateService, 'revoke_certificate', local)
        client = mock.Mock()
        client.revoke_certificate.return_value = mock.Mock(status_code=200)
        previous = _set_config(app, 'acme.revoke_on_renewal', 'true')
        try:
            with app.app_context():
                replaced = acme_renewal_service._replaced_snapshot(db.session.get(Certificate, row_id))
                acme_renewal_service._revoke_replaced_certificate(client, replaced, in_place=False)
        finally:
            _restore_config(app, 'acme.revoke_on_renewal', previous)
        local.assert_not_called()
        assert client.revoke_certificate.call_args.kwargs == {'reason': 1}
        assert self._record_kept(app, record_id) == ('keyCompromise', EARLY)

    @pytest.mark.parametrize('caller', ['finalize', 'settings sweep'])
    def test_auto_supersede_leaves_it(self, app, issuer, monkeypatch, caller):
        import json
        from unittest import mock
        from models.acme_models import AcmeAccount, AcmeOrder
        from services.acme.acme_service import AcmeService
        from services.cert_service import CertificateService
        from api.v2.acme.settings import _revoke_superseded_certificates
        from tests.test_related_certificates_pair import _restore_config, _set_config
        cn = f"supersede-over-compromise-{caller.replace(' ', '-')}.example.test"
        _, refid, ca_cert, ca_key = issuer
        _, _, old_id, record_id = self._covered(app, issuer, cn)
        newer, newer_key = _leaf(cn, ca_cert, ca_key)
        new_id = _store(app, newer, refid, key=newer_key)
        local = mock.Mock()
        monkeypatch.setattr(CertificateService, 'revoke_certificate', local)
        previous = _set_config(app, 'acme.revoke_on_renewal', 'true')
        try:
            with app.app_context():
                account = AcmeAccount(jwk='{}', jwk_thumbprint=cn)
                db.session.add(account)
                db.session.flush()
                idents = json.dumps([{'type': 'dns', 'value': cn}])
                old = AcmeOrder(account_id=account.account_id, status='valid', identifiers=idents,
                                certificate_id=old_id, created_at=EARLY)
                new = AcmeOrder(account_id=account.account_id, status='valid', identifiers=idents,
                                certificate_id=new_id, created_at=LATER)
                db.session.add_all([old, new])
                db.session.commit()
                if caller == 'finalize':
                    AcmeService(base_url='http://localhost')._auto_supersede(new, new_id)
                else:
                    _revoke_superseded_certificates()
            assert old_id not in [c.kwargs.get('cert_id') for c in local.call_args_list]
            assert self._record_kept(app, record_id) == ('keyCompromise', EARLY)
        finally:
            _restore_config(app, 'acme.revoke_on_renewal', previous)
            with app.app_context():
                AcmeOrder.query.filter(AcmeOrder.certificate_id.in_([old_id, new_id])).delete(
                    synchronize_session=False)
                AcmeAccount.query.filter_by(jwk_thumbprint=cn).delete()
                db.session.commit()


class TestAWriterNeverReplacesAGraverReason:

    @pytest.mark.parametrize('recorded, written, replaced', [
        ('keyCompromise', 'certificateHold', False),
        ('keyCompromise', 'superseded', False),
        ('unspecified', 'superseded', False),
        ('certificateHold', 'superseded', True),
        ('certificateHold', 'keyCompromise', True),
        ('unspecified', 'keyCompromise', True),
    ])
    def test_the_shared_rule(self, recorded, written, replaced):
        from types import SimpleNamespace
        from services.cert.issued_lookup import record_reason_replaceable
        assert record_reason_replaceable(SimpleNamespace(revoke_reason=recorded), written) is replaced

    def test_the_revocation_writer_keeps_a_compromise(self, app, issuer, monkeypatch):
        """The refusal above bypassed: the writer alone keeps the graver reason."""
        from services.cert.mixins import lifecycle
        from services.cert_service import CertificateService
        _, refid, ca_cert, ca_key = issuer
        real, key = _leaf('writer-keeps.example.test', ca_cert, ca_key)
        row_id = _store(app, real, refid, key=key)
        record_id = _record(app, refid, real)
        monkeypatch.setattr(lifecycle, 'revocable', lambda row, reason: True)
        with app.app_context():
            CertificateService.revoke_certificate(row_id, reason='certificateHold')
            record = db.session.get(RevokedSerial, record_id)
            assert (record.revoke_reason, record.revoked_at) == ('keyCompromise', EARLY)


class TestRelatedAndMtlsReadTheRecord:

    def test_a_partner_revoked_by_its_record_is_not_named(self, app, issuer):
        from cryptography.x509 import UnrecognizedExtension
        from services.cert.renewal import _current_related
        from utils.related_cert import RELATED_CERT_EXTENSION_OID
        _, refid, ca_cert, ca_key = issuer
        first, key_a = _leaf('related-a.example.test', ca_cert, ca_key)
        now = datetime.now(timezone.utc)
        key_b = ec.generate_private_key(ec.SECP256R1())
        second = (x509.CertificateBuilder()
                  .subject_name(x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, 'related-b.example.test')]))
                  .issuer_name(ca_cert.subject).public_key(key_b.public_key())
                  .serial_number(x509.random_serial_number())
                  .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=30))
                  .add_extension(UnrecognizedExtension(RELATED_CERT_EXTENSION_OID, b'\x30\x00'), critical=False)
                  .sign(ca_key, hashes.SHA256()))
        a_id, b_id = _store(app, first, refid, key=key_a), _store(app, second, refid, key=key_b)
        with app.app_context():
            db.session.get(Certificate, b_id).related_certificate_id = a_id
            db.session.commit()
            assert _current_related(db.session.get(Certificate, b_id)) is not None
        _record(app, refid, first)
        with app.app_context():
            assert _current_related(db.session.get(Certificate, b_id)) is None

    def test_an_mtls_assignment_refuses_a_recorded_revocation(self, app, auth_client, issuer):
        _, refid, ca_cert, ca_key = issuer
        real, key = _leaf('mtls-assign-revoked.example.test', ca_cert, ca_key)
        row_id = _store(app, real, refid, key=key)
        with app.app_context():
            db.session.get(Certificate, row_id).cert_type = 'usr_cert'
            db.session.commit()
        _record(app, refid, real)
        r = auth_client.post('/api/v2/mtls/assign', json={'cert_id': row_id})
        assert r.status_code == 400, r.data
        assert b'revoked' in r.data


class TestTheHourlyTaskRecordsWhatItMarks:

    def test_one_audit_per_marked_row(self, app, issuer):
        from models import AuditLog
        from services.ski_aki_backfill import backfill_ski_aki
        _, refid, ca_cert, ca_key = issuer
        real, key = _leaf('hourly-audit.example.test', ca_cert, ca_key)
        row_id = _store(app, real, refid, key=key)
        _record(app, refid, real)
        with app.app_context():
            floor = db.session.query(db.func.max(AuditLog.id)).scalar() or 0
            stats = backfill_ski_aki()
            assert stats['revoked_from_records'] >= 1
            entries = AuditLog.query.filter(AuditLog.id > floor, AuditLog.resource_type == 'certificate',
                                            AuditLog.resource_id == str(row_id)).all()
            assert len(entries) == 1
            entry = entries[0]
            assert entry.username == 'system' and entry.action == 'cert_revoked'
            for part in (str(real.serial_number), refid, 'keyCompromise', 'recorded revocation'):
                assert part in entry.details

    def test_a_failure_leaves_the_later_phases_running(self, app, issuer, monkeypatch):
        from services import ski_aki_backfill
        _, refid, ca_cert, ca_key = issuer
        real, key = _leaf('hourly-failure.example.test', ca_cert, ca_key)
        row_id = _store(app, real, refid, key=key)
        with app.app_context():
            db.session.get(Certificate, row_id).subject_cn = None
            db.session.commit()

        def boom():
            raise RuntimeError('records unreadable')
        monkeypatch.setattr(ski_aki_backfill, 'apply_persisted_revocations', boom)
        with app.app_context():
            ski_aki_backfill.backfill_ski_aki()
            db.session.expire_all()
            assert db.session.get(Certificate, row_id).subject_cn == 'hourly-failure.example.test'


HOLD, COMPROMISE, SUPERSEDED_FLAG = (x509.ReasonFlags.certificate_hold, x509.ReasonFlags.key_compromise,
                                     x509.ReasonFlags.superseded)


class TestTheStateTable:
    """Row × record × suspensive or final reason: what every surface answers, and whether a
    revocation (final, then hold) is still taken."""

    @pytest.mark.parametrize('row, record, answer, final_ok, hold_ok', [
        (None, None, ('good', None, None, 'ok'), True, True),
        (None, ('certificateHold', 'linked'), ('revoked', HOLD, HOLD, 'revoked'), True, False),
        (None, ('certificateHold', 'unlinked'), ('revoked', HOLD, HOLD, 'revoked'), True, False),
        (None, ('keyCompromise', 'linked'), ('revoked', COMPROMISE, COMPROMISE, 'revoked'), False, False),
        (None, ('keyCompromise', 'twin'), ('revoked', COMPROMISE, COMPROMISE, 'revoked'), False, False),
        ('certificateHold', None, ('revoked', HOLD, HOLD, 'revoked'), True, False),
        ('certificateHold', ('keyCompromise', 'twin'), ('revoked', COMPROMISE, COMPROMISE, 'revoked'), False, False),
        ('superseded', ('certificateHold', 'linked'), ('revoked', SUPERSEDED_FLAG, SUPERSEDED_FLAG, 'revoked'),
         False, False),
    ])
    def test_each_state(self, app, issuer, twin, row, record, answer, final_ok, hold_ok):
        from utils.revocation_reasons import revocable
        ca_id, refid, ca_cert, ca_key = issuer
        real, key = _leaf(f'state-{uuid.uuid4().hex[:8]}.example.test', ca_cert, ca_key)
        row_id = _store(app, real, refid, key=key)
        if row:
            with app.app_context():
                stored = db.session.get(Certificate, row_id)
                stored.revoked, stored.revoke_reason, stored.revoked_at = True, row, LATER
                db.session.commit()
        if record:
            reason, where = record
            _record(app, twin[1] if where == 'twin' else refid, real, reason=reason,
                    certificate_id=row_id if where == 'linked' else None)
        assert _surfaces(app, ca_id, real) == answer
        with app.app_context():
            stored = db.session.get(Certificate, row_id)
            assert (revocable(stored, 'keyCompromise'), revocable(stored, 'certificateHold')) == (final_ok, hold_ok)


class TestTheCrlReadsTheRecordsOnce:

    def test_the_query_count_does_not_grow_with_the_held_rows(self, app, issuer, twin):
        from sqlalchemy import event
        from services.crl_service import CRLService
        ca_id, refid, ca_cert, ca_key = issuer

        made = []

        def held_rows(count):
            for _ in range(count):
                real, key = _leaf(f'crl-count-{uuid.uuid4().hex[:8]}.example.test', ca_cert, ca_key)
                made.append(_store(app, real, refid, key=key))
                _held(app, made[-1], at=LATER)
                # Stored first, under the same CA: only the gravest-first order picks the compromise
                _record(app, twin[1], real, reason='certificateHold', certificate_id=made[-1])
                _record(app, twin[1], real, at=LATER)

        def queries():
            seen = []
            with app.app_context():
                db.session.expire_all()

                def count(*_args):
                    seen.append(1)
                event.listen(db.engine, 'before_cursor_execute', count)
                try:
                    entries = CRLService.get_revoked_certificates(ca_id)
                finally:
                    event.remove(db.engine, 'before_cursor_execute', count)
                return len(seen), entries

        held_rows(2)
        few, entries = queries()
        held_rows(6)
        many, entries = queries()
        assert many == few
        listed = {e.serial_number: e.revoke_reason for e in entries if not isinstance(e, CA)}
        with app.app_context():
            serials = [db.session.get(Certificate, i).serial_number for i in made]
        assert [listed.get(s) for s in serials] == ['keyCompromise'] * len(made)


class TestAPageReadsTheRecordsOnce:

    def test_one_record_query_and_two_per_ca_of_the_covered_rows(self, app, issuer, create_ca):
        import threading
        from sqlalchemy import event
        from services.cert.issued_lookup import persisted_revocations_of
        from services.hsm.ca_key_loader import get_ca_signing_key
        other = create_ca(cn=f'Record Rule page CA {uuid.uuid4().hex[:6]}',
                          keyUsage=['digitalSignature', 'keyCertSign', 'cRLSign'])
        with app.app_context():
            row = db.session.get(CA, other['id'])
            second = (row.refid, x509.load_pem_x509_certificate(base64.b64decode(row.crt)),
                      get_ca_signing_key(row))
        authorities = [(issuer[1], issuer[2], issuer[3]), second]
        made = []

        def recorded_rows(count):
            for refid, ca_cert, ca_key in authorities:
                for _ in range(count):
                    real, key = _leaf(f'page-{uuid.uuid4().hex[:8]}.example.test', ca_cert, ca_key)
                    made.append(_store(app, real, refid, key=key))
                    _record(app, refid, real, certificate_id=made[-1])

        def queries():
            seen, mine = [], threading.get_ident()

            def count(_conn, _cursor, statement, *_rest):
                if threading.get_ident() == mine:
                    seen.append(statement)
            with app.app_context():
                db.session.expire_all()
                rows = Certificate.query.filter(Certificate.id.in_(made)).all()
                event.listen(db.engine, 'before_cursor_execute', count)
                try:
                    found = persisted_revocations_of(rows)
                finally:
                    event.remove(db.engine, 'before_cursor_execute', count)
                return seen, found

        recorded_rows(1)
        few, _ = queries()
        recorded_rows(3)
        many, found = queries()
        # The records' query, then the CA and its same-key records for each CA of the page
        assert len(few) == len(many) == 1 + 2 * len(authorities), many
        assert set(found) == set(made)


@pytest.mark.parametrize('column, serial', [
    ('171', 171), ('ab', 171), ('AB', 171), ('10', 10), ('0x10', None), ('007', None), ('', None),
    ('not a serial', None), ('-10', -10)])
def test_a_record_column_names_one_serial_at_most(column, serial):
    from utils.serial_format import serial_named_by, unambiguous_serial_spellings
    assert serial_named_by(column) == serial
    if serial is not None:
        assert column in unambiguous_serial_spellings(serial)


class TestANegativeSerialNamesItsOwnRecordOnly:
    """format(-16, 'x') is "-10", the decimal of -10: a hex spelling counts only with a letter."""

    def test_the_spellings(self):
        from utils.serial_format import serial_named_by, unambiguous_serial_spellings
        assert unambiguous_serial_spellings(-16) == {'-16'}
        assert unambiguous_serial_spellings(-10) == {'-10', '-a', '-A'}
        assert serial_named_by('-10') == -10 and serial_named_by('-a') == -10

    def test_minus_ten_and_minus_sixteen(self, app, issuer):
        from services.cert.issued_lookup import record_serial_clause
        _, refid, _, _ = issuer
        with app.app_context():
            made = [RevokedSerial(caref=refid, serial_number=column, revoke_reason='keyCompromise',
                                  revoked_at=EARLY, valid_to=LATER) for column in ('-10', '-16')]
            db.session.add_all(made)
            db.session.commit()
            try:
                for serial in (-10, -16):
                    named = RevokedSerial.query.filter(RevokedSerial.caref == refid,
                                                       record_serial_clause(serial)).all()
                    assert [r.serial_number for r in named] == [str(serial)]
            finally:
                for record in made:
                    db.session.delete(record)
                db.session.commit()


class TestCaAndCrossRecordsReadUnambiguousSpellings:
    """A CA's or a cross-certificate's record lookup: another serial's all-digit hex is no match."""

    def test_a_child_ca(self, app, issuer):
        ca_id, refid, ca_cert, ca_key = issuer
        d, h = _homonyms()
        now = datetime.now(timezone.utc)
        child_key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, f'homonym child {uuid.uuid4().hex[:6]}')])
        child = (x509.CertificateBuilder().subject_name(name).issuer_name(ca_cert.subject)
                 .public_key(child_key.public_key()).serial_number(h)
                 .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=30))
                 .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                 .sign(ca_key, hashes.SHA256()))
        with app.app_context():
            row = CA(refid=str(uuid.uuid4()), descr='homonym child', caref=refid, serial=0,
                     crt=base64.b64encode(child.public_bytes(serialization.Encoding.PEM)).decode(),
                     subject=name.rfc4514_string(), issuer=ca_cert.subject.rfc4514_string(),
                     serial_number=str(h))
            db.session.add(row)
            db.session.commit()
            child_id = row.id
        other = _record(app, refid, ca_cert, column=str(d))
        try:
            with app.app_context():
                assert db.session.get(CA, child_id).persisted_revocation() is None
            own = _record(app, refid, ca_cert, column=str(h))
            with app.app_context():
                assert db.session.get(CA, child_id).persisted_revocation().id == own
        finally:
            with app.app_context():
                RevokedSerial.query.filter(RevokedSerial.id.in_([other])).delete(synchronize_session=False)
                RevokedSerial.query.filter_by(caref=refid, serial_number=str(h)).delete()
                db.session.delete(db.session.get(CA, child_id))
                db.session.commit()

    def test_a_cross_certificate(self, app, issuer):
        from types import SimpleNamespace
        from services.ca.cross_certs import published_record
        ca_id, refid, ca_cert, _ = issuer
        d, h = _homonyms()
        other = _record(app, refid, ca_cert, column=str(d))
        try:
            with app.app_context():
                assert published_record(SimpleNamespace(serial_number=str(h)), db.session.get(CA, ca_id)) is None
                assert published_record(SimpleNamespace(serial_number=str(d)), db.session.get(CA, ca_id)).id == other
        finally:
            with app.app_context():
                db.session.delete(db.session.get(RevokedSerial, other))
                db.session.commit()


class TestAnImportOverARenewedRowUnlinksOnlyItsOwnSerial:

    def test_the_record_of_the_serial_renewed_away_stays_linked(self, app, auth_client, issuer):
        _, refid, ca_cert, ca_key = issuer
        cn = 'renewed-then-imported.example.test'
        first, key = _leaf(cn, ca_cert, ca_key)
        row_id = _store(app, first, refid, key=key)
        r = auth_client.post(f'/api/v2/certificates/{row_id}/renew', json={})
        assert r.status_code == 200, r.data
        with app.app_context():
            renewed = db.session.get(Certificate, row_id).serial_number
            assert renewed != str(first.serial_number)
            [record] = RevokedSerial.query.filter_by(caref=refid, serial_number=str(first.serial_number)).all()
            assert record.certificate_id == row_id
        namesake, _ = _leaf(cn, ca_cert, ca_key)
        r = _import(auth_client, namesake)
        assert r.status_code == 200 and r.get_json()['data']['id'] == row_id, r.data
        with app.app_context():
            assert db.session.get(Certificate, row_id).serial_number == str(namesake.serial_number)
            record = RevokedSerial.query.filter_by(caref=refid, serial_number=str(first.serial_number)).one()
            assert record.certificate_id == row_id


class TestARecordedHoldIsShownAndLifted:
    """A hold its record alone carries (a row not yet aligned) lifts, and the detail and the
    list show the revocation the record makes, as OCSP and the CRL answer it."""

    def _recorded(self, app, issuer, cn, reason='certificateHold'):
        _, refid, ca_cert, ca_key = issuer
        real, key = _leaf(cn, ca_cert, ca_key)
        row_id = _store(app, real, refid, key=key)
        return real, row_id, _record(app, refid, real, reason=reason, certificate_id=row_id)

    def test_a_hold_carried_by_its_record_only_lifts(self, app, auth_client, issuer):
        ca_id = issuer[0]
        real, row_id, record_id = self._recorded(app, issuer, 'recorded-hold-lifts.example.test')
        r = auth_client.post(f'/api/v2/certificates/{row_id}/unhold')
        assert r.status_code == 200, r.data
        with app.app_context():
            assert db.session.get(RevokedSerial, record_id) is None
        assert _row(app, row_id) == (False, None, None)
        assert _surfaces(app, ca_id, real) == ('good', None, None, 'ok')

    def test_a_final_record_is_still_refused(self, app, auth_client, issuer):
        real, row_id, record_id = self._recorded(app, issuer, 'recorded-final-kept.example.test',
                                                 reason='keyCompromise')
        r = auth_client.post(f'/api/v2/certificates/{row_id}/unhold')
        assert r.status_code == 409, r.data
        with app.app_context():
            assert db.session.get(RevokedSerial, record_id) is not None

    def test_remove_from_crl_with_its_own_record_is_no_interrupted_lift(self, app, auth_client, issuer):
        """A row and a record both in removeFromCRL (an old ACME reason 8) prove no lift."""
        _, refid, ca_cert, ca_key = issuer
        real, key = _leaf('remove-from-crl-recorded.example.test', ca_cert, ca_key)
        row_id = _store(app, real, refid, key=key)
        record_id = _record(app, refid, real, reason='removeFromCRL', certificate_id=row_id)
        with app.app_context():
            row = db.session.get(Certificate, row_id)
            row.revoked, row.revoke_reason, row.revoked_at = True, 'removeFromCRL', LATER
            db.session.commit()
        r = auth_client.post(f'/api/v2/certificates/{row_id}/unhold')
        assert r.status_code == 409, r.data
        assert 'not on hold' in r.get_json()['message']
        assert _row(app, row_id) == (True, 'removeFromCRL', LATER)
        with app.app_context():
            assert db.session.get(RevokedSerial, record_id).revoke_reason == 'removeFromCRL'

    def test_a_final_record_beside_a_hold_record_is_no_interrupted_lift(self, app, auth_client, issuer, twin):
        """Every record of the serial must be a hold: one final record under a twin refuses."""
        from api.v2.certificates.cert_lifecycle import _interrupted_lift
        _, row_id, _ = self._recorded(app, issuer, 'hold-beside-final.example.test')
        with app.app_context():
            row = db.session.get(Certificate, row_id)
            row.revoked, row.revoke_reason, row.revoked_at = True, 'removeFromCRL', LATER
            db.session.commit()
            real = x509.load_pem_x509_certificate(base64.b64decode(row.crt))
        _record(app, twin[1], real, reason='keyCompromise', certificate_id=row_id)
        with app.app_context():
            assert _interrupted_lift(db.session.get(Certificate, row_id)) is False
        r = auth_client.post(f'/api/v2/certificates/{row_id}/unhold')
        assert r.status_code == 409, r.data
        assert _row(app, row_id) == (True, 'removeFromCRL', LATER)

    def test_a_lift_of_a_row_only_hold_left_half_done_completes(self, app, auth_client, issuer):
        """The hold was on the row alone: stopped mid-lift, no record is left and it still completes."""
        _, refid, ca_cert, ca_key = issuer
        real, key = _leaf('remove-from-crl-row-only.example.test', ca_cert, ca_key)
        row_id = _store(app, real, refid, key=key)
        with app.app_context():
            row = db.session.get(Certificate, row_id)
            row.revoked, row.revoke_reason, row.revoked_at = True, 'removeFromCRL', LATER
            db.session.commit()
        r = auth_client.post(f'/api/v2/certificates/{row_id}/unhold')
        assert r.status_code == 200, r.data
        assert _row(app, row_id) == (False, None, None)

    def test_a_lift_left_half_done_in_remove_from_crl_completes(self, app, auth_client, issuer):
        """removeFromCRL on a row is an unhold stopped between its two commits, not a final reason."""
        _, row_id, record_id = self._recorded(app, issuer, 'half-lifted.example.test')
        with app.app_context():
            row = db.session.get(Certificate, row_id)
            row.revoked, row.revoke_reason, row.revoked_at = True, 'removeFromCRL', LATER
            db.session.commit()
        r = auth_client.post(f'/api/v2/certificates/{row_id}/unhold')
        assert r.status_code == 200, r.data
        assert _row(app, row_id) == (False, None, None)
        with app.app_context():
            assert db.session.get(RevokedSerial, record_id) is None

    def test_a_final_row_is_refused_as_a_final_record_is(self, app, auth_client, issuer):
        """One refusal, one code: the row's own final reason answers as the record's does."""
        _, row_by_record, _ = self._recorded(app, issuer, 'final-by-record.example.test',
                                             reason='keyCompromise')
        _, refid, ca_cert, ca_key = issuer
        real, key = _leaf('final-by-row.example.test', ca_cert, ca_key)
        row_by_row = _store(app, real, refid, key=key)
        with app.app_context():
            row = db.session.get(Certificate, row_by_row)
            row.revoked, row.revoke_reason, row.revoked_at = True, 'keyCompromise', EARLY
            db.session.commit()
        answers = [auth_client.post(f'/api/v2/certificates/{i}/unhold') for i in (row_by_record, row_by_row)]
        assert [r.status_code for r in answers] == [409, 409], [r.data for r in answers]
        messages = [r.get_json()['message'] for r in answers]
        assert messages == [f'Certificate "{n}" is revoked for good (keyCompromise): its hold cannot be lifted'
                            for n in ('CN=final-by-record.example.test', 'CN=final-by-row.example.test')]
        assert _row(app, row_by_row) == (True, 'keyCompromise', EARLY)

    def test_a_certificate_nothing_revokes_is_not_revoked(self, app, auth_client, issuer):
        """Non-regression: passes before and after the change."""
        _, refid, ca_cert, ca_key = issuer
        real, key = _leaf('nothing-revokes.example.test', ca_cert, ca_key)
        row_id = _store(app, real, refid, key=key)
        assert auth_client.post(f'/api/v2/certificates/{row_id}/unhold').status_code == 400

    def test_the_detail_shows_the_recorded_revocation(self, app, auth_client, issuer):
        _, row_id, _ = self._recorded(app, issuer, 'recorded-detail.example.test')
        data = auth_client.get(f'/api/v2/certificates/{row_id}').get_json()['data']
        assert (data['revoked'], data['revoke_reason'], data['status']) == (True, 'certificateHold', 'revoked')
        assert data['revoked_at'].startswith('2026-01-02T03:04:05')

    def test_the_list_shows_it_with_one_record_query_for_the_page(self, app, auth_client, issuer, twin,
                                                                  create_ca):
        from sqlalchemy import event
        tag = uuid.uuid4().hex[:8]
        _, refid, ca_cert, ca_key = issuer
        recorded, plain = [], []
        with app.app_context():
            other = db.session.get(CA, create_ca(cn=f'Record Rule other CA {tag}')['id']).refid

        def rows(count):
            for _ in range(count):
                cn = f'list-{tag}-{uuid.uuid4().hex[:6]}.example.test'
                real, key = _leaf(cn, ca_cert, ca_key)
                recorded.append(_store(app, real, refid, key=key))
                _record(app, twin[1], real, reason='certificateHold', certificate_id=recorded[-1])
                real, key = _leaf(f'plain-{cn}', ca_cert, ca_key)
                plain.append(_store(app, real, refid, key=key))
                # Another CA's record of the same serial names another certificate
                _record(app, other, real, certificate_id=plain[-1])

        def listed():
            import threading
            from utils.admin_allowlist import invalidate_cache
            seen, mine = [], threading.get_ident()

            def count(_conn, _cursor, statement, *_rest):
                # Another thread's queries on the engine are not this request's cost
                if threading.get_ident() == mine:
                    seen.append(statement)
            with app.app_context():
                # The allowlist cache expires after seconds: read on both counted requests
                invalidate_cache()
                event.listen(db.engine, 'before_cursor_execute', count)
            try:
                r = auth_client.get(f'/api/v2/certificates?search={tag}&per_page=100')
            finally:
                with app.app_context():
                    event.remove(db.engine, 'before_cursor_execute', count)
            return seen, {d['id']: (d['revoked'], d['revoke_reason'], d['status'])
                          for d in r.get_json()['data']}

        rows(2)
        few, _ = listed()
        rows(6)
        many, shown = listed()
        from collections import Counter
        assert len(many) == len(few), sorted((Counter(many) - Counter(few)).items())[:6]
        assert {i: shown[i] for i in recorded} == {i: (True, 'certificateHold', 'revoked') for i in recorded}
        assert all(shown[i][0] is False for i in plain)


class TestALiftBetweenReadAndMarkWins:
    """A hold lifted while the hourly pass marks rows: the row ends unrevoked, never held
    without a record (which nothing would correct afterwards)."""

    def _held_by_record(self, app, issuer, cn):
        _, refid, ca_cert, ca_key = issuer
        real, key = _leaf(cn, ca_cert, ca_key, days=200)
        row_id = _store(app, real, refid, key=key)
        return row_id, _record(app, refid, real, reason='certificateHold', certificate_id=row_id)

    def test_the_pass_skips_a_record_deleted_after_it_read_it(self, app, issuer, monkeypatch):
        from sqlalchemy import delete
        from services.cert import issued_lookup
        row_id, record_id = self._held_by_record(app, issuer, 'lift-before-mark.example.test')
        read = issued_lookup.row_persisted_revocation

        def then_lifted(row):
            record = read(row)
            # Another worker's unhold commits between this read and the mark
            with db.engine.begin() as other:
                other.execute(delete(RevokedSerial).where(RevokedSerial.id == record_id))
            return record
        monkeypatch.setattr(issued_lookup, 'row_persisted_revocation', then_lifted)
        with app.app_context():
            marked = issued_lookup.apply_persisted_revocations({row_id})
            db.session.commit()
        assert marked == []
        assert _row(app, row_id) == (False, None, None)

    def test_an_unhold_after_the_mark_clears_the_row_it_did_not_read_held(
            self, app, auth_client, issuer, monkeypatch):
        from sqlalchemy import update
        from services.cert import issued_lookup
        row_id, record_id = self._held_by_record(app, issuer, 'mark-before-lift.example.test')
        lift = issued_lookup.lift_persisted_revocation

        def marked_meanwhile(*args, **kwargs):
            # The pass marks the row and commits after the unhold read it unrevoked
            with db.engine.begin() as other:
                other.execute(update(Certificate).where(Certificate.id == row_id).values(
                    revoked=True, revoke_reason='certificateHold', revoked_at=EARLY))
            return lift(*args, **kwargs)
        monkeypatch.setattr(issued_lookup, 'lift_persisted_revocation', marked_meanwhile)
        r = auth_client.post(f'/api/v2/certificates/{row_id}/unhold')
        assert r.status_code == 200, r.data
        assert _row(app, row_id) == (False, None, None)
        with app.app_context():
            assert db.session.get(RevokedSerial, record_id) is None


def _on_postgresql(app):
    with app.app_context():
        return db.engine.dialect.name == 'postgresql'


def _wait_for_a_lock_waiter(conn, seconds=5.0):
    """Whether another session of this worker waits on a lock within ``seconds`` (polled).
    The workers share the database: a waiter is ours when it holds locks on our schema's tables."""
    import time
    from sqlalchemy import text
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        conn.execute(text('SELECT pg_stat_clear_snapshot()'))  # the view is cached per transaction
        if conn.execute(text(
                "SELECT count(*) FROM pg_stat_activity a WHERE a.wait_event_type = 'Lock' "
                "AND a.datname = current_database() AND a.pid <> pg_backend_pid() AND EXISTS ("
                "SELECT 1 FROM pg_locks l JOIN pg_class c ON c.oid = l.relation "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE l.pid = a.pid AND l.granted AND n.nspname = current_schema())")).scalar():
            return True
        time.sleep(0.02)
    return False


class TestAFinalRevocationBetweenReadAndLift:
    """A final revocation committed after an unhold read the hold is never undone by it."""

    def _final_meanwhile(self, app, monkeypatch, row_id, record_id, where=('row', 'record')):
        from sqlalchemy import update
        from services.cert import issued_lookup
        read, done = issued_lookup.persisted_revocation, []

        def then_revoked(*args, **kwargs):
            # After the route's own check of the record, its last read before writing
            import sys
            found = read(*args, **kwargs)
            if sys._getframe(1).f_code.co_name == 'unhold_certificate' and not done:
                done.append(True)
                with db.engine.begin() as other:
                    if 'row' in where:
                        other.execute(update(Certificate).where(Certificate.id == row_id).values(
                            revoked=True, revoke_reason='keyCompromise', revoked_at=LATER))
                    if 'record' in where:
                        other.execute(update(RevokedSerial).where(RevokedSerial.id == record_id).values(
                            revoke_reason='keyCompromise', revoked_at=LATER))
            return found
        monkeypatch.setattr(issued_lookup, 'persisted_revocation', then_revoked)
        return done

    @pytest.mark.parametrize('row_held', [True, False])
    def test_the_unhold_is_refused_and_both_stay_final(self, app, auth_client, issuer, monkeypatch, row_held):
        _, refid, ca_cert, ca_key = issuer
        real, key = _leaf(f'final-meanwhile-{row_held}.example.test', ca_cert, ca_key, days=200)
        row_id = _store(app, real, refid, key=key)
        record_id = _record(app, refid, real, reason='certificateHold', certificate_id=row_id)
        if row_held:
            _held(app, row_id)
        done = self._final_meanwhile(app, monkeypatch, row_id, record_id)
        r = auth_client.post(f'/api/v2/certificates/{row_id}/unhold')
        assert done and r.status_code == 409, r.data
        assert _row(app, row_id) == (True, 'keyCompromise', LATER)
        with app.app_context():
            assert db.session.get(RevokedSerial, record_id).revoke_reason == 'keyCompromise'

    @pytest.mark.parametrize('where', ['row', 'record'])
    def test_either_final_alone_refuses_and_nothing_changes(self, app, auth_client, issuer, monkeypatch, where):
        _, refid, ca_cert, ca_key = issuer
        real, key = _leaf(f'final-only-{where}.example.test', ca_cert, ca_key, days=200)
        row_id = _store(app, real, refid, key=key)
        record_id = _record(app, refid, real, reason='certificateHold', certificate_id=row_id)
        _held(app, row_id)
        done = self._final_meanwhile(app, monkeypatch, row_id, record_id, where=(where,))
        r = auth_client.post(f'/api/v2/certificates/{row_id}/unhold')
        assert done and r.status_code == 409, r.data
        final = where == 'row'
        assert _row(app, row_id) == ((True, 'keyCompromise', LATER) if final else (True, 'certificateHold', EARLY))
        with app.app_context():
            assert db.session.get(RevokedSerial, record_id).revoke_reason == (
                'certificateHold' if final else 'keyCompromise')


class TestTheLockOrderOfAPassAndAnUnhold:

    def test_an_unhold_waiting_on_a_marking_pass_lifts_after_it(self, app, auth_client, issuer):
        """PostgreSQL: the pass holds the record and marks the row while the unhold waits: no deadlock."""
        import threading
        from sqlalchemy import select, update
        if not _on_postgresql(app):
            pytest.skip('row locks are PostgreSQL behaviour; SQLite serializes writers')
        _, refid, ca_cert, ca_key = issuer
        real, key = _leaf('lock-order.example.test', ca_cert, ca_key, days=200)
        row_id = _store(app, real, refid, key=key)
        record_id = _record(app, refid, real, reason='certificateHold', certificate_id=row_id)
        with app.app_context():
            engine = db.engine
        locked, outcome = threading.Event(), {}

        def marking_pass():
            try:
                with engine.connect() as conn:
                    with conn.begin():
                        conn.execute(select(RevokedSerial.id).where(RevokedSerial.id == record_id)
                                     .with_for_update(read=True))
                        locked.set()
                        outcome['waited'] = _wait_for_a_lock_waiter(conn)
                        conn.execute(update(Certificate).where(Certificate.id == row_id).values(
                            revoked=True, revoke_reason='certificateHold', revoked_at=EARLY))
            except Exception as e:  # the deadlock victim, if any
                outcome['error'] = repr(e)
        worker = threading.Thread(target=marking_pass)
        worker.start()
        locked.wait(10)
        r = auth_client.post(f'/api/v2/certificates/{row_id}/unhold')
        worker.join(30)
        assert 'error' not in outcome and outcome.get('waited'), outcome
        assert r.status_code == 200, r.data
        assert _row(app, row_id) == (False, None, None)
        with app.app_context():
            assert db.session.get(RevokedSerial, record_id) is None


class TestTheShareLockOfThePass:

    def test_a_pending_lift_makes_the_pass_wait_and_skip(self, app, issuer):
        """PostgreSQL: a record deleted by an uncommitted unhold is waited for, then not marked."""
        import threading
        from sqlalchemy import delete
        from services.cert import issued_lookup
        if not _on_postgresql(app):
            pytest.skip('row locks are PostgreSQL behaviour; SQLite serializes writers')
        _, refid, ca_cert, ca_key = issuer
        real, key = _leaf('share-lock.example.test', ca_cert, ca_key, days=200)
        row_id = _store(app, real, refid, key=key)
        record_id = _record(app, refid, real, reason='certificateHold', certificate_id=row_id)
        with app.app_context():
            engine = db.engine
        deleted, outcome = threading.Event(), {}

        def pending_lift():
            with engine.connect() as conn:
                with conn.begin():
                    conn.execute(delete(RevokedSerial).where(RevokedSerial.id == record_id))
                    deleted.set()
                    outcome['waited'] = _wait_for_a_lock_waiter(conn)
        worker = threading.Thread(target=pending_lift)
        worker.start()
        deleted.wait(10)
        with app.app_context():
            marked = issued_lookup.apply_persisted_revocations({row_id})
            db.session.commit()
        worker.join(30)
        assert outcome.get('waited') and marked == []
        assert _row(app, row_id) == (False, None, None)


def test_a_lift_committed_after_the_pass_reread_still_wins(app, issuer, monkeypatch):
    """SQLite opens its write transaction at the mark: the mark itself checks the record."""
    from sqlalchemy import delete
    from services.cert import issued_lookup
    if _on_postgresql(app):
        pytest.skip("PostgreSQL: the re-read's share lock makes such a lift wait (test above)")
    _, refid, ca_cert, ca_key = issuer
    real, key = _leaf('lift-after-reread.example.test', ca_cert, ca_key, days=200)
    row_id = _store(app, real, refid, key=key)
    record_id = _record(app, refid, real, reason='certificateHold', certificate_id=row_id)
    reread = issued_lookup._record_still_held

    def then_lifted(record):
        still = reread(record)
        with db.engine.begin() as other:
            other.execute(delete(RevokedSerial).where(RevokedSerial.id == record_id))
        return still
    monkeypatch.setattr(issued_lookup, '_record_still_held', then_lifted)
    with app.app_context():
        assert issued_lookup.apply_persisted_revocations({row_id}) == []
        db.session.commit()
    assert _row(app, row_id) == (False, None, None)
