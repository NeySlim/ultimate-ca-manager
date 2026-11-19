"""An archived row whose name is taken is restored under a suffixed name, never merged.

DNS providers, ACME CA accounts and webhooks are found again by name. Two
archived rows of one name, or a name held here by a different row, used to
land on the same row: one secret survived, the other was lost.
"""
import json

import pytest

from models import db
from models.acme_client_account import AcmeClientAccount
from models.acme_models import AcmeDomain, DnsProvider
from services.backup.restore_report import with_restore_warnings
from services.webhook_service import WebhookEndpoint
from tests.test_backup_hostile_corpus import PASSWORD, _forged, _service

from tests.fresh_app import fresh_app_fixtures

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()

PREFIX = 'lot124-'


def _provider(name, provider_type='cloudflare', token='t'):
    return {'name': name, 'provider_type': provider_type,
            'credentials': json.dumps({'api_token': token}),
            'is_default': False, 'enabled': True}


def _account(label, account_url=None, directory_url='https://ca.example/directory'):
    return {'label': label, 'directory_url': directory_url, 'email': 'ops@example.com',
            'account_url': account_url, 'account_key_algorithm': 'ES256',
            'is_default': False, 'proxy_enabled': False}


def _hook(name, url):
    return {'name': name, 'url': url, 'events': '["*"]', 'enabled': True,
            'auth_type': 'none', 'custom_headers': '{}'}


def _restore(sections, **rows):
    """Merge an archive whose `sections` hold exactly `rows`, and return the results."""
    def replace(data):
        for name in sections:
            data[name] = rows.get(name, [])
    blob = _forged(sections, mutate=replace)
    results = _service().restore_backup(blob, PASSWORD, mode='merge')
    db.session.expire_all()
    return results


def _ours(results):
    return [entry for entry in results['renamed'] if entry['from'].startswith(PREFIX)]


@pytest.fixture
def clean(app):
    with app.app_context():
        yield
        db.session.rollback()
        AcmeDomain.query.filter(AcmeDomain.domain.like(f'{PREFIX}%')).delete(
            synchronize_session=False)
        for model, column in ((DnsProvider, DnsProvider.name),
                              (AcmeClientAccount, AcmeClientAccount.label),
                              (WebhookEndpoint, WebhookEndpoint.name)):
            model.query.filter(column.like(f'{PREFIX}%')).delete(synchronize_session=False)
        db.session.commit()


def _add(row):
    db.session.add(row)
    db.session.commit()
    return row.id


def _tokens(name_like):
    return {p.name: json.loads(p.credentials)['api_token']
            for p in DnsProvider.query.filter(DnsProvider.name.like(name_like))}


