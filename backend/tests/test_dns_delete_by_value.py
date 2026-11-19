"""delete_txt_record removes the one value it is given: other challenges share the name."""
import json
import sys

import dns.message
import dns.rcode
import dns.rdataclass
import dns.resolver
import pytest
import requests

from services.acme.dns_providers import PROVIDER_REGISTRY, create_provider
from services.acme.dns_providers.base import BaseDnsProvider

NAME = '_acme-challenge.example.com'


def test_txt_matches_reads_quoted_and_split_values():
    assert BaseDnsProvider.txt_matches('"tok"', 'tok')
    assert BaseDnsProvider.txt_matches('"to" "k"', 'tok')
    assert BaseDnsProvider.txt_matches(' tok ', 'tok')
    assert not BaseDnsProvider.txt_matches('"tok2"', 'tok')
    assert not BaseDnsProvider.txt_matches(None, 'tok')


def test_every_provider_takes_the_value():
    import inspect
    for cls in PROVIDER_REGISTRY.values():
        params = inspect.signature(cls.delete_txt_record).parameters
        assert 'record_value' in params, cls.__name__


class _Resp:
    def __init__(self, status, body=None):
        self.status_code = status
        self.reason = ''
        self.text = json.dumps(body) if body is not None else ''
        self._body = body

    def json(self):
        return self._body


# --- RFC 2136 ---------------------------------------------------------------

class FakeNameserver:
    """Applies an UPDATE message the way RFC 2136 §3.4.2 does for TXT."""

    def __init__(self):
        self.rrsets = {}

    def tcp(self, update, server, port=53, timeout=None):
        for rrset in update.update:
            name = rrset.name.to_text().rstrip('.')
            values = self.rrsets.setdefault(name, [])
            texts = [b''.join(r.strings).decode() for r in rrset]
            if rrset.deleting == dns.rdataclass.ANY:
                values.clear()
            elif rrset.deleting == dns.rdataclass.NONE:
                values[:] = [v for v in values if v not in texts]
            else:
                values.extend(t for t in texts if t not in values)
        response = dns.message.make_response(update)
        response.set_rcode(dns.rcode.NOERROR)
        return response


def test_rfc2136_deletes_one_value(monkeypatch):
    import dns.query
    ns = FakeNameserver()
    monkeypatch.setattr(dns.query, 'tcp', ns.tcp)
    monkeypatch.setattr(dns.resolver, 'resolve', lambda *a, **k: (_ for _ in ()).throw(dns.resolver.NXDOMAIN()))
    p = create_provider('rfc2136', {'server': '192.0.2.1', 'zone': 'example.com',
                                    'tsig_key_name': 'k.', 'tsig_key_secret': 'c2VjcmV0c2VjcmV0'})
    for value in ('apex', 'wild'):
        assert p.create_txt_record('example.com', NAME, value)[0]
    ok, msg = p.delete_txt_record('example.com', NAME, 'apex')
    assert ok, msg
    assert ns.rrsets[NAME] == ['wild']


# --- Cloudflare ---------------------------------------------------------------

class FakeCloudflare:
    def __init__(self):
        self.records = []
        self.next_id = 1

    def __call__(self, method, url, headers=None, json=None, params=None, timeout=None,
                 allow_redirects=True):
        path = url.split('/client/v4', 1)[1]
        ok = lambda result: _Resp(200, {'success': True, 'result': result})
        if path == '/zones':
            return ok([{'id': 'z1', 'name': 'example.com'}] if params.get('name') == 'example.com' else [])
        if path == '/zones/z1/dns_records' and method == 'GET':
            return ok([r for r in self.records if r['name'] == params['name'] and r['type'] == params['type']])
        if path == '/zones/z1/dns_records' and method == 'POST':
            rec = {'id': str(self.next_id), **json}
            self.next_id += 1
            self.records.append(rec)
            return ok(rec)
        if method == 'DELETE':
            rid = path.rsplit('/', 1)[1]
            self.records = [r for r in self.records if r['id'] != rid]
            return ok({'id': rid})
        return _Resp(404, {'success': False, 'errors': [{'message': 'not found'}]})


def test_cloudflare_deletes_one_value(monkeypatch):
    api = FakeCloudflare()
    monkeypatch.setattr(requests, 'request', api)
    p = create_provider('cloudflare', {'api_token': 'tokentoken'})
    for value in ('apex', 'wild'):
        assert p.create_txt_record('example.com', NAME, value)[0]
    ok, msg = p.delete_txt_record('example.com', NAME, 'apex')
    assert ok, msg
    assert [r['content'] for r in api.records] == ['wild']


# --- custom command and manual -------------------------------------------------

def test_custom_command_delete_receives_the_value(tmp_path):
    trace = tmp_path / 'trace'
    helper = tmp_path / 'helper.py'
    helper.write_text("import os, sys\nopen(sys.argv[1], 'a').write(os.environ['ACTION'] + '|' + os.environ['RECORD_VALUE'] + '\\n')\n")
    cmd = f'{sys.executable} {helper} {trace}'
    p = create_provider('custom_command', {'create_command': cmd, 'delete_command': cmd})
    assert p.delete_txt_record('example.com', NAME, 'apex')[0]
    assert trace.read_text() == 'delete|apex\n'


def test_manual_cleanup_names_the_value():
    ok, msg = create_provider('manual', {}).delete_txt_record('example.com', NAME, 'apex')
    assert ok and 'apex' in msg
