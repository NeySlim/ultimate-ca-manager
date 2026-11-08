"""ACME proxy dns-01: a TXT record the DNS provider refused is never submitted
upstream (the shared upstream account would count a failed validation), the
order fails locally, and the TXT records of orders that can no longer be issued
are removed."""
import base64
import copy
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import requests

import services.acme.acme_proxy_service as proxy_mod
from services.acme import outbound
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
    started = []

    def __init__(self, target=None, args=(), **_kw):
        _ThreadRecorder.created.append((target, args))
        self.target, self.args = target, args
        self.name = ''
        self.daemon = False

    def start(self):
        _ThreadRecorder.started.append((self.target, self.args))


@pytest.fixture(autouse=True)
def _clean(app, monkeypatch):
    _ThreadRecorder.created = []
    _ThreadRecorder.started = []
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

    def test_challenge_of_a_refused_record_reads_invalid(self, app, monkeypatch):
        with app.app_context():
            row = _order(status='invalid')
            row.set_challenges_dict({CHALL_URL: {'status': 'failed', 'error': 'x'}})
            db.session.commit()
            svc, calls = _svc(monkeypatch, {AUTHZ_URL: _Resp({
                'status': 'pending', 'identifier': {'type': 'dns', 'value': DOMAIN},
                'challenges': [{'type': 'dns-01', 'url': CHALL_URL, 'status': 'pending',
                                'token': 'tok'}]})})
            data, _link = svc.respond_challenge(_b64(CHALL_URL))
            assert data['status'] == 'invalid' and data['error']['detail']
            assert calls == [(AUTHZ_URL, '')]
            assert _ThreadRecorder.created == []


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


OTHER = 'other.example.com'
AUTHZ_B = f'{UPSTREAM}/acme/authz/dns/2'
CHALL_B = f'{UPSTREAM}/acme/chall/dns/2/x'


def _authz(status='pending', domain=DOMAIN, chall=CHALL_URL, chall_status='pending'):
    return {'status': status, 'identifier': {'type': 'dns', 'value': domain},
            'challenges': [{'type': 'dns-01', 'url': chall, 'status': chall_status,
                            'token': 'tok'}]}


def _refused(**overrides):
    row = _order(status='invalid', **overrides)
    row.set_challenges_dict({CHALL_URL: {'status': 'failed', 'error': 'x'}})
    db.session.commit()
    return row


def _two_names(**overrides):
    return _order(domains=json.dumps([DOMAIN, OTHER]),
                  upstream_authz_urls=json.dumps([AUTHZ_URL, AUTHZ_B]), **overrides)


@pytest.fixture
def _quiet_rows(monkeypatch):
    monkeypatch.setattr(proxy_mod, '_dns_rows_hook', lambda *_a, **_k: None)
    monkeypatch.setattr('api.v2.acme_domains.find_provider_for_domain',
                        lambda *_a, **_k: {'provider': object()})


def _automation_orders():
    return [args[4] for target, args in _ThreadRecorder.created
            if getattr(target, '__name__', '') == '_bg_respond_challenge']


def _started_automations():
    return [args[4] for target, args in _ThreadRecorder.started
            if getattr(target, '__name__', '') == '_bg_respond_challenge']


def _cleanups():
    return [args for target, args in _ThreadRecorder.created
            if getattr(target, '__name__', '') == '_bg_cleanup_dns_records']


@pytest.mark.usefixtures('_quiet_rows')
class TestRetryAfterARefusal:
    """The upstream CA hands the still-pending authorization (and order) of the
    refused order to the client's next order: that new order is the one served."""

    def test_next_order_on_the_same_authorization_is_served(self, app, monkeypatch):
        with app.app_context():
            _refused(client_jwk_thumbprint='T')
            live = _order(client_jwk_thumbprint='T', order_url=f'{ORDER_URL}b',
                          upstream_order_url=f'{ORDER_URL}b')
            svc, _calls = _svc(monkeypatch, {AUTHZ_URL: _Resp(_authz())})
            authz, _ident = svc.get_authz(_b64(AUTHZ_URL), requester_thumbprint='T')
            assert authz['status'] == 'pending'
            assert authz['challenges'][0]['status'] == 'pending'
            assert _automation_orders() == [live.id]

    def test_next_order_on_the_same_upstream_order_is_served(self, app, monkeypatch):
        with app.app_context():
            _refused(client_jwk_thumbprint='T')
            _order(client_jwk_thumbprint='T')
            svc, _calls = _svc(monkeypatch, {ORDER_URL: _Resp(
                {'status': 'pending', 'authorizations': [AUTHZ_URL],
                 'finalize': f'{ORDER_URL}/finalize'})})
            order = svc.get_order(_b64(ORDER_URL), requester_thumbprint='T')
            assert order['status'] == 'pending' and 'error' not in order

    def test_certificate_of_the_retry_lands_on_the_live_order(self, app, monkeypatch):
        cert_url = f'{UPSTREAM}/acme/cert/dns/1'
        with app.app_context():
            dead = _refused(client_jwk_thumbprint='T')
            live = _order(client_jwk_thumbprint='T')
            svc, _calls = _svc(monkeypatch, {ORDER_URL: _Resp(
                {'status': 'valid', 'authorizations': [AUTHZ_URL],
                 'finalize': f'{ORDER_URL}/finalize', 'certificate': cert_url})})
            svc.get_order(_b64(ORDER_URL), requester_thumbprint='T')
            db.session.refresh(dead)
            db.session.refresh(live)
            assert (dead.certificate_url, live.certificate_url) == (None, cert_url)
            assert svc._find_order_for_certificate(cert_url, requester_thumbprint='T').id == live.id