class TestDnsProviders:
    def test_two_archived_homonyms_keep_their_own_token(self, clean):
        results = _restore(['dns_providers'], dns_providers=[
            _provider(f'{PREFIX}dup', token='first'),
            _provider(f'{PREFIX}dup', token='second')])
        assert _tokens(f'{PREFIX}dup%') == {f'{PREFIX}dup': 'first',
                                            f'{PREFIX}dup (2)': 'second'}
        assert _ours(results) == [{
            'section': 'dns_providers', 'from': f'{PREFIX}dup', 'to': f'{PREFIX}dup (2)',
            'reason': 'name held by another row of the archive'}]

    def test_a_suffix_does_not_take_a_name_the_archive_holds(self, clean):
        _restore(['dns_providers'], dns_providers=[
            _provider(f'{PREFIX}sfx', token='a'), _provider(f'{PREFIX}sfx', token='b'),
            _provider(f'{PREFIX}sfx (2)', token='c')])
        assert _tokens(f'{PREFIX}sfx%') == {f'{PREFIX}sfx': 'a', f'{PREFIX}sfx (3)': 'b',
                                            f'{PREFIX}sfx (2)': 'c'}

    def test_a_homonym_of_another_type_does_not_overwrite_the_row_here(self, clean):
        here = DnsProvider(name=f'{PREFIX}held', provider_type='route53')
        here.credentials = json.dumps({'api_token': 'mine'})
        here_id = _add(here)
        results = _restore(['dns_providers'], dns_providers=[
            _provider(f'{PREFIX}held', token='theirs')])
        kept = db.session.get(DnsProvider, here_id)
        assert (kept.name, kept.provider_type) == (f'{PREFIX}held', 'route53')
        assert _tokens(f'{PREFIX}held%') == {f'{PREFIX}held': 'mine',
                                             f'{PREFIX}held (2)': 'theirs'}
        assert [e['to'] for e in _ours(results)] == [f'{PREFIX}held (2)']

    def test_the_same_provider_is_updated_in_place(self, clean):
        here = DnsProvider(name=f'{PREFIX}same', provider_type='cloudflare')
        here.credentials = json.dumps({'api_token': 'old'})
        here_id = _add(here)
        results = _restore(['dns_providers'], dns_providers=[
            _provider(f'{PREFIX}same', token='new')])
        assert _tokens(f'{PREFIX}same%') == {f'{PREFIX}same': 'new'}
        assert db.session.get(DnsProvider, here_id) is not None
        assert _ours(results) == []

    def test_an_archive_older_than_124_lands_on_the_rows_the_migration_renamed(self, clean):
        first = DnsProvider(name=f'{PREFIX}mig', provider_type='cloudflare')
        second = DnsProvider(name=f'{PREFIX}mig (2)', provider_type='cloudflare')
        first.credentials = second.credentials = json.dumps({'api_token': 'before'})
        ids = (_add(first), _add(second))
        _restore(['dns_providers'], dns_providers=[
            _provider(f'{PREFIX}mig', token='a'), _provider(f'{PREFIX}mig', token='b')])
        assert _tokens(f'{PREFIX}mig%') == {f'{PREFIX}mig': 'a', f'{PREFIX}mig (2)': 'b'}
        assert {p.id for p in DnsProvider.query.filter(
            DnsProvider.name.like(f'{PREFIX}mig%'))} == set(ids)

    def test_a_reference_two_archived_homonyms_share_is_reported(self, clean):
        domain = {'domain': f'{PREFIX}amb.example', 'dns_provider_id': 1,
                  'dns_provider_id_ref': {'name': f'{PREFIX}amb'},
                  'issuing_ca_id': None, 'issuing_ca_id_ref': None}
        results = _restore(['dns_providers', 'acme_domains'], dns_providers=[
            _provider(f'{PREFIX}amb', token='a'), _provider(f'{PREFIX}amb', token='b')],
            acme_domains=[domain])
        restored = AcmeDomain.query.filter_by(domain=f'{PREFIX}amb.example').one()
        assert db.session.get(DnsProvider, restored.dns_provider_id).name == f'{PREFIX}amb'
        assert [w for w in results['ambiguous_references'] if f'{PREFIX}amb' in w] == [
            f"acme_domains.dns_provider_id names '{PREFIX}amb', which 2 archived "
            f"dns_providers rows hold: it now points at the first one, restored as '{PREFIX}amb'"]

    def test_a_domain_follows_its_renamed_provider(self, clean):
        here = DnsProvider(name=f'{PREFIX}ref', provider_type='route53')
        _add(here)
        domain = {'domain': f'{PREFIX}ref.example', 'dns_provider_id': 1,
                  'dns_provider_id_ref': {'name': f'{PREFIX}ref'},
                  'issuing_ca_id': None, 'issuing_ca_id_ref': None}
        _restore(['dns_providers', 'acme_domains'],
                 dns_providers=[_provider(f'{PREFIX}ref')], acme_domains=[domain])
        restored = AcmeDomain.query.filter_by(domain=f'{PREFIX}ref.example').one()
        provider = db.session.get(DnsProvider, restored.dns_provider_id)
        assert (provider.name, provider.provider_type) == (f'{PREFIX}ref (2)', 'cloudflare')


