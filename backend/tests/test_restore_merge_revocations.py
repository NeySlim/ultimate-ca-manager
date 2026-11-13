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
