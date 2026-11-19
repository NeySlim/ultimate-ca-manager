"""DuckDNS, Hurricane Electric and FreeDNS hold one TXT value per name: a cleanup leaves
the name to another order still validating it, and a domain with its wildcard is refused."""
import json
import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from models import db
from models.acme_models import AcmeClientOrder, DnsProvider
from services.acme import acme_client_service as client_mod
from services.acme.acme_client_service import AcmeClientService
from services.acme.acme_proxy_service import AcmeProxyService
from services.acme.dns_providers import get_provider_class
from utils.datetime_utils import utc_now

SINGLE = ('duckdns', 'hurricane', 'freedns')


def _recording(provider_type, calls):
    """The real provider class, its API calls recorded instead of sent."""
    class Recording(get_provider_class(provider_type)):
        def __init__(self):
            self.credentials = {}
            self._transient_secrets = []

        def create_txt_record(self, domain, record_name, record_value, ttl=300):
            calls.append(('create', record_name, record_value))
            return True, 'ok'

        def delete_txt_record(self, domain, record_name, record_value):
            calls.append(('delete', record_name, record_value))
            return True, 'ok'
    return Recording()


@pytest.fixture
def rows(app):
    made = []

    def provider(provider_type):
        row = DnsProvider(name=f'single-{uuid.uuid4().hex[:8]}', provider_type=provider_type, credentials='{}')
        db.session.add(row)
        db.session.commit()
        made.append(row)
        return row

    def order(domains, provider_row=None, status='pending', **extra):
        row = AcmeClientOrder(domains=json.dumps(domains), environment='staging', challenge_type='dns-01',
                              status=status, dns_provider_id=provider_row.id if provider_row else None, **extra)
        row.set_challenges_dict({d: {'dns_txt_name': f'_acme-challenge.{d.removeprefix("*.")}',
                                     'dns_txt_value': f'value-{uuid.uuid4().hex[:6]}'} for d in domains})
        db.session.add(row)
        db.session.commit()
        made.append(row)
        return row

    with app.app_context():
        yield SimpleNamespace(provider=provider, order=order)
        db.session.rollback()
        ids = {type(r): [] for r in made}
        for row in made:
            ids[type(row)].append(row.id)
        for model in (AcmeClientOrder, DnsProvider):  # a failed renewal deletes its own order
            if ids.get(model):
                model.query.filter(model.id.in_(ids[model])).delete(synchronize_session=False)
        db.session.commit()


def _domain():
    return f'single-{uuid.uuid4().hex[:8]}.example.org'


def test_only_the_three_single_value_providers_say_so():
    assert all(get_provider_class(t).SINGLE_TXT_VALUE is True for t in SINGLE)
    assert get_provider_class('cloudflare').SINGLE_TXT_VALUE is False


@pytest.mark.parametrize('provider_type', SINGLE)
def test_a_cleanup_leaves_the_name_to_another_order_in_progress(rows, monkeypatch, provider_type):
    calls = []
    monkeypatch.setattr(client_mod, 'create_provider', lambda *_a: _recording(provider_type, calls))
    name = _domain()
    provider = rows.provider(provider_type)
    first = rows.order([name], provider)
    second = rows.order([name], provider)

    assert AcmeClientService.cleanup_dns_challenge(first)[0]
    assert calls == []  # the second order's value stays published

    second.status = 'issued'
    db.session.commit()
    assert AcmeClientService.cleanup_dns_challenge(first)[0]
    assert [c[:2] for c in calls] == [('delete', f'_acme-challenge.{name}')]


@pytest.mark.parametrize('status, expires_in, age, blocks', [
    # 'ready': every authorization is valid already (RFC 8555 §7.1.6), the TXT is no longer needed
    ('ready', None, None, False), ('processing', None, None, True), ('validating', None, None, True),
    ('valid', None, None, False), ('invalid', None, None, False), ('error', None, None, False),
    ('pending', timedelta(hours=1), None, True), ('pending', -timedelta(hours=1), None, False),
    ('pending', None, timedelta(days=8), False),
])
def test_what_counts_as_an_order_in_progress(rows, monkeypatch, status, expires_in, age, blocks):
    calls = []
    monkeypatch.setattr(client_mod, 'create_provider', lambda *_a: _recording('duckdns', calls))
    name = _domain()
    provider = rows.provider('duckdns')
    extra = {}
    if expires_in is not None:
        extra['expires_at'] = utc_now() + expires_in
    if age is not None:
        extra['created_at'] = utc_now() - age
    rows.order([f'*.{name}'], provider, status=status, **extra)
    assert AcmeClientService.cleanup_dns_challenge(rows.order([name], provider))[0]
    assert bool(calls) is not blocks


