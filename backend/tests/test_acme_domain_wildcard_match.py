"""A domain registered with its wildcard spelling must be found again (#352).

Both mapping tables accept ``*.custom`` on the way in, and neither could find
it afterwards: the lookup stripped the wildcard from the domain it was asked
about, then compared the result to the stored text. The entry matched nothing
at all, not even itself, and every order for that zone was signed by the
default CA while the operator watched a mapping that said otherwise.
"""
import json

import pytest

from models import db
from models.acme_models import AcmeDomain, AcmeLocalDomain
from api.v2.acme_local_domains import find_local_domain_ca
from api.v2.acme_domains import find_provider_for_domain
from services.acme import domain_match


@pytest.fixture(scope='module')
def _mapping_ids(app, create_ca):
    """Real CAs and a DNS provider for the rows to point at, keyed by the
    numbers the tests use: PostgreSQL enforces both foreign keys."""
    from models.acme_models import DnsProvider

    from models import CA
    from tests.seeded_rows import delete_cas

    ids = {n: create_ca(cn=f'Wildcard match CA {n}')['id'] for n in (2, 3, 7, 8, 9)}
    with app.app_context():
        provider = DnsProvider.query.filter_by(name='wildcard-match-provider').first()
        if provider is None:
            provider = DnsProvider(name='wildcard-match-provider', provider_type='cloudflare')
            db.session.add(provider)
            db.session.commit()
        ids['provider'] = provider.id
    yield ids
    with app.app_context():
        db.session.rollback()
        AcmeDomain.query.filter_by(dns_provider_id=ids['provider']).delete()
        DnsProvider.query.filter_by(id=ids['provider']).delete()
        delete_cas(CA.query.filter(CA.id.in_([ids[n] for n in (2, 3, 7, 8, 9)])))
        db.session.commit()


@pytest.fixture
def clean_domains(app, _mapping_ids):
    """These tests read both mapping tables as a whole."""
    def wipe():
        with app.app_context():
            AcmeLocalDomain.query.delete()
            AcmeDomain.query.delete()
            db.session.commit()

    wipe()
    yield _mapping_ids
    wipe()


class TestTheWildcardSpellingIsFoundAgain:
    @pytest.mark.parametrize('asked', ['host.custom', '*.custom', 'custom'])
    def test_an_entry_stored_as_a_wildcard_resolves(
            self, app, clean_domains, asked):
        with app.app_context():
            db.session.add(AcmeLocalDomain(domain='*.custom', issuing_ca_id=clean_domains[7]))
            db.session.commit()

            assert find_local_domain_ca(asked) == clean_domains[7]

    @pytest.mark.parametrize('asked', ['host.custom', '*.custom', 'custom'])
    def test_the_bare_spelling_still_resolves(self, app, clean_domains, asked):
        with app.app_context():
            db.session.add(AcmeLocalDomain(domain='custom', issuing_ca_id=clean_domains[7]))
            db.session.commit()

            assert find_local_domain_ca(asked) == clean_domains[7]

    def test_the_dns_table_answers_the_same_way(self, app, clean_domains):
        with app.app_context():
            db.session.add(AcmeDomain(domain='*.example.test',
                                      dns_provider_id=clean_domains['provider'], issuing_ca_id=clean_domains[9]))
            db.session.commit()

            result = find_provider_for_domain('api.example.test')

        assert result is not None, 'the wildcard entry was not found'
        assert result['issuing_ca_id'] == clean_domains[9]
        assert result['matched_domain'] == '*.example.test'

    def test_an_unrelated_domain_still_matches_nothing(
            self, app, clean_domains):
        with app.app_context():
            db.session.add(AcmeLocalDomain(domain='*.custom', issuing_ca_id=clean_domains[7]))
            db.session.commit()

            assert find_local_domain_ca('elsewhere.test') is None
            assert find_local_domain_ca('notcustom') is None

    def test_a_sibling_zone_is_not_swallowed(self, app, clean_domains):
        """`*.custom` covers what is under `custom`, not a name that merely
        ends with those letters."""
        with app.app_context():
            db.session.add(AcmeLocalDomain(domain='*.custom', issuing_ca_id=clean_domains[7]))
            db.session.commit()

            assert find_local_domain_ca('mycustom') is None


class TestTheMostSpecificEntryDecides:
    def test_a_subdomain_entry_wins_over_its_parent(self, app, clean_domains):
        with app.app_context():
            db.session.add(AcmeLocalDomain(domain='plain.test', issuing_ca_id=clean_domains[2]))
            db.session.add(
                AcmeLocalDomain(domain='deep.plain.test', issuing_ca_id=clean_domains[3]))
            db.session.commit()

            assert find_local_domain_ca('host.deep.plain.test') == clean_domains[3]
            assert find_local_domain_ca('host.plain.test') == clean_domains[2]

    def test_the_bare_spelling_wins_over_the_wildcard_at_the_same_level(
            self, app, clean_domains):
        """Registering both is refused, but a database that already holds the
        two must still give one stable answer."""
        with app.app_context():
            db.session.add(AcmeLocalDomain(domain='*.custom', issuing_ca_id=clean_domains[7]))
            db.session.add(AcmeLocalDomain(domain='custom', issuing_ca_id=clean_domains[8]))
            db.session.commit()

            assert find_local_domain_ca('host.custom') == clean_domains[8]