@pytest.mark.usefixtures('_quiet_rows')
class TestRefusalOnAnotherNameOfTheOrder:
    def test_record_of_the_other_name_is_not_submitted(self, app, monkeypatch):
        provider = _provider(monkeypatch, (True, 'ok'))
        with app.app_context():
            row = _two_names()
            svc, calls = _svc(monkeypatch, {CHALL_B: _Resp({'status': 'processing'})})
            order_id = row.id

            def _refuse_the_first_name(*_a, **_k):
                # The other authorization's thread is refused while this one writes
                svc._fail_dns_automation(db.session.get(AcmeClientOrder, order_id),
                                         CHALL_URL, DOMAIN, 'refused')
                return True, 'ok'
            provider.create_txt_record.side_effect = _refuse_the_first_name

            svc._run_dns01_automation(CHALL_B, 'tok.up', OTHER, order_id, AUTHZ_B)

            assert calls == []
            [(_app, records, cleaned_id)] = _cleanups()
            assert cleaned_id == order_id
            assert {r['record_name'] for r in records} == {f'_acme-challenge.{OTHER}'}
            db.session.refresh(row)
            assert not json.loads(row.dns_records_created or '[]')

    def test_shared_authorization_is_still_submitted_for_a_live_order(self, app, monkeypatch):
        provider = _provider(monkeypatch, (True, 'ok'))
        with app.app_context():
            row = _two_names()
            _order(domains=json.dumps([OTHER]), upstream_authz_urls=json.dumps([AUTHZ_B]),
                   order_url=f'{ORDER_URL}b', upstream_order_url=f'{ORDER_URL}b')
            svc, calls = _svc(monkeypatch, {CHALL_B: _Resp({'status': 'processing'})})
            order_id = row.id

            def _refuse_the_first_name(*_a, **_k):
                svc._fail_dns_automation(db.session.get(AcmeClientOrder, order_id),
                                         CHALL_URL, DOMAIN, 'refused')
                return True, 'ok'
            provider.create_txt_record.side_effect = _refuse_the_first_name

            svc._run_dns01_automation(CHALL_B, 'tok.up', OTHER, order_id, AUTHZ_B)
            assert calls == [(CHALL_B, {})]

    def test_retry_restarts_the_automation_the_dead_order_gave_up(self, app, monkeypatch):
        provider = _provider(monkeypatch, (True, 'ok'))
        provider.create_txt_record.side_effect = [(False, 'zone not found'), (True, 'ok')]
        with app.app_context():
            row = _two_names(client_jwk_thumbprint='T')
            row.set_challenges_dict({CHALL_URL: {'status': 'initiated'},
                                     CHALL_B: {'status': 'initiated'}})
            db.session.commit()
            svc, calls = _svc(monkeypatch, {AUTHZ_B: _Resp(_authz(domain=OTHER, chall=CHALL_B))})
            svc._run_dns01_automation(CHALL_URL, 'tok.up', DOMAIN, row.id, AUTHZ_URL)
            svc._run_dns01_automation(CHALL_B, 'tok.up', OTHER, row.id, AUTHZ_B)
            assert calls == []

            # The CA hands the same pending authorizations to the client's next order
            retry = _two_names(client_jwk_thumbprint='T', order_url=f'{ORDER_URL}b',
                               upstream_order_url=f'{ORDER_URL}b')
            svc.get_authz(_b64(AUTHZ_B), requester_thumbprint='T')
            assert _automation_orders() == [retry.id]

    def test_refusal_releases_the_records_of_the_other_name(self, app, monkeypatch):
        _provider(monkeypatch, (False, 'zone not found'))
        records = [{'domain': OTHER, 'record_name': f'_acme-challenge.{OTHER}',
                    'value': 'v2', 'provider_id': 5}]
        with app.app_context():
            row = _two_names(dns_records_created=json.dumps(records))
            svc, calls = _svc(monkeypatch)
            svc._run_dns01_automation(CHALL_URL, 'tok.up', DOMAIN, row.id, AUTHZ_URL)
            assert calls == []
            [(_app, released, _order_id)] = _cleanups()
            assert released == records

    def test_other_authorization_starts_no_automation(self, app, monkeypatch):
        with app.app_context():
            _refused(domains=json.dumps([DOMAIN, OTHER]),
                     upstream_authz_urls=json.dumps([AUTHZ_URL, AUTHZ_B]))
            svc, _calls = _svc(monkeypatch, {AUTHZ_B: _Resp(_authz(domain=OTHER, chall=CHALL_B))})
            authz, _ident = svc.get_authz(_b64(AUTHZ_B))
            assert authz['status'] == 'invalid'
            assert authz['challenges'][0]['status'] == 'invalid'
            assert _ThreadRecorder.created == []

    def test_other_challenge_starts_no_automation(self, app, monkeypatch):
        with app.app_context():
            _refused(domains=json.dumps([DOMAIN, OTHER]),
                     upstream_authz_urls=json.dumps([AUTHZ_URL, AUTHZ_B]))
            svc, calls = _svc(monkeypatch, {
                AUTHZ_URL: _Resp(_authz()),
                AUTHZ_B: _Resp(_authz(domain=OTHER, chall=CHALL_B))})
            data, _link = svc.respond_challenge(_b64(CHALL_B))
            assert data['status'] == 'invalid' and data['error']['detail']
            assert calls and all(payload == '' for _url, payload in calls)
            assert _ThreadRecorder.created == []


@pytest.mark.usefixtures('_quiet_rows')
class TestDeadOrdersSharingAnAuthorization:
    RECORDS = [{'domain': DOMAIN, 'record_name': f'_acme-challenge.{DOMAIN}',
                'value': 'v1', 'provider_id': 5}]

    def test_invalid_authorization_releases_the_records(self, app, monkeypatch):
        with app.app_context():
            row = _order(dns_records_created=json.dumps(self.RECORDS))
            svc, _calls = _svc(monkeypatch, {AUTHZ_URL: _Resp(
                _authz(status='invalid', chall_status='invalid'))})
            svc.get_authz(_b64(AUTHZ_URL))
            [(_app, records, order_id)] = _cleanups()
            assert records == self.RECORDS and order_id == row.id

    def test_sibling_on_the_invalid_authorization_does_not_keep_them(self, app, monkeypatch):
        with app.app_context():
            first = _order(dns_records_created=json.dumps(self.RECORDS),
                           client_jwk_thumbprint='T1')
            second = _order(order_url=f'{ORDER_URL}b', upstream_order_url=f'{ORDER_URL}b',
                            dns_records_created=json.dumps(self.RECORDS),
                            client_jwk_thumbprint='T2')
            svc, _calls = _svc(monkeypatch, {AUTHZ_URL: _Resp(
                _authz(status='invalid', chall_status='invalid'))})
            svc.get_authz(_b64(AUTHZ_URL), requester_thumbprint='T1')
            [(_app, _records, order_id)] = _cleanups()
            assert order_id == first.id
            db.session.refresh(second)
            assert second.status == 'invalid'

    def test_non_pending_sibling_does_not_keep_them(self, app, monkeypatch):
        with app.app_context():
            row = _order(dns_records_created=json.dumps(self.RECORDS))
            _order(order_url=f'{ORDER_URL}b', upstream_order_url=f'{ORDER_URL}b',
                   status='invalid')
            svc, _calls = _svc(monkeypatch)
            svc._release_order_records(row)
            [(_app, records, _order_id)] = _cleanups()
            assert records == self.RECORDS

    def test_invalid_upstream_order_marks_the_local_order(self, app, monkeypatch):
        with app.app_context():
            row = _order()
            svc, _calls = _svc(monkeypatch, {ORDER_URL: _Resp(
                {'status': 'invalid', 'finalize': f'{ORDER_URL}/finalize'})})
            svc.get_order(_b64(ORDER_URL))
            db.session.refresh(row)
            assert row.status == 'invalid'


@pytest.mark.usefixtures('_quiet_rows')
class TestAuthorizationReads:
    def test_authorization_retry_after_is_kept(self, app, monkeypatch):
        with app.app_context():
            _order()
            svc, _calls = _svc(monkeypatch, {AUTHZ_URL: _Resp(
                _authz(chall_status='processing'), headers={'Retry-After': '30'})})
            svc.get_authz(_b64(AUTHZ_URL))
            assert svc.retry_after == '30'

    def test_challenge_scan_reads_at_most_the_limit(self, app, monkeypatch):
        urls = [f'{UPSTREAM}/acme/authz/dns/scan/{i}' for i in range(40)]
        with app.app_context():
            row = _order(upstream_authz_urls=json.dumps(urls))
            svc, calls = _svc(monkeypatch, {url: _Resp(_authz(chall=f'{url}/c')) for url in urls})
            with pytest.raises(proxy_mod.ProxyResourceNotFoundError):
                svc._read_challenge(f'{UPSTREAM}/acme/chall/unnamed/x', None, [row])
            assert len(calls) == proxy_mod._CHALLENGE_SCAN_LIMIT == 3

    def test_unknown_challenge_under_a_known_authorization_reads_only_it(self, app, monkeypatch):
        urls = [f'{UPSTREAM}/acme/authz/7/{i}' for i in range(40)]
        with app.app_context():
            row = _order(upstream_authz_urls=json.dumps(urls))
            svc, calls = _svc(monkeypatch, {url: _Resp(_authz(chall=f'{url}/c')) for url in urls})
            with pytest.raises(proxy_mod.ProxyResourceNotFoundError):
                svc._read_challenge(f'{UPSTREAM}/acme/chall/7/35/forged', None, [row])
            assert calls == [(urls[35], '')]

    def test_scan_reads_first_the_authorization_named_in_the_challenge_url(self, app, monkeypatch):
        # Let's Encrypt nests the authorization id in the challenge URL
        urls = [f'{UPSTREAM}/acme/authz/7/{i}' for i in range(40)]
        wanted = f'{UPSTREAM}/acme/chall/7/35/Xy'
        with app.app_context():
            row = _order(upstream_authz_urls=json.dumps(urls))
            answers = {url: _Resp(_authz(chall=f'{UPSTREAM}/acme/chall/7/{i}/Xy'))
                       for i, url in enumerate(urls)}
            svc, calls = _svc(monkeypatch, answers)
            url, _authz_doc, chall = svc._read_challenge(wanted, None, [row])
            assert url == urls[35] and chall['url'] == wanted
            assert len(calls) == 1


