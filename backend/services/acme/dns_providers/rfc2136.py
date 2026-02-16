"""
RFC2136 (Dynamic DNS Update) Provider
Uses nsupdate protocol for BIND, Knot, PowerDNS, etc.
Requires dnspython library (dns.update, dns.tsigkeyring)
"""
import logging
from typing import Tuple, Dict, Any, Optional

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class Rfc2136DnsProvider(BaseDnsProvider):
    PROVIDER_TYPE = "rfc2136"
    PROVIDER_NAME = "RFC2136 (nsupdate)"
    PROVIDER_DESCRIPTION = "Dynamic DNS Update (BIND, Knot, PowerDNS)"
    REQUIRED_CREDENTIALS = ["server", "tsig_key_name", "tsig_key_secret"]
    
    def _get_keyring(self):
        """Create TSIG keyring for authentication."""
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
    
    def _find_zone(self, domain: str) -> Optional[str]:
        """Find the zone for a domain by trying SOA queries."""
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
        # Fallback: use configured zone or guess from domain
        zone = self.credentials.get('zone')
        if zone:
            return zone
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
        
        keyring, algo = self._get_keyring()
        if keyring is None:
            return False, "Failed to create TSIG keyring"
        
        server = self.credentials['server']
        port = int(self.credentials.get('port', 53))
        
        try:
            update = dns.update.Update(zone, keyring=keyring, keyalgorithm=algo)
            update.add(dns.name.from_text(record_name), ttl, 'TXT', record_value)
            response = dns.query.tcp(update, server, port=port, timeout=30)
            rcode = response.rcode()
            if rcode == 0:
                return True, "Record created successfully"
            return False, f"DNS update failed with rcode {rcode}"
        except Exception as e:
            return False, f"DNS update failed: {e}"
    
    def delete_txt_record(self, domain: str, record_name: str) -> Tuple[bool, str]:
        try:
            import dns.update
            import dns.query
            import dns.name
        except ImportError:
            return False, "dnspython not installed"
        
        zone = self._find_zone(domain)
        if not zone:
            return False, f"Could not determine zone for {domain}"
        
        keyring, algo = self._get_keyring()
        if keyring is None:
            return False, "Failed to create TSIG keyring"
        
        server = self.credentials['server']
        port = int(self.credentials.get('port', 53))
        
        try:
            update = dns.update.Update(zone, keyring=keyring, keyalgorithm=algo)
            update.delete(dns.name.from_text(record_name), 'TXT')
            response = dns.query.tcp(update, server, port=port, timeout=30)
            rcode = response.rcode()
            if rcode == 0:
                return True, "Record deleted successfully"
            return False, f"DNS update failed with rcode {rcode}"
        except Exception as e:
            return False, f"DNS update failed: {e}"
    
    def test_connection(self) -> Tuple[bool, str]:
        try:
            import dns.query
            import dns.message
        except ImportError:
            return False, "dnspython not installed. Run: pip install dnspython"
        
        server = self.credentials['server']
        port = int(self.credentials.get('port', 53))
        
        try:
            # Send a simple SOA query to verify connectivity
            zone = self.credentials.get('zone', 'example.com')
            query = dns.message.make_query(zone, 'SOA')
            keyring, algo = self._get_keyring()
            if keyring:
                query.use_tsig(keyring=keyring, algorithm=algo)
            response = dns.query.tcp(query, server, port=port, timeout=10)
            return True, f"Connected to DNS server {server}:{port}"
        except Exception as e:
            return False, f"Connection failed: {e}"
    
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
                 {'value': 'hmac-md5', 'label': 'HMAC-MD5'},
             ]},
        ]
