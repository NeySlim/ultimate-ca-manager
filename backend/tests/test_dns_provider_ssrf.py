"""PowerDNS and Plesk reach the operator's URL through the pinned SSRF guard.

Their API key travels in a header of their own (X-API-Key, KEY), which requests
keeps on a redirect to another origin; the guard drops it there.
"""
import pytest

from services.acme.dns_providers.plesk import PleskDnsProvider
from services.acme.dns_providers.powerdns import PowerDnsDnsProvider


class _Answer:
    def __init__(self, status_code=200, location=None):
        self.status_code = status_code
        self.headers = {'Location': location} if location else {}
        self.text = ''
        self.reason = 'OK'
        self.content = b''

    def json(self):
        return {}

    def close(self):
        pass


@pytest.fixture
def wire(monkeypatch):
    """Every hop with its headers; the first answers a redirect to another origin."""
    import requests

    hops = []

    def _send(url, **kwargs):
        hops.append((url, dict(kwargs.get('headers') or {})))
        if len(hops) == 1:
            return _Answer(302, 'http://93.184.216.35/elsewhere')
        return _Answer(200)

    for method in ('get', 'post', 'patch'):
        monkeypatch.setattr(requests, method, lambda url, **kw: _send(url, **kw))

    def _unguarded(*_a, **_kw):
        raise AssertionError('request sent outside the SSRF guard')

    monkeypatch.setattr(requests, 'request', _unguarded)
    return hops


def test_powerdns_key_does_not_follow_a_redirect(wire):
    provider = PowerDnsDnsProvider({'server_url': 'http://93.184.216.34:8081', 'api_key': 'pdns-key'})
    provider._request('GET', '/zones')
    assert wire[0][1].get('X-API-Key') == 'pdns-key'
    assert len(wire) == 2 and 'X-API-Key' not in wire[1][1]


def test_plesk_key_does_not_follow_a_redirect(wire):
    import xml.etree.ElementTree as ET

    provider = PleskDnsProvider({'server_url': 'https://93.184.216.34:8443', 'api_key': 'plesk-key'})
    packet = ET.Element('packet')
    ET.SubElement(ET.SubElement(packet, 'webspace'), 'get')
    provider._request(packet)
    assert wire[0][1].get('KEY') == 'plesk-key'
    assert len(wire) == 2 and 'KEY' not in wire[1][1]


def test_cloud_metadata_is_refused(wire):
    provider = PowerDnsDnsProvider({'server_url': 'http://169.254.169.254', 'api_key': 'pdns-key'})
    ok, why = provider._request('GET', '/zones')
    assert ok is False and wire == [] and 'cloud metadata' in why


def test_a_server_on_the_same_host_stays_reachable(wire):
    provider = PowerDnsDnsProvider({'server_url': 'http://127.0.0.1:8081', 'api_key': 'pdns-key'})
    provider._request('GET', '/zones')
    assert wire and wire[0][0].startswith('http://127.0.0.1:8081/')
