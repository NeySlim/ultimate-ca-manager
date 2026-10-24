"""Expected TXT values of the DNS UPDATE listener (R1-R7).

Integration tests run through ``AcmeProxyService.get_authz`` and
``get_certificate`` with the upstream stubbed, as the other proxy tests do.
"""
import base64
import hashlib
import json
import secrets
import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError, OperationalError

import services.acme.acme_proxy_service as proxy_mod
from models import (db, AcmeClientAccount, AcmeClientOrder, AcmeDomain,
                    DnsProvider)
from models.acme_dns_update import AcmeProxyDnsChallenge
from services.acme.dns_update import records
from utils.datetime_utils import utc_now

UPSTREAM = 'https://acme-stub.example'
AUTHZ_URL = f'{UPSTREAM}/acme/authz-v3/9001'
CHALL_URL = f'{UPSTREAM}/acme/chall-v3/9001/AbCd'
CERT_URL = f'{UPSTREAM}/acme/cert/dns-rec'
IDENT = 'app.example.com'
RECORD = '_acme-challenge.app.example.com.'
TOKEN_RFC = 'evaGxfADs6pSRb2LAv9IZf17Dt3juxGJ-PCt92wr-oA'
THUMB_RFC = 'NzbLsXh8uDCcd-6MNwXF4W_7noWXFZAfHkxZsRGC9Xs'
TOKEN = 'tok-' + 'a' * 30


def _b64(url):
    return base64.urlsafe_b64encode(url.encode()).rstrip(b'=').decode()


def _value(thumb, token=TOKEN):
    digest = hashlib.sha256(f'{token}.{thumb}'.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b'=').decode()


def _iso(dt):
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


class _FakeResp:
    def __init__(self, payload, status_code=200):
        self.status_code = status_code
        self._payload = payload
        self.headers = {}
        self.text = json.dumps(payload)
        self.content = self.text.encode()

    def json(self):
        return self._payload


class _Recorder:
    """Stands in for threading.Thread: records, never runs."""
    created = []

    def __init__(self, *a, **k):
        _Recorder.created.append(k.get('target') or (a[0] if a else None))
        self.name = ''
        self.daemon = False

    def start(self):
        pass


@pytest.fixture(autouse=True)
def _fresh_cache(monkeypatch):
    monkeypatch.setattr(records, '_cache', records.ActiveRecordCache())


@pytest.fixture
def env(app):
    """Proxy account, ACME Domains entry for example.com, clean tables."""
    with app.app_context():
        floor = db.session.query(db.func.max(AcmeClientOrder.id)).scalar() or 0
        provider = DnsProvider(name=f'rec-{uuid.uuid4().hex[:6]}',
                               provider_type='manual',
                               zones=json.dumps(['example.com']))
        account = AcmeClientAccount(
            directory_url=f'https://rec-{uuid.uuid4().hex}.example/directory',
            label='records', email='ops@example.com')
        db.session.add_all([provider, account])
        db.session.commit()
        db.session.add(AcmeDomain(domain='example.com',
                                  dns_provider_id=provider.id))
        db.session.commit()
        ns = SimpleNamespace(account_id=account.id, provider_id=provider.id)
        yield ns
        db.session.rollback()
        AcmeProxyDnsChallenge.query.delete()
        AcmeClientOrder.query.filter(AcmeClientOrder.id > floor).delete(
            synchronize_session=False)
        AcmeDomain.query.filter_by(domain='example.com').delete()
        DnsProvider.query.filter_by(id=provider.id).delete()
        AcmeClientAccount.query.filter_by(id=account.id).delete()
        db.session.commit()


def _seed_order(env, account_id, thumb, status='pending', **kw):
    order = AcmeClientOrder(
        domains=json.dumps([IDENT]), environment='staging',
        challenge_type='dns-01', status=status, is_proxy_order=True,
        order_url=f'{UPSTREAM}/o/{account_id}',
        upstream_order_url=f'{UPSTREAM}/o/{account_id}',
        upstream_authz_urls=json.dumps([AUTHZ_URL]),
        certificate_url=kw.pop('certificate_url', None),
        account_id=account_id, client_jwk_thumbprint=thumb,
        acme_client_account_id=env.account_id, **kw)
    db.session.add(order)
    db.session.commit()
    return order


def _svc(monkeypatch, authz):
    svc = proxy_mod.AcmeProxyService('https://ucm.example/acme/proxy')
    svc.upstream_directory_url = f'{UPSTREAM}/directory'
    monkeypatch.setattr(svc, '_post_with_account',
                        lambda *_a, **_k: _FakeResp(authz))
    monkeypatch.setattr(svc, '_get_account_thumbprint', lambda: 'upstream-thumb')
    _Recorder.created = []
    monkeypatch.setattr(proxy_mod.threading, 'Thread', _Recorder)
    return svc