BAD_NONCE = {'type': 'urn:ietf:params:acme:error:badNonce', 'detail': 'JWS has an invalid anti-replay nonce'}


class _FailingPost:
    """Upstream challenge POST that answers ``answer`` or raises it."""

    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def __call__(self, url, payload=None, *_a, **_k):
        self.calls.append((url, payload))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


@pytest.mark.usefixtures('_quiet_rows')
class TestChallengeSubmissionFailure:
    """The upstream POST of the challenge fails: the order fails locally, its TXT
    records are released and the next order on the authorization starts afresh."""

    @pytest.mark.parametrize('answer, rechecked', [
        (_Resp(BAD_NONCE, 400, {'Replay-Nonce': 'n'}), False),
        (_Resp({'type': 'urn:ietf:params:acme:error:rateLimited'}, 429), False),
        (requests.exceptions.ConnectTimeout('upstream unreachable'), False),
        (_Resp({'type': 'urn:ietf:params:acme:error:serverInternal', 'detail': 'boom'}, 500), True),
        (requests.exceptions.ReadTimeout('no answer'), True),
        (requests.exceptions.ConnectionError('Connection aborted.', 'RemoteDisconnected'), True),
    ])
    def test_failed_post_fails_the_order_and_releases_its_records(self, app, monkeypatch,
                                                                  answer, rechecked):
        _provider(monkeypatch, (True, 'ok'))
        with app.app_context():
            row = _order(client_jwk_thumbprint='T')
            row.set_challenges_dict({CHALL_URL: {'status': 'initiated'}})
            db.session.commit()
            svc, _calls = _svc(monkeypatch)
            post = _FailingPost(answer)
            monkeypatch.setattr(svc, '_post_with_account', post)
            svc._run_dns01_automation(CHALL_URL, 'tok.up', DOMAIN, row.id, AUTHZ_URL)

            # An answer that may hide a received POST is checked on the authorization
            assert post.calls == [(CHALL_URL, {})] + ([(AUTHZ_URL, '')] if rechecked else [])
            db.session.refresh(row)
            assert row.status == 'invalid'
            assert row.challenges_dict[CHALL_URL]['status'] == 'failed'
            assert row.error_message
            # An authorization left unread may hide a received POST: its record stays a while,
            # listed until deleted
            listed = json.loads(row.dns_records_created or '[]')
            assert bool(listed) == rechecked and all(r['release_at'] for r in listed)
            [(_app, released, order_id, *delay)] = _cleanups()
            assert order_id == row.id
            assert {r['record_name'] for r in released} == {f'_acme-challenge.{DOMAIN}'}
            assert delay == ([proxy_mod._SUBMITTED_RECORD_LINGER] if rechecked else [])

    def test_client_reads_the_failure_and_its_next_order_is_served(self, app, monkeypatch):
        _provider(monkeypatch, (True, 'ok'))
        with app.app_context():
            row = _order(client_jwk_thumbprint='T')
            row.set_challenges_dict({CHALL_URL: {'status': 'initiated'}})
            db.session.commit()
            svc, _calls = _svc(monkeypatch)
            monkeypatch.setattr(svc, '_post_with_account', _FailingPost(_Resp(
                {'type': 'urn:ietf:params:acme:error:rateLimited', 'detail': 'slow down'}, 429)))
            svc._run_dns01_automation(CHALL_URL, 'tok.up', DOMAIN, row.id, AUTHZ_URL)

            svc, _calls = _svc(monkeypatch, {
                ORDER_URL: _Resp({'status': 'pending', 'authorizations': [AUTHZ_URL],
                                  'finalize': f'{ORDER_URL}/finalize'}),
                AUTHZ_URL: _Resp(_authz())})
            order = svc.get_order(_b64(ORDER_URL), requester_thumbprint='T')
            assert order['status'] == 'invalid'
            assert order['error']['type'] == 'urn:ietf:params:acme:error:rateLimited'
            authz, _ident = svc.get_authz(_b64(AUTHZ_URL), requester_thumbprint='T')
            assert authz['challenges'][0]['status'] == 'invalid'
            with pytest.raises(ProxyOrderNotReadyError):
                svc.finalize_order(_b64(ORDER_URL), 'unused', requester_thumbprint='T')

            retry = _order(client_jwk_thumbprint='T', order_url=f'{ORDER_URL}b',
                           upstream_order_url=f'{ORDER_URL}b')
            _ThreadRecorder.created = []
            svc, _calls = _svc(monkeypatch, {AUTHZ_URL: _Resp(_authz())})
            svc.get_authz(_b64(AUTHZ_URL), requester_thumbprint='T')
            assert _automation_orders() == [retry.id]


class _Upstream:
    """Upstream answers by URL; an exception answer is raised."""

    def __init__(self, answers):
        self.answers = dict(answers)
        self.calls = []

    def __call__(self, url, payload=None, *_a, **_k):
        self.calls.append((url, payload))
        answer = self.answers[url]
        if isinstance(answer, Exception):
            raise answer
        return answer


def _csr_pem(domain):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    csr = (x509.CertificateSigningRequestBuilder().subject_name(x509.Name([]))
           .add_extension(x509.SubjectAlternativeName([x509.DNSName(domain)]), False)
           .sign(ec.generate_private_key(ec.SECP256R1()), hashes.SHA256()))
    return csr.public_bytes(serialization.Encoding.PEM).decode()


def _txt(key_authz):
    return base64.urlsafe_b64encode(hashlib.sha256(key_authz.encode()).digest()).rstrip(b'=').decode()


