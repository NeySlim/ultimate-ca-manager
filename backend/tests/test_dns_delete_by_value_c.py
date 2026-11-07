"""delete_txt_record removes the one value it is given: other challenges share the name."""
import json as jsonlib
import logging
import re
from urllib.parse import parse_qs

import pytest
import requests

from services.acme.dns_providers import create_provider

NAME = '_acme-challenge.example.com'


class _Resp:
    def __init__(self, status, body=None, text=None, content_type='application/json'):
        self.status_code = status
        self.reason = 'error' if status >= 400 else 'OK'
        self._body = body
        self.text = text if text is not None else (jsonlib.dumps(body) if body is not None else '')
        self.headers = {'content-type': content_type}
        self.cookies = None

    def json(self):
        return self._body


def _two_values_then_delete_one(p, domain='example.com', name=NAME):
    for value in ('apex', 'wild'):
        ok, msg = p.create_txt_record(domain, name, value)
        assert ok, msg
    return p.delete_txt_record(domain, name, 'apex')


# --- per-record APIs: list, then delete by id -----------------------------------

class FakeHover:
    """Hover: entries under /domains/{zone}/dns, deleted by /dns/{id}."""

    def __init__(self):
        self.entries = []
        self.deleted = []

    def post(self, url, data=None, timeout=None):
        return _Resp(200, {'succeeded': True})

    def request(self, method, url, json=None, timeout=None):
        path = url.removeprefix('https://www.hover.com/api')
        if path == '/domains/example.com/dns' and method == 'POST':
            self.entries.append({'id': f'dns{len(self.entries) + 1}', **json})
            return _Resp(200, {'succeeded': True})
        if path == '/domains/example.com/dns' and method == 'GET':
            return _Resp(200, {'domains': [{'entries': list(self.entries)}]})
        m = re.fullmatch(r'/dns/(\w+)', path)
        if m and method == 'DELETE':
            self.deleted.append(m.group(1))
            self.entries = [e for e in self.entries if e['id'] != m.group(1)]
            return _Resp(200, {'succeeded': True})
        return _Resp(404, {})


def test_hover_deletes_one_value(monkeypatch):
    api = FakeHover()
    monkeypatch.setattr(requests, 'Session', lambda: api)
    ok, msg = _two_values_then_delete_one(create_provider('hover', {'username': 'u', 'password': 'p'}))
    assert ok, msg
    assert api.deleted == ['dns1']
    assert [e['content'] for e in api.entries] == ['wild']


class FakeInfomaniak:
    def __init__(self):
        self.records = []
        self.deleted = []

    def __call__(self, method, url, headers=None, json=None, params=None, timeout=None):
        path = url.removeprefix('https://api.infomaniak.com')
        ok = lambda data: _Resp(200, {'result': 'success', 'data': data})
        if path == '/1/product':
            return ok([{'id': 7, 'customer_name': 'example.com'}])
        if path == '/1/domain/7/dns/record' and method == 'POST':
            rec = {'id': len(self.records) + 1, **json}
            self.records.append(rec)
            return ok(rec)
        if path == '/1/domain/7/dns/record' and method == 'GET':
            return ok(list(self.records))
        m = re.fullmatch(r'/1/domain/7/dns/record/(\d+)', path)
        if m and method == 'DELETE':
            self.deleted.append(int(m.group(1)))
            self.records = [r for r in self.records if r['id'] != int(m.group(1))]
            return ok(True)
        return _Resp(404, {'result': 'error', 'error': {'description': 'not found'}})


def test_infomaniak_deletes_one_value(monkeypatch):
    api = FakeInfomaniak()
    monkeypatch.setattr(requests, 'request', api)
    ok, msg = _two_values_then_delete_one(create_provider('infomaniak', {'api_token': 'tokentoken'}))
    assert ok, msg
    assert api.deleted == [1]
    assert [r['target'] for r in api.records] == ['wild']


class FakeInwx:
    """INWX JSON-RPC: nameserver.info lists the records of a name, deleteRecord takes an id."""

    def __init__(self):
        self.records = []
        self.deleted = []

    def __call__(self, url, json=None, timeout=None, headers=None, cookies=None):
        method, params = json['method'], json['params']
        ok = lambda data=None: _Resp(200, {'code': 1000, 'resData': data or {}})
        if method in ('account.login', 'account.logout'):
            return ok()
        if method == 'nameserver.createRecord':
            self.records.append({'id': len(self.records) + 1, 'name': params['name'],
                                 'type': params['type'], 'content': params['content']})
            return ok({'id': len(self.records)})
        if method == 'nameserver.info':
            return ok({'record': [r for r in self.records
                                  if r['name'] == params['name'] and r['type'] == params['type']]})
        if method == 'nameserver.deleteRecord':
            self.deleted.append(params['id'])
            self.records = [r for r in self.records if r['id'] != params['id']]
            return ok()
        return _Resp(200, {'code': 2303, 'msg': 'Object does not exist'})