def _authz(status='pending', chall_status=None, expires=None, types=('dns-01',)):
    payload = {
        'status': status,
        'identifier': {'type': 'dns', 'value': IDENT},
        'challenges': [
            {'type': t, 'url': CHALL_URL if t == 'dns-01' else f'{CHALL_URL}-{t}',
             'status': chall_status or status, 'token': TOKEN}
            for t in types],
    }
    if expires:
        payload['expires'] = expires
    return payload


def _get_authz(svc, acct='acct-a', thumb='thumb-a'):
    return svc.get_authz(_b64(AUTHZ_URL), requester_account_id=acct,
                         requester_thumbprint=thumb)


def _rows():
    db.session.expire_all()
    return AcmeProxyDnsChallenge.query.order_by(AcmeProxyDnsChallenge.id).all()


def _two_orders(env):
    a = _seed_order(env, 'acct-a', 'thumb-a')
    b = _seed_order(env, 'acct-b', 'thumb-b')
    return a, b


# ---------------------------------------------------------------- R1 / R2

def test_R1_expected_value_matches_independent_computation_pos():
    digest = hashlib.sha256(f'{TOKEN_RFC}.{THUMB_RFC}'.encode()).digest()
    independent = base64.urlsafe_b64encode(digest).rstrip(b'=').decode()
    assert records.expected_value(TOKEN_RFC, THUMB_RFC) == independent
    assert proxy_mod._dns01_txt_value(f'{TOKEN_RFC}.{THUMB_RFC}') == independent


def test_R1_expected_value_alphabet_and_length_neg():
    for _ in range(200):
        value = records.expected_value(secrets.token_urlsafe(32),
                                       secrets.token_urlsafe(32))
        assert len(value) == 43
        assert not set(value) & {'=', '+', '/'}


def test_R2_wildcard_stripped_and_lowercased_pos():
    assert records.record_name_for('*.Example.COM') == '_acme-challenge.example.com.'
    assert records.record_name_for('App.Example.com') == RECORD


def test_R2_wildcard_never_in_name_neg():
    for ident in ('*.example.com', '*.A.B.example.com', '*.*.example.com'[2:]):
        assert '*' not in records.record_name_for(ident)


# --------------------------------------------------------------------- R3

def test_R3_two_orders_get_own_rows_pos(app, env, monkeypatch):
    with app.app_context():
        a, b = _two_orders(env)
        svc = _svc(monkeypatch, _authz())
        _get_authz(svc)
        rows = {r.order_id: r for r in _rows()}
        assert set(rows) == {a.id, b.id}
        assert rows[a.id].txt_value == _value('thumb-a')
        assert rows[b.id].txt_value == _value('thumb-b')
        assert rows[a.id].txt_value != rows[b.id].txt_value
        for order, row in ((a, rows[a.id]), (b, rows[b.id])):
            assert row.zone_name == 'example.com.'
            assert row.record_name == RECORD
            assert row.client_jwk_thumbprint == order.client_jwk_thumbprint
            assert row.account_id == order.account_id
            assert row.acme_client_account_id == env.account_id
            assert row.status == 'pending'
            assert row.upstream_challenge_url == CHALL_URL


def test_R3_second_call_is_idempotent_pos(app, env, monkeypatch):
    with app.app_context():
        _two_orders(env)
        svc = _svc(monkeypatch, _authz())
        _get_authz(svc)
        _get_authz(svc)
        assert len(_rows()) == 2


def test_R3_authz_valid_writes_nothing_neg(app, env, monkeypatch):
    with app.app_context():
        _two_orders(env)
        _get_authz(_svc(monkeypatch, _authz('valid')))
        assert _rows() == []


def test_R3_not_owner_writes_nothing_neg(app, env, monkeypatch):
    with app.app_context():
        _two_orders(env)
        svc = _svc(monkeypatch, _authz())
        with pytest.raises(PermissionError):
            _get_authz(svc, 'acct-intruder', 'thumb-intruder')
        assert _rows() == []


def test_R3_no_dns01_challenge_writes_nothing_neg(app, env, monkeypatch):
    with app.app_context():
        _two_orders(env)
        svc = _svc(monkeypatch, _authz(types=('http-01',)))
        with pytest.raises(proxy_mod.ProxyDns01OnlyError):
            _get_authz(svc)
        assert _rows() == []