@pytest.mark.usefixtures('_quiet_rows')
class TestAmbiguousSubmission:
    """A POST that may have reached the CA (no answer, 5xx) is checked on the
    authorization: a challenge the CA took is submitted, its record kept."""

    def _run(self, app, monkeypatch, answer, authz):
        _provider(monkeypatch, (True, 'ok'))
        row = _order(client_jwk_thumbprint='T')
        row.set_challenges_dict({CHALL_URL: {'status': 'initiated'}})
        db.session.commit()
        svc, _calls = _svc(monkeypatch)
        upstream = _Upstream({CHALL_URL: answer, AUTHZ_URL: _Resp(authz),
                              ORDER_URL: _Resp({'status': 'ready', 'authorizations': [AUTHZ_URL],
                                                'finalize': f'{ORDER_URL}/finalize'})})
        monkeypatch.setattr(svc, '_post_with_account', upstream)
        svc._run_dns01_automation(CHALL_URL, 'tok.up', DOMAIN, row.id, AUTHZ_URL)
        db.session.refresh(row)
        return svc, row, upstream

    @pytest.mark.parametrize('answer', [
        requests.exceptions.ReadTimeout('read timed out'),
        _Resp({'type': 'urn:ietf:params:acme:error:serverInternal', 'detail': 'boom'}, 502),
    ])
    @pytest.mark.parametrize('authz', [
        _authz(status='valid', chall_status='valid'),
        _authz(chall_status='processing'),
        _authz(chall_status='invalid'),
        _authz(status='valid'),
        _authz(status='invalid'),
    ])
    def test_challenge_the_ca_took_is_submitted(self, app, monkeypatch, answer, authz):
        with app.app_context():
            svc, row, upstream = self._run(app, monkeypatch, answer, authz)
            assert upstream.calls == [(CHALL_URL, {}), (AUTHZ_URL, '')]
            assert row.status == 'pending'
            assert row.challenges_dict[CHALL_URL]['status'] == 'submitted'
            assert json.loads(row.dns_records_created)
            assert _cleanups() == []
            order = svc.get_order(_b64(ORDER_URL), requester_thumbprint='T')
            assert order['status'] == 'ready' and 'error' not in order

    def test_challenge_still_pending_fails_the_order(self, app, monkeypatch):
        with app.app_context():
            _svc_, row, upstream = self._run(
                app, monkeypatch, requests.exceptions.ReadTimeout('read timed out'), _authz())
            assert upstream.calls == [(CHALL_URL, {}), (AUTHZ_URL, '')]
            assert row.status == 'invalid'
            assert row.challenges_dict[CHALL_URL]['status'] == 'failed'
            assert 'did not answer' in row.challenges_dict[CHALL_URL]['problem']['detail']
            [(_app, released, _order_id)] = _cleanups()
            assert released

    def test_unread_authorization_keeps_the_record_a_while(self, app, monkeypatch):
        with app.app_context():
            _provider(monkeypatch, (True, 'ok'))
            row = _order(client_jwk_thumbprint='T')
            row.set_challenges_dict({CHALL_URL: {'status': 'initiated'}})
            db.session.commit()
            svc, _calls = _svc(monkeypatch)
            monkeypatch.setattr(svc, '_post_with_account', _Upstream({
                CHALL_URL: requests.exceptions.ReadTimeout('read timed out'),
                AUTHZ_URL: requests.exceptions.ReadTimeout('read timed out')}))
            svc._run_dns01_automation(CHALL_URL, 'tok.up', DOMAIN, row.id, AUTHZ_URL)
            db.session.refresh(row)
            assert row.status == 'invalid'
            [(_app, released, _order_id, delay)] = _cleanups()
            assert _txt('tok.up') in [r['value'] for r in released]
            assert delay == proxy_mod._SUBMITTED_RECORD_LINGER

    def test_validation_the_ca_finished_later_does_not_revive_the_order(self, app, monkeypatch):
        """POST and authorization read time out, then the CA validates with the lingering
        TXT: invalid stays final for the order, its authorization and challenge (RFC 8555 §7.1.6)."""
        with app.app_context():
            _provider(monkeypatch, (True, 'ok'))
            row = _order(client_jwk_thumbprint='T')
            row.set_challenges_dict({CHALL_URL: {'status': 'initiated'}})
            db.session.commit()
            svc, _calls = _svc(monkeypatch)
            monkeypatch.setattr(svc, '_post_with_account', _Upstream({
                CHALL_URL: requests.exceptions.ReadTimeout('read timed out'),
                AUTHZ_URL: requests.exceptions.ReadTimeout('read timed out')}))
            svc._run_dns01_automation(CHALL_URL, 'tok.up', DOMAIN, row.id, AUTHZ_URL)

            seen = []
            for order_status, authz in (('pending', _authz()),
                                        ('ready', _authz(status='valid', chall_status='valid'))):
                def answers():
                    return {ORDER_URL: _Resp({'status': order_status, 'authorizations': [AUTHZ_URL],
                                              'finalize': f'{ORDER_URL}/finalize'}),
                            AUTHZ_URL: _Resp(copy.deepcopy(authz))}
                svc, _calls = _svc(monkeypatch, answers())
                authz_view, _ident = svc.get_authz(_b64(AUTHZ_URL), requester_thumbprint='T')
                svc, _calls = _svc(monkeypatch, answers())
                chall, _link = svc.respond_challenge(_b64(CHALL_URL), requester_thumbprint='T')
                seen.append((svc.get_order(_b64(ORDER_URL), requester_thumbprint='T')['status'],
                             authz_view['status'], authz_view['challenges'][0]['status'],
                             chall['status']))
            assert seen == [('invalid',) * 4] * 2
            assert _started_automations() == []
            with pytest.raises(ProxyOrderNotReadyError, match='did not answer'):
                svc.finalize_order(_b64(ORDER_URL), _csr_pem(DOMAIN), requester_thumbprint='T')

    @pytest.mark.parametrize('upstream_status', ['pending', 'ready', 'processing', 'valid'])
    def test_local_failure_stays_invalid_whatever_the_upstream_order(
            self, app, monkeypatch, upstream_status):
        with app.app_context():
            row = _failed_order()
            payload = {'status': upstream_status, 'authorizations': [AUTHZ_URL],
                       'finalize': f'{ORDER_URL}/finalize'}
            if upstream_status == 'valid':
                payload['certificate'] = f'{UPSTREAM}/acme/cert/dns/1'
            svc, _calls = _svc(monkeypatch, {ORDER_URL: _Resp(payload)})
            order = svc.get_order(_b64(ORDER_URL), requester_thumbprint='T')
            assert order['status'] == 'invalid'
            assert order['error']['type'] == 'urn:ietf:params:acme:error:rateLimited'
            assert 'certificate' not in order
            db.session.refresh(row)
            assert row.certificate_url is None

    def test_finalize_after_a_local_failure_is_refused_without_upstream_call(self, app, monkeypatch):
        with app.app_context():
            _failed_order()
            svc, calls = _svc(monkeypatch)
            with pytest.raises(ProxyOrderNotReadyError, match='invalid.*slow down'):
                svc.finalize_order(_b64(ORDER_URL), _csr_pem(DOMAIN), requester_thumbprint='T')
            assert calls == []


def _failed_order(**overrides):
    row = _order(client_jwk_thumbprint='T', status='invalid', **overrides)
    row.set_challenges_dict({CHALL_URL: {'status': 'failed', 'error': 'x', 'problem': {
        'type': 'urn:ietf:params:acme:error:rateLimited', 'detail': 'slow down'}}})
    db.session.commit()
    return row


@pytest.mark.usefixtures('_quiet_rows')
class TestRetryAfterTheCaValidated:
    """The CA validated the challenge of a locally failed order: the client's next
    order reuses that authorization and is ready without a new validation."""

    @pytest.mark.parametrize('retry_url', [f'{ORDER_URL}b', ORDER_URL])
    def test_retried_order_reuses_the_validated_authorization(self, app, monkeypatch, retry_url):
        from models import DnsProvider
        _provider(monkeypatch, (True, 'ok'))
        with app.app_context():
            model = DnsProvider(name='retry-validated', provider_type='manual', credentials='{}')
            db.session.add(model)
            db.session.commit()
            monkeypatch.setattr('api.v2.acme_domains.find_provider_for_domain',
                                lambda *_a, **_k: {'provider': model})
            try:
                _failed_order()
                ready = {'status': 'ready', 'authorizations': [AUTHZ_URL],
                         'finalize': f'{retry_url}/finalize'}
                svc, calls = _svc(monkeypatch, {
                    f'{UPSTREAM}/acme/new-order': _Resp(dict(ready), 201, {'Location': retry_url}),
                    AUTHZ_URL: _Resp(_authz(status='valid', chall_status='valid')),
                    retry_url: _Resp(dict(ready)),
                    f'{retry_url}/finalize': _Resp({'status': 'processing',
                                                    'finalize': f'{retry_url}/finalize'})})
                order, order_id = svc.new_order([{'type': 'dns', 'value': DOMAIN}],
                                                client_thumbprint='T')
                assert order['status'] == 'ready'
                authz, _ident = svc.get_authz(_b64(AUTHZ_URL), requester_thumbprint='T')
                assert authz['status'] == 'valid'
                assert authz['challenges'][0]['status'] == 'valid'
                assert svc.get_order(order_id, requester_thumbprint='T')['status'] == 'ready'
                done = svc.finalize_order(order_id, _csr_pem(DOMAIN), requester_thumbprint='T')
                assert done['status'] == 'processing'
                assert CHALL_URL not in [url for url, _payload in calls]
                assert _started_automations() == []
            finally:
                AcmeClientOrder.query.filter_by(is_proxy_order=True).delete()
                db.session.delete(model)
                db.session.commit()