def test_a_provider_with_several_values_deletes_its_own_value_anyway(rows, monkeypatch):
    calls = []
    monkeypatch.setattr(client_mod, 'create_provider', lambda *_a: _recording('cloudflare', calls))
    name = _domain()
    provider = rows.provider('cloudflare')
    first = rows.order([name], provider)
    rows.order([name], provider)
    assert AcmeClientService.cleanup_dns_challenge(first)[0]
    assert calls == [('delete', f'_acme-challenge.{name}', first.challenges_dict[name]['dns_txt_value'])]


def test_the_proxy_cleanup_leaves_the_name_to_another_order(rows):
    calls = []
    name = _domain()
    record = f'_acme-challenge.{name}'
    rows.order([name], rows.provider('hurricane'))
    AcmeProxyService._delete_dns_record(_recording('hurricane', calls), name, record, 'v')
    assert calls == []
    AcmeProxyService._delete_dns_record(_recording('hurricane', calls), f'other-{name}',
                                        f'_acme-challenge.other-{name}', 'v')
    assert calls == [('delete', f'_acme-challenge.other-{name}', 'v')]


def test_the_renewal_cleanup_leaves_the_name_to_another_order(rows):
    from unittest.mock import MagicMock
    from services import acme_renewal_service as renew_mod

    name = _domain()
    provider = rows.provider('duckdns')
    parent = rows.order([name], provider, status='issued')
    other = rows.order([name], provider)

    def run():
        calls = []
        client = MagicMock()
        client.account = None
        client.create_order.return_value = (True, 'ok', rows.order([name], provider))
        client.verify_challenge.side_effect = RuntimeError('STOP')
        with patch.object(renew_mod, 'renewal_client', return_value=client), \
             patch('services.acme.dns_providers.create_provider', return_value=_recording('duckdns', calls)), \
             patch.object(renew_mod, 'wait_for_challenges', return_value={'ok': True, 'missing': [], 'waited': 0}):
            with pytest.raises(Exception):
                renew_mod.renew_certificate(db.session.get(AcmeClientOrder, parent.id))
        return [c[0] for c in calls]

    assert run() == ['create']  # the other order keeps its value
    other.status = 'invalid'
    db.session.commit()
    assert run() == ['create', 'delete']


@pytest.mark.parametrize('provider_type', SINGLE)
def test_a_domain_and_its_wildcard_are_refused_before_the_ca_is_asked(rows, auth_client, monkeypatch,
                                                                      provider_type):
    asked = []
    monkeypatch.setattr(AcmeClientService, 'for_issuance', classmethod(lambda cls, **_kw: asked.append(1)))
    name = _domain()
    provider = rows.provider(provider_type)
    answer = auth_client.post('/api/v2/acme/client/request', json={
        'domains': [name, f'*.{name}'], 'email': 'a@example.com', 'challenge_type': 'dns-01',
        'environment': 'staging', 'dns_provider_id': provider.id})
    assert answer.status_code == 400
    message = answer.get_json()['message']
    assert 'one TXT value per name' in message and f'*.{name}' in message
    assert asked == []


def test_a_domain_and_its_wildcard_pass_on_a_provider_with_several_values(rows, auth_client, monkeypatch):
    asked = []
    monkeypatch.setattr(AcmeClientService, 'for_issuance',
                        classmethod(lambda cls, **_kw: asked.append(1) or (_ for _ in ()).throw(RuntimeError)))
    name = _domain()
    auth_client.post('/api/v2/acme/client/request', json={
        'domains': [name, f'*.{name}'], 'email': 'a@example.com', 'challenge_type': 'dns-01',
        'environment': 'staging', 'dns_provider_id': rows.provider('cloudflare').id})
    assert asked == [1]


def test_create_order_refuses_a_domain_and_its_wildcard_before_any_request(rows):
    """The renewal and the preflight reach the CA through create_order, not the request route."""
    svc = AcmeClientService.__new__(AcmeClientService)
    svc.ensure_account = lambda _email: pytest.fail('the CA account was contacted')
    svc._post = lambda *_a: pytest.fail('the CA was asked')
    name = _domain()
    ok, message, order = svc.create_order([name, f'*.{name}'], 'a@example.com', 'dns-01',
                                          dns_provider_id=rows.provider('freedns').id)
    assert not ok and order is None and 'one TXT value per name' in message


