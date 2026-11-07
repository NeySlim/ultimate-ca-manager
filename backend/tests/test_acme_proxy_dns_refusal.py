"""ACME proxy dns-01: a TXT record the DNS provider refused is never submitted
upstream (the shared upstream account would count a failed validation), the
order fails locally, and the TXT records of orders that can no longer be issued
are removed."""
import base64
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import services.acme.acme_proxy_service as proxy_mod
from models import db, AcmeClientOrder
from services.acme.acme_proxy_service import AcmeProxyService, ProxyOrderNotReadyError

UPSTREAM = 'https://ca-dns.example'
DIRECTORY_URL = f'{UPSTREAM}/directory'
ORDER_URL = f'{UPSTREAM}/acme/order/dns/1'
AUTHZ_URL = f'{UPSTREAM}/acme/authz/dns/1'
CHALL_URL = f'{UPSTREAM}/acme/chall/dns/1/x'
DOMAIN = 'refused.example.com'


def _b64(url):
    return base64.urlsafe_b64encode(url.encode()).rstrip(b'=').decode()


class _Resp:
    def __init__(self, payload, status_code=200, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.text = json.dumps(payload)
        self.content = self.text.encode()

    def json(self):
        return self._payload


class _ThreadRecorder:
    created = []

    def __init__(self, target=None, args=(), **_kw):
        _ThreadRecorder.created.append((target, args))
        self.name = ''
        self.daemon = False

    def start(self):
        pass


@pytest.fixture(autouse=True)
def _clean(app, monkeypatch):
    _ThreadRecorder.created = []
    monkeypatch.setattr(proxy_mod.threading, 'Thread', _ThreadRecorder)
    yield
    with app.app_context():
        AcmeClientOrder.query.filter_by(is_proxy_order=True).delete()
        db.session.commit()


def _order(**overrides):
    values = dict(domains=json.dumps([DOMAIN]), environment='staging',
                  challenge_type='dns-01', status='pending', order_url=ORDER_URL,
                  upstream_order_url=ORDER_URL, upstream_authz_urls=json.dumps([AUTHZ_URL]),
                  is_proxy_order=True)
    values.update(overrides)
    row = AcmeClientOrder(**values)
    db.session.add(row)
    db.session.commit()
    return row


def _svc(monkeypatch, answers=None):
    calls = []

    def _post(url, payload=None, *_a, **_k):
        calls.append((url, payload))
        if url not in (answers or {}):
            raise AssertionError(f'unexpected upstream call to {url}')
        return answers[url]

    svc = AcmeProxyService('http://localhost/acme/proxy')
    svc.upstream_directory_url = DIRECTORY_URL
    svc.directory = {'newOrder': f'{UPSTREAM}/acme/new-order', 'meta': {}}
    svc.account = SimpleNamespace(id=None, preferred_chain='')
    monkeypatch.setattr(svc, '_post_with_account', _post)
    monkeypatch.setattr(svc, '_get_account_thumbprint', lambda: 'up')
    return svc, calls


def _provider(monkeypatch, create_result):
    model = SimpleNamespace(id=5, provider_type='manual', credentials='{}')
    monkeypatch.setattr('api.v2.acme_domains.find_provider_for_domain',
                        lambda *_a, **_k: {'provider': model})
    provider = MagicMock()
    provider.SINGLE_TXT_VALUE = False
    provider.get_acme_challenge_name.side_effect = lambda d: f'_acme-challenge.{d}'
    if isinstance(create_result, Exception):
        provider.create_txt_record.side_effect = create_result
    else:
        provider.create_txt_record.return_value = create_result
    monkeypatch.setattr('services.acme.dns_providers.create_provider', lambda *_a, **_k: provider)
    monkeypatch.setattr(proxy_mod, 'wait_for_txt',
                        lambda *_a, **_k: {'ok': True, 'missing': [], 'waited': 0})
    monkeypatch.setattr(proxy_mod, 'dns_propagation_timeout', lambda *_a, **_k: 0)
    return provider


class TestRefusedRecordIsNotSubmitted:
    @pytest.mark.parametrize('result', [(False, 'API refused: zone not found'),
                                        RuntimeError('provider unreachable')])
    def test_refusal_fails_the_order_without_an_upstream_call(self, app, monkeypatch, result):
        _provider(monkeypatch, result)
        with app.app_context():
            row = _order()
            svc, calls = _svc(monkeypatch)
            svc._run_dns01_automation(CHALL_URL, 'tok.up', DOMAIN, row.id, AUTHZ_URL)

            assert calls == []
            db.session.refresh(row)
            assert row.status == 'invalid'
            assert not json.loads(row.dns_records_created or '[]')
            assert row.challenges_dict[CHALL_URL]['status'] == 'failed'
            assert 'refused' in row.error_message or 'unreachable' in row.error_message

    def test_accepted_record_is_still_submitted(self, app, monkeypatch):
        _provider(monkeypatch, (True, 'ok'))
        with app.app_context():
            row = _order()
            svc, calls = _svc(monkeypatch, {CHALL_URL: _Resp({'status': 'processing'})})
            svc._run_dns01_automation(CHALL_URL, 'tok.up', DOMAIN, row.id, AUTHZ_URL)

            assert calls == [(CHALL_URL, {})]
            db.session.refresh(row)
            assert row.status == 'pending'
            assert row.challenges_dict[CHALL_URL]['status'] == 'submitted'

    def test_client_sees_the_failed_order_and_authorization(self, app, monkeypatch):
        with app.app_context():
            row = _order(status='invalid', error_message='DNS provider refused')
            row.set_challenges_dict({CHALL_URL: {'status': 'failed', 'error': 'x'}})
            db.session.commit()
            svc, calls = _svc(monkeypatch, {
                ORDER_URL: _Resp({'status': 'pending', 'authorizations': [AUTHZ_URL],
                                  'finalize': f'{ORDER_URL}/finalize'}),
                AUTHZ_URL: _Resp({'status': 'pending',
                                  'identifier': {'type': 'dns', 'value': DOMAIN},
                                  'challenges': [{'type': 'dns-01', 'url': CHALL_URL,
                                                  'status': 'pending', 'token': 'tok'}]}),
            })
            monkeypatch.setattr('api.v2.acme_domains.find_provider_for_domain',
                                lambda *_a, **_k: {'provider': object()})

            order = svc.get_order(_b64(ORDER_URL))
            assert order['status'] == 'invalid'
            assert order['error']['type'] == 'urn:ietf:params:acme:error:serverInternal'

            authz, _ident = svc.get_authz(_b64(AUTHZ_URL))
            assert authz['status'] == 'invalid'
            [chall] = authz['challenges']
            assert chall['status'] == 'invalid' and chall['error']['detail']
            # No new automation for a challenge whose record was refused
            assert _ThreadRecorder.created == []

            with pytest.raises(ProxyOrderNotReadyError):
                svc.finalize_order(_b64(ORDER_URL), 'unused')


class TestRecordsOfDeadOrdersAreRemoved:
    RECORDS = [{'domain': DOMAIN, 'record_name': f'_acme-challenge.{DOMAIN}',
                'value': 'v1', 'provider_id': 5}]

    def _cleanups(self):
        return [args for target, args in _ThreadRecorder.created
                if getattr(target, '__name__', '') == '_bg_cleanup_dns_records']

    def test_invalid_upstream_order_releases_its_records(self, app, monkeypatch):
        with app.app_context():
            row = _order(dns_records_created=json.dumps(self.RECORDS))
            svc, _calls = _svc(monkeypatch, {ORDER_URL: _Resp(
                {'status': 'invalid', 'finalize': f'{ORDER_URL}/finalize'})})
            svc.get_order(_b64(ORDER_URL))

            [(_app, records, order_id)] = self._cleanups()
            assert records == self.RECORDS and order_id == row.id
            db.session.refresh(row)
            assert row.dns_records_created is None

    def test_record_shared_with_a_pending_sibling_is_kept(self, app, monkeypatch):
        with app.app_context():
            _order(dns_records_created=json.dumps(self.RECORDS))
            _order(order_url=f'{ORDER_URL}b', upstream_order_url=f'{ORDER_URL}b')
            svc, _calls = _svc(monkeypatch, {ORDER_URL: _Resp(
                {'status': 'invalid', 'finalize': f'{ORDER_URL}/finalize'})})
            svc.get_order(_b64(ORDER_URL))
            assert self._cleanups() == []

    def test_deactivation_releases_the_records(self, app, monkeypatch):
        authz = {'status': 'pending', 'identifier': {'type': 'dns', 'value': DOMAIN},
                 'challenges': [{'type': 'dns-01', 'url': CHALL_URL, 'status': 'pending'}]}
        with app.app_context():
            _order(dns_records_created=json.dumps(self.RECORDS))
            svc, _calls = _svc(monkeypatch, {AUTHZ_URL: _Resp(authz)})
            real = svc._post_with_account

            def _post(url, payload=None, *a, **k):
                if payload == {'status': 'deactivated'}:
                    return _Resp({**authz, 'status': 'deactivated'})
                return real(url, payload, *a, **k)

            monkeypatch.setattr(svc, '_post_with_account', _post)
            svc.deactivate_authz(_b64(AUTHZ_URL))
            [(_app, records, _order_id)] = self._cleanups()
            assert records == self.RECORDS