@pytest.mark.usefixtures('_quiet_rows')
class TestProblemWithoutDetail:
    """RFC 7807 §3.1: ``detail`` is optional; its absence must not stall the order."""

    def test_rate_limit_without_detail_fails_the_order(self, app, monkeypatch):
        _provider(monkeypatch, (True, 'ok'))
        with app.app_context():
            row = _order(client_jwk_thumbprint='T')
            row.set_challenges_dict({CHALL_URL: {'status': 'initiated'}})
            db.session.commit()
            svc, _calls = _svc(monkeypatch)
            monkeypatch.setattr(svc, '_post_with_account', _FailingPost(_Resp(
                {'type': 'urn:ietf:params:acme:error:rateLimited'}, 429)))
            svc._run_dns01_automation(CHALL_URL, 'tok.up', DOMAIN, row.id, AUTHZ_URL)
            db.session.refresh(row)
            assert row.status == 'invalid'
            assert row.challenges_dict[CHALL_URL]['status'] == 'failed'
            assert 'rateLimited' in row.error_message

            svc, _calls = _svc(monkeypatch, {ORDER_URL: _Resp(
                {'status': 'pending', 'authorizations': [AUTHZ_URL],
                 'finalize': f'{ORDER_URL}/finalize'})})
            with pytest.raises(ProxyOrderNotReadyError, match='rateLimited'):
                svc.finalize_order(_b64(ORDER_URL), 'unused', requester_thumbprint='T')


@pytest.mark.usefixtures('_quiet_rows')
class TestSubmittedRecordOutlivesASiblingFailure:
    def test_record_of_a_submitted_challenge_is_released_later(self, app, monkeypatch):
        records = [{'domain': DOMAIN, 'record_name': f'_acme-challenge.{DOMAIN}',
                    'value': 'v1', 'provider_id': 5},
                   {'domain': OTHER, 'record_name': f'_acme-challenge.{OTHER}',
                    'value': 'v2', 'provider_id': 5}]
        _provider(monkeypatch, (True, 'ok'))
        with app.app_context():
            row = _two_names(dns_records_created=json.dumps(records))
            row.set_challenges_dict({
                CHALL_B: {'status': 'submitted', 'records': [[f'_acme-challenge.{OTHER}', 'v2']]},
                CHALL_URL: {'status': 'initiated'}})
            db.session.commit()
            svc, _calls = _svc(monkeypatch)
            svc._fail_dns_automation(row, CHALL_URL, DOMAIN, 'refused')
            by_delay = {(args[3] if len(args) > 3 else 0): args[1] for args in _cleanups()}
            assert by_delay.pop(0) == records[:1]
            [(delay, kept)] = by_delay.items()
            assert [{k: v for k, v in r.items() if k != 'release_at'} for r in kept] == records[1:]
            assert delay > 0 and all(r['release_at'] for r in kept)

    def test_lingering_record_is_deleted_only_after_the_wait(self, app, monkeypatch):
        from models import DnsProvider
        provider = _provider(monkeypatch, (True, 'ok'))
        events = []
        provider.delete_txt_record.side_effect = (
            lambda _zone, name, _value: events.append(('delete', name)) or (True, 'ok'))
        monkeypatch.setattr(proxy_mod.time, 'sleep', lambda seconds: events.append(('sleep', seconds)))
        with app.app_context():
            model = DnsProvider(name='linger-wait', provider_type='manual', credentials='{}')
            db.session.add(model)
            db.session.commit()
            records = [{'domain': DOMAIN, 'record_name': f'_acme-challenge.{DOMAIN}',
                        'value': 'v1', 'provider_id': model.id},
                       {'domain': OTHER, 'record_name': f'_acme-challenge.{OTHER}',
                        'value': 'v2', 'provider_id': model.id}]
            row = _two_names(dns_records_created=json.dumps(records))
            row.set_challenges_dict({
                CHALL_B: {'status': 'submitted', 'records': [[f'_acme-challenge.{OTHER}', 'v2']]},
                CHALL_URL: {'status': 'initiated'}})
            db.session.commit()
            svc, _calls = _svc(monkeypatch)
            svc._fail_dns_automation(row, CHALL_URL, DOMAIN, 'refused')
            try:
                for target, args in _ThreadRecorder.created:
                    target(*args)
                    events.append(('done',))
            finally:
                db.session.delete(model)
                db.session.commit()
            assert events == [('delete', f'_acme-challenge.{DOMAIN}'), ('done',),
                              ('sleep', proxy_mod._SUBMITTED_RECORD_LINGER),
                              ('delete', f'_acme-challenge.{OTHER}'), ('done',)]


@pytest.mark.usefixtures('_quiet_rows')
class TestValueAlreadyPublishedBySibling:
    def test_sibling_record_is_not_written_again(self, app, monkeypatch):
        provider = _provider(monkeypatch, (False, 'record already exists'))
        name = f'_acme-challenge.{DOMAIN}'
        mine = {'domain': DOMAIN, 'record_name': name, 'value': _txt('tok.up'), 'provider_id': 5}
        with app.app_context():
            _order(status='invalid', dns_records_created=json.dumps([mine]))
            row = _order(order_url=f'{ORDER_URL}b', upstream_order_url=f'{ORDER_URL}b')
            svc, calls = _svc(monkeypatch, {CHALL_URL: _Resp({'status': 'processing'})})
            svc._run_dns01_automation(CHALL_URL, 'tok.up', DOMAIN, row.id, AUTHZ_URL)
            assert provider.create_txt_record.call_count == 0
            assert calls == [(CHALL_URL, {})]
            db.session.refresh(row)
            assert row.challenges_dict[CHALL_URL]['status'] == 'submitted'
            assert [r['value'] for r in json.loads(row.dns_records_created)] == [mine['value']]


class TestBadNonceRetries:
    """RFC 8555 §6.5: each badNonce answer carries the nonce of the next attempt."""

    def _svc(self, monkeypatch, answers):
        svc = AcmeProxyService.__new__(AcmeProxyService)
        sent = []

        def _sign_and_post(url, payload, nonce, kid=None):
            sent.append(nonce)
            return answers[len(sent) - 1]

        monkeypatch.setattr(svc, '_get_nonce', lambda: 'n0')
        monkeypatch.setattr(svc, '_sign_and_post', _sign_and_post)
        return svc, sent

    def test_two_bad_nonces_in_a_row_are_retried(self, monkeypatch):
        answers = [_Resp(BAD_NONCE, 400, {'Replay-Nonce': 'n1'}),
                   _Resp(BAD_NONCE, 400, {'Replay-Nonce': 'n2'}),
                   _Resp({'status': 'processing'})]
        svc, sent = self._svc(monkeypatch, answers)
        resp = svc._post_jws(CHALL_URL, {}, kid='k')
        assert resp.status_code == 200
        assert sent == ['n0', 'n1', 'n2']

    def test_retries_are_bounded(self, monkeypatch):
        answers = [_Resp(BAD_NONCE, 400, {'Replay-Nonce': f'n{i + 1}'}) for i in range(10)]
        svc, sent = self._svc(monkeypatch, answers)
        resp = svc._post_jws(CHALL_URL, {}, kid='k')
        assert resp.status_code == 400
        assert len(sent) == 1 + outbound.BAD_NONCE_RETRIES

    def test_other_400_is_not_retried(self, monkeypatch):
        answers = [_Resp({'type': 'urn:ietf:params:acme:error:malformed'}, 400,
                         {'Replay-Nonce': 'n1'})]
        svc, sent = self._svc(monkeypatch, answers)
        assert svc._post_jws(CHALL_URL, {}, kid='k').status_code == 400
        assert sent == ['n0']