def test_the_proxy_refuses_a_domain_and_its_wildcard_before_upstream(app):
    from services.acme.acme_proxy_service import ProxySingleTxtValueError

    provider = SimpleNamespace(id=1, provider_type='duckdns')
    with app.app_context():
        svc = AcmeProxyService('https://ucm.example/acme/proxy')
        svc.directory = {'newOrder': 'https://ca.example/new-order'}
    with app.app_context(), \
         patch.object(svc, '_post_with_account', side_effect=AssertionError('upstream was asked')), \
         patch('api.v2.acme_domains.find_provider_for_domain', return_value={'provider': provider}):
        with pytest.raises(ProxySingleTxtValueError, match='one TXT value per name'):
            svc.new_order([{'type': 'dns', 'value': 'x.duckdns.org'}, {'type': 'dns', 'value': '*.x.duckdns.org'}])


def test_the_proxy_publishes_only_the_upstream_value_on_a_single_value_provider(rows, monkeypatch):
    """A second value would replace the one the CA validates."""
    from services.acme import acme_proxy_service as proxy_mod

    calls = []
    name = _domain()
    provider_row = rows.provider('duckdns')
    order = rows.order([name], provider_row)
    order.is_proxy_order = True
    db.session.commit()
    svc = AcmeProxyService('https://ucm.example/acme/proxy')
    monkeypatch.setattr(svc, '_client_txt_values', lambda *_a, **_k: ['client-value'])
    monkeypatch.setattr(svc, '_post_with_account', lambda *_a, **_k: SimpleNamespace(status_code=200, text=''))
    monkeypatch.setattr(proxy_mod, 'wait_for_txt', lambda *_a: {'ok': True, 'waited': 0})
    with patch('api.v2.acme_domains.find_provider_for_domain', return_value={'provider': provider_row}), \
         patch('services.acme.dns_providers.create_provider', return_value=_recording('duckdns', calls)):
        svc._run_dns01_automation('https://ca.example/chall/1', 'token.thumb', name, order.id)
    assert [c[0] for c in calls] == ['create'] and calls[0][2] != 'client-value'
    assert [r['value'] for r in json.loads(db.session.get(AcmeClientOrder, order.id).dns_records_created)] \
        == [calls[0][2]]


def test_a_repeated_identifier_is_not_a_second_value(rows, auth_client, monkeypatch):
    """The CA deduplicates identifiers: only distinct names under one value are refused."""
    created = []
    name = f'{uuid.uuid4().hex[:8]}.duckdns.org'
    provider = rows.provider('duckdns')

    def create_order(**kw):
        created.append(kw['domains'])
        return True, 'Order created', rows.order([name], provider)
    client = SimpleNamespace(create_order=create_order,
                             setup_dns_challenge=lambda _o: (False, 'not published here', {}))
    monkeypatch.setattr(AcmeClientService, 'for_issuance', classmethod(lambda cls, **_kw: client))
    answer = auth_client.post('/api/v2/acme/client/request', json={
        'domains': [name, name.upper()], 'email': 'a@example.com', 'challenge_type': 'dns-01',
        'environment': 'staging', 'dns_provider_id': provider.id})
    assert answer.status_code == 201, answer.get_json()
    assert len(created) == 1


def test_the_refusal_names_each_identifier_once():
    from services.acme.single_txt_value import apex_and_wildcard_refusal
    message = apex_and_wildcard_refusal(['x.example', '*.x.example', 'X.example.'],
                                        get_provider_class('hurricane'))
    assert 'so x.example, *.x.example cannot' in message


def test_the_proxy_cleanup_of_an_order_still_pending_is_not_left_to_itself(rows, monkeypatch):
    """A failed commit of 'valid' leaves the order pending: its own cleanup must still clear the name."""
    calls = []
    name = _domain()
    provider = rows.provider('hurricane')
    order = rows.order([name], provider)
    order.is_proxy_order = True
    db.session.commit()
    svc = AcmeProxyService('https://ucm.example/acme/proxy')
    from flask import current_app
    with patch('services.acme.dns_providers.create_provider', return_value=_recording('hurricane', calls)), \
         patch.object(db.session, 'remove', lambda: None):
        svc._bg_cleanup_dns_records(current_app._get_current_object(), [
            {'provider_id': provider.id, 'domain': name, 'record_name': f'_acme-challenge.{name}',
             'value': 'v'}], order.id)
    assert calls == [('delete', f'_acme-challenge.{name}', 'v')]


def test_duckdns_holds_one_value_per_sub_name():
    from services.acme.single_txt_value import apex_and_wildcard_refusal
    duckdns = get_provider_class('duckdns')
    assert duckdns.single_value_key('_acme-challenge.a.foo.duckdns.org') == 'foo'
    assert duckdns.single_value_key('_acme-challenge.FOO.duckdns.org.') == 'foo'
    assert 'foo.duckdns.org, www.foo.duckdns.org' in apex_and_wildcard_refusal(
        ['foo.duckdns.org', 'www.foo.duckdns.org'], duckdns)
    for other in ('hurricane', 'freedns'):
        cls = get_provider_class(other)
        assert cls.single_value_key('_acme-challenge.A.x.example.') == '_acme-challenge.a.x.example'
        assert apex_and_wildcard_refusal(['x.example', 'a.x.example'], cls) is None