def test_R3_no_acme_domain_writes_nothing_neg(app, env, monkeypatch):
    with app.app_context():
        _two_orders(env)
        AcmeDomain.query.filter_by(domain='example.com').delete()
        db.session.commit()
        authz, _ident = _get_authz(_svc(monkeypatch, _authz()))
        assert authz['challenges']
        assert _rows() == []


def test_R3_row_written_when_sibling_started_automation_pos(app, env, monkeypatch):
    with app.app_context():
        a, b = _two_orders(env)
        a.set_challenges_dict({CHALL_URL: {'status': 'initiated'}})
        db.session.commit()
        svc = _svc(monkeypatch, _authz())
        _get_authz(svc, 'acct-b', 'thumb-b')
        assert _Recorder.created == []
        assert len(_rows()) == 2


@pytest.mark.parametrize('chall_status', ['pending', 'processing'])
def test_R9_sibling_gets_row_while_challenge_is_not_final_pos(app, env, monkeypatch,
                                                              chall_status):
    # RFC 8555 section 7.1.6: pending and processing are not final.
    with app.app_context():
        a, b = _two_orders(env)
        a.set_challenges_dict({CHALL_URL: {'status': 'initiated'}})
        db.session.commit()
        svc = _svc(monkeypatch, _authz('pending', chall_status=chall_status))
        _get_authz(svc, 'acct-b', 'thumb-b')
        assert _Recorder.created == []  # the automation of the sibling runs already
        rows = {r.order_id: r for r in _rows()}
        assert set(rows) == {a.id, b.id}
        assert rows[b.id].txt_value == _value('thumb-b')
        assert rows[b.id].status == 'pending'


def test_R9_processing_challenge_does_not_start_automation_neg(app, env, monkeypatch):
    with app.app_context():
        _two_orders(env)
        _get_authz(_svc(monkeypatch, _authz('pending', chall_status='processing')))
        assert _Recorder.created == []
        assert len(_rows()) == 2


@pytest.mark.parametrize('authz_status,chall_status', [
    ('pending', 'valid'), ('valid', 'valid'), ('valid', 'processing'),
    ('valid', 'pending'), ('invalid', 'processing'), ('invalid', 'pending')])
def test_R9_final_authz_or_valid_challenge_writes_nothing_neg(
        app, env, monkeypatch, authz_status, chall_status):
    with app.app_context():
        _two_orders(env)
        _get_authz(_svc(monkeypatch, _authz(authz_status, chall_status=chall_status)))
        assert _rows() == []


def test_R9_invalid_challenge_closes_rows_and_writes_none_neg(app, env, monkeypatch):
    with app.app_context():
        a, b = _two_orders(env)
        _get_authz(_svc(monkeypatch, _authz('pending', chall_status='invalid')))
        assert _rows() == []  # nothing written for the orders without rows
        _seed_rows(a, b)
        _get_authz(_svc(monkeypatch, _authz('pending', chall_status='invalid')))
        assert [r.status for r in _rows()] == ['closed', 'closed']
        assert len(_rows()) == 2  # no new row next to the closed ones


# --------------------------------------------------------------------- R4

def _run_get_certificate(monkeypatch, acct='acct-a', thumb='thumb-a'):
    from services.cert_service import CertificateService
    from tests.test_acme_proxy_issue_fixes import _self_signed_pem

    pem = _self_signed_pem()
    svc = proxy_mod.AcmeProxyService('https://ucm.example/acme/proxy')
    svc.upstream_directory_url = f'{UPSTREAM}/directory'
    svc.account = SimpleNamespace(preferred_chain='')
    resp = SimpleNamespace(
        status_code=200, content=pem.encode(),
        headers={'Content-Type': 'application/pem-certificate-chain'})
    monkeypatch.setattr(svc, '_post_with_account', lambda *_a, **_k: resp)
    monkeypatch.setattr(CertificateService, 'import_certificate',
                        staticmethod(lambda **_kw: SimpleNamespace(id=4243)))
    svc.get_certificate(_b64(CERT_URL), requester_account_id=acct,
                        requester_thumbprint=thumb)


def _seed_rows(a, b):
    for order, thumb in ((a, 'thumb-a'), (b, 'thumb-b')):
        db.session.add(AcmeProxyDnsChallenge(
            order_id=order.id, client_jwk_thumbprint=thumb, identifier=IDENT,
            record_name=RECORD, txt_value=_value(thumb), zone_name='example.com.',
            upstream_challenge_url=CHALL_URL,
            expires_at=utc_now() + timedelta(hours=1)))
    db.session.commit()


