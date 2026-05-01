"""
CAs Export Operations
"""

from . import bp
from flask import request, Response, g
import base64
import subprocess
import tempfile
import os
import logging

from auth.unified import require_auth, has_permission
from utils.response import success_response, error_response
from utils.sanitize import sanitize_filename
from utils.datetime_utils import utc_isoformat
from models import CA, Certificate, db
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from security.encryption import decrypt_private_key

logger = logging.getLogger(__name__)


@bp.route('/api/v2/cas/export', methods=['GET', 'POST'])
@require_auth(['read:cas'])
def export_all_cas():
    """Export all CA certificates in various formats"""
    
    if request.method == 'POST' and request.is_json:
        data = request.get_json()
        export_format = data.get('format', 'pem').lower()
    else:
        export_format = request.args.get('format', 'pem').lower()
    
    cas = CA.query.filter(CA.crt.isnot(None)).all()
    if not cas:
        return error_response('No CAs to export', 404)
    
    try:
        if export_format == 'pem':
            pem_data = b''
            for ca in cas:
                if ca.crt:
                    pem_data += base64.b64decode(ca.crt)
                    if not pem_data.endswith(b'\n'):
                        pem_data += b'\n'
            
            return Response(
                pem_data,
                mimetype='application/x-pem-file',
                headers={'Content-Disposition': 'attachment; filename="ca-certificates.pem"'}
            )
        
        elif export_format == 'pkcs7' or export_format == 'p7b':
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.pem', delete=False) as f:
                for ca in cas:
                    if ca.crt:
                        f.write(base64.b64decode(ca.crt))
                        f.write(b'\n')
                pem_file = f.name
            
            try:
                p7b_output = subprocess.check_output([
                    'openssl', 'crl2pkcs7', '-nocrl',
                    '-certfile', pem_file,
                    '-outform', 'DER'
                ], stderr=subprocess.DEVNULL, timeout=30)
                
                return Response(
                    p7b_output,
                    mimetype='application/x-pkcs7-certificates',
                    headers={'Content-Disposition': 'attachment; filename="ca-certificates.p7b"'}
                )
            finally:
                os.unlink(pem_file)
        
        else:
            return error_response(f'Bulk export only supports PEM and P7B formats. Use individual export for DER/PKCS12/PFX', 400)
    
    except Exception as e:
        logger.error(f"Export failed: {e}")
        return error_response('Export failed', 500)