class TestAcmeAccounts:
    def test_another_registration_under_the_same_label_is_renamed(self, clean):
        here_id = _add(AcmeClientAccount(**_account(f'{PREFIX}acct', 'https://ca.example/acct/1')))
        results = _restore(['acme_client_accounts'], acme_client_accounts=[
            _account(f'{PREFIX}acct', 'https://ca.example/acct/2')])
        assert db.session.get(AcmeClientAccount, here_id).account_url == 'https://ca.example/acct/1'
        renamed = AcmeClientAccount.query.filter_by(label=f'{PREFIX}acct (2)').one()
        assert renamed.account_url == 'https://ca.example/acct/2'
        assert [e['to'] for e in _ours(results)] == [f'{PREFIX}acct (2)']

    def test_the_same_registration_under_another_label_is_updated(self, clean):
        here_id = _add(AcmeClientAccount(**_account(f'{PREFIX}kept', 'https://ca.example/acct/3')))
        results = _restore(['acme_client_accounts'], acme_client_accounts=[
            {**_account(f'{PREFIX}relabelled', 'https://ca.example/acct/3'),
             'email': 'new@example.com'}])
        rows = AcmeClientAccount.query.filter_by(account_url='https://ca.example/acct/3').all()
        assert [(r.id, r.label, r.email) for r in rows] == [
            (here_id, f'{PREFIX}kept', 'new@example.com')]
        assert _ours(results) == [{
            'section': 'acme_client_accounts', 'from': f'{PREFIX}relabelled',
            'to': f'{PREFIX}kept', 'reason': 'same row here under this name'}]

    def test_an_unregistered_homonym_never_takes_a_registered_account(self, clean):
        here_id = _add(AcmeClientAccount(**_account(
            f'{PREFIX}L', 'https://prod.example/acct/1', 'https://prod.example/dir')))
        results = _restore(['acme_client_accounts'], acme_client_accounts=[
            _account(f'{PREFIX}L', None, 'https://staging.example/dir')])
        kept = db.session.get(AcmeClientAccount, here_id)
        assert (kept.label, kept.directory_url, kept.account_url) == (
            f'{PREFIX}L', 'https://prod.example/dir', 'https://prod.example/acct/1')
        restored = AcmeClientAccount.query.filter_by(label=f'{PREFIX}L (2)').one()
        assert (restored.directory_url, restored.account_url) == (
            'https://staging.example/dir', None)
        assert [e['to'] for e in _ours(results)] == [f'{PREFIX}L (2)']

    def test_an_unregistered_homonym_in_the_same_directory_is_renamed(self, clean):
        here_id = _add(AcmeClientAccount(**_account(
            f'{PREFIX}R', 'https://ca.example/acct/9', 'https://ca.example/dir')))
        results = _restore(['acme_client_accounts'], acme_client_accounts=[
            _account(f'{PREFIX}R', None, 'https://ca.example/dir')])
        assert db.session.get(AcmeClientAccount, here_id).account_url == 'https://ca.example/acct/9'
        assert [e['to'] for e in _ours(results)] == [f'{PREFIX}R (2)']

    def test_an_unregistered_account_of_another_directory_is_renamed(self, clean):
        here_id = _add(AcmeClientAccount(**_account(f'{PREFIX}U', None, 'https://a.example/dir')))
        results = _restore(['acme_client_accounts'], acme_client_accounts=[
            _account(f'{PREFIX}U', None, 'https://b.example/dir')])
        assert db.session.get(AcmeClientAccount, here_id).directory_url == 'https://a.example/dir'
        assert [e['to'] for e in _ours(results)] == [f'{PREFIX}U (2)']

    def test_an_unregistered_account_is_found_by_its_label(self, clean):
        here_id = _add(AcmeClientAccount(**_account(f'{PREFIX}unreg')))
        results = _restore(['acme_client_accounts'], acme_client_accounts=[
            {**_account(f'{PREFIX}unreg'), 'email': 'other@example.com'}])
        assert db.session.get(AcmeClientAccount, here_id).email == 'other@example.com'
        assert AcmeClientAccount.query.filter(
            AcmeClientAccount.label.like(f'{PREFIX}unreg%')).count() == 1
        assert _ours(results) == []


class TestWebhooks:
    def test_a_homonym_with_another_url_is_renamed(self, clean):
        here_id = _add(WebhookEndpoint(**_hook(f'{PREFIX}hook', 'https://a.example/h')))
        results = _restore(['webhook_endpoints'], webhook_endpoints=[
            _hook(f'{PREFIX}hook', 'https://b.example/h')])
        assert db.session.get(WebhookEndpoint, here_id).url == 'https://a.example/h'
        assert WebhookEndpoint.query.filter_by(
            name=f'{PREFIX}hook (2)').one().url == 'https://b.example/h'
        assert [e['to'] for e in _ours(results)] == [f'{PREFIX}hook (2)']

    def test_the_same_url_under_another_name_is_updated(self, clean):
        here_id = _add(WebhookEndpoint(**_hook(f'{PREFIX}here', 'https://c.example/h')))
        _restore(['webhook_endpoints'], webhook_endpoints=[
            {**_hook(f'{PREFIX}there', 'https://c.example/h'), 'events': '["certificate.issued"]'}])
        rows = WebhookEndpoint.query.filter_by(url='https://c.example/h').all()
        assert [(r.id, r.name, r.events) for r in rows] == [
            (here_id, f'{PREFIX}here', '["certificate.issued"]')]


def test_the_restore_message_names_the_renamed_rows():
    message = with_restore_warnings('Restored.', {'renamed': [
        {'section': 'dns_providers', 'from': 'cf', 'to': 'cf (2)', 'reason': 'x'}]})
    assert message == ('Restored. 1 row was restored under another name: '
                       'DNS provider cf as cf (2).')
