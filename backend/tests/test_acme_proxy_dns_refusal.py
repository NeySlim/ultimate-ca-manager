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

    @pytest.mark.parametrize('answer', [
        _Resp(BAD_NONCE, 400, {'Replay-Nonce': 'n'}),
        _Resp({'type': 'urn:ietf:params:acme:error:serverInternal', 'detail': 'boom'}, 500),
        ConnectionError('upstream unreachable'),
    ])
    def test_failed_post_fails_the_order_and_releases_its_records(self, app, monkeypatch,
                                                                  answer):
        _provider(monkeypatch, (True, 'ok'))
        with app.app_context():
            row = _order(client_jwk_thumbprint='T')
            row.set_challenges_dict({CHALL_URL: {'status': 'initiated'}})
            db.session.commit()
            svc, _calls = _svc(monkeypatch)
            post = _FailingPost(answer)
            monkeypatch.setattr(svc, '_post_with_account', post)
            svc._run_dns01_automation(CHALL_URL, 'tok.up', DOMAIN, row.id, AUTHZ_URL)

            assert post.calls == [(CHALL_URL, {})]
            db.session.refresh(row)
            assert row.status == 'invalid'
            assert row.challenges_dict[CHALL_URL]['status'] == 'failed'
            assert row.error_message
            assert row.dns_records_created is None
            [(_app, released, order_id)] = _cleanups()
            assert order_id == row.id
            assert {r['record_name'] for r in released} == {f'_acme-challenge.{DOMAIN}'}

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
        assert len(sent) == 1 + proxy_mod._BAD_NONCE_RETRIES

    def test_other_400_is_not_retried(self, monkeypatch):
        answers = [_Resp({'type': 'urn:ietf:params:acme:error:malformed'}, 400,
                         {'Replay-Nonce': 'n1'})]
        svc, sent = self._svc(monkeypatch, answers)
        assert svc._post_jws(CHALL_URL, {}, kid='k').status_code == 400
        assert sent == ['n0']