def _in_another_thread(app, fn):
    """Run ``fn`` to completion in a real thread with its own app context and session
    (threading.Thread is replaced by a recorder in this module)."""
    import _thread
    import threading
    done, errors = threading.Event(), []

    def body():
        try:
            with app.app_context():
                try:
                    fn()
                finally:
                    db.session.remove()
        except BaseException as exc:  # noqa: BLE001 - re-raised in the test thread
            errors.append(exc)
        finally:
            done.set()

    _thread.start_new_thread(body, ())
    assert done.wait(30)
    if errors:
        raise errors[0]


def _fresh(order_id):
    db.session.expire_all()
    return db.session.get(AcmeClientOrder, order_id)


@pytest.mark.usefixtures('_quiet_rows')
class TestConcurrentChallengesOfOneOrder:
    """Two dns-01 threads of one order: each writes its own challenge onto the
    row as it is at that moment, never a copy read before the other's write."""

    X_RECORD = {'domain': DOMAIN, 'record_name': f'_acme-challenge.{DOMAIN}',
                'value': 'vx', 'provider_id': 5}

    def _row(self, records=None):
        row = _two_names(client_jwk_thumbprint='T',
                         dns_records_created=json.dumps(records) if records else None)
        row.set_challenges_dict({CHALL_URL: {'status': 'initiated'},
                                 CHALL_B: {'status': 'initiated'}})
        db.session.commit()
        return row.id

    def test_failure_during_a_sibling_post_fails_the_order(self, app, monkeypatch):
        _provider(monkeypatch, (True, 'ok'))
        with app.app_context():
            order_id = self._row()

            def fail_other():
                other, _calls = _svc(monkeypatch)
                other._fail_challenge_submission(
                    db.session.get(AcmeClientOrder, order_id), CHALL_B, OTHER, None)

            def post(url, payload=None, *_a, **_k):
                assert url == CHALL_URL
                _in_another_thread(app, fail_other)
                return _Resp({'status': 'processing'})

            svc, _calls = _svc(monkeypatch)
            monkeypatch.setattr(svc, '_post_with_account', post)
            svc._run_dns01_automation(CHALL_URL, 'tok.up', DOMAIN, order_id, AUTHZ_URL)

            row = _fresh(order_id)
            assert {url: s['status'] for url, s in row.challenges_dict.items()} == {
                CHALL_URL: 'submitted', CHALL_B: 'failed'}
            assert row.status == 'invalid'
            svc, _calls = _svc(monkeypatch, {ORDER_URL: _Resp(
                {'status': 'pending', 'authorizations': [AUTHZ_URL, AUTHZ_B],
                 'finalize': f'{ORDER_URL}/finalize'})})
            order = svc.get_order(_b64(ORDER_URL), requester_thumbprint='T')
            assert order['status'] == 'invalid' and order['error']['type'].endswith('serverInternal')

    def test_submission_during_a_sibling_post_keeps_its_records(self, app, monkeypatch):
        _provider(monkeypatch, (True, 'ok'))
        submitted = [[self.X_RECORD['record_name'], self.X_RECORD['value']]]
        with app.app_context():
            order_id = self._row(records=[self.X_RECORD])

            def submit_other():
                other, _calls = _svc(monkeypatch)
                other._mark_submitted(db.session.get(AcmeClientOrder, order_id), CHALL_URL, submitted)

            def post(url, payload=None, *_a, **_k):
                assert url == CHALL_B
                _in_another_thread(app, submit_other)
                return _Resp({'type': 'urn:ietf:params:acme:error:rateLimited', 'detail': 'slow'}, 429)

            svc, _calls = _svc(monkeypatch)
            monkeypatch.setattr(svc, '_post_with_account', post)
            svc._run_dns01_automation(CHALL_B, 'tok.up', OTHER, order_id, AUTHZ_B)

            row = _fresh(order_id)
            assert row.challenges_dict[CHALL_URL]['status'] == 'submitted'
            assert row.challenges_dict[CHALL_URL]['records'] == submitted
            assert row.challenges_dict[CHALL_B]['status'] == 'failed'
            by_delay = {(args[3] if len(args) > 3 else 0): args[1] for args in _cleanups()}
            assert [r['value'] for r in by_delay.pop(proxy_mod._SUBMITTED_RECORD_LINGER)] == ['vx']
            assert 'vx' not in [r['value'] for r in by_delay.pop(0, [])]
            assert by_delay == {}

    def test_record_of_a_challenge_posted_during_a_sibling_failure_waits(self, app, monkeypatch):
        """Y fails while X's POST is in flight: X ends submitted, the CA reads its TXT."""
        _provider(monkeypatch, (True, 'ok'))
        with app.app_context():
            order_id = self._row()

            def fail_other():
                other, _calls = _svc(monkeypatch)
                other._fail_challenge_submission(
                    db.session.get(AcmeClientOrder, order_id), CHALL_B, OTHER, None)

            def post(url, payload=None, *_a, **_k):
                _in_another_thread(app, fail_other)
                return _Resp({'status': 'processing'})

            svc, _calls = _svc(monkeypatch)
            monkeypatch.setattr(svc, '_post_with_account', post)
            svc._run_dns01_automation(CHALL_URL, 'tok.up', DOMAIN, order_id, AUTHZ_URL)

            assert _fresh(order_id).challenges_dict[CHALL_URL]['status'] == 'submitted'
            by_delay = {(args[3] if len(args) > 3 else 0): args[1] for args in _cleanups()}
            lingering = by_delay.pop(proxy_mod._SUBMITTED_RECORD_LINGER)
            assert _txt('tok.up') in [r['value'] for r in lingering]
            assert by_delay == {}

    def test_record_written_meanwhile_is_kept(self, app, monkeypatch):
        provider = _provider(monkeypatch, (True, 'ok'))
        other_record = {'domain': OTHER, 'record_name': f'_acme-challenge.{OTHER}',
                        'value': 'vz', 'provider_id': 5}
        with app.app_context():
            order_id = self._row()
            written = []

            def create(*_a, **_k):
                if not written:
                    written.append(True)
                    _in_another_thread(app, lambda: _append_record(order_id, other_record))
                return True, 'ok'

            provider.create_txt_record.side_effect = create
            svc, _calls = _svc(monkeypatch, {CHALL_URL: _Resp({'status': 'processing'})})
            svc._run_dns01_automation(CHALL_URL, 'tok.up', DOMAIN, order_id, AUTHZ_URL)
            values = [r['value'] for r in json.loads(_fresh(order_id).dns_records_created)]
            assert 'vz' in values and _txt('tok.up') in values

    def test_release_takes_the_records_written_meanwhile(self, app, monkeypatch):
        other_record = {'domain': OTHER, 'record_name': f'_acme-challenge.{OTHER}',
                        'value': 'vz', 'provider_id': 5}
        with app.app_context():
            order_id = self._row(records=[self.X_RECORD])
            row = db.session.get(AcmeClientOrder, order_id)
            assert row.dns_records_created
            _in_another_thread(app, lambda: _append_record(order_id, other_record))
            svc, _calls = _svc(monkeypatch)
            svc._release_order_records(row)
            assert sorted(r['value'] for args in _cleanups() for r in args[1]) == ['vx', 'vz']
            listed = json.loads(_fresh(order_id).dns_records_created)
            assert sorted(r['value'] for r in listed if r['release_at']) == ['vx', 'vz']

    def test_abandon_keeps_a_failure_written_meanwhile(self, app, monkeypatch):
        with app.app_context():
            order_id = self._row()
            row = db.session.get(AcmeClientOrder, order_id)
            assert row.challenges_dict

            def fail_other(fresh_row):
                states = fresh_row.challenges_dict
                states[CHALL_B] = {'status': 'failed', 'error': 'x'}
                fresh_row.set_challenges_dict(states)

            _in_another_thread(app, lambda: proxy_mod._update_order_row(
                db.session.get(AcmeClientOrder, order_id), fail_other))
            AcmeProxyService._abandon_challenge(row, CHALL_URL)
            assert {url: s['status'] for url, s in _fresh(order_id).challenges_dict.items()} == {
                CHALL_URL: 'abandoned', CHALL_B: 'failed'}


