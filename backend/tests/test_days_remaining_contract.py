"""The server publishes the number the screens were written to read.

`details.expiredDaysAgo` -- "Certificate expired {{count}} days ago" -- ships
in all nine locales and was unreachable, because `Certificate.days_remaining`
clamped at zero. A certificate that expired a year ago and one expiring this
afternoon both answered `0`. The one value that did go negative was `-1`,
which meant "this row has no expiry date" and which every `< 0` reader took
for "long expired".

`contracts/days_remaining_contract.json` is the table;
`frontend/src/lib/__tests__/expiryContract.test.js` holds the browser to the
other half of it.
"""
import json
import os
from datetime import timedelta

import pytest

from utils.datetime_utils import utc_now
from utils.days_remaining import days_remaining, has_expired

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONTRACT = os.path.join(_REPO, 'contracts', 'days_remaining_contract.json')

with open(CONTRACT) as _fh:
    _DOC = json.load(_fh)


def _published_cases():
    for row in _DOC['published']:
        yield pytest.param(row['hours_from_now'], row['expected'],
                           id=f'{row["hours_from_now"]}h')


def _bucket_cases():
    for row in _DOC['buckets']:
        yield pytest.param(row['days_remaining'], row['bucket'],
                           id=f'{row["days_remaining"]}')


class TestTheServerPublishesWhatTheContractSays:
    @pytest.mark.parametrize('hours,expected', list(_published_cases()))
    def test_the_helper_answers_the_contract(self, hours, expected):
        now = utc_now()
        valid_to = None if hours is None else now + timedelta(hours=hours)
        assert days_remaining(valid_to, now) == expected

    def test_no_expiry_date_is_not_a_number(self):
        assert days_remaining(None) is None, (
            'a row with no expiry date used to answer -1, and every reader '
            'testing "< 0" called it expired')

    def test_no_expiry_date_has_not_expired(self):
        assert has_expired(None) is False

    @pytest.mark.parametrize('hours,expected', list(_published_cases()))
    def test_expiry_agrees_with_the_sign(self, hours, expected):
        now = utc_now()
        valid_to = None if hours is None else now + timedelta(hours=hours)
        assert has_expired(valid_to, now) is (
            expected is not None and expected <= 0)


class TestZeroIsTheInstantOfExpiryAndNothingElse:
    """The floor was what made `0` ambiguous: anything from a full day left
    down to the moment of expiry landed on it, so the detail panel said
    expired while the badge beside it said expiring."""

    @pytest.mark.parametrize('hours', [1, 6, 12, 23])
    def test_a_certificate_with_hours_left_is_not_expired(self, hours):
        now = utc_now()
        left = days_remaining(now + timedelta(hours=hours), now)
        assert left == 1, f'{hours}h left reported as {left}'
        assert has_expired(now + timedelta(hours=hours), now) is False

    @pytest.mark.parametrize('hours', [1, 6, 12, 23])
    def test_a_certificate_past_by_hours_is_expired(self, hours):
        now = utc_now()
        left = days_remaining(now - timedelta(hours=hours), now)
        assert left == -1, f'{hours}h past reported as {left}'
        assert has_expired(now - timedelta(hours=hours), now) is True


class TestEveryEndpointPublishesTheSameField:
    """`/api/v2/certificates` clamped, `/api/v2/user-certificates` and
    `/api/v2/truststore/expiring` did not, so the same field name meant two
    different things depending on which route served the row."""

    def test_an_expired_certificate_reports_a_negative_number(
            self, app, create_cert):
        from models import Certificate, db

        cert = create_cert(cn='days-contract-expired.example.com')
        with app.app_context():
            row = db.session.get(Certificate, cert['id'])
            # Half a day off the boundary: the property reads the clock
            # again, and on an exact multiple of a day the microseconds
            # between writing the date and reading it back decide the answer.
            row.valid_to = utc_now() - timedelta(days=412, hours=12)
            db.session.commit()
            assert row.days_remaining == -413, (
                'the clamp made a certificate that expired more than a year '
                f'ago indistinguishable from one expiring today: '
                f'{row.days_remaining}')

    def test_a_certificate_with_no_expiry_date_reports_nothing(
            self, app, create_cert):
        from models import Certificate, db

        cert = create_cert(cn='days-contract-noexpiry.example.com')
        with app.app_context():
            row = db.session.get(Certificate, cert['id'])
            row.valid_to = None
            db.session.commit()
            assert row.days_remaining is None
            assert row.to_dict()['days_remaining'] is None

    def test_the_serialised_row_carries_the_same_number(
            self, app, create_cert):
        from models import Certificate, db

        cert = create_cert(cn='days-contract-serialised.example.com')
        with app.app_context():
            row = db.session.get(Certificate, cert['id'])
            row.valid_to = utc_now() - timedelta(days=5, hours=12)
            db.session.commit()
            assert row.to_dict()['days_remaining'] == -6


class TestTheBucketsTheContractNames:
    """The classification the screens apply, checked here so the browser test
    and this one cannot drift apart on what a number means."""

    @pytest.mark.parametrize('days,bucket', list(_bucket_cases()))
    def test_the_bucket_matches(self, days, bucket):
        if days is None:
            assert bucket == 'none'
            return
        if days <= 0:
            assert bucket == 'expired'
        elif days <= 30:
            assert bucket == 'expiring'
        else:
            assert bucket == 'valid'
