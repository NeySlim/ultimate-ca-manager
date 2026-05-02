"""CSR and certificate decode routes"""
import base64

from flask import request
from cryptography import x509
from cryptography.hazmat.backends import default_backend

from auth.unified import require_auth
from utils.response import success_response, error_response

from . import tools_bp, csr_to_dict, cert_to_dict, logger


@tools_bp.route('/decode-csr', methods=['POST'])
@require_auth()
def decode_csr():
    """Decode a CSR and return its contents"""
    data = request.get_json() or {}
    pem_data = data.get('pem', '').strip()

    if not pem_data:
        return error_response('CSR data is required', 400)

    try:
        csr = None

        # Check for BASE64-encoded binary (DER)
        if pem_data.startswith('BASE64:'):
            raw_bytes = base64.b64decode(pem_data[7:])
            csr = x509.load_der_x509_csr(raw_bytes, default_backend())
        else:
            # Try to load as PEM
            if '-----BEGIN' not in pem_data:
                pem_data = f"-----BEGIN CERTIFICATE REQUEST-----\n{pem_data}\n-----END CERTIFICATE REQUEST-----"
            csr = x509.load_pem_x509_csr(pem_data.encode(), default_backend())

        result = csr_to_dict(csr)
        return success_response(data=result)

    except Exception as e:
        logger.error(f'Failed to decode CSR: {e}')
        return error_response('Failed to decode CSR', 400)


@tools_bp.route('/decode-cert', methods=['POST'])
@require_auth()
def decode_cert():
    """Decode a certificate and return its contents"""
    data = request.get_json() or {}
    pem_data = data.get('pem', '').strip()

    if not pem_data:
        return error_response('Certificate data is required', 400)

    try:
        certs = []

        # Check for BASE64-encoded binary (DER)
        if pem_data.startswith('BASE64:'):
            raw_bytes = base64.b64decode(pem_data[7:])
            # Try DER certificate first
            try:
                certs = [x509.load_der_x509_certificate(raw_bytes, default_backend())]
            except Exception:
                pass
            # Try PKCS7 DER
            if not certs:
                try:
                    from cryptography.hazmat.primitives.serialization import pkcs7
                    certs = pkcs7.load_der_pkcs7_certificates(raw_bytes)
                except Exception:
                    pass
            # Try PKCS12
            if not certs:
                try:
                    from cryptography.hazmat.primitives.serialization import pkcs12 as p12mod
                    _, cert, chain = p12mod.load_key_and_certificates(raw_bytes, None)
                    if cert:
                        certs = [cert]
                    if chain:
                        certs.extend(chain)
                except Exception:
                    pass
        else:
            # Try PEM certificate
            try:
                if '-----BEGIN CERTIFICATE-----' in pem_data:
                    certs = [x509.load_pem_x509_certificate(pem_data.encode(), default_backend())]
                elif '-----BEGIN PKCS7-----' in pem_data:
                    from cryptography.hazmat.primitives.serialization import pkcs7
                    certs = pkcs7.load_pem_pkcs7_certificates(pem_data.encode())
                else:
                    # Try wrapping as PEM cert
                    wrapped = f"-----BEGIN CERTIFICATE-----\n{pem_data}\n-----END CERTIFICATE-----"
                    certs = [x509.load_pem_x509_certificate(wrapped.encode(), default_backend())]
            except Exception:
                pass

        if not certs:
            return error_response('Failed to decode certificate. Supported formats: PEM, DER, PKCS7, PKCS12', 400)

        # Return first cert details, plus chain info if multiple
        result = cert_to_dict(certs[0])
        if len(certs) > 1:
            result['chain'] = [cert_to_dict(c) for c in certs[1:]]
        return success_response(data=result)

    except Exception as e:
        logger.error(f'Failed to decode certificate: {e}')
        return error_response('Failed to decode certificate', 400)
