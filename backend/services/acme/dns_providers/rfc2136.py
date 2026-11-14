"""
RFC2136 (Dynamic DNS Update) Provider
Uses nsupdate protocol for BIND, Knot, PowerDNS, etc.
Requires dnspython library (dns.update, dns.tsigkeyring)
"""
import base64
import binascii
import ipaddress
import logging
import socket
from typing import Tuple, Dict, Any, Optional

import fips_mode
from fips_mode import FipsRestricted

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class Rfc2136DnsProvider(BaseDnsProvider):
    PROVIDER_TYPE = "rfc2136"
    PROVIDER_NAME = "RFC2136 (nsupdate)"
    PROVIDER_DESCRIPTION = "Dynamic DNS Update (BIND, Knot, PowerDNS)"
    REQUIRED_CREDENTIALS = ["server", "tsig_key_name", "tsig_key_secret"]

    @classmethod
    def validate_credentials(cls, credentials):
        # hashlib and hmac fall back to CPython's MD5, so only UCM can refuse it
        if str(credentials.get('tsig_algorithm') or '').strip().lower() == 'hmac-md5':
            fips_mode.refuse('TSIG hmac-md5')

    @classmethod
    def refuse_short_secret(cls, credentials):
        """At save time, in FIPS mode: a TSIG secret under 14 bytes is not an HMAC key the module takes."""
        text = credentials.get('tsig_key_secret')
        if not isinstance(text, str) or not text.strip():
            return
        try:
            secret = base64.b64decode(text.strip(), validate=True)
        except (ValueError, binascii.Error):
            return  # not base64: dnspython refuses it with its own error
        fips_mode.refuse_short_hmac_key(secret, 'TSIG key secret')

    def _get_keyring(self):
        """Create TSIG keyring for authentication."""
        self.validate_credentials(self.credentials)
        try:
            import dns.tsigkeyring
            algo = self.credentials.get('tsig_algorithm', 'hmac-sha256')
            algo_map = {
                'hmac-md5': 'HMAC-MD5.SIG-ALG.REG.INT',
                'hmac-sha1': 'hmac-sha1',
                'hmac-sha256': 'hmac-sha256',
                'hmac-sha384': 'hmac-sha384',
                'hmac-sha512': 'hmac-sha512',
            }
            dns_algo = algo_map.get(algo.lower(), 'hmac-sha256')
            keyring = dns.tsigkeyring.from_text({
                self.credentials['tsig_key_name']: self.credentials['tsig_key_secret']
            })
            return keyring, dns_algo
        except ImportError:
            return None, None
    
    def _port(self) -> int:
        return int(self.credentials.get('port') or 53)

    def _addresses(self):
        """Addresses of the configured server: dnspython only connects to an IP."""
        server = str(self.credentials['server']).strip()
        try:
            return [str(ipaddress.ip_address(server))]
        except ValueError:
            pass
        found = []
        for info in socket.getaddrinfo(server, self._port(), type=socket.SOCK_STREAM):
            if info[4][0] not in found:
                found.append(info[4][0])
        return found

    def _send(self, message, timeout=30):
        """TCP exchange with the configured server, trying each of its addresses
        within one overall timeout (an unreachable AAAA times out, it does not refuse)."""
        import dns.exception
        import dns.query
        failure = OSError(f"no address for {self.credentials['server']}")
        addresses = self._addresses()
        for address in addresses:
            try:
                return dns.query.tcp(message, address, port=self._port(),
                                     timeout=timeout / len(addresses))
            except (OSError, dns.exception.Timeout) as exc:
                failure = exc
        raise failure

    @staticmethod
    def _reason(exc) -> str:
        return str(exc) or type(exc).__name__

    def _zone_from_server(self, domain: str) -> Optional[str]:
        """Zone of ``domain`` per the configured server's authoritative SOA (RFC 2136 §4)."""
        try:
            import dns.message
            import dns.rcode
            import dns.rdatatype
            import dns.flags
            query = dns.message.make_query(domain, 'SOA')
            keyring, algo = self._get_keyring()
            if keyring:
                query.use_tsig(keyring=keyring, algorithm=algo)
            response = self._send(query, timeout=10)
        except Exception as exc:
            logger.info("RFC2136: SOA lookup of %s on the server failed: %s", domain, self._reason(exc))
            return None
        if response.rcode() not in (dns.rcode.NOERROR, dns.rcode.NXDOMAIN) or not (
                response.flags & dns.flags.AA):
            return None
        for rrset in list(response.answer) + list(response.authority):
            if rrset.rdtype == dns.rdatatype.SOA:
                return rrset.name.to_text(omit_final_dot=True)
        return None

    def _find_zone(self, domain: str) -> Optional[str]:
        """The configured zone when it contains the name, else the one the configured
        server is authoritative for (one provider may serve several zones)."""
        configured = str(self.credentials.get('zone') or '').strip().rstrip('.').lower()
        name = domain.rstrip('.').lower()
        if configured and (name == configured or name.endswith('.' + configured)):
            return configured
        zone = self._zone_from_server(domain)
        if zone:
            return zone
        try:
            import dns.resolver
            domain_parts = domain.split('.')
            for i in range(len(domain_parts) - 1):
                zone_name = '.'.join(domain_parts[i:])
                try:
                    dns.resolver.resolve(zone_name, 'SOA')
                    return zone_name
                except Exception:
                    continue
        except ImportError:
            pass
        parts = domain.split('.')
        if len(parts) >= 2:
            return '.'.join(parts[-2:])
        return domain
    
    def create_txt_record(self, domain: str, record_name: str, record_value: str, ttl: int = 300) -> Tuple[bool, str]:
        try:
            import dns.update
            import dns.query
            import dns.name
        except ImportError:
            return False, "dnspython not installed. Run: pip install dnspython"
        
        zone = self._find_zone(domain)
        if not zone:
            return False, f"Could not determine zone for {domain}"
        
        try:
            keyring, algo = self._get_keyring()
        except FipsRestricted as e:
            return False, str(e)
        if keyring is None:
            return False, "Failed to create TSIG keyring"
        
        try:
            update = dns.update.Update(zone, keyring=keyring, keyalgorithm=algo)
            update.add(dns.name.from_text(record_name), ttl, 'TXT', record_value)
            response = self._send(update)
            rcode = response.rcode()
            if rcode == 0:
                return True, "Record created successfully"
            return False, f"DNS update failed with rcode {rcode}"
        except Exception as e:
            return False, f"DNS update failed: {self._reason(e)}"
    
    def delete_txt_record(self, domain: str, record_name: str, record_value: str) -> Tuple[bool, str]:
        try:
            import dns.update
            import dns.query
            import dns.name
        except ImportError:
            return False, "dnspython not installed"
        
        zone = self._find_zone(domain)
        if not zone:
            return False, f"Could not determine zone for {domain}"
        
        try:
            keyring, algo = self._get_keyring()
        except FipsRestricted as e:
            return False, str(e)
        if keyring is None:
            return False, "Failed to create TSIG keyring"
        
        try:
            update = dns.update.Update(zone, keyring=keyring, keyalgorithm=algo)
            # Class NONE delete of this one RR (RFC 2136 §2.5.4): other values stay
            update.delete(dns.name.from_text(record_name), 'TXT', record_value)
            response = self._send(update)
            rcode = response.rcode()
            if rcode == 0:
                return True, "Record deleted successfully"
            return False, f"DNS update failed with rcode {rcode}"
        except Exception as e:
            return False, f"DNS update failed: {self._reason(e)}"
    
    def test_connection(self) -> Tuple[bool, str]:
        try:
            import dns.query
            import dns.message
        except ImportError:
            return False, "dnspython not installed. Run: pip install dnspython"
        
        server = self.credentials['server']
        port = self._port()

        try:
            # Send a simple SOA query to verify connectivity
            zone = self.credentials.get('zone') or 'example.com'
            query = dns.message.make_query(zone, 'SOA')
            keyring, algo = self._get_keyring()
            if keyring:
                query.use_tsig(keyring=keyring, algorithm=algo)
            self._send(query, timeout=10)
            return True, f"Connected to DNS server {server}:{port}"
        except Exception as e:
            return False, f"Connection failed: {self._reason(e)}"
    
    @classmethod
    def get_credential_schema(cls):
        return [
            {'name': 'server', 'label': 'DNS Server', 'type': 'text', 'required': True,
             'help': 'IP or hostname of the authoritative DNS server'},
            {'name': 'port', 'label': 'Port', 'type': 'text', 'required': False, 'default': '53'},
            {'name': 'zone', 'label': 'Zone', 'type': 'text', 'required': False,
             'help': 'DNS zone (auto-detected if empty)'},
            {'name': 'tsig_key_name', 'label': 'TSIG Key Name', 'type': 'text', 'required': True,
             'help': 'e.g. acme-update.example.com'},
            {'name': 'tsig_key_secret', 'label': 'TSIG Key Secret', 'type': 'password', 'required': True,
             'help': 'Base64-encoded TSIG secret'},
            {'name': 'tsig_algorithm', 'label': 'TSIG Algorithm', 'type': 'select', 'required': False,
             'default': 'hmac-sha256',
             'options': [
                 {'value': 'hmac-sha256', 'label': 'HMAC-SHA256'},
                 {'value': 'hmac-sha512', 'label': 'HMAC-SHA512'},
                 {'value': 'hmac-sha384', 'label': 'HMAC-SHA384'},
                 {'value': 'hmac-sha1', 'label': 'HMAC-SHA1'},
             ] + ([] if fips_mode.enabled() else [{'value': 'hmac-md5', 'label': 'HMAC-MD5'}])},
        ]
