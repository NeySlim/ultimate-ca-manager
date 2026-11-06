"""Every provider puts the challenge record in the most specific zone it holds.

A dns-01 challenge is a TXT record, and the record only answers if it is
created in the zone that is actually authoritative for the name. When an
operator holds both `example.co.uk` and a delegated `sub.example.co.uk`, the
record for `_acme-challenge.sub.example.co.uk` belongs in the child. Put it in
the parent and the resolver never sees it: the CA retries, the order expires
and the issuance fails without anything in UCM saying why.

Three different algorithms decided this across the provider set:

* the correct one, a walk from the most specific candidate down, which 25
  providers implement inline and identically;
* `domain.endswith(zone)` over the provider's zone list in **API order**, so
  whichever of parent and child the API happens to return first wins -- nine
  providers;
* a fixed last-two-labels split that never asks the API at all, which turns
  `sub.example.co.uk` into `co.uk` -- the default in `BaseDnsProvider`.

`endswith` also has no dot boundary, so zone `example.com` captures
`notexample.com`, and four providers read the zone name with `.get('name', '')`,
which makes `endswith('')` true for the first entry in the list whatever it is.

`BaseDnsProvider.find_zone` is the one algorithm now.
"""
import pytest

from services.acme.dns_providers.base import BaseDnsProvider
from services.acme.dns_providers.alwaysdata import AlwaysdataDnsProvider
from services.acme.dns_providers.bunny import BunnyDnsProvider
from services.acme.dns_providers.checkdomain import CheckdomainDnsProvider
from services.acme.dns_providers.cloudns import ClouDnsDnsProvider
from services.acme.dns_providers.corenetworks import CoreNetworksDnsProvider
from services.acme.dns_providers.dnsimple import DnsimpleDnsProvider
from services.acme.dns_providers.dnsmadeeasy import DnsMadeEasyDnsProvider
from services.acme.dns_providers.domeneshop import DomeneshopDnsProvider
from services.acme.dns_providers.dynu import DynuDnsProvider
from services.acme.dns_providers.hetzner import HetznerDnsProvider


FQDN = '_acme-challenge.sub.example.co.uk'
NAME = 'sub.example.co.uk'

# Deliberately least-specific first: that ordering is what separates a
# longest-suffix walk from a first-match one.
ZONES = ['co.uk', 'example.co.uk', 'sub.example.co.uk']


def _zone_name(result):
    """Providers return the zone name, an (id, name) pair, or the zone dict."""
    if result is None:
        return None
    if isinstance(result, tuple):
        return result[1]
    if isinstance(result, dict):
        for k in ('name', 'Domain', 'domain'):
            if k in result:
                return result[k]
        raise AssertionError(f'no zone name in {result!r}')
    return result


class _ConcreteProvider(BaseDnsProvider):
    """`BaseDnsProvider` is abstract; the fallback helper is not."""

    PROVIDER_TYPE = 'test'
    REQUIRED_CREDENTIALS = []

    def create_txt_record(self, domain, record_name, record_value, ttl=300):
        return True, 'ok'

    def delete_txt_record(self, domain, record_name, record_value):
        return True, 'ok'

    def test_connection(self):
        return True, 'ok'


# (class, credentials, selection method, response builder)
PROVIDERS = [
    (AlwaysdataDnsProvider, {'api_key': 'k', 'account': 'a'}, '_find_domain',
     lambda zs: [{'id': i, 'name': z} for i, z in enumerate(zs)]),
    (BunnyDnsProvider, {'api_key': 'k'}, '_find_zone',
     lambda zs: {'Items': [{'Id': i, 'Domain': z} for i, z in enumerate(zs)]}),
    (CheckdomainDnsProvider, {'api_token': 't'}, '_find_domain',
     lambda zs: {'_embedded': {'domains': [{'id': i, 'name': z}
                                           for i, z in enumerate(zs)]}}),
    (ClouDnsDnsProvider, {'auth_id': 'i', 'auth_password': 'p'}, '_find_zone',
     lambda zs: [{'name': z} for z in zs]),
    (CoreNetworksDnsProvider, {'username': 'u', 'password': 'p'}, '_find_zone',
     lambda zs: [{'name': z} for z in zs]),
    (DnsimpleDnsProvider, {'api_token': 't', 'account_id': '1'}, '_find_zone',
     lambda zs: {'data': [{'name': z} for z in zs]}),
    (DnsMadeEasyDnsProvider, {'api_key': 'k', 'secret_key': 's'}, '_find_domain',
     lambda zs: {'data': [{'id': i, 'name': z} for i, z in enumerate(zs)]}),
    (DomeneshopDnsProvider, {'api_token': 't', 'api_secret': 's'}, '_find_domain',
     lambda zs: [{'id': i, 'domain': z} for i, z in enumerate(zs)]),
    (DynuDnsProvider, {'api_key': 'k'}, '_get_domain_id',
     lambda zs: {'domains': [{'id': i, 'name': z} for i, z in enumerate(zs)]}),
    # The reference implementation, to show the whole set now agrees.
    (HetznerDnsProvider, {'api_token': 't'}, '_get_zone',
     lambda zs: {'zones': [{'id': str(i), 'name': z} for i, z in enumerate(zs)]}),
]