def test_inwx_deletes_one_value(monkeypatch):
    api = FakeInwx()
    monkeypatch.setattr(requests, 'post', api)
    ok, msg = _two_values_then_delete_one(create_provider('inwx', {'username': 'u', 'password': 'p'}))
    assert ok, msg
    assert api.deleted == [1]
    assert [r['content'] for r in api.records] == ['wild']


class FakeIonos:
    """IONOS returns a TXT content quoted, as the real API does."""

    def __init__(self):
        self.records = []
        self.deleted = []

    def __call__(self, method, url, headers=None, json=None, params=None, timeout=None,
                 allow_redirects=True):
        path = url.removeprefix('https://api.hosting.ionos.com/dns/v1')
        if path == '/zones':
            return _Resp(200, [{'id': 'z1', 'name': 'example.com'}])
        if path == '/zones/z1/records' and method == 'POST':
            for rec in json:
                self.records.append({'id': f'r{len(self.records) + 1}', **rec,
                                     'content': f'"{rec["content"]}"'})
            return _Resp(201, json)
        if path == '/zones/z1' and method == 'GET':
            return _Resp(200, {'id': 'z1', 'records': list(self.records)})
        m = re.fullmatch(r'/zones/z1/records/(\w+)', path)
        if m and method == 'DELETE':
            self.deleted.append(m.group(1))
            self.records = [r for r in self.records if r['id'] != m.group(1)]
            return _Resp(200)
        return _Resp(404, {'message': 'not found'})


def test_ionos_deletes_one_value(monkeypatch):
    api = FakeIonos()
    monkeypatch.setattr(requests, 'request', api)
    ok, msg = _two_values_then_delete_one(create_provider('ionos', {'public_prefix': 'pre', 'api_key': 'secret'}))
    assert ok, msg
    assert api.deleted == ['r1']
    assert [r['content'] for r in api.records] == ['"wild"']


class FakeLinode:
    def __init__(self):
        self.records = []
        self.deleted = []

    def __call__(self, method, url, headers=None, json=None, params=None, timeout=None):
        path = url.removeprefix('https://api.linode.com/v4')
        if path == '/domains':
            return _Resp(200, {'data': [{'id': 5, 'domain': 'example.com'}]})
        if path == '/domains/5/records' and method == 'POST':
            rec = {'id': len(self.records) + 1, **json}
            self.records.append(rec)
            return _Resp(200, rec)
        if path == '/domains/5/records' and method == 'GET':
            return _Resp(200, {'data': list(self.records)})
        m = re.fullmatch(r'/domains/5/records/(\d+)', path)
        if m and method == 'DELETE':
            self.deleted.append(int(m.group(1)))
            self.records = [r for r in self.records if r['id'] != int(m.group(1))]
            return _Resp(200, {})
        return _Resp(404, {'errors': [{'reason': 'Not found'}]})


def test_linode_deletes_one_value(monkeypatch):
    api = FakeLinode()
    monkeypatch.setattr(requests, 'request', api)
    p = create_provider('linode', {'api_token': 'tokentoken'})
    for value in ('wild', 'apex'):
        assert p.create_txt_record('example.com', NAME, value)[0]
    ok, msg = p.delete_txt_record('example.com', NAME, 'apex')
    assert ok, msg
    assert api.deleted == [2]
    assert [r['target'] for r in api.records] == ['wild']


class FakeNamecom:
    def __init__(self):
        self.records = []
        self.deleted = []

    def __call__(self, method, url, auth=None, json=None, timeout=None, headers=None):
        path = url.removeprefix('https://api.name.com/v4')
        if path == '/domains/example.com' and method == 'GET':
            return _Resp(200, {'domainName': 'example.com'})
        if path == '/domains/example.com/records' and method == 'POST':
            rec = {'id': len(self.records) + 1, **json}
            self.records.append(rec)
            return _Resp(200, rec)
        if path == '/domains/example.com/records' and method == 'GET':
            return _Resp(200, {'records': list(self.records)})
        m = re.fullmatch(r'/domains/example.com/records/(\d+)', path)
        if m and method == 'DELETE':
            self.deleted.append(int(m.group(1)))
            self.records = [r for r in self.records if r['id'] != int(m.group(1))]
            return _Resp(200, {})
        return _Resp(404, {'message': 'Not Found'})


