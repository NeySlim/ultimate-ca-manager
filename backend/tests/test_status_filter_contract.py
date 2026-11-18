"""A status filter answers about the status asked for, or refuses.

Every listing compared the query parameter against lowercase literals with
`==`, and none of them said so or checked. `?status=Expired` -- the spelling
the CA screens use for the very same idea, because `models/ca.py` publishes
`Active` / `Pending` / `Revoked` / `Expired` while `models/certificate.py`
publishes `valid` / `expiring` / `expired` / `revoked` -- matched no branch
anywhere, and the three listings then did three different things with that:

* `/api/v2/certificates` collected no conditions, and the `if conditions:`
  guard skipped the filter, so the caller asking for expired certificates
  received **every** certificate, revoked and valid alike;
* `/api/v2/user-certificates` matched no row and dropped them all, so the
  caller received **nothing** -- while `pagination.total` kept reporting the
  unfiltered count, giving "0 of 47";
* `/api/v2/ssh/certificates` behaved like the first.

Same input, opposite answers, no error from any of them. The first is the
one that matters: a filter that silently turns itself off hands back more
than was asked for.
"""
import json

import pytest

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')


LISTINGS = (
    '/api/v2/certificates',
    '/api/v2/user-certificates',
    '/api/v2/ssh/certificates',
)


def _rows(response):
    body = response.get_json() or {}
    data = body.get('data')
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ('items', 'certificates'):
            if isinstance(data.get(key), list):
                return data[key]
    raise AssertionError(f'no rows in {json.dumps(body)[:200]}')


@pytest.fixture(scope='module')
def a_mixed_bag(create_cert, auth_client):
    """One valid certificate and one revoked one, so a filter has work."""
    keep = create_cert(cn='status-filter-keep.example.com')
    gone = create_cert(cn='status-filter-revoked.example.com')
    auth_client.post(f'/api/v2/certificates/{gone["id"]}/revoke',
                     data=json.dumps({'reason': 'superseded'}),
                     content_type='application/json')
    return keep, gone


class TestAFilterNeverQuietlyTurnsItselfOff:
    @pytest.mark.parametrize('route', LISTINGS)
    @pytest.mark.parametrize('status', ['banana', 'Signed', 'Active', ''])
    def test_a_status_it_does_not_know_is_refused(
            self, auth_client, route, status):
        r = auth_client.get(f'{route}?status={status}')
        assert r.status_code == 400, (
            f'{route} answered {r.status_code} for status={status!r}, which '
            'matches no branch; the filter was dropped and the caller got '
            'rows it did not ask for')

    @pytest.mark.parametrize('route', LISTINGS)
    def test_the_refusal_says_what_is_accepted(self, auth_client, route):
        r = auth_client.get(f'{route}?status=banana')
        message = json.dumps(r.get_json() or {}).lower()
        assert 'expired' in message and 'revoked' in message, (
            f'{route} refused without naming the statuses it does accept: '
            f'{message[:200]}')

    @pytest.mark.parametrize('route', LISTINGS)
    def test_an_unknown_status_beside_a_known_one_is_still_refused(
            self, auth_client, route):
        r = auth_client.get(f'{route}?status=revoked&status=banana')
        assert r.status_code == 400, (
            f'{route} kept the half it understood and answered anyway, which '
            'is the narrower list the caller did not ask for')


