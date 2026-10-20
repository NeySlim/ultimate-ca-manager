"""Shape rule shared by the local and DNS-provider ACME domain tables."""
import pytest

from models import db
from services.acme.domain_match import is_valid_entry

BOTH_MODES = pytest.mark.parametrize('single', [True, False], ids=['local', 'dns'])


def _local(domain):
    return is_valid_entry(domain, allow_single_label=True)


def _dns(domain):
    return is_valid_entry(domain, allow_single_label=False)


@pytest.mark.parametrize('entry', ['lan', 'intranet', 'zz', '*.lan', 'Corp', '*.qa'])
def test_bare_private_tld_only_on_the_local_table(entry):
    assert _local(entry) is True
    assert _dns(entry) is False


@BOTH_MODES
@pytest.mark.parametrize('entry', [
    'shop.example.org',
    'x.y.z.example.net',
    '*.svc.example.org',
    'web-01.example.org',
    '42.example.net',
    'MAIL.Example.ORG',
    'a.bc',
    'w--x.k8s.example.io',
])
def test_multi_label_names_accepted(entry, single):
    assert is_valid_entry(entry, allow_single_label=single) is True


@BOTH_MODES
def test_label_length_bound(single):
    assert is_valid_entry('q' * 63 + '.example.org', allow_single_label=single) is True
    assert is_valid_entry('q' * 64 + '.example.org', allow_single_label=single) is False
    assert is_valid_entry('svc.' + 'r' * 64, allow_single_label=single) is False


def test_long_top_label_alone_is_bounded_too():
    assert _local('t' * 63) is True
    assert _local('t' * 64) is False


def test_total_length_is_not_bounded():
    many = '.'.join(['seg'] * 100) + '.example.org'
    assert len(many) > 255
    assert _dns(many) is True


@BOTH_MODES
@pytest.mark.parametrize('entry', [
    None, '', '\t', ' shop.example.org', 'shop.example.org ', ' lan',
    '*', '*.', '*..',
    '.org', 'example.org.', 'a..example.org', '.', '..', 'lan.',
    '*.*.svc.example.org', 'x*.example.org', 'svc.*.example.org', '**.example.org',
    'web_01.example.org', 'web 01.example.org', 'web#01.example.org',
    'café.example.org', 'shop.example.org/x', 'shop:443.example.org',
    'example.42', 'svc.example.4b', 'svc.example.b4', 'svc.example.x',
    '-web.example.org', 'web-.example.org', 'web.-example.org', 'web.org-',
    'example.org\n', 'mail\n.example.org', '\nexample.org', 'example.org\r',
    '/srv/../x', '../lan',
])
def test_malformed_entries_refused(entry, single):
    assert is_valid_entry(entry, allow_single_label=single) is False


@pytest.mark.parametrize('entry', ['z', '*.z', 'lan\n', '*.lan\n', '-lan', '4g', 'l_an'])
def test_single_label_still_has_to_be_well_formed(entry):
    assert _local(entry) is False


@pytest.mark.parametrize('entry', [12345, b'example.org', ['example.org']])
def test_non_strings_refused(entry):
    assert _local(entry) is False
    assert _dns(entry) is False


@pytest.mark.parametrize('entry', [
    'shop.example.org', '*.svc.example.org', 'web_01.example.org', 'example.42',
    'a..example.org', 'example.org\n', 'q' * 64 + '.example.org', '*.*.x.example.org',
])
def test_modes_agree_beyond_a_single_label(entry):
    assert _local(entry) == _dns(entry)


# Through the routes: the two tables apply the two modes.

_API_NAME = 'intranet'


@pytest.fixture
def _no_intranet_rows(app):
    from models.acme_models import AcmeDomain, AcmeLocalDomain, DnsProvider

    def purge():
        with app.app_context():
            for model in (AcmeLocalDomain, AcmeDomain):
                model.query.filter(model.domain.in_([_API_NAME, '*.' + _API_NAME])).delete(
                    synchronize_session=False)
            DnsProvider.query.filter_by(name='entry-shape-provider').delete()
            db.session.commit()

    purge()
    yield
    purge()


def test_api_accepts_bare_tld_locally_and_refuses_it_for_dns(
        app, auth_client, create_ca, _no_intranet_rows):
    from models.acme_models import DnsProvider
    from api.v2.acme_local_domains import find_local_domain_ca

    ca = create_ca(cn='Entry Shape CA')
    local = auth_client.post('/api/v2/acme/local-domains',
                             json={'domain': _API_NAME, 'issuing_ca_id': ca['id']})
    assert local.status_code in (200, 201), local.get_json()

    # An accepted entry stays reachable by the lookup, for itself and below.
    with app.app_context():
        assert find_local_domain_ca(_API_NAME) == ca['id']
        assert find_local_domain_ca('build.' + _API_NAME) == ca['id']

    with app.app_context():
        provider = DnsProvider(name='entry-shape-provider', provider_type='manual',
                               credentials='{}')
        db.session.add(provider)
        db.session.commit()
        provider_id = provider.id

    dns = auth_client.post('/api/v2/acme/domains',
                           json={'domain': _API_NAME, 'dns_provider_id': provider_id})
    assert dns.status_code == 400, dns.get_json()
    assert 'Invalid domain format' in dns.get_data(as_text=True)