def test_a_duckdns_cleanup_sees_an_order_on_the_same_sub_name(rows, monkeypatch):
    calls = []
    monkeypatch.setattr(client_mod, 'create_provider', lambda *_a: _recording('duckdns', calls))
    sub = uuid.uuid4().hex[:8]
    provider = rows.provider('duckdns')
    rows.order([f'{sub}.duckdns.org'], provider)
    assert AcmeClientService.cleanup_dns_challenge(rows.order([f'a.{sub}.duckdns.org'], provider))[0]
    assert calls == []


def test_a_hurricane_cleanup_ignores_an_order_on_the_parent_name(rows, monkeypatch):
    calls = []
    monkeypatch.setattr(client_mod, 'create_provider', lambda *_a: _recording('hurricane', calls))
    name = _domain()
    provider = rows.provider('hurricane')
    rows.order([name], provider)
    assert AcmeClientService.cleanup_dns_challenge(rows.order([f'a.{name}'], provider))[0]
    assert [c[:2] for c in calls] == [('delete', f'_acme-challenge.a.{name}')]


def test_the_txt_lock_is_taken_on_the_single_value_key(rows, monkeypatch):
    from contextlib import contextmanager
    from services.acme import acme_proxy_service as proxy_mod
    from services import acme_renewal_service as renew_mod

    held = []

    @contextmanager
    def recording(name):
        held.append(name)
        yield
    for module, attr in ((client_mod, 'txt_record_lock'), (proxy_mod, '_txt_record_lock'),
                         (renew_mod, 'txt_record_lock')):
        monkeypatch.setattr(module, attr, recording)
    calls = []
    monkeypatch.setattr(client_mod, 'create_provider', lambda *_a: _recording('duckdns', calls))
    sub = uuid.uuid4().hex[:8]
    provider = rows.provider('duckdns')
    order = rows.order([f'a.{sub}.duckdns.org'], provider)
    svc = AcmeClientService.__new__(AcmeClientService)
    assert svc.setup_dns_challenge(order)[0]
    assert AcmeClientService.cleanup_dns_challenge(order)[0]
    AcmeProxyService._delete_dns_record(_recording('duckdns', calls), 'x', f'_acme-challenge.{sub}.duckdns.org', 'v')
    assert held == [sub, sub, sub]


def test_the_renewal_and_the_proxy_publish_lock_the_single_value_key(rows, monkeypatch):
    from contextlib import contextmanager
    from unittest.mock import MagicMock
    from services.acme import acme_proxy_service as proxy_mod
    from services import acme_renewal_service as renew_mod

    held = []

    @contextmanager
    def recording(name):
        held.append(name)
        yield
    monkeypatch.setattr(proxy_mod, '_txt_record_lock', recording)
    monkeypatch.setattr(renew_mod, 'txt_record_lock', recording)
    sub = uuid.uuid4().hex[:8]
    name = f'a.{sub}.duckdns.org'
    provider = rows.provider('duckdns')
    parent = rows.order([name], provider, status='issued')
    client = MagicMock()
    client.account = None
    client.create_order.return_value = (True, 'ok', rows.order([name], provider))
    client.verify_challenge.side_effect = RuntimeError('STOP')
    with patch.object(renew_mod, 'renewal_client', return_value=client), \
         patch('services.acme.dns_providers.create_provider', return_value=_recording('duckdns', [])), \
         patch.object(renew_mod, 'wait_for_challenges', return_value={'ok': True, 'missing': [], 'waited': 0}):
        with pytest.raises(Exception):
            renew_mod.renew_certificate(db.session.get(AcmeClientOrder, parent.id))
    assert held == [sub, sub]  # publish, then cleanup

    held.clear()
    order = rows.order([name], provider)
    order.is_proxy_order = True
    db.session.commit()
    svc = AcmeProxyService('https://ucm.example/acme/proxy')
    monkeypatch.setattr(svc, '_post_with_account', lambda *_a, **_k: SimpleNamespace(status_code=200, text=''))
    monkeypatch.setattr(proxy_mod, 'wait_for_txt', lambda *_a: {'ok': True, 'waited': 0})
    with patch('api.v2.acme_domains.find_provider_for_domain', return_value={'provider': provider}), \
         patch('services.acme.dns_providers.create_provider', return_value=_recording('duckdns', [])):
        svc._run_dns01_automation('https://ca.example/chall/1', 'token.thumb', name, order.id)
    assert held == [sub]