IDS = [p[0].__name__ for p in PROVIDERS]


def _provider(cls, creds, response, monkeypatch):
    p = cls(creds)
    monkeypatch.setattr(p, '_request', lambda *a, **kw: (True, response))
    return p


class TestTheMostSpecificZoneWins:
    @pytest.mark.parametrize('cls,creds,method,build', PROVIDERS, ids=IDS)
    def test_a_delegated_child_zone_is_preferred_over_its_parent(
            self, cls, creds, method, build, monkeypatch):
        p = _provider(cls, creds, build(ZONES), monkeypatch)
        assert _zone_name(getattr(p, method)(NAME)) == 'sub.example.co.uk'

    @pytest.mark.parametrize('cls,creds,method,build', PROVIDERS, ids=IDS)
    def test_the_answer_does_not_depend_on_the_api_list_order(
            self, cls, creds, method, build, monkeypatch):
        p = _provider(cls, creds, build(list(reversed(ZONES))), monkeypatch)
        assert _zone_name(getattr(p, method)(NAME)) == 'sub.example.co.uk'

    @pytest.mark.parametrize('cls,creds,method,build', PROVIDERS, ids=IDS)
    def test_an_unrelated_zone_list_yields_nothing(
            self, cls, creds, method, build, monkeypatch):
        p = _provider(cls, creds, build(['elsewhere.example', 'other.test']),
                      monkeypatch)
        assert _zone_name(getattr(p, method)(NAME)) is None

    @pytest.mark.parametrize('cls,creds,method,build', PROVIDERS, ids=IDS)
    def test_a_zone_that_is_merely_a_string_suffix_does_not_match(
            self, cls, creds, method, build, monkeypatch):
        """`notexample.com` ends with `example.com` and is a different zone."""
        p = _provider(cls, creds, build(['example.com']), monkeypatch)
        assert _zone_name(getattr(p, method)('notexample.com')) is None

    @pytest.mark.parametrize('cls,creds,method,build', PROVIDERS, ids=IDS)
    def test_a_nameless_entry_does_not_swallow_every_name(
            self, cls, creds, method, build, monkeypatch):
        """An entry read as '' made `endswith('')` true for the first row."""
        p = _provider(cls, creds, build(['', 'example.co.uk']), monkeypatch)
        assert _zone_name(getattr(p, method)(NAME)) == 'example.co.uk'

    @pytest.mark.parametrize('cls,creds,method,build', PROVIDERS, ids=IDS)
    def test_the_zone_itself_is_its_own_most_specific_zone(
            self, cls, creds, method, build, monkeypatch):
        p = _provider(cls, creds, build(ZONES), monkeypatch)
        assert _zone_name(getattr(p, method)('example.co.uk')) == 'example.co.uk'


class TestTheSharedSelector:
    def test_it_walks_from_the_most_specific_candidate_down(self):
        assert BaseDnsProvider.find_zone(NAME, ZONES) == 'sub.example.co.uk'
        assert BaseDnsProvider.find_zone(NAME, list(reversed(ZONES))) == 'sub.example.co.uk'

    def test_it_anchors_on_a_label_boundary(self):
        assert BaseDnsProvider.find_zone('notexample.com', ['example.com']) is None
        assert BaseDnsProvider.find_zone('a.example.com', ['example.com']) == 'example.com'

    def test_it_ignores_empty_and_missing_candidates(self):
        assert BaseDnsProvider.find_zone(NAME, ['', None, 'example.co.uk']) == 'example.co.uk'
        assert BaseDnsProvider.find_zone(NAME, []) is None

    def test_it_is_case_and_trailing_dot_insensitive(self):
        assert BaseDnsProvider.find_zone('A.Example.CO.UK.', ['example.co.uk']) == 'example.co.uk'

    def test_it_strips_a_wildcard_label(self):
        assert BaseDnsProvider.find_zone('*.example.co.uk', ['example.co.uk']) == 'example.co.uk'

    def test_it_returns_the_candidate_object_when_asked(self):
        zones = [{'n': 'example.co.uk'}, {'n': 'sub.example.co.uk'}]
        won = BaseDnsProvider.find_zone(NAME, zones, key=lambda z: z['n'])
        assert won is zones[1]


class TestTheFallbackWithoutAZoneList:
    """`get_zone_for_domain` is what the providers with no zone API use."""

    def test_a_two_label_registry_suffix_keeps_three_labels(self):
        p = _ConcreteProvider({})
        assert p.get_zone_for_domain('sub.example.co.uk') == 'example.co.uk'
        assert p.get_zone_for_domain('example.co.uk') == 'example.co.uk'

    def test_an_ordinary_suffix_still_keeps_two_labels(self):
        p = _ConcreteProvider({})
        assert p.get_zone_for_domain('sub.example.com') == 'example.com'
        assert p.get_zone_for_domain('example.com') == 'example.com'

    def test_a_wildcard_and_a_trailing_dot_are_not_labels(self):
        p = _ConcreteProvider({})
        assert p.get_zone_for_domain('*.example.com.') == 'example.com'


