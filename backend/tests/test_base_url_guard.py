"""
Base URL guardrails (#303): reachability probe on PATCH (with force
override), canonical-redirect skip when the host stopped resolving, and the
UCM_DISABLE_CANONICAL_REDIRECT escape hatch.
"""
import socket

import pytest

import utils.public_endpoints as pe
from utils.public_endpoints import admin_host_resolves, probe_admin_base_url


class TestProbe:
    def test_unresolvable_host(self, monkeypatch):
        def fail(*_a, **_k):
            raise socket.gaierror('nope')
        monkeypatch.setattr(socket, 'getaddrinfo', fail)
        err = probe_admin_base_url('https://dead.invalid:8443')
        assert err and 'resolve' in err

    def test_reachable_host(self, monkeypatch):
        class _Sock:
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
            def settimeout(self, _t):
                pass
            def connect(self, _addr):
                return None
        monkeypatch.setattr(socket, 'getaddrinfo',
                            lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM,
                                             6, '', ('192.0.2.1', 8443))])
        monkeypatch.setattr(socket, 'socket', lambda *a, **k: _Sock())
        assert probe_admin_base_url('https://ok.example:8443') is None


class TestResolveCache:
    def test_cache_and_negative(self, monkeypatch):
        pe._RESOLVE_CACHE.clear()
        calls = {'n': 0}
        def fail(*_a, **_k):
            calls['n'] += 1
            raise socket.gaierror('nope')
        monkeypatch.setattr(socket, 'getaddrinfo', fail)
        assert admin_host_resolves('gone.example') is False
        assert admin_host_resolves('gone.example') is False
        assert calls['n'] == 1  # cached
        pe._RESOLVE_CACHE.clear()


class TestPatchGuard:
    def _patch(self, auth_client, body):
        return auth_client.patch('/api/v2/settings/general', json=body)

    def test_unreachable_base_url_is_refused(self, auth_client, monkeypatch):
        monkeypatch.setattr(pe, 'probe_admin_base_url',
                            lambda _u: "'dead.invalid' does not resolve in DNS")
        r = self._patch(auth_client, {'base_url': 'https://dead.invalid:8443'})
        assert r.status_code == 400
        assert 'force' in r.get_json().get('message', '') or 'force' in str(r.get_json())

    def test_the_refusal_says_where_the_name_is_checked_and_what_to_do(self, auth_client,
                                                                       monkeypatch):
        # #453: a container on a network without outside DNS fails here for a valid public name
        monkeypatch.setattr(pe, 'probe_admin_base_url',
                            lambda _u: "'ucm.example.test' does not resolve in DNS")
        r = self._patch(auth_client, {'base_url': 'https://ucm.example.test'})
        assert r.status_code == 400
        message = r.get_json().get('message', '')
        assert 'from this server' in message and 'container' in message
        assert 'network alias' in message and '"force": true' in message

    def test_force_applies_anyway_and_can_be_cleared(self, auth_client, monkeypatch):
        monkeypatch.setattr(pe, 'probe_admin_base_url',
                            lambda _u: 'unreachable')
        r = self._patch(auth_client, {'base_url': 'https://dead.invalid:8443',
                                      'force': True})
        assert r.status_code == 200, r.get_json()
        # clearing never probes
        r = self._patch(auth_client, {'base_url': ''})
        assert r.status_code == 200, r.get_json()

    def test_reachable_base_url_applies_without_force(self, auth_client, monkeypatch):
        monkeypatch.setattr(pe, 'probe_admin_base_url', lambda _u: None)
        r = self._patch(auth_client, {'base_url': 'https://alive.example:8443'})
        assert r.status_code == 200, r.get_json()
        r = self._patch(auth_client, {'base_url': ''})
        assert r.status_code == 200, r.get_json()


class TestRedirectSkips:
    def test_env_kill_switch(self, app, monkeypatch):
        monkeypatch.setenv('UCM_DISABLE_CANONICAL_REDIRECT', '1')
        client = app.test_client()
        # No redirect even though the host differs from any canonical value
        r = client.get('/', headers={'Host': '198.51.100.7:8443'})
        assert r.status_code != 302
