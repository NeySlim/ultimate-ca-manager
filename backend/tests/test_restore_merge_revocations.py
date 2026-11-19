"""A merge restore and the revocations made here: a final one is never lowered, for a
certificate or a CA, and a suspension gives way to the archive (SQLite and PostgreSQL)."""
from datetime import datetime

import pytest

from models import db
from tests.test_restore_recorded_revocations import _record, _state
from tests.test_restore_replace_dependents import (  # noqa: F401  (fixture)
    _authority_row, _certificate_row, _restore, _snapshot, target,
)

EARLY = datetime(2026, 1, 2, 3, 4, 5)
LATER = datetime(2026, 2, 3, 4, 5, 6)


def _revoke(row, reason, at):
    row.revoked, row.revoke_reason, row.revoked_at = True, reason, at


def _row_revocation(refid):
    from models import Certificate
    db.session.expire_all()
    row = Certificate.query.filter_by(refid=refid).one()
    return bool(row.revoked), row.revoke_reason, row.revoked_at


class TestACertificateRevokedHere:

    def test_between_equal_reasons_the_earlier_date_stays(self, target):
        issuer = _authority_row('merge-tie-ca')
        row = _certificate_row('merge-tie', issuer)
        _revoke(row, 'superseded', LATER)
        blob = _snapshot()
        _revoke(row, 'superseded', EARLY)
        db.session.commit()

        _restore(blob, mode='merge')

        assert _row_revocation('merge-tie') == (True, 'superseded', EARLY)

    def test_a_graver_record_of_the_archive_sets_the_row_reason(self, target):
        """Valid in the archive with a compromise recorded, superseded here: compromise everywhere."""
        from models import CA, Certificate
        from services.cert.issued_lookup import answered_revocation
        issuer = _authority_row('merge-graver-ca')
        row = _certificate_row('merge-graver', issuer)
        record = _record(row, 'keyCompromise')
        blob = _snapshot()
        _revoke(row, 'superseded', LATER)
        record.revoke_reason, record.revoked_at = 'superseded', LATER
        db.session.commit()

        _restore(blob, mode='merge')

        assert _state('merge-graver') == (True, 'keyCompromise', ['keyCompromise'])
        row = Certificate.query.filter_by(refid='merge-graver').one()
        ca = CA.query.filter_by(refid=row.caref).one()
        assert answered_revocation(row, ca).revoke_reason == 'keyCompromise'

    def test_a_hold_carried_by_the_row_alone_gives_way_to_a_valid_archive(self, target):
        """Suspensions are reversible: what is not final is the archive's in a merge."""
        issuer = _authority_row('merge-hold-ca')
        row = _certificate_row('merge-row-hold', issuer)
        blob = _snapshot()
        _revoke(row, 'certificateHold', LATER)
        db.session.commit()

        _restore(blob, mode='merge')

        assert _state('merge-row-hold') == (False, None, [])


class TestACaRevokedHere:

    @pytest.mark.parametrize('archived', [None, 'certificateHold', 'superseded'])
    def test_the_archive_never_lowers_it(self, target, archived):
        from models import CA
        refid = f'merge-ca-{archived or "valid"}'
        ca = _authority_row(refid)[0]
        if archived:
            _revoke(ca, archived, LATER)
        blob = _snapshot()
        _revoke(ca, 'keyCompromise', LATER)
        db.session.commit()

        _restore(blob, mode='merge')

        db.session.expire_all()
        ca = CA.query.filter_by(refid=refid).one()
        assert (bool(ca.revoked), ca.revoke_reason, ca.revoked_at) == (True, 'keyCompromise', LATER)

    def test_a_graver_archive_still_wins(self, target):
        from models import CA
        ca = _authority_row('merge-ca-graver')[0]
        _revoke(ca, 'keyCompromise', EARLY)
        blob = _snapshot()
        _revoke(ca, 'superseded', LATER)
        db.session.commit()

        _restore(blob, mode='merge')

        db.session.expire_all()
        ca = CA.query.filter_by(refid='merge-ca-graver').one()
        assert (bool(ca.revoked), ca.revoke_reason, ca.revoked_at) == (True, 'keyCompromise', EARLY)