@bp.route('/api/v2/cas/<int:ca_id>/export', methods=['GET', 'POST'])
@require_auth(['read:cas'])
def export_ca(ca_id):
    """
    Export CA certificate in various formats
    
    Params (query or POST body):
        format: pem (default), der, pkcs12
        include_key: bool - Include private key
        include_chain: bool - Include parent CA chain
        password: string - Required for PKCS12
    """
    
    ca = CA.query.get(ca_id)
    if not ca:
        return error_response('CA not found', 404)
    
    if not ca.crt:
        return error_response('CA certificate data not available', 400)
    
    if request.method == 'POST' and request.is_json:
        data = request.get_json()
        export_format = data.get('format', 'pem').lower()
        include_key = bool(data.get('include_key', False))
        include_chain = bool(data.get('include_chain', False))
        password = data.get('password')
    else:
        export_format = request.args.get('format', 'pem').lower()
        include_key = request.args.get('include_key', 'false').lower() == 'true'
        include_chain = request.args.get('include_chain', 'false').lower() == 'true'
        password = request.args.get('password')
    
    # Private key export requires write permission (operator+)
    if include_key or export_format in ('pkcs12', 'pfx', 'key', 'jks'):
        if not has_permission('write:cas', g.permissions):
            return error_response('Private key export requires write:cas permission', 403)
        # HSM-backed CAs cannot export their private key — it never leaves the HSM
        if ca.uses_hsm:
            return error_response('Cannot export HSM-backed key', 409)
    
    try:
        cert_pem = base64.b64decode(ca.crt)
        
        # Private key only export
        if export_format == 'key':
            if not ca.prv:
                return error_response('CA has no private key', 400)
            key_pem = base64.b64decode(decrypt_private_key(ca.prv))
            if password:
                private_key = serialization.load_pem_private_key(key_pem, password=None, backend=default_backend())
                key_pem = private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.BestAvailableEncryption(password.encode())
                )
            return Response(
                key_pem,
                mimetype='application/x-pem-file',
                headers={'Content-Disposition': f'attachment; filename="{sanitize_filename(ca.descr or ca.refid)}.key"'}
            )
        
        if export_format == 'pem':
            result = cert_pem
            content_type = 'application/x-pem-file'
            filename = f"{sanitize_filename(ca.descr or ca.refid)}.crt"
            
            # Include private key if requested
            if include_key and ca.prv:
                key_pem = base64.b64decode(decrypt_private_key(ca.prv))
                if not result.endswith(b'\n'):
                    result += b'\n'
                result += key_pem
                filename = f"{sanitize_filename(ca.descr or ca.refid)}_with_key.pem"
            
            # Include parent CA chain if requested
            if include_chain and ca.caref:
                parent = CA.query.filter_by(refid=ca.caref).first()
                while parent:
                    if parent.crt:
                        parent_cert = base64.b64decode(parent.crt)
                        if not result.endswith(b'\n'):
                            result += b'\n'
                        result += parent_cert
                    if parent.caref:
                        parent = CA.query.filter_by(refid=parent.caref).first()
                    else:
                        break
                if include_key:
                    filename = f"{sanitize_filename(ca.descr or ca.refid)}_full_chain.pem"
                else:
                    filename = f"{sanitize_filename(ca.descr or ca.refid)}_chain.pem"
            
            return Response(
                result,
                mimetype=content_type,
                headers={'Content-Disposition': f'attachment; filename="{filename}"'}
            )
        
        elif export_format == 'der':
            
            cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
            der_bytes = cert.public_bytes(serialization.Encoding.DER)
            
            return Response(
                der_bytes,
                mimetype='application/x-x509-ca-cert',
                headers={'Content-Disposition': f'attachment; filename="{sanitize_filename(ca.descr or ca.refid)}.der"'}
            )
        
        elif export_format == 'pkcs12':
            if not password:
                return error_response('Password required for PKCS12 export', 400)
            if not ca.prv:
                return error_response('CA has no private key for PKCS12 export', 400)
            
            cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
            key_pem = base64.b64decode(decrypt_private_key(ca.prv))
            private_key = serialization.load_pem_private_key(key_pem, password=None, backend=default_backend())
            
            # Build parent CA chain if available and requested
            ca_certs = []
            if include_chain and ca.caref:
                parent = CA.query.filter_by(refid=ca.caref).first()
                while parent:
                    if parent.crt:
                        parent_cert = x509.load_pem_x509_certificate(
                            base64.b64decode(parent.crt), default_backend()
                        )
                        ca_certs.append(parent_cert)
                    if parent.caref:
                        parent = CA.query.filter_by(refid=parent.caref).first()
                    else:
                        break

            p12_bytes = pkcs12.serialize_key_and_certificates(
                name=(ca.descr or ca.refid).encode(),
                key=private_key,
                cert=cert,
                cas=ca_certs if ca_certs else None,
                encryption_algorithm=serialization.BestAvailableEncryption(password.encode())
            )
            
            return Response(
                p12_bytes,
                mimetype='application/x-pkcs12',
                headers={'Content-Disposition': f'attachment; filename="{sanitize_filename(ca.descr or ca.refid)}.p12"'}
            )
        
        elif export_format == 'pkcs7' or export_format == 'p7b':
            
            # Create temporary PEM file with CA chain
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.pem', delete=False) as f:
                f.write(cert_pem)
                # Include parent chain
                if include_chain and ca.caref:
                    parent = CA.query.filter_by(refid=ca.caref).first()
                    while parent:
                        if parent.crt:
                            f.write(b'\n')
                            f.write(base64.b64decode(parent.crt))
                        if parent.caref:
                            parent = CA.query.filter_by(refid=parent.caref).first()
                        else:
                            break
                pem_file = f.name
            
            try:
                p7b_output = subprocess.check_output([
                    'openssl', 'crl2pkcs7', '-nocrl',
                    '-certfile', pem_file,
                    '-outform', 'DER'
                ], stderr=subprocess.DEVNULL, timeout=30)
                
                return Response(
                    p7b_output,
                    mimetype='application/x-pkcs7-certificates',
                    headers={'Content-Disposition': f'attachment; filename="{sanitize_filename(ca.descr or ca.refid)}.p7b"'}
                )
            finally:
                os.unlink(pem_file)
        
        elif export_format == 'pfx':
            # PFX is same as PKCS12
            if not password:
                return error_response('Password required for PFX export', 400)
            if not ca.prv:
                return error_response('CA has no private key for PFX export', 400)
            
            cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
            key_pem_data = base64.b64decode(decrypt_private_key(ca.prv))
            private_key = serialization.load_pem_private_key(key_pem_data, password=None, backend=default_backend())
            
            # Build parent CA chain if available and requested
            ca_certs = []
            if include_chain and ca.caref:
                parent = CA.query.filter_by(refid=ca.caref).first()
                while parent:
                    if parent.crt:
                        parent_cert = x509.load_pem_x509_certificate(
                            base64.b64decode(parent.crt), default_backend()
                        )
                        ca_certs.append(parent_cert)
                    if parent.caref:
                        parent = CA.query.filter_by(refid=parent.caref).first()
                    else:
                        break

            p12_bytes = pkcs12.serialize_key_and_certificates(
                name=(ca.descr or ca.refid).encode(),
                key=private_key,
                cert=cert,
                cas=ca_certs if ca_certs else None,
                encryption_algorithm=serialization.BestAvailableEncryption(password.encode())
            )
            
            return Response(
                p12_bytes,
                mimetype='application/x-pkcs12',
                headers={'Content-Disposition': f'attachment; filename="{sanitize_filename(ca.descr or ca.refid)}.pfx"'}
            )
        
        elif export_format == 'jks':
            if not password:
                return error_response('Password required for JKS export', 400)
            if not ca.prv:
                return error_response('CA has no private key for JKS export', 400)

            import jks as pyjks
            import time

            cert_obj = x509.load_pem_x509_certificate(cert_pem, default_backend())
            key_pem_data = base64.b64decode(decrypt_private_key(ca.prv))
            private_key = serialization.load_pem_private_key(key_pem_data, password=None, backend=default_backend())

            cert_der = cert_obj.public_bytes(serialization.Encoding.DER)
            key_pkcs8 = private_key.private_bytes(
                serialization.Encoding.DER,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption()
            )

            cert_chain = [("X.509", cert_der)]

            if include_chain and ca.caref:
                parent = CA.query.filter_by(refid=ca.caref).first()
                while parent:
                    if parent.crt:
                        parent_cert = x509.load_pem_x509_certificate(
                            base64.b64decode(parent.crt), default_backend()
                        )
                        cert_chain.append(("X.509", parent_cert.public_bytes(serialization.Encoding.DER)))
                    if parent.caref:
                        parent = CA.query.filter_by(refid=parent.caref).first()
                    else:
                        break

            ts = int(time.time() * 1000)
            pke = pyjks.PrivateKeyEntry(
                alias=(ca.descr or ca.refid).lower().replace(' ', '-'),
                cert_chain=cert_chain,
                pkey_pkcs8=key_pkcs8,
                timestamp=ts,
            )

            keystore = pyjks.KeyStore.new("jks", [pke])
            jks_bytes = keystore.saves(password)

            return Response(
                jks_bytes,
                mimetype='application/x-java-keystore',
                headers={'Content-Disposition': f'attachment; filename="{sanitize_filename(ca.descr or ca.refid)}.jks"'}
            )

        else:
            return error_response(f'Unsupported format: {export_format}', 400)
    
    except Exception as e:
        logger.error(f"Export failed: {e}")
        return error_response('Export failed', 500)