def test_R4_get_certificate_closes_rows_of_that_order_pos(app, env, monkeypatch):
    with app.app_context():
        a = _seed_order(env, 'acct-a', 'thumb-a', certificate_url=CERT_URL)
        b = _seed_order(env, 'acct-b', 'thumb-b')
        _seed_rows(a, b)
        _run_get_certificate(monkeypatch)
        assert db.session.get(AcmeClientOrder, a.id).status == 'valid'
        status = {r.order_id: r.status for r in _rows()}
        assert status[a.id] == 'closed'
        assert status[b.id] == 'pending'  # neg: other order untouched


def test_R4_get_certificate_by_other_account_closes_nothing_neg(app, env, monkeypatch):
    with app.app_context():
        a = _seed_order(env, 'acct-a', 'thumb-a', certificate_url=CERT_URL)
        b = _seed_order(env, 'acct-b', 'thumb-b')
        _seed_rows(a, b)
        with pytest.raises(PermissionError):
            _run_get_certificate(monkeypatch, 'acct-x', 'thumb-x')
        assert {r.status for r in _rows()} == {'pending'}


def test_R4_authz_invalid_closes_rows_of_its_challenge_urls_pos(app, env, monkeypatch):
    with app.app_context():
        a, b = _two_orders(env)
        _seed_rows(a, b)
        other = AcmeProxyDnsChallenge(
            order_id=b.id, client_jwk_thumbprint='thumb-b', identifier=IDENT,
            record_name=RECORD, txt_value='other-value', zone_name='example.com.',
            upstream_challenge_url=f'{UPSTREAM}/other-chall',
            expires_at=utc_now() + timedelta(hours=1))
        db.session.add(other)
        db.session.commit()
        _get_authz(_svc(monkeypatch, _authz('invalid')))
        by_url = {}
        for r in _rows():
            by_url.setdefault(r.upstream_challenge_url, set()).add(r.status)
        assert by_url[CHALL_URL] == {'closed'}
        assert by_url[f'{UPSTREAM}/other-chall'] == {'pending'}  # neg


def test_R4_failed_challenge_closes_rows_pos(app, env, monkeypatch):
    with app.app_context():
        a, b = _two_orders(env)
        _seed_rows(a, b)
        _get_authz(_svc(monkeypatch, _authz('pending', chall_status='invalid')))
        assert {r.status for r in _rows()} == {'closed'}


@pytest.mark.parametrize('authz_status,chall_status', [
    ('valid', 'valid'), ('pending', 'processing'), ('pending', 'valid')])
def test_R4_processing_or_valid_keeps_rows_neg(app, env, monkeypatch,
                                               authz_status, chall_status):
    # A client that fetched the pending authorization may still send its
    # update after UCM's own automation moved the challenge on (race).
    with app.app_context():
        a, b = _two_orders(env)
        _seed_rows(a, b)
        _get_authz(_svc(monkeypatch, _authz(authz_status, chall_status=chall_status)))
        assert {r.status for r in _rows()} == {'pending'}


@pytest.mark.parametrize('chall_status,expected', [
    ('invalid', 'closed'),      # pos: failed final state closes the rows
    ('valid', 'pending'),       # neg: success is closed by get_certificate
    ('processing', 'pending'),  # neg: still in flight
])
def test_R4_respond_challenge_closes_only_failed_rows(app, env, monkeypatch,
                                                      chall_status, expected):
    with app.app_context():
        a, b = _two_orders(env)
        _seed_rows(a, b)
        svc = proxy_mod.AcmeProxyService('https://ucm.example/acme/proxy')
        svc.upstream_directory_url = f'{UPSTREAM}/directory'
        chall = {'type': 'dns-01', 'url': CHALL_URL, 'status': chall_status,
                 'token': TOKEN}
        resp = _FakeResp(chall)
        resp.headers = {'Link': f'<{AUTHZ_URL}>;rel="up"'}
        monkeypatch.setattr(svc, '_post_with_account', lambda *_a, **_k: resp)
        svc.respond_challenge(_b64(CHALL_URL), requester_account_id='acct-a',
                              requester_thumbprint='thumb-a')
        assert {r.status for r in _rows()} == {expected}


def test_R4_expires_capped_to_24h_pos(app, env, monkeypatch):
    with app.app_context():
        _two_orders(env)
        now = utc_now()
        _get_authz(_svc(monkeypatch, _authz(expires=_iso(now + timedelta(days=7)))))
        for r in _rows():
            assert abs((r.expires_at - (now + records.ACTIVE_MAX_AGE))
                       .total_seconds()) < 60


def test_R4_expires_below_cap_kept_neg(app, env, monkeypatch):
    with app.app_context():
        _two_orders(env)
        now = utc_now()
        _get_authz(_svc(monkeypatch, _authz(expires=_iso(now + timedelta(hours=1)))))
        for r in _rows():
            assert abs((r.expires_at - (now + timedelta(hours=1)))
                       .total_seconds()) < 60