class TestTheSpellingIsNotTheQuestion:
    """The two halves of the product spell the same idea differently, so the
    filter takes either and answers the same."""

    @pytest.mark.parametrize('route', LISTINGS)
    @pytest.mark.parametrize('spelling', ['revoked', 'REVOKED', 'Revoked'])
    def test_the_same_status_however_it_is_written(
            self, auth_client, a_mixed_bag, route, spelling):
        canonical = auth_client.get(f'{route}?status=revoked')
        written = auth_client.get(f'{route}?status={spelling}')
        assert written.status_code == 200, written.data
        assert len(_rows(written)) == len(_rows(canonical)), (
            f'{route} answered {spelling!r} with a different number of rows '
            'than it answered "revoked" with')

    @pytest.mark.parametrize('route', LISTINGS)
    def test_the_ca_spelling_of_expired_asks_the_same_question(
            self, auth_client, a_mixed_bag, route):
        """`Expired` is how `models/ca.py` writes it, and it used to leave
        `/api/v2/certificates` returning every row and
        `/api/v2/user-certificates` returning none."""
        lower = auth_client.get(f'{route}?status=expired&per_page=100')
        upper = auth_client.get(f'{route}?status=Expired&per_page=100')
        assert upper.status_code == 200, upper.data
        assert len(_rows(upper)) == len(_rows(lower)), (
            f'{route}: "Expired" and "expired" are the same question and got '
            f'{len(_rows(upper))} and {len(_rows(lower))} rows')

    def test_the_ca_spelling_does_not_return_the_whole_table(
            self, auth_client, a_mixed_bag):
        # Narrowed to this fixture's rows: a full run leaves over a page of others
        asked = _rows(auth_client.get(
            '/api/v2/certificates?status=Expired&search=status-filter-&per_page=100'))
        everything = _rows(auth_client.get(
            '/api/v2/certificates?search=status-filter-&per_page=100'))
        assert len(asked) < len(everything), (
            'asking for the expired ones by the CA spelling handed back '
            'every certificate there is')


class TestAKnownStatusStillFilters:
    """The refusal must not have cost the filter its day job."""

    def test_revoked_excludes_the_valid_one(self, auth_client, a_mixed_bag):
        keep, gone = a_mixed_bag
        # Narrowed to this fixture's two rows: the default page is 20 long,
        # and a full run leaves enough revoked certificates that the one
        # made here lands on a later page.
        rows = _rows(auth_client.get(
            '/api/v2/certificates?status=revoked&search=status-filter-'
            '&per_page=100'))
        names = {row.get('common_name') for row in rows}
        assert gone['common_name'] in names
        assert keep['common_name'] not in names

    def test_asking_for_a_status_is_not_asking_for_everything(
            self, auth_client, a_mixed_bag):
        filtered = _rows(auth_client.get(
            '/api/v2/certificates?status=revoked&search=status-filter-&per_page=100'))
        everything = _rows(auth_client.get(
            '/api/v2/certificates?search=status-filter-&per_page=100'))
        assert len(filtered) < len(everything), (
            'the filter returned as much as no filter at all')

    @pytest.mark.parametrize('status', ['valid', 'expiring', 'expired',
                                        'revoked', 'orphan', 'archived'])
    def test_every_documented_status_is_accepted(self, auth_client, status):
        r = auth_client.get(f'/api/v2/certificates?status={status}')
        assert r.status_code == 200, (
            f'{status} is in the vocabulary and was refused: {r.data[:200]}')


class TestTheVocabularyIsWrittenDownOnce:
    def test_the_listing_accepts_exactly_what_the_module_publishes(self):
        from utils.cert_status import CERTIFICATE_STATUS_FILTERS
        assert CERTIFICATE_STATUS_FILTERS == (
            'valid', 'expiring', 'expired', 'revoked', 'orphan', 'archived')

    def test_a_status_is_normalised_not_guessed(self):
        from utils.cert_status import (CERTIFICATE_STATUS_FILTERS,
                                       normalize_status_filters)
        names, unknown = normalize_status_filters(
            ['Expired', ' REVOKED'], CERTIFICATE_STATUS_FILTERS)
        assert names == ['expired', 'revoked']
        assert unknown == []

    def test_an_unknown_status_is_reported_not_dropped(self):
        from utils.cert_status import (CERTIFICATE_STATUS_FILTERS,
                                       normalize_status_filters)
        names, unknown = normalize_status_filters(
            ['expired', 'banana'], CERTIFICATE_STATUS_FILTERS)
        assert unknown == ['banana'], (
            'dropping it silently is how the filter turned itself off')
