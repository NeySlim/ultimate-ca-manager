"""SSL certificate checker routes"""
import ipaddress
import os
import ssl
import socket
from time import monotonic

from flask import request
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.x509.oid import ExtensionOID

from auth.unified import require_auth
from utils.response import success_response, error_response
from utils.ssrf_protection import validated_addresses

from . import tools_bp, cert_to_dict, get_extension_value, logger


def _is_ip(value):
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def _vetted_addresses(hostname, port):
    """The addresses ``hostname`` resolves to, vetted once as the other outbound routes
    vet theirs (no cloud metadata, loopback, link-local or multicast); the connection
    goes to these, never to a second resolution of the name."""
    literal = f'[{hostname}]' if ':' in hostname else hostname
    # A host named in SSRF_ALLOWED_DOMAINS may be loopback or link-local, never cloud metadata
    allowed = hostname in os.getenv('SSRF_ALLOWED_DOMAINS', '').split(',')
    addresses = validated_addresses(f'https://{literal}:{port}/', allow_loopback=allowed)[1]
    for address in addresses if not allowed else ():
        ip = ipaddress.ip_address(address)
        if ip.is_link_local or ip.is_multicast:
            raise ValueError(f'{address} is a link-local or multicast address')
    return addresses


# One wait for the whole check, however many addresses the name has: connections and
# handshake share it, so unreachable addresses never stack their timeouts
CHECK_DEADLINE = 15
CONNECT_TIMEOUT = 10


def _connect(addresses, port, deadline):
    last = socket.timeout('timed out')
    for address in addresses:
        remaining = deadline - monotonic()
        if remaining <= 0:
            break
        try:
            sock = socket.create_connection((address, port), timeout=min(CONNECT_TIMEOUT, remaining))
        except OSError as exc:
            last = exc
            continue
        sock.settimeout(max(deadline - monotonic(), 0.1))  # the TLS handshake gets what is left
        return sock
    raise last


@tools_bp.route('/check-ssl', methods=['POST'])
@require_auth(['admin:system'])
def check_ssl():
    """Check SSL certificate of a remote server: an outbound probe of any host and
    port, so admin:system as the discovery scans."""
    data = request.get_json() or {}
    hostname = str(data.get('hostname') or '').strip().rstrip('.')
    port = data.get('port', 443)

    if not hostname:
        return error_response('Hostname is required', 400)

    try:
        port = int(port)
    except (TypeError, ValueError):
        port = 443
    if not 1 <= port <= 65535:
        return error_response('Port must be between 1 and 65535', 400)

    try:
        addresses = _vetted_addresses(hostname, port)
    except ValueError as exc:
        if 'Cannot resolve' in str(exc):
            return error_response(f'Could not resolve hostname: {hostname}', 400)
        return error_response('Access to this address is blocked', 403)

    try:
        # Create SSL context
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE  # We want to see invalid certs too

        # Connect to the vetted addresses; the name still goes in SNI
        sni = None if _is_ip(hostname) else hostname
        with _connect(addresses, port, monotonic() + CHECK_DEADLINE) as sock:
            with context.wrap_socket(sock, server_hostname=sni) as ssock:
                # Get certificate chain
                der_cert = ssock.getpeercert(binary_form=True)
                cert = x509.load_der_x509_certificate(der_cert, default_backend())

                # Get cipher info
                cipher = ssock.cipher()
                tls_version = ssock.version()

                # Parse certificate
                cert_info = cert_to_dict(cert)
                cert_info['hostname'] = hostname
                cert_info['port'] = port
                cert_info['cipher'] = {
                    'name': cipher[0] if cipher else None,
                    'version': cipher[1] if cipher else None,
                    'bits': cipher[2] if cipher else None
                }
                cert_info['tls_version'] = tls_version

                # Check hostname match
                san = get_extension_value(cert, ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
                hostname_match = False
                if san:
                    for name in san:
                        if isinstance(name, x509.DNSName):
                            if name.value == hostname:
                                hostname_match = True
                                break
                            # Wildcard matching
                            if name.value.startswith('*.'):
                                domain = name.value[2:]
                                if hostname.endswith(domain) and hostname.count('.') == domain.count('.') + 1:
                                    hostname_match = True
                                    break

                cert_info['hostname_match'] = hostname_match

                # Check if self-signed
                cert_info['self_signed'] = cert.subject == cert.issuer

                # Issues list
                issues = []
                if cert_info['status'] == 'expired':
                    issues.append('Certificate has expired')
                elif cert_info['status'] == 'not_yet_valid':
                    issues.append('Certificate is not yet valid')
                if not hostname_match:
                    issues.append(f'Hostname mismatch: {hostname} not in SANs')
                if cert_info['self_signed']:
                    issues.append('Self-signed certificate')
                if cert_info['days_until_expiry'] < 30 and cert_info['status'] == 'valid':
                    issues.append(f'Expires in {cert_info["days_until_expiry"]} days')

                cert_info['issues'] = issues
                cert_info['has_issues'] = len(issues) > 0

                return success_response(data=cert_info)

    except socket.timeout:
        return error_response(f'Connection timeout to {hostname}:{port}', 400)
    except socket.gaierror:
        return error_response(f'Could not resolve hostname: {hostname}', 400)
    except ConnectionRefusedError:
        return error_response(f'Connection refused by {hostname}:{port}', 400)
    except Exception as e:
        logger.error(f'SSL check failed: {e}')
        return error_response('SSL check failed', 400)