def test_R4_unparsable_or_missing_expires_uses_cap_pos(app, env, monkeypatch):
    with app.app_context():
        _two_orders(env)
        now = utc_now()
        _get_authz(_svc(monkeypatch, _authz(expires='not-a-date')))
        for r in _rows():
            assert abs((r.expires_at - (now + records.ACTIVE_MAX_AGE))
                       .total_seconds()) < 60


def test_R4_old_rows_purged_pos(app, env, monkeypatch):
    with app.app_context():
        a, b = _two_orders(env)
        db.session.add(AcmeProxyDnsChallenge(
            order_id=a.id, client_jwk_thumbprint='x', identifier=IDENT,
            record_name=RECORD, txt_value='old', zone_name='example.com.',
            expires_at=utc_now() - records.PURGE_AFTER - timedelta(hours=1)))
        db.session.add(AcmeProxyDnsChallenge(
            order_id=a.id, client_jwk_thumbprint='x', identifier=IDENT,
            record_name=RECORD, txt_value='recent', zone_name='example.com.',
            expires_at=utc_now() - timedelta(days=1)))
        db.session.commit()
        _get_authz(_svc(monkeypatch, _authz()))
        values = {r.txt_value for r in _rows()}
        assert 'old' not in values
        assert 'recent' in values  # neg: not yet past the purge age


# --------------------------------------------------------------------- R6

def _initiated(order_id):
    db.session.expire_all()
    order = db.session.get(AcmeClientOrder, order_id)
    return order.challenges_dict.get(CHALL_URL, {}).get('status')


def test_R6_preexisting_duplicate_does_not_break_get_authz_pos(app, env, monkeypatch):
    with app.app_context():
        a, b = _two_orders(env)
        db.session.add(AcmeProxyDnsChallenge(
            order_id=a.id, client_jwk_thumbprint='thumb-a', identifier=IDENT,
            record_name=RECORD, txt_value=_value('thumb-a'),
            zone_name='example.com.',
            expires_at=utc_now() + timedelta(hours=1)))
        db.session.commit()
        authz, ident = _get_authz(_svc(monkeypatch, _authz()))
        assert ident['value'] == IDENT and authz['challenges']
        assert _initiated(a.id) == 'initiated'
        assert len(_rows()) == 2  # only the missing row was added
        assert len(_Recorder.created) == 1


@pytest.mark.parametrize('error', [
    IntegrityError('INSERT', {}, Exception('dup')),
    RuntimeError('boom'),
])
def test_R6_flush_error_in_savepoint_keeps_get_authz_neg(app, env, monkeypatch, error):
    with app.app_context():
        a, b = _two_orders(env)
        svc = _svc(monkeypatch, _authz())
        real_flush = db.session.flush
        calls = []

        def _flush_once(*args, **kwargs):
            if not calls:
                calls.append(1)
                raise error
            return real_flush(*args, **kwargs)

        monkeypatch.setattr(db.session, 'flush', _flush_once)
        authz, ident = _get_authz(svc)
        assert calls == [1]
        assert ident['value'] == IDENT and authz['challenges']
        # The savepoint of the failed row is rolled back; the sibling row is stored.
        assert [r.order_id for r in _rows()] == [b.id]
        assert _initiated(a.id) == 'initiated'
        assert len(_Recorder.created) == 1


def _conflict_on(monkeypatch, order_ids):
    """Raise IntegrityError on a flush that holds a new row of one of the orders."""
    real_flush = db.session.flush

    def _flush(*args, **kwargs):
        if any(isinstance(o, AcmeProxyDnsChallenge) and o.order_id in order_ids
               for o in db.session.new):
            raise IntegrityError('INSERT', {}, Exception('dup'))
        return real_flush(*args, **kwargs)

    monkeypatch.setattr(db.session, 'flush', _flush)


def _persist(orders):
    return records.persist_expected_values(
        orders, IDENT, TOKEN, CHALL_URL, None, utc_now())


def test_A4_conflict_on_one_row_keeps_the_other_rows_pos(app, env, monkeypatch):
    with app.app_context():
        a, b = _two_orders(env)
        _conflict_on(monkeypatch, {a.id})
        assert _persist([a, b]) == 1
        assert [r.order_id for r in _rows()] == [b.id]


