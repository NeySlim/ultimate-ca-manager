"""Certificate format conversion routes"""
import base64
import os
import tempfile

from flask import request
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

from auth.unified import require_auth
from utils.response import success_response, error_response

from . import tools_bp, logger


@tools_bp.route('/convert', methods=['POST'])
@require_auth()
def convert_certificate():
    """Convert certificate/key between formats

    Uses SmartParser (same engine as Smart Import) for input detection.
    Supports input: PEM, DER, PKCS12/PFX, PKCS7/P7B
    Supports output: PEM, DER, PKCS12, PKCS7
    """
    from services.smart_import.parser import SmartParser, ObjectType

    data = request.get_json() or {}
    input_data = data.get('pem', '').strip()
    output_format = data.get('output_format', 'pem')
    password = data.get('password', '') or None
    pkcs12_password = data.get('pkcs12_password', '')
    chain_pem = data.get('chain', '').strip()
    key_pem = data.get('private_key', '').strip()

    if not input_data:
        return error_response('Input data is required', 400)

    try:
        import subprocess

        parser = SmartParser()

        # Decode binary input if BASE64: prefixed (from file upload)
        is_binary = input_data.startswith('BASE64:')
        if is_binary:
            raw_input = base64.b64decode(input_data[7:])
        else:
            raw_input = input_data

        # Guard rail: binary files (PKCS12/PFX) require a password
        if is_binary and not password:
            # Check if it looks like PKCS12 (starts with ASN.1 SEQUENCE)
            is_likely_pkcs12 = isinstance(raw_input, bytes) and len(raw_input) > 4 and raw_input[0] == 0x30
            # Try DER cert/key first — those don't need passwords
            test_objects = parser.parse(raw_input, password=None)
            if not test_objects and is_likely_pkcs12:
                return error_response('Password is required for PKCS12/PFX files', 400)

        # Parse with SmartParser — same engine as certificate import page
        objects = parser.parse(raw_input, password=password)
        if not objects and password:
            objects = parser.parse(raw_input, password=None)

        # Parse additional key if provided separately
        if key_pem:
            if key_pem.startswith('BASE64:'):
                key_input = base64.b64decode(key_pem[7:])
            else:
                key_input = key_pem
            key_objects = parser.parse(key_input, password=password)
            objects.extend([o for o in key_objects if o.type == ObjectType.PRIVATE_KEY])

        # Load crypto objects from parsed PEM/DER
        certs = []
        keys = []
        csrs = []

        for obj in objects:
            try:
                if obj.type == ObjectType.CERTIFICATE:
                    if obj.raw_pem:
                        certs.append(x509.load_pem_x509_certificate(obj.raw_pem.encode(), default_backend()))
                    elif obj.raw_der:
                        certs.append(x509.load_der_x509_certificate(obj.raw_der, default_backend()))
                elif obj.type == ObjectType.PRIVATE_KEY:
                    if obj.raw_pem:
                        keys.append(serialization.load_pem_private_key(obj.raw_pem.encode(), password=None, backend=default_backend()))
                    elif obj.raw_der:
                        keys.append(serialization.load_der_private_key(obj.raw_der, password=None, backend=default_backend()))
                elif obj.type == ObjectType.CSR:
                    if obj.raw_pem:
                        csrs.append(x509.load_pem_x509_csr(obj.raw_pem.encode(), default_backend()))
                    elif obj.raw_der:
                        csrs.append(x509.load_der_x509_csr(obj.raw_der, default_backend()))
            except Exception as e:
                logger.warning(f'Converter: failed to load {obj.type} object: {e}')

        # Parse chain certs
        chain_certs = []
        if chain_pem:
            for obj in parser.parse(chain_pem):
                if obj.type == ObjectType.CERTIFICATE and obj.raw_pem:
                    try:
                        chain_certs.append(x509.load_pem_x509_certificate(obj.raw_pem.encode(), default_backend()))
                    except Exception:
                        pass

        if not certs and not keys and not csrs:
            return error_response('Could not parse input data. Supported formats: PEM, DER, PKCS12, PKCS7', 400)

        detected_format = 'pem' if isinstance(raw_input, str) else 'binary'
        result = {}

        # Convert to requested output format
        if output_format == 'pem':
            pem_parts = []
            for cert in certs:
                pem_parts.append(cert.public_bytes(serialization.Encoding.PEM).decode())
            for key in keys:
                enc = serialization.NoEncryption()
                pem_parts.append(key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=enc
                ).decode())
            for csr in csrs:
                pem_parts.append(csr.public_bytes(serialization.Encoding.PEM).decode())

            result = {
                'format': 'pem',
                'data': '\n'.join(pem_parts),
                'filename': 'converted.pem',
                'detected_format': detected_format,
                'contents': {
                    'certificates': len(certs),
                    'private_keys': len(keys),
                    'csrs': len(csrs)
                }
            }

        elif output_format == 'der':
            # DER can only contain one object
            if certs:
                der_data = certs[0].public_bytes(serialization.Encoding.DER)
                filename = 'certificate.der'
            elif keys:
                der_data = keys[0].private_bytes(
                    encoding=serialization.Encoding.DER,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption()
                )
                filename = 'private_key.der'
            elif csrs:
                der_data = csrs[0].public_bytes(serialization.Encoding.DER)
                filename = 'request.der'
            else:
                return error_response('No data to convert to DER', 400)

            result = {
                'format': 'der',
                'data': base64.b64encode(der_data).decode(),
                'filename': filename,
                'detected_format': detected_format
            }

        elif output_format == 'pkcs12':
            if not certs:
                return error_response('Certificate is required for PKCS12 output', 400)
            if not keys:
                return error_response('Private key is required for PKCS12 output', 400)
            if not pkcs12_password:
                return error_response('Password is required for PKCS12 output', 400)

            # Use first cert and key
            cert = certs[0]
            key = keys[0]

            # Additional certs (rest of certs + chain)
            ca_certs = certs[1:] + chain_certs if len(certs) > 1 or chain_certs else None

            p12_pwd = pkcs12_password.encode() if pkcs12_password else None
            p12_data = serialization.pkcs12.serialize_key_and_certificates(
                name=b"certificate",
                key=key,
                cert=cert,
                cas=ca_certs,
                encryption_algorithm=serialization.BestAvailableEncryption(p12_pwd) if p12_pwd else serialization.NoEncryption()
            )

            result = {
                'format': 'pkcs12',
                'data': base64.b64encode(p12_data).decode(),
                'filename': 'certificate.p12',
                'detected_format': detected_format
            }

        elif output_format == 'pkcs7':
            if not certs:
                return error_response('At least one certificate is required for PKCS7', 400)

            # Build PEM with all certs
            all_certs_pem = ''
            for cert in certs + chain_certs:
                all_certs_pem += cert.public_bytes(serialization.Encoding.PEM).decode()

            # Use OpenSSL to create PKCS7
            with tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False) as f:
                f.write(all_certs_pem)
                temp_pem = f.name

            try:
                p7_data = subprocess.check_output([
                    'openssl', 'crl2pkcs7', '-nocrl', '-certfile', temp_pem
                ], timeout=30)
                result = {
                    'format': 'pkcs7',
                    'data': p7_data.decode(),
                    'filename': 'certificates.p7b',
                    'detected_format': detected_format
                }
            finally:
                os.unlink(temp_pem)

        elif output_format == 'jks':
            if not certs:
                return error_response('Certificate is required for JKS output', 400)
            if not keys:
                return error_response('Private key is required for JKS output', 400)
            if not pkcs12_password:
                return error_response('Password is required for JKS output', 400)

            import jks as pyjks
            import time as _time

            cert = certs[0]
            key = keys[0]
            ts = int(_time.time() * 1000)

            cert_der = cert.public_bytes(serialization.Encoding.DER)
            key_pkcs8 = key.private_bytes(
                serialization.Encoding.DER,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption()
            )

            cert_chain = [("X.509", cert_der)]
            for ca_cert in (certs[1:] + chain_certs):
                cert_chain.append(("X.509", ca_cert.public_bytes(serialization.Encoding.DER)))

            pke = pyjks.PrivateKeyEntry(
                alias='certificate',
                cert_chain=cert_chain,
                pkey_pkcs8=key_pkcs8,
                timestamp=ts,
            )

            keystore = pyjks.KeyStore.new("jks", [pke])
            jks_bytes = keystore.saves(pkcs12_password)

            result = {
                'format': 'jks',
                'data': base64.b64encode(jks_bytes).decode(),
                'filename': 'certificate.jks',
                'detected_format': detected_format
            }

        else:
            return error_response(f'Unknown output format: {output_format}', 400)

        return success_response(data=result)

    except Exception as e:
        logger.error(f'Conversion failed: {e}')
        return error_response('Conversion failed', 400)
