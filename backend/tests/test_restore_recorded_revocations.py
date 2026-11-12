"""A restore and the revocation records: the rows it writes take the revocation their CA
records (as the hourly pass would), and the holds an older release left behind a lift,
named as such by the archive alone, are not restored (SQLite and PostgreSQL)."""
from datetime import datetime

import pytest

from models import db
from tests.test_backup_cross_installation import PASSWORD, _service
from tests.test_backup_hostile_corpus import _reseal
from tests.test_restore_replace_dependents import (  # noqa: F401  (fixture)
    _authority_row, _certificate_row, _restore, _snapshot, target,
)

EARLY = datetime(2026, 1, 2, 3, 4, 5)
OLD, RECENT = '2.253', '2.254'


def _record(row, reason, *, linked=True):
    from models import RevokedSerial
    from utils.serial_format import canonical_serial
    record = RevokedSerial(caref=row.caref, serial_number=canonical_serial(row.serial_number),
                           revoked_at=EARLY, revoke_reason=reason, valid_to=row.valid_to,
                           certificate_id=row.id if linked else None)
    db.session.add(record)
    db.session.flush()
    return record


def _revoked(row, reason):
    row.revoked, row.revoke_reason, row.revoked_at = True, reason, EARLY


def _version(blob, version):
    data = _service()._decrypt_framed(blob, PASSWORD)[1]
    data['metadata']['ucm_version'] = version
    return _reseal(blob, data)


def _state(refid):
    """(row revoked, row reason, reasons of the records of its serial under its CA)."""
    from models import Certificate, RevokedSerial
    from utils.serial_format import canonical_serial
    db.session.expire_all()
    row = Certificate.query.filter_by(refid=refid).one()
    reasons = sorted(r.revoke_reason for r in RevokedSerial.query.filter_by(
        caref=row.caref, serial_number=canonical_serial(row.serial_number)))
    return bool(row.revoked), row.revoke_reason, reasons


def _audited(refid):
    from models import AuditLog, Certificate
    row = Certificate.query.filter_by(refid=refid).one()
    return [e.details for e in AuditLog.query.filter_by(resource_type='certificate', resource_id=str(row.id))
            if 'origin: recorded revocation' in (e.details or '')]


class TestTheRowsARestoreWritesTakeTheirRecords:

    @pytest.mark.parametrize('reason', ['keyCompromise', 'certificateHold'])
    def test_an_archive_older_than_the_revocation(self, target, reason):
        issuer = _authority_row('restore-align-ca')
        row = _certificate_row('restore-align', issuer)
        blob = _snapshot()
        _revoked(row, reason)
        _record(row, reason)
        # A row the archive does not carry is the hourly pass's, not the restore's
        _record(_certificate_row('restore-not-written', issuer), reason)
        db.session.commit()

        results = _restore(blob, mode='merge')

        assert _state('restore-align') == (True, reason, [reason])
        # A final revocation here is kept by the merge itself; a hold is written back from its record
        marked = 0 if reason == 'keyCompromise' else 1
        assert results['revoked_from_records'] == marked
        assert len(_audited('restore-align')) == marked
        assert _state('restore-not-written') == (False, None, [reason])


class TestAnOlderArchiveLeavesItsLiftedHoldsOut:

    def _one(self, refid, *, row_reason=None, record_reason='certificateHold', version=OLD, record=None):
        """An archive of one certificate and one linked record, restored over an empty base."""
        from models import Certificate, RevokedSerial
        issuer = _authority_row(f'{refid}-ca')
        row = _certificate_row(refid, issuer)
        if row_reason:
            _revoked(row, row_reason)
        made = _record(row, record_reason)
        if record:
            record(made)
        blob = _version(_snapshot(), version)
        RevokedSerial.query.delete()
        db.session.delete(Certificate.query.filter_by(refid=refid).one())
        db.session.commit()
        return _restore(blob, mode='merge')

    def test_a_leftover_is_not_restored(self, target):
        results = self._one('lifted-leftover')
        assert _state('lifted-leftover') == (False, None, [])
        assert results['lifted_holds_skipped'] == 1

    def test_a_real_hold_is_kept(self, target):
        results = self._one('lifted-real-hold', row_reason='certificateHold')
        assert _state('lifted-real-hold') == (True, 'certificateHold', ['certificateHold'])
        assert results['lifted_holds_skipped'] == 0

    def test_a_final_record_linked_to_an_unrevoked_row_is_kept(self, target):
        self._one('lifted-final', record_reason='keyCompromise')
        assert _state('lifted-final') == (True, 'keyCompromise', ['keyCompromise'])

    def test_a_hold_of_another_serial_linked_to_the_row_is_kept(self, target):
        """The record of a serial renewed away in place stays linked to the row."""
        def renewed_away(record):
            record.serial_number = str(int(record.serial_number) + 1)
        self._one('lifted-other-serial', record=renewed_away)
        from models import Certificate, RevokedSerial
        row = Certificate.query.filter_by(refid='lifted-other-serial').one()
        assert [r.certificate_id for r in RevokedSerial.query.filter_by(caref=row.caref)] == [row.id]

    def test_a_leftover_under_a_twin_of_the_key_is_not_restored(self, target):
        """A second record of the CA's subject and key (a re-signed root) in the archive."""
        from models import CA

        def under_a_twin(record):
            ca = CA.query.filter_by(refid=record.caref).one()
            db.session.add(CA(refid='lifted-twin', descr='lifted-twin', url_slug='lifted-twin', crt=ca.crt,
                              subject=ca.subject, issuer=ca.issuer, serial_number=ca.serial_number))
            db.session.flush()
            record.caref = 'lifted-twin'
        results = self._one('lifted-twin-leaf', record=under_a_twin)
        assert results['lifted_holds_skipped'] == 1

    def test_a_hold_under_another_key_is_kept(self, target):
        other = _authority_row('lifted-elsewhere-ca')[0].refid

        def elsewhere(record):
            record.caref = other
        self._one('lifted-other-key', record=elsewhere)
        from models import RevokedSerial
        assert RevokedSerial.query.filter_by(caref=other).count() == 1

    @pytest.mark.parametrize('version', [RECENT, '3.0-dev'])
    def test_a_recent_archive_keeps_a_linked_hold(self, target, version):
        results = self._one('lifted-recent', version=version)
        assert _state('lifted-recent') == (True, 'certificateHold', ['certificateHold'])
        assert results['lifted_holds_skipped'] == 0

    def test_a_live_hold_the_archive_does_not_carry_is_left_alone(self, target):
        issuer = _authority_row('live-hold-ca')
        row = _certificate_row('live-hold', issuer)
        blob = _version(_snapshot(), OLD)
        _record(row, 'certificateHold')
        db.session.commit()

        _restore(blob, mode='merge')

        assert _state('live-hold') == (True, 'certificateHold', ['certificateHold'])


@pytest.mark.parametrize('version, older', [
    (None, True), ('', True), ('unknown', True), ('1.9', True), ('2.253', True), ('v2.200', True),
    ('2.254-dev', False), ('2.254', False), ('2.300', False), ('3.0-dev', False), ('3.1', False),
])
def test_which_archive_may_hold_lifted_holds(version, older):
    from services.backup.restore.repairs import archive_may_hold_lifted_holds
    metadata = {} if version is None else {'ucm_version': version}
    assert archive_may_hold_lifted_holds({'metadata': metadata}) is older