class TestTheTwoSpellingsAreOneEntry:
    def _create(self, auth_client, domain, ca_id):
        return auth_client.post(
            '/api/v2/acme/local-domains',
            data=json.dumps({'domain': domain, 'issuing_ca_id': ca_id}),
            content_type='application/json')

    def test_registering_both_spellings_is_refused(
            self, app, auth_client, clean_domains, create_ca):
        ca = create_ca(cn='Wildcard Mapping CA')

        first = self._create(auth_client, '*.custom', ca['id'])
        assert first.status_code == 201, first.data

        second = self._create(auth_client, 'custom', ca['id'])

        assert second.status_code == 409, second.data
        assert 'already registered' in json.loads(second.data)['message']

    def test_the_refusal_names_the_entry_that_is_in_the_way(
            self, app, auth_client, clean_domains, create_ca):
        ca = create_ca(cn='Wildcard Mapping CA 2')
        assert self._create(auth_client, 'custom', ca['id']).status_code == 201

        refused = self._create(auth_client, '*.custom', ca['id'])

        assert refused.status_code == 409
        assert 'custom' in json.loads(refused.data)['message']


class TestTheDnsMappedTableIsGuardedTheSameWay:
    """The same rule, on the other table.

    The local-domain route refused the second spelling and the DNS-mapped
    route did not: `example.test` and `*.example.test` could both be
    registered there, and only the first one the lookup ranked was ever
    reached. Which of the two was in force depended on the order they came
    back in, and the screen showed both (#352, reported by @gb-123-git).
    """

    def _create(self, auth_client, domain, provider_id):
        return auth_client.post(
            '/api/v2/acme/domains',
            data=json.dumps({'domain': domain,
                             'dns_provider_id': provider_id}),
            content_type='application/json')

    @pytest.fixture
    def provider(self, app, clean_domains):
        from models import db
        from models.acme_models import DnsProvider

        with app.app_context():
            existing = DnsProvider.query.filter_by(
                name='wildcard-guard-provider').first()
            if existing is None:
                existing = DnsProvider(name='wildcard-guard-provider',
                                       provider_type='cloudflare')
                db.session.add(existing)
                db.session.commit()
            return existing.id

    @pytest.mark.parametrize('first, second',
                             [('*.example.test', 'example.test'),
                              ('example.test', '*.example.test')])
    def test_registering_both_spellings_is_refused(
            self, app, auth_client, provider, first, second):
        assert self._create(auth_client, first, provider).status_code == 201

        refused = self._create(auth_client, second, provider)

        assert refused.status_code == 409, refused.data
        message = json.loads(refused.data)['message']
        assert 'already registered' in message
        assert first in message, (
            'the refusal must name the entry that is in the way, not the one '
            'being asked for')

    def test_a_malformed_domain_is_still_a_bad_request(
            self, app, auth_client, provider):
        """The duplicate check used to run first, so a domain the format
        check would have refused came back as a conflict."""
        refused = self._create(auth_client, '*', provider)

        assert refused.status_code == 400, refused.data


class TestAutoApproveHonoursTheWildcardEntry:
    def test_a_wildcard_entry_auto_approves_its_subdomains(
            self, app, clean_domains):
        from services.acme.acme_service import AcmeService

        with app.app_context():
            db.session.add(AcmeLocalDomain(
                domain='*.custom', issuing_ca_id=clean_domains[7], auto_approve=True))
            db.session.commit()

            assert AcmeService._is_domain_auto_approved('host.custom') is True
            assert AcmeService._is_domain_auto_approved('other.test') is False

    def test_the_most_specific_entry_decides_the_answer(
            self, app, clean_domains):
        """A subdomain that says "challenge me" is not overruled by a parent
        that says otherwise."""
        from services.acme.acme_service import AcmeService

        with app.app_context():
            db.session.add(AcmeLocalDomain(
                domain='custom', issuing_ca_id=clean_domains[7], auto_approve=True))
            db.session.add(AcmeLocalDomain(
                domain='strict.custom', issuing_ca_id=clean_domains[7], auto_approve=False))
            db.session.commit()

            assert AcmeService._is_domain_auto_approved('strict.custom') is False
            assert AcmeService._is_domain_auto_approved('other.custom') is True


class TestTheMatcherItself:
    @pytest.mark.parametrize('given,expected', [
        ('*.Custom', 'custom'),
        ('Custom.', 'custom'),
        ('  *.custom.  ', 'custom'),
        ('', ''),
        (None, ''),
    ])
    def test_normalize(self, given, expected):
        assert domain_match.normalize(given) == expected

    def test_candidates_are_ordered_most_specific_first(self):
        assert domain_match.candidates('a.b.test') == [
            'a.b.test', '*.a.b.test', 'b.test', '*.b.test', 'test', '*.test']

    def test_candidates_of_nothing_is_nothing(self):
        assert domain_match.candidates('*.') == []
        assert domain_match.candidates(None) == []
