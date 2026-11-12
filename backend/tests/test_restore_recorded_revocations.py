"""A restore and the revocation records: the rows it writes take the revocation their CA
records, as the hourly pass would (SQLite and PostgreSQL)."""
from datetime import datetime

import pytest

from models import db
from tests.test_restore_replace_dependents import (  # noqa: F401  (fixture)
    _authority_row, _certificate_row, _restore, _snapshot, target,
)

EARLY = datetime(2026, 1, 2, 3, 4, 5)


def _serial(row):
    import base64
    from cryptography import x509
    return x509.load_pem_x509_certificate(base64.b64decode(row.crt)).serial_number


def _record(row, reason, *, linked=True):
    from models import RevokedSerial
    record = RevokedSerial(caref=row.caref, serial_number=str(_serial(row)),
                           revoked_at=EARLY, revoke_reason=reason, valid_to=row.valid_to,
                           certificate_id=row.id if linked else None)
    db.session.add(record)
    db.session.flush()
    return record


def _revoked(row, reason):
    row.revoked, row.revoke_reason, row.revoked_at = True, reason, EARLY


def _state(refid):
    """(row revoked, row reason, reasons of the records of its serial under its CA)."""
    from models import Certificate, RevokedSerial
    from utils.serial_format import unambiguous_serial_spellings
    db.session.expire_all()
    row = Certificate.query.filter_by(refid=refid).one()
    reasons = sorted(r.revoke_reason for r in RevokedSerial.query.filter(
        RevokedSerial.caref == row.caref,
        RevokedSerial.serial_number.in_(unambiguous_serial_spellings(_serial(row)))))
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
        assert results['revoked_from_records'] == 1
        assert len(_audited('restore-align')) == 1
        assert _state('restore-not-written') == (False, None, [reason])