def test_A4_single_conflicting_row_gives_zero_and_get_authz_goes_on_neg(
        app, env, monkeypatch, caplog):
    with app.app_context():
        a = _seed_order(env, 'acct-a', 'thumb-a')
        _conflict_on(monkeypatch, {a.id})
        assert _persist([a]) == 0
        assert _rows() == []
        assert _value('thumb-a') not in caplog.text  # logged without values
        authz, ident = _get_authz(_svc(monkeypatch, _authz()))
        assert ident['value'] == IDENT and authz['challenges']
        assert _initiated(a.id) == 'initiated'
        assert _rows() == []


def test_A4_cache_not_invalidated_when_nothing_inserted_pos(app, env, monkeypatch):
    with app.app_context():
        a, b = _two_orders(env)
        assert _persist([a, b]) == 2
        calls = []
        monkeypatch.setattr(records, 'invalidate_cache', lambda: calls.append(1))
        assert _persist([a, b]) == 0  # both rows exist already
        assert calls == []
        assert _persist([]) == 0 and calls == []


def test_A4_cache_invalidated_once_when_rows_inserted_neg(app, env, monkeypatch):
    with app.app_context():
        a, b = _two_orders(env)
        calls = []
        monkeypatch.setattr(records, 'invalidate_cache', lambda: calls.append(1))
        assert _persist([a, b]) == 2
        assert calls == [1]


def test_R6_hook_exception_is_swallowed_neg(app, env, monkeypatch):
    with app.app_context():
        a, _b = _two_orders(env)

        def _boom(*_a, **_k):
            raise RuntimeError('records down')

        monkeypatch.setattr(records, 'persist_expected_values', _boom)
        monkeypatch.setattr(records, 'close_for_challenge_urls', _boom)
        authz, _ident = _get_authz(_svc(monkeypatch, _authz()))
        assert authz['challenges']
        assert _initiated(a.id) == 'initiated'
        _get_authz(_svc(monkeypatch, _authz('valid')))


# --------------------------------------------------------------------- R7

def test_R7_order_without_thumbprint_gets_no_row_pos(app, env, monkeypatch):
    with app.app_context():
        a = _seed_order(env, 'acct-a', 'thumb-a')
        _seed_order(env, 'acct-b', None)  # sibling without a thumbprint
        _get_authz(_svc(monkeypatch, _authz()))
        assert [r.order_id for r in _rows()] == [a.id]


def test_R7_sibling_with_thumbprint_gets_row_neg(app, env, monkeypatch):
    with app.app_context():
        a = _seed_order(env, 'acct-a', 'thumb-a')
        b = _seed_order(env, 'acct-b', 'thumb-b')
        _get_authz(_svc(monkeypatch, _authz()))
        assert {r.order_id for r in _rows()} == {a.id, b.id}


# ------------------------------------------------------------------ cache

def _direct_row(order, value='v1', status='pending', expires=None, name=RECORD):
    row = AcmeProxyDnsChallenge(
        order_id=order.id, client_jwk_thumbprint='t', identifier=IDENT,
        record_name=name, txt_value=value, zone_name='example.com.',
        status=status, expires_at=expires or utc_now() + timedelta(hours=1),
        acme_client_account_id=env_account(order), account_id=order.account_id)
    db.session.add(row)
    db.session.commit()
    return row


def env_account(order):
    return order.acme_client_account_id


def test_cache_new_row_visible_after_invalidate_pos(app, env, monkeypatch):
    with app.app_context():
        a, _b = _two_orders(env)
        assert records.get_active_snapshot().by_name == {}
        _direct_row(a)
        assert records.get_active_snapshot().by_name == {}  # warm, no reload
        records.invalidate_cache()
        snap = records.get_active_snapshot()
        assert [r.txt_value for r in snap.by_name[RECORD]] == ['v1']
        assert snap.zones == frozenset({'example.com.'})
        rec = snap.by_name[RECORD][0]
        assert rec.order_id == a.id and rec.account_id == 'acct-a'
        assert rec.acme_client_account_id == env.account_id


def test_cache_new_row_visible_after_max_age_pos(app, env, monkeypatch):
    with app.app_context():
        a, _b = _two_orders(env)
        clock = [1000.0]
        monkeypatch.setattr(records, '_monotonic', lambda: clock[0])
        records.get_active_snapshot()
        _direct_row(a)
        clock[0] += records.CACHE_MAX_AGE_S - 0.5
        assert records.get_active_snapshot().by_name == {}  # neg: still fresh
        clock[0] += 1
        assert RECORD in records.get_active_snapshot().by_name


def test_cache_persist_invalidates_pos(app, env, monkeypatch):
    with app.app_context():
        _two_orders(env)
        assert records.get_active_snapshot().by_name == {}
        _get_authz(_svc(monkeypatch, _authz()))
        assert len(records.get_active_snapshot().by_name[RECORD]) == 2
        _get_authz(_svc(monkeypatch, _authz('invalid')))
        assert records.get_active_snapshot().by_name == {}


