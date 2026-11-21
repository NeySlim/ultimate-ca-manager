"""A merge restore and the revocations made here: none is lowered, final or suspension, for a
certificate or a CA; a graver archive still wins (SQLite and PostgreSQL)."""
from datetime import datetime

import pytest

from models import db
from tests.test_restore_recorded_revocations import _record, _state
from tests.test_restore_replace_dependents import (  # noqa: F401  (fixture)
    _authority_row, _certificate_row, _restore, _snapshot, _user, target,
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

    def test_a_hold_carried_by_the_row_alone_survives_a_valid_archive(self, target):
        """Lifting a hold is an authenticated act, and the hold here is the newer state."""
        issuer = _authority_row('merge-hold-ca')
        row = _certificate_row('merge-row-hold', issuer)
        blob = _snapshot()
        _revoke(row, 'certificateHold', LATER)
        db.session.commit()

        _restore(blob, mode='merge')

        assert _row_revocation('merge-row-hold') == (True, 'certificateHold', LATER)

    def test_a_lift_in_progress_here_is_no_revocation_to_keep(self, target):
        """A row staged removeFromCRL by an unhold is being lifted: a valid archive agrees."""
        issuer = _authority_row('merge-lifting-ca')
        row = _certificate_row('merge-lifting', issuer)
        blob = _snapshot()
        _revoke(row, 'removeFromCRL', LATER)
        db.session.commit()

        _restore(blob, mode='merge')

        assert _row_revocation('merge-lifting') == (False, None, None)

    def test_a_final_revocation_of_the_archive_replaces_a_hold_here(self, target):
        issuer = _authority_row('merge-hold-final-ca')
        row = _certificate_row('merge-hold-final', issuer)
        _revoke(row, 'keyCompromise', LATER)
        blob = _snapshot()
        _revoke(row, 'certificateHold', EARLY)
        db.session.commit()

        _restore(blob, mode='merge')

        assert _row_revocation('merge-hold-final') == (True, 'keyCompromise', LATER)

    @pytest.mark.parametrize('archived_at, here_at', [(EARLY, LATER), (LATER, EARLY)])
    def test_between_two_holds_the_earlier_date_stays(self, target, archived_at, here_at):
        """As between two final revocations of one reason: the earlier date."""
        refid = f'merge-two-holds-{archived_at.month}'
        issuer = _authority_row(f'{refid}-ca')
        row = _certificate_row(refid, issuer)
        _revoke(row, 'certificateHold', archived_at)
        blob = _snapshot()
        _revoke(row, 'certificateHold', here_at)
        db.session.commit()

        _restore(blob, mode='merge')

        assert _row_revocation(refid) == (True, 'certificateHold', EARLY)

    def test_a_replace_restore_takes_the_archive_over_a_hold_here(self, target):
        """Only a merge keeps what was done here: a replace restore puts the archive back."""
        _user('replace-hold-admin')
        issuer = _authority_row('replace-hold-ca')
        row = _certificate_row('replace-row-hold', issuer)
        blob = _snapshot()
        _revoke(row, 'certificateHold', LATER)
        db.session.commit()

        _restore(blob, mode='replace')

        assert _row_revocation('replace-row-hold') == (False, None, None)


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

    def test_a_hold_here_survives_a_valid_archive(self, target):
        from models import CA
        ca = _authority_row('merge-ca-hold')[0]
        blob = _snapshot()
        _revoke(ca, 'certificateHold', LATER)
        db.session.commit()

        _restore(blob, mode='merge')

        db.session.expire_all()
        ca = CA.query.filter_by(refid='merge-ca-hold').one()
        assert (bool(ca.revoked), ca.revoke_reason, ca.revoked_at) == (True, 'certificateHold', LATER)

    def test_a_final_archive_replaces_a_hold_here(self, target):
        from models import CA
        ca = _authority_row('merge-ca-hold-final')[0]
        _revoke(ca, 'superseded', LATER)
        blob = _snapshot()
        _revoke(ca, 'certificateHold', EARLY)
        db.session.commit()

        _restore(blob, mode='merge')

        db.session.expire_all()
        ca = CA.query.filter_by(refid='merge-ca-hold-final').one()
        assert (bool(ca.revoked), ca.revoke_reason, ca.revoked_at) == (True, 'superseded', LATER)

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