def _append_record(order_id, record):
    def _add(row):
        row.dns_records_created = json.dumps(json.loads(row.dns_records_created or '[]') + [record])

    proxy_mod._update_order_row(db.session.get(AcmeClientOrder, order_id), _add)


@pytest.mark.usefixtures('_quiet_rows')
class TestAutomationStartedMeanwhile:
    """The flag is set by another worker between the read of the sibling orders and
    the flagging: the second request starts no thread."""

    @pytest.mark.parametrize('entry', ['authz', 'challenge'])
    def test_flag_set_meanwhile_starts_no_thread(self, app, monkeypatch, entry):
        with app.app_context():
            order_id = _order(client_jwk_thumbprint='T').id
            svc, _calls = _svc(monkeypatch, {AUTHZ_URL: _Resp(_authz())})
            original = svc._challenge_automation_started

            def started(chall_url, orders):
                seen = original(chall_url, orders)
                _in_another_thread(app, lambda: AcmeProxyService._mark_initiated(
                    db.session.get(AcmeClientOrder, order_id), CHALL_URL))
                return seen

            monkeypatch.setattr(svc, '_challenge_automation_started', started)
            if entry == 'authz':
                svc.get_authz(_b64(AUTHZ_URL), requester_thumbprint='T')
            else:
                svc.respond_challenge(_b64(CHALL_URL), requester_thumbprint='T')
            assert _automation_orders() and _started_automations() == []
            assert _fresh(order_id).challenges_dict[CHALL_URL]['status'] == 'initiated'


class TestOrderRowUpdate:
    def test_failed_commit_leaves_the_session_usable(self, app):
        with app.app_context():
            row = _order()
            db.session.add(AcmeClientOrder(domains=None, is_proxy_order=True))
            with pytest.raises(Exception):
                proxy_mod._update_order_row(row, lambda _row: None)
            assert AcmeClientOrder.query.filter_by(id=row.id).count() == 1


@pytest.fixture
def _recorded_rows(monkeypatch):
    calls = []
    monkeypatch.setattr(proxy_mod, '_dns_rows_hook', lambda action, *args: calls.append((action, args)))
    monkeypatch.setattr('api.v2.acme_domains.find_provider_for_domain',
                        lambda *_a, **_k: {'provider': object()})
    return calls


@pytest.mark.usefixtures('_quiet_rows')
class TestSiblingOrderOfOneAccount:
    """O1 {a, b} and O2 {a} of one account share the authorization of a: O1 failing
    on b leaves the challenge of a served pending to O2 (RFC 8555 §7.1.6)."""

    def test_challenge_cached_on_the_failed_order_is_served_for_the_live_one(self, app, monkeypatch):
        with app.app_context():
            first = _two_names(client_jwk_thumbprint='T')
            _order(client_jwk_thumbprint='T', order_url=f'{ORDER_URL}b',
                   upstream_order_url=f'{ORDER_URL}b')
            svc, _calls = _svc(monkeypatch, {AUTHZ_URL: _Resp(_authz())})
            svc.get_authz(_b64(AUTHZ_URL), requester_thumbprint='T')
            assert _automation_orders() == [first.id]

            first = _fresh(first.id)
            states = first.challenges_dict
            states[CHALL_B] = {'status': 'failed', 'error': 'x'}
            first.set_challenges_dict(states)
            first.status = 'invalid'
            db.session.commit()

            svc, _calls = _svc(monkeypatch, {AUTHZ_URL: _Resp(_authz())})
            chall, _link = svc.respond_challenge(_b64(CHALL_URL), requester_thumbprint='T')
            assert chall['status'] == 'processing' and 'error' not in chall

    @pytest.mark.parametrize('first_url', [ORDER_URL, f'{ORDER_URL}b'])
    def test_valid_retry_wins_over_the_failed_order(self, app, monkeypatch, first_url):
        with app.app_context():
            _failed_order(order_url=first_url, upstream_order_url=first_url)
            _order(client_jwk_thumbprint='T', status='valid')
            cert_url = f'{UPSTREAM}/acme/cert/dns/1'
            svc, _calls = _svc(monkeypatch, {
                ORDER_URL: _Resp({'status': 'valid', 'authorizations': [AUTHZ_URL],
                                  'finalize': f'{ORDER_URL}/finalize', 'certificate': cert_url}),
                AUTHZ_URL: _Resp(_authz(status='valid', chall_status='valid'))})
            order = svc.get_order(_b64(ORDER_URL), requester_thumbprint='T')
            assert order['status'] == 'valid' and order.get('certificate')
            authz, _ident = svc.get_authz(_b64(AUTHZ_URL), requester_thumbprint='T')
            assert authz['status'] == 'valid'
            assert authz['challenges'][0]['status'] == 'valid'


    @pytest.mark.parametrize('failed_first', [True, False])
    def test_failed_order_wins_over_a_deactivated_one_on_one_order_url(self, app, monkeypatch,
                                                                       failed_first):
        """Both dead: the deactivated row must not serve the valid upstream order."""
        with app.app_context():
            make = [_failed_order, lambda: _order(
                client_jwk_thumbprint='T', status='invalid',
                deactivated_authz_urls=json.dumps([AUTHZ_URL]))]
            for build in (make if failed_first else make[::-1]):
                build()
            svc, _calls = _svc(monkeypatch, {ORDER_URL: _Resp({
                'status': 'valid', 'authorizations': [AUTHZ_URL],
                'finalize': f'{ORDER_URL}/finalize',
                'certificate': f'{UPSTREAM}/acme/cert/dns/1'})})
            order = svc.get_order(_b64(ORDER_URL), requester_thumbprint='T')
            assert order['status'] == 'invalid' and 'certificate' not in order

class TestLocalFailureLeavesSharedRowsOpen:
    """A local failure closes the DNS UPDATE rows of its own order only: the other
    accounts sharing the upstream challenge still validate it."""

    @pytest.mark.parametrize('entry', ['authz', 'challenge'])
    def test_failed_order_read_closes_no_shared_row(self, app, monkeypatch, _recorded_rows, entry):
        with app.app_context():
            _failed_order()
            _order(client_jwk_thumbprint='U', order_url=f'{ORDER_URL}b',
                   upstream_order_url=f'{ORDER_URL}b')
            svc, _calls = _svc(monkeypatch, {AUTHZ_URL: _Resp(_authz()),
                                             ORDER_URL: _Resp({'status': 'pending'})})
            if entry == 'authz':
                served, _ident = svc.get_authz(_b64(AUTHZ_URL), requester_thumbprint='T')
                served = served['challenges'][0]
            else:
                served, _link = svc.respond_challenge(_b64(CHALL_URL), requester_thumbprint='T')
            assert served['status'] == 'invalid'
            assert 'close_for_challenge_urls' not in [action for action, _args in _recorded_rows]

    def test_failed_order_read_still_writes_the_live_sibling_row(self, app, monkeypatch,
                                                                 _recorded_rows):
        """Upstream pending: the row of the live order is written although T's view is invalid."""
        with app.app_context():
            _failed_order()
            live = _order(client_jwk_thumbprint='U', order_url=f'{ORDER_URL}b',
                          upstream_order_url=f'{ORDER_URL}b')
            svc, _calls = _svc(monkeypatch, {AUTHZ_URL: _Resp(_authz())})
            served, _ident = svc.get_authz(_b64(AUTHZ_URL), requester_thumbprint='T')
            assert served['status'] == 'invalid'
            [args] = [args for action, args in _recorded_rows
                      if action == 'persist_expected_values']
            assert [o.id for o in args[0]] == [live.id]

    def test_upstream_failure_still_closes_the_rows(self, app, monkeypatch, _recorded_rows):
        with app.app_context():
            _failed_order()
            svc, _calls = _svc(monkeypatch, {AUTHZ_URL: _Resp(_authz(chall_status='invalid'))})
            svc.respond_challenge(_b64(CHALL_URL), requester_thumbprint='T')
            assert ('close_for_challenge_urls', ([CHALL_URL],)) in _recorded_rows

    def test_already_valid_is_not_logged_for_a_failed_order(self, app, monkeypatch, caplog,
                                                             _recorded_rows):
        import logging
        with app.app_context(), caplog.at_level(logging.INFO, logger=proxy_mod.logger.name):
            _failed_order()
            svc, _calls = _svc(monkeypatch, {
                AUTHZ_URL: _Resp(_authz(status='valid', chall_status='valid'))})
            authz, _ident = svc.get_authz(_b64(AUTHZ_URL), requester_thumbprint='T')
            assert authz['status'] == 'invalid'
            assert not any('passed through without validation' in r.getMessage()
                           for r in caplog.records)