def test_cache_excludes_inactive_rows_neg(app, env, monkeypatch):
    with app.app_context():
        a, b = _two_orders(env)
        done = _seed_order(env, 'acct-c', 'thumb-c', status='valid')
        _direct_row(a, 'closed', status='closed')
        _direct_row(a, 'expired', expires=utc_now() - timedelta(seconds=1))
        _direct_row(done, 'order-valid')
        _direct_row(b, 'active')
        records.invalidate_cache()
        snap = records.get_active_snapshot()
        assert [r.txt_value for r in snap.by_name[RECORD]] == ['active']


def test_R8_closed_valid_order_and_recent_expiry_are_soa_rows_only_pos(app, env, monkeypatch):
    with app.app_context():
        a, _b = _two_orders(env)
        done = _seed_order(env, 'acct-c', 'thumb-c', status='valid')
        _direct_row(a, 'closed', status='closed')
        _direct_row(done, 'order-valid')
        _direct_row(a, 'expired-23h', expires=utc_now() - timedelta(hours=23))
        _direct_row(a, 'expired-1s', expires=utc_now() - timedelta(seconds=1))
        records.invalidate_cache()
        snap = records.get_active_snapshot()
        assert records.SOA_GRACE == timedelta(hours=24)
        assert sorted(r.txt_value for r in snap.soa_rows) == [
            'closed', 'expired-1s', 'expired-23h', 'order-valid']
        assert snap.zones == frozenset({'example.com.'})
        assert snap.by_name == {}  # none of them is active: adds never use them


def test_R8_active_row_is_in_both_views_pos(app, env, monkeypatch):
    with app.app_context():
        a, _b = _two_orders(env)
        _direct_row(a, 'active')
        _direct_row(a, 'closed', status='closed')
        records.invalidate_cache()
        snap = records.get_active_snapshot()
        assert [r.txt_value for r in snap.by_name[RECORD]] == ['active']
        assert sorted(r.txt_value for r in snap.soa_rows) == ['active', 'closed']


def test_R8_row_past_the_grace_is_in_neither_view_neg(app, env, monkeypatch):
    with app.app_context():
        a, _b = _two_orders(env)
        _direct_row(a, 'old-closed', status='closed',
                    expires=utc_now() - timedelta(hours=25))
        _direct_row(a, 'old-pending', expires=utc_now() - timedelta(hours=25))
        records.invalidate_cache()
        snap = records.get_active_snapshot()
        assert snap.soa_rows == () and snap.zones == frozenset()
        assert snap.by_name == {}


def test_R8_empty_snapshot_has_no_soa_rows_neg():
    snap = records._EMPTY_SNAPSHOT
    assert snap.soa_rows == () and snap.zones == frozenset() and snap.by_name == {}


def test_cache_warm_snapshot_runs_no_sql_pos(app, env, monkeypatch):
    with app.app_context():
        a, _b = _two_orders(env)
        _direct_row(a)
        records.get_active_snapshot()
        statements = []

        def _count(conn, cursor, statement, *_a):
            statements.append(statement)

        event.listen(db.engine, 'before_cursor_execute', _count)
        try:
            for _ in range(5):
                records.get_active_snapshot()
            assert statements == []
            records.invalidate_cache()  # neg: a cold snapshot does query
            records.get_active_snapshot()
            assert len(statements) == 1
        finally:
            event.remove(db.engine, 'before_cursor_execute', _count)


def test_cache_reload_error_keeps_previous_snapshot_neg(app, env, monkeypatch):
    with app.app_context():
        a, _b = _two_orders(env)
        _direct_row(a)
        before = records.get_active_snapshot()
        assert RECORD in before.by_name

        def _boom(*_a, **_k):
            raise OperationalError('SELECT', {}, Exception('db gone'))

        monkeypatch.setattr(db.session, 'query', _boom)
        records.invalidate_cache()
        after = records.get_active_snapshot()
        assert after is before
        monkeypatch.undo()


# ---------------------------------------------------------------- retry backoff (C3)

def _failing_cache(monkeypatch, fail=True):
    clock = [1000.0]
    monkeypatch.setattr(records, '_monotonic', lambda: clock[0])
    cache = records.ActiveRecordCache()
    calls = []
    state = {'fail': fail}

    def _load(now):
        calls.append(1)
        if state['fail']:
            raise OperationalError('SELECT', {}, Exception('db gone'))
        return records.ActiveSnapshot({}, frozenset(), ())

    monkeypatch.setattr(cache, '_load', _load)
    return cache, clock, calls, state