def test_namecom_deletes_one_value(monkeypatch):
    api = FakeNamecom()
    monkeypatch.setattr(requests, 'request', api)
    ok, msg = _two_values_then_delete_one(create_provider('namecom', {'username': 'u', 'api_token': 't'}))
    assert ok, msg
    assert api.deleted == [1]
    assert [r['answer'] for r in api.records] == ['wild']


class FakeNetlify:
    def __init__(self):
        self.records = []
        self.deleted = []

    def __call__(self, method, url, headers=None, json=None, timeout=None):
        path = url.removeprefix('https://api.netlify.com/api/v1')
        if path == '/dns_zones':
            return _Resp(200, [{'id': 'z1', 'name': 'example.com'}])
        if path == '/dns_zones/z1/dns_records' and method == 'POST':
            rec = {'id': f'r{len(self.records) + 1}', **json}
            self.records.append(rec)
            return _Resp(201, rec)
        if path == '/dns_zones/z1/dns_records' and method == 'GET':
            return _Resp(200, list(self.records))
        m = re.fullmatch(r'/dns_zones/z1/dns_records/(\w+)', path)
        if m and method == 'DELETE':
            self.deleted.append(m.group(1))
            self.records = [r for r in self.records if r['id'] != m.group(1)]
            return _Resp(204)
        return _Resp(404, {'message': 'Not Found'})


def test_netlify_deletes_one_value(monkeypatch):
    api = FakeNetlify()
    monkeypatch.setattr(requests, 'request', api)
    ok, msg = _two_values_then_delete_one(create_provider('netlify', {'api_token': 'tokentoken'}))
    assert ok, msg
    assert api.deleted == ['r1']
    assert [r['value'] for r in api.records] == ['wild']


# --- whole-zone APIs: read, drop the value, write the rest back ------------------

class FakeNamecheap:
    """getHosts returns the host list (namespaced, as the real API), setHosts replaces it."""

    def __init__(self):
        self.hosts = [{'Name': 'www', 'Type': 'A', 'Address': '192.0.2.10', 'TTL': '1800', 'MXPref': '10'}]
        self.sets = []
        self.get_fails = False
        self.email_type = 'MX'

    def _email_attr(self):
        return f' EmailType="{self.email_type}"' if self.email_type else ''

    def post(self, url, data=None, timeout=None):
        assert data['Command'] == 'namecheap.domains.dns.setHosts'
        return self(url, params=data, timeout=timeout)

    def __call__(self, url, params=None, timeout=None):
        cmd = params['Command']
        if cmd == 'namecheap.domains.dns.getHosts':
            if self.get_fails:
                return _Resp(200, text='<ApiResponse Status="ERROR" xmlns="http://api.namecheap.com/xml.response"><Errors><Error>Internal error</Error></Errors></ApiResponse>')
            hosts = ''.join(f'<host Name="{h["Name"]}" Type="{h["Type"]}" Address="{h["Address"]}" '
                            f'TTL="{h["TTL"]}" MXPref="{h["MXPref"]}"/>' for h in self.hosts)
            return _Resp(200, text=f'<ApiResponse Status="OK" xmlns="http://api.namecheap.com/xml.response"><CommandResponse><DomainDNSGetHostsResult Domain="example.com"{self._email_attr()} IsUsingOurDNS="true">'
                                   f'{hosts}</DomainDNSGetHostsResult></CommandResponse></ApiResponse>')
        if cmd == 'namecheap.domains.dns.setHosts':
            self.sets.append(dict(params))
            self.email_type = params.get('EmailType', 'NONE')  # setHosts without it resets mail
            hosts, i = [], 1
            while f'HostName{i}' in params:
                hosts.append({'Name': params[f'HostName{i}'], 'Type': params[f'RecordType{i}'],
                              'Address': params[f'Address{i}'], 'TTL': params[f'TTL{i}'],
                              'MXPref': params.get(f'MXPref{i}', '10')})
                i += 1
            self.hosts = hosts
            return _Resp(200, text='<ApiResponse Status="OK" xmlns="http://api.namecheap.com/xml.response"/>')
        return _Resp(200, text='<ApiResponse Status="ERROR" xmlns="http://api.namecheap.com/xml.response"><Errors><Error>bad command</Error></Errors></ApiResponse>')


def _namecheap(monkeypatch):
    api = FakeNamecheap()
    monkeypatch.setattr(requests, 'get', lambda url, params=None, timeout=None: api(
        url, params=params, timeout=timeout) if params['Command'] != 'namecheap.domains.dns.setHosts'
        else pytest.fail('setHosts sent as GET'))
    monkeypatch.setattr(requests, 'post', api.post)
    return api, create_provider('namecheap', {'api_user': 'u', 'api_key': 'k', 'client_ip': '198.51.100.1'})