@pytest.mark.usefixtures('_quiet_rows')
class TestRetryWithinTheLinger:
    """A retry on the same authorization publishes the value its failed sibling still
    holds during the delay: not written twice, not deleted under the live order."""

    def _fail_with_linger(self, monkeypatch):
        row = _order(client_jwk_thumbprint='T')
        row.set_challenges_dict({CHALL_URL: {'status': 'initiated'}})
        db.session.commit()
        svc, _calls = _svc(monkeypatch)
        monkeypatch.setattr(svc, '_post_with_account', _Upstream({
            CHALL_URL: requests.exceptions.ReadTimeout('read timed out'),
            AUTHZ_URL: requests.exceptions.ReadTimeout('read timed out')}))
        svc._run_dns01_automation(CHALL_URL, 'tok.up', DOMAIN, row.id, AUTHZ_URL)
        return row.id

    def test_retry_neither_rewrites_nor_loses_the_lingering_value(self, app, monkeypatch):
        from models import DnsProvider
        provider = _provider(monkeypatch, (True, 'ok'))
        deleted = []
        provider.delete_txt_record.side_effect = (
            lambda _zone, name, value: deleted.append(value) or (True, 'ok'))
        monkeypatch.setattr(proxy_mod.time, 'sleep', lambda _seconds: None)
        with app.app_context():
            model = DnsProvider(name='linger-retry', provider_type='manual', credentials='{}')
            db.session.add(model)
            db.session.commit()
            monkeypatch.setattr('api.v2.acme_domains.find_provider_for_domain',
                                lambda *_a, **_k: {'provider': model})
            try:
                failed_id = self._fail_with_linger(monkeypatch)
                [(target, args)] = [(t, a) for t, a in _ThreadRecorder.created
                                    if getattr(t, '__name__', '') == '_bg_cleanup_dns_records']
                assert args[3] == proxy_mod._SUBMITTED_RECORD_LINGER

                # Duplicate refused, as Cloudflare does
                provider.create_txt_record.reset_mock()
                provider.create_txt_record.return_value = (False, 'record already exists')
                retry = _order(client_jwk_thumbprint='T', order_url=f'{ORDER_URL}b',
                               upstream_order_url=f'{ORDER_URL}b')
                svc, _calls = _svc(monkeypatch, {CHALL_URL: _Resp({'status': 'processing'})})
                svc._run_dns01_automation(CHALL_URL, 'tok.up', DOMAIN, retry.id, AUTHZ_URL)
                retry = _fresh(retry.id)
                assert retry.status == 'pending'
                assert retry.challenges_dict[CHALL_URL]['status'] == 'submitted'
                assert _txt('tok.up') in [r['value'] for r in json.loads(retry.dns_records_created)]
                assert provider.create_txt_record.call_count == 0

                target(*args)
                assert deleted == []
                assert not json.loads(_fresh(failed_id).dns_records_created or '[]')
            finally:
                AcmeClientOrder.query.filter_by(is_proxy_order=True).delete()
                db.session.delete(model)
                db.session.commit()

    def test_lingering_value_is_deleted_when_no_order_holds_it(self, app, monkeypatch):
        from models import DnsProvider
        provider = _provider(monkeypatch, (True, 'ok'))
        deleted = []
        provider.delete_txt_record.side_effect = (
            lambda _zone, name, value: deleted.append(value) or (True, 'ok'))
        monkeypatch.setattr(proxy_mod.time, 'sleep', lambda _seconds: None)
        with app.app_context():
            model = DnsProvider(name='linger-alone', provider_type='manual', credentials='{}')
            db.session.add(model)
            db.session.commit()
            monkeypatch.setattr('api.v2.acme_domains.find_provider_for_domain',
                                lambda *_a, **_k: {'provider': model})
            try:
                failed_id = self._fail_with_linger(monkeypatch)
                for target, args in list(_ThreadRecorder.created):
                    target(*args)
                assert _txt('tok.up') in deleted
                assert not json.loads(_fresh(failed_id).dns_records_created or '[]')
            finally:
                AcmeClientOrder.query.filter_by(is_proxy_order=True).delete()
                db.session.delete(model)
                db.session.commit()

    def test_value_whose_deletion_is_long_overdue_is_written_again(self, app, monkeypatch):
        """A restart lost the deferred deletion: past one more delay the value is not trusted."""
        import time
        provider = _provider(monkeypatch, (True, 'ok'))
        name = f'_acme-challenge.{DOMAIN}'
        overdue = {'domain': DOMAIN, 'record_name': name, 'value': _txt('tok.up'), 'provider_id': 5,
                   'release_at': time.time() - proxy_mod._SUBMITTED_RECORD_LINGER - 1}
        with app.app_context():
            _order(status='invalid', dns_records_created=json.dumps([overdue]))
            row = _order(order_url=f'{ORDER_URL}b', upstream_order_url=f'{ORDER_URL}b')
            svc, _calls = _svc(monkeypatch, {CHALL_URL: _Resp({'status': 'processing'})})
            svc._run_dns01_automation(CHALL_URL, 'tok.up', DOMAIN, row.id, AUTHZ_URL)
            provider.create_txt_record.assert_called_once_with(DOMAIN, name, _txt('tok.up'))

    def test_issued_order_still_deletes_a_value_a_sibling_lists(self, app, monkeypatch):
        """Issued, the shared authorization is valid: the sibling no longer needs the value."""
        from flask import current_app
        from models import DnsProvider
        provider = _provider(monkeypatch, (True, 'ok'))
        deleted = []
        provider.delete_txt_record.side_effect = (
            lambda _zone, name, value: deleted.append(value) or (True, 'ok'))
        with app.app_context():
            model = DnsProvider(name='issued-sibling', provider_type='manual', credentials='{}')
            db.session.add(model)
            db.session.commit()
            record = {'domain': DOMAIN, 'record_name': f'_acme-challenge.{DOMAIN}',
                      'value': 'shared', 'provider_id': model.id}
            try:
                issued = _order(status='valid')
                _order(order_url=f'{ORDER_URL}b', upstream_order_url=f'{ORDER_URL}b',
                       dns_records_created=json.dumps([record]))
                svc, _calls = _svc(monkeypatch)
                svc._bg_cleanup_dns_records(current_app._get_current_object(), [record], issued.id)
                assert deleted == ['shared']
            finally:
                AcmeClientOrder.query.filter_by(is_proxy_order=True).delete()
                db.session.delete(model)
                db.session.commit()


class TestAbandonGuard:
    @pytest.mark.parametrize('state', ['submitted', 'failed'])
    def test_only_an_initiated_challenge_is_abandoned(self, app, state):
        with app.app_context():
            row = _order()
            row.set_challenges_dict({CHALL_URL: {'status': state, 'error': 'x'}})
            db.session.commit()
            AcmeProxyService._abandon_challenge(row, CHALL_URL)
            assert _fresh(row.id).challenges_dict[CHALL_URL]['status'] == state
