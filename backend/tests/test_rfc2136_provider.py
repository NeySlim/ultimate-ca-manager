"""RFC 2136 DNS provider against a local authoritative server: a server given by
name, the configured zone, SOA discovery on that server, readable errors."""
import socket
import socketserver
import struct
import threading

import dns.flags
import dns.message
import dns.name
import dns.opcode
import dns.rcode
import dns.rdataclass
import dns.rdatatype
import dns.resolver
import dns.rrset
import dns.tsigkeyring
import pytest

from services.acme.dns_providers import create_provider

ZONE = 'int.example.test'
NAME = f'_acme-challenge.host.{ZONE}'
KEY_NAME = 'acme-key.'
SECRET = 'c2VjcmV0c2VjcmV0c2VjcmV0c2VjcmV0'
KEYRING = dns.tsigkeyring.from_text({KEY_NAME: SECRET})


class _Handler(socketserver.BaseRequestHandler):
    def handle(self):
        while True:
            head = self._read(2)
            if not head:
                return
            wire = self._read(struct.unpack('!H', head)[0])
            message = dns.message.from_wire(wire, keyring=KEYRING)
            response = dns.message.make_response(message)
            if message.opcode() == dns.opcode.UPDATE:
                self.server.updates.append(str(message.zone[0].name))
            else:
                self._answer_soa(message, response)
            out = response.to_wire()
            self.request.sendall(struct.pack('!H', len(out)) + out)

    def _answer_soa(self, message, response):
        qname = message.question[0].name
        zone = dns.name.from_text(ZONE)
        if not self.server.answer_soa or not qname.is_subdomain(zone):
            response.set_rcode(dns.rcode.REFUSED)
            return
        response.flags |= dns.flags.AA
        soa = dns.rrset.from_text(zone, 300, 'IN', 'SOA',
                                  f'ns.{ZONE}. admin.{ZONE}. 1 3600 600 86400 300')
        (response.answer if qname == zone else response.authority).append(soa)

    def _read(self, size):
        data = b''
        while len(data) < size:
            chunk = self.request.recv(size - len(data))
            if not chunk:
                return b''
            data += chunk
        return data



@pytest.fixture
def nameserver():
    server = socketserver.ThreadingTCPServer(('127.0.0.1', 0), _Handler)
    server.daemon_threads = True
    server.updates = []
    server.answer_soa = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


@pytest.fixture
def public_parent_zone(monkeypatch):
    """The system resolver only sees the public parent zone (split horizon)."""
    def _resolve(name, rdtype='A', *_a, **_k):
        if rdtype == 'SOA' and str(name).rstrip('.') == 'example.test':
            return object()
        raise dns.resolver.NXDOMAIN()
    monkeypatch.setattr(dns.resolver, 'resolve', _resolve)


def _provider(server, port, zone=''):
    return create_provider('rfc2136', {
        'server': server, 'port': str(port), 'zone': zone,
        'tsig_key_name': KEY_NAME, 'tsig_key_secret': SECRET,
    })


def _loopback_name():
    """A host name that resolves to 127.0.0.1 here."""
    for name in ('localhost', socket.gethostname()):
        try:
            if any(info[4][0] == '127.0.0.1' for info in socket.getaddrinfo(name, 53)):
                return name
        except OSError:
            continue
    pytest.skip('no host name resolves to 127.0.0.1')


class TestServerByName:
    def test_update_reaches_a_server_given_by_name(self, nameserver, public_parent_zone):
        port = nameserver.server_address[1]
        ok, message = _provider(_loopback_name(), port, ZONE).create_txt_record(
            f'host.{ZONE}', NAME, 'value')
        assert ok, message
        assert nameserver.updates == [f'{ZONE}.']

    def test_connection_test_accepts_a_server_name(self, nameserver):
        ok, message = _provider(_loopback_name(), nameserver.server_address[1], ZONE).test_connection()
        assert ok, message

    def test_failure_message_is_never_empty(self, monkeypatch):
        import dns.query
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            closed_port = sock.getsockname()[1]
        ok, message = _provider(_loopback_name(), closed_port, ZONE).create_txt_record(
            f'host.{ZONE}', NAME, 'value')
        assert not ok and message.split(':', 1)[1].strip()

        def _silent(*_a, **_k):
            raise ValueError()
        monkeypatch.setattr(dns.query, 'tcp', _silent)
        ok, message = _provider('127.0.0.1', closed_port, ZONE).create_txt_record(
            f'host.{ZONE}', NAME, 'value')
        assert not ok and message.split(':', 1)[1].strip()


class TestZone:
    def test_configured_zone_wins_over_the_system_resolver(self, nameserver, public_parent_zone):
        nameserver.answer_soa = False
        ok, message = _provider('127.0.0.1', nameserver.server_address[1], ZONE).create_txt_record(
            f'host.{ZONE}', NAME, 'value')
        assert ok, message
        assert nameserver.updates == [f'{ZONE}.']

    def test_empty_zone_is_found_on_the_configured_server(self, nameserver, public_parent_zone):
        ok, message = _provider('127.0.0.1', nameserver.server_address[1]).create_txt_record(
            f'host.{ZONE}', NAME, 'value')
        assert ok, message
        assert nameserver.updates == [f'{ZONE}.']

    def test_delete_uses_the_same_zone(self, nameserver, public_parent_zone):
        ok, message = _provider('127.0.0.1', nameserver.server_address[1], ZONE).delete_txt_record(
            f'host.{ZONE}', NAME, 'value')
        assert ok, message
        assert nameserver.updates == [f'{ZONE}.']
