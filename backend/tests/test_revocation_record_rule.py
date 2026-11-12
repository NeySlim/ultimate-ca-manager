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

    def test_no_renewal_event_and_no_binding_follows(self, app, auth_client, issuer, monkeypatch):
        from services import binding_attention, webhook_service
        _, refid, ca_cert, ca_key = issuer
        current, key = _leaf('revoked-update.example.test', ca_cert, ca_key)
        row_id = _store(app, current, refid, key=key)
        revoked, _ = _leaf('revoked-update.example.test', ca_cert, ca_key, key=key)
        _record(app, refid, revoked)
        renewed, followed = [], []
        monkeypatch.setattr(webhook_service, 'emit_cert_renewed', lambda *a, **k: renewed.append(a))
        monkeypatch.setattr(binding_attention, 'follow_key', lambda *a, **k: followed.append(a) or False)
        r = _import(auth_client, revoked, key)
        assert r.status_code == 200, r.data
        assert _row(app, row_id) == (True, 'keyCompromise', EARLY)
        assert renewed == [] and followed == []


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


class TestARecordAloneHoldsItsRow:
    """A suspension record linked to its unrevoked row of the same serial is a hold, with no
    exception (migration 154 deleted, once, those an earlier lift left behind)."""

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
        from tests.test_acme_revocation_parallel_paths import _es256_revocation
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