class TestTheProvidersWithNoZoneApi:
    """netcup, namecheap, porkbun and vercel never ask which zones exist."""

    def test_netcup_splits_on_the_registrable_domain(self):
        from services.acme.dns_providers.netcup import NetcupDnsProvider
        p = NetcupDnsProvider({'customer_number': '1', 'api_key': 'k',
                               'api_password': 'p'})
        assert p._split_domain_and_host(FQDN, NAME) == \
            ('example.co.uk', '_acme-challenge.sub')
        assert p._split_domain_and_host('_acme-challenge.example.com',
                                        'example.com') == \
            ('example.com', '_acme-challenge')
        assert p._split_domain_and_host('example.com', 'example.com') == \
            ('example.com', '@')

    def test_namecheap_addresses_the_registered_domain(self):
        from services.acme.dns_providers.namecheap import NamecheapDnsProvider
        p = NamecheapDnsProvider({'api_user': 'u', 'api_key': 'k',
                                  'client_ip': '198.51.100.1'})
        # A sub-domain must not become an SLD of its own.
        assert p._parse_domain('sub.example.com') == ('example', 'com')
        assert p._parse_domain('example.com') == ('example', 'com')
        # A two-label registry suffix belongs to the TLD, not to the SLD.
        assert p._parse_domain(NAME) == ('example', 'co.uk')
        # And the host is relative to that zone, not to the name validated.
        assert p._relative_host('_acme-challenge.sub.example.com',
                                'sub.example.com') == '_acme-challenge.sub'
        assert p._relative_host(FQDN, NAME) == '_acme-challenge.sub'
        assert p._relative_host('example.com', 'example.com') == '@'

    @pytest.mark.parametrize('module,cls_name,creds', [
        ('porkbun', 'PorkbunDnsProvider',
         {'api_key': 'k', 'secret_api_key': 's'}),
        ('vercel', 'VercelDnsProvider', {'api_token': 't'}),
    ])
    def test_the_naive_providers_keep_a_two_label_registry_suffix(
            self, module, cls_name, creds):
        import importlib
        cls = getattr(importlib.import_module(
            f'services.acme.dns_providers.{module}'), cls_name)
        p = cls(creds)
        assert p.get_zone_for_domain(NAME) == 'example.co.uk'
        assert p.get_zone_for_domain('sub.example.com') == 'example.com'


# (module, class, credentials, the API path the zone is written into)
VERBATIM = [
    ('epik', 'EpikDnsProvider', {'api_key': 'k'}, '/domains/{zone}/records'),
    ('hostinger', 'HostingerDnsProvider', {'api_token': 't'}, '/dns/{zone}/records'),
    ('hover', 'HoverDnsProvider', {'username': 'u', 'password': 'p'},
     '/domains/{zone}/dns'),
    ('mythicbeasts', 'MythicBeastsDnsProvider',
     {'api_key': 'k', 'api_secret': 's'}, '/zones/{zone}/records'),
]


class TestTheProvidersThatTookTheCallersNameAsTheZone:
    """Four providers put the caller's argument straight into the API path.

    The ACME client path passes the name being validated, so
    `sub.example.com` addressed a zone of that name -- one the account does
    not hold -- while the proxy path passed a zone it had guessed itself.
    Same provider, same name, two different zones depending on the caller.
    Both callers now pass the name and the provider resolves the zone.
    """

    @pytest.mark.parametrize('module,cls_name,creds,path', VERBATIM,
                             ids=[v[1] for v in VERBATIM])
    def test_a_subdomain_is_written_into_its_registrable_zone(
            self, module, cls_name, creds, path, monkeypatch):
        import importlib
        cls = getattr(importlib.import_module(
            f'services.acme.dns_providers.{module}'), cls_name)
        p = cls(creds)

        seen = {}
        monkeypatch.setattr(p, '_request',
                            lambda method, url, *a, **kw: (seen.update(url=url), (True, {}))[1])

        p.create_txt_record('sub.example.com',
                            '_acme-challenge.sub.example.com', 'tok')
        assert seen['url'] == path.format(zone='example.com')

    @pytest.mark.parametrize('module,cls_name,creds,path', VERBATIM,
                             ids=[v[1] for v in VERBATIM])
    def test_a_two_label_registry_suffix_keeps_three_labels(
            self, module, cls_name, creds, path, monkeypatch):
        import importlib
        cls = getattr(importlib.import_module(
            f'services.acme.dns_providers.{module}'), cls_name)
        p = cls(creds)

        seen = {}
        monkeypatch.setattr(p, '_request',
                            lambda method, url, *a, **kw: (seen.update(url=url), (True, {}))[1])

        p.create_txt_record(NAME, FQDN, 'tok')
        assert seen['url'] == path.format(zone='example.co.uk')
