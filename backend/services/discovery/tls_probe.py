"""
TLS probing mixin — connects to host:port and extracts certificate info.
"""
import socket
import ssl
import hashlib
import ipaddress
import logging
from typing import Dict

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization

from .helpers import _is_blocked_ip

logger = logging.getLogger(__name__)


class TLSProbeMixin:

    def probe_tls(self, host: str, port: int = 443, timeout: int = None,
                  resolve_dns: bool = False, sni_hostname: str = None) -> Dict:
        """Connect to host:port via TLS and return certificate info.
        If sni_hostname is set, connect to host but use sni_hostname for TLS SNI.
        For IP targets, avoids sending IP as SNI per RFC 6066.
        On TLSV1_UNRECOGNIZED_NAME, retries without SNI then with PTR hostname."""
        connect_timeout = timeout or self.timeout
        result = {'target': host, 'port': port}
        if sni_hostname:
            result['sni_hostname'] = sni_hostname

        # Determine SNI strategy: don't send IP addresses as SNI (RFC 6066)
        is_ip = False
        try:
            ipaddress.ip_address(host)
            is_ip = True
        except ValueError:
            pass

        # SSRF protection: block scans to loopback/link-local/multicast
        if is_ip and _is_blocked_ip(host):
            result['error'] = 'Target IP is in a restricted range'
            result['error_type'] = 'blocked'
            return result

        if sni_hostname:
            sni_attempts = [sni_hostname]
        elif is_ip:
            # For IPs: try without SNI first, then with PTR hostname
            sni_attempts = [None]
            try:
                ptr_host, _, _ = socket.gethostbyaddr(host)
                if ptr_host and ptr_host != host:
                    # SEC-06: Validate PTR hostname resolves back to same IP (anti-rebinding)
                    try:
                        resolved = socket.getaddrinfo(ptr_host, None)[0][4][0]
                        if resolved == host:
                            sni_attempts.append(ptr_host)
                        else:
                            logger.debug(f"PTR rebinding blocked: {ptr_host} resolves to {resolved}, expected {host}")
                    except (socket.gaierror, OSError):
                        pass
            except (socket.herror, socket.gaierror, OSError):
                pass
        else:
            # For hostnames: resolve and check SSRF before connecting
            try:
                resolved = socket.getaddrinfo(host, port)[0][4][0]
                if _is_blocked_ip(resolved):
                    result['error'] = 'Target hostname resolves to a restricted IP'
                    result['error_type'] = 'blocked'
                    return result
            except (socket.gaierror, OSError):
                pass  # Let the connection attempt handle DNS errors
            sni_attempts = [host]

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        last_error = None
        for sni in sni_attempts:
            try:
                with socket.create_connection((host, port), timeout=connect_timeout) as sock:
                    kwargs = {}
                    if sni:
                        kwargs['server_hostname'] = sni
                    with ctx.wrap_socket(sock, **kwargs) as tls:
                        der = tls.getpeercert(binary_form=True)
                        if not der:
                            result['error'] = 'No certificate returned'
                            result['error_type'] = 'no_cert'
                            return result

                        cert = x509.load_der_x509_certificate(der)
                        pem = cert.public_bytes(serialization.Encoding.PEM).decode()
                        fp = hashlib.sha256(der).hexdigest().upper()

                        # Extract SANs
                        san_dns = []
                        san_ips = []
                        san_emails = []
                        san_uris = []
                        try:
                            san_ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
                            san_dns = san_ext.value.get_values_for_type(x509.DNSName)
                            san_ips = [str(ip) for ip in san_ext.value.get_values_for_type(x509.IPAddress)]
                            san_emails = san_ext.value.get_values_for_type(x509.RFC822Name)
                            san_uris = san_ext.value.get_values_for_type(x509.UniformResourceIdentifier)
                        except x509.ExtensionNotFound:
                            pass

                        result.update({
                            'subject': cert.subject.rfc4514_string(),
                            'issuer': cert.issuer.rfc4514_string(),
                            'serial_number': format(cert.serial_number, 'X'),
                            'not_before': cert.not_valid_before_utc.isoformat(),
                            'not_after': cert.not_valid_after_utc.isoformat(),
                            'fingerprint_sha256': fp,
                            'pem_certificate': pem,
                            'san_dns_names': san_dns,
                            'san_ip_addresses': san_ips,
                            'san_emails': san_emails,
                            'san_uris': san_uris,
                        })

                # Reverse DNS resolution
                if resolve_dns and not sni_hostname:
                    try:
                        hostname, _, _ = socket.gethostbyaddr(host)
                        if hostname and hostname != host:
                            result['dns_hostname'] = hostname
                    except (socket.herror, socket.gaierror, OSError):
                        pass

                return result  # Success — stop retrying

            except ssl.SSLError as e:
                if 'TLSV1_UNRECOGNIZED_NAME' in str(e):
                    last_error = e
                    logger.debug(f"TLS probe {host}:{port} SNI={sni}: unrecognized name, trying next")
                    continue  # Try next SNI strategy
                result['error'] = str(e)
                result['error_type'] = 'tls'
                return result
            except ConnectionRefusedError:
                result['error'] = 'Connection refused'
                result['error_type'] = 'refused'
                return result
            except socket.timeout:
                result['error'] = 'Connection timed out'
                result['error_type'] = 'timeout'
                return result
            except socket.gaierror as e:
                result['error'] = f'DNS resolution failed: {e}'
                result['error_type'] = 'dns'
                return result
            except OSError as e:
                result['error'] = str(e)
                result['error_type'] = 'network'
                return result
            except Exception as e:
                logger.debug(f"TLS probe {host}:{port} (SNI={sni}) failed: {e}")
                result['error'] = str(e)
                result['error_type'] = 'tls'
                return result

        # All SNI attempts failed with UNRECOGNIZED_NAME
        if last_error:
            result['error'] = 'TLS handshake rejected (server requires specific hostname/SNI)'
            result['error_type'] = 'sni_rejected'
        return result
