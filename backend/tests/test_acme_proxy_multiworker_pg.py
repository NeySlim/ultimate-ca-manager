"""Two workers of the ACME proxy (two nodes) on one database.

Worker A serves the authorizations of an order; worker B, which shares no process
memory with it, answers both challenges of that order at once. B finds each
challenge's order and authorization in the database, and both challenges end up
recorded on the order row.
"""
import json
import os
import threading
import uuid
from types import SimpleNamespace

import pytest

import services.acme.acme_proxy_service as proxy_mod
from models import AcmeClientOrder, db
from services.acme.acme_proxy_service import AcmeProxyService
from tests.test_acme_proxy_resolution import _Resp, _Upstream, _b64, _order

_PG_URL = os.environ.get('UCM_TEST_PG_URL')
UPSTREAM = 'https://ca-c1.example'
DIRECTORY_URL = f'{UPSTREAM}/directory'
# Challenges not nested under their authorization (as Pebble names them)
AUTHZ = {name: f'{UPSTREAM}/authZ/{name}' for name in ('a', 'b')}
CHALL = {name: f'{UPSTREAM}/chalZ/{name}' for name in ('a', 'b')}
DOMAIN = {name: f'{name}.multiworker.example' for name in ('a', 'b')}
ACCOUNT = 'c1-multiworker'
_Thread = threading.Thread


def _authz(name):
    return _Resp({'status': 'pending', 'identifier': {'type': 'dns', 'value': DOMAIN[name]},
                  'challenges': [{'type': 'dns-01', 'url': CHALL[name], 'status': 'pending',
                                  'token': f'tok-{name}'}]})


def _worker():
    """A service instance whose upstream answers only this order's two authorizations."""
    svc = AcmeProxyService('https://ucm.example/acme/proxy')
    svc.upstream_directory_url = DIRECTORY_URL
    svc.account = SimpleNamespace(id=None, preferred_chain='')
    svc._post_with_account = _Upstream({AUTHZ[n]: (lambda n=n: _authz(n)) for n in AUTHZ})
    svc._get_account_thumbprint = lambda: 'upstream-thumb'
    return svc


def _forget_process_memory():
    """What another node holds: none of this process's caches."""
    for value in vars(proxy_mod).values():
        if isinstance(value, proxy_mod._TtlCache):
            value.clear()


def _scenario(app, monkeypatch):
    started = []

    class _Recorder:
        def __init__(self, target=None, args=(), **_kw):
            started.append(args)
            self.name, self.daemon = '', False

        def start(self):
            pass

    with app.app_context():
        target = _order(account_id=ACCOUNT, domains=json.dumps(list(DOMAIN.values())),
                        upstream_authz_urls=json.dumps(list(AUTHZ.values()))).id
        # Newer orders of the same requester: a blind scan would read their authorizations first
        for n in range(proxy_mod._CHALLENGE_SCAN_LIMIT + 1):
            url = f'{UPSTREAM}/order/decoy-{n}'
            _order(account_id=ACCOUNT, order_url=url, upstream_order_url=url,
                   upstream_authz_urls=json.dumps([f'{UPSTREAM}/authZ/decoy-{n}']))
        db.session.remove()

    monkeypatch.setattr('api.v2.acme_domains.find_provider_for_domain', lambda *_a, **_k: None)
    with app.app_context():
        node_a = _worker()
        for name in AUTHZ:
            node_a.get_authz(_b64(AUTHZ[name]), requester_account_id=ACCOUNT)
        db.session.remove()

    _forget_process_memory()
    monkeypatch.setattr('api.v2.acme_domains.find_provider_for_domain',
                        lambda *_a, **_k: {'provider': object()})
    monkeypatch.setattr(threading, 'Thread', _Recorder)
    results, both = {}, threading.Barrier(2, timeout=10)

    def respond(name):
        try:
            with app.app_context():
                node_b = _worker()
                both.wait()
                data, _link = node_b.respond_challenge(_b64(CHALL[name]),
                                                       requester_account_id=ACCOUNT)
                results[name] = (data['status'], node_b._post_with_account.calls)
                db.session.remove()
        except Exception as exc:  # noqa: BLE001
            results[name] = repr(exc)

    workers = [_Thread(target=respond, args=(name,)) for name in AUTHZ]
    for w in workers:
        w.start()
    for w in workers:
        w.join(60)

    assert results == {n: ('processing', [AUTHZ[n]]) for n in AUTHZ}, results
    assert sorted((args[1], args[4]) for args in started) == \
        [(CHALL[n], target) for n in sorted(AUTHZ)]
    with app.app_context():
        states = db.session.get(AcmeClientOrder, target).challenges_dict
        db.session.remove()
    assert {url: state['status'] for url, state in states.items()} == \
        {CHALL[n]: 'initiated' for n in AUTHZ}


def test_two_workers_on_sqlite(app, monkeypatch, tmp_path):
    from tests.test_backup_cross_installation import _bound_to

    with _bound_to(app, f"sqlite:///{tmp_path / 'proxy.db'}"):
        _scenario(app, monkeypatch)


@pytest.mark.postgres
@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
def test_two_workers_on_postgresql(app, monkeypatch):
    from tests.test_backup_cross_installation import _bound_to
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own

    with _a_schema_of_our_own(f'proxy_workers_{uuid.uuid4().hex[:6]}') as url, \
            _bound_to(app, url, is_postgresql=True):
        _scenario(app, monkeypatch)
