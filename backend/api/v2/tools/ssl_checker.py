"""SSL certificate checker routes"""
import ssl
import socket

from flask import request
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.x509.oid import ExtensionOID

from auth.unified import require_auth
from utils.response import success_response, error_response

from . import tools_bp, cert_to_dict, get_extension_value, is_safe_host, logger


@tools_bp.route('/check-ssl', methods=['POST'])
@require_auth()
def check_ssl():
    """Check SSL certificate of a remote server"""
    data = request.get_json() or {}
    hostname = data.get('hostname', '').strip()
    port = data.get('port', 443)

    if not hostname:
        return error_response('Hostname is required', 400)

    # SSRF Protection
    if not is_safe_host(hostname):
        return error_response('Access to private/local network resources is blocked', 403)

    try:
        port = int(port)
    except (TypeError, ValueError):
        port = 443

    try:
        # Create SSL context
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE  # We want to see invalid certs too

        # Connect
        with socket.create_connection((hostname, port), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
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