def test_namecheap_deletes_one_value(monkeypatch):
    api, p = _namecheap(monkeypatch)
    ok, msg = _two_values_then_delete_one(p)
    assert ok, msg
    assert [(h['Name'], h['Address'], h['TTL']) for h in api.hosts] == \
        [('www', '192.0.2.10', '1800'), ('_acme-challenge', 'wild', '1800')]


def test_namecheap_keeps_the_mail_setting(monkeypatch):
    api, p = _namecheap(monkeypatch)
    _two_values_then_delete_one(p)
    assert api.sets and all(s['EmailType'] == 'MX' for s in api.sets)
    assert api.email_type == 'MX'


def test_namecheap_sends_mx_when_the_answer_omits_the_mail_setting(monkeypatch):
    api, p = _namecheap(monkeypatch)
    api.email_type = None
    api.hosts.append({'Name': '@', 'Type': 'MX', 'Address': 'mail.example.com', 'TTL': '1800', 'MXPref': '10'})
    assert p.create_txt_record('example.com', NAME, 'apex')[0]
    assert api.sets[-1]['EmailType'] == 'MX'
    assert ('@', 'MX') in [(h['Name'], h['Type']) for h in api.hosts]


def test_namecheap_failed_read_writes_nothing(monkeypatch):
    api, p = _namecheap(monkeypatch)
    api.get_fails = True
    assert not p.create_txt_record('example.com', NAME, 'apex')[0]
    assert not p.delete_txt_record('example.com', NAME, 'apex')[0]
    assert api.sets == []
    assert [h['Name'] for h in api.hosts] == ['www']


class FakeNetcup:
    """updateDnsRecords applies the submitted records: id + deleterecord deletes, no id creates."""

    def __init__(self):
        self.records = [{'id': '1', 'hostname': 'www', 'type': 'A', 'destination': '192.0.2.10',
                         'priority': '', 'state': 'yes'}]
        self.updates = []

    def __call__(self, url, json=None, timeout=None, headers=None):
        action, param = json['action'], json['param']
        ok = lambda data=None: _Resp(200, {'status': 'success', 'responsedata': data or {}})
        if action == 'login':
            return ok({'apisessionid': 'sess'})
        if action == 'logout':
            return ok()
        if action == 'infoDnsRecords':
            return ok({'dnsrecords': [dict(r) for r in self.records]})
        if action == 'updateDnsRecords':
            sent = param['dnsrecordset']['dnsrecords']
            self.updates.append(sent)
            for rec in sent:
                if rec.get('deleterecord'):
                    self.records = [r for r in self.records if r['id'] != rec['id']]
                elif not rec.get('id'):
                    self.records.append({**rec, 'id': str(len(self.records) + 10)})
            return ok()
        return _Resp(200, {'status': 'error', 'longmessage': 'unknown action'})


def test_netcup_deletes_one_value(monkeypatch):
    api = FakeNetcup()
    monkeypatch.setattr(requests, 'post', api)
    p = create_provider('netcup', {'customer_number': '1', 'api_key': 'k', 'api_password': 'p'})
    ok, msg = _two_values_then_delete_one(p)
    assert ok, msg
    flagged = [r['destination'] for r in api.updates[-1] if r.get('deleterecord')]
    assert flagged == ['apex']
    assert [(r['hostname'], r['destination']) for r in api.records] == \
        [('www', '192.0.2.10'), ('_acme-challenge', 'wild')]


# --- Hurricane Electric: one value per name, no read: whole-name cleanup, said aloud ---

def test_hurricane_warns_that_cleanup_clears_the_name(monkeypatch, caplog):
    sent = []
    monkeypatch.setattr(requests, 'post', lambda url, data=None, timeout=None: sent.append(data) or _Resp(200, text='good'))
    p = create_provider('hurricane', {'password': 'ddnskey'})
    with caplog.at_level(logging.WARNING, logger='services.acme.dns_providers.hurricane'):
        ok, msg = p.delete_txt_record('example.com', NAME, 'apex')
    assert ok, msg
    assert sent == [{'hostname': NAME, 'password': 'ddnskey', 'txt': ''}]
    assert any('every TXT value' in r.getMessage() for r in caplog.records)


def test_hurricane_refused_clear_is_false(monkeypatch):
    monkeypatch.setattr(requests, 'post', lambda url, data=None, timeout=None: _Resp(200, text='badauth'))
    p = create_provider('hurricane', {'password': 'ddnskey'})
    ok, msg = p.delete_txt_record('example.com', NAME, 'apex')
    assert not ok and 'badauth' in msg