def test_cache_failed_reload_is_not_retried_within_2s_pos(app, monkeypatch, caplog):
    with app.app_context():
        cache, clock, calls, _state = _failing_cache(monkeypatch)
        first = cache.snapshot()
        assert first is records._EMPTY_SNAPSHOT and calls == [1]
        for _ in range(5):
            clock[0] += 0.3
            assert cache.snapshot() is first
        assert calls == [1]
        assert caplog.text.count('Active rows not reloaded') == 1


def test_cache_failed_reload_is_retried_after_2s_neg(app, monkeypatch, caplog):
    with app.app_context():
        cache, clock, calls, state = _failing_cache(monkeypatch)
        cache.snapshot()
        clock[0] += records._RETRY_S + 0.1
        cache.snapshot()
        assert calls == [1, 1]
        assert caplog.text.count('Active rows not reloaded') == 2
        state['fail'] = False
        clock[0] += records._RETRY_S + 0.1
        cache.snapshot()
        assert len(calls) == 3
        for _ in range(3):  # loaded: fresh, no more loads
            cache.snapshot()
        assert len(calls) == 3


def test_cache_failed_reload_keeps_previous_snapshot_during_backoff_pos(app, monkeypatch):
    with app.app_context():
        cache, clock, calls, state = _failing_cache(monkeypatch, fail=False)
        loaded = cache.snapshot()
        state['fail'] = True
        clock[0] += records.CACHE_MAX_AGE_S + 1
        assert cache.snapshot() is loaded
        assert cache.snapshot() is loaded
        assert len(calls) == 2


def test_cache_invalidate_after_failure_retries_at_once_neg(app, monkeypatch):
    with app.app_context():
        cache, clock, calls, _state = _failing_cache(monkeypatch)
        cache.snapshot()
        cache.snapshot()
        assert calls == [1]
        cache.invalidate()
        cache.snapshot()
        assert calls == [1, 1]


# ---------------------------------------------------------------- no write work when nothing is new (C4)

def _count_statements():
    statements = []

    def _count(conn, cursor, statement, *_a):
        statements.append(statement.lstrip().split(None, 1)[0].upper())

    event.listen(db.engine, 'before_cursor_execute', _count)
    return statements, lambda: event.remove(db.engine, 'before_cursor_execute', _count)


def test_R3_nothing_new_does_no_zone_lookup_purge_or_commit_pos(app, env, monkeypatch):
    with app.app_context():
        a, b = _two_orders(env)
        assert _persist([a, b]) == 2
        zone_calls, commits, invalidations = [], [], []
        real_zone_for, real_commit = records.zone_for, records._commit
        monkeypatch.setattr(records, 'zone_for',
                            lambda i: zone_calls.append(i) or real_zone_for(i))
        monkeypatch.setattr(records, '_commit', lambda: commits.append(1) or real_commit())
        monkeypatch.setattr(records, 'invalidate_cache', lambda: invalidations.append(1))
        statements, stop = _count_statements()
        try:
            assert _persist([a, b]) == 0
        finally:
            stop()
        assert zone_calls == [] and commits == [] and invalidations == []
        assert 'DELETE' not in statements and 'COMMIT' not in statements
        assert 'INSERT' not in statements
        assert len(_rows()) == 2


def test_R3_one_new_row_does_zone_lookup_insert_and_commit_neg(app, env, monkeypatch):
    with app.app_context():
        a, b = _two_orders(env)
        assert _persist([a]) == 1
        zone_calls, commits, invalidations = [], [], []
        real_zone_for, real_commit = records.zone_for, records._commit
        monkeypatch.setattr(records, 'zone_for',
                            lambda i: zone_calls.append(i) or real_zone_for(i))
        monkeypatch.setattr(records, '_commit', lambda: commits.append(1) or real_commit())
        monkeypatch.setattr(records, 'invalidate_cache', lambda: invalidations.append(1))
        statements, stop = _count_statements()
        try:
            assert _persist([a, b]) == 1
        finally:
            stop()
        assert zone_calls == [IDENT] and commits == [1] and invalidations == [1]
        assert 'INSERT' in statements and 'DELETE' in statements
        assert {r.order_id for r in _rows()} == {a.id, b.id}


def test_R3_new_row_without_zone_writes_nothing_neg(app, env, monkeypatch):
    with app.app_context():
        a, _b = _two_orders(env)
        monkeypatch.setattr(records, 'zone_for', lambda i: None)
        commits = []
        monkeypatch.setattr(records, '_commit', lambda: commits.append(1) or True)
        assert _persist([a]) == 0
        assert commits == [] and _rows() == []
